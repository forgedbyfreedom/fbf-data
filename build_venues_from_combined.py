#!/usr/bin/env python3
"""
build_venues_from_combined.py

Reads combined.json, extracts UNIQUE home teams,
queries Wikidata for each team’s home venue + GPS coords,
and classifies venue_type as:
  - "outdoor"
  - "indoor"
  - "retractable"

Rule B for retractable is applied downstream in weather script
(assume indoor unless open status is verified).

Output:
  venues.json

Structure:
{
  "timestamp": "...",
  "venues": {
     "Team Name": {
        "venue": "Stadium Name",
        "lat": 00.0000,
        "lon": -00.0000,
        "venue_type": "outdoor|indoor|retractable",
        "source": "wikidata",
        "wikidata_team_qid": "Q....",
        "wikidata_venue_qid": "Q....",
        "updated_at": "..."
     },
     ...
  },
  "misses": ["Team no match", ...]
}
"""

import json
import os
import re
import time
import requests
from datetime import datetime, timezone

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
HEADERS = {
    "Accept": "application/sparql+json",
    "User-Agent": "fbf-venues-bot/1.0 (forgedbyfreedom)"
}
TIMEOUT = 18

OUTFILE = "venues.json"


INDOOR_KEYWORDS = [
    "dome", "indoor", "enclosed", "roofed", "covered stadium",
    "arena", "fieldhouse", "coliseum (indoor)", "ice arena"
]

RETRACTABLE_KEYWORDS = [
    "retractable", "convertible", "sliding roof", "movable roof",
    "retractable roof", "roof can open"
]


def safe_get(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def normalize_team_name(name: str) -> str:
    """Basic cleanup to help Wikidata matching."""
    if not name:
        return name
    name = name.strip()
    # remove rankings / seed patterns if they ever show up
    name = re.sub(r"^\#\d+\s+", "", name)
    name = re.sub(r"\s+\(\d+\)$", "", name)
    return name


def classify_venue_type(venue_label: str, venue_type_label: str, instance_label: str) -> str:
    """
    Determine outdoor/indoor/retractable using labels.
    If retractable keywords found => "retractable"
    Else if indoor keywords found => "indoor"
    Else => "outdoor"
    """
    blob = " ".join(filter(None, [venue_label, venue_type_label, instance_label])).lower()

    for kw in RETRACTABLE_KEYWORDS:
        if kw in blob:
            return "retractable"

    for kw in INDOOR_KEYWORDS:
        if kw in blob:
            return "indoor"

    return "outdoor"


def sparql_team_venue_query(team_label: str) -> str:
    """
    Try to find a team entity with exact English label.
    Get:
      - team QID
      - venue QID + label
      - coordinates (P625)
      - venue type (P2775) label
      - instance of (P31) label
    """
    return f"""
    SELECT ?team ?venue ?venueLabel ?coord ?venueTypeLabel ?instanceLabel WHERE {{
      ?team rdfs:label "{team_label}"@en .
      OPTIONAL {{ ?team wdt:P115 ?venue . }}           # home venue
      OPTIONAL {{ ?team wdt:P276 ?venue . }}           # location (fallback for some clubs)
      OPTIONAL {{ ?venue wdt:P625 ?coord . }}          # coordinates
      OPTIONAL {{ ?venue wdt:P2775 ?venueType . }}     # type of venue
      OPTIONAL {{ ?venue wdt:P31 ?instance . }}        # instance of
      SERVICE wikibase:label {{
        bd:serviceParam wikibase:language "en".
        ?venue rdfs:label ?venueLabel .
        ?venueType rdfs:label ?venueTypeLabel .
        ?instance rdfs:label ?instanceLabel .
      }}
    }}
    LIMIT 1
    """


def run_sparql(query: str):
    r = requests.get(
        WIKIDATA_SPARQL,
        params={"query": query, "format": "json"},
        headers=HEADERS,
        timeout=TIMEOUT
    )
    r.raise_for_status()
    return r.json()


def parse_coord(coord_str: str):
    """
    Wikidata coord format: "Point(-83.7487 42.2658)"
    Returns (lat, lon)
    """
    if not coord_str:
        return (None, None)
    m = re.search(r"Point\(([-\d\.]+)\s+([-\d\.]+)\)", coord_str)
    if not m:
        return (None, None)
    lon = float(m.group(1))
    lat = float(m.group(2))
    return (lat, lon)


def qid_from_uri(uri: str):
    if not uri:
        return None
    return uri.split("/")[-1]


def lookup_team_venue(team_name: str):
    query = sparql_team_venue_query(team_name)
    data = run_sparql(query)
    bindings = safe_get(data, "results", "bindings", default=[])
    if not bindings:
        return None

    b = bindings[0]
    team_uri = safe_get(b, "team", "value")
    venue_uri = safe_get(b, "venue", "value")
    venue_label = safe_get(b, "venueLabel", "value")
    coord_str = safe_get(b, "coord", "value")
    venue_type_label = safe_get(b, "venueTypeLabel", "value")
    instance_label = safe_get(b, "instanceLabel", "value")

    lat, lon = parse_coord(coord_str)

    venue_type = classify_venue_type(venue_label, venue_type_label, instance_label)

    return {
        "venue": venue_label,
        "lat": lat,
        "lon": lon,
        "venue_type": venue_type,
        "source": "wikidata",
        "wikidata_team_qid": qid_from_uri(team_uri),
        "wikidata_venue_qid": qid_from_uri(venue_uri),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }


def main():
    if not os.path.exists("combined.json"):
        raise SystemExit("❌ combined.json not found.")

    with open("combined.json", "r", encoding="utf-8") as f:
        combined = json.load(f)

    games = combined.get("data", [])
    home_teams = sorted({normalize_team_name(g.get("home_team")) for g in games if g.get("home_team")})

    venues = {}
    misses = []

    print(f"[🏟️] Looking up venues for {len(home_teams)} unique home teams...")

    for i, team in enumerate(home_teams, 1):
        try:
            print(f"  ({i}/{len(home_teams)}) {team} ...", end="", flush=True)
            rec = lookup_team_venue(team)
            if not rec or not rec.get("venue") or rec.get("lat") is None:
                print(" miss")
                misses.append(team)
                continue
            venues[team] = rec
            print(f" ok → {rec['venue']} ({rec['venue_type']})")
            time.sleep(0.4)  # be nice to Wikidata
        except Exception as e:
            print(f" error: {e}")
            misses.append(team)

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "venues": venues,
        "misses": misses
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"[✅] Saved {OUTFILE} with {len(venues)} venues, {len(misses)} misses.")


if __name__ == "__main__":
    main()
