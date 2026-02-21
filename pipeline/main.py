"""Pipeline orchestrator. Fetches all data sources, computes metrics, writes JSON."""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

from pipeline.toggl import get_workspace_and_projects, fetch_time_entries, compute_daily_metrics
from pipeline.todoist import fetch_completed_items, compute_daily_completions
from pipeline.google_sheets import fetch_form_responses, fetch_freedom_data


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    assert config_path.exists(), f"Config not found: {config_path}"
    with open(config_path) as f:
        return yaml.safe_load(f)


def run(start_date: str | None = None):
    load_dotenv()
    config = load_config()
    tz = ZoneInfo(config["timezone"])
    now = datetime.now(tz)
    today = now.strftime("%Y-%m-%d")

    toggl_token = os.environ.get("TOGGL_TOKEN")
    todoist_token = os.environ.get("TODOIST_TOKEN")
    sheet_id = os.environ.get("DAILY_FORM_SHEET_ID")
    google_creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")

    assert toggl_token, "TOGGL_TOKEN not set"
    assert todoist_token, "TODOIST_TOKEN not set"

    if not start_date:
        lookback = config.get("lookback_days", 30)
        start_date = (now - timedelta(days=lookback)).strftime("%Y-%m-%d")

    print(f"Pipeline run: {now.isoformat()}")
    print(f"Date range: {start_date} to {today}")
    print()

    # --- Toggl ---
    print("[1/4] Fetching Toggl data...")
    workspace_id, projects = get_workspace_and_projects(toggl_token)
    print(f"  Workspace: {workspace_id}, Projects: {list(projects.keys())}")
    entries = fetch_time_entries(toggl_token, start_date, today)
    toggl_days = compute_daily_metrics(entries, projects, config["toggl"], tz)
    print(f"  Toggl: {len(toggl_days)} days of data")
    print()

    # --- Todoist ---
    print("[2/4] Fetching Todoist data...")
    since_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=tz)
    until_dt = now
    completed = fetch_completed_items(
        todoist_token,
        since=since_dt.isoformat(),
        until=until_dt.isoformat(),
    )
    todoist_days = compute_daily_completions(
        completed, config["todoist"], tz, start_date, today,
    )
    print(f"  Todoist: {len(todoist_days)} days of data")
    print()

    # --- Google Sheets (form + freedom) ---
    habits_days: dict[str, dict] = {}
    freedom_days: dict[str, float] = {}
    has_google = sheet_id and (google_creds_path or os.environ.get("GOOGLE_CREDENTIALS"))

    if has_google:
        assert sheet_id is not None
        print("[3/4] Fetching Google Sheets data...")
        sheets_config = config["google_sheets"]
        try:
            habits_days = fetch_form_responses(
                sheet_id,
                sheets_config["form_responses_sheet"],
                tz,
                credentials_path=google_creds_path,
            )
        except Exception as e:
            print(f"  WARNING: Failed to fetch form responses: {e}")

        try:
            freedom_days = fetch_freedom_data(
                sheet_id,
                sheets_config["freedom_sheet"],
                tz,
                credentials_path=google_creds_path,
            )
        except Exception as e:
            print(f"  WARNING: Failed to fetch Freedom data: {e}")
        print()
    else:
        print("[3/4] Skipping Google Sheets (no credentials configured)")
        print()

    # --- Merge ---
    print("[4/4] Merging and writing metrics...")
    all_dates = []
    d = datetime.strptime(start_date, "%Y-%m-%d")
    end_d = datetime.strptime(today, "%Y-%m-%d")
    while d <= end_d:
        all_dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)

    days: list[dict] = []
    for date_str in all_dates:
        toggl = toggl_days.get(date_str, {})
        freedom_hrs = freedom_days.get(date_str)

        total_hours = toggl.get("total_hours")
        sleep_hours = toggl.get("sleep_hours")
        untracked = round(24 - total_hours, 2) if total_hours is not None else None

        if freedom_hrs is not None:
            waking = (24 - sleep_hours) if sleep_hours is not None else 24
            blocker_downtime = round(max(0, waking - freedom_hrs), 2)
        else:
            blocker_downtime = None

        day: dict = {
            "date": date_str,
            "work_hours": toggl.get("work_hours"),
            "unendorsed_hours": toggl.get("unendorsed_hours"),
            "untracked_hours": untracked,
            "blocker_downtime_hours": blocker_downtime,
            "sleep_hours": toggl.get("sleep_hours"),
            "bedtime": toggl.get("bedtime"),
            "wake_time": toggl.get("wake_time"),
            "todoist": todoist_days.get(date_str, {}),
            "habits": habits_days.get(date_str, {}),
            "freedom_hours": freedom_hrs,
        }
        days.append(day)

    metrics = {
        "last_updated": now.isoformat(),
        "timezone": config["timezone"],
        "days": days,
    }

    out_path = Path(__file__).parent.parent / "docs" / "data" / "metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"  Wrote {len(days)} days to {out_path}")
    print(f"  Date range: {all_dates[0] if all_dates else 'N/A'} to {all_dates[-1] if all_dates else 'N/A'}")
    print("Done.")


if __name__ == "__main__":
    start = sys.argv[1] if len(sys.argv) > 1 else None
    run(start_date=start)
