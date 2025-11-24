import os, json, requests, datetime as dt


NWS_UA = os.getenv("NWS_USER_AGENT", "fbf-data (contact@forgedbyfreedom.org)")
HEADERS = {"User-Agent": NWS_UA}


def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def normalize_combined(combined):
    if isinstance(combined, dict) and "data" in combined:
        return combined["data"]
    if isinstance(combined, list):
        return combined
    return []


def parse_game_time_utc(g):
    s = g.get("date_utc") or g.get("dateUTC") or g.get("date")
    if not s:
        return None
    try:
        if s.endswith("Z"):
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.datetime.fromisoformat(s)
    except Exception:
        return None


def nws_points(lat, lon):
    url = f"https://api.weather.gov/points/{lat},{lon}"
    r = requests.get(url, headers=HEADERS, timeout=10)
    if not r.ok:
        return None, f"points_http_{r.status_code}"
    j = r.json()
    props = j.get("properties") or {}
    return props, None


def nws_hourly_forecast(hourly_url):
    r = requests.get(hourly_url, headers=HEADERS, timeout=10)
    if not r.ok:
        return None, f"hourly_http_{r.status_code}"
    j = r.json()
    periods = (j.get("properties") or {}).get("periods") or []
    return periods, None


def pick_period(periods, kickoff_utc):
    if not periods or not kickoff_utc:
        return None
    best = None
    best_delta = None

    for p in periods:
        try:
            start = dt.datetime.fromisoformat(p["startTime"])
            delta = abs((start - kickoff_utc).total_seconds())
            if best_delta is None or delta < best_delta:
                best = p
                best_delta = delta
        except Exception:
            continue

    return best


def mph_from_wind(wind_str):
    # NWS windSpeed can be "5 mph" or "5 to 10 mph"
    if not wind_str:
        return None
    try:
        nums = [float(x) for x in wind_str.replace("mph", "").replace("to", " ").split() if x.replace(".", "").isdigit()]
        if not nums:
            return None
        return sum(nums) / len(nums)
    except Exception:
        return None


def main():
    combined = normalize_combined(load_json("combined.json", []))
    venues = load_json("stadiums_outdoor.json", {})
    if not isinstance(venues, dict):
        venues = {}

    weather_raw = {}

    for g in combined:
        if not isinstance(g, dict):
            continue

        gid = g.get("game_id") or g.get("id")
        if not gid:
            continue

        v = g.get("venue") or {}
        if not isinstance(v, dict):
            v = {}

        # Indoor → no weather
        if v.get("indoor"):
            weather_raw[gid] = {"indoor": True}
            continue

        lat = v.get("lat") or v.get("latitude")
        lon = v.get("lon") or v.get("longitude")

        # fallback from stadiums_outdoor if needed
        if (not lat or not lon):
            # match by id or name
            vid = str(v.get("id") or v.get("venue_id") or "")
            match = None
            for kk, vv in venues.items():
                if not isinstance(vv, dict):
                    continue
                if vid and str(vv.get("id")) == vid:
                    match = vv
                    break
                if (vv.get("name") or "").lower() == (v.get("name") or "").lower():
                    match = vv
                    break
            if match:
                lat = match.get("lat")
                lon = match.get("lon")

        if not lat or not lon:
            weather_raw[gid] = {"error": "no_coords"}
            continue

        kickoff = parse_game_time_utc(g)

        props, err = nws_points(lat, lon)
        if err or not props:
            weather_raw[gid] = {"error": err or "points_failed", "lat": lat, "lon": lon}
            continue

        hourly_url = props.get("forecastHourly")
        if not hourly_url:
            weather_raw[gid] = {"error": "no_hourly_url", "lat": lat, "lon": lon}
            continue

        periods, err2 = nws_hourly_forecast(hourly_url)
        if err2 or not periods:
            weather_raw[gid] = {"error": err2 or "hourly_failed", "lat": lat, "lon": lon}
            continue

        p = pick_period(periods, kickoff)
        if not p:
            weather_raw[gid] = {"error": "no_period_match", "lat": lat, "lon": lon}
            continue

        wind_mph = mph_from_wind(p.get("windSpeed"))
        rain_pct = None
        try:
            rain_pct = (p.get("probabilityOfPrecipitation") or {}).get("value")
        except Exception:
            rain_pct = None

        weather_raw[gid] = {
            "lat": lat,
            "lon": lon,
            "temperatureF": p.get("temperature"),
            "windSpeedMph": wind_mph,
            "rainChancePct": rain_pct,
            "shortForecast": p.get("shortForecast"),
            "detailedForecast": p.get("detailedForecast"),
        }

    save_json("weather_raw.json", weather_raw)
    print("✅ weather_raw.json updated")


if __name__ == "__main__":
    main()
