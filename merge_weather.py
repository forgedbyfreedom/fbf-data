#!/usr/bin/env python3
"""
merge_weather.py
--------------------------------
Merges weather.json + weather_risk1.json onto combined.json.

Safe for:
- missing venues
- missing coords
- games without lat/lon
- indoor games
- null venue objects

Output:
- combined.json (updated)
"""

import json, os

COMBINED_FILE = "combined.json"
WEATHER_FILE = "weather.json"
RISK_FILE = "weather_risk1.json"

def load(path):
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)

def safe_get_venue(g):
    """Always return a dict, even when venue is None."""
    v = g.get("venue")
    if isinstance(v, dict):
        return v
    return {}  # safe blank venue

def merge_weather_into_game(game, weather_map, risk_map):
    venue = safe_get_venue(game)

    # Try name first
    venue_name = venue.get("name", "")
    venue_name_key = venue_name.lower().strip() if venue_name else None

    # Try coords (best)
    lat = venue.get("lat")
    lon = venue.get("lon")

    weather_key = None

    # Priority: lat/lon → name → fallback
    if lat and lon:
        weather_key = f"{lat:.4f},{lon:.4f}"
    elif venue_name_key:
        weather_key = venue_name_key

    # Default None
    game_weather = None
    game_risk = None

    if weather_key and weather_key in weather_map:
        game_weather = weather_map[weather_key]

    if weather_key and weather_key in risk_map:
        game_risk = risk_map[weather_key]

    # Apply results
    game["weather"] = game_weather or {"error": "no_weather"}
    game["weatherRisk"] = game_risk or {"risk": None}

def main():
    combined = load(COMBINED_FILE)
    weather = load(WEATHER_FILE)
    risk = load(RISK_FILE)

    if not combined or "data" not in combined:
        print("❌ combined.json missing")
        return
    if not weather:
        print("⚠️ weather.json missing")
        weather = {}
    if not risk:
        print("⚠️ risk file missing")
        risk = {}

    # Convert weather list → dict
    weather_map = {}
    for w in weather.get("data", []):
        k = w.get("key")
        if k:
            weather_map[k] = w

    # Convert risk list → dict
    risk_map = {}
    for r in risk.get("data", []):
        k = r.get("key")
        if k:
            risk_map[k] = r

    total = len(combined["data"])
    merged = 0

    for game in combined["data"]:
        before = game.get("weather")
        merge_weather_into_game(game, weather_map, risk_map)
        after = game.get("weather")

        if after and after != {"error": "no_weather"}:
            merged += 1

    with open(COMBINED_FILE, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"[✅] Weather merged for {merged}/{total} games.")

if __name__ == "__main__":
    main()
