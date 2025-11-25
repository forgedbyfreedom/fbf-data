#!/usr/bin/env python3
"""
merge_weather.py
--------------------------------
Merges weather.json + weather_risk1.json into combined.json
using coordinate-based keys ONLY.

Both weather.json and weather_risk1.json use:
    key = "lat,lon" (rounded to 4 decimals)
"""

import json
import os

COMBINED = "combined.json"
WEATHER = "weather.json"
RISK = "weather_risk1.json"


def load(path):
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def format_key(lat, lon):
    try:
        return f"{float(lat):.4f},{float(lon):.4f}"
    except:
        return None


def merge():
    combined = load(COMBINED)
    weather = load(WEATHER)
    risk = load(RISK)

    if not combined or "data" not in combined:
        print("❌ combined.json missing or invalid")
        return

    weather_map = {d["key"]: d for d in weather.get("data", [])} if weather else {}
    risk_map = {d["key"]: d for d in risk.get("data", [])} if risk else {}

    merged = 0

    for g in combined["data"]:
        venue = g.get("venue", {})
        lat = venue.get("lat")
        lon = venue.get("lon")

        key = format_key(lat, lon)
        if not key:
            g["weather"] = {"error": "no_coords"}
            g["weatherRisk"] = {"risk": None}
            continue

        g["weather"] = weather_map.get(key, {"error": "no_weather"})
        g["weatherRisk"] = risk_map.get(key, {"risk": None})

        if key in weather_map:
            merged += 1

    with open(COMBINED, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"[✅] Weather merged for {merged}/{len(combined['data'])} games.")


if __name__ == "__main__":
    merge()
