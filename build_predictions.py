#!/usr/bin/env python3
"""
build_predictions.py

Rule-based baseline picks for SU / ATS / OU.
Uses:
- combined.json (required)
- weather.json (optional, outdoor-only)
- injuries.json (optional)
- referee_trends.json (optional)

Outputs: predictions.json

Safe on blank repo.
"""

import json, os, math
from datetime import datetime, timezone

COMBINED_FILE = "combined.json"
WEATHER_FILE = "weather.json"
INJURIES_FILE = "injuries.json"
REF_TRENDS_FILE = "referee_trends.json"
OUTFILE = "predictions.json"

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def find_weather(matchup, event_id, wx_rows):
    for w in wx_rows:
        if event_id and w.get("event_id") == event_id:
            return w
        if matchup and w.get("matchup") == matchup:
            return w
    return None

def injury_count(team, injuries_map):
    if not team:
        return 0
    return len(injuries_map.get(team, []))

def ou_weather_adjust(total, wx):
    """
    Simple outdoor weather logic:
    - High wind / precip suppress scoring.
    """
    if total is None or wx is None:
        return total, 0.0

    wind = wx.get("wind_kph") or 0
    precip = wx.get("precip_mm") or 0

    adj = 0.0
    if wind >= 25: adj -= 2.0
    if wind >= 35: adj -= 3.5
    if precip >= 2: adj -= 1.5
    if precip >= 5: adj -= 2.5

    return max(0, total + adj), adj

def confidence_from_spread(spread):
    """
    spread magnitude -> rough confidence
    """
    if spread is None:
        return 0.50
    s = abs(spread)
    if s >= 14: return 0.72
    if s >= 10: return 0.68
    if s >= 7:  return 0.64
    if s >= 4:  return 0.58
    if s >= 2:  return 0.55
    return 0.52

def main():
    combined = load_json(COMBINED_FILE, {}).get("data", [])
    if not combined:
        payload = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
            "data": [],
            "note": "combined.json missing or empty"
        }
        with open(OUTFILE, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"⚠️  Wrote empty {OUTFILE}")
        return

    wx_rows = load_json(WEATHER_FILE, {}).get("data", [])
    injuries_map = load_json(INJURIES_FILE, {}).get("data", {})
    ref_trends = load_json(REF_TRENDS_FILE, {}).get("data", [])

    out = []

    for g in combined:
        fav_team = g.get("fav_team") or g.get("favorite_team") or None
        dog_team = g.get("dog_team") or g.get("underdog_team") or None
        spread = g.get("fav_spread")
        if spread is None:
            spread = g.get("spread")
        total = g.get("total")

        # baseline fav/dog from string if missing
        if not fav_team or not dog_team:
            fav_str = g.get("favorite","")
            dog_str = g.get("underdog","")
            fav_team = fav_str.rsplit(" ",1)[0] if fav_str else fav_team
            dog_team = dog_str.rsplit(" ",1)[0] if dog_str else dog_team

        wx = find_weather(g.get("matchup"), g.get("event_id"), wx_rows)

        # Injuries (simple downgrade)
        fav_inj = injury_count(fav_team, injuries_map)
        dog_inj = injury_count(dog_team, injuries_map)
        inj_edge = dog_inj - fav_inj  # positive helps fav

        # SU pick
        su_pick = fav_team or g.get("home_team")
        su_conf = confidence_from_spread(spread) + min(0.08, inj_edge*0.01)

        # ATS pick
        # If injuries favor fav, lean ATS fav; else small spreads lean dog
        ats_pick = None
        if spread is None:
            ats_pick = None
            ats_conf = 0.50
        else:
            if inj_edge >= 2 and abs(spread) <= 10:
                ats_pick = f"{fav_team} {spread}"
                ats_conf = min(0.70, confidence_from_spread(spread) + 0.03)
            elif abs(spread) <= 3:
                ats_pick = f"{dog_team} +{abs(spread)}"
                ats_conf = 0.55
            else:
                ats_pick = f"{fav_team} {spread}"
                ats_conf = confidence_from_spread(spread) - 0.02

        # OU pick with weather adjust
        ou_pick, ou_conf = None, 0.50
        if total is not None:
            adj_total, adj = ou_weather_adjust(total, wx)
            # if weather suppresses, prefer Under slightly
            ou_pick = "Under" if adj < 0 else "Over"
            ou_conf = 0.54 + min(0.06, abs(adj)*0.01)

        out.append({
            "sport_key": g.get("sport_key"),
            "matchup": g.get("matchup"),
            "commence_time": g.get("commence_time"),
            "book": g.get("book"),
            "fav_team": fav_team,
            "dog_team": dog_team,
            "spread": spread,
            "total": total,
            "weather_used": bool(wx),
            "injuries_used": bool(injuries_map),
            "su_pick": su_pick,
            "su_confidence": round(max(0.50, min(0.80, su_conf)), 3),
            "ats_pick": ats_pick,
            "ats_confidence": round(max(0.50, min(0.75, ats_conf)), 3),
            "ou_pick": ou_pick,
            "ou_confidence": round(max(0.50, min(0.70, ou_conf)), 3),
            "baseline_model": "rule_v1"
        })

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "count": len(out),
        "data": out
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {OUTFILE} with {len(out)} predictions")

if __name__ == "__main__":
    main()
