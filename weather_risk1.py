import json

def load_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return {}

def compute_risk(entry):
    """Very simple weather risk logic."""
    temp = entry.get("temp")
    wind = entry.get("wind")
    precip = entry.get("precip")

    risk = 0
    details = []

    if temp is None:
        return 0, ["missing_temp"]

    # Temperature risk
    if temp < 32:
        risk += 2
        details.append("cold")
    elif temp > 90:
        risk += 2
        details.append("heat")

    # Wind risk
    if wind is not None and wind > 20:
        risk += 2
        details.append("windy")

    # Precip risk
    if precip and precip > 40:
        risk += 2
        details.append("precip")

    return risk, details

def main():
    weather = load_json("weather.json")
    risk_output = {"timestamp": None, "data": {}}

    risk_output["timestamp"] = weather.get("timestamp")

    for entry in weather.get("data", []):
        lat = entry.get("lat")
        lon = entry.get("lon")
        if lat is None or lon is None:
            continue

        key = f"{lat},{lon}"

        r, details = compute_risk(entry)
        risk_output["data"][key] = {
            "risk": r,
            "details": details
        }

    print(f"✅ Weather risk scores computed for {len(risk_output['data'])} locations.")

    with open("weather_risk1.json", "w") as f:
        json.dump(risk_output, f, indent=2)

if __name__ == "__main__":
    main()
