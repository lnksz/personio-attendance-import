#!/usr/bin/env python3

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
    logging.debug(first_response.headers, '\n', first_response.text)
    logging.debug(first_response.headers, '\n')
    set_cookie = first_response.headers["set-cookie"]
    token = set_cookie.split()[0].split('=')[1].rstrip(';')
    logging.info(f'CSRF: {set_cookie}')
    logging.info(f"CSRF: {token}")

    return session, token


def get_projects(session: requests.Session) -> requests.Response:
    response = session.get(PROJECTS_URL, headers={"Accept": "application/json"})
    logging.debug('Projects:')
    logging.debug(response.headers, '\n', response.text)
    return response


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog='Personio Attendance Importer',
        description='Import attendance entries from services like Toggl')

    parser.add_argument('-i', '--input-file', type=argparse.FileType('r'), required=True, dest='input_file')
    args = parser.parse_args()

    logging.basicConfig()
    logging.getLogger().setLevel(logging.INFO)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.INFO)
    requests_log.propagate = True

    try:
        session, token = login(LOGIN_URL, EMAIL, PASSWORD)
        days = {}
        entries = models.csv_to_toggl_entries(os.path.abspath(args.input_file.name), PROJECTS_MAPPING)
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
            resp_dict = json.loads(response.text)
            if response.status_code != 200 or not resp_dict['success']:
                logging.error(f'FAILED to register attendance on {date}')
                logging.info(f'Attendance Req:\n{response.request.headers}\n{response.request.body}')
                logging.info(f'Attendance Resp:\n{response.headers}\n{response.text}')
    except:
        logging.exception('FAILED')
    finally:
        session.close()
