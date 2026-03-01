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
MAX_AGE_DAYS = 90  # prune scores older than 90 days


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


def main():
    combined = load_json(COMBINED, {})
    games = combined.get("data", [])

    # Load existing scores
    scores_data = load_json(SCORES_FILE, {"scores": {}})
    existing = scores_data.get("scores", {})
    initial_count = len(existing)

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

        # Only add if not already saved (don't overwrite)
        if gid not in existing:
            home_team = g.get("home_team") or {}
            away_team = g.get("away_team") or {}

            existing[gid] = {
                "home_score": home_score,
                "away_score": away_score,
                "sport": (g.get("sport") or "").upper(),
                "date_utc": g.get("date_utc"),
                "odds": g.get("odds") or {},
                "home_team": home_team if isinstance(home_team, dict) else {"name": str(home_team)},
                "away_team": away_team if isinstance(away_team, dict) else {"name": str(away_team)},
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            new_count += 1

    # Prune old scores (older than MAX_AGE_DAYS)
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    pruned = 0
    to_remove = []
    for gid, score in existing.items():
        date_str = score.get("date_utc")
        if date_str:
            try:
                game_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                if game_date < cutoff:
                    to_remove.append(gid)
                    pruned += 1
            except Exception:
                pass
    for gid in to_remove:
        del existing[gid]

    # Write back
    scores_data["scores"] = existing
    scores_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    scores_data["count"] = len(existing)

    with open(SCORES_FILE, "w") as f:
        json.dump(scores_data, f, indent=2)

    print(f"[save_scores] {new_count} new scores saved ({len(existing)} total, {pruned} pruned)")


if __name__ == "__main__":
    main()
