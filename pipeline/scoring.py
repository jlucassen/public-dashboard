"""Daily scoring: count how many metrics are in the red.

Rating thresholds match those in docs/app.js exactly.
Work counts as 2 metrics worth of importance.
"""


def rate_work(h):
    if h is None:
        return "na"
    if h < 6:
        return "bad"
    if h < 8:
        return "warn"
    if h <= 10:
        return "good"
    return "great"


def rate_sleep(h):
    if h is None:
        return "na"
    if h < 7:
        return "bad"
    if h < 8:
        return "warn"
    if h <= 9:
        return "good"
    if h <= 10:
        return "warn"
    return "bad"


def rate_unendorsed(h):
    if h is None:
        return "na"
    if h == 0:
        return "great"
    if h < 0.5:
        return "good"
    if h < 1:
        return "warn"
    return "bad"


def rate_untracked(h):
    if h is None:
        return "na"
    if h < 0.5:
        return "great"
    if h < 1:
        return "good"
    if h < 2:
        return "warn"
    return "bad"


def _time_to_minutes(t):
    if not t:
        return None
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def rate_wake_time(t):
    mins = _time_to_minutes(t)
    if mins is None:
        return "na"
    if mins < 240:
        return "bad"
    if mins < 300:
        return "warn"
    if mins < 360:
        return "good"
    if mins < 420:
        return "warn"
    return "bad"


def rate_bed_time(t):
    mins = _time_to_minutes(t)
    if mins is None:
        return "na"
    adj = mins + 1440 if mins < 720 else mins
    if adj < 1200:
        return "bad"
    if adj < 1260:
        return "warn"
    if adj < 1320:
        return "good"
    if adj < 1380:
        return "warn"
    return "bad"


def rate_combined_routine(a, b):
    if a is True and b is True:
        return "good"
    if a is True or b is True:
        return "warn"
    if a is False or b is False:
        return "bad"
    return "na"


def rate_single_task(val):
    if val is True:
        return "good"
    if val is False:
        return "bad"
    return "na"


METRIC_DEFS = [
    ("Work", 2, lambda d, t: rate_work(d.get("work_hours"))),
    ("Sleep", 1, lambda d, t: rate_sleep(d.get("sleep_hours"))),
    ("Unendorsed time", 1, lambda d, t: rate_unendorsed(d.get("unendorsed_hours"))),
    ("Untracked time", 1, lambda d, t: rate_untracked(d.get("untracked_hours"))),
    ("Wake time", 1, lambda d, t: rate_wake_time(d.get("wake_time"))),
    ("Bed time", 1, lambda d, t: rate_bed_time(d.get("bedtime"))),
    ("Morning routine", 1, lambda d, t: rate_combined_routine(t.get("Morning Hygiene"), t.get("Morning OODA"))),
    ("Night routine", 1, lambda d, t: rate_combined_routine(t.get("Night Hygiene"), t.get("Night OODA"))),
    ("Fortitude", 1, lambda d, t: rate_single_task(t.get("Fortitude"))),
    ("Eat Healthy", 1, lambda d, t: rate_single_task(t.get("Eat Healthy"))),
]


def get_red_metrics(day: dict) -> tuple[list[str], int]:
    """Return (list of red metric names, total red count with work weighted x2)."""
    todoist = day.get("todoist", {})
    red_names = []
    red_count = 0

    for name, weight, rate_fn in METRIC_DEFS:
        if rate_fn(day, todoist) in ("bad", "na"):
            red_names.append(name)
            red_count += weight

    return red_names, red_count


RED_THRESHOLD = 5


def find_consecutive_red_days(
    days: list[dict],
    today: str,
    threshold: int = RED_THRESHOLD,
    min_streak: int = 2,
) -> list[tuple[str, int, list[str]]] | None:
    """Check completed days (before today) for a streak of >= min_streak bad days.

    Returns the bad-day streak as [(date, red_count, red_names), ...] if found,
    or None if no streak.
    """
    completed = [d for d in days if d["date"] < today]
    if len(completed) < min_streak:
        return None

    streak = []
    for day in reversed(completed):
        red_names, red_count = get_red_metrics(day)
        if red_count >= threshold:
            streak.append((day["date"], red_count, red_names))
        else:
            break

    if len(streak) < min_streak:
        return None

    streak.reverse()
    return streak
