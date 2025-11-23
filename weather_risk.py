import json, math, os
from datetime import datetime

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default

def clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))

def wind_risk(mph):
    # Meaningful football/baseball effects start ~12–15mph
    if mph is None: return 0
    return clamp((mph - 8) * 4)

def rain_risk(pct):
    if pct is None: return 0
    return clamp(pct * 0.7)

def temp_risk(temp_f):
    if temp_f is None: return 0
    # penalties for extreme cold or heat
    if temp_f < 32:
        return clamp((32 - temp_f) * 2.2)
    if temp_f > 90:
        return clamp((temp_f - 90) * 2.0)
    return 0

def sport_weights(sport):
    # tailor by sport
    sport = (sport or "").lower()
    if sport in ["nfl", "ncaaf"]:
        return dict(wind=0.45, rain=0.35, temp=0.20)
    if sport in ["mlb"]:
        return dict(wind=0.55, rain=0.30, temp=0.15)
    if sport in ["soccer", "mls", "epl"]:
        return dict(wind=0.30, rain=0.45, temp=0.25)
    if sport in ["nascar", "f1"]:
        return dict(wind=0.10, rain=0.65, temp=0.25)
    return dict(wind=0.35, rain=0.35, temp=0.30)

def performance_tags(sport, wind, rain, temp):
    tags = []

    s = (sport or "").lower()

    # wind
    if wind >= 15:
        tags += ["high_wind", "passing_penalty", "kicking_penalty"]
        if s == "mlb":
            tags += ["hr_suppression", "flyball_variance"]

    # rain/snow proxy from short forecast if you want later
    if rain is not None and rain >= 50:
        tags += ["rain_game", "ball_security_risk"]
        if s in ["mls", "soccer"]:
            tags += ["slower_pitch", "lower_xg"]

    # temperature
    if temp is not None and temp <= 32:
        tags += ["freezing_game", "run_rate_up", "fg_penalty"]
    if temp is not None and temp >= 90:
        tags += ["heat_game", "fatigue_risk"]

    return tags

def main():
    games = load_json("combined.json", [])
    weather = load_json("weather_raw.json", {})

    out = {}

    for g in games:
        gid = g.get("game_id") or g.get("id")
        if not gid:
            continue

        w = weather.get(gid, {})
        if w.get("indoor") or w.get("error"):
            out[gid] = {
                "indoor": bool(w.get("indoor")),
                "error": w.get("error")
            }
            continue

        wind = w.get("windSpeedMph")
        rain = w.get("rainChancePct")
        temp = w.get("temperatureF")
        sport = g.get("sport")

        wr = wind_risk(wind)
        rr = rain_risk(rain)
        tr = temp_risk(temp)

        weights = sport_weights(sport)
        overall = clamp(wr * weights["wind"] + rr * weights["rain"] + tr * weights["temp"])

        out[gid] = {
            "overallRisk": round(overall, 1),
            "windRisk": round(wr, 1),
            "rainRisk": round(rr, 1),
            "tempRisk": round(tr, 1),
            "tags": performance_tags(sport, wind, rain, temp)
        }

    with open("weather_risk.json", "w") as f:
        json.dump(out, f, indent=2)

    print(f"[✅] Weather risk scored for {len(out)} games.")

if __name__ == "__main__":
    main()
