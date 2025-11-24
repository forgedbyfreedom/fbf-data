#!/usr/bin/env python3
"""
weather_risk1.py
Reads: combined.json + weather_raw.json
Writes: weather_risk1.json
"""

import json


def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
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
    if s == "mlb":
        return {"wind": 0.55, "rain": 0.30, "temp": 0.15}
    if s in ["soccer", "mls", "epl"]:
        return {"wind": 0.30, "rain": 0.45, "temp": 0.25}
    if s in ["nascar", "f1"]:
        return {"wind": 0.10, "rain": 0.65, "temp": 0.25}

    return {"wind": 0.35, "rain": 0.35, "temp": 0.30}


def performance_tags(sport, wind, rain, temp):
    tags = []
    s = (sport or "").lower()

    try:
        if wind is not None and float(wind) >= 15:
            tags += ["high_wind", "passing_penalty", "kicking_penalty"]
            if s == "mlb":
                tags.append("hr_suppression")

        if rain is not None and float(rain) >= 50:
            tags += ["rain_game", "ball_security_risk"]

        if temp is not None and float(temp) <= 32:
            tags += ["freezing_game", "run_rate_up"]

        if temp is not None and float(temp) >= 90:
            tags += ["heat_game", "fatigue_risk"]

    except:
        pass

    return tags


def main():
    games = load_json("combined.json", {})
    weather = load_json("weather_raw.json", {})

    # combined payload format: {timestamp, count, data:[...]}
    if isinstance(games, dict) and "data" in games:
        games = games["data"]

    out = {}

    for g in games:
        if not isinstance(g, dict):
            continue

        gid = g.get("id") or g.get("game_id")
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
        score = clamp(
            wr * weights["wind"]
            + rr * weights["rain"]
            + tr * weights["temp"]
        )

        out[gid] = {
            "overallRisk": round(score, 1),
            "windRisk": round(wr, 1),
            "rainRisk": round(rr, 1),
            "tempRisk": round(tr, 1),
            "tags": performance_tags(sport, wind, rain, temp),
        }

    with open("weather_risk1.json", "w") as f:
        json.dump(out, f, indent=2)

    print(f"[✅] Weather risk scored for {len(out)} games.")


if __name__ == "__main__":
    main()
