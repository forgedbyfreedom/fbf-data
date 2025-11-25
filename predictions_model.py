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
    """Extract numerical features safely."""
    odds = game.get("odds", {})
    venue = game.get("venue", {})
    weather = game.get("weather", {})
    risk = game.get("weatherRisk", {})

    spread = odds.get("spread", 0)
    total = odds.get("total", 0)

    # Weather F
    temp = weather.get("temperatureF") or 70
    wind = weather.get("windSpeedMph") or 0
    rain = weather.get("rainChancePct") or 0

    # Indoor override
    if venue.get("indoor"):
        wind = 0
        rain = 0

    # Risk scoring (0–3)
    risk_score = (risk.get("risk") or 0)

    return {
        "spread": float(spread),
        "total": float(total),
        "temp": float(temp),
        "wind": float(wind),
        "rain": float(rain),
        "risk": float(risk_score),
        "indoor": 1.0 if venue.get("indoor") else 0.0,
    }


def predict(game):
    """
    Core prediction logic.
    Tuned so:
      - outdoor wind/rain reduces scoring
      - spread influences expected margin
      - risk reduces overall scoring & confidence
    """

    X = build_features(game)

    spread = X["spread"]
    total = X["total"]
    risk = X["risk"]

    # --- WEATHER ADJUSTMENT ---
    weather_penalty = (
        (X["wind"] * 0.25) +
        (X["rain"] * 0.15) +
        (risk * 2.5)
    )

    # indoor → no penalty
    if X["indoor"] == 1:
        weather_penalty = 0

    adjusted_total = max(20.0, total - weather_penalty)

    # --- SCORE SPLIT ---
    # Spread splits scoring
    home_base = adjusted_total / 2 + (-spread / 2)
    away_base = adjusted_total / 2 + (spread / 2)

    # clamp
    home_score = max(3.0, home_base)
    away_score = max(3.0, away_base)

    # --- WIN PROBABILITY ---
    margin = home_score - away_score
    win_prob = sigmoid(margin / 6)

    # --- CONFIDENCE ---
    confidence = max(5, min(100, (abs(margin) * 8) - (risk * 10)))

    return {
        "projected_home_score": round(home_score, 1),
        "projected_away_score": round(away_score, 1),
        "projected_total": round(home_score + away_score, 1),
        "projected_spread": round(home_score - away_score, 1),
        "win_probability_home": round(win_prob, 3),
        "confidence": int(confidence),
    }
