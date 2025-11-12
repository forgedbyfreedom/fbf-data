#!/usr/bin/env python3
"""
track_accuracy.py
Evaluates weekly accuracy for favorites, ATS, and O/U based on ESPN Core API final scores.
Requires an up-to-date combined.json (from your odds fetchers).
Logs results to performance_log.json
"""

import requests, json, os
from datetime import datetime, timezone

OUTPUT = "performance_log.json"

def get_json(url):
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️  Failed {url}: {e}")
        return None

def extract_score(event):
    """Extract team scores cleanly from ESPN Core API event object."""
    try:
        competitors = event["competitions"][0]["competitors"]
        return {
            c["team"]["displayName"]: int(c.get("score", 0))
            for c in competitors
            if "team" in c
        }
    except Exception:
        return {}

def main():
    if not os.path.exists("combined.json"):
        print("❌ combined.json not found.")
        return

    with open("combined.json") as f:
        odds_data = json.load(f).get("data", [])

    results = []
    total_su = total_ats = total_ou = total_games = 0

    # ESPN Core API league map
    league_map = {
        "nfl": "football/leagues/nfl",
        "ncaaf": "football/leagues/college-football",
        "nba": "basketball/leagues/nba",
        "ncaab": "basketball/leagues/mens-college-basketball",
        "nhl": "hockey/leagues/nhl",
        "mlb": "baseball/leagues/mlb",
    }

    for g in odds_data:
        sport_key = g.get("sport_key", "")
        sport = sport_key.split("_")[-1]

        league_path = league_map.get(sport, None)
        if not league_path:
            continue

        url = f"https://sports.core.api.espn.com/v2/sports/{league_path}/events"
        events_data = get_json(url)
        if not events_data or "items" not in events_data:
            print(f"⚠️  No events found for {sport_key}")
            continue

        for ev_ref in events_data["items"]:
            if not isinstance(ev_ref, dict) or "$ref" not in ev_ref:
                continue

            ev_url = ev_ref["$ref"]
            event_data = get_json(ev_url)
            if not event_data:
                continue

            name = event_data.get("name", "")
            if g["home_team"] not in name and g["away_team"] not in name:
                continue

            scores = extract_score(event_data)
            if len(scores) < 2:
                continue

            fav = g.get("favorite_team")
            dog = g.get("dog_team")
            spread = g.get("fav_spread", 0) or 0
            total_line = g.get("total", 0) or 0

            fav_score = scores.get(fav, 0)
            dog_score = scores.get(dog, 0)
            total_score = fav_score + dog_score

            # Straight up (SU)
            su_correct = fav_score > dog_score

            # ATS (cover spread)
            ats_correct = (fav_score - dog_score) > abs(spread)

            # Over/Under
            ou_correct = total_score > total_line

            results.append({
                "matchup": g["matchup"],
                "favorite": fav,
                "spread": spread,
                "total": total_line,
                "fav_score": fav_score,
                "dog_score": dog_score,
                "SU_correct": su_correct,
                "ATS_correct": ats_correct,
                "OU_correct": ou_correct,
            })

            total_su += int(su_correct)
            total_ats += int(ats_correct)
            total_ou += int(ou_correct)
            total_games += 1
            break

    accuracy = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "games_checked": total_games,
        "SU_accuracy": round((total_su / total_games * 100), 2) if total_games else 0,
        "ATS_accuracy": round((total_ats / total_games * 100), 2) if total_games else 0,
        "OU_accuracy": round((total_ou / total_games * 100), 2) if total_games else 0,
    }

    print(f"[📊] Week summary: {accuracy}")
    log = []
    if os.path.exists(OUTPUT):
        with open(OUTPUT) as f:
            log = json.load(f)
    log.append(accuracy)
    with open(OUTPUT, "w") as f:
        json.dump(log, f, indent=2)
    print(f"[💾] Logged accuracy → {OUTPUT}")

if __name__ == "__main__":
    print(f"[🏈] Tracking accuracy at {datetime.now(timezone.utc).isoformat()}...")
    main()

