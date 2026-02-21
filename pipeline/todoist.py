"""Todoist API client. Checks daily completion of individual recurring tasks."""

import requests
from datetime import datetime
from collections import defaultdict
from zoneinfo import ZoneInfo


TODOIST_API = "https://api.todoist.com/api/v1"


def fetch_completed_items(
    token: str, since: str, until: str, limit: int = 200
) -> list[dict]:
    """Fetch all completed items from Todoist API v1.

    Args:
        token: Todoist API token
        since: ISO datetime string for range start
        until: ISO datetime string for range end
        limit: items per page (max 200)
    """
    all_items = []
    cursor = None

    while True:
        params = {"since": since, "until": until, "limit": limit}
        if cursor:
            params["cursor"] = cursor

        resp = requests.get(
            f"{TODOIST_API}/tasks/completed/by_completion_date",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        all_items.extend(items)

        print(f"  Todoist: fetched {len(items)} completed items (cursor={'yes' if cursor else 'initial'})")

        cursor = data.get("next_cursor")
        if not cursor or not items:
            break

    return all_items


def compute_daily_completions(
    items: list[dict],
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

    for item in items:
        content = (item.get("content") or "").lower().strip()
        completed_at = item.get("completed_at")
        if not completed_at:
            continue

        if content not in all_task_names_lower:
            continue

        try:
            dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00")).astimezone(tz)
        except (ValueError, TypeError):
            continue

        date_key = dt.strftime("%Y-%m-%d")
        completed_pairs.add((date_key, content))

    today = datetime.now(tz).strftime("%Y-%m-%d")

    from datetime import timedelta
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
