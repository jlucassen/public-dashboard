"""Google Sheets client. Reads form responses."""

import json
import os
from datetime import datetime
from collections import defaultdict
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _get_service(credentials_path: str | None = None):
    """Build a Google Sheets API service using service account credentials.

    Credentials can come from a file path or the GOOGLE_CREDENTIALS env var (JSON string).
    """
    if credentials_path and os.path.exists(credentials_path):
        creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    elif os.environ.get("GOOGLE_CREDENTIALS"):
        info = json.loads(os.environ["GOOGLE_CREDENTIALS"])
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        raise RuntimeError(
            "No Google credentials found. Set GOOGLE_CREDENTIALS env var "
            "or provide a credentials file path."
        )

    return build("sheets", "v4", credentials=creds)


def fetch_form_responses(
    sheet_id: str,
    sheet_name: str,
    tz: ZoneInfo,
    credentials_path: str | None = None,
) -> dict[str, dict]:
    """Read Google Form responses and return daily habit metrics.

    Assumes the sheet has a Timestamp column (first) followed by question columns.
    Each question is a 1-5 numeric scale. Questions may appear/disappear over time.

    Returns {date_str: {question_name: value, ...}}.
    """
    service = _get_service(credentials_path)
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{sheet_name}'",
    ).execute()

    rows = result.get("values", [])
    if len(rows) < 2:
        print("  Google Sheets: no form responses found")
        return {}

    headers = rows[0]
    days: dict[str, dict] = {}

    error_count = 0
    for row in rows[1:]:
        if not row:
            continue
        try:
            timestamp_str = row[0]
            dt = _parse_sheets_timestamp(timestamp_str, tz)
            date_key = dt.strftime("%Y-%m-%d")

            day_data = {}
            for i, header in enumerate(headers[1:], start=1):
                if i < len(row) and row[i].strip():
                    try:
                        day_data[header] = int(row[i])
                    except ValueError:
                        try:
                            day_data[header] = float(row[i])
                        except ValueError:
                            day_data[header] = row[i]

            if day_data:
                days[date_key] = day_data
        except Exception as e:
            error_count += 1
            if error_count <= 5:
                print(f"  WARNING: Failed to parse form row: {e}")

    if error_count > 5:
        print(f"  WARNING: {error_count} total form row parse errors")

    print(f"  Google Sheets: parsed {len(days)} days of form responses")
    return days



def _parse_sheets_timestamp(ts: str, tz: ZoneInfo) -> datetime:
    """Parse common Google Sheets timestamp formats."""
    for fmt in [
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]:
        try:
            dt = datetime.strptime(ts, fmt)
            return dt.replace(tzinfo=tz)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {ts!r}")
