import json, os, time, hashlib
import requests

USER_AGENT = os.getenv("NWS_USER_AGENT", "fbf-data-weather (contact@forgedbyfreedom.com)")
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/geo+json"
}

CACHE_DIR = "cache/nws"
os.makedirs(CACHE_DIR, exist_ok=True)

STADIUM_DB_PATH = "data/stadiums_master.json"


# -----------------------------------------------------
# CACHE HELPERS
# -----------------------------------------------------
def _cache_key(url):
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def cached_get(url, ttl_seconds=1800):
    """Get + cache NWS responses to avoid rate limits."""
    key = _cache_key(url)
    path = os.path.join(CACHE_DIR, f"{key}.json")

    if os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if age < ttl_seconds:
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except:
                pass

    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        if r.status_code != 200:
            print(f"[⚠️] NWS returned status {r.status_code} for {url}")
            return None
        data = r.json()
    except Exception as e:
        print(f"[⚠️] NWS request failed: {e}")
        return None

    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except:
        pass

    return data


# -----------------------------------------------------
# FORECAST PARSING
# -----------------------------------------------------
def get_grid_info(lat, lon):
    url = f"https://api.weather.gov/points/{lat},{lon}"
    return cached_get(url, ttl_seconds=86400)


def parse_forecast(fc):
    props = fc.get("properties", {})
    periods = props.get("periods", [])
    if not periods:
        return None

    p0 = periods[0]
    rain = (p0.get("probabilityOfPrecipitation") or {}).get("value")
    wind_speed = p0.get("windSpeed", "0 mph")

    # Extract numeric wind speed
    wind_num = 0
