#!/usr/bin/env python3
"""
build_h2h.py
Builds head-to-head historical matchup data for all team pairs.
Output: h2h_data.json { "teama_vs_teamb": { wins, losses, avg_margin, games, ... } }
"""

import json, re
from datetime import datetime, timezone

HISTORICAL_FILE = "historical_results.json"
COMBINED_FILE = "combined.json"
OUTFILE = "h2h_data.json"


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


def main():
    games = []

    # Load from historical
    try:
        with open(HISTORICAL_FILE, "r") as f:
            hist = json.load(f)
        for g in hist.get("data", []):
            home = g.get("home_team") or {}
            away = g.get("away_team") or {}
            hs = home.get("score")
            as_ = away.get("score")
            if hs is None or as_ is None:
                continue
            dt = parse_date(g.get("date_utc"))
            sport = (g.get("sport") or "").lower()
            if not sport:
                continue
            games.append({
                "sport": sport,
                "date": dt,
                "home": home.get("name", ""),
                "away": away.get("name", ""),
                "home_score": float(hs),
                "away_score": float(as_),
            })
    except Exception:
        pass

    # Load completed from combined
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
            if not sport:
                continue
            games.append({
                "sport": sport,
                "date": dt,
                "home": home.get("name", "") if isinstance(home, dict) else str(home),
                "away": away.get("name", "") if isinstance(away, dict) else str(away),
                "home_score": float(g["home_score"]),
                "away_score": float(g["away_score"]),
            })
    except Exception:
        pass

    if not games:
        print("[h2h] No completed games found")
        with open(OUTFILE, "w") as f:
            json.dump({}, f, indent=2)
        return

    # Build H2H stats for each unique matchup
    # Key: "{norm_home}_vs_{norm_away}" (alphabetically ordered)
    h2h = {}

    for g in games:
        home = g["home"]
        away = g["away"]
        if not home or not away:
            continue

        # Canonical key: alphabetical order of normalized names
        norm_h = normalize_team(home)
        norm_a = normalize_team(away)
        if norm_h <= norm_a:
            key = f"{norm_h}_vs_{norm_a}"
            team_a, team_b = home, away
            score_a, score_b = g["home_score"], g["away_score"]
        else:
            key = f"{norm_a}_vs_{norm_h}"
            team_a, team_b = away, home
            score_a, score_b = g["away_score"], g["home_score"]

        if key not in h2h:
            h2h[key] = {
                "team_a": team_a,
                "team_b": team_b,
                "sport": g["sport"],
                "games": 0,
                "a_wins": 0,
                "b_wins": 0,
                "draws": 0,
                "total_margin": 0.0,  # positive = team_a advantage
                "last_5_margins": [],
            }

        rec = h2h[key]
        rec["games"] += 1
        margin = score_a - score_b
        rec["total_margin"] += margin
        rec["last_5_margins"].append(margin)
        if len(rec["last_5_margins"]) > 5:
            rec["last_5_margins"] = rec["last_5_margins"][-5:]

        if score_a > score_b:
            rec["a_wins"] += 1
        elif score_b > score_a:
            rec["b_wins"] += 1
        else:
            rec["draws"] += 1

    # Compute averages
    for key, rec in h2h.items():
        if rec["games"] > 0:
            rec["avg_margin"] = round(rec["total_margin"] / rec["games"], 2)
        else:
            rec["avg_margin"] = 0.0
        if rec["last_5_margins"]:
            rec["recent_avg_margin"] = round(sum(rec["last_5_margins"]) / len(rec["last_5_margins"]), 2)
        else:
            rec["recent_avg_margin"] = 0.0
        del rec["total_margin"]

    with open(OUTFILE, "w") as f:
        json.dump(h2h, f, indent=2)

    print(f"[h2h] Wrote {OUTFILE}: {len(h2h)} matchup pairs from {len(games)} games")


if __name__ == "__main__":
    main()
