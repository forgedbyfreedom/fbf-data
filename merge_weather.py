#!/usr/bin/env python3
"""
Merge weather_risk1.json into combined.json.
"""

import json, datetime
from pathlib import Path

COMBINED = Path("combined.json")
WEATHER = Path("weather_risk1.json")

def load(path):
    if not path.exists():
        return None
    with open(path, "r") as f:
        return json.load(f)

def normalize(name):
    return name.lower().strip() if name else ""

def main():
    combined = load(COMBINED)
    weather = load(WEATHER)

    if not combined or "data" not in combined:
        print("❌ combined.json invalid")
        return

    wx_map = {}
    for w in weather.get("data", []):
        key = normalize(w["key"])
        wx_map[key] = w

    for g in combined["data"]:
        venue_name = normalize(g.get("venue", {}).get("name"))
        wx = wx_map.get(venue_name)
        if wx:
            g["weather"] = {
                "temperatureF": wx.get("temperatureF"),
                "windSpeedMph": wx.get("windSpeedMph"),
                "shortForecast": wx.get("shortForecast"),
            }
            g["weatherRisk"] = {"risk": wx.get("risk")}

    combined["timestamp"] = datetime.datetime.utcnow().isoformat()

    with open(COMBINED, "w") as f:
        json.dump(combined, f, indent=2)

    print("✅ Weather merged into combined.json")

if __name__ == "__main__":
    main()
