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
- injuries.json / *_injuries.json / injuries_*.json  (injury counts)

Output:
- build_feature_rows() returns list[dict]
- FEATURES list defines model columns
"""

import os, json, re, math
from datetime import datetime, timezone

COMBINED_FILE = "combined.json"
WEATHER_FILE = "weather.json"
REF_TRENDS_FILE = "referee_trends.json"

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
    # fallback glob
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
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())

def norm_matchup(home, away):
    return f"{norm_team(away)}@{norm_team(home)}"

def parse_utc(iso_str):
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

def haversine_km(lat1, lon1, lat2, lon2):
    # basic travel feature (optional)
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d1 = math.radians(lat2 - lat1)
    d2 = math.radians(lon2 - lon1)
    a = math.sin(d1/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(d2/2)**2
    return 2*r*math.atan2(math.sqrt(a), math.sqrt(1-a))

def build_feature_rows():
    combined = load_json(COMBINED_FILE, {}).get("data", [])
    if not combined:
        print("⚠️ combined.json missing/empty → no feature rows.")
        return []

    weather = load_json(WEATHER_FILE, {}).get("data", [])
    refs = load_json(REF_TRENDS_FILE, {}).get("data", [])
    injuries = load_json(INJURIES_FILE, {}).get("data", []) if INJURIES_FILE else []

    # build lookup maps
    wx_by_id = {w.get("event_id"): w for w in weather if w.get("event_id")}
    ref_by_id = {r.get("event_id"): r for r in refs if r.get("event_id")}

    # fallback lookup by matchup+time
    wx_by_key = {}
    for w in weather:
        k = (norm_team(w.get("matchup")), w.get("commence_time"))
        wx_by_key[k] = w

    ref_by_key = {}
    for r in refs:
        k = (norm_team(r.get("matchup")), r.get("commence_time"))
        ref_by_key[k] = r

    inj_by_team = {}
    for row in injuries:
        tn = norm_team(row.get("team"))
        if tn:
            inj_by_team[tn] = safe_int(row.get("injuries", row.get("count", 0)), 0)

    rows = []

    for g in combined:
        home = g.get("home_team")
        away = g.get("away_team")
        if not home or not away:
            continue

        event_id = g.get("event_id")  # may be None
        commence = g.get("commence_time")
        matchup_key = norm_matchup(home, away)
        time_dt = parse_utc(commence)

        spread = safe_float(g.get("spread", g.get("fav_spread")))
        total = safe_float(g.get("total")) if g.get("total") is not None else None

        fav_team = g.get("fav_team") or g.get("favorite_team") or g.get("fav") or g.get("fav_team_name")
        dog_team = g.get("dog_team") or g.get("underdog_team") or g.get("dog") or g.get("dog_team_name")

        if not fav_team or not dog_team:
            # best-effort: infer favorite from spread sign
            fav_team = g.get("home_team") if spread < 0 else g.get("away_team")
            dog_team = away if fav_team == home else home

        # lookup weather
        wx = None
        if event_id and event_id in wx_by_id:
            wx = wx_by_id[event_id]
        else:
            wx = wx_by_key.get((norm_team(g.get("matchup")), commence))

        temp_c = safe_float(wx.get("temperature_c"), 0.0) if wx else 0.0
        wind_kph = safe_float(wx.get("wind_kph"), 0.0) if wx else 0.0
        precip_mm = safe_float(wx.get("precip_mm"), 0.0) if wx else 0.0

        # lookup referee trends
        rf = None
        if event_id and event_id in ref_by_id:
            rf = ref_by_id[event_id]
        else:
            rf = ref_by_key.get((norm_team(g.get("matchup")), commence))

        ref_home_win_pct = safe_float(rf.get("home_win_pct"), 50.0) if rf else 50.0
        ref_over_pct = safe_float(rf.get("over_pct"), 50.0) if rf else 50.0
        ref_fav_cover_pct = safe_float(rf.get("fav_cover_pct"), 50.0) if rf else 50.0

        # injuries
        home_inj = inj_by_team.get(norm_team(home), 0)
        away_inj = inj_by_team.get(norm_team(away), 0)

        # is home favorite
        is_home_fav = 1 if norm_team(fav_team) == norm_team(home) else 0

        # placeholders for next upgrades
        rest_diff_days = 0.0
        travel_km_diff = 0.0
        elo_diff = 0.0

        rows.append({
            "event_id": event_id or matchup_key + (commence or ""),
            "matchup": g.get("matchup") or f"{away} @ {home}",
            "sport_key": g.get("sport_key"),
            "commence_time": commence,
            "home_team": home,
            "away_team": away,
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
        })

    return rows


if __name__ == "__main__":
    rows = build_feature_rows()
    print(f"✅ Built {len(rows)} feature rows.")
