#!/usr/bin/env python3
"""
fetch_weather.py
Fetches weather.gov forecast data for each game's venue coords.
Writes: weather_raw.json
"""

import json
import requests
import time

# ------------------------------------------------------------
# Load combined.json and extract venue coordinates
# ------------------------------------------------------------
def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def get_weather(lat, lon):
    """
    Calls NWS "points" and "forecast" API.
    Returns dict or {"error": "..."}
    """

    try:
        # Step 1: Find grid endpoint
        p_url = f"https://api.weather.gov/points/{lat},{lon}"
        headers = {"User-Agent": "fbf-data (contact@forgedbyfreedom.com)"}

        p = requests.get(p_url, timeout=10, headers=headers).json()
        grid = p.get("properties", {})
        fc_url = grid.get("forecast")

        if not fc_url:
            return {"error": "no_forecast_url"}

        # Step 2: Get forecast data
        f = requests.get(fc_url, timeout=10, headers=headers).json()
        periods = f.get("properties", {}).get("periods", [])
        if not periods:
            return {"error": "no_periods"}

        # Use the FIRST period (next upcoming)
        p0 = periods[0]

        out = {
            "temperatureF": p0.get("temperature"),
            "windSpeedMph": None,
            "rainChancePct": p0.get("probabilityOfPrecipitation", {}).get("value"),
            "indoor": False,
        }

        # Parse wind speed "12 mph", "5 to 10 mph"
        wind_raw = p0.get("windSpeed", "")
        if isinstance(wind_raw, str) and wind_raw:
            try:
                num = wind_raw.split(" ")[0]
                out["windSpeedMph"] = float(num)
            except:
                out["windSpeedMph"] = None

        return out

    except Exception as e:
        return {"error": str(e)}


def main():
    games = load_json("combined.json", {})

    # combined.json format:
    # { "timestamp": "...", "count": N, "data": [...] }
    if isinstance(games, dict) and "data" in games:
        games = games["data"]

    weather_out = {}

    for g in games:
        gid = g.get("id") or g.get("game_id")
        venue = g.get("venue") or {}

        lat = venue.get("latitude")
        lon = venue.get("longitude")

        if not gid:
            continue

        if lat is None or lon is None:
            weather_out[gid] = {"error": "no_coords"}
            continue

        w = get_weather(lat, lon)
        weather_out[gid] = w

        time.sleep(0.3)  # polite rate limiting

    save_json("weather_raw.json", weather_out)
    print("FETCH WEATHER FILE UPDATED SUCCESSFULLY")


if __name__ == "__main__":
    main()
