#!/usr/bin/env python3
"""
build_predictions.py
Rule-based picks using:
- spread -> base win prob
- weather (outdoor only)
- injuries summary
- referee trends (if any)

Writes predictions.json
Also attaches g["picks"] into combined.json for the UI.
"""

import json, os, math
from datetime import datetime, timezone

OUT_FILE = "predictions.json"

def logistic(x):
    return 1 / (1 + math.exp(-x))

def base_prob_from_spread(spread):
    # simple mapping: -3 ~ 58%, -7 ~ 68%, -14 ~ 80%
    if spread is None:
        return 0.5
    return logistic(-spread / 6.0)

def weather_adjust(prob, weather):
    if not weather:
        return prob
    wind = weather.get("wind_mph") or 0
    precip = weather.get("precip_prob") or 0
    temp = weather.get("temp_f")

    # wind/precip reduce favorite edge slightly + nudge under
    prob_adj = prob
    if wind >= 15:
        prob_adj -= 0.02
    if precip >= 0.4:
        prob_adj -= 0.02
    if temp is not None and temp <= 25:
        prob_adj -= 0.01

    return max(0.05, min(0.95, prob_adj))

def injury_adjust(prob, home_inj, away_inj, fav_team, home_team):
    if not fav_team:
        return prob
    fav_is_home = (fav_team == home_team)

    def out_count(x):
        return (x or {}).get("out", 0)

    fav_inj = home_inj if fav_is_home else away_inj
    dog_inj = away_inj if fav_is_home else home_inj

    diff_out = out_count(dog_inj) - out_count(fav_inj)
    # each net "out" in favor gives ~1.5% edge
    prob_adj = prob + 0.015 * diff_out
    return max(0.05, min(0.95, prob_adj))

def total_pick(total, weather):
    if total is None:
        return None
    wind = (weather or {}).get("wind_mph") or 0
    precip = (weather or {}).get("precip_prob") or 0
    adj_total = total
    if wind >= 15:
        adj_total -= 1.0
    if precip >= 0.4:
        adj_total -= 0.5
    return adj_total

def main():
    if not os.path.exists("combined.json"):
        print("❌ combined.json missing")
        return

    with open("combined.json","r",encoding="utf-8") as f:
        payload = json.load(f)

    games = payload.get("data", [])
    preds = {"timestamp": datetime.now(timezone.utc).isoformat(), "data": []}

    for g in games:
        fav_team = g.get("fav_team")
        dog_team = g.get("dog_team")
        spread = g.get("fav_spread")
        total = g.get("total")
        weather = g.get("weather")
        home_inj = g.get("home_injuries", {}).get("summary") if isinstance(g.get("home_injuries"), dict) else g.get("home_injuries")
        away_inj = g.get("away_injuries", {}).get("summary") if isinstance(g.get("away_injuries"), dict) else g.get("away_injuries")

        base_prob = base_prob_from_spread(spread)
        prob = weather_adjust(base_prob, weather)
        prob = injury_adjust(prob, home_inj, away_inj, fav_team, g.get("home_team"))

        # Picks
        su_pick = fav_team if prob >= 0.5 else dog_team
        ats_pick = fav_team if spread is not None else None
        adj_total = total_pick(total, weather)
        ou_pick = None
        if adj_total is not None and total is not None:
            ou_pick = "Under" if adj_total < total else "Over"

        picks = {
            "SU_prob": round(prob * 100, 1),
            "SU_pick": su_pick,
            "ATS_pick": ats_pick,
            "OU_pick": ou_pick,
        }

        g["picks"] = picks
        preds["data"].append({
            "matchup": g.get("matchup"),
            "sport_key": g.get("sport_key"),
            "fav_team": fav_team,
            "dog_team": dog_team,
            "spread": spread,
            "total": total,
            "picks": picks,
        })

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(preds, f, indent=2)

    payload["data"] = games
    with open("combined.json","w",encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"[✅] Predictions built for {len(preds['data'])} games.")

if __name__ == "__main__":
    main()
