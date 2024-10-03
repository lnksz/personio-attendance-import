#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "loguru",
#     "requests",
# ]
# ///

import datetime
import json
import uuid
from loguru import logger
import argparse
import os

# Own modules
import models
import personio
import toggl

try:
    from config import (
        ATTENDANCE_URL,
        LOGIN_URL,
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


if __name__ == "__main__":
    today = datetime.datetime.now().date()
    parser = argparse.ArgumentParser(
        prog="Personio Attendance Importer",
        description="Import attendance entries from services like Toggl",
    )

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

    # For debugging requests:
    # requests_log = logging.getLogger("requests.packages.urllib3")
    # requests_log.setLevel(logging.DEBUG)
    # requests_log.propagate = True

    report = args.input_file
    if not report:
        report = toggl.get_detailed_report_csv(
            args.start_date, args.end_date, TOGGL_EMAIL, TOGGL_PASSWORD, TOGGL_WORKSPACE
        )
    else:
        report = report.name

    try:
        session, token = personio.login(LOGIN_URL, EMAIL, PASSWORD)
        days = {}
        entries = models.csv_to_toggl_entries(os.path.abspath(report), PROJECTS_MAPPING)
        models.sanitize_toggl_entries(entries)
        days = models.toggl_entries_to_personio_days(entries)

        for date, day in days.items():
            attendance = day.to_personio_attendance(PROFILE_ID)
            logger.info(f"Registering entries ({len(attendance["periods"])}) from {date}")

            response = session.put(
                f"{ATTENDANCE_URL}/{uuid.uuid1()}",
                json=attendance,
                headers={
                    "X-XSRF-TOKEN": token,
                    "X-CSRF-Token": token,
                },
            )
            logger.info(
                f"response: {response.status_code} "
                f'{response.headers["content-type"]}'
            )
            logger.trace(f"reponse content:\n {response.text}")

            if (
                response.status_code != 200
                or response.headers["content-type"] != "application/json"
            ):
                logger.error(
                    f"Attendance Req:\n"
                    f"Heads: {response.request.headers}\n"
                    f"Request: {response.request.body}"
                )
                logger.error(f"FAILED to register attendance for {date}")

                continue
            resp_dict = json.loads(response.text)
            if response.status_code != 200 or not resp_dict["success"]:
                logger.error(
                    f"Attendance Req:\n"
                    f"{response.request.headers}\n"
                    f"{response.request.body}"
                )
                logger.info(f"Attendance Resp:\n{response.text}")
                logger.error(f"FAILED to register attendance for {date}")
    except Exception as e:
        logger.exception("FAILED", exc_info=e)
    finally:
        session.close()
