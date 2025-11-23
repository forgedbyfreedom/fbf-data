import json

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default

def clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))

def wind_risk(mph):
    try:
        if mph is None:
            return 0
        return clamp((float(mph) - 8) * 4)
    except:
        return 0

def rain_risk(pct):
    try:
        if pct is None:
            return 0
        return clamp(float(pct) * 0.7)
    except:
        return 0

def temp_risk(temp_f):
    try:
        if temp_f is None:
            return 0
        temp_f = float(temp_f)
        if temp_f < 32:
            return clamp((32 - temp_f) * 2.2)
        if temp_f > 90:
            return clamp((temp_f - 90) * 2.0)
        return 0
    except:
        return 0

def sport_weights(sport):
    s = (sport or "").lower()

    if s in ["nfl", "ncaaf"]:
        return {"wind": 0.45, "rain": 0.35, "temp": 0.20}

    # non-football ignored
    return None

def performance_tags(sport, wind, rain, temp):
    tags = []
    s = (sport or "").lower()

    try:
        if wind is not None and float(wind) >= 15:
            tags += ["high_wind", "passing_penalty", "kicking_penalty"]

        if rain is not None and float(rain) >= 50:
            tags += ["rain_game", "ball_security_risk"]

        if temp
