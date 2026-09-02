#!/usr/bin/env python3
"""
build_power_ratings.py
Computes sport-specific offensive/defensive power ratings from historical data.

For each team, calculates:
- Offensive rating: points scored per game (adjusted for opponent strength)
- Defensive rating: points allowed per game (adjusted for opponent strength)
- Net rating: offense - defense (positive = good)
- Pace proxy: average total points in team's games
- Home/away splits: separate ratings for home and road games
- Recent form: last 10 game trend (hot/cold)
- ATS record: overall and recent against-the-spread performance

Output: power_ratings.json

Run AFTER: build_historical_results.py
Run BEFORE: merge_features.py
"""

import json, math, re
from collections import defaultdict
from datetime import datetime, timezone

HISTORICAL = "historical_results.json"
OUTPUT = "power_ratings.json"

# League average points per game (approximate baselines)
LEAGUE_AVG = {
    "nfl": 22.5,
    "ncaaf": 28.0,
    "nba": 112.0,
    "ncaab": 72.0,
    "nhl": 3.1,
    "mlb": 4.5,
}


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def normalize(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def main():
    hist = load_json(HISTORICAL, {})
    games = hist.get("data", [])
    if not games:
        print("[power_ratings] No historical data")
        return

    # Collect per-team stats
    # Structure: teams[sport][team_key] = { games, home_games, away_games, ... }
    teams = defaultdict(lambda: defaultdict(lambda: {
        "name": "",
        "abbr": "",
        "games": 0,
        "home_games": 0,
        "away_games": 0,
        "pts_scored": 0,
        "pts_allowed": 0,
        "home_pts_scored": 0,
        "home_pts_allowed": 0,
        "away_pts_scored": 0,
        "away_pts_allowed": 0,
        "home_wins": 0,
        "away_wins": 0,
        "home_losses": 0,
        "away_losses": 0,
        "totals": [],
        "margins": [],
        "ats_wins": 0,
        "ats_losses": 0,
        "ats_pushes": 0,
        "recent_games": [],  # (date, margin, scored, allowed, is_home, ats_result)
    }))

    # Sort games by date for recent form tracking
    sorted_games = sorted(games, key=lambda g: g.get("date_utc", "") or "")

    for g in sorted_games:
        sport = (g.get("sport") or "").lower()
        if sport not in LEAGUE_AVG:
            continue

        home = g.get("home_team", {})
        away = g.get("away_team", {})
        home_score = home.get("score")
        away_score = away.get("score")
        if home_score is None or away_score is None:
            continue

        home_name = home.get("name", "")
        away_name = away.get("name", "")
        home_abbr = home.get("abbr", "")
        away_abbr = away.get("abbr", "")
        home_key = normalize(home_name) or normalize(home_abbr)
        away_key = normalize(away_name) or normalize(away_abbr)

        if not home_key or not away_key:
            continue

        hs = float(home_score)
        aws = float(away_score)
        total = hs + aws
        margin = hs - aws
        date = g.get("date_utc", "")
        ats = g.get("ats_result", "none")

        # Home team stats
        ht = teams[sport][home_key]
        ht["name"] = home_name
        ht["abbr"] = home_abbr
        ht["games"] += 1
        ht["home_games"] += 1
        ht["pts_scored"] += hs
        ht["pts_allowed"] += aws
        ht["home_pts_scored"] += hs
        ht["home_pts_allowed"] += aws
        ht["totals"].append(total)
        ht["margins"].append(margin)
        if margin > 0:
            ht["home_wins"] += 1
        else:
            ht["home_losses"] += 1

        # ATS for home team
        home_ats = "none"
        if "covers" in ats:
            # figure out if home team covered
            fav = g.get("favorite", "")
            if fav == home_abbr:
                home_ats = "win" if "covers" in ats else "loss"
            elif fav == away_abbr:
                home_ats = "loss" if "covers" in ats else "win"
            else:
                # Check by ats string
                if home_abbr and home_abbr in ats and "covers" in ats:
                    home_ats = "win"
                elif away_abbr and away_abbr in ats and "covers" in ats:
                    home_ats = "loss"
        elif "fails" in ats:
            fav = g.get("favorite", "")
            if fav == home_abbr:
                home_ats = "loss"
            elif fav == away_abbr:
                home_ats = "win"
        elif ats == "push":
            home_ats = "push"

        if home_ats == "win":
            ht["ats_wins"] += 1
        elif home_ats == "loss":
            ht["ats_losses"] += 1
        elif home_ats == "push":
            ht["ats_pushes"] += 1

        ht["recent_games"].append((date, margin, hs, aws, True, home_ats))

        # Away team stats
        at = teams[sport][away_key]
        at["name"] = away_name
        at["abbr"] = away_abbr
        at["games"] += 1
        at["away_games"] += 1
        at["pts_scored"] += aws
        at["pts_allowed"] += hs
        at["away_pts_scored"] += aws
        at["away_pts_allowed"] += hs
        at["totals"].append(total)
        at["margins"].append(-margin)
        if margin < 0:
            at["away_wins"] += 1
        else:
            at["away_losses"] += 1

        away_ats = "none"
        if home_ats == "win":
            away_ats = "loss"
        elif home_ats == "loss":
            away_ats = "win"
        elif home_ats == "push":
            away_ats = "push"

        if away_ats == "win":
            at["ats_wins"] += 1
        elif away_ats == "loss":
            at["ats_losses"] += 1
        elif away_ats == "push":
            at["ats_pushes"] += 1

        at["recent_games"].append((date, -margin, aws, hs, False, away_ats))

    # Shrinkage prior: a team's own numbers get weight games/(games+PRIOR_GAMES),
    # the league mean gets the rest. 8 is roughly "trust a team once it has
    # half a season of evidence".
    PRIOR_GAMES = 8.0

    # Compute ratings
    output = {}
    for sport, sport_teams in teams.items():
        league_avg = LEAGUE_AVG.get(sport, 50)
        sport_output = {}

        _rated = [t for t in sport_teams.values() if t["games"] > 0]
        league_off_mean = (sum(x["pts_scored"] / x["games"] for x in _rated) / len(_rated)) if _rated else 0.0
        league_def_mean = (sum(x["pts_allowed"] / x["games"] for x in _rated) / len(_rated)) if _rated else 0.0

        for team_key, t in sport_teams.items():
            if t["games"] < 3:
                continue

            g = t["games"]

            # ── SHRINK TOWARD THE LEAGUE MEAN ON THIN SAMPLES ────────
            # A rating built from four games is noise wearing a number. On
            # 2026-09-01 Arkansas-Pine Bluff carried a net rating of -55.3 off
            # 4 games and Tennessee State -38.8 off 5, against 32-37 games for
            # the FBS sides they were compared with. Those numbers reached the
            # adjustment layer at full weight and produced projections such as
            # Furman beating Tennessee by 47. Shrinking pulls a thin sample
            # toward average instead of letting it shout.
            w = g / (g + PRIOR_GAMES)
            off_rating = round(w * (t["pts_scored"] / g) + (1 - w) * league_off_mean, 1)
            def_rating = round(w * (t["pts_allowed"] / g) + (1 - w) * league_def_mean, 1)
            net_rating = round(off_rating - def_rating, 1)

            # Pace: average total points in this team's games
            pace = round(sum(t["totals"]) / len(t["totals"]), 1) if t["totals"] else league_avg * 2

            # Home/away splits
            hg = t["home_games"] or 1
            ag = t["away_games"] or 1
            home_off = round(t["home_pts_scored"] / hg, 1)
            home_def = round(t["home_pts_allowed"] / hg, 1)
            away_off = round(t["away_pts_scored"] / ag, 1)
            away_def = round(t["away_pts_allowed"] / ag, 1)

            home_win_pct = round(100 * t["home_wins"] / hg, 1)
            away_win_pct = round(100 * t["away_wins"] / ag, 1)

            # ATS record
            ats_total = t["ats_wins"] + t["ats_losses"]
            ats_pct = round(100 * t["ats_wins"] / ats_total, 1) if ats_total > 0 else 50.0

            # Recent form: last 10 games
            recent = t["recent_games"][-10:]
            recent_margins = [r[1] for r in recent]
            recent_scored = [r[2] for r in recent]
            recent_allowed = [r[3] for r in recent]
            recent_wins = sum(1 for r in recent if r[1] > 0)
            recent_ats_wins = sum(1 for r in recent if r[5] == "win")
            recent_ats_total = sum(1 for r in recent if r[5] in ("win", "loss"))

            recent_avg_margin = round(sum(recent_margins) / len(recent_margins), 1) if recent_margins else 0
            recent_avg_scored = round(sum(recent_scored) / len(recent_scored), 1) if recent_scored else 0
            recent_avg_allowed = round(sum(recent_allowed) / len(recent_allowed), 1) if recent_allowed else 0
            recent_win_pct = round(100 * recent_wins / len(recent), 1) if recent else 50
            recent_ats_pct = round(100 * recent_ats_wins / recent_ats_total, 1) if recent_ats_total > 0 else 50

            # Momentum: compare recent 5 to prior 5
            last5 = t["recent_games"][-5:]
            prior5 = t["recent_games"][-10:-5] if len(t["recent_games"]) >= 10 else []
            last5_margin = sum(r[1] for r in last5) / max(len(last5), 1)
            prior5_margin = sum(r[1] for r in prior5) / max(len(prior5), 1) if prior5 else last5_margin
            momentum = round(last5_margin - prior5_margin, 1)

            # Consistency: stdev of margins
            if len(t["margins"]) > 1:
                mean_m = sum(t["margins"]) / len(t["margins"])
                variance = sum((m - mean_m) ** 2 for m in t["margins"]) / (len(t["margins"]) - 1)
                margin_stdev = round(math.sqrt(variance), 1)
            else:
                margin_stdev = 0

            # Scoring consistency (stdev of totals)
            if len(t["totals"]) > 1:
                mean_t = sum(t["totals"]) / len(t["totals"])
                t_var = sum((x - mean_t) ** 2 for x in t["totals"]) / (len(t["totals"]) - 1)
                total_stdev = round(math.sqrt(t_var), 1)
            else:
                total_stdev = 0

            sport_output[team_key] = {
                "name": t["name"],
                "abbr": t["abbr"],
                "games": g,
                "off_rating": off_rating,
                "def_rating": def_rating,
                "net_rating": net_rating,
                "rating_weight": round(w, 3),
                "pace": pace,
                "home_off": home_off,
                "home_def": home_def,
                "away_off": away_off,
                "away_def": away_def,
                "home_win_pct": home_win_pct,
                "away_win_pct": away_win_pct,
                "ats_pct": ats_pct,
                "ats_record": f"{t['ats_wins']}-{t['ats_losses']}-{t['ats_pushes']}",
                "recent_win_pct": recent_win_pct,
                "recent_ats_pct": recent_ats_pct,
                "recent_avg_margin": recent_avg_margin,
                "recent_avg_scored": recent_avg_scored,
                "momentum": momentum,
                "margin_stdev": margin_stdev,
                "total_stdev": total_stdev,
            }

        output[sport] = sport_output

    total_teams = sum(len(v) for v in output.values())
    with open(OUTPUT, "w") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "team_count": total_teams,
            "ratings": output,
        }, f, indent=2)

    print(f"[power_ratings] {total_teams} teams across {len(output)} sports")
    for sport, st in output.items():
        if st:
            # Show top 3 by net rating
            top = sorted(st.values(), key=lambda x: x["net_rating"], reverse=True)[:3]
            names = ", ".join(f"{t['abbr']} ({t['net_rating']:+.1f})" for t in top)
            print(f"  {sport}: {len(st)} teams — top: {names}")


if __name__ == "__main__":
    main()
