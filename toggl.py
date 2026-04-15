from base64 import b64encode
from loguru import logger
from typing import Dict, List
import csv
import io
import requests
import uuid

from personio import PersonioDay


class TogglTimeEntry:
    def __init__(
        self,
        project_mapping: tuple,
        client: str,
        project: str,
        desc: str,
        start_date: str,
        start_time: str,
        end_date: str,
        end_time: str,
    ):
        self.client = client
        self.project = project
        self.desc = desc
        self.start_date = start_date
        self.start_time = start_time
        self.end_date = end_date
        self.end_time = end_time
        self.project_mapping = project_mapping

    def __str__(self):
        return f"Client: {self.client}\nProj: {self.project}\nDesc: {self.desc}\n{self.start_date}T{self.start_time} - {self.end_date}T{self.end_time}\n"

    def __repr__(self):
        return self.__str__()

    def proj_toggl2personio(self):
        """Converts Toggl client name which has the internal project ID, to Personio project ID"""
        for pers_id, internal_id, _ in self.project_mapping:
            if internal_id in self.client or internal_id in self.project:
                return pers_id
        return None

    def to_personio_period(self):
        return {
            "id": str(uuid.uuid1()),
            "project_id": self.proj_toggl2personio(),
            "period_type": "work",
            "legacy_break_min": 0,
            "comment": f"[{self.project}]",
            # Could be a config whether or not to include all details
            # "comment": f'[{self.project}] {self.desc}',
            "start": f"{self.start_date}T{self.start_time}",
            "end": f"{self.end_date}T{self.end_time}",
        }


def stop_running_timer(auth: str, workspace_id: int):
    logger.debug("Check running timer")
    current = requests.get(
        "https://api.track.toggl.com/api/v9/me/time_entries/current",
        headers={"content-type": "application/json", "Authorization": f"Basic {auth}"},
    )

    if current.status_code != 200:
        logger.error(f"Failed to fetch current timer: {current.status_code} {current.text}")
        logger.debug(f"Request headers: {current.request.headers}")
        raise RuntimeError("Couldn't fetch current timer")

    try:
        current_data = current.json()
    except requests.exceptions.JSONDecodeError as e:
        logger.error(f"Invalid JSON response: {e.msg}. Response content: {current.text}")
        raise RuntimeError("Invalid JSON response from Toggl API")

    if current_data is None:
        logger.info("No running timer")
        return

    cid = current_data["id"]
    stoped = requests.patch(
        f"https://api.track.toggl.com/api/v9/workspaces/{workspace_id}/time_entries/{cid}/stop",
        headers={"content-type": "application/json", "Authorization": f"Basic {auth}"},
    )
    if stoped.status_code == 200:
        logger.info("Stopped running timer")
    else:
        logger.error(f"Failed to stop timer: {stoped.status_code} {stoped.text}")
        raise RuntimeError("Couldn't stop timer")


def get_detailed_report_csv(
    start_date: str,
    end_date: str,
    email: str,
    password: str,
    workspace_id: int,
    continue_running: bool = False,
) -> str:
    auth = b64encode(f"{email}:{password}".encode()).decode("ascii")
    if not continue_running:
        stop_running_timer(auth, workspace_id)

    logger.info(f"Query toggl from {start_date} to {end_date}")
    response = requests.post(
        f"https://api.track.toggl.com/reports/api/v3/workspace/{workspace_id}/search/"
        "time_entries.csv",
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
    if response.status_code != 200:
        logger.error(
            f"Toggl export:\n"
            f"Request: {response.request.body}\n"
            f"Response: {response.text}"
        )
        raise RuntimeError("Toggl export failed")

    out_csv = f"Toggl_time_entries_{start_date}_to_{end_date}.csv"
    with open(out_csv, "w", encoding="utf-8") as f:
        f.write(response.text)
        logger.info(f"Saved report to {out_csv}")
    return out_csv


def csv_to_toggl_entries(csv_file: str, proj_mapping: tuple) -> List[TogglTimeEntry]:
    # 0     1      2       3        4     5            6
    # User, Email, Client, Project, Task, Description, Billable,
    # 7           8           9         10        11        12    13
    # Start date, Start time, End date, End time, Duration, Tags, Amount ()
    entries = []
    with io.open(csv_file, "r", encoding="utf-8") as csvfile:
        reader = csv.reader(
            csvfile, delimiter=",", quotechar='"', doublequote=True, lineterminator="\n"
        )
        try:
            next(reader)  # skip header
            for row in reader:
                (
                    _,
                    _,
                    client,
                    proj,
                    _,
                    desc,
                    _,
                    start_date,
                    start_time,
                    end_date,
                    end_time,
                    duration,
                    *_,
                ) = row
                if duration.startswith("00:00:"):
                    # Skip super short entries with less than 1m duration
                    # Personio doesn't like this
                    continue
                entries.append(
                    TogglTimeEntry(
                        proj_mapping,
                        client,
                        proj,
                        desc,
                        start_date,
                        start_time,
                        end_date,
                        end_time,
                    )
                )
        except ValueError:
            print(f"Error parsing entry {row}")
    return entries


def worked_duration(
    entries: List[TogglTimeEntry],
) -> int:
    total_seconds = 0

    def time_to_seconds(time_str: str) -> int:
        hours, minutes, seconds = (int(part) for part in time_str.split(":"))
        return hours * 3600 + minutes * 60 + seconds

    for entry in entries:
        start_seconds = time_to_seconds(entry.start_time)
        end_seconds = time_to_seconds(entry.end_time)
        total_seconds += end_seconds - start_seconds

    return total_seconds


def sanitize_toggl_entries(entries: List[TogglTimeEntry]) -> List[TogglTimeEntry]:
    """With Toggl, it's possible to have overlapping entries.
    I think because of the different control sources (web, desktop, mobile)...
    There are entries which start before the previous one ends.
    Toggl can handle this, but Personio can't."""
    entries.sort(key=lambda x: (x.start_date, x.start_time))
    for prev_entry, entry in zip(entries, entries[1:]):
        if (
            prev_entry.end_date == entry.start_date
            and entry.start_time <= prev_entry.end_time
        ):
            entry.start_time, prev_entry.end_time = (
                prev_entry.end_time,
                entry.start_time,
            )
    return entries


def toggl_entries_to_personio_days(entries: list) -> Dict[str, PersonioDay]:
    days = {}
    for entry in entries:
        if entry.start_date not in days:
            days[entry.start_date] = PersonioDay(entry.start_date)
        days[entry.start_date].add_period(entry.to_personio_period())
    return days
