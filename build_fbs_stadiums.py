#!/usr/bin/env python3
import json
import re
import requests
from pathlib import Path

COMBINED = Path("combined.json")
MASTER = Path("stadiums_master.json")
OUTDOOR = Path("stadiums_outdoor.json")
FBS = Path("fbs_stadiums.json")

GEOCODER = "https://nominatim.openstreetmap.org/search"


def load_json(path, default=None):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def normalize(name):
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(r"[^a-z0-9 ]+", "", n)
    n = re.sub(r"\s+", " ", n)
    return n


def geocode(city, state):
    """Basic geocoder to fill missing lat/lon."""
    try:
        q = f"{city}, {state}, USA"
        params = {"q": q, "format": "json", "limit": 1}
        r = requests.get(GEOCODER, params=params, timeout=10)
        if r.status_code == 200:
            arr = r.json()
            if arr:
                return float(arr[0]["lat"]), float(arr[0]["lon"])
    except:
        pass
    return None, None


def extract_venues(combined):
    venues = {}
    missing_coords = []

    for g in combined.get("data", []):
        v = g.get("venue")
        if not isinstance(v, dict):
            continue

        name = v.get("name")
        if not name:
            continue

        key = normalize(name)
        if key not in venues:
            venues[key] = {
                "name": name,
                "norm": key,
                "city": v.get("city"),
                "state": v.get("state"),
                "indoor": v.get("indoor", False),
                "grass": v.get("grass"),
                "lat": v.get("lat"),
                "lon": v.get("lon"),
            }

        # Track missing coordinates
        if venues[key]["lat"] is None or venues[key]["lon"] is None:
            missing_coords.append(key)

    # Fill missing lat/lon
    filled = 0
    for key in missing_coords:
        city = venues[key]["city"]
        state = venues[key]["state"]
        if not city or not state:
            continue

        lat, lon = geocode(city, state)
        if lat and lon:
            venues[key]["lat"] = lat
            venues[key]["lon"] = lon
            filled += 1

    print(f"🔥 Geocoder filled {filled} missing venues.")
    return venues


def main():
    combined = load_json(COMBINED, {})
    if not combined:
        print("❌ combined.json missing")
        return

    venues = extract_venues(combined)

    # Save master
    save_json(MASTER, venues)
    print(f"🎉 stadiums_master.json written: {len(venues)} venues")

    # Outdoor stadiums only
    outdoor = {k: v for k, v in venues.items() if not v.get("indoor")}
    save_json(OUTDOOR, outdoor)
    print(f"🎉 stadiums_outdoor.json written: {len(outdoor)} outdoor venues")

    # FBS subset (city+state heuristic)
    fbs = {k: v for k, v in venues.items() if v.get("state") in ["AL","GA","FL","TX","CA","NC","SC","TN","KY","LA","MS","AR","VA","WV","PA","OH","MI","IN","IL","MO","OK","NE","KS","IA","WI","MN","CO","AZ","WA","OR","UT","ID","NM","NV","MA","CT","NY","NJ","MD"]}
    save_json(FBS, fbs)
    print(f"🎉 fbs_stadiums.json written: {len(fbs)} FBS venues")


if __name__ == "__main__":
    main()
