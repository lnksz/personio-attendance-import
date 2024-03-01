from typing import Dict, List
import uuid
import csv
import io


class TogglTimeEntry:
    def __init__(self, project_mapping: tuple, client: str, project: str, desc: str, start_date: str, start_time: str, end_date: str, end_time: str):
        self.client = client
        self.project = project
        self.desc = desc
        self.start_date = start_date
        self.start_time = start_time
        self.end_date = end_date
        self.end_time = end_time
        self.project_mapping = project_mapping

    def __str__(self):
        return f'Client: {self.client}\nProj: {self.project}\nDesc: {self.desc}\n{self.start_date}T{self.start_time} - {self.end_date}T{self.end_time}\n'

    def __repr__(self):
        return self.__str__()

    def proj_toggl2personio(self, client: str):
        """Converts Toggl client name which has the internal project ID, to Personio project ID"""
        for pers_id, internal_id in self.project_mapping:
            if internal_id in client:
                return pers_id
        return None

    def to_personio_period(self):
        return {
            "id": str(uuid.uuid1()),
            "project_id": self.proj_toggl2personio(self.client),
            "period_type": "work",
            "legacy_break_min": 0,
            "comment": f'[{self.project}]',
            # Could be a config whether or not to include all details
            # "comment": f'[{self.project}] {self.desc}',
            "start": f'{self.start_date}T{self.start_time}Z',
            "end": f'{self.end_date}T{self.end_time}Z',
        }


class PersonioDay:
    def __init__(self, date: str):
        self.date = date
        self.periods = []
        self.uuid = str(uuid.uuid1())

    def __str__(self):
        return f'{self.date} - {len(self.periods)}'

    def __repr__(self):
        return self.__str__()

    def add_period(self, period: dict):
        self.periods.append(period)

    def to_personio_attendance(self, employee_id: int):
        return {
            "employee_id": employee_id,
            "periods": self.periods,
        }


def csv_to_toggl_entries(csv_file: str, proj_mapping: tuple) -> List[TogglTimeEntry]:
    # 0    1     2      3       4    5           6        7          8          9        10       11       12   13
    # User,Email,Client,Project,Task,Description,Billable,Start date,Start time,End date,End time,Duration,Tags,Amount ()
    entries = []
    with io.open(csv_file, 'r', encoding='utf-8-sig') as csvfile:
        reader = csv.reader(csvfile, delimiter=',', quotechar='"', doublequote=True, lineterminator='\n')
        try:
            for idx, row in enumerate(reader):
                if idx == 0:
                    continue
                _, _, client, proj, _, desc, _, start_date, start_time, end_date, end_time, _, _, _ = row
                entries.append(TogglTimeEntry(
                    proj_mapping, client, proj, desc, start_date, start_time, end_date, end_time))
        except ValueError:
            print(f'Error parsing row {idx} len({len(row)}): {row}')
    return entries


def sanitize_toggl_entries(entries: List[TogglTimeEntry]) -> List[TogglTimeEntry]:
    """With Toggl, it's possible to have overlapping entries.
       I think because of the different control sources (web, desktop, mobile)...
       There are entries which start before the previous one ends.
       Toggl can handle this, but Personio can't."""
    entries.sort(key=lambda x: (x.start_date, x.start_time))
    for prev_entry, entry in zip(entries, entries[1:]):
        if prev_entry.end_date == entry.start_date and entry.start_time <= prev_entry.end_time:
            entry.start_time, prev_entry.end_time = prev_entry.end_time, entry.start_time
    return entries


def toggl_entries_to_personio_days(entries: list) -> Dict[str, PersonioDay]:
    days = {}
    for entry in entries:
        if entry.start_date not in days:
            days[entry.start_date] = PersonioDay(entry.start_date)
        days[entry.start_date].add_period(entry.to_personio_period())
    return days
