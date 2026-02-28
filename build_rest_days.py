#!/usr/bin/env python3
"""
build_rest_days.py
Calculates days since each team's last completed game.
Output: rest_data.json  { "team_name": days_rest, ... }
"""

import json, re
from datetime import datetime, timezone

COMBINED_FILE = "combined.json"
HISTORICAL_FILE = "historical_results.json"
OUTFILE = "rest_data.json"


def normalize_team(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        pass
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def main():
    # Load completed games from combined + historical
    completed = []

    try:
        with open(COMBINED_FILE, "r") as f:
            combined = json.load(f)
        for g in combined.get("data", []):
            if g.get("home_score") is not None and g.get("away_score") is not None:
                home = g.get("home_team") or {}
                away = g.get("away_team") or {}
                dt = parse_date(g.get("date_utc"))
                if dt:
                    home_name = home.get("name", "") if isinstance(home, dict) else str(home)
                    away_name = away.get("name", "") if isinstance(away, dict) else str(away)
                    completed.append((home_name, dt))
                    completed.append((away_name, dt))
    except Exception:
        pass

    try:
        with open(HISTORICAL_FILE, "r") as f:
            historical = json.load(f)
        for g in historical.get("data", []):
            home = g.get("home_team") or {}
            away = g.get("away_team") or {}
            dt = parse_date(g.get("date_utc"))
            if dt:
                home_name = home.get("name", "") if isinstance(home, dict) else str(home)
                away_name = away.get("name", "") if isinstance(away, dict) else str(away)
                completed.append((home_name, dt))
                completed.append((away_name, dt))
    except Exception:
        pass

    if not completed:
        print("[rest_days] No completed games found, writing defaults")
        with open(OUTFILE, "w") as f:
            json.dump({}, f, indent=2)
        return

    # Find most recent game date per team
    now = datetime.now(timezone.utc)
    team_last_game = {}
    for team_name, game_dt in completed:
        if not team_name:
            continue
        norm = normalize_team(team_name)
        if norm not in team_last_game or game_dt > team_last_game[norm]["dt"]:
            team_last_game[norm] = {"dt": game_dt, "name": team_name}

    # Calculate days since last game
    rest_data = {}
    for norm, info in team_last_game.items():
        days = (now - info["dt"]).days
        rest_data[info["name"]] = max(0, days)
        rest_data[norm] = max(0, days)

    with open(OUTFILE, "w") as f:
        json.dump(rest_data, f, indent=2)

    print(f"[rest_days] Wrote {OUTFILE}: {len(team_last_game)} teams")


if __name__ == "__main__":
    main()
