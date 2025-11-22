#!/usr/bin/env python3
"""
build_fbs_stadiums.py

Builds a full FBS stadium list from ESPN Core API:
- Pulls all FBS teams (group 80)
- Follows venue refs for GPS + roof/indoor info
- Applies manual indoor overrides for known domes/retractables
- Output: fbs_stadiums.json

Safe if ESPN endpoints fail.
"""

import json, os, sys, time
from datetime import datetime, timezone
import requests

OUTFILE = "fbs_stadiums.json"
TIMEOUT = 15

# ESPN Core API base
BASE = "https://sports.core.api.espn.com/v2/sports/football/leagues/college-football"

# Group 80 = FBS in ESPN structure
FBS_TEAMS_URL = f"{BASE}/groups/80/teams?limit=500"

# Known indoor / retractable FBS teams (team displayName -> indoor True)
# This keeps "outdoor only weather" accurate even if ESPN venue metadata is missing.
INDOOR_TEAM_OVERRIDES = {
    # ACC / Big 12 / Big Ten etc.
    "Syracuse Orange": True,          # JMA Wireless Dome
    "Duke Blue Devils": False,
    "Pittsburgh Panthers": False,
    "Miami Hurricanes": False,
    "SMU Mustangs": False,
    "Houston Cougars": False,
    "UTSA Roadrunners": True,         # Alamodome
    "Tulsa Golden Hurricane": False,

    # SEC / others
    "Alabama Crimson Tide": False,
    "Georgia Bulldogs": False,
    "LSU Tigers": False,

    # Big Ten
    "Northwestern Wildcats": False,
    "Illinois Fighting Illini": False,

    # Pac / west
    "UNLV Rebels": True,              # Allegiant Stadium (retractable but roofed)
    "Arizona State Sun Devils": False,

    # Independents / AAC / CUSA / MWC / Sun Belt etc.
    "Liberty Flames": False,
    "Boise State Broncos": False,
    "Hawai'i Rainbow Warriors": False,
}

def get_json(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def deref(ref_obj):
    """ESPN core often returns {$ref: url}."""
    if isinstance(ref_obj, dict) and "$ref" in ref_obj:
        return get_json(ref_obj["$ref"])
    return ref_obj

def safe(val, default=None):
    return val if val is not None else default

def infer_indoor_from_venue(venue):
    """
    Attempt to infer indoor/retractable from ESPN venue metadata.
    Defaults to False if unknown.
    """
    if not isinstance(venue, dict):
        return False

    # ESPN sometimes exposes 'indoor' or roofType
    if venue.get("indoor") is True:
        return True

    roof = (venue.get("roofType") or venue.get("roof") or "").lower()
    surface = (venue.get("surface") or "").lower()

    # Common roof keywords
    if any(k in roof for k in ["dome", "indoor", "retract", "covered"]):
        return True

    # If venue explicitly says outdoor
    if "outdoor" in roof:
        return False

    # If still unknown, assume outdoor (safer for "outdoor only weather")
    return False

def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    try:
        teams_payload = get_json(FBS_TEAMS_URL)
        items = teams_payload.get("items", [])
    except Exception as e:
        payload = {
            "timestamp": stamp,
            "count": 0,
            "data": [],
            "errors": [f"Failed to fetch FBS teams: {e}"],
        }
        with open(OUTFILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"❌ {OUTFILE} wrote empty list (teams fetch failed)")
        return

    out = []
    errors = []

    for it in items:
        try:
            team = deref(it)
            if not isinstance(team, dict):
                continue

            team_id = team.get("id")
            team_name = team.get("displayName")
            abbr = team.get("abbreviation")
            short_name = team.get("shortDisplayName")

            # conference (best effort)
            conf_name = None
            try:
                conf = deref(team.get("conference"))
                conf_name = conf.get("name") or conf.get("shortName")
            except Exception:
                conf_name = None

            venue = None
            try:
                venue = deref(team.get("venue"))
            except Exception:
                venue = None

            if not isinstance(venue, dict):
                errors.append({"team": team_name, "reason": "venue missing"})
                continue

            venue_id = venue.get("id")
            venue_name = venue.get("fullName") or venue.get("name")
            address = venue.get("address") or {}
            city = address.get("city")
            state = address.get("state")
            country = address.get("country")

            lat = venue.get("latitude")
            lon = venue.get("longitude")

            indoor = infer_indoor_from_venue(venue)

            # Manual override by team name if present
            if team_name in INDOOR_TEAM_OVERRIDES:
                indoor = INDOOR_TEAM_OVERRIDES[team_name]

            out.append({
                "team_id": team_id,
                "team_name": team_name,
                "abbreviation": abbr,
                "short_name": short_name,
                "conference": conf_name,
                "venue_id": venue_id,
                "venue_name": venue_name,
                "latitude": lat,
                "longitude": lon,
                "city": city,
                "state": state,
                "country": country,
                "indoor": indoor,
                "source": "espn-core",
            })

        except Exception as e:
            errors.append({"item": str(it)[:120], "reason": str(e)})

    payload = {
        "timestamp": stamp,
        "count": len(out),
        "data": out,
        "errors": errors or None,
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {OUTFILE} with {len(out)} FBS stadium entries")

if __name__ == "__main__":
    main()
