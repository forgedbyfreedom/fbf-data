#!/usr/bin/env python3
"""
feature_engineering.py

Turns combined.json + enrichments into ML-ready rows.
Safe if enrichments missing.
"""

import json, os, math
from datetime import datetime, timezone

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def build_feature_rows():
    combined = load_json("combined.json", {}).get("data", [])
    weather = load_json("weather.json", {}).get("data", [])
    refs = load_json("referee_trends.json", {}).get("data", [])
    injuries = load_json("injuries.json", {}).get("data", [])

    wx_by_event = {w.get("event_id"): w for w in weather if w.get("event_id")}
    ref_by_name = {r.get("referee"): r for r in refs if r.get("referee")}

    inj_by_team = {}
    for i in injuries:
        t = i.get("team")
        inj_by_team.setdefault(t, 0)
        inj_by_team[t] += 1

    rows = []
    for g in combined:
        fav = g.get("fav_team")
        dog = g.get("dog_team")
        if not fav or not dog:
            continue

        wx = wx_by_event.get(g.get("event_id"), {})
        home = g.get("home_team")
        away = g.get("away_team")

        rows.append({
            "sport_key": g.get("sport_key"),
            "spread": g.get("fav_spread") or 0.0,
            "total": g.get("total") or 0.0,
            "is_home_fav": 1.0 if fav == home else 0.0,
            "home_injuries": float(inj_by_team.get(home, 0)),
            "away_injuries": float(inj_by_team.get(away, 0)),
            "temp_c": float(wx.get("temperature_c") or 0.0),
            "wind_kph": float(wx.get("wind_kph") or 0.0),
            "precip_mm": float(wx.get("precip_mm") or 0.0),
            # placeholder for ref bias once you add referee mapping
            "ref_home_win_pct": 50.0,
            "ref_over_pct": 50.0,
            "ref_fav_cover_pct": 50.0,
            "event_id": g.get("event_id"),
            "matchup": g.get("matchup"),
            "fav_team": fav,
            "dog_team": dog,
            "home_team": home,
            "away_team": away,
            "commence_time": g.get("commence_time"),
        })

    return rows
