#!/usr/bin/env python3
"""
tag_favorites.py
Reads combined.json and adds:
- fav_team, dog_team        (full team names)
- fav_abbr, dog_abbr        (abbreviations)
- fav_spread, dog_spread     (signed floats)
- spread                     (fav spread, always <= 0)
- favorite, underdog         (display strings like "DET -6.5")
Writes combined.json back in-place.

ESPN convention:
- odds.spread = home team's spread (negative = home favored, positive = away favored)
- odds.details = "<FAV_ABBR> -<pts>" or "<FAV_ABBR> -<moneyline>" for NHL/MLB
"""

import json, os, re
from datetime import datetime, timezone


def parse_details_abbr(details):
    """Extract the favorite abbreviation from details string like 'DET -6.5' or 'FLA -120'."""
    if not details or not isinstance(details, str):
        return None
    parts = details.strip().split()
    if len(parts) >= 2:
        return parts[0].strip()
    return None


def main():
    if not os.path.exists("combined.json"):
        print("combined.json missing")
        return

    with open("combined.json", "r", encoding="utf-8") as f:
        payload = json.load(f)

    games = payload.get("data", [])
    tagged = 0

    for g in games:
        odds = g.get("odds")
        if not odds or not isinstance(odds, dict):
            continue

        spread = odds.get("spread")
        total = odds.get("total")
        details = odds.get("details")

        home_team = g.get("home_team") or {}
        away_team = g.get("away_team") or {}
        home_name = home_team.get("name", "")
        away_name = away_team.get("name", "")
        home_abbr = home_team.get("abbr", "")
        away_abbr = away_team.get("abbr", "")

        # Determine favorite from spread sign
        # ESPN: negative spread = home favored, positive = away favored
        if spread is not None and isinstance(spread, (int, float)) and spread != 0:
            if spread < 0:
                # Home is favorite
                fav_name, dog_name = home_name, away_name
                fav_abbr, dog_abbr_val = home_abbr, away_abbr
                fav_spread = spread          # negative (giving points)
                dog_spread = abs(spread)     # positive (getting points)
            else:
                # Away is favorite
                fav_name, dog_name = away_name, home_name
                fav_abbr, dog_abbr_val = away_abbr, home_abbr
                fav_spread = -abs(spread)    # always store fav spread as negative
                dog_spread = abs(spread)

            g["fav_team"] = fav_name
            g["dog_team"] = dog_name
            g["fav_abbr"] = fav_abbr
            g["dog_abbr"] = dog_abbr_val
            g["fav_spread"] = float(fav_spread)
            g["dog_spread"] = float(dog_spread)
            g["spread"] = float(fav_spread)
            g["favorite"] = f"{fav_abbr} {fav_spread:+.1f}"
            g["underdog"] = f"{dog_abbr_val} +{dog_spread:.1f}"
            g["tagged_at"] = datetime.now(timezone.utc).isoformat()
            tagged += 1

        elif spread == 0:
            # Pick'em
            g["fav_team"] = home_name
            g["dog_team"] = away_name
            g["fav_abbr"] = home_abbr
            g["dog_abbr"] = away_abbr
            g["fav_spread"] = 0.0
            g["dog_spread"] = 0.0
            g["spread"] = 0.0
            g["favorite"] = f"{home_abbr} PK"
            g["underdog"] = f"{away_abbr} PK"
            g["tagged_at"] = datetime.now(timezone.utc).isoformat()
            tagged += 1

        elif details and isinstance(details, str):
            # Moneyline-only games (common in NHL/MLB)
            # details like "FLA -120" — determine favorite from moneyline
            fav_abbr_parsed = parse_details_abbr(details)
            if fav_abbr_parsed:
                if fav_abbr_parsed == home_abbr:
                    fav_name, dog_name = home_name, away_name
                    fav_abbr, dog_abbr_val = home_abbr, away_abbr
                elif fav_abbr_parsed == away_abbr:
                    fav_name, dog_name = away_name, home_name
                    fav_abbr, dog_abbr_val = away_abbr, home_abbr
                else:
                    continue

                g["fav_team"] = fav_name
                g["dog_team"] = dog_name
                g["fav_abbr"] = fav_abbr
                g["dog_abbr"] = dog_abbr_val
                g["fav_spread"] = None  # no point spread for ML-only
                g["dog_spread"] = None
                g["spread"] = None
                g["favorite"] = details.strip()
                g["underdog"] = dog_abbr_val
                g["tagged_at"] = datetime.now(timezone.utc).isoformat()
                tagged += 1

    payload["data"] = games
    with open("combined.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"[tag_favorites] Tagged {tagged}/{len(games)} games.")


if __name__ == "__main__":
    main()
