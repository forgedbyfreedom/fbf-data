#!/usr/bin/env python3
"""
build_historical.py
Downloads full ESPN historical game data (scores, officials, injuries)
Stores into /history/<sport>.json
"""

import requests, json, os, time
from datetime import datetime

SPORTS = {
    "nfl":   "football/leagues/nfl",
    "ncaaf": "football/leagues/college-football",
    "nba":   "basketball/leagues/nba",
    "ncaab": "basketball/leagues/mens-college-basketball",
    "nhl":   "hockey/leagues/nhl",
    "mlb":   "baseball/leagues/mlb",
}

def fetch_json(url):
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except:
        return None

def build_history():
    os.makedirs("history", exist_ok=True)
    out = {}

    for key, path in SPORTS.items():
        print(f"\n🔎 Fetching historical for: {key}")

        url = f"https://sports.core.api.espn.com/v2/sports/{path}/events"
        data = fetch_json(url)
        if not data or "items" not in data:
            print(f"⚠️  No events for {key}")
            continue

        events = []
        for e in data["items"]:
            if "$ref" not in e:
                continue
            ev = fetch_json(e["$ref"])
            if not ev:
                continue

            events.append({
                "id": ev.get("id"),
                "name": ev.get("name"),
                "date": ev.get("date"),
                "shortName": ev.get("shortName"),
                "competitions": ev.get("competitions"),
            })
            time.sleep(0.1)

        out[key] = events
        with open(f"history/{key}.json", "w") as f:
            json.dump(events, f, indent=2)

        print(f"✅ Saved history/{key}.json ({len(events)} games)")

    out["timestamp"] = datetime.utcnow().isoformat()

    with open("history/history_index.json", "w") as f:
        json.dump(out, f, indent=2)

    print("\n🎉 Historical database built successfully!\n")

if __name__ == "__main__":
    build_history()
