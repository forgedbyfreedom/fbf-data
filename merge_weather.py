#!/usr/bin/env python3
import json
import os
from pathlib import Path
import datetime

COMBINED_FILE = Path("combined.json")
WEATHER_FILE = Path("weather.json")
OUT_FILE = Path("weather_merged.json")


def load_json(path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def main():
    combined = load_json(COMBINED_FILE)
    weather = load_json(WEATHER_FILE)

    if not combined or "data" not in combined:
        print("❌ combined.json missing or invalid")
        return
    if not weather or "data" not in weather:
        print("❌ weather.json missing or invalid")
        return

    wmap = weather["data"]  # { gameId: { ... } }

    games = combined["data"]
    attached = 0

    for g in games:
        if not isinstance(g, dict):
            continue
        gid = g.get("id")
        if gid is None:
            continue
        wk = wmap.get(str(gid))
        if not wk:
            continue

        # Build normalized weather object for frontend
        temp = wk.get("temperatureF")
        wind = wk.get("windSpeedMph")
        summary = wk.get("shortForecast") or wk.get("summary")
        risk_val = wk.get("risk")

        g["weather"] = {
            "summary": summary,
            "description": wk.get("detailedForecast"),
            "temperatureF": temp,
            "temp": temp,
            "windSpeedMph": wind,
            "wind": wind,
        }
        g["weatherRisk"] = {"risk": risk_val}
        attached += 1

    combined["weather_merged_at"] = datetime.datetime.utcnow().isoformat()

    # Write merged snapshot AND overwrite combined.json so frontend sees it
    save_json(OUT_FILE, combined)
    save_json(COMBINED_FILE, combined)
    print(f"✅ Weather merged onto {attached} games → {OUT_FILE} & {COMBINED_FILE}")


if __name__ == "__main__":
    main()
