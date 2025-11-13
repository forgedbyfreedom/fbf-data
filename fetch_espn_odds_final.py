#!/usr/bin/env python3
import requests
import json
from datetime import datetime
import sys

def safe_get(url):
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        return r.json()
    except:
        return None


def extract_odds(odds_json, home, away):
    """
    ESPN odds payload ALWAYS looks like:
        odds.providers[n].odds[n].details
    where "details" contains:
        homeSpread
        awaySpread
        overUnder
    """
    if not odds_json or "items" not in odds_json:
        return None

    for item in odds_json["items"]:
        prov = safe_get(item["$ref"])
        if not prov or "details" not in prov:
            continue

        details = prov["details"]

        home_spread = details.get("homeSpread")
        away_spread = details.get("awaySpread")
        total = details.get("overUnder")

        # We need to determine favorite
        if home_spread is not None and away_spread is not None:
            if home_spread < away_spread:
                favorite = f"{home} {home_spread}"
                underdog = f"{away} {('+' + str(abs(away_spread))) if away_spread <= 0 else away_spread}"
            else:
                favorite = f"{away} {away_spread}"
                underdog = f"{home} {('+' + str(abs(home_spread))) if home_spread <= 0 else home_spread}"
        else:
            continue

        return {
            "favorite": favorite,
            "underdog": underdog,
            "total": total
        }

    return None


def build_event(event_id, sport_key, league):
    event_url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/{league}/events/{event_id}"
    event_data = safe_get(event_url)
    if not event_data:
        return None

    comp_url = event_data["competitions"][0]["$ref"]
    comp = safe_get(comp_url)
    if not comp:
        return None

    competitors = comp["competitors"]
    home_data = safe_get(competitors[0]["team"]["$ref"])
    away_data = safe_get(competitors[1]["team"]["$ref"])

    home_team = home_data.get("displayName", "HOME")
    away_team = away_data.get("displayName", "AWAY")

    odds_url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/{league}/events/{event_id}/odds"
    odds_json = safe_get(odds_url)

    odds = extract_odds(odds_json, home_team, away_team)

    return {
        "sport_key": sport_key,
        "matchup": f"{away_team}@{home_team}",
        "home_team": home_team,
        "away_team": away_team,
        "favorite": odds["favorite"] if odds else None,
        "underdog": odds["underdog"] if odds else None,
        "total": odds["total"] if odds else None,
        "commence_time": comp["date"],
        "book": "ESPN",
        "fetched_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    }


def main():
    out = {"timestamp": datetime.utcnow().strftime("%Y%m%d_%H%M"), "data": []}

    # Update with however you store event IDs
    events = {
        "americanfootball_nfl": ("nfl", []),
        "americanfootball_ncaaf": ("college-football", [])
    }

    # Load events from your existing combined.json
    try:
        with open("combined.json", "r") as f:
            combined = json.load(f)
            for game in combined["data"]:
                league_key = game["sport_key"]
                event_id = game.get("event_id")
                if event_id and league_key in events:
                    events[league_key][1].append(event_id)
    except:
        pass

    # Fetch fresh odds
    for sport_key, (league, ids) in events.items():
        for eid in ids:
            evt = build_event(eid, sport_key, league)
            if evt:
                out["data"].append(evt)

    with open("combined.json", "w") as f:
        json.dump(out, f, indent=2)

    print(f"[OK] Saved {len(out['data'])} games")


if __name__ == "__main__":
    main()

