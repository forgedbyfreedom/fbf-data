#!/usr/bin/env python3
import json
import os
from datetime import datetime

INJURY_FILE = "injuries.json"
COMBINED_FILE = "combined.json"
OUTPUT_FILE = "combined.json"  # injuries merged in-place

def normalize_team_name(team):
    """
    Safely convert team values to lowercase strings.
    Handles:
      - "Chicago Bears"
      - {"name": "Chicago Bears"}
      - None
    """
    if isinstance(team, str):
        return team.lower().strip()
    if isinstance(team, dict):
        name = team.get("name") or team.get("displayName") or ""
        return name.lower().strip()
    return ""

def load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return {}

def main():
    combined = load_json(COMBINED_FILE)
    injuries = load_json(INJURY_FILE)

    if "data" not in combined:
        print("❌ combined.json missing data[]")
        return

    all_games = combined["data"]

    # build lookup table for injuries
    injury_lookup = {}
    for team, info in injuries.items():
        injury_lookup[team.lower()] = info

    merged = []

    for g in all_games:
        home_key = normalize_team_name(g.get("home_team"))
        away_key = normalize_team_name(g.get("away_team"))

        g["home_injuries"] = injury_lookup.get(home_key, [])
        g["away_injuries"] = injury_lookup.get(away_key, [])

        merged.append(g)

    combined["data"] = merged
    combined["timestamp"] = datetime.utcnow().strftime("%Y%m%d_%H%M")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"✅ Injury merge complete — {len(merged)} games updated.")

if __name__ == "__main__":
    main()
