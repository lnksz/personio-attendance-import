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


if __name__ == "__main__":
    today = datetime.datetime.now().date()
    tomorrow = today + datetime.timedelta(days=1)
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
        help="Input CSV containing the attendance entries (default: None)",
    )
    parser.add_argument(
        "-s",
        "--start-date",
        dest="start_date",
        default=str(today),
        help=f"Start date for the report (default: {today})",
    )
    parser.add_argument(
        "-e",
        "--end-date",
        dest="end_date",
        default=str(tomorrow),
        help=f"The last date since start-date to INCLUDE in the report (default: {tomorrow})",
    )
    args = parser.parse_args()

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

    report = args.input_file
    if not report:
        report = toggl.get_detailed_report_csv(
            args.start_date, args.end_date, TOGGL_EMAIL, TOGGL_PASSWORD, TOGGL_WORKSPACE
        )
        worked = toggl.get_work_duration(TOGGL_EMAIL, TOGGL_PASSWORD, args.start_date)
        logger.info(f"Worked hours: {worked / 3600.0:.2f}")
    else:
        report = report.name

    session = None
    try:
        session, t1, t2, t3 = personio.login(LOGIN_URL, EMAIL, PASSWORD)
        days = {}
        entries = models.csv_to_toggl_entries(os.path.abspath(report), PROJECTS_MAPPING)
        models.sanitize_toggl_entries(entries)
        days = models.toggl_entries_to_personio_days(entries)

        for date, day in days.items():
            attendance = day.to_personio_attendance(PROFILE_ID)
            logger.info(
                f"Registering entries ({len(attendance["periods"])}) from {date}"
            )

            resp = session.put(
                f"{ATTENDANCE_URL}/{uuid.uuid1()}",
                json=attendance,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "XSRF-TOKEN": t1,
                    "X-XSRF-TOKEN": t2,
                    "X-CSRF-Token": t2,
                    "X-ATHENA-XSRF-TOKEN": t3,
                },
            )
            content_type = resp.headers.get("content-type", "")
            logger.info(
                f"response: {resp.status_code} " f'{content_type}'
            )
            logger.trace(f"reponse content:\n {resp.text}")

            if (
                resp.status_code != 200
                or content_type != "application/json"
            ):
                logger.error(
                    f"Attendance Req:\n"
                    f"Heads: {resp.request.headers}\n"
                    f"Request: {resp.request.body}\n"
                    f"Response: {resp}\n{resp.text}\n"
                )
                logger.error(f"FAILED to register attendance for {date}")

                continue
            resp_dict = json.loads(resp.text)
            if resp.status_code != 200 or not resp_dict["success"]:
                logger.error(
                    f"Attendance Req:\n{resp.request.headers}\n{resp.request.body}"
                )
                logger.info(f"Attendance Resp:\n{resp.text}")
                logger.error(f"FAILED to register attendance for {date}")
    except Exception as e:
        logger.exception("FAILED", exc_info=e)
    finally:
        if session:
            session.close()
