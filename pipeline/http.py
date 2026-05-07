"""HTTP helper with retries for transient failures.

Third-party APIs (Toggl, Todoist) occasionally return 5xx / 429 or drop
connections. The pipeline runs hourly, so a single transient blip should
not fail the whole run -- but if retries are exhausted we still raise so
the failure is loud and visible (per the project's fail-fast policy).
"""

import random
import time

import requests


RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_BASE_BACKOFF_SEC = 2.0
DEFAULT_MAX_BACKOFF_SEC = 60.0


def _compute_backoff(
    attempt: int,
    retry_after: str | None,
    base: float,
    cap: float,
) -> float:
    """Honor server-provided Retry-After (in seconds), else exponential + jitter."""
    if retry_after:
        try:
            return min(float(retry_after), cap)
        except ValueError:
            pass
    delay = min(base * (2 ** (attempt - 1)), cap)
    return delay + random.uniform(0, delay * 0.25)


def get_with_retries(
    url: str,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_backoff: float = DEFAULT_BASE_BACKOFF_SEC,
    max_backoff: float = DEFAULT_MAX_BACKOFF_SEC,
    **kwargs,
) -> requests.Response:
    """GET `url`, retrying on transient errors (5xx, 429, connection issues).

    Raises on final failure. `kwargs` are passed to `requests.get`.
    """
    assert max_attempts >= 1, "max_attempts must be >= 1"
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            if attempt == max_attempts:
                raise
            delay = _compute_backoff(attempt, None, base_backoff, max_backoff)
            print(
                f"  HTTP {type(e).__name__} on {url} "
                f"(attempt {attempt}/{max_attempts}), retrying in {delay:.1f}s"
            )
            time.sleep(delay)
            continue

        if resp.status_code in RETRY_STATUS_CODES and attempt < max_attempts:
            delay = _compute_backoff(
                attempt, resp.headers.get("Retry-After"), base_backoff, max_backoff,
            )
            print(
                f"  HTTP {resp.status_code} on {url} "
                f"(attempt {attempt}/{max_attempts}), retrying in {delay:.1f}s"
            )
            time.sleep(delay)
            continue

        return resp

    assert last_exc is not None, "unreachable: loop must either return or raise"
    raise last_exc
