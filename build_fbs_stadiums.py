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
HEADERS = {"User-Agent": "fbf-stadium-geocoder/1.0 (forgedbyfreedom.org)"}


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def normalize(name: str) -> str:
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(r"[^a-z0-9 ]+", "", n)
    n = re.sub(r"\s+", " ", n)
    return n


def geocode(city: str, state: str):
    """Basic geocoder to fill missing lat/lon."""
    if not city or not state:
        return None, None

    try:
        q = f"{city}, {state}, USA"
        params = {"q": q, "format": "json", "limit": 1}
        r = requests.get(GEOCODER, params=params, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            arr = r.json()
            if arr:
                return float(arr[0]["lat"]), float(arr[0]["lon"])
    except Exception:
        pass
    return None, None


def extract_venues(combined):
    venues = {}
    missing_coords_keys = []

    for g in combined.get("data", []):
        if not isinstance(g, dict):
            continue

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
                "indoor": bool(v.get("indoor", False)),
                "grass": v.get("grass"),
                "lat": v.get("lat"),
                "lon": v.get("lon"),
            }

        if venues[key]["lat"] is None or venues[key]["lon"] is None:
            missing_coords_keys.append(key)

    filled = 0
    for key in missing_coords_keys:
        city = venues[key]["city"]
        state = venues[key]["state"]
        lat, lon = geocode(city, state)
        if lat is not None and lon is not None:
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

    save_json(MASTER, venues)
    print(f"🎉 stadiums_master.json written: {len(venues)} venues")

    outdoor = {k: v for k, v in venues.items() if not v.get("indoor")}
    save_json(OUTDOOR, outdoor)
    print(f"🎉 stadiums_outdoor.json written: {len(outdoor)} outdoor venues")

    fbs_states = {
        "AL","GA","FL","TX","CA","NC","SC","TN","KY","LA","MS","AR","VA","WV","PA",
        "OH","MI","IN","IL","MO","OK","NE","KS","IA","WI","MN","CO","AZ","WA","OR",
        "UT","ID","NM","NV","MA","CT","NY","NJ","MD"
    }
    fbs = {k: v for k, v in venues.items() if v.get("state") in fbs_states}
    save_json(FBS, fbs)
    print(f"🎉 fbs_stadiums.json written: {len(fbs)} FBS venues")


if __name__ == "__main__":
    main()
