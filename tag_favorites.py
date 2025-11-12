#!/usr/bin/env python3
"""
tag_favorites.py
Cleans and finalizes favorite/dog/spread info for ESPN data.
"""

import json, os, re
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEAGUES = ["nfl", "ncaaf", "ncaab", "ncaaw", "mlb", "nhl"]

def extract_spread_from_details(details: str):
    """
    Parse ESPN 'details' strings like 'NE -3.5' or 'BUF +7' and return team and spread.
    """
    if not details:
        return None, None
    parts = details.split()
    for i, p in enumerate(parts):
        if p.startswith("-") or p.startswith("+"):
            try:
                spread = float(p)
                team = parts[i - 1] if i > 0 else None
                return team, spread
            except:
                continue
    return None, None


def process_league(file_path):
    if not os.path.exists(file_path):
        return []

    with open(file_path, "r") as f:
        try:
            raw = json.load(f)
        except:
            return []

    data = raw.get("data", [])
    for g in data:
        details = g.get("details") or ""
        team, spread = extract_spread_from_details(details)

        # Set favorite and dog teams based on the sign of the spread
        if team:
            g["favorite_team"] = team
            g["fav_spread"] = spread
            # Determine dog
            if g.get("home_team") == team:
                g["dog_team"] = g.get("away_team")
            else:
                g["dog_team"] = g.get("home_team")
        else:
            # Default fallback — keep home/away structure
            g["favorite_team"] = g.get("home_team")
            g["dog_team"] = g.get("away_team")
            g["fav_spread"] = None

    # Save back
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    out = {"timestamp": timestamp, "data": data}
    with open(file_path, "w") as f:
        json.dump(out, f, indent=2)

    print(f"[💾] Saved → {os.path.basename(file_path)} ({len(data)} games)")
    return data


def main():
    print(f"[🏈] Tagging favorites and underdogs at {datetime.now(timezone.utc).isoformat()}Z...")
    combined = []

    for league in LEAGUES:
        path = os.path.join(BASE_DIR, f"{league}.json")
        combined.extend(process_league(path))

    combined_out = os.path.join(BASE_DIR, "combined.json")
    with open(combined_out, "w") as f:
        json.dump({"timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"), "data": combined}, f, indent=2)

    print(f"[💾] Saved → combined.json ({len(combined)} games)")
    print("[✅] Tagging complete.")


if __name__ == "__main__":
    main()

