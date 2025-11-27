#!/usr/bin/env python3
"""
Fetch weather for every venue using stadiums_master.json.
Never relies on combined.json for lat/lon.
"""

import json, requests, time
from pathlib import Path

MASTER = Path("stadiums_master.json")
OUTFILE = Path("weather_raw.json")

HEADERS = {"User-Agent": "fbf-weather-fetcher"}

def load_master():
    if not MASTER.exists():
        print("❌ stadiums_master.json missing")
        return {}
    with open(MASTER, "r") as f:
        return json.load(f)

def fetch_point(lat, lon):
    try:
        url = f"https://api.weather.gov/points/{lat},{lon}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        return r.json()["properties"]["forecastHourly"]
    except:
        return None

def fetch_hourly(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def main():
    stadiums = load_master()
    keys = list(stadiums.keys())

    results = []

    print(f"🔎 Fetching weather for {len(keys)} venues...")

    for key, v in stadiums.items():
        lat = v.get("lat")
        lon = v.get("lon")
        tid = v.get("team_id")

        if not lat or not lon:
            results.append({"key": key, "team_id": tid, "error": "missing_coords"})
            continue

        point_url = fetch_point(lat, lon)
        if not point_url:
            results.append({"key": key, "team_id": tid, "error": "point_lookup_failed"})
            continue

        hourly = fetch_hourly(point_url)
        if not hourly:
            results.append({"key": key, "team_id": tid, "error": "hourly_failed"})
            continue

        p = hourly["properties"]["periods"][0]  # nearest forecast

        results.append({
            "key": key,
            "team_id": tid,
            "temperatureF": p.get("temperature"),
            "windSpeedMph": p.get("windSpeed"),
            "shortForecast": p.get("shortForecast"),
        })

        time.sleep(0.25)  # polite

    with open(OUTFILE, "w") as f:
        json.dump({"data": results}, f, indent=2)

    print(f"✅ Weather written → {OUTFILE}")

if __name__ == "__main__":
    main()
