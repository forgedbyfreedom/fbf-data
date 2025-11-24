import json
import re
from collections import defaultdict

COMBINED_PATH = "combined.json"
STADIUMS_MASTER_PATH = "stadiums_master.json"

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

def main():
    combined = load_json(COMBINED_PATH, {})
    if isinstance(combined, dict) and "data" in combined:
        games = combined["data"]
    elif isinstance(combined, list):
        games = combined
    else:
        games = []

    existing_master = load_json(STADIUMS_MASTER_PATH, {})

    master = {}  # key = venue_id or normalized name

    # seed with existing master (defensive: only dict entries)
    if isinstance(existing_master, dict):
        for k, v in existing_master.items():
            if isinstance(v, dict):
                master[k] = v

    # extract venues from combined
    for g in games:
        if not isinstance(g, dict):
            continue

        venue = g.get("venue") or {}
        if not isinstance(venue, dict):
            continue

        vname = venue.get("name") or g.get("venue_name")
        city = venue.get("city") or ""
        state = venue.get("state") or ""
        indoor = bool(venue.get("indoor"))
        grass = venue.get("grass")
        vid = venue.get("id") or venue.get("venue_id") or g.get("venue_id")

        lat = None
        lon = None

        # ESPN sometimes puts coords under different keys
        for k_lat, k_lon in [
            ("lat", "lon"),
            ("latitude", "longitude"),
            ("latitude", "longitude"),
            ("y", "x"),
        ]:
            if venue.get(k_lat) and venue.get(k_lon):
                lat = venue.get(k_lat)
                lon = venue.get(k_lon)
                break

        key = str(vid) if vid else normalize_name(vname)

        if not key:
            continue

        master.setdefault(key, {})
        master[key].update({
            "name": vname,
            "norm": normalize_name(vname),
            "city": city,
            "state": state,
            "indoor": indoor,
            "grass": grass,
        })

        if lat and lon:
            try:
                master[key]["lat"] = float(lat)
                master[key]["lon"] = float(lon)
            except Exception:
                pass

    save_json(STADIUMS_MASTER_PATH, master)
    print(f"[✅] stadiums_master.json built ({len(master)} venues).")

if __name__ == "__main__":
    main()
