#!/usr/bin/env python3
import json
import re
from pathlib import Path

COMBINED = Path("combined.json")
MASTER = Path("stadiums_master.json")
OUTFILE = Path("combined.json")
GEO_CACHE = Path("geo_cache.json")        # written by fetch_weather.py, keyed "city|STATE"
TEAM_VENUES = Path("team_venues.json")    # team -> home venue, accumulated across runs


def load_json(path, default=None):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default


def normalize(name):
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(r"[^a-z0-9 ]+", "", n)
    n = re.sub(r"\s+", " ", n)
    return n


def team_key(name):
    """Key format for team_venues.json.

    Must match merge_features.normalize() exactly, which strips spaces as well
    as punctuation. This module's own normalize() KEEPS spaces (it is used for
    venue-name matching against stadiums_master), so writing team keys with it
    produced "alabama crimson tide" while the consumer looked up
    "alabamacrimsontide" - and travel_km stayed 0 on every game even after 69
    of 80 teams had coordinates. Same class of bug as the one this file was
    written to fix.
    """
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def find_match(venue, master):
    """Match by name normalization."""
    name = venue.get("name")
    if not name:
        return None

    key = normalize(name)
    return master.get(key)


def coords_from_geo_cache(venue, geo):
    """Fall back to the persisted geocode cache when the venue is not in master."""
    city = (venue.get("city") or "").strip().lower()
    state = (venue.get("state") or "").strip().upper()
    if not city or not state:
        return None
    hit = geo.get(f"{city}|{state}")
    if isinstance(hit, list) and len(hit) == 2:
        return hit[0], hit[1]
    return None


def main():
    combined = load_json(COMBINED, {})
    master = load_json(MASTER, {})
    geo = load_json(str(GEO_CACHE), {}) or {}
    team_venues = load_json(str(TEAM_VENUES), {}) or {}
    # Re-key anything stored under the old space-separated format.
    team_venues = {team_key(k): v for k, v in team_venues.items()}

    if not combined or "data" not in combined:
        print("❌ combined.json missing or invalid")
        return

    updated = 0

    for g in combined["data"]:
        venue = g.get("venue")
        if not isinstance(venue, dict):
            continue

        match = find_match(venue, master)
        if not match:
            continue

        # Inject coordinates
        if "lat" in match and venue.get("lat") is None:
            venue["lat"] = match["lat"]
            updated += 1

        if "lon" in match and venue.get("lon") is None:
            venue["lon"] = match["lon"]

    # Second pass: anything still missing coordinates, fill from the persisted
    # geocode cache. stadiums_master only carries 20 of 75 venues with
    # coordinates, which is why weather reached just 53 of 81 games.
    from_cache = 0
    for g in combined["data"]:
        venue = g.get("venue")
        if not isinstance(venue, dict) or venue.get("lat") is not None:
            continue
        hit = coords_from_geo_cache(venue, geo)
        if hit:
            venue["lat"], venue["lon"] = hit
            from_cache += 1

    # Record each team's home venue. Travel distance needs to know where the
    # AWAY side normally plays, and nothing in the repo held that: merge_features
    # was looking up team names in a dictionary keyed by stadium names, so
    # travel_km was 0 on every game ever scored. Accumulated across runs so it
    # fills in as the season goes.
    learned = 0
    for g in combined["data"]:
        if g.get("neutral_site"):
            continue
        venue = g.get("venue") or {}
        home = g.get("home_team") or {}
        name = home.get("name") if isinstance(home, dict) else None
        if not name or not venue.get("name"):
            continue
        key = team_key(name)
        entry = {"venue": venue.get("name"), "city": venue.get("city"),
                 "state": venue.get("state")}
        if venue.get("lat") is not None:
            entry["lat"] = venue.get("lat")
            entry["lon"] = venue.get("lon")
        prev = team_venues.get(key) or {}
        # keep coordinates we already learned if this record lacks them
        if "lat" not in entry and "lat" in prev:
            entry["lat"], entry["lon"] = prev["lat"], prev["lon"]
        if prev != entry:
            learned += 1
        team_venues[key] = entry

    with open(TEAM_VENUES, "w") as f:
        json.dump(team_venues, f, indent=2, sort_keys=True)
    print(f"🏟  team home venues known: {len(team_venues)} ({learned} updated this run, "
          f"{sum(1 for v in team_venues.values() if v.get('lat') is not None)} with coordinates)")
    print(f"📍 filled {from_cache} venue coordinates from the geocode cache")

    with open(OUTFILE, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"📌 Updated combined.json with coordinates for {updated} venues.")


if __name__ == "__main__":
    main()
