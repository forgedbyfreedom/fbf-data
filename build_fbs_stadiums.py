import json
import time
import requests
from pathlib import Path

COMBINED_PATH = "combined.json"
OUT_PATH = "fbs_stadiums.json"
OUTDOOR_PATH = "stadiums_outdoor.json"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
UA = "fbf-data (contact@forgedbyfreedom.com)"

POWER5_HINTS = [
    "SEC", "BIG TEN", "BIG 12", "ACC", "PAC", "PAC-12", "PAC-10"
]

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)

def norm(s):
    return (s or "").strip()

def geocode_osm(query):
    try:
        params = {"q": query, "format": "json", "limit": 1}
        r = requests.get(NOMINATIM_URL, params=params, headers={"User-Agent": UA}, timeout=20)
        if not r.ok:
            return None
        data = r.json()
        if not data:
            return None
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return {"lat": lat, "lon": lon, "source": "osm"}
    except:
        return None

def extract_games():
    games = load_json(COMBINED_PATH, [])
    if isinstance(games, dict) and "data" in games:
        games = games["data"]
    return [g for g in games if isinstance(g, dict)]

def main():
    games = extract_games()

    # Existing cache (so we only geocode once)
    cache = load_json(OUT_PATH, {})

    stadiums = dict(cache)  # clone

    created = 0
    geocoded = 0

    for g in games:
        sport = (g.get("sport") or "").lower()
        if sport != "ncaaf":
            continue

        venue = g.get("venue") or {}
        vname = norm(venue.get("name"))
        city  = norm(venue.get("city"))
        state = norm(venue.get("state"))

        if not vname:
            continue

        key = vname.lower()

        if key not in stadiums:
            stadiums[key] = {
                "name": vname,
                "city": city,
                "state": state,
                "lat": None,
                "lon": None,
                "indoor": bool(venue.get("indoor")),
                "grass": bool(venue.get("grass")),
                "source": "espn"
            }
            created += 1

        # If ESPN already gives coords, take them
        espn_lat = venue.get("latitude") or venue.get("lat")
        espn_lon = venue.get("longitude") or venue.get("lon")
        if espn_lat and espn_lon:
            stadiums[key]["lat"] = float(espn_lat)
            stadiums[key]["lon"] = float(espn_lon)
            stadiums[key]["source"] = "espn_coords"
            stadiums[key]["city"] = stadiums[key]["city"] or city
            stadiums[key]["state"] = stadiums[key]["state"] or state
            continue

        # If missing coords, try cached first
        if stadiums[key].get("lat") and stadiums[key].get("lon"):
            continue

        # OSM geocode once per missing stadium
        q = vname
        if city or state:
            q = f"{vname}, {city} {state}".strip()

        geo = geocode_osm(q)
        if geo:
            stadiums[key]["lat"] = geo["lat"]
            stadiums[key]["lon"] = geo["lon"]
            stadiums[key]["source"] = "osm"
            stadiums[key]["city"] = stadiums[key]["city"] or city
            stadiums[key]["state"] = stadiums[key]["state"] or state
            geocoded += 1

        # Respect Nominatim politeness
        time.sleep(1.05)

    # Save master stadium cache
    save_json(OUT_PATH, stadiums)

    # Create quick outdoor subset
    outdoor = {
        k: v for k, v in stadiums.items()
        if not v.get("indoor") and v.get("lat") and v.get("lon")
    }
    save_json(OUTDOOR_PATH, outdoor)

    print(f"✅ Wrote {OUT_PATH} with {len(stadiums)} FBS venues "
          f"(new: {created}, geocoded: {geocoded})")
    print(f"✅ Wrote {OUTDOOR_PATH} with {len(outdoor)} outdoor FBS venues")

if __name__ == "__main__":
    main()
