#!/usr/bin/env python3
"""
build_weather.py

Uses fbs_stadiums.json + combined.json to attach outdoor-only weather.
- Only applies to outdoor stadiums.
- Uses Open-Meteo forecast (no key).
- Output: weather.json

Safe if inputs missing.
"""

import json, os, math
from datetime import datetime, timezone
import requests

STADIUMS_FILE = "fbs_stadiums.json"
COMBINED_FILE = "combined.json"
OUTFILE = "weather.json"
TIMEOUT = 12

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

def get_json(url, params=None):
    r = requests.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def to_utc_dt(iso_str):
    try:
        return datetime.fromisoformat(iso_str.replace("Z","+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

def nearest_hour_index(times, target_dt):
    # times are ISO strings in UTC
    best_i, best_diff = None, None
    for i, ts in enumerate(times):
        dt = to_utc_dt(ts)
        if not dt:
            continue
        diff = abs((dt - target_dt).total_seconds())
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_i = i
    return best_i

def main():
    stadiums_payload = load_json(STADIUMS_FILE, {})
    combined_payload = load_json(COMBINED_FILE, {})

    stadiums = stadiums_payload.get("data", [])
    games = combined_payload.get("data", [])

    if not stadiums or not games:
        payload = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
            "data": [],
            "note": "Missing fbs_stadiums.json or combined.json",
        }
        with open(OUTFILE, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"⚠️  Wrote empty {OUTFILE} (no inputs)")
        return

    # Map venue by team name (best-effort matching)
    venue_by_team = {}
    for s in stadiums:
        tn = (s.get("team_name") or "").lower()
        if tn:
            venue_by_team[tn] = s

    out = []
    errors = []

    for g in games:
        sport_key = g.get("sport_key","")
        if "ncaaf" not in sport_key:
            continue  # only FBS weather for now

        home_team = (g.get("home_team") or "").lower()
        away_team = (g.get("away_team") or "").lower()
        commence = to_utc_dt(g.get("commence_time") or "")
        if not commence:
            continue

        venue = venue_by_team.get(home_team)
        if not venue:
            errors.append({"matchup": g.get("matchup"), "reason": "home venue not found"})
            continue

        if venue.get("indoor"):
            # outdoor only rule
            continue

        lat, lon = venue["latitude"], venue["longitude"]

        try:
            params = {
                "latitude": lat,
                "longitude": lon,
                "hourly": "temperature_2m,precipitation,wind_speed_10m,weather_code",
                "timezone": "UTC",
            }
            wx = get_json(OPEN_METEO_URL, params=params)
            hourly = wx.get("hourly", {})
            times = hourly.get("time", [])
            if not times:
                raise ValueError("no hourly times")

            i = nearest_hour_index(times, commence)
            if i is None:
                raise ValueError("no nearest hour")

            entry = {
                "matchup": g.get("matchup"),
                "event_id": g.get("event_id"),
                "sport_key": sport_key,
                "commence_time": g.get("commence_time"),
                "venue_name": venue.get("venue_name"),
                "latitude": lat,
                "longitude": lon,
                "forecast_utc": times[i],
                "temperature_c": hourly.get("temperature_2m", [None])[i],
                "wind_kph": hourly.get("wind_speed_10m", [None])[i],
                "precip_mm": hourly.get("precipitation", [None])[i],
                "weather_code": hourly.get("weather_code", [None])[i],
                "outdoor": True,
                "source": "open-meteo",
            }
            out.append(entry)

        except Exception as e:
            errors.append({"matchup": g.get("matchup"), "reason": str(e)})

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "count": len(out),
        "data": out,
        "errors": errors or None,
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {OUTFILE} with {len(out)} weather rows (outdoor only)")

if __name__ == "__main__":
    main()
