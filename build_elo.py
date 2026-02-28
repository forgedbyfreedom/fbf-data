#!/usr/bin/env python3
"""
build_elo.py
Implements Elo rating system for all sports.
Processes historical_results.json chronologically.
Output: elo_ratings.json { "sport": { "team_name": elo_rating, ... } }
"""

import json, re
from datetime import datetime, timezone

HISTORICAL_FILE = "historical_results.json"
COMBINED_FILE = "combined.json"
OUTFILE = "elo_ratings.json"

DEFAULT_ELO = 1500
K_FACTOR = 20


def normalize_team(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except Exception:
        return None


def expected_score(elo_a, elo_b):
    return 1 / (1 + 10 ** ((elo_b - elo_a) / 400))


def update_elo(winner_elo, loser_elo, draw=False):
    exp_w = expected_score(winner_elo, loser_elo)
    exp_l = expected_score(loser_elo, winner_elo)

    if draw:
        new_w = winner_elo + K_FACTOR * (0.5 - exp_w)
        new_l = loser_elo + K_FACTOR * (0.5 - exp_l)
    else:
        new_w = winner_elo + K_FACTOR * (1.0 - exp_w)
        new_l = loser_elo + K_FACTOR * (0.0 - exp_l)

    return round(new_w, 1), round(new_l, 1)


def main():
    # Load historical results
    games = []

    try:
        with open(HISTORICAL_FILE, "r") as f:
            hist = json.load(f)
        for g in hist.get("data", []):
            home = g.get("home_team") or {}
            away = g.get("away_team") or {}
            home_score = home.get("score")
            away_score = away.get("score")
            if home_score is None or away_score is None:
                continue
            dt = parse_date(g.get("date_utc"))
            sport = (g.get("sport") or "").lower()
            if not sport or not dt:
                continue
            games.append({
                "sport": sport,
                "date": dt,
                "home_name": home.get("name", ""),
                "away_name": away.get("name", ""),
                "home_score": float(home_score),
                "away_score": float(away_score),
            })
    except Exception as e:
        print(f"[elo] Could not load historical: {e}")

    # Also include completed games from combined.json
    try:
        with open(COMBINED_FILE, "r") as f:
            combined = json.load(f)
        for g in combined.get("data", []):
            if g.get("home_score") is None or g.get("away_score") is None:
                continue
            home = g.get("home_team") or {}
            away = g.get("away_team") or {}
            dt = parse_date(g.get("date_utc"))
            sport = (g.get("sport") or "").lower()
            if not sport or not dt:
                continue
            games.append({
                "sport": sport,
                "date": dt,
                "home_name": home.get("name", "") if isinstance(home, dict) else str(home),
                "away_name": away.get("name", "") if isinstance(away, dict) else str(away),
                "home_score": float(g["home_score"]),
                "away_score": float(g["away_score"]),
            })
    except Exception:
        pass

    if not games:
        print("[elo] No completed games found, writing defaults")
        with open(OUTFILE, "w") as f:
            json.dump({}, f, indent=2)
        return

    # Sort chronologically
    games.sort(key=lambda x: x["date"])

    # Process: separate Elo per sport
    elo = {}  # sport -> {team_name: rating}

    for g in games:
        sport = g["sport"]
        if sport not in elo:
            elo[sport] = {}

        home = g["home_name"]
        away = g["away_name"]
        if not home or not away:
            continue

        sport_elo = elo[sport]
        home_elo = sport_elo.get(home, DEFAULT_ELO)
        away_elo = sport_elo.get(away, DEFAULT_ELO)

        if g["home_score"] > g["away_score"]:
            new_home, new_away = update_elo(home_elo, away_elo)
        elif g["away_score"] > g["home_score"]:
            new_away, new_home = update_elo(away_elo, home_elo)
        else:
            new_home, new_away = update_elo(home_elo, away_elo, draw=True)

        sport_elo[home] = new_home
        sport_elo[away] = new_away

    with open(OUTFILE, "w") as f:
        json.dump(elo, f, indent=2)

    total_teams = sum(len(v) for v in elo.values())
    print(f"[elo] Wrote {OUTFILE}: {total_teams} teams across {len(elo)} sports")
    for sport, teams in sorted(elo.items()):
        ratings = sorted(teams.values(), reverse=True)
        if ratings:
            print(f"  {sport}: {len(teams)} teams, range {ratings[-1]:.0f}-{ratings[0]:.0f}")


if __name__ == "__main__":
    main()
