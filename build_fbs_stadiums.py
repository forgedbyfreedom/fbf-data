import json
import requests
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

COMBINED_FILE = ROOT / "combined.json"
MASTER_FILE = ROOT / "stadiums_master.json"
FBS_FILE = ROOT / "fbs_stadiums.json"
OUTDOOR_FILE = ROOT / "stadiums_outdoor.json"

# -----------------------------
# Simple fallback geocoder
# -----------------------------
def geocode(query):
    """Return (lat, lon) or (None, None)"""
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1"
        r = requests.get(url, timeout=10, headers={"User-Agent": "fbf-weather"})
        r.raise_for_status()
        d = r.json()
        if isinstance(d, list) and d:
            return float(d[0]["lat"]), float(d[0]["lon"])
    except:
        return None, None
    return None, None


def normalize_team(name: str) -> str:
    """Normalize for matching."""
    return name.lower().replace("state", "").replace("university", "").strip()


def main():
    with open(COMBINED_FILE, "r") as f:
        combined = json.load(f)["data"]

    # This collects venue info keyed consistently
    stadiums = {}

    print("🔍 Extracting venues from combined.json ...")

    for game in combined:
        venue = game.get("venue")
        if not venue:
            continue

        name = venue.get("name")
        if not name:
            continue

        name_key = name.strip().lower()

        if name_key not in stadiums:
            stadiums[name_key] = {
                "venue_name": name.strip(),
                "city": venue.get("city", ""),
                "state": venue.get("state", ""),
                "indoor": bool(venue.get("indoor")),
                "grass": bool(venue.get("grass")),
                "lat": venue.get("lat"),
                "lon": venue.get("lon"),
            }

    # Attempt to fill missing lat/lon
    print("🌎 Geocoding missing coordinates (fallback)...")
    geo_filled = 0

    for key, v in stadiums.items():
        if not v["lat"] or not v["lon"]:
            query = f"{v['venue_name']}, {v['city']} {v['state']}"
            lat, lon = geocode(query)
            if lat and lon:
                stadiums[key]["lat"] = lat
                stadiums[key]["lon"] = lon
                geo_filled += 1
            time.sleep(1.1)  # avoid Nominatim rate limits

    print(f"🔥 Geocoder filled {geo_filled} missing venues.")

    # Write master
    with open(MASTER_FILE, "w") as f:
        json.dump(stadiums, f, indent=2)

    # Outdoor = indoor == False AND has valid coords
    outdoor = {}
    for key, v in stadiums.items():
        if not v["indoor"] and v["lat"] and v["lon"]:
            outdoor[key] = v

    with open(OUTDOOR_FILE, "w") as f:
        json.dump(outdoor, f, indent=2)

    # FBS-only = Power Five + Group of Five teams (based on combined)
    fbs = {}
    for game in combined:
        for t in [game.get("home_team"), game.get("away_team")]:
            if not t:
                continue

            team_name = t.get("name", "")
            if not team_name:
                continue

            team_norm = normalize_team(team_name)

            # Match stadium by “city + team”
            for key, v in stadiums.items():
                if team_norm in key:
                    fbs[key] = v

    with open(FBS_FILE, "w") as f:
        json.dump(fbs, f, indent=2)

    print(f"🎉 stadiums_master.json written: {len(stadiums)} venues")
    print(f"🎉 stadiums_outdoor.json written: {len(outdoor)} outdoor venues")
    print(f"🎉 fbs_stadiums.json written: {len(fbs)} FBS venues")


if __name__ == "__main__":
    main()
