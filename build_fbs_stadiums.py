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
    """Try to geocode a stadium using OpenStreetMap."""
    query = f"{stadium_name}, {city}, {state}, USA"
    try:
        url = f"{GEOCODE_URL}?q={quote(query)}&format=json&limit=1"
        r = requests.get(url, headers=HEADERS, timeout=15)
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
    """Extract all venues from combined.json (all sports)."""
    venues = {}

    for g in combined.get("data", []):
        v = g.get("venue") or {}   # <-- SAFE: protects against null

        name = v.get("name", "").strip()
        city = v.get("city", "").strip()
        state = v.get("state", "").strip()
        indoor = bool(v.get("indoor", False))
        grass = bool(v.get("grass", False))

        if not name or not city or not state:
            continue  # skip incomplete venue info

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
    """Geocode stadiums missing lat/lon."""
    filled = 0
    for k, v in venues.items():
        if not v.get("lat") or not v.get("lon"):
            lat, lon = geocode(v["name"], v["city"], v["state"])
            if lat and lon:
                v["lat"] = lat
                v["lon"] = lon
                filled += 1
    return filled


def get_fbs_locations(combined):
    """Return all (city, state) pairs for NCAAF game venues."""
    locs = set()

    for g in combined.get("data", []):
        if g.get("sport") != "ncaaf":
            continue

        v = g.get("venue") or {}   # <-- FIXED: prevents crash on `None`

        city = v.get("city")
        state = v.get("state")

        if city and state:
            locs.add((city.lower(), state.lower()))

    return locs


def build_outdoor(venues):
    """Outdoor = NOT indoor + has lat/lon."""
    outdoor = {}
    for key, v in venues.items():
        if not v.get("indoor") and v.get("lat") and v.get("lon"):
            outdoor[key] = v
    return outdoor


def build_fbs(outdoor, fbs_locations):
    """FBS stadiums = outdoor stadiums in NCAAF city/state pairs."""
    fbs = {}
    for key, v in outdoor.items():
        loc = (v["city"].lower(), v["state"].lower())
        if loc in fbs_locations:
            fbs[key] = v
    return fbs


def main():
    print("🔍 Extracting venues from combined.json ...")
    combined = load_combined()

    venues = extract_venues(combined)

    print("🌎 Geocoding missing coordinates (fallback)...")
    filled = fill_missing_coords(venues)
    print(f"🔥 Geocoder filled {filled} missing venues.")

    outdoor = build_outdoor(venues)
    fbs_locations = get_fbs_locations(combined)
    fbs = build_fbs(outdoor, fbs_locations)

    # Write JSON outputs
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
