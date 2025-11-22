#!/usr/bin/env python3
"""
build_weather_for_games.py

Uses combined.json + venues.json.

Weather rules:
- venue_type == "outdoor"    => fetch forecast
- venue_type == "indoor"     => skip (weather_applicable: false)
- venue_type == "retractable"=> Rule B: assume indoor unless verified open
                               so skip with reason "retractable_assumed_closed"

Forecast provider:
Open-Meteo hourly forecast (no key).

Output:
  weather.json

Structure:
{
  "timestamp": "...",
  "data": [
     {
       "event_id": "...",
       "matchup": "...",
       "home_team": "...",
       "venue": "...",
       "venue_type": "...",
       "weather_applicable": true|false,
       "skip_reason": null | "...",
       "forecast": {
          "temp_c": ...,
          "wind_kph": ...,
          "precip_mm": ...,
          "weathercode": ...,
          "time_utc": "..."
       }
     }, ...
  ]
}
"""

import json
import os
import math
import requests
from datetime import datetime, timezone

OUTFILE = "weather.json"
TIMEOUT = 12


def safe_float(x):
    try:
        return float(x)
    except Exception:
        return None


def parse_iso_z(s: str):
    # expects "2025-11-16T18:00:00Z"
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def nearest_hour_index(times, target_dt_utc):
    """Find index of closest hourly time in list."""
    if not times or not target_dt_utc:
        return None
    # times are strings in ISO format like "2025-11-16T18:00"
    best_i, best_delta = None, None
    for i, t in enumerate(times):
        dt_i = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
        delta = abs((dt_i - target_dt_utc).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_i = i
    return best_i


def fetch_open_meteo_hourly(lat, lon, start_dt_utc):
    """
    Fetch hourly forecast around game time.
    We'll ask for hourly in UTC to keep alignment easy.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,precipitation,weathercode,windspeed_10m",
        "timezone": "UTC",
        "forecast_days": 7
    }
    r = requests.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def main():
    if not os.path.exists("combined.json"):
        raise SystemExit("❌ combined.json not found.")
    if not os.path.exists("venues.json"):
        raise SystemExit("❌ venues.json not found. Run build_venues_from_combined.py first.")

    with open("combined.json", "r", encoding="utf-8") as f:
        combined = json.load(f)
    with open("venues.json", "r", encoding="utf-8") as f:
        venues_payload = json.load(f)

    games = combined.get("data", [])
    venues = venues_payload.get("venues", {})

    out = []
    print(f"[🌦️] Building weather for {len(games)} games...")

    for g in games:
        home = g.get("home_team")
        if not home:
            continue

        venue_rec = venues.get(home)
        base = {
            "event_id": g.get("event_id"),
            "matchup": g.get("matchup"),
            "sport_key": g.get("sport_key"),
            "home_team": home,
            "away_team": g.get("away_team"),
            "commence_time": g.get("commence_time"),
            "venue": venue_rec.get("venue") if venue_rec else None,
            "venue_type": venue_rec.get("venue_type") if venue_rec else None,
            "weather_applicable": False,
            "skip_reason": None,
            "forecast": None
        }

        if not venue_rec:
            base["skip_reason"] = "no_venue_found"
            out.append(base)
            continue

        vtype = venue_rec.get("venue_type")
        lat = venue_rec.get("lat")
        lon = venue_rec.get("lon")

        if vtype == "indoor":
            base["skip_reason"] = "indoor_venue"
            out.append(base)
            continue

        if vtype == "retractable":
            # RULE B: assume indoor unless verified open
            base["skip_reason"] = "retractable_assumed_closed"
            out.append(base)
            continue

        # Outdoor only from here
        game_dt = parse_iso_z(g.get("commence_time"))
        if not game_dt or lat is None or lon is None:
            base["skip_reason"] = "missing_time_or_coords"
            out.append(base)
            continue

        try:
            wx = fetch_open_meteo_hourly(lat, lon, game_dt)
            hourly = wx.get("hourly", {})
            times = hourly.get("time", [])
            idx = nearest_hour_index(times, game_dt)

            if idx is None:
                base["skip_reason"] = "forecast_not_found"
                out.append(base)
                continue

            temp_c = safe_float(hourly.get("temperature_2m", [None])[idx])
            precip_mm = safe_float(hourly.get("precipitation", [None])[idx])
            wind_kph = safe_float(hourly.get("windspeed_10m", [None])[idx])
            weathercode = hourly.get("weathercode", [None])[idx]

            base["weather_applicable"] = True
            base["forecast"] = {
                "time_utc": times[idx] + "Z",
                "temp_c": temp_c,
                "precip_mm": precip_mm,
                "wind_kph": wind_kph,
                "weathercode": weathercode
            }
            out.append(base)

        except Exception as e:
            base["skip_reason"] = f"forecast_error: {e}"
            out.append(base)

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "data": out
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"[✅] Saved {OUTFILE} with {len(out)} records.")


if __name__ == "__main__":
    main()
