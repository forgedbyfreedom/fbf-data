#!/usr/bin/env python3
"""
predictions_model.py
Feature-driven prediction model:
- Uses spread, total, power ratings, weather, risk, injuries, rest, elo, h2h
- Outputs:
    projected_spread
    projected_total
    projected_home_score
    projected_away_score
    win_probability
    confidence
"""

import math


def sigmoid(x):
    try:
        return 1 / (1 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def build_features(game):
    """Extract features safely; handle None values gracefully."""
    odds = game.get("odds") or {}
    venue = game.get("venue") or {}
    weather = game.get("weather") or {}
    risk = game.get("weatherRisk") or {}

    spread = odds.get("spread", 0) or 0
    total = odds.get("total", 0) or 0
    has_odds = odds.get("spread") is not None

    temp = weather.get("temperatureF")
    wind = weather.get("windSpeedMph")
    rain = weather.get("rainChancePct")

    temp = temp if isinstance(temp, (int, float)) else 70
    wind = wind if isinstance(wind, (int, float)) else 5
    rain = rain if isinstance(rain, (int, float)) else 0

    indoor_flag = 1.0 if venue.get("indoor") else 0.0
    if indoor_flag == 1.0:
        wind = 0
        rain = 0

    risk_score = risk.get("risk")
    risk_score = risk_score if isinstance(risk_score, (int, float)) else 0

    # Injury counts (merged by merge_injuries.py)
    home_inj = game.get("injury_count_home", 0) or 0
    away_inj = game.get("injury_count_away", 0) or 0

    # Rest days (added by build_rest_days.py via feature_engineering)
    rest_diff = game.get("rest_diff_days", 0) or 0

    # Elo difference (added by build_elo.py via feature_engineering)
    elo_diff = game.get("elo_diff", 0) or 0

    # H2H historical margin average
    h2h_margin = game.get("h2h_margin_avg", 0) or 0

    return {
        "spread": float(spread),
        "total": float(total),
        "has_odds": has_odds,
        "temp": float(temp),
        "wind": float(wind),
        "rain": float(rain),
        "risk": float(risk_score),
        "indoor": indoor_flag,
        "home_injuries": int(home_inj),
        "away_injuries": int(away_inj),
        "rest_diff": float(rest_diff),
        "elo_diff": float(elo_diff),
        "h2h_margin": float(h2h_margin),
    }


def predict(game):
    """
    Core prediction logic.
    - spread drives expected margin
    - weather reduces scoring (outdoor only)
    - injuries shift margin toward healthier team
    - rest advantage gives slight edge
    - elo difference captures team quality beyond spread
    - h2h trends provide historical context
    """

    X = build_features(game)

    spread = X["spread"]
    total = X["total"]
    risk = X["risk"]

    # WEATHER ADJUSTMENT
    # NBA, NHL, NCAAB, NCAAW are always played indoors — never apply weather
    INDOOR_SPORTS = {"nba", "nhl", "ncaab", "ncaaw"}
    sport = (game.get("sport") or "").lower()
    weather_penalty = 0.0
    if sport not in INDOOR_SPORTS and X["indoor"] != 1:
        weather_penalty = (
            (X["wind"] * 0.25) +
            (X["rain"] * 0.15) +
            (risk * 2.5)
        )

    adjusted_total = max(20.0, total - weather_penalty)

    # INJURY ADJUSTMENT: each injury shifts ~0.3 points against that team
    injury_shift = (X["away_injuries"] - X["home_injuries"]) * 0.3

    # REST ADJUSTMENT: ~0.5 points per day of rest advantage
    rest_shift = X["rest_diff"] * 0.5

    # ELO ADJUSTMENT: scale elo_diff to approximate point value
    # 100 Elo points ~ 3 points of spread equivalent
    elo_shift = X["elo_diff"] * 0.03

    # H2H ADJUSTMENT: historical margin average gets small weight
    h2h_shift = X["h2h_margin"] * 0.15

    # Split scoring based on spread + adjustments
    total_shift = injury_shift + rest_shift + elo_shift + h2h_shift
    home_base = adjusted_total / 2 + (-spread / 2) + (total_shift / 2)
    away_base = adjusted_total / 2 + (spread / 2) - (total_shift / 2)

    home_score = max(3.0, home_base)
    away_score = max(3.0, away_base)

    # Win probability (logistic function)
    margin = home_score - away_score
    win_prob = sigmoid(margin / 6)

    # CONFIDENCE: logistic-based (replaces old linear formula)
    # margin of 7 -> ~85%, margin of 3 -> ~65%, margin of 14 -> ~95%
    base_conf = sigmoid(abs(margin) / 4.0) * 100
    data_penalty = 0 if X["has_odds"] else -20
    weather_conf_penalty = risk * 5
    confidence = max(5, min(95, base_conf + data_penalty - weather_conf_penalty))

    return {
        "projected_home_score": round(home_score, 1),
        "projected_away_score": round(away_score, 1),
        "projected_total": round(home_score + away_score, 1),
        "projected_spread": round(home_score - away_score, 1),
        "win_probability_home": round(win_prob, 3),
        "confidence": int(confidence),
    }
