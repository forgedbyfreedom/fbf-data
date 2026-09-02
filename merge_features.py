#!/usr/bin/env python3
"""
merge_features.py
Merges all auxiliary feature data onto combined.json game records:
- Referee trends (ref_home_bias, ref_over_bias, ref_consistency)
- H2H matchup history (h2h_margin_avg)
- Rest days (rest_diff_days)
- Elo ratings (elo_diff)
- Travel distance (travel_km)

Run AFTER: build_rest_days.py, build_elo.py, build_h2h.py, build_ref_trends.py
Run BEFORE: build_predictions.py
"""

import json, math, re

# Beyond a bye week, extra days are a schedule gap, not rest. Anything larger
# (an offseason, an FCS team on a different calendar) carries no signal.
MAX_USEFUL_REST_DAYS = 14

COMBINED = "combined.json"
REF_TRENDS = "referee_trends.json"
H2H_DATA = "h2h_data.json"
REST_DATA = "rest_data.json"
ELO_DATA = "elo_ratings.json"
STADIUMS = "stadiums_master.json"
TEAM_VENUES = "team_venues.json"
POWER_RATINGS = "power_ratings.json"
SITUATIONAL = "situational_data.json"
PUBLIC_BETTING = "public_betting.json"
LINE_MOVEMENT = "line_movement.json"
STARTERS = "starters_data.json"

# Ref trend weight — applied to the blended (60% career + 40% recent) value
# Up from 0.05; the blend already handles career vs recent weighting
REF_WEIGHT = 0.15


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def normalize(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _team_home_coords(team_venues, stadium_coords, team_name):
    """Coordinates of a team's own home stadium, or None if not learned yet."""
    rec = team_venues.get(normalize(team_name))
    if not rec:
        return None
    lat, lon = rec.get("lat"), rec.get("lon")
    if lat is not None and lon is not None:
        try:
            return (float(lat), float(lon))
        except (TypeError, ValueError):
            pass
    vn = rec.get("venue")
    if vn:
        return stadium_coords.get(normalize(vn))
    return None

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_ref_stats(ref_entry, sport):
    """Get sport-specific ref stats if available, otherwise fall back to overall."""
    if not ref_entry:
        return None

    # Prefer sport-specific stats when available
    by_sport = ref_entry.get("by_sport", {})
    if sport and sport in by_sport:
        sport_stats = by_sport[sport]
        # Merge sport-specific with overall (sport-specific takes priority)
        merged = dict(ref_entry)
        merged.update(sport_stats)
        return merged

    return ref_entry


def main():
    combined = load_json(COMBINED, {})
    games = combined.get("data", [])
    if not games:
        print("[merge_features] No games in combined.json")
        return

    # --- Load auxiliary data ---
    ref_data = load_json(REF_TRENDS, {})
    refs = ref_data.get("refs", {})

    # Build ref lookup by normalized name for fuzzy matching
    refs_normalized = {}
    for ref_key, ref_val in refs.items():
        norm = normalize(ref_key)
        refs_normalized[norm] = ref_val
        # Also store by the original key lowered/stripped
        refs_normalized[ref_key.lower().strip()] = ref_val

    h2h_data = load_json(H2H_DATA, {})

    rest_data = load_json(REST_DATA, {})

    elo_data = load_json(ELO_DATA, {})

    stadiums = load_json(STADIUMS, {})
    # Build stadium lookup by normalized name
    team_venues = load_json(TEAM_VENUES, {}) or {}

    stadium_coords = {}
    for key, s in stadiums.items():
        lat = s.get("lat") or s.get("latitude")
        lon = s.get("lon") or s.get("longitude")
        if lat and lon:
            try:
                stadium_coords[normalize(key)] = (float(lat), float(lon))
            except (ValueError, TypeError):
                pass
            # Also key by team name if present
            team = s.get("team") or s.get("name")
            if team:
                stadium_coords[normalize(team)] = (float(lat), float(lon))

    ref_merged = 0
    h2h_merged = 0
    rest_merged = 0
    elo_merged = 0
    travel_merged = 0

    for g in games:
        sport = (g.get("sport") or "").lower()
        home_team = g.get("home_team") or {}
        away_team = g.get("away_team") or {}
        home_name = home_team.get("name", "") if isinstance(home_team, dict) else str(home_team)
        away_name = away_team.get("name", "") if isinstance(away_team, dict) else str(away_team)

        # --- REFEREE TRENDS (enriched) ---
        officials = g.get("officials") or []
        ref_home_bias = 0.0
        ref_over_bias = 0.0
        ref_consistency = 0.0
        ref_count = 0
        for off in officials:
            if isinstance(off, dict):
                name = off.get("name", "")
            elif isinstance(off, str):
                name = off
            else:
                continue

            # Try multiple lookup strategies
            ref_key = name.lower().strip()
            r = refs_normalized.get(ref_key) or refs_normalized.get(normalize(name))
            if not r:
                continue

            # Get sport-specific stats if available
            r = get_ref_stats(r, sport)

            # Blend career (60%) and recent (40%) for over_pct
            career_over = r.get("over_pct", 50)
            recent_over = r.get("recent_over_pct", career_over)
            blended_over = career_over * 0.6 + recent_over * 0.4

            # Blend career and recent for home_win_pct
            career_home = r.get("home_win_pct", 50)
            recent_home = r.get("recent_home_win_pct", career_home)
            blended_home = career_home * 0.6 + recent_home * 0.4

            # Use blended recent-weighted stats with higher weight
            ref_home_bias += (blended_home - 50) * REF_WEIGHT
            ref_over_bias += (blended_over - 50) * REF_WEIGHT

            # Consistency: low total_stdev = more predictable ref
            total_stdev = r.get("total_stdev", 0)
            if total_stdev > 0:
                ref_consistency += total_stdev

            # NFL penalty home/away ratio — ratio > 1.0 means more home penalties
            # which counterintuitively means ref is tougher on home team
            pen_ratio = r.get("home_away_penalty_ratio", 1.0)
            if pen_ratio and pen_ratio != 1.0:
                # Adjust home bias: more away penalties = home advantage
                penalty_bias = (1.0 - pen_ratio) * 0.5  # subtle shift
                ref_home_bias += penalty_bias

            # MLB umpire scoring tendency — runs above/below league avg
            ump_runs = r.get("ump_runs_per_game") or r.get("ump_recent_runs_per_game")
            if ump_runs and ump_runs > 0:
                # MLB avg is ~8.5 runs/game; deviation suggests over/under tendency
                ump_over_shift = (ump_runs - 8.5) * 0.1
                ref_over_bias += ump_over_shift

            ref_count += 1

        if ref_count > 0:
            g["ref_home_bias"] = round(ref_home_bias / ref_count, 3)
            g["ref_over_bias"] = round(ref_over_bias / ref_count, 3)
            g["ref_consistency"] = round(ref_consistency / ref_count, 1)  # avg stdev across officials
            ref_merged += 1
        else:
            # No assigned officials — use league-average ref tendencies by sport.
            # These come from aggregating all refs in referee_trends.json.
            # Home win ~54% across all sports, over ~50.5% (slight over bias).
            sport_ref_defaults = {
                "nfl":   {"home_bias": 0.6, "over_bias": 0.3, "consistency": 10.0},
                "ncaaf": {"home_bias": 0.5, "over_bias": 0.2, "consistency": 11.0},
                "nba":   {"home_bias": 0.5, "over_bias": 0.4, "consistency": 9.0},
                "ncaab": {"home_bias": 0.4, "over_bias": 0.3, "consistency": 10.0},
                "ncaaw": {"home_bias": 0.4, "over_bias": 0.3, "consistency": 10.0},
                "nhl":   {"home_bias": 0.3, "over_bias": 0.2, "consistency": 1.5},
                "mlb":   {"home_bias": 0.2, "over_bias": 0.3, "consistency": 2.5},
            }
            # No crew assigned, so there is no referee signal for this game.
            #
            # This used to fall back to a sport-level constant (0.5 for NCAAF,
            # 0.6 for NFL). Since ESPN does not publish crews until close to
            # kickoff, that constant was applied to 100% of games - every game
            # on the 2026-09-02 slate carried a ref_home_bias of exactly 0.5 or
            # 0.6 and nothing else. That is not a referee adjustment, it is a
            # blanket home-field nudge wearing a referee label, and the market
            # already prices generic home field. Only ref_consistency is kept,
            # because it widens the simulation rather than moving the line.
            defaults = sport_ref_defaults.get(sport, {"home_bias": 0.0, "over_bias": 0.0, "consistency": 0.0})
            g["ref_home_bias"] = 0.0
            g["ref_over_bias"] = 0.0
            g["ref_consistency"] = defaults["consistency"]

        # --- REFEREE PENALTY DETAIL (NFL only) ---
        # Store per-game penalty rates and key penalty breakdowns for display + prediction
        if sport == "nfl" and ref_count > 0:
            # Collect penalty detail from the head referee (first matched official)
            for off in officials:
                if isinstance(off, dict):
                    name = off.get("name", "")
                elif isinstance(off, str):
                    name = off
                else:
                    continue
                ref_key = name.lower().strip()
                r = refs_normalized.get(ref_key) or refs_normalized.get(normalize(name))
                if not r:
                    continue
                r = get_ref_stats(r, sport)

                # Store penalty rates for dashboard display
                penalties_pg = r.get("penalties_per_game", 0)
                career_games = r.get("games", 0)
                key_pens = r.get("key_penalties", {})

                # Calculate per-game rates for key penalty types
                pen_rates = {}
                for pen_name, pen_data in key_pens.items():
                    if isinstance(pen_data, dict) and career_games > 0:
                        count = pen_data.get("count", 0)
                        home = pen_data.get("home", 0)
                        away = pen_data.get("away", 0)
                        pen_rates[pen_name] = {
                            "per_game": round(count / career_games, 2),
                            "home": home,
                            "away": away,
                            "h_a_ratio": round(home / away, 2) if away > 0 else None,
                        }

                g["ref_penalties_per_game"] = penalties_pg
                g["ref_penalty_detail"] = pen_rates
                g["ref_crew_chief"] = r.get("name", name)

                # Use DPI rate to further adjust over bias
                # NFL avg DPI is ~0.8/game; refs who call more DPI = more big plays = higher scoring
                dpi_data = key_pens.get("defensive pass interference", {})
                if isinstance(dpi_data, dict) and career_games > 0:
                    dpi_pg = dpi_data.get("count", 0) / career_games
                    dpi_shift = (dpi_pg - 0.8) * 0.3  # above avg DPI caller → more scoring
                    g["ref_over_bias"] = round(g["ref_over_bias"] + dpi_shift, 3)

                # Use holding rate to adjust total — more holding = more stalled drives = lower scoring
                hold_data = key_pens.get("offensive holding", {})
                if isinstance(hold_data, dict) and career_games > 0:
                    hold_pg = hold_data.get("count", 0) / career_games
                    hold_shift = (hold_pg - 2.0) * -0.15  # above avg holding = lower scoring
                    g["ref_over_bias"] = round(g["ref_over_bias"] + hold_shift, 3)

                break  # only use the first matched official (crew chief)

        # --- H2H MATCHUPS ---
        # h2h_data uses canonical key: alphabetical order of normalized names
        norm_home = normalize(home_name)
        norm_away = normalize(away_name)
        pair = sorted([norm_home, norm_away])
        h2h_key = f"{pair[0]}_vs_{pair[1]}"
        h2h = h2h_data.get(h2h_key)
        if h2h and h2h.get("games", 0) > 0:
            # avg_margin is from team_a's perspective (alphabetical first)
            avg_margin = h2h.get("recent_avg_margin") or h2h.get("avg_margin", 0)
            # If home team is team_a, margin is positive for home advantage
            # If home team is team_b, flip it
            if normalize(h2h.get("team_a", "")) == norm_home:
                g["h2h_margin_avg"] = round(avg_margin, 2)
            else:
                g["h2h_margin_avg"] = round(-avg_margin, 2)
            h2h_merged += 1
        else:
            g["h2h_margin_avg"] = 0.0

        # --- REST DAYS ---
        # rest_data holds raw days since a team last played, which across an
        # offseason is a number like 240. Differencing those unclamped produced
        # rest_diff_days of -430 for Furman at Tennessee, and at 0.25 points a
        # day that is a -107 point "rest advantage" for the FCS side. It was
        # the single largest term in the whole adjustment layer (mean 10.7
        # points across the slate, against 1.3 for team quality) and it is what
        # made the board fade every big favourite in week one.
        #
        # Past a bye week, more days off is not more rest - it is just a longer
        # gap. Clamp each side before differencing so the feature measures what
        # it is supposed to measure.
        DEFAULT_REST = 7

        def _useful_rest(v):
            if v is None:
                return None
            try:
                return max(0, min(int(v), MAX_USEFUL_REST_DAYS))
            except (TypeError, ValueError):
                return None

        home_rest = _useful_rest(rest_data.get(home_name) or rest_data.get(normalize(home_name)))
        away_rest = _useful_rest(rest_data.get(away_name) or rest_data.get(normalize(away_name)))
        if home_rest is not None and away_rest is not None:
            g["rest_diff_days"] = home_rest - away_rest
            rest_merged += 1
        elif home_rest is not None:
            g["rest_diff_days"] = home_rest - DEFAULT_REST
            rest_merged += 1
        elif away_rest is not None:
            g["rest_diff_days"] = DEFAULT_REST - away_rest
            rest_merged += 1
        else:
            g["rest_diff_days"] = 0

        # --- ELO RATINGS ---
        sport_elo = elo_data.get(sport, {})
        home_elo = sport_elo.get(home_name) or sport_elo.get(normalize(home_name))
        away_elo = sport_elo.get(away_name) or sport_elo.get(normalize(away_name))
        if home_elo is not None and away_elo is not None:
            g["elo_diff"] = round(home_elo - away_elo, 1)
            g["home_elo"] = round(home_elo, 1)
            g["away_elo"] = round(away_elo, 1)
            elo_merged += 1
        else:
            g["elo_diff"] = 0
            g["home_elo"] = 1500
            g["away_elo"] = 1500

        # --- TRAVEL DISTANCE ---
        venue = g.get("venue") or {}
        venue_name = venue.get("name", "")
        # Where each team normally plays. stadium_coords is keyed by STADIUM
        # name, so looking a TEAM name up in it never matched and travel_km was
        # 0 on every game the model has ever scored. team_venues.json maps team
        # -> home venue and is accumulated across runs by
        # build_venues_from_combined.py.
        venue_coords = stadium_coords.get(normalize(venue_name))
        if venue_coords is None and venue.get("lat") is not None:
            try:
                venue_coords = (float(venue["lat"]), float(venue["lon"]))
            except (TypeError, ValueError, KeyError):
                venue_coords = None
        home_coords = _team_home_coords(team_venues, stadium_coords, home_name)
        away_coords = _team_home_coords(team_venues, stadium_coords, away_name)
        if venue_coords and away_coords:
            away_travel = haversine_km(away_coords[0], away_coords[1], venue_coords[0], venue_coords[1])
            home_travel = 0
            if home_coords:
                home_travel = haversine_km(home_coords[0], home_coords[1], venue_coords[0], venue_coords[1])
            g["travel_km"] = round(away_travel - home_travel, 1)
            travel_merged += 1
        else:
            g["travel_km"] = 0

    # --- POWER RATINGS ---
    power_data = load_json(POWER_RATINGS, {})
    power_ratings = power_data.get("ratings", {})
    power_merged = 0

    for g in games:
        sport = (g.get("sport") or "").lower()
        home_team = g.get("home_team") or {}
        away_team = g.get("away_team") or {}
        home_name = home_team.get("name", "") if isinstance(home_team, dict) else str(home_team)
        away_name = away_team.get("name", "") if isinstance(away_team, dict) else str(away_team)
        norm_home = normalize(home_name)
        norm_away = normalize(away_name)

        sport_pr = power_ratings.get(sport, {})
        home_pr = sport_pr.get(norm_home)
        away_pr = sport_pr.get(norm_away)

        if home_pr and away_pr:
            # Net rating differential
            g["power_diff"] = round(home_pr["net_rating"] - away_pr["net_rating"], 1)
            # Offensive matchup: home offense vs away defense and vice versa
            g["off_def_mismatch"] = round(
                (home_pr["off_rating"] - away_pr["def_rating"]) -
                (away_pr["off_rating"] - home_pr["def_rating"]), 1
            )
            # Pace: average of both teams' pace indicates expected total
            g["pace_avg"] = round((home_pr["pace"] + away_pr["pace"]) / 2, 1)
            # Home/away split advantage
            g["home_split_edge"] = round(home_pr["home_win_pct"] - away_pr["away_win_pct"], 1)
            # Recent form: momentum differential
            g["momentum_diff"] = round(home_pr["momentum"] - away_pr["momentum"], 1)
            # Recent ATS: if one team has been hot ATS and the other cold
            g["recent_ats_diff"] = round(home_pr["recent_ats_pct"] - away_pr["recent_ats_pct"], 1)
            # Consistency: lower stdev = more predictable
            g["home_margin_stdev"] = home_pr["margin_stdev"]
            g["away_margin_stdev"] = away_pr["margin_stdev"]
            power_merged += 1
        else:
            g["power_diff"] = 0
            g["off_def_mismatch"] = 0
            g["pace_avg"] = 0
            g["home_split_edge"] = 0
            g["momentum_diff"] = 0
            g["recent_ats_diff"] = 0
            g["home_margin_stdev"] = 0
            g["away_margin_stdev"] = 0

    # --- SITUATIONAL SPOTS ---
    sit_data = load_json(SITUATIONAL, {})
    sit_spots = sit_data.get("spots", {})
    sit_merged = 0

    for g in games:
        game_id = str(g.get("id") or g.get("event_id") or "")
        spot = sit_spots.get(game_id)
        if spot:
            g["spot_score"] = spot.get("spot_score", 0)
            g["home_b2b"] = spot.get("home_b2b", False)
            g["away_b2b"] = spot.get("away_b2b", False)
            g["revenge_home"] = spot.get("revenge_home", False)
            g["revenge_away"] = spot.get("revenge_away", False)
            g["divisional"] = spot.get("divisional", False)
            g["home_streak"] = spot.get("home_streak", 0)
            g["away_streak"] = spot.get("away_streak", 0)
            sit_merged += 1
        else:
            g["spot_score"] = 0
            g["home_b2b"] = False
            g["away_b2b"] = False
            g["revenge_home"] = False
            g["revenge_away"] = False
            g["divisional"] = False
            g["home_streak"] = 0
            g["away_streak"] = 0

    # --- PUBLIC BETTING ---
    pub_data = load_json(PUBLIC_BETTING, {})
    pub_games = pub_data.get("games", [])
    # Build lookup by team abbreviation pairs
    pub_lookup = {}
    for pg in pub_games:
        t1 = (pg.get("team1_abbr") or "").upper()
        t2 = (pg.get("team2_abbr") or "").upper()
        if t1 and t2:
            pub_lookup[f"{t1}_{t2}"] = pg
            pub_lookup[f"{t2}_{t1}"] = pg
    pub_merged = 0

    for g in games:
        home_team = g.get("home_team") or {}
        away_team = g.get("away_team") or {}
        home_abbr = (home_team.get("abbr") or "").upper() if isinstance(home_team, dict) else ""
        away_abbr = (away_team.get("abbr") or "").upper() if isinstance(away_team, dict) else ""

        pub = pub_lookup.get(f"{home_abbr}_{away_abbr}") or pub_lookup.get(f"{away_abbr}_{home_abbr}")
        if pub:
            g["public_pct"] = pub.get("public_pct", 50)
            g["public_side"] = pub.get("public_side", "")
            g["fade_signal"] = pub.get("fade_signal", 0)

            # Compute public edge: positive = public is on home, negative = public is on away
            if pub.get("public_side") == home_abbr:
                g["public_home_pct"] = pub.get("public_pct", 50)
            else:
                g["public_home_pct"] = 100 - pub.get("public_pct", 50)
            pub_merged += 1
        else:
            g["public_pct"] = 50
            g["public_side"] = ""
            g["fade_signal"] = 0
            g["public_home_pct"] = 50

    # --- LINE MOVEMENT ---
    line_data = load_json(LINE_MOVEMENT, {})
    line_merged = 0

    for g in games:
        game_id = str(g.get("id") or g.get("event_id") or "")
        lm = line_data.get(game_id)
        if lm:
            g["spread_delta"] = lm.get("spread_delta", 0) or 0
            g["total_delta"] = lm.get("total_delta", 0) or 0
            g["spread_direction"] = lm.get("spread_direction", "stable")
            g["total_direction"] = lm.get("total_direction", "stable")
            g["spread_moves"] = lm.get("spread_moves", 0)
            line_merged += 1
        else:
            g["spread_delta"] = 0
            g["total_delta"] = 0
            g["spread_direction"] = "stable"
            g["total_direction"] = "stable"
            g["spread_moves"] = 0

    # --- STARTERS (MLB / NHL) ---
    starter_data = load_json(STARTERS, {})
    mlb_starters = starter_data.get("mlb", {})
    nhl_starters = starter_data.get("nhl", {})
    starter_merged = 0

    for g in games:
        sport = (g.get("sport") or "").lower()
        game_id = str(g.get("id") or g.get("event_id") or "")

        if sport == "mlb":
            home_sp = mlb_starters.get(f"{game_id}_home")
            away_sp = mlb_starters.get(f"{game_id}_away")
            if home_sp or away_sp:
                g["home_starter"] = {
                    "name": home_sp.get("name") if home_sp else None,
                    "era": home_sp.get("era") if home_sp else None,
                    "whip": home_sp.get("whip") if home_sp else None,
                } if home_sp else None
                g["away_starter"] = {
                    "name": away_sp.get("name") if away_sp else None,
                    "era": away_sp.get("era") if away_sp else None,
                    "whip": away_sp.get("whip") if away_sp else None,
                } if away_sp else None

                # Pitcher quality differential (lower ERA = better)
                if home_sp and away_sp and home_sp.get("era") and away_sp.get("era"):
                    g["starter_era_diff"] = round(away_sp["era"] - home_sp["era"], 2)  # positive = home advantage
                else:
                    g["starter_era_diff"] = 0
                starter_merged += 1
            else:
                g["starter_era_diff"] = 0

        elif sport == "nhl":
            home_g = nhl_starters.get(f"{game_id}_home")
            away_g = nhl_starters.get(f"{game_id}_away")
            if home_g or away_g:
                g["home_goalie"] = {
                    "name": home_g.get("name") if home_g else None,
                    "save_pct": home_g.get("save_pct") if home_g else None,
                    "gaa": home_g.get("gaa") if home_g else None,
                } if home_g else None
                g["away_goalie"] = {
                    "name": away_g.get("name") if away_g else None,
                    "save_pct": away_g.get("save_pct") if away_g else None,
                    "gaa": away_g.get("gaa") if away_g else None,
                } if away_g else None

                # Goalie quality differential (higher save% = better)
                if home_g and away_g and home_g.get("save_pct") and away_g.get("save_pct"):
                    g["goalie_sv_diff"] = round(home_g["save_pct"] - away_g["save_pct"], 3)
                else:
                    g["goalie_sv_diff"] = 0
                starter_merged += 1
            else:
                g["goalie_sv_diff"] = 0

    # Write back
    with open(COMBINED, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"[merge_features] {len(games)} games processed")
    print(f"  Refs: {ref_merged} | H2H: {h2h_merged} | Rest: {rest_merged} | Elo: {elo_merged} | Travel: {travel_merged}")
    print(f"  Power: {power_merged} | Spots: {sit_merged} | Public: {pub_merged} | Lines: {line_merged} | Starters: {starter_merged}")


if __name__ == "__main__":
    main()
