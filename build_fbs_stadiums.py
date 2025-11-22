#!/usr/bin/env python3
"""
build_fbs_stadiums.py

Builds a full FBS stadium list with GPS and indoor/outdoor determination.
- Pulls FBS teams from ESPN (group=80).
- Extracts venue name + geo.
- Marks indoor using known dome list + name heuristics.
- Outputs: fbs_stadiums.json

Safe on empty repo; only needs requests.
"""

import json, os, re, sys
from datetime import datetime, timezone
import requests

OUTFILE = "fbs_stadiums.json"
TIMEOUT = 12

FBS_TEAMS_URL = "https://site.api.espn.com/apis/v2/sports/football/college-football/teams?groups=80&limit=500"

# Known indoor/roofed FBS venues (not exhaustive, but covers major domes)
KNOWN_INDOOR_VENUES = {
    "Mercedes-Benz Stadium",          # Georgia State / bowl games
    "Alamodome",                      # UTSA
    "Carrier Dome", "JMA Wireless Dome",  # Syracuse
    "Ford Field",                     # bowls
    "Lucas Oil Stadium",             # bowls
    "AT&T Stadium",                  # bowls
    "State Farm Stadium",            # bowls
    "Mitsubishi Electric Classic",   # etc
    "Tropicana Field",
    "U.S. Bank Stadium",
    "NRG Stadium",
    "Caesars Superdome",
    "Acrisure Stadium Dome",         # just in case naming changes
    "Hawaii's Aloha Stadium",        # old but roofed portions
    "Allegiant Stadium",             # bowls
    "Marriott Center",               # not football, but safe
}

INDOOR_NAME_HINTS = [
    r"\bDome\b",
    r"\bIndoor\b",
    r"\bStadium\b.*\bRoof\b",
    r"\bSuperdome\b",
    r"\bFieldhouse\b",
]

def get_json(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def is_indoor(venue_name: str) -> bool:
    if not venue_name:
        return False
    if venue_name in KNOWN_INDOOR_VENUES:
        return True
    for pat in INDOOR_NAME_HINTS:
        if re.search(pat, venue_name, re.I):
            return True
    return False

def main():
    stadiums = {}
    errors = []

    try:
        data = get_json(FBS_TEAMS_URL)
        teams = (data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", []))
    except Exception as e:
        print(f"❌ Failed to pull FBS teams: {e}")
        teams = []

    for twrap in teams:
        team = twrap.get("team", {})
        tid = team.get("id")
        tname = team.get("displayName") or team.get("name")
        venue = (team.get("venue") or {})

        vname = venue.get("fullName") or venue.get("name")
        address = venue.get("address") or {}
        geo = address.get("geo") or {}

        lat = geo.get("latitude")
        lon = geo.get("longitude")

        if not vname or lat is None or lon is None:
            # Some teams don’t report geo; skip but track
            errors.append({"team": tname, "venue": vname, "reason": "missing geo or name"})
            continue

        indoor = is_indoor(vname)

        stadiums[vname] = {
            "venue_name": vname,
            "team_id": tid,
            "team_name": tname,
            "latitude": float(lat),
            "longitude": float(lon),
            "indoor": indoor,
            "outdoor": not indoor,
            "address": {
                "city": address.get("city"),
                "state": address.get("state"),
            },
        }

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "count": len(stadiums),
        "data": sorted(stadiums.values(), key=lambda x: (x["team_name"] or "")),
        "errors": errors or None,
        "source": "ESPN_FBS_TEAMS",
        "note": "Outdoor only is determined by dome list + name heuristics.",
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {OUTFILE} with {len(stadiums)} stadiums")

if __name__ == "__main__":
    main()
