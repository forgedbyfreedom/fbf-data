#!/usr/bin/env python3
"""
build_historical_results.py

Creates historical_results.json from combined.json by pulling ESPN final scores.
Used as ML labels.

Safe if combined.json missing.
"""

import json, os
from datetime import datetime, timezone
import requests

TIMEOUT = 12
COMBINED_FILE = "combined.json"
OUTFILE = "historical_results.json"

LEAGUE_MAP = {
    "nfl": "football/leagues/nfl",
    "ncaaf": "football/leagues/college-football",
    "nba": "basketball/leagues/nba",
    "ncaab": "basketball/leagues/mens-college-basketball",
    "nhl": "hockey/leagues/nhl",
    "mlb": "baseball/leagues/mlb",
}

def get_json(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_score(event):
    try:
        comp = event["competitions"][0]
        competitors = comp["competitors"]
        scores = {}
        for c in competitors:
            name = c["team"]["displayName"]
            scores[name] = int(float(c.get("score", 0)))
        return scores, comp.get("status", {})
    except Exception:
        return {}, {}

def main():
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    combined = load_json(COMBINED_FILE, {})
    games = combined.get("data", [])

    if not games:
        payload = {"timestamp": ts, "data": [], "note": "combined.json missing or empty"}
        with open(OUTFILE, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"⚠️ Wrote empty {OUTFILE}")
        return

    existing = load_json(OUTFILE, {}).get("data", [])
    seen_ids = {g.get("event_id") for g in existing if g.get("event_id")}

    new_rows = []
    for g in games:
        sport_key = g.get("sport_key","")
        sport = sport_key.split("_")[-1]
        league_path = LEAGUE_MAP.get(sport)
        if not league_path or not g.get("event_id"):
            continue
        if g["event_id"] in seen_ids:
            continue

        try:
            ev_url = f"https://sports.core.api.espn.com/v2/sports/{league_path}/events/{g['event_id']}"
            ev = get_json(ev_url)
            scores, status = extract_score(ev)
            state = (status.get("type") or {}).get("state")
            if state != "post":
                continue

            fav = g.get("fav_team")
            dog = g.get("dog_team")
            spread = g.get("fav_spread") or 0
            total_line = g.get("total") or 0

            fav_score = scores.get(fav, 0)
            dog_score = scores.get(dog, 0)
            total_score = fav_score + dog_score

            new_rows.append({
                "event_id": g["event_id"],
                "sport_key": sport_key,
                "matchup": g.get("matchup"),
                "home_team": g.get("home_team"),
                "away_team": g.get("away_team"),
                "fav_team": fav,
                "dog_team": dog,
                "fav_spread": spread,
                "total_line": total_line,
                "fav_score": fav_score,
                "dog_score": dog_score,
                "home_win": scores.get(g.get("home_team"),0) > scores.get(g.get("away_team"),0),
                "fav_cover": (fav_score - dog_score) > abs(spread),
                "over": total_score > total_line if total_line else None,
                "referee": None,  # fill later if you add crew extraction
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            continue

    payload = {
        "timestamp": ts,
        "count": len(existing) + len(new_rows),
        "data": existing + new_rows
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {OUTFILE} (+{len(new_rows)} new finals)")

if __name__ == "__main__":
    main()
