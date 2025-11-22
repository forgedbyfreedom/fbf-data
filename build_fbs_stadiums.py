#!/usr/bin/env python3
"""
build_fbs_stadiums.py

Builds a full FBS stadium list from ESPN Core API.
Outputs fbs_stadiums.json with:
- team_name
- venue_name
- latitude / longitude
- indoor (True/False)

Safe on API failures.
"""

import json, os, re
from datetime import datetime, timezone
import requests

TIMEOUT = 12
OUTFILE = "fbs_stadiums.json"

CF_TEAMS_URL = "https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/teams?limit=400"

INDOOR_KEYWORDS = [
    "dome", "indoor", "covered", "stadium at the dome",
    "superdome", "allegiant", "mercedes-benz stadium"
]

# Extra known indoor/roofed venues (best-effort)
KNOWN_INDOOR = {
    "carrier dome",
    "allegiant stadium",
    "mercedes-benz stadium",
    "caesars superdome",
    "at&t stadium",
    "ford field",
    "u.s. bank stadium",
    "lucas oil stadium",
    "state farm stadium",
}

def get_json(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def safe(o, path, default=None):
    cur = o
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur

def is_indoor(venue_name: str) -> bool:
    vn = (venue_name or "").lower()
    if vn in KNOWN_INDOOR:
        return True
    for kw in INDOOR_KEYWORDS:
        if kw in vn:
            return True
    return False

def main():
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    out = []
    errors = []

    try:
        teams_list = get_json(CF_TEAMS_URL).get("items", [])
    except Exception as e:
        payload = {"timestamp": ts, "data": [], "errors": [str(e)]}
        with open(OUTFILE, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"⚠️ Wrote empty {OUTFILE} (teams fetch failed)")
        return

    for t in teams_list:
        ref = t.get("$ref")
        if not ref:
            continue
        try:
            team = get_json(ref)
            team_name = safe(team, ["displayName"], "") or safe(team, ["name"], "")
            venue_ref = safe(team, ["venue", "$ref"], None)
            if not venue_ref:
                continue
            venue = get_json(venue_ref)
            venue_name = venue.get("fullName") or venue.get("name") or ""
            lat = venue.get("address", {}).get("latitude")
            lon = venue.get("address", {}).get("longitude")

            if lat is None or lon is None:
                # sometimes nested differently
                lat = venue.get("location", {}).get("latitude")
                lon = venue.get("location", {}).get("longitude")

            if lat is None or lon is None:
                errors.append({"team": team_name, "reason": "missing lat/lon"})
                continue

            out.append({
                "team_name": team_name,
                "venue_name": venue_name,
                "latitude": float(lat),
                "longitude": float(lon),
                "indoor": is_indoor(venue_name),
                "source": "espn-core",
            })
        except Exception as e:
            errors.append({"team_ref": ref, "reason": str(e)})

    payload = {
        "timestamp": ts,
        "count": len(out),
        "data": out,
        "errors": errors or None
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {OUTFILE} with {len(out)} FBS venues")

if __name__ == "__main__":
    main()
