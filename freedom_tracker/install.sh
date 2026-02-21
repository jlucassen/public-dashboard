#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "ERROR: Virtual environment not found at $PROJECT_DIR/.venv"
    echo "Run 'uv venv && uv pip install -e .' from the project root first."
    exit 1
fi

mkdir -p "$LAUNCH_AGENTS"
mkdir -p "$HOME/.freedom_tracker"

echo "Installing Freedom tracker launchd agents..."

for plist_template in "$SCRIPT_DIR"/com.dashboard.*.plist; do
    plist_name="$(basename "$plist_template")"
    dest="$LAUNCH_AGENTS/$plist_name"

    launchctl bootout "gui/$(id -u)/$plist_name" 2>/dev/null || true

    sed -e "s|__VENV_PYTHON__|$VENV_PYTHON|g" \
        -e "s|__TRACKER_SCRIPT__|$SCRIPT_DIR/tracker.py|g" \
        -e "s|__SUMMARY_SCRIPT__|$SCRIPT_DIR/daily_summary.py|g" \
        -e "s|__HOME__|$HOME|g" \
        -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
        "$plist_template" > "$dest"

    launchctl bootstrap "gui/$(id -u)" "$dest"
    echo "  Installed: $plist_name"
done

echo ""
echo "Freedom tracker installed successfully."
echo "  - Tracker runs every 5 minutes"
echo "  - Daily summary pushes to Google Sheets at 11:55 PM"
echo "  - Logs at ~/.freedom_tracker/"
echo ""
echo "To uninstall:"
echo "  launchctl bootout gui/\$(id -u)/com.dashboard.freedom-tracker"
echo "  launchctl bootout gui/\$(id -u)/com.dashboard.freedom-summary"
