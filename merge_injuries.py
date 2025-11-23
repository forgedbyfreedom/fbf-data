#!/usr/bin/env python3
import json
import os
import requests
from datetime import datetime

INJURIES_OUTPUT = "injuries.json"
COMBINED_FILE = "combined.json"
ESPN_INJURY_API = "https://sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/teams/{team_id}/injuries"

SPORT_MAP = {
    "americanfootball_nfl": ("football", "nfl"),
    "americanfootball_ncaaf": ("football", "college-football"),
    "basketball_nba": ("basketball", "nba"),
    "basketball_ncaab": ("basketball", "mens-college-basketball"),
    "icehockey_nhl": ("hockey", "nhl")
}

def normalize_team(team):
    """Return a safe lowercase team name from either a string or dict."""
    if isinstance(team, str):
        return team.lower()

    if isinstance(team, dict):
        return (
            team.get("displayName") or
            team.get("shortDisplayName") or
            team.get("name") or
            team.get("nickname") or
            team.get("abbreviation") or
            ""
        ).lower()

    return ""

def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        return json.load(open(path, "r"))
    except:
        return None

def fetch_injuries(team_id, sport_key):
    if sport_key not in SPORT_MAP:
        return []

    sport, league = SPORT_MAP[sport_key]
    url = ESPN_INJURY_API.format(sport=sport, league=league, team_id=team_id)

    try:
        r = requests.get(url, timeout=10)
        if not r.ok:
            return []
        data = r.json()
        if "items" not in data:
            return []
        injuries = []
        for item in data["items"]:
            try:
                injury = requests.get(item["$ref"]).json()
                injuries.append(injury)
            except:
                pass
        return injuries
    except Exception:
        return []

def main():
    combined = load_json(COMBINED_FILE)
    if not combined or "data" not in combined:
        print("⚠️ combined.json missing/empty")
        return

    teams_needed = set()
    game_list = combined["data"]

    for g in game_list:
        teams_needed.add(normalize_team(g.get("home_team")))
        teams_needed.add(normalize_team(g.get("away_team")))

    injuries_out = {}
    for sport_key, (sport, league) in SPORT_MAP.items():
        for team_name in teams_needed:
            # ESPN does not provide reverse lookup by name here; skip until mapping available
            continue

    json.dump(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "injuries": injuries_out
        },
        open(INJURIES_OUTPUT, "w"),
        indent=2
    )
    print("✅ injuries.json updated.")

if __name__ == "__main__":
    main()
