import json
import math

# -------------------------------------
# Load NWS weather file
# -------------------------------------
with open("weather.json", "r") as f:
    weather = json.load(f)

risk_scores = {}

# -------------------------------------
# Helper to clamp values
# -------------------------------------
def clamp(v, lo, hi):
    return max(lo, min(hi, v))

# -------------------------------------
# Compute risk score for 1 game’s forecast
# -------------------------------------
def compute_risk(data):
    """
    Compute a weather impact score from 0–100
    Higher = worse weather
    """

    if not data:
        return 0

    temp = data.get("temperature")
    wind = data.get("windSpeed")
    rain = data.get("probabilityOfPrecipitation")
    snow = data.get("snowfallAmount")

    # Normalize temperature
    if temp is None:
        temp_score = 0
    else:
        # Bad if < 32°F or > 90°F
        if temp < 32:
            temp_score = clamp((32 - temp) * 1.5, 0, 25)
        elif temp > 90:
            temp_score = clamp((temp - 90) * 1.2, 0, 25)
        else:
            temp_score = 0

    # Normalize wind
    if wind is None:
        wind_score = 0
    else:
        try:
            w = float(wind)
        except:
            w = 0
        wind_score = clamp((w - 10) * 1.8, 0, 30)

    # Normalize rain
    if rain is None:
        rain_score = 0
    else:
        rain_score = clamp(rain * 0.6, 0, 25)

    # Normalize snow
    if snow is None:
        snow_score = 0
    else:
        snow_score = clamp(snow * 2.0, 0, 40)

    # Final risk score
    total = temp_score + wind_score + rain_score + snow_score
    return clamp(total, 0, 100)

# -------------------------------------
# Process all games
# -------------------------------------
for game_id, data in weather.items():
    try:
        risk_scores[game_id] = {
            "risk": compute_risk(data),
            "details": data
        }
    except Exception as e:
        risk_scores[game_id] = {"risk": 0, "error": str(e)}

# -------------------------------------
# Save output
# -------------------------------------
with open("weather_risk1.json", "w") as f:
    json.dump(risk_scores, f, indent=2)

print("✅ Weather risk scores computed for", len(risk_scores), "games.")
