from loguru import logger
from base64 import b64encode
import requests
from datetime import datetime


def get_duration(entry: dict) -> int:
    if entry["stop"] is not None:
        return entry["duration"]
    start = datetime.fromisoformat(entry["start"])
    now = datetime.now()
    return int(now.timestamp() - start.timestamp())


def get_work_duration(
    email: str,
    password: str,
    since_date: str = None,
) -> int:
    auth = b64encode(f"{email}:{password}".encode()).decode("ascii")
    if since_date is not None:
        since = int(datetime.fromisoformat(since_date).timestamp())
    else:
        since = int(datetime.combine(datetime.now().date(), datetime.min.time()).timestamp())
    today = requests.get(
        f"https://api.track.toggl.com/api/v9/me/time_entries?since={since}",
        headers={"content-type": "application/json", "Authorization": f"Basic {auth}"},
    )
    if today.status_code != 200:
        raise RuntimeError("Couldn't get today's entries")

    return sum([get_duration(entry) for entry in today.json()])


def stop_running_timer(auth: bytes, workspace_id: int):
    logger.debug("Check running timer")
    current = requests.get(
        "https://api.track.toggl.com/api/v9/me/time_entries/current",
        headers={"content-type": "application/json", "Authorization": f"Basic {auth}"},
    )
    if current.status_code == 200 and current.json() is None:
        logger.info("No running timer")
        return

    cid = current.json()["id"]
    stoped = requests.patch(
        f"https://api.track.toggl.com/api/v9/workspaces/{workspace_id}/time_entries/{cid}/stop",
        headers={"content-type": "application/json", "Authorization": f"Basic {auth}"},
    )
    if stoped.status_code == 200:
        logger.info("Stopped running timer")
    else:
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
        stop_running_timer(auth.encode(), workspace_id)

    logger.info(f"Query toggl from {start_date} to {end_date}")
    response = requests.post(
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
