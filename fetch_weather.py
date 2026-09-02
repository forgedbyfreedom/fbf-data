#!/usr/bin/env python3
import json
import os
import time
import requests

COMBINED_FILE = "combined.json"
OUTFILE = "weather_raw.json"

HEADERS = {"User-Agent": "fbf-weather-fetcher/1.0 (forgedbyfreedom.org)"}
GEOCODER = "https://nominatim.openstreetmap.org/search"

US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS",
    "KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY",
    "NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV",
    "WI","WY"
}


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def is_us_outdoor(venue):
    if not isinstance(venue, dict):
        return False
    indoor = bool(venue.get("indoor", False))
    state = venue.get("state")
    if indoor:
        return False
    if not state or state not in US_STATES:
        return False
    return True


# Geocode results are cached ON DISK, not just in memory.
#
# This used to be a bare in-memory dict, so every run re-geocoded every venue
# from scratch and threw the answers away. Nominatim asks for a 1 second gap
# between requests and rate-limits cloud IPs, so in practice most lookups
# failed and coverage never accumulated: on 2026-09-02 only 20 of 75 stadiums
# had coordinates and just 53 of 81 games got weather at all. Persisting the
# cache means coverage only ever grows, and a venue is geocoded once, forever.
GEO_CACHE_FILE = "geo_cache.json"


def _load_geo_cache():
    try:
        with open(GEO_CACHE_FILE) as f:
            raw = json.load(f)
        out = {}
        for k, v in raw.items():
            city, _, state = k.partition("|")
            if isinstance(v, list) and len(v) == 2:
                out[(city, state)] = (v[0], v[1])
        return out
    except Exception:
        return {}


def _save_geo_cache(cache):
    try:
        raw = {f"{c}|{st}": list(v) for (c, st), v in cache.items()
               if v and v[0] is not None}
        with open(GEO_CACHE_FILE, "w") as f:
            json.dump(raw, f, indent=2, sort_keys=True)
        print(f"[weather] geocode cache: {len(raw)} venues on disk")
    except Exception as e:
        print(f"[weather] could not save geocode cache: {e}")


_geo_cache = _load_geo_cache()


def geocode(city, state):
    """Geocode city/state -> (lat, lon) with simple in-memory cache."""
    if not city or not state:
        return None, None

    key = (city.strip().lower(), state.strip().upper())
    if key in _geo_cache:
        return _geo_cache[key]

    try:
        q = f"{city}, {state}, USA"
        params = {"q": q, "format": "json", "limit": 1}
        r = requests.get(GEOCODER, params=params, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            arr = r.json()
            if arr:
                lat = float(arr[0]["lat"])
                lon = float(arr[0]["lon"])
                _geo_cache[key] = (lat, lon)
                # Be nice to Nominatim
                time.sleep(1.0)
                return lat, lon
    except Exception:
        pass

    # Deliberately not cached: a miss here is nearly always a rate limit or a
    # transient failure, not a place that cannot be found. Caching it would
    # make one bad run permanent.
    return None, None


def fetch_point(lat, lon):
    url = f"https://api.weather.gov/points/{lat},{lon}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        return data["properties"]["forecastHourly"]
    except Exception:
        return None


def fetch_hourly(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def parse_wind_mph(raw_wind):
    """NOAA windSpeed is often '10 mph'. Convert to numeric mph when possible."""
    if raw_wind is None:
        return None
    if isinstance(raw_wind, (int, float)):
        return float(raw_wind)
    if isinstance(raw_wind, str):
        parts = raw_wind.split()
        for p in parts:
            try:
                return float(p)
            except ValueError:
                continue
    return None


def estimate_rain_chance(forecast_text):
    """Estimate rain chance % from NOAA shortForecast text when numeric value is unavailable."""
    if not forecast_text:
        return 0
    text = forecast_text.lower()
    precip_words = ["rain", "showers", "storm", "thunder", "snow", "sleet", "freezing", "hail", "drizzle"]
    has_precip = any(w in text for w in precip_words)
    if not has_precip:
        return 0
    if "slight chance" in text:
        return 20
    if "chance" in text and "slight" not in text:
        return 50
    if "likely" in text:
        return 70
    # Words like "rain", "showers" without qualifiers = high chance
    return 80


def main():
    combined = load_json(COMBINED_FILE)
    if not combined or "data" not in combined:
        print("❌ combined.json missing or invalid")
        return

    games = combined["data"]
    print(f"🔎 Fetching weather for {len(games)} games...")

    weather_map = {}
    processed = 0

    for g in games:
        if not isinstance(g, dict):
            continue

        gid = g.get("id")
        venue = g.get("venue") or {}

        if not gid:
            continue

        # Skip non-US / indoor
        if not is_us_outdoor(venue):
            continue

        lat = venue.get("lat")
        lon = venue.get("lon")

        if lat is None or lon is None:
            city = venue.get("city")
            state = venue.get("state")
            lat, lon = geocode(city, state)

        if lat is None or lon is None:
            print(f"  [skip] {gid}: no coordinates for venue {venue.get('name', '?')} ({venue.get('city')}, {venue.get('state')})")
            continue

        point_url = fetch_point(lat, lon)
        if not point_url:
            print(f"  [skip] {gid}: NOAA point lookup failed for ({lat}, {lon})")
            continue

        hourly = fetch_hourly(point_url)
        if not hourly or "properties" not in hourly:
            print(f"  [skip] {gid}: hourly forecast fetch failed")
            continue

        periods = hourly["properties"].get("periods") or []
        if not periods:
            continue

        props = periods[0]
        temp = props.get("temperature")
        wind_raw = props.get("windSpeed")
        wind_mph = parse_wind_mph(wind_raw)
        short = props.get("shortForecast")
        detailed = props.get("detailedForecast")

        # Extract precipitation probability from NOAA data
        precip_raw = props.get("probabilityOfPrecipitation") or {}
        precip_pct = precip_raw.get("value")  # NOAA provides this as a numeric %
        if precip_pct is None:
            # Estimate from shortForecast text if NOAA doesn't provide numeric value
            precip_pct = estimate_rain_chance(short)

        weather_map[str(gid)] = {
            "temperatureF": temp,
            "windSpeedMph": wind_mph,
            "rainChancePct": precip_pct,
            "shortForecast": short,
            "detailedForecast": detailed,
        }
        processed += 1

    save_json(OUTFILE, {"data": weather_map})
    print(f"✅ Weather written: {processed} locations → {OUTFILE}")


if __name__ == "__main__":
    try:
        main()
    finally:
        _save_geo_cache(_geo_cache)
