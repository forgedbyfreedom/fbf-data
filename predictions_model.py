#!/usr/bin/env python3
"""
predictions_model.py

Goal:
- Always produce predictions for all games in combined.json.
- If ML model exists -> use it.
- If not -> fallback heuristic (favorite + spread + home + weather + injuries).

Outputs per game:
{
  "id": ...,
  "sport": ...,
  "pick_side": "HOME" | "AWAY",
  "pick_team": "...",
  "confidence": 0-100,
  "high_confidence": bool,
  "edge": float,          # est margin vs spread
  "pred_margin": float,   # predicted home margin (home - away)
  "pred_total": float,    # predicted game total
  "notes": [...]
}
"""

import json
import math
from pathlib import Path

import numpy as np
import joblib

BASE = Path(__file__).resolve().parent
MODEL_FILE = BASE / "model.pkl"          # optional
SCALER_FILE = BASE / "scaler.pkl"        # optional


# ---------------------------
# Helpers
# ---------------------------

def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def safe_get(d, keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def implied_favorite(game):
    """
    Determine favorite from tagged favorites or odds.details.
    Returns:
      fav_side: "HOME" / "AWAY" / None
      fav_team_name: str or None
    """
    fav = game.get("favorite")
    if fav:
        # favorite sometimes like "SF -7" or "DET -3"
        fav_abbr = fav.split()[0].strip()
        home_abbr = safe_get(game, ["home_team","abbr"])
        away_abbr = safe_get(game, ["away_team","abbr"])
        if fav_abbr == home_abbr:
            return "HOME", safe_get(game, ["home_team","name"])
        if fav_abbr == away_abbr:
            return "AWAY", safe_get(game, ["away_team","name"])

    odds_details = safe_get(game, ["odds","details"], "")
    if isinstance(odds_details, str) and odds_details.strip():
        token = odds_details.split()[0].strip()
        home_abbr = safe_get(game, ["home_team","abbr"])
        away_abbr = safe_get(game, ["away_team","abbr"])
        if token == home_abbr:
            return "HOME", safe_get(game, ["home_team","name"])
        if token == away_abbr:
            return "AWAY", safe_get(game, ["away_team","name"])

    return None, None


def is_indoor(game):
    return bool(safe_get(game, ["venue","indoor"], False))


def weather_penalty(game):
    """
    Convert weatherRisk into a numeric penalty to scoring / predictability.
    If weatherRisk missing, return 0.
    """
    wr = game.get("weatherRisk") or {}
    if not isinstance(wr, dict):
        return 0.0

    # normalize common fields if present
    wind = float(wr.get("windRisk", 0) or 0)
    rain = float(wr.get("rainRisk", 0) or 0)
    snow = float(wr.get("snowRisk", 0) or 0)
    storm = float(wr.get("stormRisk", 0) or 0)

    return clamp((wind + rain + snow + storm) / 4.0, 0.0, 1.0)


def injury_penalty(game):
    """
    Use injury counts if present to penalize confidence.
    """
    ih = float(game.get("injury_count_home", 0) or 0)
    ia = float(game.get("injury_count_away", 0) or 0)
    total = ih + ia
    # scale to 0..1
    return clamp(total / 10.0, 0.0, 1.0)


def sport_baseline_total(sport):
    """
    fallback totals by sport when none available
    """
    s = (sport or "").lower()
    if s == "nfl": return 44.0
    if s == "ncaaf": return 52.0
    if s == "nba": return 226.0
    if s == "ncaab": return 141.0
    if s == "nhl": return 6.3
    if s == "mlb": return 8.6
    return 0.0


# ---------------------------
# Feature extraction
# ---------------------------

def extract_features(game):
    """
    Build a compact numeric feature vector.
    This is used only if an ML model exists.
    """
    sport = (game.get("sport") or "").lower()
    spread = safe_get(game, ["odds","spread"], 0.0) or 0.0
    total = safe_get(game, ["odds","total"], 0.0) or sport_baseline_total(sport)

    fav_side, _ = implied_favorite(game)
    fav_home = 1.0 if fav_side == "HOME" else 0.0
    fav_away = 1.0 if fav_side == "AWAY" else 0.0

    indoor = 1.0 if is_indoor(game) else 0.0
    wpen = weather_penalty(game)
    ipen = injury_penalty(game)

    # crude home advantage by sport
    home_adv = 1.0
    if sport in ("nba","ncaab"): home_adv = 2.0
    if sport in ("nfl","ncaaf"): home_adv = 2.5
    if sport in ("nhl","mlb"): home_adv = 0.4

    return np.array([
        spread,
        total,
        fav_home,
        fav_away,
        indoor,
        wpen,
        ipen,
        home_adv
    ], dtype=float)


# ---------------------------
# Model wrapper + fallback
# ---------------------------

class PredictionsEngine:
    def __init__(self):
        self.model = None
        self.scaler = None

        if MODEL_FILE.exists():
            try:
                self.model = joblib.load(MODEL_FILE)
            except Exception:
                self.model = None

        if SCALER_FILE.exists():
            try:
                self.scaler = joblib.load(SCALER_FILE)
            except Exception:
                self.scaler = None

    def predict_game_ml(self, game):
        """
        Use ML model to predict home win prob and margin.
        Fallback if model output shape unexpected.
        """
        x = extract_features(game).reshape(1, -1)
        if self.scaler is not None:
            x = self.scaler.transform(x)

        # Two possible model types:
        # 1) classifier w/ predict_proba -> win probability
        # 2) regressor -> predicted margin directly
        pred_margin = 0.0
        win_prob_home = 0.5

        try:
            if hasattr(self.model, "predict_proba"):
                win_prob_home = float(self.model.predict_proba(x)[0][1])
                # margin proxy from prob
                pred_margin = (win_prob_home - 0.5) * 20.0
            else:
                pred_margin = float(self.model.predict(x)[0])
                win_prob_home = 1 / (1 + math.exp(-pred_margin / 7.0))
        except Exception:
            win_prob_home = 0.5
            pred_margin = 0.0

        return win_prob_home, pred_margin

    def predict_game_fallback(self, game):
        """
        Heuristic prediction:
        - Use favorite and spread to set a predicted margin
        - Add home advantage
        - Reduce confidence for weather/injuries
        """
        sport = (game.get("sport") or "").lower()
        spread = safe_get(game, ["odds","spread"], 0.0) or 0.0
        total = safe_get(game, ["odds","total"], 0.0) or sport_baseline_total(sport)

        fav_side, _ = implied_favorite(game)

        # base margin from spread: spread is shown from favorite POV sometimes.
        # We assume ESPN spread positive favors AWAY in some feeds; so normalize:
        # If favorite is home -> home margin = abs(spread)
        # If favorite is away -> home margin = -abs(spread)
        if fav_side == "HOME":
            base_margin = abs(spread)
        elif fav_side == "AWAY":
            base_margin = -abs(spread)
        else:
            base_margin = 0.0

        # home advantage nudges toward home
        home_adv = 0.0
        if sport in ("nba","ncaab"):
            home_adv = 1.5
        elif sport in ("nfl","ncaaf"):
            home_adv = 2.0
        elif sport in ("nhl","mlb"):
            home_adv = 0.3

        pred_margin = base_margin + home_adv

        # win prob from margin
        win_prob_home = 1 / (1 + math.exp(-pred_margin / 7.0))

        # total adjustment for weather (outdoor only)
        wpen = weather_penalty(game)
        if not is_indoor(game):
            total *= (1.0 - 0.07 * wpen)

        pred_total = total

        return win_prob_home, pred_margin, pred_total

    def build_prediction(self, game):
        """
        Return full prediction dict.
        """
        notes = []
        sport = (game.get("sport") or "").lower()
        spread = safe_get(game, ["odds","spread"], 0.0) or 0.0
        total = safe_get(game, ["odds","total"], 0.0) or sport_baseline_total(sport)

        if self.model is not None:
            win_prob_home, pred_margin = self.predict_game_ml(game)
            # total still needs fallback shaping
            pred_total = total
            notes.append("ml_model")
        else:
            win_prob_home, pred_margin, pred_total = self.predict_game_fallback(game)
            notes.append("fallback_logic")

        # decide side
        if win_prob_home >= 0.5:
            pick_side = "HOME"
            pick_team = safe_get(game, ["home_team","name"], "HOME")
        else:
            pick_side = "AWAY"
            pick_team = safe_get(game, ["away_team","name"], "AWAY")

        # edge vs spread (home margin - spread normalized)
        # if pick is home, edge = pred_margin - abs(spread)
        # if pick is away, edge = abs(pred_margin) - abs(spread)
        edge = 0.0
        if spread:
            if pick_side == "HOME":
                edge = pred_margin - abs(spread)
            else:
                edge = abs(pred_margin) - abs(spread)

        # confidence shaping
        base_conf = abs(win_prob_home - 0.5) * 200.0  # 0..100
        wpen = weather_penalty(game)
        ipen = injury_penalty(game)

        conf = base_conf
        conf *= (1.0 - 0.35*wpen)
        conf *= (1.0 - 0.25*ipen)

        # minor indoor boost
        if is_indoor(game):
            conf *= 1.05

        conf = clamp(conf, 1.0, 99.0)

        high_conf = conf >= 70.0

        return {
            "id": game.get("id"),
            "sport": sport,
            "name": game.get("name"),
            "shortName": game.get("shortName"),
            "date_local": game.get("date_local") or safe_get(game, ["commence_time"]),
            "pick_side": pick_side,
            "pick_team": pick_team,
            "confidence": round(conf, 1),
            "high_confidence": bool(high_conf),
            "edge": round(edge, 2),
            "pred_margin": round(pred_margin, 2),
            "pred_total": round(pred_total, 2),
            "notes": notes
        }


def predict_games(combined_data):
    """
    combined_data: dict loaded from combined.json
    returns list of prediction dicts
    """
    engine = PredictionsEngine()
    games = combined_data.get("data", [])
    preds = []

    for g in games:
        try:
            preds.append(engine.build_prediction(g))
        except Exception as e:
            preds.append({
                "id": g.get("id"),
                "sport": (g.get("sport") or "").lower(),
                "name": g.get("name"),
                "pick_side": None,
                "pick_team": None,
                "confidence": 0,
                "high_confidence": False,
                "edge": 0,
                "pred_margin": 0,
                "pred_total": 0,
                "notes": [f"error:{e}"]
            })

    return preds
