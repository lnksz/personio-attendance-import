from loguru import logger
from base64 import b64encode
import requests


def stop_running_timer(auth: bytes, workspace_id: int):
    logger.debug("Check running timer")
    current = requests.get(
        "https://api.track.toggl.com/api/v9/me/time_entries/current",
        headers={
            "content-type": "application/json",
            "Authorization": f"Basic {auth}"
        },
    )
    if current.status_code == 200 and current.json() is None:
        logger.info("No running timer")
        return

    cid = current.json()["id"]
    stoped = requests.patch(
        f'https://api.track.toggl.com/api/v9/workspaces/{workspace_id}/time_entries/{cid}/stop',
        headers={
            'content-type': 'application/json',
            'Authorization': f"Basic {auth}"
        },
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
) -> str:
    auth = b64encode(f"{email}:{password}".encode()).decode("ascii")
    stop_running_timer(auth, workspace_id)

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
    with open(out_csv, "w") as f:
        f.write(response.text)
        logger.info(f"Saved report to {out_csv}")
    return out_csv
