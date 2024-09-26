import logging
from base64 import b64encode
import requests


def get_detailed_report_csv(
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
