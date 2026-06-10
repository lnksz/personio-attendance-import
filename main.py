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


def get_untrackable_project_ids(resp: requests.Response) -> list[str]:
    if resp.status_code != 400:
        return []

    try:
        resp_dict = resp.json()
    except requests.exceptions.JSONDecodeError:
        return []

    untrackable_projects_title_re = re.compile(
        r"Projects with ids \[([^\]]+)\] for employee \d+ are not trackable"
    )
    for error in resp_dict.get("errors", []):
        if error.get("type") != "ATTENDANCE_PERIOD_PROJECT_NOT_TRACKABLE":
            continue

        title = error.get("title", "")
        match = untrackable_projects_title_re.search(title)
        if not match:
            return []

        return [project_id.strip() for project_id in match.group(1).split(",") if project_id.strip()]

    return []


def remove_untrackable_project_ids(attendance: dict, project_ids: list[str]) -> int:
    untrackable_ids = set(project_ids)
    removed = 0
    for period in attendance["periods"]:
        if period.get("project_id") in untrackable_ids:
            period["project_id"] = None
            removed += 1
    return removed


def log_toggl_day_in_personio(session: requests.Session, config, day, date, cookies) -> bool:
    attendance = day.to_personio_attendance(config.PROFILE_ID)
    logger.info(f"Registering entries ({len(attendance['periods'])}) from {date}")
    token = cookies.get("ATHENA-XSRF-TOKEN", "")

    while True:
        resp = session.put(
            f"{config.ATTENDANCE_URL}/{uuid.uuid1()}",
            json=attendance,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Referer": "https://efr-gmbh.app.personio.com/",
                "X-ATHENA-XSRF-TOKEN": token,
            },
        )
        content_type = resp.headers.get("content-type", "")
        logger.info(f"response: {resp.status_code} {content_type}")
        logger.trace(f"reponse content:\n {resp.text}")

        untrackable_project_ids = get_untrackable_project_ids(resp)
        if untrackable_project_ids:
            removed = remove_untrackable_project_ids(attendance, untrackable_project_ids)
            if removed:
                logger.warning(
                    f"Personio project ids {untrackable_project_ids} are not trackable for {date}; retrying without project mapping"
                )
                continue

        if resp.status_code != 200 or "application/json" not in content_type:
            logger.error(
                f"Attendance Req:\n"
                f"Heads: {resp.request.headers}\n"
                f"Request: {resp.request.body}\n"
                f"Response: {resp}\n{resp.text}\n"
            )
            logger.error(f"FAILED to register attendance for {date}")
            return False

        resp_dict = json.loads(resp.text)
        if resp.status_code != 200 or not resp_dict["success"]:
            logger.error(f"Attendance Req:\n{resp.request.headers}\n{resp.request.body}")
            logger.info(f"Attendance Resp:\n{resp.text}")
            logger.error(f"FAILED to register attendance for {date}")
            return False
        return True


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
            is_registered = log_toggl_day_in_personio(session, config, day, date, pers_cookies)
    except Exception as e:
        logger.exception("FAILED", exc_info=e)
        is_registered = False
    finally:
        if session:
            session.close()
    if not is_registered:
        exit(1)
