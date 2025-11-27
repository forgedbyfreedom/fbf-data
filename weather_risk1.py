#!/usr/bin/env python3
"""
weather_risk1.py

Takes per-game weather from weather_raw.json and computes a simple
risk score for football-style weather impact.

Input:  weather_raw.json
Output: weather.json
"""

import json
import os
from datetime import datetime, timezone

RAW_FILE = "weather_raw.json"
OUT_FILE = "weather.json"


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def classify_risk(temp_f, wind_mph, summary: str):
    """
    Return an integer risk level 0–3.
    0 = minimal
    1 = mild
    2 = moderate
    3 = high
    """
    risk = 0
    summary_l = (summary or "").lower()

    # Temperature extremes
    if temp_f is not None:
        if temp_f <= 25 or temp_f >= 90:
            risk += 1

    # Wind
    if wind_mph is not None:
        if wind_mph >= 15:
            risk += 1
        if wind_mph >= 25:
            risk += 1

    # Precipitation / storms
    bad_words = [
        "rain", "showers", "storm", "thunder", "snow",
        "sleet", "freezing", "hail"
    ]
    if any(w in summary_l for w in bad_words):
        risk += 1

    if risk > 3:
        risk = 3
    return risk


def main():
    raw = load_json(RAW_FILE)
    if not raw or "data" not in raw or not raw["data"]:
        print("❌ weather_raw.json missing or empty")
        return

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    out_data = {}

    for key, entry in raw["data"].items():
        temp = entry.get("temperatureF")
        wind = entry.get("windSpeedMph")
        summary = entry.get("shortForecast") or entry.get("summary")

        risk = classify_risk(temp, wind, summary)

        out_data[str(key)] = {
            "temperatureF": temp,
            "windSpeedMph": wind,
            "shortForecast": summary,
            "detailedForecast": entry.get("detailedForecast"),
            "risk": risk,
        }

    payload = {
        "timestamp": ts,
        "count": len(out_data),
        "data": out_data,
    }
    save_json(OUT_FILE, payload)
    print(f"✅ Weather risk written → {OUT_FILE}")


if __name__ == "__main__":
    main()
