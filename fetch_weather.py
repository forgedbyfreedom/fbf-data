#!/usr/bin/env python3
import json
import os
import requests

COMBINED = "combined.json"
OUTFILE = "weather.json"

HEADERS = {"User-Agent": "fbf-weather-fetcher"}

US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS",
    "KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY",
    "NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV",
    "WI","WY"
}

def load(path):
    if not os.path.exists(path):
        return None
    with open(path,"r") as f:
        return json.load(f)

def is_us_outdoor(venue):
    """Return True only for USA + outdoor stadiums."""
    if not venue: 
        return False

    state = venue.get("state")
    indoor = venue.get("indoor", False)

    if indoor:
        return False
    if state not in US_STATES:
        return False

    return True

def fetch_point(lat, lon):
    """Get the hourly forecast URL from api.weather.gov/points."""
    url = f"https://api.weather.gov/points/{lat},{lon}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 404:
            return None  # foreign (Canada/etc)
        r.raise_for_status()
        data = r.json()
        return data["properties"]["forecastHourly"]
    except:
        return None

def fetch_hourly(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()
    except:
        return None

def main():
    combined = load(COMBINED)
    if not combined or "data" not in combined:
        print("❌ combined.json missing")
        return

    results = []
    total_games = len(combined["data"])

    print(f"🔎 Fetching weather for {total_games} games...")

    for g in combined["data"]:
        venue = g.get("venue") or {}
        vid = g.get("id")

        # Skip non-US or indoor
        if not is_us_outdoor(venue):
            results.append({
                "key": str(vid),
                "error": "no_weather_needed"
            })
            continue

        lat = venue.get("lat")
        lon = venue.get("lon")

        if not lat or not lon:
            results.append({"key": str(vid), "error": "missing_coords"})
            continue

        point_url = fetch_point(lat, lon)
        if not point_url:
            results.append({"key": str(vid), "error": "point_lookup_failed"})
            continue

        hourly = fetch_hourly(point_url)
        if not hourly:
            results.append({"key": str(vid), "error": "hourly_fetch_failed"})
            continue

        props = hourly["properties"]["periods"][0]  # nearest forecast

        results.append({
            "key": str(vid),
            "temperatureF": props.get("temperature"),
            "windSpeedMph": props.get("windSpeed"),
            "shortForecast": props.get("shortForecast"),
            "detailedForecast": props.get("detailedForecast"),
        })

    with open(OUTFILE,"w") as f:
        json.dump({"data": results}, f, indent=2)

    print(f"✅ Weather written: {len(results)} locations")

if __name__ == "__main__":
    main()
