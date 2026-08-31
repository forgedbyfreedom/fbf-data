#!/usr/bin/env python3
"""
save_completed_scores.py
Persists completed game scores before combined.json is refreshed.

Run BEFORE fetch_espn_all.py in the workflow to capture scores from games
that completed since the last run. Accumulates into completed_scores.json
so track_accuracy.py can always find final scores even after combined.json
is overwritten with the next day's upcoming games.
"""

import json, os
from datetime import datetime, timezone, timedelta

COMBINED = "combined.json"
SCORES_FILE = "completed_scores.json"
# (scores are kept indefinitely; see the note in main())

# Minimum realistic final-game totals per sport (used to reject partial scores)
MIN_TOTAL = {
    "NBA": 160,    # lowest modern NBA game ~150; typical ~210-230
    "NCAAB": 100,  # lowest realistic finals ~100-110; halftimes can be 60-70
    "NCAAW": 90,   # lowest realistic finals ~90-100
    "NFL": 6,      # 3-0 games happen but are rare
    "NCAAF": 10,
    "NHL": 1,      # 1-0 games happen
    "MLB": 1,      # 1-0 games happen
    "UFC": 0,      # N/A
}


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def safe_float(x, default=None):
    try:
        if x is None:
            return default
        return float(x)
    except (ValueError, TypeError):
        return default


def score_looks_final(sport, home_score, away_score, odds=None):
    """Check if scores look like a real final score (not partial/quarter)."""
    total = home_score + away_score
    min_total = MIN_TOTAL.get(sport.upper(), 0)
    if total < min_total:
        return False

    # Extra check: if score is less than 50% of the total line, it's likely partial
    if odds:
        total_line = safe_float(odds.get("total"))
        if total_line and total_line > 0 and total < total_line * 0.5:
            return False

    return True


def main():
    combined = load_json(COMBINED, {})
    games = combined.get("data", [])

    # Load existing scores
    scores_data = load_json(SCORES_FILE, {"scores": {}})
    existing = scores_data.get("scores", {})
    initial_count = len(existing)

    # First pass: fix bad existing scores (overwrite partial/bogus scores)
    fixed = 0
    for gid, score in list(existing.items()):
        sport = (score.get("sport") or "").upper()
        if not score_looks_final(sport, score["home_score"], score["away_score"], score.get("odds")):
            # Mark as bad so it can be overwritten
            existing[gid]["_suspect"] = True
            fixed += 1
    if fixed:
        print(f"[save_scores] Found {fixed} suspect scores (partial/in-progress) to re-check")

    # Extract completed games with scores
    new_count = 0
    for g in games:
        gid = str(g.get("id") or g.get("event_id") or "")
        if not gid:
            continue

        home_score = safe_float(g.get("home_score"))
        away_score = safe_float(g.get("away_score"))
        if home_score is None or away_score is None:
            continue

        sport = (g.get("sport") or "").upper()

        # Skip scores that look like partial/in-progress
        game_odds = g.get("odds") or {}
        if not score_looks_final(sport, home_score, away_score, game_odds):
            continue

        # Add if new OR if existing score was suspect (partial)
        if gid not in existing or existing.get(gid, {}).get("_suspect"):
            home_team = g.get("home_team") or {}
            away_team = g.get("away_team") or {}

            existing[gid] = {
                "home_score": home_score,
                "away_score": away_score,
                "sport": sport,
                "date_utc": g.get("date_utc"),
                "odds": g.get("odds") or {},
                "home_team": home_team if isinstance(home_team, dict) else {"name": str(home_team)},
                "away_team": away_team if isinstance(away_team, dict) else {"name": str(away_team)},
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            new_count += 1

    # Completed scores are never pruned. They are the only record of what
    # actually happened, and track_accuracy.py can only grade a pick while
    # its game's score is still here - pruning silently shrank the graded
    # history instead of growing it.
    # Write back
    scores_data["scores"] = existing
    scores_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    scores_data["count"] = len(existing)

    with open(SCORES_FILE, "w") as f:
        json.dump(scores_data, f, indent=2)

    print(f"[save_scores] {new_count} new scores saved ({len(existing)} total, kept indefinitely)")


if __name__ == "__main__":
    main()
