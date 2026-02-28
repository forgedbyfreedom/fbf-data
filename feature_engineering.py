#!/usr/bin/env python3
"""
feature_engineering.py

Builds per-game feature rows used by:
- train_model.py
- build_predictions.py

Inputs (all optional / best-effort):
- combined.json                (required for games)
- weather.json                 (outdoor-only weather)
- referee_trends.json          (ref trend priors)
- injuries.json                (injury counts)
- rest_data.json               (days since last game per team)
- elo_ratings.json             (Elo ratings per sport/team)
- h2h_data.json                (head-to-head historical matchups)
- stadiums_master.json         (venue coordinates for travel calc)

Output:
- build_feature_rows() returns list[dict]
- FEATURES list defines model columns
"""

import os, json, re, math
from datetime import datetime, timezone

COMBINED_FILE = "combined.json"
WEATHER_FILE = "weather.json"
REF_TRENDS_FILE = "referee_trends.json"
REST_FILE = "rest_data.json"
ELO_FILE = "elo_ratings.json"
H2H_FILE = "h2h_data.json"
STADIUMS_FILE = "stadiums_master.json"

# auto-detect injuries file
INJURY_CANDIDATES = [
    "injuries.json",
    "injury_report.json",
    "injuries_latest.json",
    "injuries_fetched.json",
]

def find_injuries_file():
    for f in INJURY_CANDIDATES:
        if os.path.exists(f):
            return f
    for f in os.listdir("."):
        if re.match(r"injur(y|ies).*\.json$", f, re.I):
            return f
    return None

INJURIES_FILE = find_injuries_file()

FEATURES = [
    "spread",
    "total",
    "is_home_fav",
    "home_injuries",
    "away_injuries",
    "temp_c",
    "wind_kph",
    "precip_mm",
    "ref_home_win_pct",
    "ref_over_pct",
    "ref_fav_cover_pct",
    "rest_diff_days",
    "travel_km_diff",
    "elo_diff",
    "h2h_margin_avg",
]

def load_json(path, default):
    if not path or not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def safe_float(x, default=0.0):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default

def safe_int(x, default=0):
    try:
        if x is None:
            return default
        return int(x)
    except Exception:
        return default

def norm_team(name):
    if isinstance(name, dict):
        name = name.get("name") or name.get("abbr") or ""
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())

def norm_matchup(home, away):
    return f"{norm_team(away)}@{norm_team(home)}"

def parse_utc(iso_str):
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d1 = math.radians(lat2 - lat1)
    d2 = math.radians(lon2 - lon1)
    a = math.sin(d1/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(d2/2)**2
    return 2*r*math.atan2(math.sqrt(a), math.sqrt(1-a))


def build_feature_rows():
    combined = load_json(COMBINED_FILE, {}).get("data", [])
    if not combined:
        print("combined.json missing/empty -> no feature rows.")
        return []

    weather = load_json(WEATHER_FILE, {}).get("data", [])
    refs = load_json(REF_TRENDS_FILE, {})
    injuries_raw = load_json(INJURIES_FILE, {}) if INJURIES_FILE else {}
    rest_data = load_json(REST_FILE, {})
    elo_data = load_json(ELO_FILE, {})
    h2h_data = load_json(H2H_FILE, {})
    stadiums = load_json(STADIUMS_FILE, {})

    # Handle injuries in multiple formats
    if isinstance(injuries_raw, list):
        injuries_list = injuries_raw
    elif isinstance(injuries_raw, dict):
        injuries_list = injuries_raw.get("injuries", injuries_raw.get("data", []))
    else:
        injuries_list = []

    # build lookup maps for weather
    wx_by_id = {}
    wx_by_key = {}
    if isinstance(weather, list):
        for w in weather:
            if w.get("event_id"):
                wx_by_id[w["event_id"]] = w
            k = (norm_team(w.get("matchup")), w.get("commence_time"))
            wx_by_key[k] = w

    # Referee trends - support both old format ({data: [...]}) and new ({refs: {name: {...}}})
    ref_by_name = {}
    if isinstance(refs, dict):
        if "refs" in refs:
            # New format: {refs: {name: {home_win_pct, over_pct, ...}}}
            ref_by_name = refs.get("refs", {})
        elif "data" in refs:
            # Old format: [{event_id, home_win_pct, ...}]
            for r in refs.get("data", []):
                if r.get("name"):
                    ref_by_name[r["name"]] = r

    # Injury index: norm_team -> count
    inj_by_team = {}
    for row in injuries_list:
        tn = norm_team(row.get("team") or "")
        if tn:
            inj_by_team.setdefault(tn, 0)
            inj_by_team[tn] += 1

    # Also check game-level merged injuries
    # (merge_injuries.py adds home_injuries/away_injuries directly to games)

    # Stadium coordinate lookup for travel
    stadium_coords = {}
    if isinstance(stadiums, dict):
        stadium_list = stadiums.get("data", stadiums.get("stadiums", []))
    elif isinstance(stadiums, list):
        stadium_list = stadiums
    else:
        stadium_list = []
    for s in stadium_list:
        name = norm_team(s.get("team") or s.get("name") or "")
        lat = s.get("lat") or s.get("latitude")
        lon = s.get("lon") or s.get("longitude")
        if name and lat and lon:
            stadium_coords[name] = (float(lat), float(lon))

    rows = []

    for g in combined:
        home = g.get("home_team")
        away = g.get("away_team")
        if not home or not away:
            continue

        # Extract team names safely (home/away are dicts)
        home_name = home.get("name", "") if isinstance(home, dict) else str(home)
        away_name = away.get("name", "") if isinstance(away, dict) else str(away)
        home_abbr = home.get("abbr", "") if isinstance(home, dict) else ""
        away_abbr = away.get("abbr", "") if isinstance(away, dict) else ""

        event_id = g.get("event_id") or g.get("id")
        commence = g.get("commence_time") or g.get("date_utc")
        sport_key = (g.get("sport_key") or g.get("sport") or "").lower()

        # Spread: prefer tag_favorites output, then odds
        spread = g.get("fav_spread")
        if spread is None:
            odds = g.get("odds") or {}
            spread = safe_float(odds.get("spread"), 0.0)
        else:
            spread = safe_float(spread)

        total_val = g.get("total")
        if total_val is None:
            odds = g.get("odds") or {}
            total_val = odds.get("total")
        total = safe_float(total_val) if total_val is not None else None

        # Favorite/underdog teams
        fav_team = g.get("fav_team") or ""
        dog_team = g.get("dog_team") or ""

        if not fav_team or not dog_team:
            # Infer from spread sign (ESPN: negative = home favored)
            raw_spread = safe_float((g.get("odds") or {}).get("spread"), 0.0)
            if raw_spread < 0:
                fav_team = home_name
                dog_team = away_name
            elif raw_spread > 0:
                fav_team = away_name
                dog_team = home_name
            else:
                fav_team = home_name
                dog_team = away_name

        # is_home_fav
        is_home_fav = 1 if norm_team(fav_team) == norm_team(home_name) else 0

        # Weather lookup
        wx = None
        if event_id and str(event_id) in wx_by_id:
            wx = wx_by_id[str(event_id)]

        venue = g.get("venue") or {}
        is_indoor = venue.get("indoor", False)

        # Defaults: 21C (~70F) neutral temp, 8 kph (~5mph) typical wind
        temp_c = safe_float(wx.get("temperature_c") if wx else None, 21.0)
        wind_kph = safe_float(wx.get("wind_kph") if wx else None, 8.0)
        precip_mm = safe_float(wx.get("precip_mm") if wx else None, 0.0)

        if is_indoor:
            wind_kph = 0.0
            precip_mm = 0.0

        # Referee trends
        ref_home_win_pct = 50.0
        ref_over_pct = 50.0
        ref_fav_cover_pct = 50.0
        officials = g.get("officials") or []
        if officials and ref_by_name:
            for o in officials:
                oname = o.get("name") or o.get("fullName") or o.get("displayName") if isinstance(o, dict) else str(o)
                if oname and oname in ref_by_name:
                    rf = ref_by_name[oname]
                    ref_home_win_pct = safe_float(rf.get("home_win_pct"), 50.0)
                    ref_over_pct = safe_float(rf.get("over_pct"), 50.0)
                    ref_fav_cover_pct = safe_float(rf.get("fav_cover_pct"), 50.0)
                    break  # use first matched official (head ref)

        # Injuries: check game-level merged data first, then global index
        home_inj = safe_int(g.get("injury_count_home"))
        away_inj = safe_int(g.get("injury_count_away"))
        if home_inj == 0 and away_inj == 0:
            home_inj = inj_by_team.get(norm_team(home_name), 0)
            away_inj = inj_by_team.get(norm_team(away_name), 0)

        # Rest days
        rest_diff_days = 0.0
        if rest_data:
            home_rest = safe_float(rest_data.get(norm_team(home_name)) or rest_data.get(home_name), 3.0)
            away_rest = safe_float(rest_data.get(norm_team(away_name)) or rest_data.get(away_name), 3.0)
            rest_diff_days = home_rest - away_rest

        # Travel distance
        travel_km_diff = 0.0
        if stadium_coords:
            game_venue = venue.get("name") or ""
            # Home team travel is ~0, away team travel = distance from their home to game venue
            home_coords = stadium_coords.get(norm_team(home_name))
            away_coords = stadium_coords.get(norm_team(away_name))
            if home_coords and away_coords:
                # Approximate: away team travels to home team's venue
                travel_km_diff = haversine_km(
                    away_coords[0], away_coords[1],
                    home_coords[0], home_coords[1]
                )

        # Elo difference
        elo_diff = 0.0
        if elo_data:
            sport_elo = elo_data.get(sport_key, {})
            home_elo = safe_float(sport_elo.get(home_name) or sport_elo.get(norm_team(home_name)), 1500.0)
            away_elo = safe_float(sport_elo.get(away_name) or sport_elo.get(norm_team(away_name)), 1500.0)
            elo_diff = home_elo - away_elo

        # Head-to-head history
        h2h_margin_avg = 0.0
        if h2h_data:
            matchup_key = f"{norm_team(home_name)}_vs_{norm_team(away_name)}"
            matchup_key_rev = f"{norm_team(away_name)}_vs_{norm_team(home_name)}"
            h2h_rec = h2h_data.get(matchup_key) or h2h_data.get(matchup_key_rev)
            if h2h_rec:
                h2h_margin_avg = safe_float(h2h_rec.get("avg_margin"), 0.0)

        matchup_str = g.get("matchup") or g.get("name") or f"{away_name} @ {home_name}"

        rows.append({
            "event_id": str(event_id) if event_id else norm_team(matchup_str) + (commence or ""),
            "matchup": matchup_str,
            "sport_key": sport_key,
            "commence_time": commence,
            "home_team": home_name,
            "away_team": away_name,
            "fav_team": fav_team,
            "dog_team": dog_team,

            "spread": spread,
            "total": total,

            "is_home_fav": is_home_fav,
            "home_injuries": home_inj,
            "away_injuries": away_inj,

            "temp_c": temp_c,
            "wind_kph": wind_kph,
            "precip_mm": precip_mm,

            "ref_home_win_pct": ref_home_win_pct,
            "ref_over_pct": ref_over_pct,
            "ref_fav_cover_pct": ref_fav_cover_pct,

            "rest_diff_days": rest_diff_days,
            "travel_km_diff": travel_km_diff,
            "elo_diff": elo_diff,
            "h2h_margin_avg": h2h_margin_avg,
        })

    return rows


if __name__ == "__main__":
    rows = build_feature_rows()
    print(f"Built {len(rows)} feature rows.")
