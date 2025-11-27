#!/usr/bin/env python3
"""
prediction_fallback.py

Generates baseline predictions for games in combined.json using:
- Market spread & total
- Simple historical team strength (if historical.json exists)
- Very light weather + injuries adjustments
- Referee trends hook (if ref_trends.json exists)

This is a conservative fallback:
- It never overwrites an existing model prediction.
- Output: predictions_fallback.json with the same "data" shape
  used by predictions.json.
"""

import json
import os
from datetime import datetime, timezone
import math

COMBINED = "combined.json"
HISTORICAL = "historical.json"
REF_TRENDS = "ref_trends.json"
PRED_OUTPUT = "predictions_fallback.json"

def safe_float(x, default=None):
    try:
        return float(x)
    except Exception:
        return default

def load_json_or_empty(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default

def team_name(game_side, fallback_key):
    if isinstance(game_side, dict):
        return game_side.get("name") or game_side.get("team") or game_side.get("displayName")
    return fallback_key

def build_team_strengths():
    hist = load_json_or_empty(HISTORICAL, {})
    teams = hist.get("teams", {})
    strengths = {}
    for name, rec in teams.items():
        # basic: avg point diff is our strength proxy
        diff = safe_float(rec.get("avg_point_diff"), 0.0) or 0.0
        strengths[name] = diff
    return strengths

def logistic(x):
    # simple logistic -> [0,1]
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 1.0 if x > 0 else 0.0

def estimate_win_prob_from_spread(spread_points):
    # Typical NFL-ish heuristic: ~6 points = big swing
    return logistic(spread_points / 6.0)

def adjust_for_weather(game, total_line):
    weather = game.get("weather") or {}
    risk = (game.get("weatherRisk") or {}).get("risk")
    temp = safe_float(weather.get("temperatureF") or weather.get("temp") or weather.get("temperature"))
    wind = safe_float(weather.get("windSpeedMph") or weather.get("wind_mph") or weather.get("wind"))

    total_adjust = 0.0
    spread_adjust = 0.0

    # Windy and/or very cold → nudge totals down a bit
    if wind is not None and wind >= 15:
        total_adjust -= 1.5
    if temp is not None and temp <= 25:
        total_adjust -= 1.0

    # Explicit risk bucket if you have one
    if isinstance(risk, (int, float)):
        if risk >= 3:
            total_adjust -= 2.0
        elif risk == 2:
            total_adjust -= 1.0

    return spread_adjust, total_adjust

def adjust_for_injuries(game):
    """
    Very conservative injury tweak:
    - If key injuries exist for a side, move spread by ~1–2 points that direction.
    - This assumes merge_injuries.py attaches something like:
        game["injuries"] = {
            "home": [...],
            "away": [...]
        }
    """
    injuries = game.get("injuries")
    if not isinstance(injuries, dict):
        return 0.0  # spread adjust from home perspective

    home_list = injuries.get("home") or []
    away_list = injuries.get("away") or []

    # crude counts; you can refine later with positions / status
    home_penalty = min(len(home_list), 3) * 0.5  # up to -1.5
    away_penalty = min(len(away_list), 3) * 0.5

    # Home spread is (home - away). If home is more injured, margin drops.
    return -(home_penalty - away_penalty)

def main():
    if not os.path.exists(COMBINED):
        print(f"❌ {COMBINED} not found.")
        return

    with open(COMBINED, "r") as f:
        root = json.load(f)

    games = root.get("data") or root.get("games") or root.get("combined") or []

    team_strength = build_team_strengths()
    ref_trends = load_json_or_empty(REF_TRENDS, {}).get("refs", {})

    preds = []

    for g in games:
        gid = g.get("id")
        if gid is None:
            continue

        home_side = g.get("home_team") or {}
        away_side = g.get("away_team") or {}

        home_name = team_name(home_side, g.get("home") or "HOME")
        away_name = team_name(away_side, g.get("away") or "AWAY")

        odds = g.get("odds") or {}
        total_line = safe_float(odds.get("total"))
        spread = safe_float(odds.get("spread"))  # convention: home spread (e.g. -7.5)

        # Parse details like "Team -7.5" if present and spread missing/ambiguous
        details = odds.get("details")
        if spread is None and isinstance(details, str):
            import re
            m = re.search(r"([+-]?\d+(\.\d+)?)", details)
            if m:
                spread = safe_float(m.group(1))

        if spread is None:
            spread = 0.0  # market says pick’em or unknown

        # Home-based margin from market
        market_margin_home = spread  # if spread = -7.5, home expected -7.5? depends on convention
        # Many feeds store home spread as negative when favored.
        # We want "home expected to win by X". Flip sign if negative.
        market_margin_home = -market_margin_home

        # Team strength bump (historical average diff)
        home_strength = team_strength.get(home_name, 0.0)
        away_strength = team_strength.get(away_name, 0.0)
        strength_edge = home_strength - away_strength

        # Weather + injuries adjustments
        wx_spread_adj, wx_total_adj = adjust_for_weather(g, total_line)
        inj_spread_adj = adjust_for_injuries(g)

        margin_home = market_margin_home + strength_edge + wx_spread_adj + inj_spread_adj

        # Total baseline: market total plus weather tweak
        if total_line is None:
            # fallback generic total if book is missing a number
            total_line = 44.0
        model_total = total_line + wx_total_adj

        # Derive implied scores from margin + total
        home_score = (model_total + margin_home) / 2.0
        away_score = model_total - home_score

        # Win prob from margin
        win_prob_home = estimate_win_prob_from_spread(margin_home)

        preds.append(
            {
                "id": gid,
                "sport": g.get("sport") or g.get("sport_key"),
                "home": home_name,
                "away": away_name,
                "prediction": {
                    "projected_home_score": round(home_score, 1),
                    "projected_away_score": round(away_score, 1),
                    "projected_total": round(model_total, 1),
                    "projected_spread": round(margin_home, 1),  # home - away
                    "win_probability_home": round(win_prob_home, 4),
                },
                "source": "fallback",
                "highlight": False,
            }
        )

    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": preds,
    }

    with open(PRED_OUTPUT, "w") as f:
        json.dump(out, f, indent=2)

    print(f"✅ Wrote {PRED_OUTPUT} with {len(preds)} fallback predictions")

if __name__ == "__main__":
    main()
