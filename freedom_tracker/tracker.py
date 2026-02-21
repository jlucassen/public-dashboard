#!/usr/bin/env python3
"""Freedom process tracker. Checks if Freedom is running and logs the result.

Run every 5 minutes via launchd. Logs to ~/.freedom_tracker/YYYY-MM-DD.csv.
"""

import csv
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")
LOG_DIR = Path.home() / ".freedom_tracker"


def is_freedom_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-xi", "freedom"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error checking Freedom process: {e}", file=sys.stderr)
        return False


def log_status():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(TZ)
    log_file = LOG_DIR / f"{now.strftime('%Y-%m-%d')}.csv"

    running = is_freedom_running()

    is_new = not log_file.exists()
    with open(log_file, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp", "running"])
        writer.writerow([now.isoformat(), int(running)])


if __name__ == "__main__":
    log_status()
