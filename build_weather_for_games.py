#!/usr/bin/env python3
"""
build_weather.py

Uses:
- fbs_stadiums.json for NCAAF FBS outdoor weather
- ESPN NFL venues for NFL outdoor weather
- combined.json games list

Outputs:
- weather.json

Rules:
- Outdoor stadiums only
- Nearest hourly forecast to kickoff time (UTC)
- Open-Meteo, no key
- Safe if inputs missing

No color/layout logic here—just data.
"""

import json, os
from datetime import datetime, timezone
import requests

STADIUMS_FILE = "fbs_stadiums.json"
COMBINED_FILE = "combined.json"
OUTFILE = "weather.json"
TIMEOUT = 12

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

NFL_TEAMS_URL = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/teams?limit=64"

KNOWN_NFL_INDOOR = {
    "allegiant stadium", "at&t stadium", "caesars superdome", "ford field",
    "lucas oil stadium", "mercedes-benz stadium", "nrg stadium",
    "sofi stadium", "state farm stadium", "u.s. bank stadium",
}

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

def load_fbs_venues():
    payload = load_json(STADIUMS_FILE, {})
    venues = payload.get("data", [])
    by_team = {}
    for v in venues:
        tn = (v.get("team_name") or "").lower()
        if tn:
            by_team[tn] = v
    return by_team

def load_nfl_venues():
    by_team = {}
    try:
        teams = get_json(NFL_TEAMS_URL).get("items", [])
        for t in teams:
            ref = t.get("$ref")
            if not ref:
                continue
            team = get_json(ref)
            name = (team.get("displayName") or "").lower()
            venue_ref = team.get("venue", {}).get("$ref")
            if not venue_ref:
                continue
            venue = get_json(venue_ref)
            loc = venue.get("location", {}) or {}
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            if lat is None or lon is None:
                continue
            vname = (venue.get("fullName") or venue.get("name") or "").lower()
            indoor = venue.get("isIndoor")
            if indoor is None:
                indoor = vname in KNOWN_NFL_INDOOR
            by_team[name] = {
                "team_name": team.get("displayName"),
                "venue_name": venue.get("fullName") or venue.get("name"),
                "latitude": float(lat),
                "longitude": float(lon),
                "indoor": bool(indoor),
                "source": "espn-core",
            }
    except Exception:
        pass
    return by_team

def main():
    combined = load_json(COMBINED_FILE, {})
    games = combined.get("data", [])

    if not games:
        payload = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
            "count": 0,
            "data": [],
            "note": "Missing combined.json or no games",
        }
        with open(OUTFILE, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"⚠️ Wrote empty {OUTFILE}")
        return

    fbs_by_team = load_fbs_venues()
    nfl_by_team = load_nfl_venues()

    out, errors = [], []

    for g in games:
        sport_key = g.get("sport_key","")
        home_team = (g.get("home_team") or "").lower()
        commence = to_utc_dt(g.get("commence_time") or "")
        if not commence:
            continue

        venue = None
        if "ncaaf" in sport_key:
            venue = fbs_by_team.get(home_team)
        elif "nfl" in sport_key:
            venue = nfl_by_team.get(home_team)

        if not venue:
            continue
        if venue.get("indoor"):
            continue  # outdoor only

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
                raise ValueError("no hourly times returned")

            i = nearest_hour_index(times, commence)
            if i is None:
                raise ValueError("no nearest hour")

            out.append({
                "matchup": g.get("matchup"),
                "event_id": g.get("event_id"),
                "sport_key": sport_key,
                "commence_time": g.get("commence_time"),
                "home_team": g.get("home_team"),
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
            })

        except Exception as e:
            errors.append({"matchup": g.get("matchup"), "reason": str(e)})

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "count": len(out),
        "data": out,
        "errors": errors or None,
    }

    with open(OUTFILE, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"✅ Wrote {OUTFILE} with {len(out)} outdoor forecasts")

if __name__ == "__main__":
    main()
