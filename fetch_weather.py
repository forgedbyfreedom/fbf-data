import json, os, time, hashlib
import requests
from datetime import datetime, timezone

USER_AGENT = os.getenv("NWS_USER_AGENT", "fbf-data-weather (contact@forgedbyfreedom.com)")
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/geo+json"
}

CACHE_DIR = "cache/nws"
os.makedirs(CACHE_DIR, exist_ok=True)

STADIUM_DB_PATH = "data/stadiums_master.json"

def _cache_key(url):
    return hashlib.md5(url.encode("utf-8")).hexdigest()

def cached_get(url, ttl_seconds=1800):
    key = _cache_key(url)
    path = os.path.join(CACHE_DIR, f"{key}.json")
    now = time.time()

    if os.path.exists(path):
        age = now - os.path.getmtime(path)
        if age < ttl_seconds:
            with open(path, "r") as f:
                return json.load(f)

    r = requests.get(url, headers=HEADERS, timeout=12)
    if r.status_code != 200:
        return None

    data = r.json()
    with open(path, "w") as f:
        json.dump(data, f)

    return data

def get_grid_info(lat, lon):
    url = f"https://api.weather.gov/points/{lat},{lon}"
    data = cached_get(url, ttl_seconds=86400)
    if not data:
        return None
    props = data.get("properties", {})
    return {
        "forecast": props.get("forecast"),
        "forecastHourly": props.get("forecastHourly"),
        "gridId": props.get("gridId"),
        "gridX": props.get("gridX"),
        "gridY": props.get("gridY")
    }

def parse_forecast(forecast_json):
    """Return a compact current-period summary + raw periods."""
    props = forecast_json.get("properties", {})
    periods = props.get("periods", [])
    if not periods:
        return None

    p0 = periods[0]
    rain = (p0.get("probabilityOfPrecipitation") or {}).get("value")
    wind_speed_str = p0.get("windSpeed", "0 mph")
    # windSpeed like "12 mph" or "5 to 10 mph"
    wind_num = 0
    try:
        wind_num = int(wind_speed_str.split()[0])
    except:
        pass

    return {
        "asOf": props.get("updated"),
        "shortForecast": p0.get("shortForecast"),
        "detailedForecast": p0.get("detailedForecast"),
        "temperatureF": p0.get("temperature"),
        "temperatureUnit": p0.get("temperatureUnit"),
        "windSpeedMph": wind_num,
        "windDirection": p0.get("windDirection"),
        "rainChancePct": rain,
        "periods": periods
    }

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default

def normalize_venue(name):
    return (name or "").strip()

def enrich_coords_from_db(game, stadium_db):
    venue = normalize_venue(game.get("venue") or game.get("stadium"))
    if not venue:
        return game
    rec = stadium_db.get(venue)
    if not rec:
        return game
    game.setdefault("latitude", rec.get("lat"))
    game.setdefault("longitude", rec.get("lon"))
    game.setdefault("indoor", rec.get("indoor"))
    game.setdefault("retractable", rec.get("retractable"))
    return game

def is_indoor(game):
    # game field wins, else DB-enriched field
    if game.get("indoor") is True:
        return True
    # some feeds call it "is_indoor"
    if game.get("is_indoor") is True:
        return True
    return False

def main():
    games = load_json("combined.json", [])
    stadium_db = load_json(STADIUM_DB_PATH, {})

    weather = {}
    outdoor_count = 0

    for g in games:
        gid = g.get("game_id") or g.get("id")
        if not gid:
            continue

        g = enrich_coords_from_db(g, stadium_db)

        if is_indoor(g):
            weather[gid] = {"indoor": True, "skipped": True}
            continue

        lat, lon = g.get("latitude"), g.get("longitude")
        if not lat or not lon:
            weather[gid] = {"error": "missing_coords"}
            continue

        outdoor_count += 1

        grid = get_grid_info(lat, lon)
        if not grid or not grid.get("forecast"):
            weather[gid] = {"error": "no_grid_forecast"}
            continue

        time.sleep(0.75)  # respect NWS limits

        fc = cached_get(grid["forecast"], ttl_seconds=1800)
        if not fc:
            weather[gid] = {"error": "forecast_fetch_failed"}
            continue

        parsed = parse_forecast(fc)
        if not parsed:
            weather[gid] = {"error": "forecast_parse_failed"}
            continue

        weather[gid] = {
            "indoor": False,
            "retractable": bool(g.get("retractable")),
            "lat": lat,
            "lon": lon,
            **parsed
        }

    with open("weather_raw.json", "w") as f:
        json.dump(weather, f, indent=2)

    print(f"[✅] NWS weather fetched for {outdoor_count} outdoor games ({len(weather)} total).")

if __name__ == "__main__":
    main()
