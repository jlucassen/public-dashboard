"""Toggl Track API client. Fetches time entries and computes daily metrics.

Non-sleep categories (work, other, unendorsed, untracked) are split at
midnight boundaries in local time, reflecting 24-hour calendar days.

Sleep uses noon-to-noon windows for more intuitive day assignment:
  - bedtime on day D  = start of the first "Sleep" entry starting after noon on day D
  - wake_time on day D = end of the last "Sleep" entry starting in [noon(D-1), noon(D))
  - sleep_hours on day D = total sleep/nap time in [bedtime(D-1), bedtime(D))

Because sleep uses a variable-length window, the time categories will not
always sum to exactly 24 hours. Untracked is the residual of the 24-hour
midnight-to-midnight window.
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
    """Aggregate time entries into daily metrics.

    Returns {date_str: {total_hours, work_hours, sleep_hours, other_hours,
                        unendorsed_hours, bedtime, wake_time}}.

    Non-sleep categories use midnight-split 24-hour days. Sleep metrics use
    noon-to-noon windows (see module docstring). The time categories will not
    always sum to 24 hours.
    """
    work_project_ids = {projects[n] for n in config["work_projects"] if n in projects}
    unendorsed_id = projects.get(config["unendorsed_project"])
    sleep_project_id = projects.get(config["sleep_project"])
    sleep_descs = {d.lower() for d in config["sleep_descriptions"]}
    all_project_ids = {projects[n] for n in config["all_projects"] if n in projects}

    missing = [n for n in config["all_projects"] if n not in projects]
    if missing:
        print(f"  WARNING: Toggl projects not found: {missing}")

    # -- Phase 1: Midnight-split aggregation (all categories) --
    days: dict[str, dict] = defaultdict(lambda: {
        "total_seconds": 0,
        "work_seconds": 0,
        "sleep_seconds_midnight": 0,
        "unendorsed_seconds": 0,
    })

    night_sleep_entries: list[tuple[datetime, datetime]] = []
    all_sleep_entries: list[tuple[datetime, datetime]] = []

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

        if is_night_sleep:
            night_sleep_entries.append((start_dt, stop_dt))
        if is_sleep_category:
            all_sleep_entries.append((start_dt, stop_dt))

        for date_key, secs, _, _ in _split_at_midnight(start_dt, stop_dt, tz):
            if is_tracked:
                days[date_key]["total_seconds"] += secs
            if is_work:
                days[date_key]["work_seconds"] += secs
            if is_unendorsed:
                days[date_key]["unendorsed_seconds"] += secs
            if is_sleep_category:
                days[date_key]["sleep_seconds_midnight"] += secs

    # -- Phase 2: Bedtime and wake time (noon-to-noon windows) --
    # An entry starting at/after noon on day D -> window D = [noon(D), noon(D+1)).
    # An entry starting before noon on day D  -> window D-1 = [noon(D-1), noon(D)).
    # bedtime(window_day) = earliest start in that window.
    # wake_time(window_day + 1) = latest stop in that window.
    window_sleep: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)

    for start_dt, stop_dt in night_sleep_entries:
        local_date = start_dt.date()
        window_day = local_date if start_dt.hour >= 12 else local_date - timedelta(days=1)
        window_sleep[window_day.strftime("%Y-%m-%d")].append((start_dt, stop_dt))

    bedtimes: dict[str, datetime] = {}
    wake_times: dict[str, datetime] = {}

    for window_day_str, sleeps in window_sleep.items():
        window_day = datetime.strptime(window_day_str, "%Y-%m-%d").date()
        next_day_str = (window_day + timedelta(days=1)).strftime("%Y-%m-%d")

        earliest_start = min(s for s, _ in sleeps)
        if window_day_str not in bedtimes or earliest_start < bedtimes[window_day_str]:
            bedtimes[window_day_str] = earliest_start

        latest_stop = max(e for _, e in sleeps)
        if next_day_str not in wake_times or latest_stop > wake_times[next_day_str]:
            wake_times[next_day_str] = latest_stop

    # -- Phase 3: Sleep hours (bedtime-to-bedtime windows) --
    # sleep_hours for day D = total sleep/nap time in [bedtime(D-1), bedtime(D)).
    all_sleep_entries.sort(key=lambda x: x[0])
    all_dates = sorted(set(days.keys()) | set(bedtimes.keys()) | set(wake_times.keys()))
    sleep_hours_map: dict[str, float | None] = {}

    for date_str in all_dates:
        day = datetime.strptime(date_str, "%Y-%m-%d").date()
        prev_day_str = (day - timedelta(days=1)).strftime("%Y-%m-%d")

        bt_start = bedtimes.get(prev_day_str)
        bt_end = bedtimes.get(date_str)

        if bt_start is None or bt_end is None:
            sleep_hours_map[date_str] = None
            continue

        assert bt_start < bt_end, (
            f"bedtime window inverted for {date_str}: "
            f"bedtime({prev_day_str})={bt_start} >= bedtime({date_str})={bt_end}"
        )

        total_sleep_secs = 0.0
        for s, e in all_sleep_entries:
            if s >= bt_end:
                break
            clip_start = max(s, bt_start)
            clip_end = min(e, bt_end)
            if clip_start < clip_end:
                total_sleep_secs += (clip_end - clip_start).total_seconds()

        sleep_hours_map[date_str] = total_sleep_secs / 3600

    # -- Phase 4: Build output --
    overlap_count = 0
    result = {}
    for date_str in all_dates:
        data = days[date_str]
        total_secs = data["total_seconds"]
        if total_secs > 86400 + 60:
            overlap_count += 1
            print(f"  WARNING: {date_str} has {total_secs/3600:.1f}h tracked (overlapping entries), capping at 24h")
            total_secs = 86400

        work_secs = data["work_seconds"]
        sleep_secs_midnight = data["sleep_seconds_midnight"]
        unendorsed_secs = data["unendorsed_seconds"]
        other_secs = max(0, total_secs - work_secs - sleep_secs_midnight - unendorsed_secs)

        sleep_hrs = sleep_hours_map.get(date_str)
        day_metrics: dict = {
            "total_hours": round(total_secs / 3600, 2),
            "work_hours": round(work_secs / 3600, 2),
            "sleep_hours": round(sleep_hrs, 2) if sleep_hrs is not None else None,
            "other_hours": round(other_secs / 3600, 2),
            "unendorsed_hours": round(unendorsed_secs / 3600, 2),
            "bedtime": None,
            "wake_time": None,
        }

        if date_str in bedtimes:
            day_metrics["bedtime"] = bedtimes[date_str].strftime("%H:%M")
        if date_str in wake_times:
            day_metrics["wake_time"] = wake_times[date_str].strftime("%H:%M")

        result[date_str] = day_metrics

    if overlap_count:
        print(f"  WARNING: {overlap_count} day(s) had overlapping entries")
    return result
