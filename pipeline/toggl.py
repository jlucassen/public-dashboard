"""Toggl Track API client. Fetches time entries and computes daily metrics.

All entries are split at midnight boundaries in local time so that each
calendar day's totals reflect only the hours that fall within that day.
This guarantees work + sleep + other + unendorsed + untracked = 24 for each day.

Sleep semantics:
  - bedtime on day D = start time of the sleep entry that begins on day D
    (going to bed that night)
  - wake_time on day D = stop time of the sleep entry that ends on day D
    (waking up that morning, from last night's entry crossing midnight)
"""

import requests
from datetime import datetime, timedelta
from collections import defaultdict
from zoneinfo import ZoneInfo


TOGGL_API = "https://api.track.toggl.com/api/v9"


def _auth(token: str) -> tuple[str, str]:
    return (token, "api_token")


def get_workspace_and_projects(token: str) -> tuple[int, dict[str, int]]:
    """Returns (workspace_id, {project_name: project_id})."""
    resp = requests.get(f"{TOGGL_API}/me", auth=_auth(token), timeout=30)
    resp.raise_for_status()
    workspace_id = resp.json()["default_workspace_id"]

    resp = requests.get(
        f"{TOGGL_API}/workspaces/{workspace_id}/projects",
        auth=_auth(token),
        timeout=30,
    )
    resp.raise_for_status()
    projects = {p["name"]: p["id"] for p in resp.json()}
    return workspace_id, projects


def fetch_time_entries(
    token: str, start_date: str, end_date: str
) -> list[dict]:
    """Fetch time entries between start_date and end_date (YYYY-MM-DD, local time).

    Toggl limits queries to ~90 days, so we chunk requests automatically.
    The API uses UTC, so we pad the end by 2 days to ensure entries from the
    last local day are captured even at UTC-12. The caller's midnight-split
    logic handles assigning entries to the correct calendar day.
    """
    all_entries = []
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    chunk_days = 89

    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=chunk_days), end)
        params = {
            "start_date": current.strftime("%Y-%m-%dT00:00:00+00:00"),
            "end_date": (chunk_end + timedelta(days=2)).strftime("%Y-%m-%dT00:00:00+00:00"),
        }
        resp = requests.get(
            f"{TOGGL_API}/me/time_entries",
            auth=_auth(token),
            params=params,
            timeout=60,
        )
        resp.raise_for_status()
        entries = resp.json()
        assert isinstance(entries, list), f"Expected list, got {type(entries)}"
        all_entries.extend(entries)
        print(f"  Toggl: fetched {len(entries)} entries for {current.date()} to {chunk_end.date()}")
        current = chunk_end + timedelta(days=1)

    return all_entries


def _split_at_midnight(start_dt: datetime, stop_dt: datetime, tz: ZoneInfo):
    """Split a time range at local-time midnight boundaries.

    Yields (date_str, seconds, contains_original_start, contains_original_end).
    """
    current = start_dt
    while current < stop_dt:
        local = current.astimezone(tz)
        next_midnight = local.replace(
            hour=0, minute=0, second=0, microsecond=0,
        ) + timedelta(days=1)
        next_midnight = next_midnight.astimezone(tz)

        segment_end = min(next_midnight, stop_dt)
        secs = (segment_end - current).total_seconds()
        date_key = local.strftime("%Y-%m-%d")

        if secs > 0:
            yield (
                date_key,
                secs,
                current == start_dt,
                segment_end == stop_dt,
            )

        current = segment_end


def compute_daily_metrics(
    entries: list[dict],
    projects: dict[str, int],
    config: dict,
    tz: ZoneInfo,
) -> dict[str, dict]:
    """Aggregate time entries into daily metrics, splitting at midnight.

    Returns {date_str: {total_hours, work_hours, sleep_hours, other_hours,
                        unendorsed_hours, bedtime, wake_time}}.

    All hour fields use midnight-split segments so that for each day:
        work + sleep + other + unendorsed + untracked = 24
    """
    work_project_ids = {projects[n] for n in config["work_projects"] if n in projects}
    unendorsed_id = projects.get(config["unendorsed_project"])
    sleep_project_id = projects.get(config["sleep_project"])
    sleep_descs = {d.lower() for d in config["sleep_descriptions"]}
    all_project_ids = {projects[n] for n in config["all_projects"] if n in projects}

    missing = [n for n in config["all_projects"] if n not in projects]
    if missing:
        print(f"  WARNING: Toggl projects not found: {missing}")

    days: dict[str, dict] = defaultdict(lambda: {
        "total_seconds": 0,
        "work_seconds": 0,
        "sleep_seconds": 0,
        "unendorsed_seconds": 0,
        "bedtime_dt": None,
        "wake_time_dt": None,
    })

    for entry in entries:
        if entry.get("duration", 0) <= 0:
            continue

        pid = entry.get("project_id") or entry.get("pid")
        start_str = entry.get("start")
        stop_str = entry.get("stop")

        if not start_str or not stop_str:
            continue

        start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00")).astimezone(tz)
        stop_dt = datetime.fromisoformat(stop_str.replace("Z", "+00:00")).astimezone(tz)

        is_tracked = pid in all_project_ids
        is_work = pid in work_project_ids
        is_unendorsed = pid == unendorsed_id

        desc = (entry.get("description") or "").lower()
        is_sleep_category = pid == sleep_project_id and desc in sleep_descs
        is_night_sleep = pid == sleep_project_id and desc == "sleep"

        for date_key, secs, has_start, has_end in _split_at_midnight(start_dt, stop_dt, tz):
            if is_tracked:
                days[date_key]["total_seconds"] += secs
            if is_work:
                days[date_key]["work_seconds"] += secs
            if is_unendorsed:
                days[date_key]["unendorsed_seconds"] += secs
            if is_sleep_category:
                days[date_key]["sleep_seconds"] += secs

            if is_night_sleep:
                early_morning = start_dt.hour < 3

                if has_start:
                    if early_morning:
                        prev = (datetime.strptime(date_key, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
                        existing = days[prev]["bedtime_dt"]
                        if existing is None or start_dt > existing:
                            days[prev]["bedtime_dt"] = start_dt
                    else:
                        existing = days[date_key]["bedtime_dt"]
                        if existing is None or start_dt > existing:
                            days[date_key]["bedtime_dt"] = start_dt

                if has_end and (not has_start or early_morning):
                    existing = days[date_key]["wake_time_dt"]
                    if existing is None or stop_dt < existing:
                        days[date_key]["wake_time_dt"] = stop_dt

    overlap_count = 0
    result = {}
    for date_str, data in sorted(days.items()):
        total_secs = data["total_seconds"]
        if total_secs > 86400 + 60:
            overlap_count += 1
            print(f"  WARNING: {date_str} has {total_secs/3600:.1f}h tracked (overlapping entries), capping at 24h")
            total_secs = 86400

        work_secs = data["work_seconds"]
        sleep_secs = data["sleep_seconds"]
        unendorsed_secs = data["unendorsed_seconds"]
        other_secs = max(0, total_secs - work_secs - sleep_secs - unendorsed_secs)

        day_metrics: dict = {
            "total_hours": round(total_secs / 3600, 2),
            "work_hours": round(work_secs / 3600, 2),
            "sleep_hours": round(sleep_secs / 3600, 2),
            "other_hours": round(other_secs / 3600, 2),
            "unendorsed_hours": round(unendorsed_secs / 3600, 2),
            "bedtime": None,
            "wake_time": None,
        }

        if data["bedtime_dt"]:
            day_metrics["bedtime"] = data["bedtime_dt"].strftime("%H:%M")
        if data["wake_time_dt"]:
            day_metrics["wake_time"] = data["wake_time_dt"].strftime("%H:%M")

        result[date_str] = day_metrics

    if overlap_count:
        print(f"  WARNING: {overlap_count} day(s) had overlapping entries")
    return result
