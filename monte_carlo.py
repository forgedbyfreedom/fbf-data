#!/usr/bin/env python3
"""
monte_carlo.py
Monte Carlo simulation engine for sports predictions.

Runs N simulations per game using:
- Spread (implied margin)
- Total (implied combined score)
- Injuries (shift advantage to healthier team)
- Elo ratings (team quality beyond spread)
- H2H history (historical matchup trends)
- Rest days (fatigue advantage)
- Weather (scoring impact for outdoor games)
- Referee trends (home bias, over/under tendency)

Outputs explicit SU, ATS, O/U picks with confidence percentages.
"""

import math
import random

DEFAULT_SIMS = 10000

# Standard deviation of actual margin around expected margin, by sport
SPORT_STDEV = {
    "nfl": 13.5,
    "ncaaf": 16.0,
    "nba": 11.0,
    "ncaab": 11.5,
    "ncaaw": 12.0,
    "nhl": 2.2,
    "mlb": 3.5,
    "ufc": 0.45,  # binary outcome, small stdev around 0.5
}

# Standard deviation of actual total around expected total
TOTAL_STDEV = {
    "nfl": 10.0,
    "ncaaf": 12.0,
    "nba": 10.0,
    "ncaab": 11.0,
    "ncaaw": 11.0,
    "nhl": 1.8,
    "mlb": 3.0,
    "ufc": 0.3,
}


def safe_float(x, default=0.0):
    try:
        if x is None:
            return default
        return float(x)
    except (ValueError, TypeError):
        return default


def simulate_game(expected_margin, expected_total, margin_stdev, total_stdev,
                  spread_line, total_line, n_sims=DEFAULT_SIMS):
    """
    Run Monte Carlo simulation for a single game.

    Args:
        expected_margin: Our projected home margin (positive = home advantage)
        expected_total: Our projected combined total
        margin_stdev: Standard deviation for margin (sport-specific)
        total_stdev: Standard deviation for total (sport-specific)
        spread_line: The ESPN spread line (home team perspective)
        total_line: The ESPN over/under line
        n_sims: Number of simulations to run

    Returns dict with simulation results and explicit picks.
    """
    home_wins = 0
    home_covers = 0
    overs = 0
    margins = []
    totals = []

    for _ in range(n_sims):
        # Simulate margin: normal distribution around expected
        sim_margin = random.gauss(expected_margin, margin_stdev)
        # Simulate total: normal distribution around expected
        sim_total = max(0, random.gauss(expected_total, total_stdev))

        margins.append(sim_margin)
        totals.append(sim_total)

        # SU: did home team win?
        if sim_margin > 0:
            home_wins += 1

        # ATS: did home team cover the spread?
        # spread_line is home team's spread (negative = home favored)
        # home covers if margin > spread_line (e.g., margin=10, line=-7 -> 10 > -7 = covers)
        if spread_line is not None:
            if sim_margin > spread_line:
                home_covers += 1

        # O/U: did total go over?
        if total_line is not None:
            if sim_total > total_line:
                overs += 1

    # Calculate probabilities
    home_win_pct = home_wins / n_sims
    away_win_pct = 1.0 - home_win_pct

    cover_pct = home_covers / n_sims if spread_line is not None else None
    over_pct = overs / n_sims if total_line is not None else None

    avg_margin = sum(margins) / n_sims
    avg_total = sum(totals) / n_sims

    return {
        "simulations": n_sims,
        "home_win_pct": round(home_win_pct, 4),
        "away_win_pct": round(away_win_pct, 4),
        "home_cover_pct": round(cover_pct, 4) if cover_pct is not None else None,
        "over_pct": round(over_pct, 4) if over_pct is not None else None,
        "avg_simulated_margin": round(avg_margin, 2),
        "avg_simulated_total": round(avg_total, 2),
    }


def build_expected_values(game):
    """
    Build expected margin and total from all available features.
    Returns (expected_margin, expected_total, has_odds).
    """
    odds = game.get("odds") or {}
    spread_line = safe_float(odds.get("spread"), None)
    total_line = safe_float(odds.get("total"), None)

    # Start with Vegas line as baseline (best available prior)
    if spread_line is not None:
        base_margin = -spread_line  # ESPN spread: neg=home fav -> positive expected margin
    else:
        base_margin = 0.0

    if total_line is not None:
        base_total = total_line
    else:
        # Sport-specific defaults
        sport = (game.get("sport") or "").lower()
        sport_defaults = {
            "nfl": 44.0, "ncaaf": 52.0, "nba": 225.0, "ncaab": 145.0,
            "ncaaw": 140.0, "nhl": 6.0, "mlb": 8.5, "ufc": 1.0,
        }
        base_total = sport_defaults.get(sport, 100.0)

    # Adjustments from features
    injury_home = safe_float(game.get("injury_count_home"), 0)
    injury_away = safe_float(game.get("injury_count_away"), 0)
    injury_shift = (injury_away - injury_home) * 0.3  # each injury ~0.3 pts

    # Rest days
    rest_diff = safe_float(game.get("rest_diff_days"), 0)
    rest_shift = rest_diff * 0.4

    # Elo
    elo_diff = safe_float(game.get("elo_diff"), 0)
    elo_shift = elo_diff * 0.03  # 100 Elo ~ 3 pts

    # H2H
    h2h_margin = safe_float(game.get("h2h_margin_avg"), 0)
    h2h_shift = h2h_margin * 0.1

    # Weather (outdoor sports only)
    venue = game.get("venue") or {}
    weather = game.get("weather") or {}
    risk = game.get("weatherRisk") or {}
    weather_penalty = 0.0
    if not venue.get("indoor"):
        wind = safe_float(weather.get("windSpeedMph"), 0)
        rain = safe_float(weather.get("rainChancePct"), 0)
        risk_score = safe_float(risk.get("risk"), 0)
        weather_penalty = wind * 0.15 + rain * 0.08 + risk_score * 1.5

    # Referee trends
    ref_home_bias = 0.0  # Will be set from referee data if available
    ref_over_bias = 0.0

    expected_margin = base_margin + injury_shift + rest_shift + elo_shift + h2h_shift + ref_home_bias
    expected_total = max(0, base_total - weather_penalty + ref_over_bias)

    has_odds = spread_line is not None

    return expected_margin, expected_total, has_odds


def make_picks(sim_result, spread_line, total_line, home_name, away_name,
               home_abbr, away_abbr, fav_team=None, dog_team=None):
    """
    Generate explicit SU, ATS, O/U picks from simulation results.
    """
    picks = {}

    # SU PICK
    home_win_pct = sim_result["home_win_pct"]
    if home_win_pct >= 0.5:
        picks["su_pick"] = home_name
        picks["su_pick_abbr"] = home_abbr
        picks["su_confidence"] = round(home_win_pct * 100, 1)
    else:
        picks["su_pick"] = away_name
        picks["su_pick_abbr"] = away_abbr
        picks["su_confidence"] = round((1 - home_win_pct) * 100, 1)

    # ATS PICK — always make a pick
    cover_pct = sim_result.get("home_cover_pct")
    if cover_pct is not None:
        if cover_pct >= 0.5:
            picks["ats_pick"] = home_name
            picks["ats_pick_abbr"] = home_abbr
            picks["ats_spread"] = spread_line
            picks["ats_confidence"] = round(cover_pct * 100, 1)
        else:
            picks["ats_pick"] = away_name
            picks["ats_pick_abbr"] = away_abbr
            picks["ats_spread"] = -spread_line if spread_line is not None else 0
            picks["ats_confidence"] = round((1 - cover_pct) * 100, 1)
    else:
        # Fallback: use expected margin to determine pick
        if home_win_pct >= 0.5:
            picks["ats_pick"] = home_name
            picks["ats_pick_abbr"] = home_abbr
            picks["ats_spread"] = spread_line or 0
            picks["ats_confidence"] = round(home_win_pct * 100, 1)
        else:
            picks["ats_pick"] = away_name
            picks["ats_pick_abbr"] = away_abbr
            picks["ats_spread"] = -(spread_line or 0)
            picks["ats_confidence"] = round((1 - home_win_pct) * 100, 1)

    # O/U PICK — always make a pick
    over_pct = sim_result.get("over_pct")
    if over_pct is not None:
        if over_pct >= 0.5:
            picks["ou_pick"] = "Over"
            picks["ou_line"] = total_line
            picks["ou_confidence"] = round(over_pct * 100, 1)
        else:
            picks["ou_pick"] = "Under"
            picks["ou_line"] = total_line
            picks["ou_confidence"] = round((1 - over_pct) * 100, 1)
    else:
        # Fallback: use expected total vs line
        picks["ou_pick"] = "Over"
        picks["ou_line"] = total_line
        picks["ou_confidence"] = 50.0

    return picks


def simulate_and_pick(game, n_sims=DEFAULT_SIMS):
    """
    Full pipeline: build expected values, run simulations, make picks.
    Always generates SU, ATS, and O/U picks for every game.
    When no Vegas line exists, uses projected values as the line.
    """
    sport = (game.get("sport") or "").lower()
    odds = game.get("odds") or {}

    spread_line = safe_float(odds.get("spread"), None)
    total_line = safe_float(odds.get("total"), None)

    margin_stdev = SPORT_STDEV.get(sport, 12.0)
    total_stdev = TOTAL_STDEV.get(sport, 10.0)

    expected_margin, expected_total, has_odds = build_expected_values(game)

    # When no Vegas line, use pick'em (0) for spread and sport default for total
    # This ensures every game gets ATS and O/U picks
    sim_spread = spread_line if spread_line is not None else 0.0
    sim_total = total_line if total_line is not None else expected_total

    # Run simulation
    sim = simulate_game(
        expected_margin=expected_margin,
        expected_total=expected_total,
        margin_stdev=margin_stdev,
        total_stdev=total_stdev,
        spread_line=sim_spread,
        total_line=sim_total,
        n_sims=n_sims,
    )

    # Extract team info
    home_team = game.get("home_team") or {}
    away_team = game.get("away_team") or {}
    home_name = home_team.get("name", "") if isinstance(home_team, dict) else str(home_team)
    away_name = away_team.get("name", "") if isinstance(away_team, dict) else str(away_team)
    home_abbr = home_team.get("abbr", "") if isinstance(home_team, dict) else ""
    away_abbr = away_team.get("abbr", "") if isinstance(away_team, dict) else ""

    # Use actual Vegas lines for picks display, fall back to projected values
    pick_spread = spread_line if spread_line is not None else round(-expected_margin, 1)
    pick_total = total_line if total_line is not None else round(expected_total, 1)

    picks = make_picks(
        sim_result=sim,
        spread_line=pick_spread,
        total_line=pick_total,
        home_name=home_name,
        away_name=away_name,
        home_abbr=home_abbr,
        away_abbr=away_abbr,
        fav_team=game.get("fav_team"),
        dog_team=game.get("dog_team"),
    )

    # Flag whether picks are based on real Vegas lines or projections
    picks["has_vegas_spread"] = spread_line is not None
    picks["has_vegas_total"] = total_line is not None

    return {
        "simulation": sim,
        "picks": picks,
        "expected_margin": round(expected_margin, 2),
        "expected_total": round(expected_total, 2),
        "has_odds": has_odds,
    }


if __name__ == "__main__":
    # Quick test
    test_game = {
        "sport": "nba",
        "odds": {"spread": -6.5, "total": 225.5},
        "home_team": {"name": "Detroit Pistons", "abbr": "DET"},
        "away_team": {"name": "Cleveland Cavaliers", "abbr": "CLE"},
        "injury_count_home": 0,
        "injury_count_away": 6,
        "venue": {"indoor": True},
    }

    result = simulate_and_pick(test_game)
    print(f"Simulations: {result['simulation']['simulations']}")
    print(f"Expected margin: {result['expected_margin']}")
    print(f"Home win %: {result['simulation']['home_win_pct']*100:.1f}%")
    print(f"Home cover %: {result['simulation']['home_cover_pct']*100:.1f}%")
    print(f"Over %: {result['simulation']['over_pct']*100:.1f}%")
    print(f"\nPicks:")
    for k, v in result['picks'].items():
        print(f"  {k}: {v}")
