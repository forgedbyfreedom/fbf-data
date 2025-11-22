#!/usr/bin/env python3
"""
build_weather.py

Uses:
  - fbs_stadiums.json
  - combined.json

Produces:
  - weather.json

Behavior:
  • Only applies weather to OUTDOOR stadiums.
  • Fetches hourly weather using free Open-Meteo API (no key needed).
  • Matches games by home team → stadium.
  • Picks hour closest to kickoff.
  • Safe if input files missing (outputs empty weather.json).
"""

import json
import os
import requests
from datetime import datetime, timezone

STADIUMS_FILE = "fbs_stadiums.json"
COMBINED_FILE = "combined.json"
OUTFILE = "weather.json"
TIMEOUT = 12

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def load_json(path, default):
    """Load JSON or return default if file missing."""
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        

def get_json(url, params=None):
    r = requests.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def to_utc_dt(iso_str):
    """Convert ISO8601 → UTC datetime."""
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(timezone.ut_
