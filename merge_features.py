#!/usr/bin/env python3
"""
merge_features.py
Merges all auxiliary feature data onto combined.json game records:
- Referee trends (ref_home_bias, ref_over_bias)
- H2H matchup history (h2h_margin_avg)
- Rest days (rest_diff_days)
- Elo ratings (elo_diff)
- Travel distance (travel_km)

Run AFTER: build_rest_days.py, build_elo.py, build_h2h.py, build_ref_trends.py
Run BEFORE: build_predictions.py
"""

import json, math, re

COMBINED = "combined.json"
REF_TRENDS = "referee_trends.json"
H2H_DATA = "h2h_data.json"
REST_DATA = "rest_data.json"
ELO_DATA = "elo_ratings.json"
STADIUMS = "stadiums_master.json"


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def normalize(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def main():
    combined = load_json(COMBINED, {})
    games = combined.get("data", [])
    if not games:
        print("[merge_features] No games in combined.json")
        return

    # --- Load auxiliary data ---
    ref_data = load_json(REF_TRENDS, {})
    refs = ref_data.get("refs", {})

    h2h_data = load_json(H2H_DATA, {})

    rest_data = load_json(REST_DATA, {})

    elo_data = load_json(ELO_DATA, {})

    stadiums = load_json(STADIUMS, {})
    # Build stadium lookup by normalized name
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

        # --- REFEREE TRENDS ---
        officials = g.get("officials") or []
        ref_home_bias = 0.0
        ref_over_bias = 0.0
        ref_count = 0
        for off in officials:
            if isinstance(off, dict):
                name = off.get("name", "")
                ref_key = name.lower().strip()
                if ref_key in refs:
                    r = refs[ref_key]
                    # home_win_pct > 50 means ref favors home
                    ref_home_bias += (r.get("home_win_pct", 50) - 50) * 0.05
                    # over_pct > 50 means ref games tend to go over
                    ref_over_bias += (r.get("over_pct", 50) - 50) * 0.05
                    ref_count += 1
        if ref_count > 0:
            g["ref_home_bias"] = round(ref_home_bias / ref_count, 3)
            g["ref_over_bias"] = round(ref_over_bias / ref_count, 3)
            ref_merged += 1
        else:
            g["ref_home_bias"] = 0.0
            g["ref_over_bias"] = 0.0

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
        home_rest = rest_data.get(home_name) or rest_data.get(normalize(home_name))
        away_rest = rest_data.get(away_name) or rest_data.get(normalize(away_name))
        if home_rest is not None and away_rest is not None:
            g["rest_diff_days"] = home_rest - away_rest
            rest_merged += 1
        elif home_rest is not None:
            g["rest_diff_days"] = home_rest - 3  # assume avg 3 days if unknown
            rest_merged += 1
        elif away_rest is not None:
            g["rest_diff_days"] = 3 - away_rest
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
        venue_coords = stadium_coords.get(normalize(venue_name))
        home_coords = stadium_coords.get(norm_home)
        away_coords = stadium_coords.get(norm_away)
        if venue_coords and away_coords:
            away_travel = haversine_km(away_coords[0], away_coords[1], venue_coords[0], venue_coords[1])
            home_travel = 0
            if home_coords:
                home_travel = haversine_km(home_coords[0], home_coords[1], venue_coords[0], venue_coords[1])
            g["travel_km"] = round(away_travel - home_travel, 1)
            travel_merged += 1
        else:
            g["travel_km"] = 0

    # Write back
    with open(COMBINED, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"[merge_features] {len(games)} games processed")
    print(f"  Refs: {ref_merged} | H2H: {h2h_merged} | Rest: {rest_merged} | Elo: {elo_merged} | Travel: {travel_merged}")


if __name__ == "__main__":
    main()
