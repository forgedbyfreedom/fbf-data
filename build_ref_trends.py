#!/usr/bin/env python3
"""
build_ref_trends.py
Creates referee trend statistics from historical_results.json.

For each referee with 10+ games, calculates:
- home_win_pct: % of games where home team won
- over_pct: % of games that went over the total
- fav_cover_pct: % of games where favorite covered the spread
- games: total games officiated

Output: referee_trends.json
"""

import json, re, os
from datetime import datetime, timezone

HISTORICAL_FILE = "historical_results.json"
COMBINED_FILE = "combined.json"
OUTPUT = "referee_trends.json"
MIN_GAMES = 10


def normalize_name(name):
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def main():
    # Load historical results (which now include officials)
    games = []
    for filepath in [HISTORICAL_FILE, COMBINED_FILE]:
        if not os.path.exists(filepath):
            continue
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            for g in data.get("data", []):
                officials = g.get("officials") or []
                if not officials:
                    continue
                # Need scores for stats
                home = g.get("home_team") or {}
                away = g.get("away_team") or {}
                home_score = home.get("score") if isinstance(home, dict) else g.get("home_score")
                away_score = away.get("score") if isinstance(away, dict) else g.get("away_score")
                if home_score is None or away_score is None:
                    continue
                games.append({
                    "officials": officials,
                    "home_score": float(home_score),
                    "away_score": float(away_score),
                    "spread": g.get("spread"),
                    "total": g.get("total"),
                    "favorite": g.get("favorite"),
                    "ats_result": g.get("ats_result"),
                    "ou_result": g.get("ou_result"),
                    "home_abbr": home.get("abbr") if isinstance(home, dict) else "",
                    "away_abbr": away.get("abbr") if isinstance(away, dict) else "",
                })
        except Exception as e:
            print(f"[ref_trends] Error loading {filepath}: {e}")

    if not games:
        print("[ref_trends] No games with officials found, writing empty trends")
        out = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "historical_results.json",
            "refs": {},
        }
        with open(OUTPUT, "w") as f:
            json.dump(out, f, indent=2)
        return

    # Accumulate stats per referee
    ref_stats = {}

    for g in games:
        officials = g["officials"]
        home_score = g["home_score"]
        away_score = g["away_score"]
        home_won = home_score > away_score
        total_pts = home_score + away_score
        game_total = g.get("total")
        ats_result = g.get("ats_result", "")
        ou_result = g.get("ou_result", "")

        # Determine over/under from result or calculate
        if ou_result:
            went_over = ou_result == "over"
            went_under = ou_result == "under"
        elif game_total is not None:
            try:
                went_over = total_pts > float(game_total)
                went_under = total_pts < float(game_total)
            except (ValueError, TypeError):
                went_over = False
                went_under = False
        else:
            went_over = False
            went_under = False

        # Determine if favorite covered
        fav_covered = "_covers" in (ats_result or "")

        for o in officials:
            if isinstance(o, dict):
                name = o.get("name") or o.get("fullName") or o.get("displayName")
            elif isinstance(o, str):
                name = o
            else:
                continue

            if not name:
                continue

            norm = normalize_name(name)
            if norm not in ref_stats:
                ref_stats[norm] = {
                    "name": name,
                    "games": 0,
                    "home_wins": 0,
                    "overs": 0,
                    "unders": 0,
                    "fav_covers": 0,
                    "fav_fails": 0,
                }

            s = ref_stats[norm]
            s["games"] += 1
            if home_won:
                s["home_wins"] += 1
            if went_over:
                s["overs"] += 1
            if went_under:
                s["unders"] += 1
            if fav_covered:
                s["fav_covers"] += 1
            elif "_fails" in (ats_result or ""):
                s["fav_fails"] += 1

    # Compute percentages, filter to MIN_GAMES
    refs_output = {}
    for norm, s in ref_stats.items():
        if s["games"] < MIN_GAMES:
            continue

        ou_total = s["overs"] + s["unders"]
        ats_total = s["fav_covers"] + s["fav_fails"]

        refs_output[s["name"]] = {
            "name": s["name"],
            "games": s["games"],
            "home_win_pct": round(s["home_wins"] / s["games"] * 100, 1) if s["games"] else 50.0,
            "over_pct": round(s["overs"] / ou_total * 100, 1) if ou_total else 50.0,
            "fav_cover_pct": round(s["fav_covers"] / ats_total * 100, 1) if ats_total else 50.0,
        }

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "historical_results.json + combined.json",
        "refs": refs_output,
    }

    with open(OUTPUT, "w") as f:
        json.dump(out, f, indent=2)

    print(f"[ref_trends] Wrote {OUTPUT}: {len(refs_output)} referees with {MIN_GAMES}+ games (from {len(ref_stats)} total)")


if __name__ == "__main__":
    main()
