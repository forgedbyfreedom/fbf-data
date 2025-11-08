#!/usr/bin/env python3
# ==========================================================
# Timestamp & Run-History Logger for cron + manual runs
# ==========================================================
import datetime, sys, time, os

# Define log file path (same folder as this script)
LOG_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_HISTORY_PATH = os.path.join(LOG_DIR, "run_history.log")

# Record start time
start_time = time.time()
timestamp_start = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")

# Header printed to console + cron log
sys.stdout.write(f"\n{timestamp_start} 🕒 Starting fetch_multi.py run...\n")
sys.stdout.flush()

# Also append header to persistent run_history.log
with open(RUN_HISTORY_PATH, "a") as rh:
    rh.write(f"{timestamp_start} 🕒 Starting fetch_multi.py run...\n")

# ==========================================================
# ↓↓↓ Your existing imports and main logic go below ↓↓↓
# ==========================================================
# Example:
import os, json, requests, datetime as dt, pathlib, sys, shutil, glob, csv

error = None
try:
    # === Your existing code starts here ===
    # e.g., fetch NFL/NCAAF/weather/referees/injuries/power_ratings
    # write combined.json, etc.
    # --------------------------------------
    # (leave your full logic intact)
    # --------------------------------------
    pass  # <-- remove this placeholder once you paste around real code
    # === Your existing code ends here ===

except Exception as e:
    error = e
    # print to console/cron
    err_time = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    sys.stdout.write(f"{err_time} ❌ Error: {e}\n")
    sys.stdout.flush()
    # mirror to persistent log
    with open(RUN_HISTORY_PATH, "a") as rh:
        rh.write(f"{err_time} ❌ Error: {e}\n")

# ==========================================================
# Completion logger (always runs, even if error)
# ==========================================================
end_time = time.time()
runtime_sec = round(end_time - start_time, 2)
timestamp_end = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")

if error:
    status_msg = f"{timestamp_end} ⚠️  Fetch finished with errors. Runtime: {runtime_sec}s.\n\n"
else:
    status_msg = f"{timestamp_end} ✅ Fetch complete. Runtime: {runtime_sec}s.\n\n"

# Print to console + cron log
sys.stdout.write(status_msg)
sys.stdout.flush()

# Append to persistent run_history.log
with open(RUN_HISTORY_PATH, "a") as rh:
    rh.write(status_msg)
# ==========================================================

