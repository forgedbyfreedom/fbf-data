#!/usr/bin/env python3
"""
build_predictions.py

Rule-based baseline predictions, ML-ready.

Inputs (optional):
- combined.json           (required for games)
- weather.json            (outdoor games only)
- referee_trends.json     (if historical labels exist)
- injuries.json           (live ESPN injuries)
- power_ratings.json      (if you add it later)

Outputs:
- predictions.json

Generates SU / ATS / OU picks + confidence 0–100.
Safe if any inputs missing.
"""

import json, os, math
from datetime import datetime, timezone

COMBINED_FILE = "combined.json"
WEATHER_FILE = "weather.json"
REF_FILE = "referee_trends.json"
INJ_FILE = "injuries.json"
PR_FILE = "power_ratings.json"
OUTFILE = "predictions.json"

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def index_by_matchup(rows):
    m = {}
    for r in rows:
        key = r.get("matchup")
        if key:
            m[key] = r
    return m

def injuries_by_team(payload):
    out = {}
    for row in payload.get("data", []):
        team = (row.get("team") or "").lower()
        out[team] = row.get("injuries", [])
    return out

def ref_bias_map(payload):
    out = {}
    for r in payload.get("data", []):
        out[(r.get("referee") or "").lower()] = r
    return out

def power_by_team(payload):
    out = {}
    for r in payload.get("data", []):
        tn = (r.get("team_name") or r.get("team") or "").lower()
        if tn:
            out[tn] = float(r.get("rating", 0))
    return out

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def main():
    combined = load_json(COMBINED_FILE, {})
    games = combined.get("data", [])
    if not games:
        payload = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
            "count": 0,
            "data": [],
            "note": "combined.json missing or empty",
        }
        with open(OUTFILE, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"⚠️ Wrote empty {OUTFILE}")
        return

    wx = index_by_matchup(load_json(WEATHER_FILE, {}).get("data", []))
    refs = ref_bias_map(load_json(REF_FILE, {}))
    inj = injuries_by_team(load_json(INJ_FILE, {}))
    pr = power_by_team(load_json(PR_FILE, {}))

    out = []
    for g in games:
        matchup = g.get("matchup")
        fav = g.get("fav_team") or (g.get("favorite") or "").split(" -")[0]
        dog = g.get("dog_team") or (g.get("underdog") or "").split(" +")[0]
        spread = float(g.get("fav_spread") or g.get("spread") or 0)
        total = float(g.get("total") or 0)

        fav_l = (fav or "").lower()
        dog_l = (dog or "").lower()

        # --- Feature signals ---
        fav_pr = pr.get(fav_l, 0)
        dog_pr = pr.get(dog_l, 0)
        pr_edge = fav_pr - dog_pr  # positive favors favorite

        # injury penalties
        fav_inj = len(inj.get(fav_l, []))
        dog_inj = len(inj.get(dog_l, []))
        inj_edge = dog_inj - fav_inj  # positive favors favorite

        # weather penalty (wind/rain reduce total, help dog/under)
        w = wx.get(matchup, {})
        wind = float(w.get("wind_kph") or 0)
        precip = float(w.get("precip_mm") or 0)
        weather_drag = (wind/25.0) + (precip/5.0)

        # referee bias (if exists)
        ref_bias_fav = 0
        ref_bias_over = 0
        # (You add referee assignment later; placeholder uses g["referees"] if present)
        for rname in (g.get("referees") or []):
            rrow = refs.get((rname or "").lower())
            if rrow:
                ref_bias_fav += rrow.get("bias_fav", 0)
                ref_bias_over += rrow.get("bias_over", 0)

        # --- SU pick ---
        su_score = (
            0.6 * (abs(spread) / 7.0) +    # market strength
            0.2 * (pr_edge / 10.0) +       # power edge
            0.1 * (inj_edge / 3.0) +       # injury edge
            0.1 * ref_bias_fav
        )
        su_conf = clamp(50 + su_score * 50, 50, 95)
        su_pick = fav if spread <= 0 else dog

        # --- ATS pick ---
        ats_margin = pr_edge + (inj_edge * 0.8) + (ref_bias_fav * 2.0)
        ats_pick = fav if ats_margin > abs(spread) * 0.2 else dog
        ats_conf = clamp(50 + (ats_margin - abs(spread)*0.2) * 5, 50, 92)

        # --- OU pick ---
        if total <= 0:
            ou_pick, ou_conf = None, None
        else:
            total_delta = (pr_edge * 0.6) - (weather_drag * 4.0) + (ref_bias_over * 2.0)
            ou_pick = "over" if total_delta > 0 else "under"
            ou_conf = clamp(50 + abs(total_delta) * 4, 50, 90)

        out.append({
            "matchup": matchup,
            "sport_key": g.get("sport_key"),
            "commence_time": g.get("commence_time"),
            "favorite_team": fav,
            "underdog_team": dog,
            "spread": spread,
            "total": total if total > 0 else None,
            "SU_pick": su_pick,
            "SU_confidence": round(su_conf, 1),
            "ATS_pick": ats_pick,
            "ATS_confidence": round(ats_conf, 1),
            "OU_pick": ou_pick,
            "OU_confidence": round(ou_conf, 1) if ou_conf else None,
            "signals": {
                "power_edge": pr_edge,
                "injury_edge": inj_edge,
                "weather_drag": round(weather_drag, 3),
                "ref_bias_fav": round(ref_bias_fav, 3),
                "ref_bias_over": round(ref_bias_over, 3),
            }
        })

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "count": len(out),
        "data": out
    }

    with open(OUTFILE, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"✅ Wrote {OUTFILE} with {len(out)} predictions")

if __name__ == "__main__":
    main()
