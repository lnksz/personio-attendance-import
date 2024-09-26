# Personio Attendance Import

I find Personio's current solutions for attendence recording very limited. (As of 2023.)
The app on android isn't stable, and the web app is very limited in functionality. (No start/stop.)

On the other hand there are tools just for this purpose, like Toggl.com. Which do a much better job at this.
It would be of course nice if Toggl and Personio would integrate out of the box, but currently this isn't the case.

So here a poor man's solution to import Toggl entries into Personio.
(But could be useful to anyone, as the main part is the import into Personio, the input could be adapted to other tool exports.)

At the end of the day you can "transfer" your attendence from Toggl to Personio by

```bash
./log-today.sh
```

# Configuration

The script expects a `config.py` file next to it, from which it can read out `PROFILE_ID, EMAIL` and other potentially sensitive information.

Before running the app create on such file.

```python
# Personio credentials
EMAIL = 'me@corp.org'
PASSWORD = os.environ['PERSO_PASS']
PROFILE_ID = 123456  # This can be found in your personio profile URL

# Toggl Configuration
TOGGL_WORKSPACE = 123123
TOGGL_EMAIL = 'me@corp.com'
TOGGL_PASSWORD = os.environ['TOGGL_PASS']

# Personio Configuration
HOST = "https://corp.personio.de"
LOGIN_URL = f"{HOST}/login/index"
ATTENDANCE_URL = f'{HOST}/api/v1/attendances/days'
PROJECTS_URL = f'{HOST}/api/v1/projects?filter[active]=1'

# Project Mapping (define as an empty tuple if not used)
# You can query the project list using PROJECTS_URL
PROJECTS_MAPPING = group_mapping = (
        # Personio   Internal/from toggl
        ("12345",   "ABC123"), # Product X Development
        ("67890",   "XYZ987"), # Product X Production
    )
```

If you want to use the wrapper scripts `log-*`, then it is required, that you store your secrets with
[pass](https://www.passwordstore.org/) "the standard Unix password manager".

# Using the script

You can use a virtual environment to install dependencies and execute in it.

For the first time, create a Python virtual environment to install dependencies:

```python
python -m venv venv
. venv/bin/activate
python -m pip install -r requirements.txt
```

Then import from a detailed Toggl report (CSV)

```bash
./log-file.sh Toggl_time_entries.csv
# or directly
python main.py -i Toggl_time_entries.csv
```

Or log today's enries from Toggl:

```bash
./log-today.sh
# or directly
python main.py
```

for help see

```bash
python main.py -h
```

# Input: Toggl Export

I use the detailed report from Toggl, which is available both through UI and API.
If the data is exported through the tool and if there is a timer running,
the running timer will be stopped.

UI: https://track.toggl.com/reports/detailed/

API exploration, documented in [API](https://engineering.toggl.com/docs/)

```
export TU=MyToggleUser
export TP=MyTogglePassword

curl  https: //api.track.toggl.com/api/v9/me \
  -H "Content-Type: application/json" \
  -u "${TU}:${TP}"
# Response
{
  ...
  "default_workspace_id": 345345,
  ...
}

export WID=345345
curl -X POST https://api.track.toggl.com/reports/api/v3/workspace/$WID/search/time_entries.csv \
  -H "Content-Type: application/json" \
  -d '{"start_date": "2024-04-10", "end_date":"2024-04-11", "grouped":false,"order_by":"date","order_dir":"ASC", "hide_amounts":true}' \
  -u "${TU}:${TP}"
```

# Output: Personio API

This boils down to
- Authentication with a session
- Parsing out the XSRF token from the response
- Sending attendance data with UUIDs and right formatting

## API Analysis

Captured traffic from the Personio site and real user interaction.

Uppon each entry into a time field, the day data is sent to the server for validation and calculation.
`api/v1/attendances/employees/{{employee-id}}/validate-and-calculate-full-day`

Interesting is that here already a `uuid` is sent for the day.

### Get list of projects

```
GET /api/v1/projects?filter[active]=1 HTTP/2
Host: gmbh.personio.de
User-Agent: Mozilla/5.0
Accept: application/json, text/plain, */*
Accept-Language: en-US,en;q=0.5
Accept-Encoding: gzip, deflate, br
X-CSRF-Token: TOKEN1
X-XSRF-TOKEN: TOKEN1
...
Connection: keep-alive
Referer: https://gmbh.personio.de/attendance/employee/1234567/2023-03
Cookie: personio_browser_id=ABBA; personio_session=SESSION; _dd_s=rum=1&id=73fb67db-05ae-4298-a6a9-854ede2ecf3c&created=1678692957670&expire=1678696854223; ... XSRF-TOKEN=TOKEN
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
```

**Response**

Relevant parts:
```json
{
    "success": true,
    "data": [
        {
            "id": 1234,
            "type": "project",
            "attributes": {
                "company_id": 4321,
                "name": " Some Project",
                "active": true,
                "created_at": "2022-03-21T16:47:04Z",
                "updated_at": "2022-03-21T16:47:13Z"
            }
        }
    ]
}
```

Here the project IDs are `numbers`, but in the attendance request,
the project id is passed in as a `string`!

```json
"project_id":"79286"
```

### Attendance requests

Clicking on the calendar, and in the popup modal during adding start, end etc.

#### Validations before submission

**Request**

(not all Headers included)
```
POST https://gmbh.personio.de/api/v1/attendances/employees/1234567/validate-and-calculate-full-day

POST /api/v1/attendances/employees/1234567/validate-and-calculate-full-day HTTP/2
Host: gmbh.personio.de
User-Agent: Mozilla/5.0
Accept: application/json, text/plain, */*
Accept-Language: en-US,en;q=0.5
Accept-Encoding: gzip, deflate, br
Content-Type: application/json
X-CSRF-Token: TOKEN1
X-XSRF-TOKEN: TOKEN1
Content-Length: 198
Origin: https://gmbh.personio.de
Connection: keep-alive
Referer: https://gmbh.personio.de/attendance/employee/1234567/2023-03
Cookie: personio_browser_id=ABBA; personio_session=BEEF; ... XSRF-TOKEN=TOKEN1
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
TE: trailers
```
with body:

```json
{
    "attendance_day_id": "02218ad5-c89f-497e-b377-b561873eca93",
    "periods": [
        {
            "attendance_period_id": "95fd3082-5aec-4d36-8db6-458086c84555",
            "start": "2023-03-03 00:00:00",
            "end": "2023-03-03 00:30:00",
            "period_type": "work"
        },
        {
            "attendance_period_id": "e86a4664-f242-4a08-9584-b9893f4da318",
            "start": "2023-03-03 00:15:00",
            "end": "2023-03-03 00:20:00",
            "period_type": "break"
        }
    ]
}
```

**Response**

```json
{
    "success": true,
    "data": {
        "success": true,
        "work_duration_in_min": 25,
        "break_duration_in_min": 5,
        "alerts": []
    }
}
```

`attendence_day_id` is calculated and `attendence_period_id` is calculated.
origiantor for the request was `validate-and-calculate-full-day` from app.js

#### Submitting the form

This is done by a `PUT` request where the URL includes the days UUID.

Notes:
- for time always the `Z` timezone is used, even if the user is in a different timezone.
- Project ID is a string, not a number (like in the response for projects)
- Periods also have their own UUIDs
- Project ID and comments can be `null`


**Request**

```
PUT /api/v1/attendances/days/02218ad5-c89f-497e-b377-b561873eca93 HTTP/2
Host: gmbh.personio.de
User-Agent: Mozilla/5.0
Accept: application/json, text/plain, */*
Accept-Language: en-US,en;q=0.5
Accept-Encoding: gzip, deflate, br
Content-Type: application/json
X-CSRF-Token: TOKEN1
X-XSRF-TOKEN: TOKEN1
Content-Length: 401
Origin: https://gmbh.personio.de
Connection: keep-alive
Referer: https://gmbh.personio.de/attendance/employee/1234567/2023-03
XSRF-TOKEN=TOKEN1
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
TE: trailers
```

Body:

```json
{
    "employee_id": 1234567,
    "periods": [
        {
            "id": "95fd3082-5aec-4d36-8db6-458086c84555",
            "project_id": "79281",
            "period_type": "work",
            "legacy_break_min": 0,
            "comment": null,
            "start": "2023-03-03T00:00:00Z",
            "end": "2023-03-03T00:30:00Z"
        },
        {
            "id": "e86a4664-f242-4a08-9584-b9893f4da318",
            "project_id": null,
            "period_type": "break",
            "legacy_break_min": 0,
            "comment": null,
            "start": "2023-03-03T00:15:00Z",
            "end": "2023-03-03T00:25:00Z"
        }
    ]
}
```

**Response**

```json
{
    "employee_id": 1234567,
    "periods": [
        {
            "id": "95fd3082-5aec-4d36-8db6-458086c84555",
            "project_id": "79281",
            "period_type": "work",
            "legacy_break_min": 0,
            "comment": null,
            "start": "2023-03-03T00:00:00Z",
            "end": "2023-03-03T00:30:00Z"
        },
        {
            "id": "e86a4664-f242-4a08-9584-b9893f4da318",
            "project_id": null,
            "period_type": "break",
            "legacy_break_min": 0,
            "comment": null,
            "start": "2023-03-03T00:15:00Z",
            "end": "2023-03-03T00:25:00Z"
        }
    ]
}
```

#### Exploring UUIDs for day and period

Each day has a UUID generated most probably by the client.
This ID is then needed to create entries per day.

For each day each entry also has a UUID.
It turns out that this can be simply generated by python's UUID1 function.

```python
import uuid
print(str(uuid.uuid1()))
```

If we send a period which is outside of the day, referenced by the day UUID,
the API will return an error.

```json
{
    "success": false,
    "error": {
        "code": 400,
        "message": "Client error: `PUT http://time-management-attendance-api/companies/69632/days/02218ad5-c89f-497e-b377-b561873eca93` resulted in a `400 Bad Request` response:\n{\"errors\":[{\"id\":\"158ad8bb-b96a-43ff-80d2-8e83720b4f99\",\"status\":\"400\",\"title\":\"This period does not belong to the day\"} (truncated...)\n"
    }
}
```

BUT one can simpy generate a uuid1 for the day and create it immediately with the periods,
*IF* there isn't already a UUID assigned for that day.

**How to get the id for the day if there is already on??? Good question!**

