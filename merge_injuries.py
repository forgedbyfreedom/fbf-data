#!/usr/bin/env python3
"""
merge_injuries.py

Merges scraped injuries.json onto combined.json games.

Fixes:
- handles home_team / away_team being strings OR dicts
- handles missing/empty injuries.json safely

Inputs:
  combined.json
  injuries.json

Output:
  combined.json (overwritten with injury fields added)
"""

import json
import os
from datetime import datetime, timezone

INPUT_COMBINED = "combined.json"
INPUT_INJURIES = "injuries.json"
OUTPUT_COMBINED = "combined.json"

# Mapping from your sport_key to injury league keys
SPORTKEY_TO_LEAGUE = {
    "americanfootball_nfl": "nfl",
    "americanfootball_ncaaf": "ncaaf",
    "basketball_nba": "nba",
    "basketball_ncaab": "ncaab",
    "basketball_ncaaw": "ncaaw",
    "icehockey_nhl": "nhl",
    "baseball_mlb": "mlb",
}

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def normalize_team(team_field):
    """
    team_field can be:
      - "Chicago Bears"
      - {"name": "Chicago Bears"}
      - {"displayName": "..."}
      - {"team": {"displayName": "..."}}
    Return normalized lowercase string.
    """
    if team_field is None:
        return ""

    if isinstance(team_field, str):
        return team_field.strip().lower()

    if isinstance(team_field, dict):
        # common shapes
        for k in ("displayName", "name", "shortDisplayName", "abbreviation"):
            v = team_field.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip().lower()

        # nested "team"
        t = team_field.get("team")
        if isinstance(t, dict):
            for k in ("displayName", "name", "shortDisplayName", "abbreviation"):
                v = t.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip().lower()

        # last-ditch stringify
        return str(team_field).strip().lower()

    return str(team_field).strip().lower()

def build_injury_lookup(injuries_payload):
    """
    Creates lookup:
      lookup[league_key][normalized_team] = [injury_records...]
    """
    lookup = {}
    leagues = injuries_payload.get("leagues") or {}

    for league_key, items in leagues.items():
        league_map = {}
        for it in items or []:
            team_norm = normalize_team(it.get("team"))
            if not team_norm:
                continue
            league_map.setdefault(team_norm, []).append(it)
        lookup[league_key] = league_map

    return lookup

def main():
    combined = load_json(INPUT_COMBINED, {"count": 0, "data": []})
    injuries_payload = load_json(INPUT_INJURIES, {"leagues": {}})

    games = combined.get("data") or []
    if not games:
        print("⚠️ combined.json missing/empty → nothing to merge.")
        return

    lookup = build_injury_lookup(injuries_payload)

    merged = 0
    for g in games:
        sport_key = g.get("sport_key")
        league_key = SPORTKEY_TO_LEAGUE.get(sport_key)

        home_norm = normalize_team(g.get("home_team"))
        away_norm = normalize_team(g.get("away_team"))

        home_list = []
        away_list = []

        if league_key and league_key in lookup:
            home_list = lookup[league_key].get(home_norm, [])
            away_list = lookup[league_key].get(away_norm, [])

        # attach injuries
        g["home_injuries"] = home_list
        g["away_injuries"] = away_list
        g["injury_count_home"] = len(home_list)
        g["injury_count_away"] = len(away_list)

        if home_list or away_list:
            merged += 1

    combined["timestamp"] = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    combined["injuries_source"] = injuries_payload.get("source", "UNKNOWN")
    combined["injuries_merged_games"] = merged

    with open(OUTPUT_COMBINED, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)

    print(f"[✅] Merged injuries onto {merged}/{len(games)} games.")

if __name__ == "__main__":
    main()
