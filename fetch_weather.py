import json
import requests
import time

COMBINED_PATH = "combined.json"
STADIUMS_PATH = "fbs_stadiums.json"
OUT_PATH = "weather_raw.json"

UA = "fbf-data (contact@forgedbyfreedom.com)"

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)

def clamp(x, lo=None, hi=None):
    if lo is not None:
        x = max(lo, x)
    if hi is not None:
        x = min(hi, x)
    return x

def extract_games():
    games = load_json(COMBINED_PATH, [])
    if isinstance(games, dict) and "data" in games:
        games = games["data"]
    return [g for g in games if isinstance(g, dict)]

def get_coords_for_game(g, stadiums):
    venue = g.get("venue") or {}
    vname = (venue.get("name") or "").strip()
    indoor = bool(venue.get("indoor"))

    # ESPN coords first
    lat = venue.get("latitude") or venue.get("lat")
    lon = venue.get("longitude") or venue.get("lon")
    if lat and lon:
        return float(lat), float(lon), indoor, "espn_coords"

    # Fallback to stadium cache (name match)
    if vname:
        key = vname.lower()
        s = stadiums.get(key)
        if s and s.get("lat") and s.get("lon"):
            return float(s["lat"]), float(s["lon"]), indoor, "stadium_cache"

    return None, None, indoor, "no_coords"

def nws_point(lat, lon):
    url = f"https://api.weather.gov/points/{lat},{lon}"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    if not r.ok:
        return None
    return r.json()

def nws_forecast_hourly(forecast_url):
    r = requests.get(forecast_url, headers={"User-Agent": UA}, timeout=20)
    if not r.ok:
        return None
    return r.json()

def parse_hourly_to_simple(hourly_json):
    """
    Convert NWS hourly to:
    windSpeedMph, rainChancePct, temperatureF
    Choose next forecast period.
    """
    try:
        periods = hourly_json["properties"]["periods"]
        if not periods:
            return None
        p = periods[0]

        temp_f = p.get("temperature")

        wind = p.get("windSpeed") or ""
        # e.g. "12 mph" or "5 to 10 mph"
        mph = None
        nums = [int(x) for x in wind.replace("mph","").replace("to"," ").split() if x.isdigit()]
        if nums:
            mph = sum(nums) / len(nums)

        rain = None
        pop = p.get("probabilityOfPrecipitation") or {}
        if isinstance(pop, dict):
            rain = pop.get("value")

        return {
            "temperatureF": temp_f,
            "windSpeedMph": mph,
            "rainChancePct": rain
        }
    except:
        return None

def main():
    games = extract_games()
    stadiums = load_json(STADIUMS_PATH, {})

    out = {}

    for g in games:
        gid = g.get("game_id") or g.get("id")
        if not gid:
            continue

        lat, lon, indoor, source = get_coords_for_game(g, stadiums)

        # Indoor = auto-skip
        if indoor:
            out[gid] = {
                "indoor": True,
                "error": None,
                "source": "indoor"
            }
            continue

        if not lat or not lon:
            out[gid] = {
                "indoor": False,
                "error": "no_coords",
                "source": source
            }
            continue

        # NWS pipeline
        try:
            point_json = nws_point(lat, lon)
            if not point_json:
                out[gid] = {"indoor": False, "error": "nws_point_fail", "source": source}
                continue

            hourly_url = point_json["properties"].get("forecastHourly")
            if not hourly_url:
                out[gid] = {"indoor": False, "error": "no_hourly_url", "source": source}
                continue

            hourly_json = nws_forecast_hourly(hourly_url)
            simple = parse_hourly_to_simple(hourly_json)

            if not simple:
                out[gid] = {"indoor": False, "error": "hourly_parse_fail", "source": source}
                continue

            out[gid] = {
                "indoor": False,
                "error": None,
                "source": source,
                "lat": lat,
                "lon": lon,
                **simple
            }

        except Exception as e:
            out[gid] = {"indoor": False, "error": str(e), "source": source}

        time.sleep(0.25)  # light throttle

    save_json(OUT_PATH, out)
    print(f"FETCH WEATHER FILE UPDATED SUCCESSFULLY ({len(out)} games)")

if __name__ == "__main__":
    main()
