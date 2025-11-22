#!/usr/bin/env python3
"""
fetch_weather.py
- Reads combined.json
- For outdoor stadiums only, fetches forecast near kickoff from OpenWeather One Call 3.0
- Writes weather.json
- Adds g["weather"] to combined.json (outdoor games only)

Requires env: OPENWEATHER_API_KEY
Endpoint: https://api.openweathermap.org/data/3.0/onecall?lat=..&lon=..&appid=..&units=imperial
"""

import os, json, requests
from datetime import datetime, timezone
from dateutil import parser as dateparser

OW_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
if not OW_KEY:
    print("⚠️  OPENWEATHER_API_KEY not set. Skipping weather.")
    OW_KEY = None

STADIUMS_FILE = "stadiums_outdoor.json"
WEATHER_OUT = "weather.json"
TIMEOUT = 12

def get_json(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def load_stadiums():
    if not os.path.exists(STADIUMS_FILE):
        return {}
    with open(STADIUMS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def closest_hourly(hourlies, target_ts):
    if not hourlies:
        return None
    return min(hourlies, key=lambda h: abs(h.get("dt", 0) - target_ts))

def main():
    if not os.path.exists("combined.json"):
        print("❌ combined.json missing")
        return

    stadiums = load_stadiums()
    nfl_map = stadiums.get("NFL", {})
    cfb_map = stadiums.get("NCAAF", {})

    with open("combined.json","r",encoding="utf-8") as f:
        payload = json.load(f)

    games = payload.get("data", [])
    weather_log = {"timestamp": datetime.now(timezone.utc).isoformat(), "data": []}

    for g in games:
        if not OW_KEY:
            break

        sport_key = g.get("sport_key","")
        home = g.get("home_team")
        commence = g.get("commence_time")
        if not home or not commence:
            continue

        # locate stadium record
        rec = None
        if "nfl" in sport_key:
            rec = nfl_map.get(home)
        elif "ncaaf" in sport_key:
            rec = cfb_map.get(home)

        if not rec or not rec.get("outdoor"):
            continue

        try:
            kickoff_dt = dateparser.isoparse(commence)
            kickoff_ts = int(kickoff_dt.timestamp())

            lat, lon = rec["lat"], rec["lon"]
            url = (
                f"https://api.openweathermap.org/data/3.0/onecall"
                f"?lat={lat}&lon={lon}&appid={OW_KEY}&units=imperial"
            )
            w = get_json(url)
            hourly = w.get("hourly", [])
            h = closest_hourly(hourly, kickoff_ts) or {}

            weather_obj = {
                "stadium_team": home,
                "lat": lat,
                "lon": lon,
                "kickoff": commence,
                "temp_f": h.get("temp"),
                "wind_mph": (h.get("wind_speed") or None),
                "humidity": h.get("humidity"),
                "precip_prob": h.get("pop"),
                "conditions": (h.get("weather") or [{}])[0].get("description"),
            }

            g["weather"] = weather_obj
            weather_log["data"].append(weather_obj)

        except Exception as e:
            print(f"⚠️ weather failed for {g.get('matchup')}: {e}")

    with open(WEATHER_OUT,"w",encoding="utf-8") as f:
        json.dump(weather_log, f, indent=2)

    payload["data"] = games
    with open("combined.json","w",encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"[✅] Weather updated for {len(weather_log['data'])} outdoor games.")

if __name__ == "__main__":
    main()
