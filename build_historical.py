#!/usr/bin/env python3
"""
build_historical.py

Builds a simple historical summary from combined.json:
- per-team average points for/against
- simple point differential

This is intentionally conservative scaffolding:
- It only uses games in combined.json that have a past date
  AND some notion of final scores if present.
- If no finished games are found, it still writes a valid
  historical.json with empty structures.

Output: historical.json
"""

import json
import os
from datetime import datetime, timezone

INPUT = "combined.json"
OUTPUT = "historical.json"

def safe_float(x, default=None):
    try:
        return float(x)
    except Exception:
        return default

def safe_int(x, default=None):
    try:
        return int(x)
    except Exception:
        return default

def parse_date(dt_str):
    if not dt_str:
        return None
    try:
        # Accept ISO-ish strings
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None

def main():
    if not os.path.exists(INPUT):
        print(f"❌ {INPUT} not found.")
        return

    with open(INPUT, "r") as f:
        root = json.load(f)

    games = root.get("data") or root.get("games") or root.get("combined") or []
    now_utc = datetime.now(timezone.utc)

    teams = {}  # key: team name, value: aggregates

    finished_games = 0

    for g in games:
        # Use UTC if available, else local
        dt = parse_date(g.get("date_utc") or g.get("date_local"))
        if not dt or dt >= now_utc:
            # Skip future games
            continue

        # We need some scores; allow several common shapes
        home_score = None
        away_score = None

        # 1) explicit score fields
        home_score = safe_int(g.get("home_score"))
        away_score = safe_int(g.get("away_score"))

        # 2) nested score objects
        if home_score is None and isinstance(g.get("home_team"), dict):
            home_score = safe_int(g["home_team"].get("score"))
        if away_score is None and isinstance(g.get("away_team"), dict):
            away_score = safe_int(g["away_team"].get("score"))

        # 3) generic scores dict
        if home_score is None and isinstance(g.get("scores"), dict):
            s = g["scores"]
            home_score = safe_int(s.get("home"))
            away_score = safe_int(s.get("away"))

        if home_score is None or away_score is None:
            # No final score, treat as unfinished
            continue

        finished_games += 1

        home_name = (g.get("home_team") or {}).get("name") or g.get("home") or "HOME"
        away_name = (g.get("away_team") or {}).get("name") or g.get("away") or "AWAY"

        for name, pts_for, pts_against in [
            (home_name, home_score, away_score),
            (away_name, away_score, home_score),
        ]:
            rec = teams.setdefault(
                name,
                {
                    "team": name,
                    "games": 0,
                    "points_for": 0.0,
                    "points_against": 0.0,
                },
            )
            rec["games"] += 1
            rec["points_for"] += pts_for
            rec["points_against"] += pts_against

    # Aggregate
    teams_out = {}
    for name, rec in teams.items():
        gcount = max(rec["games"], 1)
        pf = rec["points_for"] / gcount
        pa = rec["points_against"] / gcount
        diff = pf - pa
        teams_out[name] = {
            "team": name,
            "games": rec["games"],
            "avg_points_for": round(pf, 2),
            "avg_points_against": round(pa, 2),
            "avg_point_diff": round(diff, 2),
        }

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": INPUT,
        "games_used": finished_games,
        "teams": teams_out,
    }

    with open(OUTPUT, "w") as f:
        json.dump(out, f, indent=2)

    print(
        f"✅ Wrote {OUTPUT} (teams={len(teams_out)}, historical_games={finished_games})"
    )

if __name__ == "__main__":
    main()
