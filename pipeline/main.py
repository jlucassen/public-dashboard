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
from pipeline.scoring import get_red_metrics, find_consecutive_red_days
from pipeline.notify import send_alert


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

    assert toggl_token, "TOGGL_TOKEN not set"
    assert todoist_token, "TODOIST_TOKEN not set"

    if not start_date:
        max_past_weeks = config["max_past_weeks"]
        today_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        monday = today_dt - timedelta(days=today_dt.weekday())
        earliest_monday = monday - timedelta(weeks=max_past_weeks)
        start_date = earliest_monday.strftime("%Y-%m-%d")

    print(f"Pipeline run: {now.isoformat()}")
    print(f"Date range: {start_date} to {today}")
    print()

    # --- Toggl ---
    print("[1/3] Fetching Toggl data...")
    workspace_id, projects = get_workspace_and_projects(toggl_token)
    print(f"  Workspace: {workspace_id}, Projects: {list(projects.keys())}")
    entries = fetch_time_entries(toggl_token, start_date, today)
    toggl_days = compute_daily_metrics(entries, projects, config["toggl"], tz)
    print(f"  Toggl: {len(toggl_days)} days of data")
    print()

    # --- Todoist ---
    print("[2/3] Fetching Todoist data...")
    events = fetch_completed_items(todoist_token, since=start_date, until=today)
    todoist_days = compute_daily_completions(
        events, config["todoist"], tz, start_date, today,
    )
    print(f"  Todoist: {len(todoist_days)} days of data")
    print()

    # --- Merge ---
    print("[3/3] Merging and writing metrics...")
    all_dates = []
    d = datetime.strptime(start_date, "%Y-%m-%d")
    end_d = datetime.strptime(today, "%Y-%m-%d")
    while d <= end_d:
        all_dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)

    days: list[dict] = []
    for date_str in all_dates:
        toggl = toggl_days.get(date_str, {})

        total_hours = toggl.get("total_hours")
        untracked = round(24 - total_hours, 2) if total_hours is not None else None

        day: dict = {
            "date": date_str,
            "work_hours": toggl.get("work_hours"),
            "sleep_hours": toggl.get("sleep_hours"),
            "other_hours": toggl.get("other_hours"),
            "unendorsed_hours": toggl.get("unendorsed_hours"),
            "untracked_hours": untracked,
            "bedtime": toggl.get("bedtime"),
            "wake_time": toggl.get("wake_time"),
            "todoist": todoist_days.get(date_str, {}),
        }
        days.append(day)

    # --- Score ---
    for day in days:
        red_names, red_count = get_red_metrics(day)
        day["red_count"] = red_count
        day["red_metrics"] = red_names

    # --- Read previous alert state ---
    out_path = Path(__file__).parent.parent / "docs" / "data" / "metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    last_alert_date = None
    if out_path.exists():
        try:
            with open(out_path) as f:
                old_metrics = json.load(f)
            last_alert_date = old_metrics.get("last_alert_date")
        except (json.JSONDecodeError, KeyError):
            pass

    # --- Check for consecutive bad days & notify (2 PM local only) ---
    # Sent in the afternoon so the alert lands when James is awake even on
    # rough days, rather than at midnight when he's likely still asleep.
    ALERT_HOUR = 14
    is_alert_run = now.hour == ALERT_HOUR
    streak = find_consecutive_red_days(days, today)
    if streak and is_alert_run:
        newest_bad_date = streak[-1][0]
        if newest_bad_date != last_alert_date:
            print(f"  RED ALERT: {len(streak)}-day streak detected ending {newest_bad_date}")
            gmail_user = os.environ.get("GMAIL_USER")
            gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
            emails_raw = os.environ.get("NOTIFICATION_EMAILS", "")
            recipients = [e.strip() for e in emails_raw.split(",") if e.strip()]

            if gmail_user and gmail_password and recipients:
                try:
                    send_alert(gmail_user, gmail_password, recipients, streak)
                    last_alert_date = newest_bad_date
                except Exception as e:
                    print(f"  ERROR sending alert email: {e}")
            else:
                missing = []
                if not gmail_user:
                    missing.append("GMAIL_USER")
                if not gmail_password:
                    missing.append("GMAIL_APP_PASSWORD")
                if not recipients:
                    missing.append("NOTIFICATION_EMAILS")
                print(f"  Skipping alert: missing env vars: {', '.join(missing)}")
        else:
            print(f"  Streak detected but already alerted for {newest_bad_date}, skipping")
    elif streak:
        print(f"  Streak detected but not alert hour ({now.hour:02d}:00 != {ALERT_HOUR:02d}:00), skipping email")
    else:
        print("  No consecutive red-day streak detected")

    # --- Write metrics ---
    metrics = {
        "last_updated": now.isoformat(),
        "timezone": config["timezone"],
        "max_past_weeks": config["max_past_weeks"],
        "last_alert_date": last_alert_date,
        "days": days,
    }

    with open(out_path, "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"  Wrote {len(days)} days to {out_path}")
    print(f"  Date range: {all_dates[0] if all_dates else 'N/A'} to {all_dates[-1] if all_dates else 'N/A'}")
    print("Done.")


if __name__ == "__main__":
    start = sys.argv[1] if len(sys.argv) > 1 else None
    run(start_date=start)
