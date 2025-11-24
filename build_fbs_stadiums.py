#!/usr/bin/env python3
import json
import requests
from pathlib import Path
from urllib.parse import quote

BASE = Path(__file__).resolve().parent

COMBINED_FILE = BASE / "combined.json"
MASTER_FILE = BASE / "stadiums_master.json"
OUTDOOR_FILE = BASE / "stadiums_outdoor.json"
FBS_FILE = BASE / "fbs_stadiums.json"

GEOCODE_URL = "https://nominatim.openstreetmap.org/search"

HEADERS = {
    "User-Agent": "ForgedByFreedomSportsBot/1.0"
}


def geocode(stadium_name, city, state):
    """Try to get lat/lon for stadium."""
    query = f"{stadium_name}, {city}, {state}, USA"
    try:
        url = f"{GEOCODE_URL}?q={quote(query)}&format=json&limit=1"
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except:
        pass
    return None, None


def load_combined():
    with open(COMBINED_FILE, "r") as f:
        return json.load(f)


def extract_venues(combined):
    """Extract every venue from combined.json."""
    venues = {}

    for g in combined.get("data", []):
        v = g.get("venue")
        if not v:
            continue

        name = v.get("name", "").strip()
        city = v.get("city", "").strip()
        state = v.get("state", "").strip()
        indoor = v.get("indoor", False)
        grass = v.get("grass", False)

        if not name or not city or not state:
            continue

        key = f"{name.lower()}|{city.lower()}|{state.lower()}"

        venues[key] = {
            "name": name,
            "city": city,
            "state": state,
            "indoor": indoor,
            "grass": grass,
            "lat": v.get("lat"),
            "lon": v.get("lon"),
            "source": "combined_espn"
        }

    return venues


def fill_missing_coords(venues):
    """Fill lat/lon using geocoder."""
    filled = 0
    for key, v in venues.items():
        if not v.get("lat") or not v.get("lon"):
            lat, lon = geocode(v["name"], v["city"], v["state"])
            if lat and lon:
                v["lat"] = lat
                v["lon"] = lon
                filled += 1
    return filled


def get_fbs_locations(combined):
    """Return set of (city, state) for every NCAAF game venue."""
    locs = set()

    for g in combined.get("data", []):
        if g.get("sport") != "ncaaf":
            continue

        v = g.get("venue", {})
        city = v.get("city")
        state = v.get("state")

        if city and state:
            locs.add((city.lower(), state.lower()))

    return locs


def build_outdoor(venues):
    """Outdoor = NOT indoor AND has coordinates."""
    outdoor = {}
    for k, v in venues.items():
        if not v.get("indoor") and v.get("lat") and v.get("lon"):
            outdoor[k] = v
    return outdoor


def build_fbs(outdoor, fbs_locations):
    """FBS venues = outdoor stadiums located in real NCAA FBS city/states."""
    fbs = {}
    for k, v in outdoor.items():
        city = v["city"].lower()
        state = v["state"].lower()

        if (city, state) in fbs_locations:
            fbs[k] = v
    return fbs


def main():
    print("🔍 Extracting venues from combined.json ...")
    combined = load_combined()

    venues = extract_venues(combined)

    # Fill missing coordinates
    print("🌎 Geocoding missing coordinates (fallback)...")
    filled = fill_missing_coords(venues)

    print(f"🔥 Geocoder filled {filled} missing venues.")

    # Build outdoor stadiums
    outdoor = build_outdoor(venues)

    # Build FBS stadiums (correct)
    fbs_locations = get_fbs_locations(combined)
    fbs = build_fbs(outdoor, fbs_locations)

    # Write output files
    with open(MASTER_FILE, "w") as f:
        json.dump(venues, f, indent=2)
    print(f"🎉 stadiums_master.json written: {len(venues)} venues")

    with open(OUTDOOR_FILE, "w") as f:
        json.dump(outdoor, f, indent=2)
    print(f"🎉 stadiums_outdoor.json written: {len(outdoor)} outdoor venues")

    with open(FBS_FILE, "w") as f:
        json.dump(fbs, f, indent=2)
    print(f"🎉 fbs_stadiums.json written: {len(fbs)} FBS venues")


if __name__ == "__main__":
    main()
