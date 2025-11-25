#!/usr/bin/env python3
"""
merge_weather.py
--------------------------------
Correct merge step:
- Match weather + risk using game_id (NOT lat/lon).
- If a game has no weather entry, insert defaults.
"""

import json
import os

COMBINED_FILE = "combined.json"
WEATHER_FILE = "weather_raw.json"
RISK_FILE = "weather_risk1.json"


def load(path):
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def merge_weather(game, weather_map, risk_map):
    gid = str(game.get("id"))

    w = weather_map.get(gid)
    r = risk_map.get(gid)

    # Always attach something so front-end doesn't break
    game["weather"] = w or {
        "lat": None,
        "lon": None,
        "temperatureF": None,
        "windSpeedMph": None,
        "rainChancePct": None,
        "shortForecast": None,
    }

    game["weatherRisk"] = r or {
        "risk": None
    }


def main():
    combined = load(COMBINED_FILE)
    weather_raw = load(WEATHER_FILE)
    risk_raw = load(RISK_FILE)

    if not combined or "data" not in combined:
        print("❌ combined.json missing or invalid")
        return

    if not weather_raw:
        print("⚠️ weather_raw.json missing")
        weather_raw = {}

    if not risk_raw:
        print("⚠️ weather_risk1.json missing")
        risk_raw = {}

    # These files are already dicts keyed by gameId
    weather_map = {str(k): v for k, v in weather_raw.items()}
    risk_map = {str(k): v for k, v in risk_raw.items()}

    total = len(combined["data"])
    merged = 0

    for game in combined["data"]:
        gid = str(game.get("id"))
        if gid in weather_map:
            merged += 1
        merge_weather(game, weather_map, risk_map)

    # Write updated combined.json
    with open(COMBINED_FILE, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"[✅] Weather merged for {merged}/{total} games.")


if __name__ == "__main__":
    main()
