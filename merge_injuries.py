#!/usr/bin/env python3
"""
merge_injuries.py

Builds injuries.json by pulling live ESPN injury lists for NFL + NCAAF FBS.

Inputs:
- combined.json (to know which teams matter)
- fbs_stadiums.json (for matching FBS team names)
Outputs:
- injuries.json

Safe if no data.

ESPN endpoints:
- NFL team injuries: /teams/{id}/injuries
- CFB team injuries: /teams/{id}/injuries (works for many teams)

No API keys required.
"""

import json, os
from datetime import datetime, timezone
import requests

COMBINED_FILE = "combined.json"
OUTFILE = "injuries.json"
TIMEOUT = 12

NFL_TEAMS_URL  = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/teams?limit=64"
FBS_TEAMS_URL  = "https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/seasons/2025/types/2/groups/80/teams?limit=400"

def get_json(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def safe_ref(ref):
    if isinstance(ref, dict) and "$ref" in ref:
        return ref["$ref"]
    return None

def build_team_id_map(url):
    m = {}
    try:
        items = get_json(url).get("items", [])
        for it in items:
            ref = it.get("$ref")
            if not ref:
                continue
            team = get_json(ref)
            name = (team.get("displayName") or "").lower()
            tid = team.get("id")
            if name and tid:
                m[name] = tid
    except Exception:
        pass
    return m

def fetch_injuries_for_team(league, team_id):
    """Return list of injuries for a team id."""
    inj_url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/{league}/teams/{team_id}/injuries"
    try:
        data = get_json(inj_url)
        items = data.get("items", [])
        injuries = []
        for it in items:
            ref = it.get("$ref")
            if not ref:
                continue
            inj = get_json(ref)
            athlete = safe_ref(inj.get("athlete"))
            player_name = None
            if athlete:
                ad = get_json(athlete)
                player_name = ad.get("displayName")
            injuries.append({
                "player": player_name or inj.get("athlete", {}).get("displayName"),
                "status": inj.get("status"),
                "type": inj.get("type"),
                "detail": inj.get("detail"),
                "date": inj.get("date"),
            })
        return injuries
    except Exception:
        return []

def main():
    combined = load_json(COMBINED_FILE, {})
    games = combined.get("data", [])
    if not games:
        payload = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
            "count": 0,
            "data": [],
            "note": "combined.json missing or empty",
        }
        with open(OUTFILE, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"⚠️ Wrote empty {OUTFILE}")
        return

    nfl_ids = build_team_id_map(NFL_TEAMS_URL)
    fbs_ids = build_team_id_map(FBS_TEAMS_URL)

    teams_needed = set()
    for g in games:
        teams_needed.add((g.get("home_team") or "").lower())
        teams_needed.add((g.get("away_team") or "").lower())

    out = []
    for t in sorted(teams_needed):
        if not t:
            continue

        league = None
        tid = None
        if t in nfl_ids:
            league = "nfl"
            tid = nfl_ids[t]
        elif t in fbs_ids:
            league = "college-football"
            tid = fbs_ids[t]

        if not league or not tid:
            continue

        injuries = fetch_injuries_for_team(league, tid)
        if injuries:
            out.append({
                "team": t.title(),
                "league": league,
                "team_id": tid,
                "injuries": injuries
            })

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "count": len(out),
        "data": out
    }

    with open(OUTFILE, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"✅ Wrote {OUTFILE} with {len(out)} teams having injuries")

if __name__ == "__main__":
    main()
