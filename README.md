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
HOST = "https://efr-gmbh.app.personio.com"
ATTENDANCE_URL = f"{HOST}/svc/attendance-api/v1/days"
PROJECTS_URL = f'{HOST}/api/v1/projects?filter[active]=1'
LOGIN_URL = "https://login.personio.com/u/login/identifier"
COMPANY_HASH = "longhash after email prompt, see 'state' in URL"

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

Use `uv` to run the script.

Then import from a detailed Toggl report (CSV)

```bash
./log-file.sh Toggl_time_entries.csv
```

Or log today's enries from Toggl:

```bash
./log-today.sh
# or directly
uv run main.py
```

for help see

```bash
uv run main.py -h
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
- Authentication via the login page
- Sending attendance data with UUIDs and right formatting and tokens

## API Analysis

Captured traffic from the Personio site and real user interaction.

Uppon each entry into a time field, the day data is sent to the server for validation and calculation.
`api/v1/attendances/employees/{{employee-id}}/validate-and-calculate-full-day`

Interesting is that here already a `uuid` is sent for the day.

### Login

After chasing personio's login via API calls for a while, I resorted to logging
in via the GUI through playwright. The API alone was way too brittle.

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
POST /svc/attendance-api/validate-and-calculate-full-day?propose-fix=false HTTP/2
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
    "attendance_day_id": "9b52c9d9-2405-4d3f-b61f-876d3c528b3f",
    "employee_id": 1234567,
    "periods": [
        {
            "attendance_period_id": "5a0462cc-b273-4b15-a472-5b5f7926f45d",
            "end": "2025-02-12 08:30:00",
            "period_type": "work",
            "start": "2025-02-12 12:00:00",
            "comment": null,
            "project_id": null
        },
        {
            "attendance_period_id": "7607a368-8b0e-4918-9f78-cae122c0852c",
            "end": "2025-02-12 18:00:00",
            "period_type": "work",
            "start": "2025-02-12 13:00:00",
            "comment": null,
            "project_id": 123456
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
PUT /svc/attendance-api/v1/days/9b52c9d9-2405-4d3f-b61f-876d3c528b3f HTTP/2
Host: gmbh.personio.de
User-Agent: Mozilla/5.0
Accept: application/json, text/plain, */*
Accept-Language: en-US,en;q=0.5
Accept-Encoding: gzip, deflate, br
Content-Type: application/json
XSRF-TOKEN=TOKEN1
X-CSRF-Token: TOKEN2
X-XSRF-TOKEN: TOKEN2
X-ATHENA-XSRF-TOKEN: TOKEN3
Cookie: personio_browser_id=id1; ATHENA-XSRF-TOKEN=TOKEN3; personio_session=TOKEN2; ATHENA_SESSION=session2; XSRF-TOKEN=TOKEN1
Content-Length: 401
Origin: https://gmbh.personio.de
Connection: keep-alive
Referer: https://gmbh.personio.de/attendance/employee/1234567/2023-03
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
            "id": "5a0462cc-b273-4b15-a472-5b5f7926f45d",
            "comment": null,
            "period_type": "work",
            "project_id": null,
            "start": "2025-02-12T08:30:00",
            "end": "2025-02-12T12:00:00"
        },
        {
            "id": "7607a368-8b0e-4918-9f78-cae122c0852c",
            "comment": null,
            "period_type": "work",
            "project_id": 123456,
            "start": "2025-02-12T13:00:00",
            "end": "2025-02-12T18:00:00"
        }
    ],
    "geolocation": null
}
```

**Response**

```json
{
    "success": true,
    "data": [
        {
            "id": "9b52c9d9-2405-4d3f-b61f-876d3c528b3f",
            "type": "attendancedays",
            "attributes": {
                "employee_id": 1234567,
                "company_id": 12345,
                "status": "complete",
                "day": "2025-02-12",
                "break_min": 60,
                "duration": ,
                "count_periods": 4,
                "rejection_reason": null,
                "rules_violation_reason": null,
                "created_at": "2025-02-12 18:01:00",
                "updated_at": "2025-02-12 18:01:00"
            },
            "relationships": {
                "periods": {
                    "data": [
                        {
                            "type": "attendanceperiods",
                            "id": "5a0462cc-b273-4b15-a472-5b5f7926f45d"
                        },
                        {
                            "type": "attendanceperiods",
                            "id": "7607a368-8b0e-4918-9f78-cae122c0852c"
                        },
                        {
                            "type": "attendanceperiods",
                            "id": "d62279ed-76d0-4b78-b295-1fc28f965384"
                        },
                        {
                            "type": "attendanceperiods",
                            "id": "9f4ffd48-7f16-47aa-bd34-f623b3766cac"
                        }
                    ]
                }
            }
        }
    ],
    "included": [
        {
            "type": "attendanceperiods",
            "id": "5a0462cc-b273-4b15-a472-5b5f7926f45d",
            "attributes": {
                "legacy_id": null,
                "legacy_status": "pending",
                "start": "2025-02-12T08:38:00.000Z",
                "end": "2025-02-12T08:58:00.000Z",
                "period_type": "work",
                "comment": null,
                "legacy_break_min": 0,
                "origin": "web",
                "project_id": null,
                "created_at": "2025-02-12 17:29:34",
                "updated_at": "2025-02-12 17:29:34"
            }
        },
        {
            "type": "attendanceperiods",
            "id": "7607a368-8b0e-4918-9f78-cae122c0852c",
            "attributes": {
                "legacy_id": null,
                "legacy_status": "pending",
                "start": "2025-02-12T09:00:00.000Z",
                "end": "2025-02-12T12:00:00.000Z",
                "period_type": "work",
                "comment": null,
                "legacy_break_min": 0,
                "origin": "web",
                "project_id": 536429,
                "created_at": "2025-02-12 17:29:34",
                "updated_at": "2025-02-12 17:29:34"
            }
        },
        {},
        {}
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

