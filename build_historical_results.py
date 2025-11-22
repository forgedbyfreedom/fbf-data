#!/usr/bin/env python3
"""
build_historical_results.py

Pulls final scores from ESPN Core API and builds/updates historical_results.json.
Uses combined.json to know which games to track.

Outputs:
- historical_results.json
"""

import os, json, requests, re
from datetime import datetime, timezone

COMBINED_FILE = "combined.json"
OUTFILE = "historical_results.json"
TIMEOUT = 12

LEAGUE_MAP = {
    "nfl": "football/leagues/nfl",
    "ncaaf": "football/leagues/college-football",
    "nba": "basketball/leagues/nba",
    "ncaab": "basketball/leagues/mens-college-basketball",
    "nhl": "hockey/leagues/nhl",
    "mlb": "baseball/leagues/mlb",
    "mma": "mma/leagues/ufc",
}

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_json(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def norm_team(n):
    return re.sub(r"[^a-z0-9]+", "", (n or "").lower())

def extract_scores(event):
    try:
        competitors = event["competitions"][0]["competitors"]
        out = {}
        for c in competitors:
            team = c["team"]["displayName"]
            out[team] = int(c.get("score", 0))
        return out
    except Exception:
        return {}

def compute_fav_cover(fav_score, dog_score, spread):
    if spread is None:
        return None
    return (fav_score + spread) > dog_score

def compute_over(fav_score, dog_score, total):
    if total is None:
        return None
    return (fav_score + dog_score) > total

def main():
    combined = load_json(COMBINED_FILE, {}).get("data", [])
    if not combined:
        print("⚠️ combined.json missing/empty.")
        return

    existing_payload = load_json(OUTFILE, {"data": []})
    existing = existing_payload.get("data", [])
    existing_ids = set([e.get("event_id") for e in existing if e.get("event_id")])

    results = existing[:]

    sports_present = set()
    for g in combined:
        sk = g.get("sport_key", "")
        if sk:
            sports_present.add(sk.split("_")[-1])

    for sport in sports_present:
        league_path = LEAGUE_MAP.get(sport)
        if not league_path:
            continue

        events_url = f"https://sports.core.api.espn.com/v2/sports/{league_path}/events"
        try:
            events = get_json(events_url).get("items", [])
        except Exception as e:
            print(f"⚠️ ESPN events failed for {sport}: {e}")
            continue

        for ev_ref in events:
            if not isinstance(ev_ref, dict) or "$ref" not in ev_ref:
                continue

            ev_url = ev_ref["$ref"]
            try:
                ev = get_json(ev_url)
            except Exception:
                continue

            status = ev.get("status", {}).get("type", {}).get("state")
            if status != "post":
                continue  # only finals

            ev_name = ev.get("name", "")
            scores = extract_scores(ev)
            if len(scores) < 2:
                continue

            # try to match with combined
            match_game = None
            for g in combined:
                if norm_team(g.get("home_team")) in norm_team(ev_name) and \
                   norm_team(g.get("away_team")) in norm_team(ev_name):
                    match_game = g
                    break

            if not match_game:
                continue

            event_id = match_game.get("event_id") or ev.get("id") or match_game.get("matchup")
            if event_id in existing_ids:
                continue

            fav_team = match_game.get("fav_team") or match_game.get("favorite_team") or match_game.get("home_team")
            dog_team = match_game.get("dog_team") or match_game.get("underdog_team") or match_game.get("away_team")
            spread = match_game.get("spread", match_game.get("fav_spread"))
            total = match_game.get("total")

            fav_score = scores.get(fav_team)
            dog_score = scores.get(dog_team)
            if fav_score is None or dog_score is None:
                continue

            fav_cover = compute_fav_cover(fav_score, dog_score, spread)
            over = compute_over(fav_score, dog_score, total)

            results.append({
                "event_id": event_id,
                "matchup": match_game.get("matchup"),
                "sport_key": match_game.get("sport_key"),
                "commence_time": match_game.get("commence_time"),
                "fav_team": fav_team,
                "dog_team": dog_team,
                "spread": spread,
                "total": total,
                "fav_score": fav_score,
                "dog_score": dog_score,
                "fav_cover": fav_cover,
                "over": over,
                "fetched_at": datetime.now(timezone.utc).isoformat()
            })
            existing_ids.add(event_id)

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "count": len(results),
        "data": results
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"✅ Wrote {OUTFILE} ({len(results)} total games).")

if __name__ == "__main__":
    main()
