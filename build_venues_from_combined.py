#!/usr/bin/env python3
import json
import re
import time
import requests
from pathlib import Path

COMBINED_PATH = Path("combined.json")
MASTER_PATH = Path("stadiums_master.json")
OUTDOOR_PATH = Path("stadiums_outdoor.json")
FBS_PATH = Path("fbs_stadiums.json")

GEOCODER = "https://nominatim.openstreetmap.org/search"

HEADERS = {
    "User-Agent": "fbf-weather/1.0"
}

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)

def normalize_name(name):
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(r"\s+", " ", n)
    for word in ["stadium", "field", "arena", "centre", "center", "coliseum", "dome", "the"]:
        n = n.replace(word, "")
    n = re.sub(r"[^a-z0-9 ]+", "", n)
    return n.strip()

def geocode(venue_name, city, state):
    """ Lookup missing lat/lon via OpenStreetMap """
    q = f"{venue_name}, {city}, {state}"
    params = {"q": q, "format": "json", "limit": 1}

    try:
        r = requests.get(GEOCODER, params=params, headers=HEADERS, timeout=10)
        if r.status_code == 200 and len(r.json()) > 0:
            d = r.json()[0]
            return float(d["lat"]), float(d["lon"])
    except:
        return None, None
    return None, None

def extract_coords(venue):
    """ Try all known ESPN formats """
    for key_lat, key_lon in [
        ("lat", "lon"),
        ("latitude", "longitude"),
        ("y", "x")
    ]:
        if venue.get(key_lat) and venue.get(key_lon):
            try:
                return float(venue[key_lat]), float(venue[key_lon])
            except:
                pass
    return None, None

def main():
    combined = load_json(COMBINED_PATH, {})
    if not combined or "data" not in combined:
        print("❌ combined.json missing or invalid")
        return

    games = combined["data"]
    master = {}
    outdoor = {}
    fbs = {}

    print("🔍 Extracting venues from combined.json ...")

    for g in games:
        if not isinstance(g, dict):
            continue

        v = g.get("venue") or {}
        if not isinstance(v, dict):
            continue

        name = v.get("name")
        if not name:
            continue

        city = v.get("city", "")
        state = v.get("state", "")
        indoor = bool(v.get("indoor"))
        grass = v.get("grass")
        vid = v.get("id") or v.get("venue_id") or normalize_name(name)

        lat, lon = extract_coords(v)

        if vid not in master:
            master[vid] = {
                "id": vid,
                "name": name,
                "norm": normalize_name(name),
                "city": city,
                "state": state,
                "indoor": indoor,
                "grass": grass,
            }

        if lat and lon:
            master[vid]["lat"] = lat
            master[vid]["lon"] = lon

    # Missing lat/lon → geocode
    print("🌎 Geocoding missing coordinates (fallback)...")
    geocode_count = 0

    for vid, v in master.items():
        if "lat" not in v or "lon" not in v:
            lat, lon = geocode(v["name"], v["city"], v["state"])
            if lat and lon:
                v["lat"] = lat
                v["lon"] = lon
                geocode_count += 1
                time.sleep(1)  # avoid rate limits

    print(f"🔥 Geocoder filled {geocode_count} missing venues.")

    # Write master
    save_json(MASTER_PATH, master)
    print(f"🎉 stadiums_master.json written: {len(master)} venues")

    # Outdoor filter
    for vid, v in master.items():
        if not v.get("indoor"):
            outdoor[vid] = v

    save_json(OUTDOOR_PATH, outdoor)
    print(f"🎉 stadiums_outdoor.json written: {len(outdoor)} outdoor venues")

    # FBS stadiums
    for g in games:
        if g.get("sport") == "ncaaf":
            v = g.get("venue")
            if isinstance(v, dict):
                vid = v.get("id") or normalize_name(v.get("name", ""))
                if vid in master:
                    fbs[vid] = master[vid]

    save_json(FBS_PATH, fbs)
    print(f"🎉 fbs_stadiums.json written: {len(fbs)} FBS venues")

    # Inject lat/lon back into combined.json
    updated = 0
    for g in games:
        v = g.get("venue")
        if not isinstance(v, dict):
            continue

        vid = v.get("id") or normalize_name(v.get("name", ""))
        m = master.get(vid)

        if m and "lat" in m and "lon" in m:
            v["lat"] = m["lat"]
            v["lon"] = m["lon"]
            updated += 1

    save_json(COMBINED_PATH, combined)
    print(f"📌 Updated combined.json with coordinates for {updated} games.")

if __name__ == "__main__":
    main()
