#!/usr/bin/env python3

import json
import requests
import socket
import time

COMBINED_FILE = "combined.json"
OUTPUT_FILE = "weather.json"

HEADERS = {
    "User-Agent": "FBF Sports Data (contact: support@forgedbyfreedom.com)",
    "Accept": "application/geo+json"
}

# Force IPv4 only for ALL requests
orig_getaddrinfo = socket.getaddrinfo
def ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = ipv4_only_getaddrinfo


def safe_request(url, retries=3, timeout=20):
    """Robust HTTP GET with IPv4, retries, and long timeouts."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            else:
                print(f"⚠️ HTTP {r.status_code} for {url}")
        except Exception as e:
            print(f"⚠️ Attempt {attempt}/{retries} failed: {e}")
            time.sleep(1.5 * attempt)
    return None


def collect_weather(lat, lon):
    """Fetch hourly forecast for given coordinates."""
    url = f"https://api.weather.gov/points/{lat},{lon}"
    p = safe_request(url)
    if not p:
        return None

    hourly = p["properties"].get("forecastHourly")
    if not hourly:
        return None

    data = safe_request(hourly)
    if not data:
        return None

    periods = data.get("properties", {}).get("periods", [])
    if not periods:
        return None

    # Use the first-hour forecast
    f = periods[0]

    temp_f = f.get("temperature")
    wind = f.get("windSpeed") or "0 mph"
    short = f.get("shortForecast", "")
    detailed = f.get("detailedForecast", "")

    try:
        wind_mph = float(wind.split()[0])
    except:
        wind_mph = 0.0

    return {
        "temperatureF": temp_f,
        "windSpeedMph": wind_mph,
        "rainChancePct": f.get("probabilityOfPrecipitation", {}).get("value", 0),
        "shortForecast": short,
        "detailedForecast": detailed
    }


def main():
    # Load combined.json
    with open(COMBINED_FILE, "r") as f:
        combined = json.load(f)

    weather_output = {"data": []}

    games = combined.get("data", [])
    print(f"🔎 Fetching weather for {len(games)} games...")

    for g in games:
        venue = g.get("venue") or {}
        lat = venue.get("lat")
        lon = venue.get("lon")

        if not lat or not lon:
            continue

        key = f"{lat:.4f},{lon:.4f}"

        w = collect_weather(lat, lon)
        if not w:
            continue

        weather_output["data"].append({
            "key": key,
            **w
        })

    with open(OUTPUT_FILE, "w") as f:
        json.dump(weather_output, f, indent=2)

    print(f"✅ Weather written: {len(weather_output['data'])} locations")


if __name__ == "__main__":
    main()
