# Productivity Dashboard

A static dashboard hosted on GitHub Pages that aggregates daily productivity metrics from multiple data sources.

## Data Sources

- **Toggl Track**: Total hours, sleep (bedtime, wake time, duration), work hours, unendorsed activity hours
- **Todoist**: Morning and evening routine task completion
- **Google Forms**: Custom habit ratings (1-5 scale, flexible questions)
- **Freedom**: App uptime tracking via local process monitor

## Architecture

A Python pipeline runs nightly via GitHub Actions. It fetches raw data from each source, computes aggregated metrics, and commits a single `metrics.json` file to the repo. The static frontend reads this JSON and renders charts. Raw data never touches the public repo.

## Setup

### 1. Environment Variables

Copy `.env.example` to `.env` and fill in:

```
TOGGL_TOKEN=your_toggl_api_token
TODOIST_TOKEN=your_todoist_api_token
DAILY_FORM_SHEET_ID=your_google_sheet_id
GOOGLE_CREDENTIALS_PATH=/path/to/service-account.json
```

### 2. Python Environment

```bash
uv venv
uv pip install requests python-dotenv pyyaml google-api-python-client google-auth
```

### 3. Google Cloud Setup

1. Create a Google Cloud project and enable the Google Sheets API
2. Create a service account and download the JSON key
3. Share your Google Sheet with the service account email
4. Set `GOOGLE_CREDENTIALS_PATH` in `.env` to the key file path

### 4. GitHub Secrets

Add these secrets to your GitHub repo (Settings > Secrets and variables > Actions):

- `TOGGL_TOKEN`
- `TODOIST_TOKEN`
- `DAILY_FORM_SHEET_ID`
- `GOOGLE_CREDENTIALS` (the full JSON content of the service account key)

### 5. GitHub Pages

Enable GitHub Pages from the repo settings, serving from the `docs/` directory on the `main` branch.

### 6. Freedom Tracker (Optional)

Install the local process monitor:

```bash
chmod +x freedom_tracker/install.sh
./freedom_tracker/install.sh
```

This installs two launchd agents:
- **Tracker**: checks if Freedom is running every 5 minutes, logs locally
- **Daily Summary**: pushes the day's uptime to Google Sheets at 11:55 PM

### Run Pipeline Locally

```bash
source .venv/bin/activate
python -m pipeline.main
```

Optionally pass a start date: `python -m pipeline.main 2025-01-01`

## Configuration

Edit `pipeline/config.yaml` to adjust:
- Toggl project names and sleep description
- Todoist task names for morning/evening routines
- Google Sheets tab names
- Timezone
