import json
import datetime

WEATHER_FILE = "weather.json"
VENUES_FILE = "fbs_stadiums.json"
OUTPUT_FILE = "weather_merged.json"

def merge():
    # Load venue/stadium data
    with open(VENUES_FILE, "r") as f:
        venues = json.load(f)

    # Load weather data
    with open(WEATHER_FILE, "r") as f:
        raw_weather = json.load(f)

    weather = {}

    # FIX: Only add entries that are valid dicts with lat/lon
    for w in raw_weather:
        if isinstance(w, dict) and "lat" in w and "lon" in w:
            key = f"{w['lat']},{w['lon']}"
            weather[key] = w
        else:
            print(f"[WARN] Skipped invalid weather entry: {w}")

    merged = {}

    # Merge weather → venue by coordinate match
    for venue_id, venue in venues.items():
        if not venue:
            merged[venue_id] = venue
            continue

        lat = venue.get("lat")
        lon = venue.get("lon")

        key = f"{lat},{lon}"

        venue_copy = dict(venue)

        if key in weather:
            venue_copy["weather"] = weather[key]
        else:
            venue_copy["weather"] = None

        merged[venue_id] = venue_copy

    out = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "venues": merged
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(out, f, indent=2)

    print("Weather merged successfully →", OUTPUT_FILE)


if __name__ == "__main__":
    merge()
