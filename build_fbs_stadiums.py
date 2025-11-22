#!/usr/bin/env python3
"""
build_fbs_stadiums.py
Auto-build COMPLETE FBS stadium database from ESPN Core API.

Generates:
    stadiums_fbs.json  (ALL stadiums)
    stadiums_outdoor.json (ONLY outdoor stadiums)

Output format example:
{
  "NCAAF": {
      "Michigan Wolverines": {
          "stadium": "Michigan Stadium",
          "lat": 42.2658,
          "lon": -83.7487,
          "indoor": false
      },
      ...
  }
}
"""

import json
import requests
from datetime import datetime, timezone

TIMEOUT = 10

# ESPN FBS team list
TEAMS_URL = "https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/teams?limit=300"

def get_json(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_team_objects():
    print("📡 Fetching FBS team list…")
    data = get_json(TEAMS_URL)
    teams = data.get("items", [])
    print(f"   → {len(teams)} teams found.")
    return teams


def fetch_team_details(team_ref):
    url = team_ref.get("$ref")
    if not url:
        return None

    try:
        team = get_json(url)
    except Exception:
        return None

    name = team.get("displayName") or team.get("name")
    venue_ref = team.get("venue", {}).get("$ref")

    if not venue_ref:
        return {"name": name, "stadium": None, "lat": None, "lon": None, "indoor": None}

    try:
        venue = get_json(venue_ref)
    except Exception:
        return {"name": name, "stadium": None, "lat": None, "lon": None, "indoor": None}

    # Parse location
    lat = venue.get("location", {}).get("latitude")
    lon = venue.get("location", {}).get("longitude")
    indoor = venue.get("indoor")  # boolean
    stadium = venue.get("fullName") or venue.get("shortName")

    return {
        "name": name,
        "stadium": stadium,
        "lat": lat,
        "lon": lon,
        "indoor": bool(indoor) if indoor is not None else None
    }


def main():
    teams = fetch_team_objects()
    out = {"timestamp": datetime.now(timezone.utc).isoformat(), "NCAAF": {}}

    for t in teams:
        details = fetch_team_details(t)
        if not details:
            continue

        nm = details.pop("name")
        out["NCAAF"][nm] = details
        print(f"✓ {nm}: {details['stadium']}")

    # Write full list
    with open("stadiums_fbs.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    # Extract OUTDOOR ONLY
    outdoor = {
        "NCAAF": {
            team: info
            for team, info in out["NCAAF"].items()
            if info.get("indoor") is False
        }
    }

    with open("stadiums_outdoor.json", "w", encoding="utf-8") as f:
        json.dump(outdoor, f, indent=2)

    print(f"\n[✅] Done! Wrote {len(out['NCAAF'])} total FBS stadiums")
    print(f"[🌤️] Wrote {len(outdoor['NCAAF'])} OUTDOOR stadiums → stadiums_outdoor.json")


if __name__ == "__main__":
    main()
