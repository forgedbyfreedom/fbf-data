#!/usr/bin/env python3
"""
weather_risk1.py
------------------------------------
Consumes weather_raw.json (indexed by lat,lon keys)
and produces weather_risk1.json with risk scoring.

Risk factors included:
- wind speed
- temperature (cold & heat)
- rain chance
- snow chance (if included in forecast text)
- storm phrases
"""

import json
import os
import re

RAW_FILE = "weather_raw.json"
OUT_FILE = "weather_risk1.json"


def load(path):
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def detect_snow(text):
    if not text:
        return False
    t = text.lower()
    return any(kw in t for kw in ["snow", "flurries", "wintry", "blizzard"])


def detect_storm(text):
    if not text:
        return False
    t = text.lower()
    return any(kw in t for kw in ["storm", "thunder", "lightning", "severe"])


def compute_risk(entry):
    """
    entry = {
        "lat": float,
        "lon": float,
        "temperatureF": int,
        "windSpeedMph": float,
        "rainChancePct": int,
        "shortForecast": str,
        "detailedForecast": str
    }
    """
    if not entry:
        return {"risk": None}

    temp = entry.get("temperatureF")
    wind = entry.get("windSpeedMph") or 0
    rain = entry.get("rainChancePct") or 0

    short = entry.get("shortForecast", "") or ""
    detail = entry.get("detailedForecast", "") or ""
    text = f"{short} {detail}"

    score = 0
    factors = []

    # Wind
    if wind >= 25:
        score += 3
        factors.append("High wind")
    elif wind >= 15:
        score += 2
        factors.append("Windy")

    # Temperature cold
    if temp is not None and temp <= 25:
        score += 3
        factors.append("Extreme cold")
    elif temp is not None and temp <= 40:
        score += 2
        factors.append("Cold")

    # Heat
    if temp is not None and temp >= 95:
        score += 2
        factors.append("Extreme heat")

    # Rain
    if rain >= 70:
        score += 3
        factors.append("Heavy rain")
    elif rain >= 40:
        score += 2
        factors.append("Rain possible")

    # Snow
    if detect_snow(text):
        score += 3
        factors.append("Snow")

    # Storms
    if detect_storm(text):
        score += 4
        factors.append("Storm")

    return {
        "risk": score,
        "factors": factors,
        "temperatureF": temp,
        "windSpeedMph": wind,
        "rainChancePct": rain,
    }


def main():
    raw = load(RAW_FILE)
    if not raw or "data" not in raw:
        print("❌ weather_raw.json missing or empty")
        return

    out_list = []
    for key, entry in raw["data"].items():
        risk_info = compute_risk(entry)
        out_list.append({
            "key": key,
            "risk": risk_info["risk"],
            "factors": risk_info["factors"],
            "temperatureF": risk_info["temperatureF"],
            "windSpeedMph": risk_info["windSpeedMph"],
            "rainChancePct": risk_info["rainChancePct"],
        })

    with open(OUT_FILE, "w") as f:
        json.dump({"data": out_list}, f, indent=2)

    print(f"✅ Weather risk scores computed for {len(out_list)} locations.")


if __name__ == "__main__":
    main()
