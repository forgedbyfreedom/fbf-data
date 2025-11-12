#!/usr/bin/env python3
"""
fetch_espn_core_odds.py
ESPN Core API odds fetcher (fixed for $ref URLs and HTTP→HTTPS conversion)
Accurate favorites, spreads, and totals for all major leagues.
"""

import json, requests
from datetime import datetime, timezone

SPORTS = {
    "americanfootball_nfl": "football/leagues/nfl",
    "americanfootball_ncaaf": "football/leagues/college-football",
    "basketball_nba": "basketball/leagues/nba",
    "baseball_mlb": "baseball/leagues/mlb",
    "icehockey_nhl": "hockey/leagues/nhl",
}

BASE = "https://sports.core.api.espn.com/v2/sports"

def clean_ref(ref):
    """Normalize ESPN $ref fields (dicts → str, http → https)."""
    if isinstance(ref, dict) and "$ref" in ref:
        ref = ref["$ref"]
    if isinstance(ref, str):
        ref = ref.replace("http://", "https://")
    return ref

def get_json(url):
    """Safe ESPN JSON fetcher."""
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️  Failed: {url}\n   → {e}")
        return None

def extract_odds_from_competition(comp_url, sport_key):
    """Fetch odds directly from competition details."""
    comp_url = clean_ref(comp_url)
    comp = get_json(comp_url)
    if not comp:
        return None

    competitors = comp.get("competitors", [])
    if not competitors or len(competitors) < 2:
        return None

    home = [c for c in competitors if c.get("homeAway") == "home"][0]
    away = [c for c in competitors if c.get("homeAway") == "away"][0]

    home_team = get_json(clean_ref(home["team"]["$ref"])).get("displayName", "Home")
    away_team = get_json(clean_ref(away["team"]["$ref"])).get("displayName", "Away")

    odds_ref = comp.get("odds", {}).get("$ref")
    if not odds_ref:
        return None

    odds_data = get_json(clean_ref(odds_ref))
    if not odds_data or not odds_data.get("items"):
        return None

    odds = odds_data["items"][0]
    provider = odds.get("provider", {}).get("name", "ESPN")
    details = odds.get("details", "")
    over_under = odds.get("overUnder")

    favorite = None
    spread = None
    dog = None

    # Parse “Team -3.5” style strings
    if details:
        try:
            parts = details.split()
            team_name = " ".join(parts[:-1])
            spread_val = float(parts[-1])
            if spread_val < 0:
                favorite = team_name
                dog = home_team if favorite == away_team else away_team
                spread = spread_val
            else:
                favorite = home_team if team_name == away_team else away_team
                dog = home_team if favorite == away_team else away_team
                spread = -spread_val
        except Exception:
            pass

    return {
        "sport_key": sport_key,
        "matchup": f"{away_team}@{home_team}",
        "home_team": home_team,
        "away_team": away_team,
        "favorite_team": favorite,
        "dog_team": dog,
        "fav_spread": spread,
        "total": over_under,
        "book": provider,
        "commence_time": comp.get("date"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

def main():
    all_games = []
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    for key, path in SPORTS.items():
        url = f"{BASE}/{path}/events"
        print(f"[⏱️] Fetching {key} odds → {url}")
        data = get_json(url)
        if not data or "items" not in data:
            print(f"⚠️  No events found for {key}\n")
            continue

        for ev in data["items"]:
            ev_url = clean_ref(ev)
            event_data = get_json(ev_url)
            if not event_data:
                continue

            competitions = event_data.get("competitions", [])
            if not competitions:
                continue

            comp_url = clean_ref(competitions[0])
            odds = extract_odds_from_competition(comp_url, key)
            if odds:
                all_games.append(odds)

        print(f"   → {len(all_games)} total games so far.\n")

    output = {"timestamp": timestamp, "data": all_games}
    with open("combined.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"[✅] Saved combined.json with {len(all_games)} games at {timestamp}.")

if __name__ == "__main__":
    main()

