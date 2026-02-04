# Pellet – Running and Scheduling

This guide explains how to run the scraper and set up a daily schedule on Windows.

## Requirements
- Windows 10/11
- Python 3.11+ installed
- Internet access (the script fetches product pages)

## Install dependencies
From the project folder:

```powershell
python -m pip install -r requirements.txt
```

If you don’t have a `requirements.txt`, install directly:

```powershell
python -m pip install requests beautifulsoup4 lxml playwright
```

Download browser binaries for Playwright:

```powershell
python -m playwright install
```

## Run manually
From the project folder:

```powershell
python .\pellet-tracker.py
```

Outputs:
- `pellet_prices.jsonl` (append history)
- `pellet_prices_latest.json` (latest snapshot)
- `pellet_prices.csv`
- `runs.txt`(run logs)

## Schedule daily run (Task Scheduler)
Run these commands in **Command Prompt** (not PowerShell), as your user:

```cmd
schtasks /create /sc daily /st 13:00 /tn "Pellet prices - daily scrape" ^
  /tr "cmd /c cd /d \"C:\Users\USER\Documents\Pellet\" && \"C:\Users\USER\AppData\Local\Microsoft\WindowsApps\python3.13.exe\" \"pellet-tracker.py\"" ^
  /rl highest
```

Why this works:
- `cd /d` sets the working directory so outputs are written to the project folder.
- `python3.13.exe` runs the script with the correct interpreter.

## Verify the schedule
Check status:

```cmd
schtasks /query /tn "Pellet prices - daily scrape" /v /fo LIST
```

Confirm output files were updated:
- Check timestamps on `pellet_prices_latest.json` and `runs.txt`.

## Optional: run when logged off
To run without being logged in, create the task with a specific user and password (default values):

```cmd
schtasks /create /sc daily /st 13:00 /tn "Pellet prices - daily scrape" ^
  /tr "cmd /c cd /d \"C:\Users\USER\Documents\Pellet\" && \"C:\Users\USER\AppData\Local\Microsoft\WindowsApps\python3.13.exe\" \"pellet-tracker.py\"" ^
  /ru "MACHINE_NAME\USER" /rp YOUR_PASSWORD /rl highest
```

Notes:
- Replace `YOUR_PASSWORD` with your Windows password or remove part of the command "/rp YOUR_PASSWORD /rl highest" (not recommend).
- Replace `USER` and `MACHINE_NAME` with current user name
- If you change Python versions, update the `python3.13.exe` path.
