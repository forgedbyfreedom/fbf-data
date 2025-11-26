#!/usr/bin/env python3
"""
weather_risk1.py
Convert weather_raw.json → weather_risk1.json using simple risk scoring.
"""

import json
import datetime
from pathlib import Path

RAW = Path("weather_raw.json")
OUT = Path("weather_risk1.json")


def load(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return None


def classify(entry):
    """Return a simple weather risk score."""
    if entry.get("error") == "no_weather_needed":
        return {"risk": None, "desc": "Indoor or no weather impact"}

    temp = entry.get("temperatureF")
    wind = entry.get("windSpeedMph")
    forecast = entry.get("shortForecast") or ""

    # Normalize wind if API returns "12 mph"
    if isinstance(wind, str) and wind.endswith("mph"):
        try:
            wind = int(wind.replace("mph", "").strip())
        except:
            wind = None

    risk = 0
    notes = []

    # TEMP
    if temp is not None:
        if temp <= 25:
            risk += 3; notes.append("Very cold")
        elif temp <= 40:
            risk += 2; notes.append("Cold")

    # WIND
    if wind is not None:
        if wind >= 25:
            risk += 3; notes.append("High wind")
        elif wind >= 15:
            risk += 1; notes.append("Windy")

    # PRECIP
    f = forecast.lower()
    if "snow" in f:
        risk += 3; notes.append("Snow")
    elif "rain" in f:
        risk += 2; notes.append("Rain")
    elif "showers" in f:
        risk += 1; notes.append("Showers")

    return {
        "risk": risk if risk > 0 else None,
        "desc": ", ".join(notes) if notes else "No significant impact"
    }


def main():
    raw = load(RAW)
    if not raw or "data" not in raw:
        print("❌ weather_raw.json missing or invalid")
        return

    out = {}
    for entry in raw["data"]:
        key = entry.get("key")
        if not key:
            continue

        out[key] = classify(entry)

    payload = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "data": out
    }

    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"✅ weather_risk1.json written ({len(out)} entries)")


if __name__ == "__main__":
    main()
