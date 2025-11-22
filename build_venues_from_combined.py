#!/usr/bin/env python3
"""
build_venues_from_combined.py

Creates venues.json by:
1) reading combined.json
2) pulling unique (sport_key, home_team)
3) querying Wikidata (WDQS SPARQL) for home venue + coordinates
4) adding timezone via tz-lookup fallback rule (rough but works)

No API keys required.

Output:
  venues.json
"""

import json, time, requests, re
from pathlib import Path
from datetime import datetime, timezone

COMBINED_PATH = Path("combined.json")
OUT_PATH = Path("venues.json")
WDQS_URL = "https://query.wikidata.org/sparql"
HEADERS = {"Accept": "application/sparql-results+json", "User-Agent": "fbf-data-bot/1.0"}

# --- very small timezone heuristic by longitude (good enough for US leagues)
# If you want perfect tz, swap this with a tz-lookup library or API later.
def rough_timezone(lat, lon):
    if lon is None:
        return None
    # US timezones approx
    if lon < -125: return "America/Anchorage"
    if lon < -115: return "America/Los_Angeles"
    if lon < -100: return "America/Denver"
    if lon < -85:  return "America/Chicago"
    return "America/New_York"

def safe_get(d, *keys):
    cur = d
    for k in keys:
        if not isinstance(cur, dict): return None
        cur = cur.get(k)
    return cur

def wdqs_team_home_venue(team_name):
    """
    SPARQL strategy:
    - find an entity with label == team_name (en)
    - try home venue properties:
        P115 (home venue), P131 (located in?), P276 (location)
    - take coordinate P625 from venue.
    """
    team_escaped = team_name.replace('"', '\\"')

    query = f"""
    SELECT ?team ?teamLabel ?venue ?venueLabel ?coord WHERE {{
      ?team rdfs:label "{team_escaped}"@en .
      OPTIONAL {{ ?team wdt:P115 ?venue . }}   # home venue
      OPTIONAL {{ ?team wdt:P131 ?venue . }}   # located in (fallback)
      OPTIONAL {{ ?team wdt:P276 ?venue . }}   # location (fallback)

      FILTER(BOUND(?venue))
      OPTIONAL {{ ?venue wdt:P625 ?coord . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 5
    """

    r = requests.get(WDQS_URL, params={"query": query}, headers=HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    bindings = data.get("results", {}).get("bindings", [])
    if not bindings:
        return None

    # pick first with coord if possible
    for b in bindings:
        coord = safe_get(b, "coord", "value")
        venue_label = safe_get(b, "venueLabel", "value")
        if coord and venue_label:
            latlon = parse_wkt_point(coord)
            if latlon:
                lat, lon = latlon
                return {"venue_name": venue_label, "lat": lat, "lon": lon}

    # otherwise return first venue label
    b0 = bindings[0]
    venue_label = safe_get(b0, "venueLabel", "value")
    return {"venue_name": venue_label, "lat": None, "lon": None}

def parse_wkt_point(wkt):
    # expects "Point(lon lat)"
    if not wkt: return None
    m = re.search(r"Point\(([-\d\.]+)\s+([-\d\.]+)\)", wkt)
    if not m: return None
    lon = float(m.group(1))
    lat = float(m.group(2))
    return lat, lon

def main():
    if not COMBINED_PATH.exists():
        raise SystemExit("combined.json not found")

    combined = json.loads(COMBINED_PATH.read_text())
    games = combined.get("data", [])

    pairs = {}
    for g in games:
        sport_key = g.get("sport_key")
        home = g.get("home_team")
        if sport_key and home:
            pairs[(sport_key, home)] = True

    venues = {}
    for (sport_key, home_team) in pairs.keys():
        if home_team in venues:
            continue

        try:
            print(f"[WDQS] {home_team} ...")
            info = wdqs_team_home_venue(home_team)
            if not info:
                venues[home_team] = {
                    "venue_name": None, "lat": None, "lon": None,
                    "tz": None, "sport_key": sport_key,
                    "source": "wikidata-miss"
                }
                continue

            lat, lon = info.get("lat"), info.get("lon")
            tz = rough_timezone(lat, lon)

            venues[home_team] = {
                "venue_name": info.get("venue_name"),
                "lat": lat, "lon": lon,
                "tz": tz,
                "sport_key": sport_key,
                "source": "wikidata"
            }

            # be nice to WDQS
            time.sleep(0.2)

        except Exception as e:
            venues[home_team] = {
                "venue_name": None, "lat": None, "lon": None,
                "tz": None, "sport_key": sport_key,
                "source": f"error:{e}"
            }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(venues),
        "venues": venues
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"[✅] Wrote {OUT_PATH} with {len(venues)} venues.")

if __name__ == "__main__":
    main()
