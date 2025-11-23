import json
import requests
from time import sleep

USER_AGENT = "fbf-data-weather (contact@forgedbyfreedom.com)"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/geo+json"
}

def get_grid_info(lat, lon):
    url = f"https://api.weather.gov/points/{lat},{lon}"
    r = requests.get(url, headers=HEADERS, timeout=10)

    if r.status_code != 200:
        return None

    data = r.json()
    props = data.get("properties", {})

    return {
        "gridId": props.get("gridId"),
        "gridX": props.get("gridX"),
        "gridY": props.get("gridY"),
        "forecast": props.get("forecast"),
        "forecastHourly": props.get("forecastHourly"),
        "observationStations": props.get("observationStations")
    }


def get_forecast(url):
    r = requests.get(url, headers=HEADERS, timeout=10)
    if r.status_code != 200:
        return None
    return r.json()


def load_games():
    with open("combined.json", "r") as f:
        return json.load(f)


def main():
    games = load_games()
    weather_results = {}

    for game in games:
        gid = game["game_id"]

        lat = game.get("latitude")
        lon = game.get("longitude")

        if not lat or not lon:
            weather_results[gid] = {"error": "Missing coords"}
            continue

        grid = get_grid_info(lat, lon)
        if not grid or not grid["forecast"]:
            weather_results[gid] = {"error": "No forecast grid"}
            continue

        sleep(0.75)  # avoid hitting rate limits

        forecast_data = get_forecast(grid["forecast"])
        if not forecast_data:
            weather_results[gid] = {"error": "Forecast error"}
            continue

        try:
            periods = forecast_data["properties"]["periods"]
            short_forecast = periods[0]["shortForecast"]
            temperature = periods[0]["temperature"]
            wind = periods[0]["windSpeed"]
            rain = periods[0].get("probabilityOfPrecipitation", {}).get("value")
        except Exception:
            weather_results[gid] = {"error": "Parse error"}
            continue

        weather_results[gid] = {
            "shortForecast": short_forecast,
            "temperature": temperature,
            "wind": wind,
            "rainChance": rain
        }

    with open("weather.json", "w") as f:
        json.dump(weather_results, f, indent=2)

    print(f"[✅] Weather updated for {len(weather_results)} games.")


if __name__ == "__main__":
    main()
