"""Todoist API client. Checks daily completion of individual recurring tasks via activity log."""

import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


TODOIST_API = "https://api.todoist.com/api/v1"


def fetch_completed_items(
    token: str, since: str, until: str, limit: int = 100
) -> list[dict]:
    """Fetch completed-task activity events from Todoist API v1.

    Uses the activity log which, unlike the tasks/completed endpoints,
    includes recurring task check-offs.
    """
    all_events: list[dict] = []
    cursor = None

    while True:
        params: dict = {
            "event_type": "completed",
            "object_type": "item",
            "limit": limit,
        }
        if cursor:
            params["cursor"] = cursor

        resp = requests.get(
            f"{TODOIST_API}/activities",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        all_events.extend(results)

        label = f"cursor={cursor[:12]}..." if cursor else "initial"
        print(f"  Todoist: fetched {len(results)} activity events ({label})")

        cursor = data.get("next_cursor")
        if not cursor or not results:
            break

    return all_events


def compute_daily_completions(
    events: list[dict],
    config: dict,
    tz: ZoneInfo,
    start_date: str,
    end_date: str,
) -> dict[str, dict[str, bool]]:
    """Check per-task completion for each day in the date range.

    For past days, a missing completion means the task was missed (False).
    For today, missing means not yet completed (None).

    Returns {date_str: {task_name: True/False/None}}.
    """
    all_task_names = config["morning_tasks"] + config["evening_tasks"]
    all_task_names_lower = {n.lower(): n for n in all_task_names}

    completed_pairs: set[tuple[str, str]] = set()

    for event in events:
        extra = event.get("extra_data") or {}
        content = (extra.get("content") or "").lower().strip()
        event_date = event.get("event_date")
        if not event_date:
            continue

        if content not in all_task_names_lower:
            continue

        try:
            dt = datetime.fromisoformat(event_date.replace("Z", "+00:00")).astimezone(tz)
        except (ValueError, TypeError):
            continue

        date_key = dt.strftime("%Y-%m-%d")
        completed_pairs.add((date_key, content))

    today = datetime.now(tz).strftime("%Y-%m-%d")

    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    result: dict[str, dict[str, bool]] = {}
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        day_data: dict[str, bool | None] = {}

        for task_lower, task_name in all_task_names_lower.items():
            if (date_str, task_lower) in completed_pairs:
                day_data[task_name] = True
            elif date_str < today:
                day_data[task_name] = False
            else:
                day_data[task_name] = None

        result[date_str] = day_data
        current += timedelta(days=1)

    return result
