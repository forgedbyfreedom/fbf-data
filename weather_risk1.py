#!/usr/bin/env python3
"""
weather_risk1.py — compatible with list-based weather_raw.json
"""

import json
import datetime
from pathlib import Path

RAW = Path("weather_raw.json")
OUT = Path("weather_risk1.json")


def load_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def compute_risk(entry):
    """Return simple risk score based on wind/temp."""
    if not entry or "error" in entry:
        return {"risk": None, "reason": entry.get("error", "no_data")}

    temp = entry.get("temperatureF")
    wind = entry.get("windSpeedMph")

    # Try extracting mph from "12 mph" strings
    if isinstance(wind, str) and "mph" in wind:
        try:
            wind = float(wind.split(" ")[0])
        except:
            wind = None

    risk = 0
    reasons = []

    if wind and wind >= 15:
        risk += 1
        reasons.append("wind")

    if temp and temp <= 32:
        risk += 1
        reasons.append("cold")

    return {
        "risk": risk,
        "factors": reasons or None
    }


def main():
    raw = load_json(RAW)
    if not raw or "data" not in raw or not isinstance(raw["data"], list):
        print("❌ weather_raw.json missing or empty")
        return

    output = {}

    for item in raw["data"]:
        key = str(item.get("key"))
        if not key:
            continue
        output[key] = compute_risk(item)

    payload = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "count": len(output),
        "data": output
    }

    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"✅ weather_risk1.json written ({len(output)} entries)")


if __name__ == "__main__":
    main()
