#!/usr/bin/env python3
"""
build_weather_for_games.py

Uses:
- combined.json
- fbs_stadiums.json

Writes:
- weather.json

Rules:
- ONLY applies weather to outdoor FBS (ncaaf) games.
- If stadium is indoor, skip.
- Uses Open-Meteo hourly forecast (free, no key).
- Safe if files missing.

Requires: requests
"""

import json, os
from datetime import datetime, timezone
import requests

COMBINED_FILE = "combined.json"
STADIUMS_FILE = "fbs_stadiums.json"
OUTFILE = "weather.json"
TIMEOUT = 15
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

def utc_ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

def to_utc_dt(iso_str):
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

def nearest_hour_index(times, target_dt):
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
    combined = load_json(COMBINED_FILE, {})
    stadiums = load_json(STADIUMS_FILE, {})

    games = combined.get("data", [])
    stad_list = stadiums.get("data", [])

    if not games or not stad_list:
        payload = {
            "timestamp": utc_ts(),
            "count": 0,
            "data": [],
            "note": "Missing combined.json or fbs_stadiums.json"
        }
        with open(OUTFILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"⚠️  Wrote empty {OUTFILE}")
        return

    stadium_by_team = {}
    for s in stad_list:
        tn = (s.get("team_name") or "").lower().strip()
        if tn:
            stadium_by_team[tn] = s

    out = []
    errors = []

    for g in games:
        sport_key = g.get("sport_key", "")
        if "americanfootball_ncaaf" not in sport_key:
            continue  # only FBS weather

        home_team = (g.get("home_team") or "").lower().strip()
        commence = to_utc_dt(g.get("commence_time") or "")
        if not home_team or not commence:
            continue

        venue = stadium_by_team.get(home_team)
        if not venue:
            errors.append({"matchup": g.get("matchup"), "reason": "home stadium not found"})
            continue

        if venue.get("indoor"):
            continue  # outdoor-only rule

        lat = venue.get("latitude")
        lon = venue.get("longitude")
        if lat is None or lon is None:
            errors.append({"matchup": g.get("matchup"), "reason": "missing lat/lon"})
            continue

        try:
            wx = get_json(OPEN_METEO_URL, params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "temperature_2m,precipitation,wind_speed_10m,weather_code",
                "timezone": "UTC"
            })

            hourly = wx.get("hourly", {}) or {}
            times = hourly.get("time", []) or []
            if not times:
                raise ValueError("no hourly times from meteo")

            i = nearest_hour_index(times, commence)
            if i is None:
                raise ValueError("no nearest hour")

            row = {
                "matchup": g.get("matchup"),
                "event_id": g.get("event_id"),
                "sport_key": sport_key,
                "commence_time": g.get("commence_time"),
                "home_team": g.get("home_team"),
                "venue_name": venue.get("venue_name"),
                "latitude": lat,
                "longitude": lon,
                "forecast_utc": times[i],
                "temperature_c": (hourly.get("temperature_2m") or [None])[i],
                "wind_kph": (hourly.get("wind_speed_10m") or [None])[i],
                "precip_mm": (hourly.get("precipitation") or [None])[i],
                "weather_code": (hourly.get("weather_code") or [None])[i],
                "outdoor": True,
                "source": "open-meteo"
            }
            out.append(row)

        except Exception as e:
            errors.append({"matchup": g.get("matchup"), "reason": str(e)})

    payload = {
        "timestamp": utc_ts(),
        "count": len(out),
        "data": out,
        "errors": errors or None
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {OUTFILE} with {len(out)} outdoor FBS forecasts")

if __name__ == "__main__":
    main()
