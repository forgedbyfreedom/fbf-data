#!/usr/bin/env python3
import json
import os
import re
import requests

COMBINED = "combined.json"
STADIUMS_MASTER = "stadiums_master.json"
OUTFILE = "weather_raw.json"   # <<< IMPORTANT: match weather_risk1.py

HEADERS = {"User-Agent": "fbf-weather-fetcher"}

US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS",
    "KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY",
    "NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV",
    "WI","WY"
}

GEOCODER_BASE = "https://api.weather.gov"


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_name(name: str) -> str:
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(r"[^a-z0-9 ]+", "", n)
    n = re.sub(r"\s+", " ", n)
    return n


def is_us_outdoor(venue_rec: dict) -> bool:
    """
    Decide if we should fetch weather for this venue.
    Uses stadiums_master fields, not combined.json.
    """
    if not venue_rec:
        return False

    state = venue_rec.get("state")
    indoor = venue_rec.get("indoor", False)

    if indoor:
        return False
    if state not in US_STATES:
        return False

    return True


def fetch_point(lat, lon):
    """Get hourly forecast URL from api.weather.gov/points."""
    url = f"{GEOCODER_BASE}/points/{lat},{lon}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 404:
            return None  # foreign / non-supported
        r.raise_for_status()
        data = r.json()
        return data["properties"].get("forecastHourly")
    except Exception:
        return None


def fetch_hourly(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def parse_wind_speed(val):
    """
    NWS often returns '7 mph' or '10 to 15 mph'.
    Convert to a simple numeric mph (best effort).
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    s = str(val)
    # Grab first integer in the string
    m = re.search(r"(\d+)", s)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def main():
    combined = load_json(COMBINED)
    if not combined or "data" not in combined:
        print("❌ combined.json missing or invalid")
        return

    stadiums = load_json(STADIUMS_MASTER) or {}
    if not isinstance(stadiums, dict):
        print("❌ stadiums_master.json missing or invalid")
        return

    total_games = len(combined["data"])
    print(f"🔎 Fetching weather for {total_games} games...")

    weather_out = {}

    for g in combined["data"]:
        game_id = str(g.get("id"))
        venue = g.get("venue") or {}
        venue_name = venue.get("name")

        # If no venue name, we can't map it
        if not venue_name:
            weather_out[game_id] = {"error": "no_venue_name"}
            continue

        norm = normalize_name(venue_name)
        venue_rec = stadiums.get(norm)

        # If we don't have this venue in master, skip
        if not venue_rec:
            weather_out[game_id] = {"error": "no_venue_match"}
            continue

        # Only US outdoor
        if not is_us_outdoor(venue_rec):
            weather_out[game_id] = {"error": "no_weather_needed"}
            continue

        lat = venue_rec.get("lat")
        lon = venue_rec.get("lon")
        if not lat or not lon:
            weather_out[game_id] = {"error": "missing_coords"}
            continue

        point_url = fetch_point(lat, lon)
        if not point_url:
            weather_out[game_id] = {"error": "point_lookup_failed"}
            continue

        hourly = fetch_hourly(point_url)
        if not hourly:
            weather_out[game_id] = {"error": "hourly_fetch_failed"}
            continue

        periods = (hourly.get("properties") or {}).get("periods") or []
        if not periods:
            weather_out[game_id] = {"error": "no_periods"}
            continue

        # Nearest forecast (you can later refine to game-time index if you want)
        p0 = periods[0]

        temp = p0.get("temperature")
        wind_raw = p0.get("windSpeed")
        wind_mph = parse_wind_speed(wind_raw)
        short = p0.get("shortForecast")
        detailed = p0.get("detailedForecast")

        weather_out[game_id] = {
            "temperatureF": temp,
            "windSpeedMph": wind_mph,
            "summary": short,
            "details": detailed,
        }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(weather_out, f, indent=2)

    print(f"✅ Weather written: {len(weather_out)} locations → {OUTFILE}")


if __name__ == "__main__":
    main()
