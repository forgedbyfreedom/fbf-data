#!/usr/bin/env python3
"""
Convert weather_raw.json into weather_risk1.json with proper risk scoring.
"""

import json
from pathlib import Path

RAW = Path("weather_raw.json")
OUT = Path("weather_risk1.json")

def load_raw():
    if not RAW.exists():
        print("❌ weather_raw.json missing")
        return []
    with open(RAW, "r") as f:
        js = json.load(f)
        return js.get("data", [])

def weather_risk(entry):
    """Simple scoring."""
    if "error" in entry:
        return None

    temp = entry.get("temperatureF")
    wind = entry.get("windSpeedMph")

    if temp is None or wind is None:
        return None

    risk = 0
    if temp < 35: risk += 1
    if temp < 25: risk += 1
    if wind > 15: risk += 1
    if wind > 25: risk += 1

    return risk

def main():
    raw = load_raw()
    out = []

    for e in raw:
        r = weather_risk(e)
        out.append({
            "key": e.get("key"),
            "team_id": e.get("team_id"),
            "risk": r,
            "temperatureF": e.get("temperatureF"),
            "windSpeedMph": e.get("windSpeedMph"),
            "shortForecast": e.get("shortForecast"),
        })

    with open(OUT, "w") as f:
        json.dump({"data": out}, f, indent=2)

    print(f"✅ Weather risk written → {OUT}")

if __name__ == "__main__":
    main()
