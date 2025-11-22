#!/usr/bin/env python3
"""
build_fbs_stadiums.py

Builds a full FBS stadium list with lat/lon + indoor/outdoor flag.
Output: fbs_stadiums.json

Strategy:
- Pull current FBS teams from ESPN college-football API
- For each team, get venue/stadium data (name, address, capacity, geo)
- Mark indoor based on venue.indoor boolean if present, else False
- Safe if ESPN changes fields — script degrades gracefully.

Requires: requests
"""

import json
import os
from datetime import datetime, timezone
import requests

OUTFILE = "fbs_stadiums.json"
TIMEOUT = 15

TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams"
TEAM_URL_TMPL = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/teams/{team_id}"

def get_json(url, params=None):
    r = requests.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def utc_ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

def safe_get(d, path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

def main():
    try:
        teams_payload = get_json(TEAMS_URL)
    except Exception as e:
        payload = {"timestamp": utc_ts(), "count": 0, "data": [], "error": str(e)}
        with open(OUTFILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"❌ Failed to fetch teams: {e}")
        return

    # ESPN structure: sports -> leagues -> teams (varies). We'll scan.
    teams = []
    for block in teams_payload.get("sports", []):
        for league in block.get("leagues", []):
            for t in league.get("teams", []):
                team_obj = t.get("team", t)
                tid = team_obj.get("id")
                if tid:
                    teams.append({"id": tid, "name": team_obj.get("displayName")})

    seen = set()
    out = []
    errors = []

    for t in teams:
        tid = t["id"]
        if tid in seen:
            continue
        seen.add(tid)

        try:
            team_payload = get_json(TEAM_URL_TMPL.format(team_id=tid))
            team_name = safe_get(team_payload, ["team", "displayName"], t.get("name"))
            venue = safe_get(team_payload, ["team", "venue"], {}) or {}

            venue_name = venue.get("fullName") or venue.get("name")
            address = venue.get("address", {}) or {}
            city = address.get("city")
            state = address.get("state")
            country = address.get("country")

            geo = venue.get("geoCoordinates") or venue.get("location") or {}
            lat = geo.get("latitude")
            lon = geo.get("longitude")

            indoor = bool(venue.get("indoor", False))

            if venue_name and lat is not None and lon is not None:
                out.append({
                    "team_id": tid,
                    "team_name": team_name,
                    "venue_name": venue_name,
                    "city": city,
                    "state": state,
                    "country": country,
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "capacity": venue.get("capacity"),
                    "indoor": indoor,
                    "source": "espn-site-api"
                })
            else:
                errors.append({
                    "team_id": tid,
                    "team_name": team_name,
                    "reason": "missing venue_name or lat/lon"
                })

        except Exception as e:
            errors.append({"team_id": tid, "team_name": t.get("name"), "reason": str(e)})

    payload = {
        "timestamp": utc_ts(),
        "count": len(out),
        "data": sorted(out, key=lambda x: (x.get("team_name") or "")),
        "errors": errors or None
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {OUTFILE} with {len(out)} FBS stadiums")

if __name__ == "__main__":
    main()
