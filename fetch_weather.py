import os, json, time, requests
from datetime import datetime, timezone

COMBINED_PATH = "combined.json"
WEATHER_OUT_PATH = "weather_raw.json"
STADIUMS_OUTDOOR_PATH = "stadiums_outdoor.json"
STADIUMS_BY_TEAM_PATH = "fbs_stadiums.json"

NWS_USER_AGENT = os.getenv("NWS_USER_AGENT", "fbf-data (contact@forgedbyfreedom.com)")

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)

def nws_point_forecast(lat, lon):
    """
    Get simplified forecast values from NWS:
    - windSpeedMph (approx max next 12h)
    - rainChancePct (approx PoP max next 12h)
    - temperatureF (next period temp)
    """
    try:
        headers = {"User-Agent": NWS_USER_AGENT}

        # 1) points lookup
        p = requests.get(
            f"https://api.weather.gov/points/{lat},{lon}",
            headers=headers,
            timeout=10
        )
        if p.status_code != 200:
            return {"error": "points_lookup_failed"}

        points = p.json()
        forecast_url = points["properties"]["forecastHourly"]

        # 2) hourly forecast
        f = requests.get(forecast_url, headers=headers, timeout=10)
        if f.status_code != 200:
            return {"error": "forecast_failed"}

        periods = f.json()["properties"]["periods"][:12]

        temps = []
        winds = []
        pops = []

        for per in periods:
            t = per.get("temperature")
            if t is not None:
                temps.append(float(t))

            ws = per.get("windSpeed","0").split(" ")[0]
            try:
                winds.append(float(ws))
            except:
                pass

            pop = per.get("probabilityOfPrecipitation", {}).get("value")
            if pop is not None:
                pops.append(float(pop))

        return {
            "temperatureF": temps[0] if temps else None,
            "windSpeedMph": max(winds) if winds else None,
            "rainChancePct": max(pops) if pops else None
        }
    except Exception as e:
        return {"error": str(e)}

def main():
    combined = load_json(COMBINED_PATH, [])
    games = combined["data"] if isinstance(combined, dict) and "data" in combined else combined

    # stadium lookup tables
    outdoor = load_json(STADIUMS_OUTDOOR_PATH, {})
    by_team = load_json(STADIUMS_BY_TEAM_PATH, {})

    out = {}
    now_utc = datetime.now(timezone.utc).isoformat()

    for g in games:
        if not isinstance(g, dict):
            continue

        gid = g.get("game_id") or g.get("id")
        if not gid:
            continue

        sport = (g.get("sport") or "").lower()
        home = g.get("home_team") if isinstance(g.get("home_team"), dict) else {}
        home_id = str(home.get("id") or "")

        # Default response
        out[gid] = {"timestamp": now_utc}

        # Indoor / non-weather sports
        v = g.get("venue") if isinstance(g.get("venue"), dict) else {}
        if v.get("indoor") is True:
            out[gid].update({"indoor": True})
            continue

        # Find coords:
        coords = None

        # Prefer outdoor stadium coords if available
        if home_id and home_id in outdoor:
            coords = outdoor[home_id]

        # else any stadium coords we have (even indoor False might be missing)
        if not coords and home_id and home_id in by_team:
            coords = by_team[home_id]

        lat = coords.get("lat") if isinstance(coords, dict) else None
        lon = coords.get("lon") if isinstance(coords, dict) else None

        if not lat or not lon:
            out[gid].update({"error": "no_coords"})
            continue

        forecast = nws_point_forecast(lat, lon)

        if "error" in forecast:
            out[gid].update({"error": forecast["error"], "lat": lat, "lon": lon})
            continue

        out[gid].update({
            "lat": lat,
            "lon": lon,
            "temperatureF": forecast.get("temperatureF"),
            "windSpeedMph": forecast.get("windSpeedMph"),
            "rainChancePct": forecast.get("rainChancePct"),
        })

        time.sleep(0.15)

    save_json(WEATHER_OUT_PATH, out)
    print(f"[✅] weather_raw.json updated for {len(out)} games")

if __name__ == "__main__":
    main()
