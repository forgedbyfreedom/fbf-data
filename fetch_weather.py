#!/usr/bin/env python3
"""
High-speed asynchronous weather fetcher.
-----------------------------------------
• Fetches hourly forecasts from api.weather.gov
• Async with concurrency limits (safe for NWS)
• Robust retry & exponential backoff
• Produces:
    - weather.json      (clean normalized output)
    - weather_raw.json  (raw hourly periods)
"""

import json
import asyncio
import aiohttp
import async_timeout
import math
import time

COMBINED_FILE = "combined.json"
STADIUMS_FILE = "stadiums_master.json"

OUT_FILE = "weather.json"
RAW_FILE = "weather_raw.json"

NWS_HEADERS = {
    "User-Agent": "fbf-data (weather fetcher)"
}

# Max 8 requests in flight (NWS safe limit)
CONCURRENCY = 8
TIMEOUT = 45
RETRIES = 4


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default


def make_key(lat, lon):
    """Normalized lat/lon key that merge_weather expects."""
    return f"{float(lat):.4f},{float(lon):.4f}"


# ------------------------------------------------------------
# Async Fetch Helpers
# ------------------------------------------------------------

async def fetch_json(session, url, timeout=TIMEOUT, retries=RETRIES):
    """
    Generic async GET with retries & exponential backoff.
    """
    for attempt in range(1, retries + 1):
        try:
            async with async_timeout.timeout(timeout):
                async with session.get(url, headers=NWS_HEADERS) as r:
                    if r.status == 200:
                        return await r.json(), None
                    err = f"HTTP {r.status}"
        except Exception as e:
            err = str(e)

        # Retry with backoff
        wait = 1.2 * attempt
        print(f"⚠️ fetch_json retry {attempt}/{retries} for {url}: {err}")
        await asyncio.sleep(wait)

    return None, err


async def fetch_forecast_for_location(session, lat, lon, semaphore):
    """
    Full pipeline for one stadium:
    1) GET /points/{lat,lon}
    2) Extract hourly URL
    3) GET hourly forecast
    """

    async with semaphore:  # limit concurrency
        key = make_key(lat, lon)

        # 1) Points lookup
        pts_url = f"https://api.weather.gov/points/{lat},{lon}"
        points, err = await fetch_json(session, pts_url)
        if err or not points:
            return key, None, None, f"points_failed: {err}"

        hourly = points.get("properties", {}).get("forecastHourly")
        if not hourly:
            return key, None, None, "no_hourly_url"

        # 2) Hourly forecast
        periods, err2 = await fetch_json(session, hourly)
        if err2 or not periods:
            return key, None, None, f"hourly_failed: {err2}"

        # Use first (closest hour)
        first = None
        try:
            first = periods.get("properties", {}).get("periods", [])[0]
        except:
            # old API responses: treat periods as list
            try:
                first = periods.get("periods", [])[0]
            except:
                return key, None, None, "no_periods"

        if not first:
            return key, None, None, "no_periods"

        # Normalize fields
        tempF = first.get("temperature")
        wind_raw = first.get("windSpeed") or "0 mph"
        try:
            wind_mph = float(wind_raw.split(" ")[0])
        except:
            wind_mph = 0.0

        rain = first.get("probabilityOfPrecipitation", {}).get("value") or 0

        clean = {
            "key": key,
            "lat": lat,
            "lon": lon,
            "temperatureF": tempF,
            "windSpeedMph": wind_mph,
            "rainChancePct": rain,
            "shortForecast": first.get("shortForecast") or "",
            "detailedForecast": first.get("detailedForecast") or "",
        }

        raw = { "key": key, "raw": first }

        return key, clean, raw, None


# ------------------------------------------------------------
# Main async runner
# ------------------------------------------------------------

async def run_weather_fetch():
    combined = load_json(COMBINED_FILE, {})
    if "data" not in combined:
        print("❌ combined.json missing data[]")
        return

    games = combined["data"]

    semaphore = asyncio.Semaphore(CONCURRENCY)

    tasks = []

    async with aiohttp.ClientSession() as session:
        for g in games:
            venue = g.get("venue") or {}
            lat = venue.get("lat")
            lon = venue.get("lon")

            # Skip missing coords
            if not lat or not lon:
                continue

            lat = float(lat)
            lon = float(lon)

            task = asyncio.create_task(
                fetch_forecast_for_location(session, lat, lon, semaphore)
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

    clean_rows = []
    raw_rows = []

    for key, clean, raw, err in results:
        if err:
            clean_rows.append({"key": key, "error": err})
        else:
            clean_rows.append(clean)
            raw_rows.append(raw)

    # Save outputs
    with open(OUT_FILE, "w") as f:
        json.dump({"data": clean_rows}, f, indent=2)

    with open(RAW_FILE, "w") as f:
        json.dump({"data": raw_rows}, f, indent=2)

    print(f"✅ Weather fetched for {len(clean_rows)} locations (async mode).")


# ------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------

def main():
    asyncio.run(run_weather_fetch())


if __name__ == "__main__":
    main()
