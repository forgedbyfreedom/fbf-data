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
# Values calibrated to real-world variance per sport.
# Too-tight stdev creates false confidence; too-loose kills all signal.
TOTAL_STDEV = {
    "nfl": 6.5,
    "ncaaf": 7.5,
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
ATS_HIGH_CONF = 0.59
OU_HIGH_CONF = 0.57

# Sport-specific thresholds (post-compression values)
# With ATS compressed to 50-68% range, 59% = top ~5% of picks
ATS_HIGH_CONF_BY_SPORT = {
    "nfl": 0.59, "ncaaf": 0.59,
    "nba": 0.60, "nhl": 0.60,
    "ncaab": 0.595, "ncaaw": 0.595,
    "mlb": 0.59, "ufc": 0.59,
}
OU_HIGH_CONF_BY_SPORT = {
    "nfl": 0.57, "ncaaf": 0.57,
    "nba": 0.58, "nhl": 0.58,
    "ncaab": 0.57, "ncaaw": 0.57,
    "mlb": 0.57, "ufc": 0.57,
}

# Historical over rate by sport — used to regress O/U simulation output
# toward the true base rate, just like FAV_COVER_BASE does for ATS.
# Overs hit ~49-51% historically across most sports.
OVER_BASE = {
    "nfl": 0.49,
    "ncaaf": 0.50,
    "nba": 0.50,
    "ncaab": 0.50,
    "ncaaw": 0.50,
    "nhl": 0.50,
    "mlb": 0.50,
    "ufc": 0.50,
}

# O/U regression blend: how much to trust sim vs historical base rate
# 1.0 = pure simulation, 0.0 = always pick 50/50
# Efficient markets get heavier regression (less sim trust)
OU_SIM_WEIGHT = {
    "nfl": 0.60, "ncaaf": 0.60,
    "nba": 0.40,                     # NBA totals are efficiently priced
    "ncaab": 0.95, "ncaaw": 0.90,   # college O/U model is highly accurate — near-full trust (75% hit rate)
    "nhl": 0.35,                     # NHL totals are tightest market in sports
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
    rest_w = 0.1 if is_nhl else (0.15 if is_nba else 0.25)  # Reduced from 0.4 — double-counting Vegas
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
    quality_w = 0.3 if is_nhl else (0.4 if is_nba else 0.8)  # NHL/NBA: Vegas already priced this
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

    weather_penalty = 0.0
    if apply_weather:
        wind = safe_float(weather.get("windSpeedMph"), 0)
        rain = safe_float(weather.get("rainChancePct"), 0)
        risk_score = safe_float(risk.get("risk"), 0)
        weather_penalty = wind * 0.35 + rain * 0.15 + risk_score * 3.0

    # Referee over/under bias — sport-specific amplification
    # NHL/NBA: refs barely move totals in efficient markets; college has more signal
    ref_over_multiplier = {"nhl": 0.8, "nba": 1.0, "ncaab": 2.5, "ncaaw": 2.5,
                           "nfl": 2.5, "ncaaf": 2.5, "mlb": 1.5}
    ref_over_bias = safe_float(game.get("ref_over_bias"), 0) * ref_over_multiplier.get(sport, 2.0)

    # Pace — O/U signal from historical team scoring averages
    # pace_avg = avg combined points of both teams historically
    # When pace_avg diverges from total_line, that's our edge
    # BUT: Vegas already prices pace into efficient markets (NBA, NHL).
    # Reduce weight for those sports to avoid double-counting.
    pace_avg = safe_float(game.get("pace_avg"), 0)
    pace_shift = 0.0
    if pace_avg > 0 and total_line is not None and total_line > 0:
        pace_gap = pace_avg - total_line
        pace_weights = {"nhl": 0.20, "nba": 0.15,       # was 0.60/0.35 — Vegas prices pace
                        "mlb": 0.40, "nfl": 0.45, "ncaaf": 0.45,
                        "ncaab": 0.35, "ncaaw": 0.35}   # college: keep — less efficient
        pace_w = pace_weights.get(sport, 0.35)
        pace_shift = pace_gap * pace_w

    # Total line movement (sharp money on totals)
    # Scale by sport — a 0.5 move in NHL (line ~6) is much more meaningful than in NBA (line ~225)
    total_delta = safe_float(game.get("total_delta"), 0)
    total_move_weights = {"nhl": 0.3, "mlb": 0.4, "nfl": 0.5, "ncaaf": 0.5,
                          "nba": 0.6, "ncaab": 0.6, "ncaaw": 0.6}
    total_line_shift = total_delta * total_move_weights.get(sport, 0.5)

    # Offensive/defensive mismatch affects totals too
    # High off_def_mismatch means one team's offense >> other's defense → more scoring
    total_mismatch_shift = abs(off_def_mismatch) * 0.02 if off_def_mismatch != 0 else 0.0

    # Big spread games tend to go Under (garbage time, running clock)
    spread_total_adj = 0.0
    if spread_line is not None and total_line is not None:
        abs_spread = abs(spread_line)
        if abs_spread > 10:
            # Scale: every point of spread beyond 10 nudges 0.15 toward Under
            spread_total_adj = -(abs_spread - 10) * 0.15

    # ── COMBINE ──────────────────────────────────────────────────────

    # ── COMBINE MARGIN ──────────────────────────────────────────────
    # UPDATED 03/21/2026: Uses composite team quality instead of
    # separate Elo + power + momentum + H2H (fixes multicollinearity).
    # Neutral site adjustments zero out home-dependent factors.
    expected_margin = (base_margin + injury_shift + rest_shift
                       + quality_shift                    # composite replaces elo/power/momentum/h2h
                       + ref_home_bias + travel_shift     # zeroed on neutral sites
                       + mismatch_shift + split_shift     # split zeroed on neutral sites
                       + spot_shift + public_shift
                       + line_shift + starter_shift)

    expected_total = max(0, base_total - weather_penalty + ref_over_bias
                         + pace_shift + total_line_shift
                         + total_mismatch_shift + spread_total_adj)

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
        if sport_lower == "nhl":
            # 30% sim / 70% base rate — underdogs cover ~55%
            fav_cover_pct = raw_fav_cover * 0.30 + base_rate * 0.70
        elif sport_lower == "nba":
            # 35% sim / 65% base rate — NBA spreads are extremely efficient
            fav_cover_pct = raw_fav_cover * 0.35 + base_rate * 0.65
        elif sport_lower in ("ncaab", "ncaaw"):
            # UPDATED 03/20/2026: College ATS was 33% (5-10).
            # Tournament spreads are less predictable than regular season.
            # Regression: 45% sim / 55% base rate (was 50/50)
            fav_cover_pct = raw_fav_cover * 0.45 + base_rate * 0.55
        else:
            fav_cover_pct = raw_fav_cover * 0.50 + base_rate * 0.50

        # Large spread penalty: favorites covering big spreads is harder
        # than the simulation suggests. Apply extra dog lean for spreads > 7.
        abs_spread = abs(spread_line) if spread_line else 0
        if abs_spread > 7:
            big_spread_adj = (abs_spread - 7) * 0.005
            fav_cover_pct -= big_spread_adj

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

        # LEAN DOG on very large spreads (15+): underdogs historically cover
        # large tournament spreads ~55-58% of the time. Nudge toward dog.
        if abs_spread >= 15 and sport_lower in ("ncaab", "ncaaw", "ncaaf"):
            dog_lean = min(0.06, (abs_spread - 15) * 0.004)
            fav_cover_pct -= dog_lean

        fav_cover_pct = max(0.01, min(0.99, fav_cover_pct))

        # NHL/NBA ATS confidence cap — these markets are near coin-flip
        if sport_lower == "nhl":
            fav_cover_pct = max(0.40, min(0.60, fav_cover_pct))
        elif sport_lower == "nba":
            fav_cover_pct = max(0.42, min(0.58, fav_cover_pct))

        # Compress ATS confidence: spreads are near coin-flips by design.
        # Raw 50-100% → Display 50-68%. Preserves ordering, kills inflation.
        ATS_COMPRESS = 0.36
        raw_ats = max(fav_cover_pct, 1 - fav_cover_pct) * 100
        display_ats = round(50.0 + (raw_ats - 50.0) * ATS_COMPRESS, 1)

        # MINIMUM ATS CONFIDENCE THRESHOLD
        # Don't publish ATS picks below 52% — these are coin flips that
        # drag the overall ATS record. Better to show no pick than a bad one.
        # UPDATED 03/20/2026: Was publishing 51% picks that went 5-10 ATS.
        ATS_MIN_DISPLAY = 52.0

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
        if sport_lower == "nhl":
            regressed_over = max(0.42, min(0.58, regressed_over))
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
