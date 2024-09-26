#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests",
# ]
# ///

from base64 import b64encode
import datetime
import json
import uuid
import logging
import requests
import argparse
import os
# Own modules
import models

try:
    from config import (
        ATTENDANCE_URL,
        LOGIN_URL,
        PROJECTS_URL,
        EMAIL,
        PASSWORD,
        PROFILE_ID,
        PROJECTS_MAPPING,
        TOGGL_WORKSPACE,
        TOGGL_EMAIL,
        TOGGL_PASSWORD,
    )
except ImportError:
    print("WARNING: no config.py found. Please create one!")
    exit(1)


def login(url: str, email: str, password: str) -> list[requests.Session, str]:
    session = requests.Session()

    first_response = session.post(
        url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"email": email, "password": password},
    )
    logging.info('Login')
    logging.debug(f'{str(first_response.headers)}\n{first_response.text}\n')
    set_cookie = first_response.headers["set-cookie"]
    token = set_cookie.split()[0].split('=')[1].rstrip(';')
    logging.debug(f'CSRF: {set_cookie}')
    logging.debug(f"CSRF: {token}")

    return session, token


def get_projects(session: requests.Session) -> requests.Response:
    response = session.get(PROJECTS_URL, headers={"Accept": "application/json"})
    logging.debug('Projects:')
    logging.debug(response.headers, '\n', response.text)
    return response


def get_toggl_detailed_report_csv(
    start_date: str,
    end_date: str,
    email: str,
    password: str,
    workspace_id: int,
) -> str:
    auth = b64encode(f"{email}:{password}".encode()).decode("ascii")
    out_csv = f"Toggl_time_entries_{start_date}_to_{end_date}.csv"

    logging.info(f"Query toggl from {start_date} to {end_date}")
    data = requests.post(
        f"https://api.track.toggl.com/reports/api/v3/workspace/{workspace_id}/search/time_entries.csv",
        json={
            "start_date": start_date,
            "end_date": end_date,
            "grouped": False,
            "order_by": "date",
            "order_dir": "ASC",
            "hide_amounts": True,
        },
        headers={
            "content-type": "application/json",
            "Authorization": f"Basic {auth}",
        },
    )

    with open(out_csv, "w") as f:
        f.write(data.text)
        logging.info(f"Saved report to {out_csv}")
    return out_csv


if __name__ == "__main__":
    today = datetime.datetime.now().date()
    parser = argparse.ArgumentParser(
        prog='Personio Attendance Importer',
        description='Import attendance entries from services like Toggl')

    parser.add_argument(
        "-i",
        "--input-file",
        type=argparse.FileType("r"),
        dest="input_file",
        default=None,
    )
    parser.add_argument(
        "-s",
        "--start-date",
        dest="start_date",
        default=str(today),
    )
    parser.add_argument(
        "-e",
        "--end-date",
        dest="end_date",
        default=str(today + datetime.timedelta(days=1)),
    )
    args = parser.parse_args()

    logging.basicConfig()
    logging.getLogger().setLevel(logging.INFO)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.INFO)
    requests_log.propagate = True

    report = args.input_file
    if not report:
        report = get_toggl_detailed_report_csv(
            args.start_date, args.end_date, TOGGL_EMAIL, TOGGL_PASSWORD, TOGGL_WORKSPACE
        )
    else:
        report = report.name

    try:
        session, token = login(LOGIN_URL, EMAIL, PASSWORD)
        days = {}
        entries = models.csv_to_toggl_entries(os.path.abspath(report), PROJECTS_MAPPING)
        models.sanitize_toggl_entries(entries)
        days = models.toggl_entries_to_personio_days(entries)

        for date, day in days.items():
            logging.info(f'Registering entries from {date}')

            response = session.put(
                f'{ATTENDANCE_URL}/{uuid.uuid1()}',
                json=day.to_personio_attendance(PROFILE_ID),
                headers={
                    "X-XSRF-TOKEN": token,
                    "X-CSRF-Token": token,
                },
            )
            logging.debug(f'reponse:\n {response.text}')
            resp_dict = json.loads(response.text)
            if response.status_code != 200 or not resp_dict['success']:
                logging.debug(f'Attendance Req:\n{response.request.headers}\n{response.request.body}')
                logging.info(f'Attendance Resp:\n{response.text}')
                logging.error(f'FAILED to register attendance for {date}')
    except:
        logging.exception('FAILED')
    finally:
        session.close()
