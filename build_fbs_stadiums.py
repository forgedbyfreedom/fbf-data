#!/usr/bin/env python3
"""
build_fbs_stadiums.py

Builds a full FBS stadium list automatically from ESPN Core API.
Output: fbs_stadiums.json

- Pulls all FBS teams (NCAAF FBS)
- Resolves each team's venue, gps, capacity, etc.
- Classifies indoor/outdoor:
    * If ESPN flags "isIndoor"/roofType -> trust it
    * Else uses a small known-dome override list
    * Else defaults to outdoor

Safe if ESPN is down; writes empty file with note.

No API keys required.
"""

import json, os, sys
from datetime import datetime, timezone
import requests

OUTFILE = "fbs_stadiums.json"
TIMEOUT = 15

FBS_TEAMS_URL = (
    "https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/"
    "seasons/2025/types/2/groups/80/teams?limit=400"
)

# Known FBS indoor / dome venues (failsafe if ESPN doesn't expose roofType)
KNOWN_INDOOR_VENUES = {
    "carrier dome", "jma wireless dome", "allegiant stadium", "ford field",
    "lucas oil stadium", "mercedes-benz stadium", "at&t stadium",
    "nrg stadium", "caesars superdome", "u.s. bank stadium",
    "boa stadium (indoor)", "tropicana field", "astrodome",
}

def get_json(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def load_items(url):
    data = get_json(url)
    return data.get("items", [])

def safe_ref(ref):
    if isinstance(ref, dict) and "$ref" in ref:
        return ref["$ref"]
    return None

def to_bool(v):
    return True if str(v).lower() == "true" else False if str(v).lower() == "false" else None

def classify_indoor(venue):
    """Best-effort indoor/outdoor classification."""
    # ESPN sometimes provides "isIndoor"
    if "isIndoor" in venue:
        b = to_bool(venue.get("isIndoor"))
        if b is not None:
            return b

    # Sometimes provides roofType
    roof = (venue.get("roofType") or venue.get("roof") or "").lower()
    if roof in {"dome", "indoor", "closed"}:
        return True
    if roof in {"open", "outdoor"}:
        return False

    name = (venue.get("fullName") or venue.get("name") or "").lower()
    if name in KNOWN_INDOOR_VENUES:
        return True

    return False  # default outdoor

def main():
    out = []
    errors = []

    try:
        teams_items = load_items(FBS_TEAMS_URL)
        if not teams_items:
            raise ValueError("No teams returned from ESPN FBS endpoint")

        for t_ref in teams_items:
            t_url = safe_ref(t_ref)
            if not t_url:
                continue

            try:
                team = get_json(t_url)
                team_name = team.get("displayName") or team.get("name")
                team_id = team.get("id")

                venue_ref = safe_ref(team.get("venue"))
                if not venue_ref:
                    errors.append({"team": team_name, "reason": "no venue ref"})
                    continue

                venue = get_json(venue_ref)

                addr = venue.get("address", {}) or {}
                geo = venue.get("location", {}) or {}
                lat = geo.get("latitude")
                lon = geo.get("longitude")

                if lat is None or lon is None:
                    # sometimes embedded in venue["address"]["coordinates"]
                    coords = addr.get("coordinates", {}) or {}
                    lat = lat or coords.get("latitude")
                    lon = lon or coords.get("longitude")

                if lat is None or lon is None:
                    errors.append({"team": team_name, "reason": "no gps"})
                    continue

                indoor = classify_indoor(venue)

                out.append({
                    "team_id": team_id,
                    "team_name": team_name,
                    "abbrev": team.get("abbreviation"),
                    "conference": (team.get("groups", {}) or {}).get("shortName"),
                    "venue_id": venue.get("id"),
                    "venue_name": venue.get("fullName") or venue.get("name"),
                    "city": addr.get("city"),
                    "state": addr.get("state"),
                    "country": addr.get("country"),
                    "capacity": venue.get("capacity"),
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "indoor": bool(indoor),
                    "source": "espn-core",
                })

            except Exception as e:
                errors.append({"team_ref": t_url, "reason": str(e)})
                continue

    except Exception as e:
        payload = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
            "count": 0,
            "data": [],
            "errors": [{"fatal": str(e)}],
            "note": "Failed to build stadium list from ESPN",
        }
        with open(OUTFILE, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"❌ {OUTFILE} written empty: {e}")
        return

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "count": len(out),
        "data": sorted(out, key=lambda x: (x["team_name"] or "")),
        "errors": errors or None,
    }

    with open(OUTFILE, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"✅ Wrote {OUTFILE} with {len(out)} FBS venues")

if __name__ == "__main__":
    main()
