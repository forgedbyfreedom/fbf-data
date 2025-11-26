#!/usr/bin/env python3
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
    """Simple rules for risk scoring."""
    if not entry:
        return {"risk": 0, "note": "no weather data"}

    if entry.get("error"):
        return {"risk": 0, "note": entry["error"]}

    temp = entry.get("temperatureF")
    wind_raw = entry.get("windSpeedMph")

    try:
        wind = int(wind_raw.split()[0]) if isinstance(wind_raw, str) else wind_raw
    except:
        wind = None

    risk = 0
    notes = []

    if temp is not None:
        if temp <= 20: 
            risk += 2
            notes.append("very cold")
        elif temp <= 32:
            risk += 1
            notes.append("cold")

    if wind is not None:
        if wind >= 25:
            risk += 2
            notes.append("high wind")
        elif wind >= 15:
            risk += 1
            notes.append("windy")

    return {
        "risk": risk,
        "note": ", ".join(notes) if notes else "normal"
    }

def main():
    raw = load(RAW)
    if not raw or "data" not in raw:
        print("❌ weather_raw.json missing or invalid")
        return

    output = {}
    for entry in raw["data"]:
        key = entry.get("key")
        if key is None:
            continue
        output[str(key)] = classify(entry)

    with open(OUT, "w") as f:
        json.dump({
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "data": output
        }, f, indent=2)

    print(f"✅ Built weather_risk1.json with {len(output)} entries")

if __name__ == "__main__":
    main()
