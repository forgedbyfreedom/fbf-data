#!/usr/bin/env python3
"""
backtest.py
Back-tests the Monte Carlo model against historical results.
Re-simulates each historical game with current model weights and
compares predictions to actual outcomes.

This tells us what the model WOULD have picked for past games.
"""

import json
from monte_carlo import simulate_and_pick, safe_float

HISTORICAL = "historical_results.json"


def main():
    with open(HISTORICAL) as f:
        hist = json.load(f)

    events = hist.get("data", [])
    print(f"[backtest] {len(events)} historical games")

    # Stats
    sports = ["ALL", "NFL", "NCAAF", "NBA", "NCAAB", "NHL"]
    stats = {}
    for s in sports:
        stats[s] = {
            "su_w": 0, "su_l": 0,
            "ats_w": 0, "ats_l": 0, "ats_skip": 0,
            "ou_w": 0, "ou_l": 0, "ou_skip": 0,
        }

    for event in events:
        sport = (event.get("sport") or "").upper()
        if sport not in stats:
            continue

        home_team = event.get("home_team") or {}
        away_team = event.get("away_team") or {}
        home_score = safe_float(home_team.get("score"), None)
        away_score = safe_float(away_team.get("score"), None)
        if home_score is None or away_score is None:
            continue

        spread = safe_float(event.get("spread"), None)
        total = safe_float(event.get("total"), None)
        if spread is None and total is None:
            continue

        home_name = home_team.get("name", "Home")
        home_abbr = home_team.get("abbr", "HME")
        away_name = away_team.get("name", "Away")
        away_abbr = away_team.get("abbr", "AWY")

        # Build a game dict compatible with simulate_and_pick
        game = {
            "sport": sport.lower(),
            "odds": {"spread": spread, "total": total},
            "home_team": {"name": home_name, "abbr": home_abbr},
            "away_team": {"name": away_name, "abbr": away_abbr},
            "injury_count_home": 0,
            "injury_count_away": 0,
            "venue": {"indoor": True},
        }

        # Determine favorite
        if spread is not None and spread < 0:
            game["fav_team"] = home_name
            game["fav_abbr"] = home_abbr
            game["dog_team"] = away_name
            game["dog_abbr"] = away_abbr
        elif spread is not None and spread > 0:
            game["fav_team"] = away_name
            game["fav_abbr"] = away_abbr
            game["dog_team"] = home_name
            game["dog_abbr"] = home_abbr

        try:
            result = simulate_and_pick(game, n_sims=2000)
        except Exception:
            continue

        picks = result.get("picks", {})
        actual_margin = home_score - away_score
        actual_total = home_score + away_score

        # SU
        su_pick_abbr = picks.get("su_pick_abbr")
        if su_pick_abbr:
            winner_abbr = home_abbr if home_score > away_score else away_abbr
            if home_score == away_score:
                pass
            elif su_pick_abbr == winner_abbr:
                stats["ALL"]["su_w"] += 1
                stats[sport]["su_w"] += 1
            else:
                stats["ALL"]["su_l"] += 1
                stats[sport]["su_l"] += 1

        # ATS
        if picks.get("ats_no_play"):
            stats["ALL"]["ats_skip"] += 1
            stats[sport]["ats_skip"] += 1
        elif spread is not None:
            ats_abbr_pick = picks.get("ats_pick_abbr")
            pick_is_home = (ats_abbr_pick == home_abbr)
            home_covered = actual_margin + spread > 0
            push = abs(actual_margin + spread) < 0.01
            if not push:
                covered = home_covered if pick_is_home else not home_covered
                if covered:
                    stats["ALL"]["ats_w"] += 1
                    stats[sport]["ats_w"] += 1
                else:
                    stats["ALL"]["ats_l"] += 1
                    stats[sport]["ats_l"] += 1

        # O/U
        if picks.get("ou_no_play"):
            stats["ALL"]["ou_skip"] += 1
            stats[sport]["ou_skip"] += 1
        elif total is not None:
            ou_pick = picks.get("ou_pick")
            push = abs(actual_total - total) < 0.01
            if not push:
                if (ou_pick == "Over" and actual_total > total) or \
                   (ou_pick == "Under" and actual_total < total):
                    stats["ALL"]["ou_w"] += 1
                    stats[sport]["ou_w"] += 1
                else:
                    stats["ALL"]["ou_l"] += 1
                    stats[sport]["ou_l"] += 1

    # Print results
    print(f"\n{'Sport':8s} {'SU':15s} {'ATS':20s} {'O/U':20s}")
    print("-" * 65)
    for s in sports:
        st = stats[s]
        su_t = st["su_w"] + st["su_l"]
        su_pct = st["su_w"] / su_t * 100 if su_t else 0
        ats_t = st["ats_w"] + st["ats_l"]
        ats_pct = st["ats_w"] / ats_t * 100 if ats_t else 0
        ou_t = st["ou_w"] + st["ou_l"]
        ou_pct = st["ou_w"] / ou_t * 100 if ou_t else 0

        su_str = f"{st['su_w']}-{st['su_l']} ({su_pct:.1f}%)"
        ats_str = f"{st['ats_w']}-{st['ats_l']} ({ats_pct:.1f}%) sk:{st['ats_skip']}"
        ou_str = f"{st['ou_w']}-{st['ou_l']} ({ou_pct:.1f}%) sk:{st['ou_skip']}"

        print(f"{s:8s} {su_str:15s} {ats_str:20s} {ou_str:20s}")


if __name__ == "__main__":
    main()
