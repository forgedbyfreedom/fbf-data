#!/usr/bin/env python3
"""
build_predictions.py

Server-side model that reads:
  - combined.json   (odds from The Odds API)
  - power_ratings.json
  - injuries.json
  - weather.json
  - referees.json

and produces:
  - predictions.json

Per-game output schema:

{
  "sport_key": str,
  "matchup": "Away Team@Home Team",
  "home_team": str,
  "away_team": str,
  "commence_time": ISO8601 str,

  "su_pick": "Team Name",
  "ats_pick": "Team +3.5" or "Team -6.5",
  "ou_pick": "Over 47.5" or "Under 47.5",

  "su_conf": float (0–100),
  "ats_conf": float (0–100),
  "ou_conf": float (0–100),

  "fav_team": str or null,
  "dog_team": str or null,
  "fav_spread": float or null,
  "dog_spread": float or null,
  "spread": float or null,
  "total": float or null,
  "book": str,
  "fetched_at": ISO8601 str
}

This is a *reasonable* model using:
  - power ratings
  - home field
  - injuries (if mapped in injuries.json)
  - weather (if mapped in weather.json)
  - referee / total bias (if mapped in referees.json)

You can tune the helper functions:
  - get_power_rating(...)
  - get_injury_penalty(...)
  - get_weather_adjustment(...)
  - get_ref_total_adjustment(...)
to match your exact JSON structure.
"""

import os
import json
import math
import datetime
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def load_json(filename: str, default: Any) -> Any:
    path = os.path.join(ROOT_DIR, filename)
    if not os.path.exists(path):
        print(f"[⚠️] {filename} not found, using defaults.")
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[⚠️] Failed to load {filename}: {e}")
        return default


def format_spread_value(val: float) -> str:
    """Format a spread with sign, e.g. -6.5, +3, PK."""
    if val is None:
        return ""
    if abs(val) < 1e-6:
        return "PK"
    if val > 0:
        return f"+{val:g}"
    return f"{val:g}"


# Rough home-field advantages by sport (tune as you like)
HOME_FIELD_BY_SPORT: Dict[str, float] = {
    "americanfootball_nfl": 2.5,
    "americanfootball_ncaaf": 3.0,
    "basketball_nba": 2.5,
    "basketball_ncaab": 3.5,
    "icehockey_nhl": 0.5,
    "mma_mixed_martial_arts": 0.0,  # neutral cage, usually
}


# ---------------------------------------------------------------------------
# Data access helpers – these try to be flexible with your JSON shape
# ---------------------------------------------------------------------------

def get_power_rating(team: str, sport_key: str, power_data: Any) -> float:
    """
    Try a few common layouts:

    1) { "americanfootball_nfl": { "New England Patriots": 2.3, ... }, ... }
    2) { "New England Patriots": 2.3, ... }
    3) { "teams": { "New England Patriots": 2.3, ... } }
    """
    if not isinstance(power_data, dict):
        return 0.0

    # 1) sport-specific mapping
    sport_map = power_data.get(sport_key)
    if isinstance(sport_map, dict):
        val = sport_map.get(team)
        if isinstance(val, (int, float)):
            return float(val)

    # 2) direct mapping
    val = power_data.get(team)
    if isinstance(val, (int, float)):
        return float(val)

    # 3) nested under "teams"
    teams_map = power_data.get("teams")
    if isinstance(teams_map, dict):
        val = teams_map.get(team)
        if isinstance(val, (int, float)):
            return float(val)

    return 0.0


def _extract_team_penalty_from_obj(entry: Dict[str, Any], team: str, sport_key: str) -> float:
    """
    Helper for injuries: supports entries like:
      { "team": "Buffalo Bills", "impact": -1.0, "sport_key": "americanfootball_nfl" }
    """
    e_team = entry.get("team")
    if e_team and e_team != team:
        return 0.0

    e_sport = entry.get("sport_key")
    if e_sport and e_sport != sport_key:
        return 0.0

    penalty = entry.get("impact") or entry.get("rating_penalty") or entry.get("value")
    if isinstance(penalty, (int, float)):
        return float(penalty)
    return 0.0


def get_injury_penalty(team: str, sport_key: str, injuries_data: Any) -> float:
    """
    Approx approach:

    Accepts:
      1) { "Buffalo Bills": -1.5, "Miami Dolphins": -0.5, ... }
      2) { "americanfootball_nfl": { "Buffalo Bills": -1.5, ... } }
      3) [ { "team": "...", "impact": -1.0, "sport_key": "..." }, ... ]
    """
    if injuries_data is None:
        return 0.0

    # 1) and 2) dict-based
    if isinstance(injuries_data, dict):
        sport_map = injuries_data.get(sport_key)
        if isinstance(sport_map, dict):
            val = sport_map.get(team)
            if isinstance(val, (int, float)):
                return float(val)

        val = injuries_data.get(team)
        if isinstance(val, (int, float)):
            return float(val)

    # 3) list of objects
    if isinstance(injuries_data, list):
        total_pen = 0.0
        for entry in injuries_data:
            if isinstance(entry, dict):
                total_pen += _extract_team_penalty_from_obj(entry, team, sport_key)
        return total_pen

    return 0.0


def find_weather_record(matchup: str, commence_time: str, weather_data: Any) -> Optional[Dict[str, Any]]:
    """
    Tries to match a weather record by matchup or commence_time.

    Expected shapes (any of these work):
      1) { "Cincinnati Bengals@Pittsburgh Steelers": { ... }, ... }
      2) [ { "matchup": "...", "commence_time": "...", ... }, ... ]
    """
    if not weather_data:
        return None

    if isinstance(weather_data, dict):
        rec = weather_data.get(matchup)
        if isinstance(rec, dict):
            return rec

    if isinstance(weather_data, list):
        for rec in weather_data:
            if not isinstance(rec, dict):
                continue
            if rec.get("matchup") == matchup:
                return rec
            if rec.get("commence_time") == commence_time:
                return rec

    return None


def get_weather_adjustment(matchup: str, commence_time: str, weather_data: Any) -> float:
    """
    Return an adjustment in points applied to the TOTAL:
      - bad wind / heavy rain / cold → negative (lean Under)
      - dome / perfect → slight positive (lean Over)
    """
    rec = find_weather_record(matchup, commence_time, weather_data)
    if not isinstance(rec, dict):
        return 0.0

    wind = rec.get("wind_mph") or rec.get("windSpeed") or rec.get("wind")
    precip = rec.get("precip_prob") or rec.get("precip") or rec.get("rain_chance")
    temp = rec.get("temperature") or rec.get("temp_f")

    adj = 0.0

    # Wind – kills deep passing
    if isinstance(wind, (int, float)):
        if wind >= 20:
            adj -= 3.0
        elif wind >= 12:
            adj -= 1.5

    # Rain / snow – sloppy, lower scoring
    if isinstance(precip, (int, float)):
        if precip >= 70:
            adj -= 2.0
        elif precip >= 40:
            adj -= 1.0

    # Extreme cold – often lower scoring too
    if isinstance(temp, (int, float)):
        if temp <= 25:
            adj -= 1.0

    return adj


def find_ref_record(matchup: str, referees_data: Any) -> Optional[Dict[str, Any]]:
    """
    Very loose matcher for referees / crews, expecting shapes like:

      1) { "Cincinnati Bengals@Pittsburgh Steelers": { "total_bias": +1.5 }, ... }
      2) [ { "matchup": "...", "total_bias": +1.5 }, ... ]

    If your actual structure is different, adjust this function.
    """
    if not referees_data:
        return None

    if isinstance(referees_data, dict):
        rec = referees_data.get(matchup)
        if isinstance(rec, dict):
            return rec

    if isinstance(referees_data, list):
        for rec in referees_data:
            if isinstance(rec, dict) and rec.get("matchup") == matchup:
                return rec

    return None


def get_ref_total_adjustment(matchup: str, referees_data: Any) -> float:
    """
    Returns points to *add* to the total based on crew:
      - over-heavy crew → +1 to +3
      - under-heavy crew → -1 to -3
    """
    rec = find_ref_record(matchup, referees_data)
    if not isinstance(rec, dict):
        return 0.0

    bias = rec.get("total_bias") or rec.get("ou_adjust") or rec.get("points_adjust")
    if isinstance(bias, (int, float)):
        return float(bias)

    return 0.0


# ---------------------------------------------------------------------------
# Core model
# ---------------------------------------------------------------------------

def logistic(x: float, k: float = 1.0) -> float:
    """Standard logistic, scaled by k."""
    return 1.0 / (1.0 + math.exp(-x / k))


def compute_su_prob(home_strength: float, away_strength: float) -> float:
    """
    Simple SU probability from strength differential.

    diff = home_strength - away_strength
    A diff of ~6 gives around 70–75% win probability.
    """
    diff = home_strength - away_strength
    # scale factor tunes how “sharp” this curve is
    p_home = logistic(diff, k=6.0)
    return p_home


def compute_ats_prob(edge_points: float) -> float:
    """
    ATS probability from edge between model line and market line.

    Roughly:
      edge 0 → 50%
      edge 3 → ~65%
      clamp 50–80% to avoid insane numbers.
    """
    raw = 0.5 + (edge_points / 10.0)  # 3-pt edge → 0.8, 2-pt edge → 0.7, etc.
    raw = max(0.5, min(0.8, raw))
    return raw


def compute_ou_prob(edge_points: float) -> float:
    """
    Same logic as ATS for totals.
    """
    raw = 0.5 + (edge_points / 10.0)
    raw = max(0.5, min(0.8, raw))
    return raw


def build_game_prediction(
    event: Dict[str, Any],
    power_data: Any,
    injuries_data: Any,
    weather_data: Any,
    referees_data: Any,
) -> Optional[Dict[str, Any]]:
    """
    Convert one row from combined.json into a prediction entry.
    """
    sport_key = event.get("sport_key")
    matchup = event.get("matchup")
    home_team = event.get("home_team")
    away_team = event.get("away_team")
    commence_time = event.get("commence_time")
    fav_team = event.get("fav_team")
    dog_team = event.get("dog_team")
    fav_spread = event.get("fav_spread")
    dog_spread = event.get("dog_spread")
    spread = event.get("spread")
    total = event.get("total")
    book = event.get("book")
    fetched_at = event.get("fetched_at")

    if not (sport_key and matchup and home_team and away_team and commence_time):
        return None

    # 1) base strength from power ratings + home field
    home_pr = get_power_rating(home_team, sport_key, power_data)
    away_pr = get_power_rating(away_team, sport_key, power_data)
    home_hfa = HOME_FIELD_BY_SPORT.get(sport_key, 0.0)

    # 2) injuries
    home_injury_pen = get_injury_penalty(home_team, sport_key, injuries_data)
    away_injury_pen = get_injury_penalty(away_team, sport_key, injuries_data)

    home_strength = home_pr + home_hfa + home_injury_pen
    away_strength = away_pr + away_injury_pen

    # 3) SU probability
    p_home_su = compute_su_prob(home_strength, away_strength)
    p_away_su = 1.0 - p_home_su

    if p_home_su >= 0.5:
        su_pick = home_team
        su_conf = round(p_home_su * 100.0, 1)
    else:
        su_pick = away_team
        su_conf = round(p_away_su * 100.0, 1)

    # 4) Derive model line for home (negative means home favorite)
    strength_diff = home_strength - away_strength
    model_home_line = -strength_diff

    # 5) Market spread relative to home team
    home_market_spread: Optional[float] = None
    if isinstance(spread, (int, float)) and fav_team:
        if fav_team == home_team:
            home_market_spread = float(spread)
        elif fav_team == away_team:
            home_market_spread = -float(spread)

    # ATS: only if we have a market spread
    ats_pick: Optional[str] = None
    ats_conf: Optional[float] = None
    if home_market_spread is not None:
        edge = model_home_line - home_market_spread
        p_home_ats = compute_ats_prob(edge)
        p_away_ats = 1.0 - p_home_ats

        # Decide side: home or away vs the posted line
        if p_home_ats >= 0.5:
            # Home ATS side
            # Express pick as either favorite or dog string
            
            # If home is the book favorite, use fav_spread; else dog_spread
            if fav_team == home_team and isinstance(fav_spread, (int, float)):
                ats_pick = f"{home_team} {format_spread_value(fav_spread)}"
            elif dog_team == home_team and isinstance(dog_spread, (int, float)):
                ats_pick = f"{home_team} {format_spread_value(dog_spread)}"
            else:
                # Fallback to market home spread
                ats_pick = f"{home_team} {format_spread_value(home_market_spread)}"

            ats_conf = round(p_home_ats * 100.0, 1)
        else:
            # Away ATS side
            if fav_team == away_team and isinstance(fav_spread, (int, float)):
                ats_pick = f"{away_team} {format_spread_value(fav_spread)}"
            elif dog_team == away_team and isinstance(dog_spread, (int, float)):
                ats_pick = f"{away_team} {format_spread_value(dog_spread)}"
            else:
                # If home is -3, away is +3; so flip sign
                away_spread = -home_market_spread
                ats_pick = f"{away_team} {format_spread_value(away_spread)}"

            ats_conf = round(p_away_ats * 100.0, 1)

    # 6) Totals model (weather + ref bias)
    ou_pick: Optional[str] = None
    ou_conf: Optional[float] = None

    if isinstance(total, (int, float, float)):
        total = float(total)
        weather_adj = get_weather_adjustment(matchup, commence_time, weather_data)
        ref_adj = get_ref_total_adjustment(matchup, referees_data)

        model_total = total + weather_adj + ref_adj
        edge_total = model_total - total  # typically just weather/ref driven

        p_over = compute_ou_prob(edge_total)
        p_under = 1.0 - p_over

        if p_over > p_under:
            ou_pick = f"Over {total:g}"
            ou_conf = round(p_over * 100.0, 1)
        else:
            ou_pick = f"Under {total:g}"
            ou_conf = round(p_under * 100.0, 1)

    # Build final record
    rec: Dict[str, Any] = {
        "sport_key": sport_key,
        "matchup": matchup,
        "home_team": home_team,
        "away_team": away_team,
        "commence_time": commence_time,

        "su_pick": su_pick,
        "su_conf": su_conf,

        "ats_pick": ats_pick,
        "ats_conf": ats_conf,

        "ou_pick": ou_pick,
        "ou_conf": ou_conf,

        "fav_team": fav_team,
        "dog_team": dog_team,
        "fav_spread": fav_spread,
        "dog_spread": dog_spread,
        "spread": spread,
        "total": total,
        "book": book,
        "fetched_at": fetched_at,
    }

    return rec


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("\n==============================")
    print("🧠 Building model predictions")
    print("==============================\n")

    combined = load_json("combined.json", {"timestamp": "", "data": []})
    games: List[Dict[str, Any]] = combined.get("data", [])

    power_data = load_json("power_ratings.json", {})
    injuries_data = load_json("injuries.json", {})
    weather_data = load_json("weather.json", {})
    referees_data = load_json("referees.json", {})

    predictions: List[Dict[str, Any]] = []

    for event in games:
        if not isinstance(event, dict):
            continue
        pred = build_game_prediction(
            event,
            power_data=power_data,
            injuries_data=injuries_data,
            weather_data=weather_data,
            referees_data=referees_data,
        )
        if pred is not None:
            predictions.append(pred)

    # Sort by date → sport → time (commence_time is already ISO)
    predictions.sort(
        key=lambda g: (
            g.get("commence_time", ""),
            g.get("sport_key", ""),
            g.get("matchup", ""),
        )
    )

    ts = utc_now().strftime("%Y%m%d_%H%M")
    out_obj = {
        "timestamp": ts,
        "data": predictions,
    }

    out_path = os.path.join(ROOT_DIR, "predictions.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, indent=2)

    print(f"[✅] Saved {len(predictions)} predictions → {out_path}")
    print(f"[🕒] Timestamp: {ts}\n")


if __name__ == "__main__":
    main()

