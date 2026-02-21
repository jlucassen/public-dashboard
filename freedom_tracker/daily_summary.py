#!/usr/bin/env python3
"""Summarize Freedom uptime for today and push to Google Sheet.

Run once daily at 11:55 PM via launchd.
"""

import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

TZ = ZoneInfo("America/Los_Angeles")
LOG_DIR = Path.home() / ".freedom_tracker"
CHECK_INTERVAL_MINUTES = 5
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def compute_uptime(date_str: str) -> float | None:
    """Read local CSV log and compute Freedom uptime hours for a given date."""
    log_file = LOG_DIR / f"{date_str}.csv"
    if not log_file.exists():
        print(f"No log file for {date_str}")
        return None

    running_checks = 0
    total_checks = 0

    with open(log_file) as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_checks += 1
            if int(row["running"]):
                running_checks += 1

    if total_checks == 0:
        return 0.0

    uptime_hours = round(running_checks * CHECK_INTERVAL_MINUTES / 60, 2)
    print(f"  {date_str}: {running_checks}/{total_checks} checks running = {uptime_hours}h")
    return uptime_hours


def push_to_sheet(date_str: str, uptime_hours: float):
    """Append a row to the Freedom sheet in Google Sheets."""
    load_dotenv()

    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
    sheet_id = os.environ.get("DAILY_FORM_SHEET_ID")

    assert sheet_id, "DAILY_FORM_SHEET_ID not set"

    if creds_path and os.path.exists(creds_path):
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    elif os.environ.get("GOOGLE_CREDENTIALS"):
        info = json.loads(os.environ["GOOGLE_CREDENTIALS"])
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        raise RuntimeError("No Google credentials found")

    service = build("sheets", "v4", credentials=creds)
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="'Freedom'!A:B",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [[date_str, uptime_hours]]},
    ).execute()

    print(f"  Pushed to Google Sheet: {date_str} = {uptime_hours}h")


def main():
    now = datetime.now(TZ)
    date_str = now.strftime("%Y-%m-%d")

    if len(sys.argv) > 1:
        date_str = sys.argv[1]

    print(f"Freedom daily summary for {date_str}")
    uptime = compute_uptime(date_str)

    if uptime is not None:
        try:
            push_to_sheet(date_str, uptime)
        except Exception as e:
            print(f"ERROR: Failed to push to Google Sheet: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("No data to push.")


if __name__ == "__main__":
    main()
