import json
from datetime import datetime

def load_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return {}

def get_weather_for_venue(lat, lon, weather_data):
    """Find closest matching weather entry."""
    for entry in weather_data.get("data", []):
        if round(entry.get("lat"), 3) == round(lat, 3) and round(entry.get("lon"), 3) == round(lon, 3):
            return entry
    return None

def main():
    combined = load_json("combined.json")
    weather = load_json("weather.json")
    weather_risk = load_json("weather_risk1.json")
    stadiums = load_json("stadiums_master.json")  # Always use master

    merged_count = 0

    for game in combined.get("data", []):
        sport = game.get("sport")

        # Indoor sports automatically get no weather
        if sport in ["nba", "ncaab", "nhl", "mlb"]:
            game["weather"] = {"indoor": True, "note": "Indoor sport"}
            game["weatherRisk"] = {"risk": 0, "details": []}
            continue

        # Try venue lookup
        venue = game.get("venue", {})
        venue_name = venue.get("name", "").strip()

        stadium_info = None

        # First lookup via stadium master DB
        for name, data in stadiums.items():
            if name.lower() == venue_name.lower():
                stadium_info = data
                break

        # Fallback: check the ESPN venue data inside combined JSON
        if not stadium_info:
            if venue.get("lat") and venue.get("lon"):
                stadium_info = {
                    "lat": venue.get("lat"),
                    "lon": venue.get("lon"),
                    "indoor": venue.get("indoor", False),
                    "name": venue_name
                }

        # Final fallback if still nothing → no coords
        if not stadium_info or not stadium_info.get("lat") or not stadium_info.get("lon"):
            game["weather"] = {"error": "no_coords"}
            game["weatherRisk"] = {"risk": 0, "details": []}
            continue

        lat = stadium_info["lat"]
        lon = stadium_info["lon"]
        indoor = stadium_info.get("indoor", False)

        # If indoor
        if indoor:
            game["weather"] = {"indoor": True}
            game["weatherRisk"] = {"risk": 0, "details": []}
            continue

        # Outdoor — pull closest matching weather reading
        w = get_weather_for_venue(lat, lon, weather)
        r = weather_risk.get("data", {}).get(f"{lat},{lon}", {"risk": 0, "details": []})

        if w:
            game["weather"] = w
        else:
            game["weather"] = {"error": "weather_not_found"}

        game["weatherRisk"] = r
        merged_count += 1

    print(f"[✅] Weather merged for {merged_count}/{len(combined.get('data', []))} games.")

    with open("combined.json", "w") as f:
        json.dump(combined, f, indent=2)

if __name__ == "__main__":
    main()
