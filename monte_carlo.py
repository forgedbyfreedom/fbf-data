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
# Margin standard deviation around the closing line, MEASURED on 2,370 games
# from 2021-2023 and confirmed on the 2024-2025 holdout:
#     NFL    12.88  (holdout 12.42)
#     NCAAF  15.10  (holdout 15.12)
# Football values below are those measurements. The other sports are legacy
# and unmeasured; this pipeline no longer fetches them.
SPORT_STDEV = {
    "nfl": 12.9,
    "ncaaf": 15.1,
    "nba": 11.0,
    "ncaab": 11.5,
    "ncaaw": 12.0,
    "nhl": 2.2,
    "mlb": 3.5,
    "ufc": 0.45,  # binary outcome, small stdev around 0.5
}

# Standard deviation of actual total around expected total
# Values calibrated to real-world variance per sport.
# Too-tight stdev creates false confidence; too-loose kills all signal.
# Total standard deviation, measured the same way:
#     NFL    13.21  (holdout 12.81)
#     NCAAF  15.55  (holdout 15.41)
# The previous 6.5 / 7.5 were roughly half the true dispersion, which made
# every over/under probability far more confident than the data supports.
TOTAL_STDEV = {
    "nfl": 13.2,
    "ncaaf": 15.6,
    "nba": 10.0,    # was 6.5 — real NBA total stdev ~11-12; 10 lets genuine edges survive
    "ncaab": 7.0,
    "ncaaw": 7.5,
    "nhl": 1.8,     # was 1.2 — real NHL total stdev ~1.8-2.0; old value created 80%+ phantom confidence
    "mlb": 2.5,     # was 2.0 — real MLB total stdev ~2.5-3.0
    "ufc": 0.3,
}

# Historical favorite cover rates by sport — used to correct simulation bias
# Favorites cover slightly less than 50% historically (the vig + public bias)
FAV_COVER_BASE = {
    "nfl": 0.48,
    "ncaaf": 0.48,
    "nba": 0.49,
    "ncaab": 0.48,
    "ncaaw": 0.49,
    "nhl": 0.45,   # puck line (1.5) underdogs cover ~55% — favorites rarely win by 2+
    "mlb": 0.50,
    "ufc": 0.50,
}

# High-confidence thresholds — picks above this get "BEST BET" badge.
# These should be RARE: 1-3 per day across all sports. Every game still
# gets a pick with confidence %, but the badge means we see genuine edge.
# NOTE: Confidence values are now compressed (SU 0.56x, ATS 0.36x, O/U 0.30x).
# Thresholds must account for compression. A "58% ATS" post-compression means
# the raw simulation had ~72% confidence — that IS a strong signal.
# UPDATED 03/24/2026: Best bet thresholds recalibrated for new compression ratios.
# ATS max confidence is ~53% with current compression. Old 59% threshold = 0 best bets.
# Target: ~3-5 best bets per day across all sports.
# Best bet thresholds — ATS only (O/U best bets disabled — model not reliable enough)
# Target: ~1-3 best bets per day across all sports
ATS_HIGH_CONF = 0.525
OU_HIGH_CONF = 0.99   # Effectively disabled — O/U model doesn't produce reliable high-conf picks

ATS_HIGH_CONF_BY_SPORT = {
    "nfl": 0.515, "ncaaf": 0.525,
    "nba": 0.515, "nhl": 0.515,
    "ncaab": 0.525, "ncaaw": 0.525,
    "mlb": 0.515, "ufc": 0.515,
}
OU_HIGH_CONF_BY_SPORT = {
    "nfl": 0.99, "ncaaf": 0.99,
    "nba": 0.99, "nhl": 0.99,
    "ncaab": 0.99, "ncaaw": 0.99,
    "mlb": 0.99, "ufc": 0.99,
}

# Historical over rate by sport — used to regress O/U simulation output
# toward the true base rate, just like FAV_COVER_BASE does for ATS.
# Overs hit ~49-51% historically across most sports.
# Measured 2021-2025 on 3,570 football games with a closing total and a final
# score: Over 50.0% overall (NFL 50.5% on 1,360, NCAAF 49.7% on 2,210). Both
# are inside the noise of a coin flip, so both are set to a coin flip. The old
# NFL value of 0.49 was a small standing Under lean with nothing behind it.
OVER_BASE = {
    "nfl": 0.50,
    "ncaaf": 0.50,
    "nba": 0.50,
    "ncaab": 0.50,
    "ncaaw": 0.50,
    "nhl": 0.46,   # UPDATED 03/22: NHL Unders hitting ~60%+ — lower base rate reflects reality
    "mlb": 0.50,
    "ufc": 0.50,
}

# O/U regression blend: how much to trust sim vs historical base rate
# 1.0 = pure simulation, 0.0 = always pick 50/50
# Efficient markets get heavier regression (less sim trust)
OU_SIM_WEIGHT = {
    "nfl": 0.60, "ncaaf": 0.60,
    "nba": 0.40,                     # NBA totals are efficiently priced
    "ncaab": 0.70, "ncaaw": 0.70,   # UPDATED 03/21: was 0.95 — backtest showed 45.8% (27-32), no edge. Regress harder.
    "nhl": 0.25,                     # UPDATED 03/22: was 0.35 — NHL O/U going 4-34 Over, 26-2 Under. Less sim trust.
    "mlb": 0.55, "ufc": 0.50,
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
        # Home covers if margin + spread > 0
        # e.g., spread=-6.5 (home -6.5): margin must be > 6.5 to cover
        # e.g., spread=+3.5 (home +3.5): margin must be > -3.5 to cover (home can lose by up to 3)
        if spread_line is not None:
            if sim_margin + spread_line > 0:
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


# Maximum total points the adjustment layer may move the market line, by sport.
# See the rationale in build_expected_values(). Roughly one score in the NFL,
# where lines are sharpest, and a bit more in college where they are softer.
MAX_MARGIN_ADJ = {"nfl": 7.0, "ncaaf": 10.0}
# Tighter than the margin cap. Only two things move a total now - wind and the
# market revising its own number - and neither is validated in this pipeline,
# so neither gets to move it far. See build_expected_values().
MAX_TOTAL_ADJ = {"nfl": 3.5, "ncaaf": 3.5}

# Minimum disagreement with the market before an ATS pick is published.
# At the measured college margin SD of 15.1 points, 2 points of edge is a 55%
# cover and 1 point is 52.6%, which is inside the vig. See simulate_and_pick().
MIN_EDGE_PTS = 2.0

# Same idea for totals, set higher. The totals market measured perfectly
# efficient over 3,570 football games (50.0% Over), and the only inputs left
# on that side are unvalidated, so the bar for saying anything at all is
# higher than on the margin side. At the measured total SD of 15.6 in college
# football, 3 points of disagreement is a 57.5% chance of landing on the right
# side of the number; below that the model is not saying anything a coin does
# not. In practice this means O/U picks are now rare and mostly windy games.
MIN_TOTAL_EDGE_PTS = 3.0


def build_expected_values(game):
    """
    Build expected margin and total from all available features.
    Returns (expected_margin, expected_total, has_odds).
    """
    odds = game.get("odds") or {}
    sport = (game.get("sport") or "").lower()
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
        sport_defaults = {
            "nfl": 44.0, "ncaaf": 52.0, "nba": 225.0, "ncaab": 145.0,
            "ncaaw": 140.0, "nhl": 6.0, "mlb": 8.5, "ufc": 1.0,
        }
        base_total = sport_defaults.get(sport, 100.0)

    # ── SPORT-SPECIFIC COEFFICIENT SCALING ────────────────────────────
    # NHL is a low-scoring, tight-margin sport (stdev 2.2). Coefficients
    # tuned for basketball/football produce absurd margins in hockey.
    # NBA spreads are the most efficiently priced market in sports —
    # Vegas already prices in Elo, injuries, rest, etc. Our adjustments
    # double-count these factors, pushing us toward favorites (who cover ~49%).
    # Scale adjustments down so the model doesn't override Vegas.
    is_nhl = (sport == "nhl")
    is_nba = (sport == "nba")

    # ── NEUTRAL SITE DETECTION ─────────────────────────────────────
    # ADDED 03/21/2026: March Madness and bowl games are neutral site.
    # Home/away adjustments are invalid when there's no home team.
    # Zero out: ref home bias, travel, home/away splits, spot_score home component.
    is_neutral = game.get("neutral_site", False)
    # Auto-detect tournament neutral sites for college sports
    if not is_neutral and sport in ("ncaab", "ncaaw"):
        # NCAA tournament games after conference tournaments are neutral site
        venue = game.get("venue") or {}
        venue_name = (venue.get("name") or "").lower()
        # Common tournament venue indicators
        if any(kw in venue_name for kw in ["arena", "center", "dome", "coliseum", "fieldhouse"]):
            # If venue city doesn't match either team's home city, likely neutral
            pass  # Can't reliably detect without team city data — use explicit flag
    if not is_neutral and sport == "ncaaf":
        # Bowl games are neutral site
        game_name = (game.get("name") or game.get("title") or "").lower()
        if "bowl" in game_name or "championship" in game_name or "playoff" in game_name:
            is_neutral = True

    # ── CORE MARGIN ADJUSTMENTS ──────────────────────────────────────

    # Injuries — only count residual beyond what Vegas priced
    # Vegas already adjusts for known injuries. Our edge is LATE injuries
    # (after line was set) or injury severity mispricing.
    injury_home = safe_float(game.get("injury_count_home"), 0)
    injury_away = safe_float(game.get("injury_count_away"), 0)
    inj_w = 0.1 if is_nhl else (0.12 if is_nba else 0.2)  # Reduced from 0.3 — Vegas prices most injuries
    injury_shift = (injury_away - injury_home) * inj_w

    # Rest days — reduced weight, Vegas prices this too
    rest_diff = safe_float(game.get("rest_diff_days"), 0)
    # Zeroed on the same evidence: in the fitted model the rest coefficient was
    # 0.049 points per day and the combination still lost to the line on the
    # holdout. Rest is priced by the market.
    rest_w = 0.0
    rest_shift = rest_diff * rest_w

    # ── COMPOSITE TEAM QUALITY (replaces separate Elo + power + momentum) ──
    # UPDATED 03/21/2026: Elo, power ratings, and momentum are correlated
    # measures of team quality. Adding them separately quadruple-counts
    # the same signal. Combine into one composite, weighted by reliability.
    # Then apply ONE coefficient — the residual beyond Vegas pricing.
    elo_diff = safe_float(game.get("elo_diff"), 0)
    power_diff = safe_float(game.get("power_diff"), 0)
    momentum_diff = safe_float(game.get("momentum_diff"), 0)
    h2h_margin = safe_float(game.get("h2h_margin_avg"), 0)

    # Normalize each to comparable scales, then blend
    # Elo: 100 pts diff ~ 3 pts spread equivalent → /33 to get ~pts
    # Power: already in point-like units → small weight
    # Momentum: recent form, small signal → low weight
    # H2H: historical margin avg → small weight (sample size issues)
    composite_quality = (
        (elo_diff / 33.0) * 0.50 +     # Elo is most reliable signal
        power_diff * 0.01 * 0.25 +      # Power ratings
        momentum_diff * 0.01 * 0.15 +   # Momentum (noisy)
        h2h_margin * 0.05 * 0.10        # H2H (small samples)
    )

    # Scale by sport — how much residual edge exists beyond Vegas
    # ── ZEROED 2026-09-03 ON EVIDENCE ────────────────────────────────
    # The team quality composite was tested against the closing line on 3,893
    # football games (2021-2025), deriving on 2021-2023 and evaluating once on
    # 2024-2025. Projection error, mean absolute:
    #
    #     weight 0.0 (line only)   train 11.382   holdout 10.979
    #     weight 0.4 (production)  train 11.462   holdout 11.061
    #     weight 0.8               train 11.619   holdout 11.266
    #
    # Monotonic: every non-zero weight makes the projection worse, and the
    # optimum is zero. Swept per subset - NFL, NCAAF, early season, late
    # season, small spreads, large spreads - every apparent training gain
    # reversed on the holdout. Fitted optimally by OLS across elo, rest, form
    # and season stage, it scored R-squared of -0.02 on the holdout: worse than
    # a horizontal line, and 48.0% ATS.
    #
    # This is not surprising. The closing line already prices team quality.
    # Adding a second, worse estimate of the same thing adds only noise.
    #
    # An earlier version of this analysis appeared to find a large edge. That
    # sample had not been filtered by sport and was mostly basketball and
    # hockey. On football alone the effect is absent.
    quality_w = 0.0
    quality_shift = composite_quality * quality_w

    # Referee home bias — zeroed on neutral sites
    ref_home_bias = safe_float(game.get("ref_home_bias"), 0)
    if is_neutral:
        ref_home_bias = 0.0  # No home court = no home ref bias

    # Travel fatigue — zeroed on neutral sites (both teams travel)
    travel_km = safe_float(game.get("travel_km"), 0)
    travel_w = 0.0002 if is_nhl else (0.0002 if is_nba else 0.0003)  # Reduced — Vegas prices travel
    travel_shift = travel_km * travel_w
    if is_neutral:
        travel_shift = 0.0  # Both teams traveling to neutral site

    # ── ADVANCED MARGIN ADJUSTMENTS ──────────────────────────────────

    off_def_mismatch = safe_float(game.get("off_def_mismatch"), 0)
    mismatch_w = 0.01 if is_nhl else (0.01 if is_nba else 0.02)  # Reduced — correlated with quality
    mismatch_shift = off_def_mismatch * mismatch_w

    # Home/away splits — zeroed on neutral sites
    home_split_edge = safe_float(game.get("home_split_edge"), 0)
    split_shift = home_split_edge * 0.015  # Reduced from 0.02 — correlated with quality
    if is_neutral:
        split_shift = 0.0  # No home/away when neutral

    # Situational spots (B2B, revenge, divisional, timezone — pre-calibrated in pts)
    spot_score = safe_float(game.get("spot_score"), 0)
    spot_w = 0.2 if is_nhl else (0.25 if is_nba else 0.4)  # Reduced from 0.5
    spot_shift = spot_score * spot_w
    if is_neutral:
        spot_shift *= 0.5  # Halve spot value on neutral sites — home-related spots don't apply

    # Public betting fade — contrarian signal
    fade_signal = safe_float(game.get("fade_signal"), 0)
    public_home_pct = safe_float(game.get("public_home_pct"), 50)
    public_shift = 0.0
    fade_size = 0.4 if is_nhl else (0.5 if is_nba else 0.8)
    if fade_signal >= 2:  # 70%+ public on one side
        if public_home_pct > 65:
            public_shift = -fade_size
        elif public_home_pct < 35:
            public_shift = fade_size

    # Line movement (sharp money)
    spread_delta = safe_float(game.get("spread_delta"), 0)
    line_w = 0.15 if is_nhl else (0.15 if is_nba else 0.3)  # NHL/NBA: line moves mostly noise
    line_shift = spread_delta * line_w

    # Starting pitcher / goalie quality
    starter_shift = 0.0
    if sport == "mlb":
        era_diff = safe_float(game.get("starter_era_diff"), 0)
        starter_shift = era_diff * 0.4  # 1.0 ERA advantage = 0.4 runs
    elif is_nhl:
        sv_diff = safe_float(game.get("goalie_sv_diff"), 0)
        starter_shift = sv_diff * 8.0  # 0.010 SV% diff = 0.08 goals

    # ── TOTAL ADJUSTMENTS ────────────────────────────────────────────

    # Weather (outdoor sports only) — strong O/U signal
    # UPDATED 03/21/2026: Added retractable roof venue classification.
    # Three venue types: indoor (always), outdoor (always), retractable (conditional).
    INDOOR_SPORTS = {"nba", "nhl", "ncaab", "ncaaw"}

    # Retractable roof venues — roof typically closed
    RETRACTABLE_CLOSED = {
        "allegiant stadium", "lucas oil stadium", "state farm stadium",
        "sofi stadium", "caesars superdome", "ford field", "mercedes-benz stadium",
        "nrg stadium",  # Houston — retractable, usually closed
        "loandeport park", "tropicana field",
        "rogers centre",  # Toronto — closed in cold months
        "chase field",  # Arizona — closed when hot
        "minute maid park",  # Houston — retractable
    }
    # Retractable roof venues — roof typically open (weather applies)
    RETRACTABLE_OPEN = {
        "t-mobile park",  # Seattle — often open
        "american family field",  # Milwaukee — often open in summer
        "globe life field",  # Texas — varies
    }

    venue = game.get("venue") or {}
    weather = game.get("weather") or {}
    risk = game.get("weatherRisk") or {}
    venue_name = (venue.get("name") or "").lower()
    venue_indoor = venue.get("indoor", False)

    # Determine if weather applies
    apply_weather = False
    if sport not in INDOOR_SPORTS:
        if venue_indoor:
            apply_weather = False  # Explicit indoor flag
        elif any(v in venue_name for v in RETRACTABLE_CLOSED):
            apply_weather = False  # Retractable, typically closed
        elif any(v in venue_name for v in RETRACTABLE_OPEN):
            apply_weather = True   # Retractable, typically open
        else:
            apply_weather = True   # Default: outdoor, weather applies

    # Weather. The old formula was wind*0.35 + rainChance*0.15 + risk*3.0,
    # which meant a 59% CHANCE of rain removed 8.9 points from a total before
    # a drop had fallen. Chance of rain is not rain, and the coefficients were
    # never measured against anything. On 2026-09-04 that term was a large part
    # of why the board's projected total sat below the market number on 86% of
    # games (63 Unders to 10 Overs).
    #
    # What survives is wind, and only wind that is actually strong enough to
    # change how a game is played. Below WIND_FLOOR nothing is subtracted.
    # This coefficient is NOT measured in this pipeline - the historical file
    # carries no weather - so it is deliberately small and hard-capped, and
    # build_line_study.py now records wind at lock time so it becomes testable.
    WIND_FLOOR = 10.0     # mph below which wind is not a factor
    WIND_PTS_PER_MPH = 0.20
    WIND_MAX_PTS = 3.0

    weather_penalty = 0.0
    if apply_weather:
        wind = safe_float(weather.get("windSpeedMph"), 0)
        if wind > WIND_FLOOR:
            weather_penalty = min((wind - WIND_FLOOR) * WIND_PTS_PER_MPH, WIND_MAX_PTS)

    # ── TOTALS: WHAT WAS REMOVED, AND WHY ───────────────────────────
    # Measured on the 3,570 football games in historical_results.json that
    # carry both a closing total and a final score (2021-2025).
    #
    # The market total is the benchmark and it is brutally good: games went
    # Over 50.0% of the time (1773-1771-26), mean residual +0.71 points,
    # MAE 11.49. There is no standing bias to exploit.
    #
    # Every adjustment this function used to layer on top of it was tested
    # against that sample and none of them survived:
    #
    #   big spread -> Under   -(|spread|-8)*0.15 on every game over 8 points.
    #                         Replayed: 49.2% (783-809) across 1,592 games, and
    #                         the correlation between |spread| and the total
    #                         residual is r=+0.0097 - flat, and POSITIVE, the
    #                         opposite of the direction the code assumed.
    #                         It was pushing a mean of -2.07 points on 38 of
    #                         the 77 priced games on the current board.
    #
    #   pace                  pace_gap * 0.45. Rebuilt walk-forward (each team
    #                         needing 3+ prior games): r=-0.0125 against the
    #                         residual, direction correct on 51.0% of 1,116
    #                         games with a 2+ point gap. Every non-zero weight
    #                         made MAE monotonically WORSE - 11.149 at weight
    #                         0.00, 11.264 at the 0.45 the code was using.
    #
    #   referee over bias     crew tendency * 2.5. Built walk-forward from the
    #                         officials recorded on each game (each official
    #                         needing 5+ priors): r=-0.061, direction correct
    #                         50.4% of 965 games. Nothing.
    #
    #   off/def mismatch      abs(off_def_mismatch) * 0.02. An absolute value,
    #                         so it could only ever push a total UP, never
    #                         down, on every game with any mismatch at all.
    #                         That is a structural lean, not an opinion,
    #                         regardless of what the coefficient is.
    #
    # A scan of the alternatives - total level, month, sport, spread bucket -
    # produced nothing that held. The candidates that cleared 52.4% on one
    # split flipped sign on the other, and the two best (|spread| 7-14 Over,
    # |spread| 14-21 Under) are adjacent buckets pointing opposite ways, which
    # is what noise looks like, not a mechanism.
    #
    # So the totals layer no longer has an opinion about scoring. It carries
    # wind, and it carries the market moving the number itself. That is all
    # that is left standing.

    # Total line movement - the market revising its own number. This is
    # market information rather than a model opinion, which is why it stays.
    # It is unvalidated: the historical file holds no line-movement snapshot.
    total_delta = safe_float(game.get("total_delta"), 0)
    total_move_weights = {"nfl": 0.5, "ncaaf": 0.5}
    total_line_shift = total_delta * total_move_weights.get(sport, 0.5)

    # ── COMBINE ──────────────────────────────────────────────────────

    # ── COMBINE MARGIN ──────────────────────────────────────────────
    # UPDATED 03/21/2026: Uses composite team quality instead of
    # separate Elo + power + momentum + H2H (fixes multicollinearity).
    # Neutral site adjustments zero out home-dependent factors.
    raw_adjustment = (injury_shift + rest_shift
                      + quality_shift                    # composite replaces elo/power/momentum/h2h
                      + ref_home_bias + travel_shift     # zeroed on neutral sites
                      + mismatch_shift + split_shift     # split zeroed on neutral sites
                      + spot_shift + public_shift
                      + line_shift + starter_shift)

    # ── CAP THE TOTAL ADJUSTMENT ─────────────────────────────────────
    # The closing line is the best single predictor available: measured
    # against 5 seasons of results it carries an MAE of ~9.3 points, and a
    # walk-forward test of every feature in this pipeline failed to beat it
    # out of sample (50.9% ATS pooled, under the 52.4% breakeven). So the
    # adjustments below are a modest opinion layered on a strong prior, not
    # a replacement for it.
    #
    # Uncapped, they were not behaving that way. On 2026-09-01 the mean
    # adjustment on games with a spread of 14+ was -18.0 points, and Furman
    # at Tennessee (line +46.5) was adjusted by -103.8 to an expected margin
    # of -57.3 - i.e. the model projected Furman to win by 57. That single
    # failure mode made the board take the underdog in 37 of 37 games priced
    # at 14 or more, which is not an opinion, it is a broken input.
    #
    # Capping keeps the opinion and discards the blowups.
    # Per-factor breakdown, stashed for diagnostics. Makes it possible to ask
    # which inputs are actually moving a number and which are dead weight,
    # rather than assuming a feature is doing work because it is computed.
    game["_adj_breakdown"] = {
        "injury": round(injury_shift, 3),
        "rest": round(rest_shift, 3),
        "quality": round(quality_shift, 3),
        "ref_home_bias": round(ref_home_bias, 3),
        "travel": round(travel_shift, 3),
        "mismatch": round(mismatch_shift, 3),
        "home_away_split": round(split_shift, 3),
        "situational_spot": round(spot_shift, 3),
        "public_fade": round(public_shift, 3),
        "line_movement": round(line_shift, 3),
        "starters": round(starter_shift, 3),
    }
    game["_total_adj_breakdown"] = {
        "wind": round(-weather_penalty, 3),
        "total_line_move": round(total_line_shift, 3),
    }

    cap = MAX_MARGIN_ADJ.get(sport, 7.0)
    game["_margin_adj_raw"] = round(raw_adjustment, 2)
    game["_margin_adj_clamped"] = abs(raw_adjustment) > cap
    if raw_adjustment > cap:
        raw_adjustment = cap
    elif raw_adjustment < -cap:
        raw_adjustment = -cap

    expected_margin = base_margin + raw_adjustment

    raw_total_adjustment = -weather_penalty + total_line_shift
    tcap = MAX_TOTAL_ADJ.get(sport, 7.0)
    if raw_total_adjustment > tcap:
        raw_total_adjustment = tcap
    elif raw_total_adjustment < -tcap:
        raw_total_adjustment = -tcap

    expected_total = max(0, base_total + raw_total_adjustment)

    has_odds = spread_line is not None

    return expected_margin, expected_total, has_odds


def make_picks(sim_result, spread_line, total_line, home_name, away_name,
               home_abbr, away_abbr, fav_team=None, dog_team=None,
               fav_abbr=None, dog_abbr=None, sport="",
               has_vegas_spread=False, has_vegas_total=False):
    """
    Generate explicit SU, ATS, O/U picks from simulation results.

    ATS logic is based on favorite/underdog, NOT home/away.
    The favorite is whoever has the negative spread (gives points).

    Includes:
    - Favorite cover regression (historical fav cover rate ~48-49%)
    - Confidence filtering (skip low-edge ATS/O/U picks)
    - Sport-specific ATS calibration
    """
    picks = {}
    sport_lower = sport.lower() if sport else ""

    # --- Determine favorite and underdog ---
    if spread_line is not None and spread_line < 0:
        fav_name = fav_team or home_name
        dog_name = dog_team or away_name
        f_abbr = fav_abbr or home_abbr
        d_abbr = dog_abbr or away_abbr
        fav_spread = spread_line
        dog_spread = -spread_line
        fav_is_home = True
    elif spread_line is not None and spread_line > 0:
        fav_name = fav_team or away_name
        dog_name = dog_team or home_name
        f_abbr = fav_abbr or away_abbr
        d_abbr = dog_abbr or home_abbr
        fav_spread = -spread_line
        dog_spread = spread_line
        fav_is_home = False
    else:
        fav_name = home_name
        dog_name = away_name
        f_abbr = home_abbr
        d_abbr = away_abbr
        fav_spread = 0
        dog_spread = 0
        fav_is_home = True

    # --- SU PICK: who wins straight up ---
    # Compress SU confidence into a tighter, more realistic range.
    # Raw sim: 50-100% → Display: 50-78%. This preserves relative ordering
    # (better teams still show higher confidence) without inflating numbers.
    # Formula: display = 50 + (raw - 50) * 0.56  →  90% raw = 72.4%, 80% raw = 66.8%
    SU_COMPRESS = 0.56
    SU_FLOOR = 50.0
    home_win_pct = sim_result["home_win_pct"]
    raw_conf = max(home_win_pct, 1 - home_win_pct) * 100
    display_conf = round(SU_FLOOR + (raw_conf - SU_FLOOR) * SU_COMPRESS, 1)

    if home_win_pct >= 0.5:
        picks["su_pick"] = home_name
        picks["su_pick_abbr"] = home_abbr
        picks["su_confidence"] = display_conf
    else:
        picks["su_pick"] = away_name
        picks["su_pick_abbr"] = away_abbr
        picks["su_confidence"] = display_conf

    # --- ATS PICK: who covers the spread ---
    # Only make ATS picks when a real Vegas spread exists
    cover_pct = sim_result.get("home_cover_pct")

    if cover_pct is not None and has_vegas_spread:
        if fav_is_home:
            raw_fav_cover = cover_pct
        else:
            raw_fav_cover = 1.0 - cover_pct

        # REGRESSION: blend simulation result toward historical base rate
        # This prevents overconfident favorite picks.
        # Vegas spreads are ~50/50 by design; our edge is small.
        base_rate = FAV_COVER_BASE.get(sport_lower, 0.49)

        # Regression by sport — blend sim toward historical base rate
        # More efficient markets get heavier regression (less sim trust)
        # UPDATED 03/22/2026: Previous weights were filtering out 100% of
        # NBA/NFL/NHL ATS picks. The regression was so heavy that no pick
        # could ever reach the confidence threshold. Increased sim trust
        # for pro sports so genuine edge can surface.
        if sport_lower == "nhl":
            # 40% sim / 60% base — was 30/70, blocked every pick
            fav_cover_pct = raw_fav_cover * 0.40 + base_rate * 0.60
        elif sport_lower == "nba":
            # 45% sim / 55% base — was 35/65, blocked every pick
            fav_cover_pct = raw_fav_cover * 0.45 + base_rate * 0.55
        elif sport_lower in ("ncaab", "ncaaw"):
            # 45% sim / 55% base — college tournament spreads less predictable
            fav_cover_pct = raw_fav_cover * 0.45 + base_rate * 0.55
        elif sport_lower in ("nfl", "ncaaf"):
            # 55% sim / 45% base — NFL has more variance than NBA/NHL
            fav_cover_pct = raw_fav_cover * 0.55 + base_rate * 0.45
        else:
            fav_cover_pct = raw_fav_cover * 0.50 + base_rate * 0.50

        abs_spread = abs(spread_line) if spread_line else 0

        # REMOVED 2026-09-02: a dog lean of (abs_spread - 7) * 0.005, which
        # subtracted up to 19.8 points of cover probability at a 46.5 line.
        # Measured against 5 repaired seasons of NFL and college football, the
        # favourite covers:
        #
        #     0-7    46.8%   (n=5410)      <- penalty applied: none
        #     7-14   48.5%   (n=2042)      <- penalty applied: 1.8 pts
        #     14-25  49.1%   (n=1089)      <- penalty applied: 6.2 pts
        #     25+    50.1%   (n=913)       <- penalty applied: 17.8 pts
        #
        # The correction ran backwards: heaviest exactly where favourites do
        # best, absent where underdogs actually have the edge. Together with the
        # dog_lean below it guaranteed the underdog on every large spread - the
        # board went 37 for 37 on games priced at 14 or more. The base_rate
        # regression above already carries the real, mild historical dog lean.

        # Big spread dampener: large spreads are unpredictable ATS regardless
        # of what the simulation thinks. A 30-point spread doesn't mean 90% cover.
        # Pull aggressively toward 50% as spread grows.
        # UPDATED 03/20/2026: Increased college dampening — tournament mismatches
        # were generating 51-55% picks on 15-30pt spreads that went 5-10 ATS.
        if abs_spread > 7:
            if sport_lower in ("ncaab", "ncaaw", "ncaaf"):
                # College: tournament mismatches are near coin-flips ATS
                # Starts dampening at 7 (not 10), heavier pull toward 50%
                dampen = min(0.85, (abs_spread - 7) * 0.035)
            else:
                # Pro: large spreads still unpredictable
                dampen = min(0.60, (abs_spread - 7) * 0.025)
            fav_cover_pct = fav_cover_pct * (1 - dampen) + 0.50 * dampen

        # REMOVED 2026-09-02: a further dog lean of up to 6 points on college
        # spreads of 15+, justified in its comment by underdogs covering
        # "~55-58% of the time". In the repaired historical data they cover
        # 50.9% at 14-25 and 49.9% at 25+ - inside the margin of error of a
        # coin flip, and nowhere near 55-58%. The claim did not survive being
        # checked, so the adjustment goes with it.

        fav_cover_pct = max(0.01, min(0.99, fav_cover_pct))

        # NHL/NBA ATS confidence cap — these markets are near coin-flip
        if sport_lower == "nhl":
            fav_cover_pct = max(0.40, min(0.60, fav_cover_pct))
        elif sport_lower == "nba":
            fav_cover_pct = max(0.42, min(0.58, fav_cover_pct))

        # Compress ATS confidence: spreads are near coin-flips by design.
        # UPDATED 03/22/2026: Sport-specific compression. Pro sports were being
        # compressed so hard that no pick could ever surface. Allow more signal
        # for pro sports while keeping college tight.
        ATS_COMPRESS_BY_SPORT = {
            "nhl": 0.50,    # was 0.36 — let puck line picks breathe
            "nba": 0.50,    # was 0.36 — let NBA spread picks breathe
            "nfl": 0.50,    # was 0.36 — let NFL spread picks breathe
            "mlb": 0.45,    # run line
            "ncaab": 0.36,  # keep tight — college is noisy
            "ncaaw": 0.36,
            "ncaaf": 0.42,  # moderate
            "ufc": 0.40,
        }
        ATS_COMPRESS = ATS_COMPRESS_BY_SPORT.get(sport_lower, 0.40)
        raw_ats = max(fav_cover_pct, 1 - fav_cover_pct) * 100
        display_ats = round(50.0 + (raw_ats - 50.0) * ATS_COMPRESS, 1)

        # MINIMUM ATS CONFIDENCE THRESHOLD — sport-specific
        # UPDATED 03/22/2026: Global 52% was filtering out 100% of NHL/NBA/NFL picks.
        # These markets are efficiently priced — 51% IS a real pick there.
        # College spreads are noisier — keep higher threshold.
        ATS_MIN_BY_SPORT = {
            "nhl": 50.5,    # Puck line is near coin-flip — any lean is signal
            "nba": 50.5,    # NBA spreads efficient — small edge is real
            "nfl": 50.5,    # NFL spreads efficient — small edge is real
            "mlb": 50.5,    # Run line
            "ncaab": 52.0,  # College — keep higher bar, noisier market
            "ncaaw": 52.0,
            "ncaaf": 51.0,  # College football — moderate
            "ufc": 50.5,
        }
        ATS_MIN_DISPLAY = ATS_MIN_BY_SPORT.get(sport_lower, 51.0)

        if display_ats >= ATS_MIN_DISPLAY:
            if fav_cover_pct >= 0.5:
                picks["ats_pick"] = fav_name
                picks["ats_pick_abbr"] = f_abbr
                picks["ats_spread"] = fav_spread
                picks["ats_confidence"] = display_ats
            else:
                picks["ats_pick"] = dog_name
                picks["ats_pick_abbr"] = d_abbr
                picks["ats_spread"] = dog_spread
                picks["ats_confidence"] = display_ats
        else:
            # Below threshold — no ATS pick (protects record)
            picks["ats_pick"] = None
            picks["ats_pick_abbr"] = None
            picks["ats_spread"] = fav_spread
            picks["ats_confidence"] = display_ats  # still show confidence, just no pick
            picks["ats_below_threshold"] = True

        # High confidence flag — sport-specific thresholds
        ats_conf = picks["ats_confidence"] / 100.0
        ats_threshold = ATS_HIGH_CONF_BY_SPORT.get(sport_lower, ATS_HIGH_CONF)
        picks["ats_high_conf"] = ats_conf >= ats_threshold
    else:
        # No real spread — skip ATS entirely (no fake picks)
        picks["ats_pick"] = None
        picks["ats_pick_abbr"] = None
        picks["ats_spread"] = None
        picks["ats_confidence"] = None
        picks["ats_high_conf"] = False

    # --- O/U PICK ---
    # Mirrors ATS regression logic: blend simulation output toward historical
    # base rate to prevent overconfident picks in efficient markets.
    over_pct = sim_result.get("over_pct")
    if over_pct is not None and has_vegas_total:
        # REGRESSION: blend simulation toward historical over base rate
        base_over = OVER_BASE.get(sport_lower, 0.50)
        sim_weight = OU_SIM_WEIGHT.get(sport_lower, 0.55)
        regressed_over = over_pct * sim_weight + base_over * (1.0 - sim_weight)

        # NHL/NBA O/U confidence cap — these markets are near coin-flip
        # UPDATED 03/22/2026: NHL games going Under at massive rate (26-2 Under vs 4-34 Over
        # in backtest). Apply structural Under lean — NHL totals are consistently set too high.
        if sport_lower == "nhl":
            regressed_over -= 0.04  # Structural Under lean — games consistently go Under
            regressed_over = max(0.38, min(0.58, regressed_over))
        elif sport_lower == "nba":
            regressed_over = max(0.43, min(0.57, regressed_over))

        # Compress O/U confidence: totals are efficiently priced.
        # Raw 50-100% → Display 50-65%. Very tight range — totals are hard.
        OU_COMPRESS = 0.30
        raw_ou = max(regressed_over, 1 - regressed_over) * 100
        display_ou = round(50.0 + (raw_ou - 50.0) * OU_COMPRESS, 1)

        if regressed_over >= 0.5:
            picks["ou_pick"] = "Over"
            picks["ou_line"] = total_line
            picks["ou_confidence"] = display_ou
        else:
            picks["ou_pick"] = "Under"
            picks["ou_line"] = total_line
            picks["ou_confidence"] = display_ou

        # High confidence flag — sport-specific thresholds
        ou_conf = picks["ou_confidence"] / 100.0
        ou_threshold = OU_HIGH_CONF_BY_SPORT.get(sport_lower, OU_HIGH_CONF)
        picks["ou_high_conf"] = ou_conf >= ou_threshold
    else:
        # No real total line — skip O/U entirely
        picks["ou_pick"] = None
        picks["ou_line"] = total_line
        picks["ou_confidence"] = None
        picks["ou_high_conf"] = False

    return picks


def simulate_and_pick(game, n_sims=DEFAULT_SIMS):
    """
    Full pipeline: build expected values, run simulations, make picks.
    Always generates SU, ATS, and O/U picks for every game.
    When no Vegas line exists, uses projected values as the line.

    Includes stdev adjustments for:
    - Referee consistency (predictable refs → tighter sims)
    - Team-specific volatility (blend with sport default)
    - Divisional games (play tighter historically)
    """
    sport = (game.get("sport") or "").lower()
    odds = game.get("odds") or {}

    spread_line = safe_float(odds.get("spread"), None)
    total_line = safe_float(odds.get("total"), None)

    margin_stdev = SPORT_STDEV.get(sport, 12.0)
    total_stdev = TOTAL_STDEV.get(sport, 10.0)

    expected_margin, expected_total, has_odds = build_expected_values(game)

    # ── STDEV ADJUSTMENTS ────────────────────────────────────────────

    # Referee consistency: predictable refs → tighter simulations
    ref_consistency = safe_float(game.get("ref_consistency"), 0)
    if ref_consistency > 0:
        sport_default_stdev = TOTAL_STDEV.get(sport, 10.0)
        consistency_ratio = ref_consistency / sport_default_stdev
        adjustment = max(0.85, min(1.15, consistency_ratio))
        total_stdev *= adjustment
        margin_stdev *= (1.0 + (adjustment - 1.0) * 0.5)

    # Team-specific margin volatility: blend 60% sport / 40% team
    home_margin_stdev = safe_float(game.get("home_margin_stdev"), 0)
    away_margin_stdev = safe_float(game.get("away_margin_stdev"), 0)
    if home_margin_stdev > 0 and away_margin_stdev > 0:
        team_stdev = (home_margin_stdev + away_margin_stdev) / 2
        margin_stdev = margin_stdev * 0.6 + team_stdev * 0.4

    # Divisional games play tighter (8% reduction)
    if game.get("divisional"):
        margin_stdev *= 0.92

    # ── SIMULATION ───────────────────────────────────────────────────

    sim_spread = spread_line if spread_line is not None else 0.0
    sim_total = total_line if total_line is not None else expected_total

    sim = simulate_game(
        expected_margin=expected_margin,
        expected_total=expected_total,
        margin_stdev=margin_stdev,
        total_stdev=total_stdev,
        spread_line=sim_spread,
        total_line=sim_total,
        n_sims=n_sims,
    )

    # ── PICKS ────────────────────────────────────────────────────────

    home_team = game.get("home_team") or {}
    away_team = game.get("away_team") or {}
    home_name = home_team.get("name", "") if isinstance(home_team, dict) else str(home_team)
    away_name = away_team.get("name", "") if isinstance(away_team, dict) else str(away_team)
    home_abbr = home_team.get("abbr", "") if isinstance(home_team, dict) else ""
    away_abbr = away_team.get("abbr", "") if isinstance(away_team, dict) else ""

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
        fav_abbr=game.get("fav_abbr"),
        dog_abbr=game.get("dog_abbr"),
        sport=sport,
        has_vegas_spread=spread_line is not None,
        has_vegas_total=total_line is not None,
    )

    picks["has_vegas_spread"] = spread_line is not None
    picks["has_vegas_total"] = total_line is not None

    # ── SUPPRESS PICKS THE MODEL IS NOT QUALIFIED TO MAKE ────────────
    # A clamped adjustment means the feature layer wanted to move the market
    # by more than one score-and-a-half. In practice that never signals a real
    # edge; it signals inputs outside the range the ratings can represent -
    # typically an FBS side facing an opponent with almost no game history, so
    # the ratings cannot express how large the gap truly is. Emitting a pick
    # there produced a board that faded the favourite in 37 of 37 games priced
    # at 14 or more. Saying nothing is more accurate than saying that.
    # ── ONLY SPEAK WHEN THE DISAGREEMENT IS MATERIAL ─────────────────
    # Replaces an asymmetric "publish only on underdog leans" rule shipped
    # earlier the same day. That rule came from a sample that had not been
    # filtered by sport - it was mostly basketball and hockey. Re-run on
    # football alone, with 2021-2023 for derivation and 2024-2025 held out,
    # the effect disappeared entirely:
    #
    #     leans underdog   dog covers 47.9% train / 45.1% holdout
    #     leans favourite  fav covers 50.1% train / 50.9% holdout
    #
    # Nothing there. A full scan of candidate splits - spread size, sport,
    # rest edges, form, season stage, totals - produced no signal whose lower
    # confidence bound cleared the 52.4% breakeven.
    #
    # So there is no validated ATS edge, and the gate makes no directional
    # claim. It is a magnitude test: with the measured margin SD of 15.1
    # points in college football, an edge of 2 points is a 55% cover and an
    # edge of 1 point is 52.6% - barely breakeven. Below MIN_EDGE_PTS the
    # model is not saying anything a coin does not.
    #
    # The remaining live inputs - injuries, weather, line movement, public
    # betting - could not be tested here because the historical file carries
    # no snapshot of them. They are unvalidated, not endorsed.
    if spread_line is not None:
        edge_vs_line = expected_margin - (-spread_line)
        picks["model_edge_pts"] = round(edge_vs_line, 2)
        if abs(edge_vs_line) < MIN_EDGE_PTS:
            picks["ats_pick"] = None
            picks["ats_pick_abbr"] = None
            picks["ats_spread"] = None
            picks["ats_confidence"] = None
            picks["ats_high_conf"] = False
            picks["ats_suppressed"] = True
            picks["ats_suppressed_reason"] = (
                f"model differs from the line by {abs(edge_vs_line):.1f} pts, "
                f"under the {MIN_EDGE_PTS} pt bar for a meaningful cover probability")
    # ── O/U MAGNITUDE GATE ───────────────────────────────────────────
    # The mirror of the ATS gate above, and for a stronger reason: the totals
    # market measured 50.0% Over on 3,570 football games, and every opinion
    # this model used to hold about scoring was measured at zero (see
    # build_expected_values). Publishing an Over/Under on a total the model
    # agrees with is publishing a coin flip with a percentage printed on it.
    #
    # Before this gate the board carried 63 Unders against 10 Overs, with the
    # projected total sitting below the market number on 86% of games - not an
    # opinion, a bias. O/U accuracy over the first graded picks was 47.6%.
    if total_line is not None and picks.get("ou_pick"):
        total_edge = expected_total - total_line
        picks["ou_edge_pts"] = round(total_edge, 2)
        if abs(total_edge) < MIN_TOTAL_EDGE_PTS:
            picks["ou_pick"] = None
            picks["ou_confidence"] = None
            picks["ou_high_conf"] = False
            picks["ou_suppressed"] = True
            picks["ou_suppressed_reason"] = (
                f"model differs from the total by {abs(total_edge):.1f} pts, "
                f"under the {MIN_TOTAL_EDGE_PTS} pt bar for a meaningful edge")
    if not picks.get("ou_suppressed"):
        picks["ou_suppressed"] = False

    if game.get("_margin_adj_clamped"):
        picks["ats_pick"] = None
        picks["ats_pick_abbr"] = None
        picks["ats_spread"] = None
        picks["ats_confidence"] = None
        picks["ats_high_conf"] = False
        picks["ats_suppressed"] = True
        picks["ats_suppressed_reason"] = "model disagrees with the line by more than it can justify"
    elif not picks.get("ats_suppressed"):
        picks["ats_suppressed"] = False

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
