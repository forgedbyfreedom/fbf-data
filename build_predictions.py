#!/usr/bin/env python3
"""
build_predictions.py

Generates predictions.json using the combined.json feed.
This version is SAFE with our new ESPN structure (team dicts).

We currently use a simple heuristic model:
- if favorite exists: predict favorite wins
- else: 50/50
- confidence based on spread magnitude
"""

import json
import os
from datetime import datetime

COMBINED_FILE = "combined.json"
OUTPUT_FILE = "predictions.json"


def normalize_team(team):
    """Extract team name safely whether dict or string."""
    if isinstance(team, str):
        return team

    if isinstance(team, dict):
        return (
            team.get("displayName")
            or team.get("shortDisplayName")
            or team.get("name")
            or team.get("nickname")
            or team.get("abbreviation")
            or ""
        )
    return ""


def load_combined():
    if not os.path.exists(COMBINED_FILE):
        print("⚠ combined.json missing.")
        return None

    try:
        return json.load(open(COMBINED_FILE, "r"))
    except Exception as e:
        print(f"⚠ Error loading combined.json: {e}")
        return None


def heuristic_predict(game):
    """
    Simple prediction:
    - If favorite_team exists → pick favorite
    - Confidence = min(max(abs(spread) * 10, 55), 95)
    """

    fav_team = normalize_team(game.get("fav_team"))
    dog_team = normalize_team(game.get("dog_team"))
    spread = game.get("fav_spread")

    # No odds? 50/50
    if not fav_team or spread is None:
        return {
            "predicted_winner": normalize_team(game.get("home_team")),
            "predicted_loser": normalize_team(game.get("away_team")),
            "confidence": 50.0
        }

    # Confidence scales with spread:
    # 2.5 → ~75%
    # 6.5 → ~90%
    conf = min(max(abs(spread) * 10 + 55, 55), 95)

    return {
        "predicted_winner": fav_team,
        "predicted_loser": dog_team,
        "confidence": round(conf, 1)
    }


def main():
    combined = load_combined()
    if not combined or "data" not in combined:
        print("⚠ No combined.json data.")
        json.dump({"timestamp": datetime.utcnow().isoformat(), "predictions": []},
                  open(OUTPUT_FILE, "w"), indent=2)
        return

    games = combined["data"]
    predictions = []

    for g in games:
        pred = heuristic_predict(g)

        predictions.append({
            "event_id": g.get("event_id"),
            "sport": g.get("sport_key"),
            "matchup": g.get("matchup"),
            "home_team": normalize_team(g.get("home_team")),
            "away_team": normalize_team(g.get("away_team")),
            "favorite": g.get("favorite"),
            "spread": g.get("spread"),
            "total": g.get("total"),
            "prediction": pred
        })

    out = {
        "timestamp": datetime.utcnow().isoformat(),
        "count": len(predictions),
        "predictions": predictions
    }

    json.dump(out, open(OUTPUT_FILE, "w"), indent=2)
    print(f"✅ Wrote {OUTPUT_FILE} ({len(predictions)} predictions)")


if __name__ == "__main__":
    main()
