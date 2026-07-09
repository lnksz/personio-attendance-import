from personio import PersonioDay
from dataclasses import dataclass
import datetime
import json
import re
import uuid
import requests
from loguru import logger
import argparse
import os

# Own modules
import personio
import toggl


@dataclass
class Config:
    # Personio credentials
    EMAIL: str
    PASSWORD: str
    PROFILE_ID: int

    # Toggl Configuration
    TOGGL_WORKSPACE: int
    TOGGL_EMAIL: str
    TOGGL_PASSWORD: str

    # Personio Configuration
    HOST: str
    ATTENDANCE_URL: str
    PROJECTS_URL: str
    LOGIN_URL: str
    COMPANY_HASH: str
    NON_APPROVABLE: tuple[str]

    # Project Mapping (define as an empty tuple if not used)
    # Personio ID from projects/filter[active]=1
    # Personio internal project ID | EFR project ID | EFR project name
    PROJECTS_MAPPING: tuple[tuple[str, str, str], ...]


def require_config(command: str | None):
    from config import CONFIG as c

    try:
        required_names = ["COMPANY_HASH", "LOGIN_URL", "EMAIL", "PASSWORD"]
        if command != "login":
            required_names.extend(
                [
                    "ATTENDANCE_URL",
                    "PROFILE_ID",
                    "PROJECTS_MAPPING",
                    "TOGGL_WORKSPACE",
                    "TOGGL_EMAIL",
                    "TOGGL_PASSWORD",
                ]
            )
        for n in required_names:
            if not hasattr(c, n) or not getattr(c, n):
                logger.error(f"Config is missing required element: {n}")
                raise SystemExit(1)

    except ImportError:
        logger.error("WARNING: no config.py or config element is missing.")
        raise SystemExit(1)

    return c


def login_or_exit(config):
    cookies = personio.login(
        user=config.EMAIL,
        password=config.PASSWORD,
        url=config.LOGIN_URL,
        company_hash=config.COMPANY_HASH,
    )
    if not cookies:
        logger.error("Login failed, no cookies returned.")
        raise SystemExit(1)
    return cookies


if __name__ == "__main__":
    today = datetime.datetime.now().date()
    tomorrow = today + datetime.timedelta(days=1)
    parser = argparse.ArgumentParser(
        prog="Personio Attendance Importer",
        description="Import attendance entries from services like Toggl",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["login"],
        help="Run only the Personio login flow",
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
    parser.add_argument(
        "-c",
        "--continue",
        dest="continue_running",
        action="store_true",
        help="If set, do not stop the running time entry",
    )
    args = parser.parse_args()

    config = require_config(args.command)

    if args.command == "login":
        logger.info("Running in login-only mode")
        cookies = login_or_exit(config)
        logger.success("Login succeeded.")
        raise SystemExit(0)

    report = None
    if args.command != "login":
        report = args.input_file
        if not report:
            report = toggl.get_detailed_report_csv(
                args.start_date,
                args.end_date,
                config.TOGGL_EMAIL,
                config.TOGGL_PASSWORD,
                config.TOGGL_WORKSPACE,
                args.continue_running,
            )
        else:
            report = report.name

    session = None
    is_registered = False
    try:
        pers_cookies = login_or_exit(config)
        if not pers_cookies:
            logger.error("Login failed, no cookies returned.")

            raise RuntimeError("Login failed")

        days = {}
        entries = toggl.csv_to_toggl_entries(os.path.abspath(report), config.PROJECTS_MAPPING)
        worked_seconds = toggl.worked_duration(entries)
        logger.info(f"Worked: {worked_seconds // 3600:02d}:{worked_seconds % 3600 // 60:02d}")
        toggl.sanitize_toggl_entries(entries)
        days = toggl.toggl_entries_to_personio_days(entries)

        session = requests.Session()
        session.cookies.update(pers_cookies)

        for date, day in days.items():
            attendance = day.to_personio_attendance(config.PROFILE_ID)
            is_registered = personio.log_toggl_day_in_personio(
                session, config, day, date, pers_cookies
            )

        personio.approve_zeiterfassung_dashboard(config.HOST, pers_cookies, config.NON_APPROVABLE)
    except Exception as e:
        logger.exception("FAILED", exc_info=e)
        is_registered = False
    finally:
        if session:
            session.close()
    if not is_registered:
        exit(1)
