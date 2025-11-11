#!/usr/bin/env python3
"""
tag_favorites.py
--------------------------------------
Determines favorite and underdog teams from line data
and tags them explicitly in combined.json and league files.

- The favorite ALWAYS carries the NEGATIVE spread.
- Uses Moneyline odds when spreads are ambiguous.
- Works across NFL, NCAAF, NCAAB, NCAAW, MLB, NHL, UFC, etc.
"""

import json, os, math
from datetime import datetime

def load_json(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            elif isinstance(data, list):
                return data
            else:
                return []
    except Exception as e:
        print(f"⚠️  Error loading {path}: {e}")
        return []

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"timestamp": datetime.utcnow().strftime("%Y%m%d_%H%M"), "data": data}, f, indent=2)
        print(f"[💾] Saved → {path} ({len(data)} games)")
    except Exception as e:
        print(f"❌ Error saving {path}: {e}")

def determine_favorite(row):
    """
    Determines favorite and underdog based on spread and ML.
    The negative spread team is always the favorite.
    """
    matchup = row.get("matchup", "")
    if "@" not in matchup:
        return row

    away, home = [t.strip() for t in matchup.split("@", 1)]

    spread = row.get("spread", None)
    ml_fav = row.get("ml_fav", None)
    ml_dog = row.get("ml_dog", None)

    # Default to home as favorite if unknown
    favorite_team = home
    dog_team = away
    fav_spread = None

    # Logic: negative spread = favorite
    if isinstance(spread, (int, float)):
        if spread < 0:
            favorite_team, dog_team = away, home
            fav_spread = spread
        elif spread > 0:
            favorite_team, dog_team = home, away
            fav_spread = -abs(spread)

    # Fallback: moneyline odds
    elif ml_fav and ml_dog:
        try:
            if ml_fav < ml_dog:
                favorite_team, dog_team = away, home
                fav_spread = row.get("spread", -1.5)
            else:
                favorite_team, dog_team = home, away
                fav_spread = row.get("spread", -1.5)
        except Exception:
            pass

    row.update({
        "away_team": away,
        "home_team": home,
        "favorite_team": favorite_team,
        "dog_team": dog_team,
        "fav_spread": fav_spread
    })
    return row

def tag_all_files():
    files = [f for f in os.listdir(".") if f.endswith(".json") and not f.startswith("combined_backup")]
    all_rows = []

    for file in files:
        data = load_json(file)
        if not data:
            continue

        fixed = [determine_favorite(row) for row in data]
        save_json(file, fixed)

        if "combined" not in file:
            all_rows.extend(fixed)

    # Update combined.json
    if all_rows:
        save_json("combined.json", all_rows)
    else:
        print("⚠️  No data found to tag.")

if __name__ == "__main__":
    print(f"[🏈] Tagging favorites and underdogs at {datetime.utcnow().isoformat()}Z...")
    tag_all_files()
    print("[✅] Tagging complete.")

