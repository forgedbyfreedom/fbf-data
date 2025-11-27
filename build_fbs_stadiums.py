#!/usr/bin/env python3
"""
Rebuild stadiums_master.json by scraping ESPN’s venue data directly.
This fixes the NULL latitude/longitude problem permanently.
"""

import json
import requests
from pathlib import Path
import time

OUT_MASTER = Path("stadiums_master.json")
OUT_OUTDOOR = Path("stadiums_outdoor.json")
OUT_FBS = Path("fbs_stadiums.json")

HEADERS = {"User-Agent": "fbf-stadium-builder"}

# ESPN team → venue metadata endpoint
ESPN_VENUE_URL = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{team_id}"

SPORT_MAP = {
    "ncaaf": ("football", "college-football"),
    "nfl": ("football", "nfl"),
    "ncaab": ("basketball", "mens-college-basketball"),
    "nba": ("basketball", "nba"),
    "mlb": ("baseball", "mlb"),
    "nhl": ("hockey", "nhl")
}

# All team IDs we care about (auto-collected from combined.json)
def load_team_ids():
    ids = set()
    try:
        with open("combined.json", "r") as f:
            data = json.load(f).get("data", [])
            for g in data:
                home = g.get("home_team", {}).get("id")
                away = g.get("away_team", {}).get("id")
                if home: ids.add(home)
                if away: ids.add(away)
        return sorted(ids)
    except:
        print("❌ combined.json missing or unreadable")
        return []

def fetch_venue_for_team(team_id):
    """Fetch venue for a given ESPN team ID using all sport/league prefixes."""
    for sport_key, (sport, league) in SPORT_MAP.items():
        url = ESPN_VENUE_URL.format(sport=sport, league=league, team_id=team_id)
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                continue
            js = r.json()
            venue = js.get("team", {}).get("venue")
            if venue:
                return {
                    "team_id": team_id,
                    "name": venue.get("fullName"),
                    "city": venue.get("address", {}).get("city"),
                    "state": venue.get("address", {}).get("state"),
                    "lat": venue.get("address", {}).get("latitude"),
                    "lon": venue.get("address", {}).get("longitude"),
                    "indoor": venue.get("indoor", False),
                    "grass": venue.get("grass"),
                }
        except:
            continue
    return None

def main():
    team_ids = load_team_ids()
    print(f"🔍 Fetching venue data for {len(team_ids)} teams...")

    venues = {}
    for tid in team_ids:
        v = fetch_venue_for_team(tid)
        if v and v["name"]:
            key = v["name"].lower().strip()
            venues[key] = v
        time.sleep(0.25)  # ESPN-friendly pacing

    print(f"🎉 Built {len(venues)} real stadium entries.")

    # Save master file
    with open(OUT_MASTER, "w") as f:
        json.dump(venues, f, indent=2)

    # Outdoor stadiums
    outdoor = {k: v for k,v in venues.items() if not v.get("indoor")}
    with open(OUT_OUTDOOR, "w") as f:
        json.dump(outdoor, f, indent=2)
    print(f"🎉 stadiums_outdoor.json written: {len(outdoor)} venues")

    # FBS-state filter
    fbs_states = {
        "AL","GA","FL","TX","CA","NC","SC","TN","KY","LA","MS","AR","VA","WV",
        "PA","OH","MI","IN","IL","MO","OK","NE","KS","IA","WI","MN","CO","AZ",
        "WA","OR","UT","ID","NM","NV","MA","CT","NY","NJ","MD"
    }
    fbs = {k:v for k,v in venues.items() if v.get("state") in fbs_states}

    with open(OUT_FBS, "w") as f:
        json.dump(fbs, f, indent=2)

    print(f"🎉 fbs_stadiums.json written: {len(fbs)} venues")

if __name__ == "__main__":
    main()
