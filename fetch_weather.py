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


_geo_cache = {}


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

    _geo_cache[key] = (None, None)
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
            # No usable coordinates
            continue

        point_url = fetch_point(lat, lon)
        if not point_url:
            continue

        hourly = fetch_hourly(point_url)
        if not hourly or "properties" not in hourly:
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

        weather_map[str(gid)] = {
            "temperatureF": temp,
            "windSpeedMph": wind_mph,
            "shortForecast": short,
            "detailedForecast": detailed,
        }
        processed += 1

    save_json(OUTFILE, {"data": weather_map})
    print(f"✅ Weather written: {processed} locations → {OUTFILE}")


if __name__ == "__main__":
    main()
