import json
import re
import time
import requests

COMBINED_PATH = "combined.json"
MASTER_PATH = "stadiums_master.json"
FBS_OUT_PATH = "fbs_stadiums.json"
OUTDOOR_PATH = "stadiums_outdoor.json"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
UA = "fbf-data (contact@forgedbyfreedom.com)"

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)

def normalize_name(name):
    if not name:
        return ""
    n = name.strip().lower()
    n = re.sub(r"\s+", " ", n)
    n = n.replace("stadium", "").replace("arena", "").replace("field", "")
    n = n.replace("center", "").replace("centre", "")
    n = n.replace("coliseum", "").replace("dome", "")
    n = n.replace("the ", "")
    n = re.sub(r"[^a-z0-9 ]+", "", n)
    return n.strip()

def geocode_via_nominatim(name, city, state):
    if not name:
        return None, None
    q = ", ".join([x for x in [name, city, state, "USA"] if x])
    try:
        r = requests.get(
            NOMINATIM_URL,
            params={"q": q, "format": "json", "limit": 1},
            headers={"User-Agent": UA},
            timeout=10,
        )
        if not r.ok:
            return None, None
        data = r.json()
        if not data:
            return None, None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        return None, None

def main():
    # Ensure master exists by re-building from combined if needed
    combined = load_json(COMBINED_PATH, {})
    if isinstance(combined, dict) and "data" in combined:
        games = combined["data"]
    elif isinstance(combined, list):
        games = combined
    else:
        games = []

    master = load_json(MASTER_PATH, {})
    if not isinstance(master, dict):
        master = {}

    # Defensive: remove any non-dict values (fixes your int .get crash)
    master = {k: v for k, v in master.items() if isinstance(v, dict)}

    # Collect all venues seen in combined
    seen = {}
    for g in games:
        if not isinstance(g, dict):
            continue
        venue = g.get("venue") or {}
        if not isinstance(venue, dict):
            continue

        vname = venue.get("name") or g.get("venue_name")
        if not vname:
            continue

        city = venue.get("city") or ""
        state = venue.get("state") or ""
        indoor = bool(venue.get("indoor"))
        vid = venue.get("id") or venue.get("venue_id") or g.get("venue_id")
        key = str(vid) if vid else normalize_name(vname)

        if not key:
            continue

        seen.setdefault(key, {})
        seen[key].update({
            "name": vname,
            "norm": normalize_name(vname),
            "city": city,
            "state": state,
            "indoor": indoor,
            "sport_hint": g.get("sport")
        })

        # pull coords if ESPN already provided them in combined
        for k_lat, k_lon in [("lat","lon"), ("latitude","longitude"), ("y","x")]:
            if venue.get(k_lat) and venue.get(k_lon):
                try:
                    seen[key]["lat"] = float(venue.get(k_lat))
                    seen[key]["lon"] = float(venue.get(k_lon))
                except Exception:
                    pass

    # Merge seen into master
    for k, v in seen.items():
        master.setdefault(k, {})
        master[k].update(v)

    # Fill missing lat/lon using light geocode (only if missing)
    filled = 0
    for k, v in master.items():
        if v.get("lat") and v.get("lon"):
            continue

        # only geocode outdoor football / major college venues
        s = (v.get("sport_hint") or "").lower()
        if s not in ["ncaaf", "nfl"]:
            continue

        lat, lon = geocode_via_nominatim(v.get("name"), v.get("city"), v.get("state"))
        if lat and lon:
            v["lat"] = lat
            v["lon"] = lon
            filled += 1
            time.sleep(1.1)  # polite throttle

    save_json(MASTER_PATH, master)

    # Outdoor subset for weather
    outdoor = {
        k: v for k, v in master.items()
        if isinstance(v, dict)
        and not v.get("indoor")
        and v.get("lat") and v.get("lon")
    }

    save_json(OUTDOOR_PATH, outdoor)

    # FBS stadiums = outdoor + football hint
    fbs = {
        k: v for k, v in outdoor.items()
        if (v.get("sport_hint") or "").lower() == "ncaaf"
    }

    save_json(FBS_OUT_PATH, fbs)

    print(f"[✅] stadiums_master.json updated ({len(master)} venues).")
    print(f"[✅] stadiums_outdoor.json built ({len(outdoor)} outdoor venues).")
    print(f"[✅] fbs_stadiums.json built ({len(fbs)} FBS outdoor venues).")
    print(f"[ℹ️] Filled coords via geocode: {filled}")

if __name__ == "__main__":
    main()
