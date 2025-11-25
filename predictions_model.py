#!/usr/bin/env python3
"""
predictions_model.py
Simple feature-driven model:
- Uses spread, total, power ratings, weather, risk
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
    return 1 / (1 + math.exp(-x))


def build_features(game):
    """Extract features safely; handle None values gracefully."""
    odds = game.get("odds") or {}
    venue = game.get("venue") or {}
    weather = game.get("weather") or {}
    risk = game.get("weatherRisk") or {}

    # Spread / total default to 0 if absent
    spread = odds.get("spread", 0) or 0
    total = odds.get("total", 0) or 0

    # Weather defaults
    temp = weather.get("temperatureF")
    wind = weather.get("windSpeedMph")
    rain = weather.get("rainChancePct")

    temp = temp if isinstance(temp, (int, float)) else 70
    wind = wind if isinstance(wind, (int, float)) else 0
    rain = rain if isinstance(rain, (int, float)) else 0

    # Indoor override removes weather penalties
    indoor_flag = 1.0 if venue.get("indoor") else 0.0
    if indoor_flag == 1.0:
        wind = 0
        rain = 0

    # Risk score
    risk_score = risk.get("risk")
    risk_score = risk_score if isinstance(risk_score, (int, float)) else 0

    return {
        "spread": float(spread),
        "total": float(total),
        "temp": float(temp),
        "wind": float(wind),
        "rain": float(rain),
        "risk": float(risk_score),
        "indoor": indoor_flag,
    }


def predict(game):
    """
    Core prediction logic.
    - outdoor wind/rain reduces scoring
    - spread influences expected margin
    - risk reduces scoring & confidence
    """

    X = build_features(game)

    spread = X["spread"]
    total = X["total"]
    risk = X["risk"]

    # WEATHER ADJUSTMENT
    weather_penalty = (
        (X["wind"] * 0.25) +
        (X["rain"] * 0.15) +
        (risk * 2.5)
    )

    # indoor venues ignore weather
    if X["indoor"] == 1:
        weather_penalty = 0

    adjusted_total = max(20.0, total - weather_penalty)

    # Split scoring based on spread
    home_base = adjusted_total / 2 + (-spread / 2)
    away_base = adjusted_total / 2 + (spread / 2)

    # Clamp to minimum values
    home_score = max(3.0, home_base)
    away_score = max(3.0, away_base)

    # Win probability (simple logistic function)
    margin = home_score - away_score
    win_prob = sigmoid(margin / 6)

    # Confidence scaled to margin and weather risk
    confidence = max(5, min(100, (abs(margin) * 8) - (risk * 10)))

    return {
        "projected_home_score": round(home_score, 1),
        "projected_away_score": round(away_score, 1),
        "projected_total": round(home_score + away_score, 1),
        "projected_spread": round(home_score - away_score, 1),
        "win_probability_home": round(win_prob, 3),
        "confidence": int(confidence),
    }
