import json
import re

COMBINED_PATH = "combined.json"
OUTDOOR_PATH = "stadiums_outdoor.json"
WEATHER_RAW_PATH = "weather_raw.json"
WEATHER_OUT_PATH = "weather.json"

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
    stadiums = load_json(OUTDOOR_PATH, {})
    weather_raw = load_json(WEATHER_RAW_PATH, {})

    if isinstance(combined, dict) and "data" in combined:
        games = combined["data"]
    elif isinstance(combined, list):
        games = combined
    else:
        games = []

    # Build fast lookup by venue normalized name
    stad_by_norm = {}
    for sid, s in stadiums.items():
        if not isinstance(s, dict):
            continue
        norm = s.get("norm") or normalize_name(s.get("name"))
        if norm:
            stad_by_norm[norm] = sid

    merged_count = 0
    out_weather = {}

    for g in games:
        if not isinstance(g, dict):
            continue

        gid = g.get("game_id") or g.get("id")
        venue = g.get("venue") or {}

        if not isinstance(venue, dict):
            out_weather[gid] = {"error": "bad_venue"}
            continue

        vname = venue.get("name") or g.get("venue_name")
        norm = normalize_name(vname)

        sid = None
        if venue.get("id") and str(venue.get("id")) in weather_raw:
            sid = str(venue.get("id"))
        elif norm in stad_by_norm:
            sid = stad_by_norm[norm]

        if not sid:
            out_weather[gid] = {"error": "no_coords"}
            continue

        w = weather_raw.get(sid)
        if not w:
            out_weather[gid] = {"error": "no_weather"}
            continue

        out_weather[gid] = w
        merged_count += 1

    save_json(WEATHER_OUT_PATH, out_weather)
    print(f"[✅] Weather merged for {merged_count}/{len(games)} games.")

if __name__ == "__main__":
    main()
