import json
import time
import requests

OUTDOOR_PATH = "stadiums_outdoor.json"
WEATHER_RAW_PATH = "weather_raw.json"

UA = "fbf-data (contact@forgedbyfreedom.com)"
NWS_POINTS = "https://api.weather.gov/points/{lat},{lon}"

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)

def safe_get(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=12)
        if not r.ok:
            return None
        return r.json()
    except Exception:
        return None

def main():
    stadiums = load_json(OUTDOOR_PATH, {})
    if not isinstance(stadiums, dict):
        stadiums = {}

    out = {}

    for sid, s in stadiums.items():
        if not isinstance(s, dict):
            continue

        lat = s.get("lat")
        lon = s.get("lon")

        if not lat or not lon:
            out[sid] = {"error": "no_coords"}
            continue

        points = safe_get(NWS_POINTS.format(lat=lat, lon=lon))
        if not points:
            out[sid] = {"error": "nws_points_fail"}
            continue

        forecast_url = (points.get("properties") or {}).get("forecastHourly")
        if not forecast_url:
            out[sid] = {"error": "no_forecast_url"}
            continue

        forecast = safe_get(forecast_url)
        if not forecast:
            out[sid] = {"error": "forecast_fail"}
            continue

        periods = (forecast.get("properties") or {}).get("periods") or []
        if not periods:
            out[sid] = {"error": "no_periods"}
            continue

        # Take next 6 hours and compute max wind, max rain chance, temp
        next_hours = periods[:6]

        winds = []
        rains = []
        temps = []

        for p in next_hours:
            try:
                wstr = p.get("windSpeed", "0 mph")
                mph = float(wstr.split()[0])
                winds.append(mph)
            except Exception:
                pass

            try:
                rains.append(float((p.get("probabilityOfPrecipitation") or {}).get("value") or 0))
            except Exception:
                pass

            try:
                temps.append(float(p.get("temperature")))
            except Exception:
                pass

        out[sid] = {
            "windSpeedMph": max(winds) if winds else 0,
            "rainChancePct": max(rains) if rains else 0,
            "temperatureF": temps[0] if temps else None,
            "source": "NWS",
            "stadium": {
                "name": s.get("name"),
                "city": s.get("city"),
                "state": s.get("state"),
            }
        }

        time.sleep(0.35)

    save_json(WEATHER_RAW_PATH, out)
    print("FETCH WEATHER FILE UPDATED SUCCESSFULLY")

if __name__ == "__main__":
    main()
