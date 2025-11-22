#!/usr/bin/env python3
"""
referee_trends.py

Builds referee crew trend stats.

Inputs (optional):
- combined.json  (current slate, may include referee fields)
- historical_results.json (future labeled outcomes)

Outputs:
- referee_trends.json

Safe if inputs missing.
"""

import json, os
from datetime import datetime, timezone
from collections import defaultdict

COMBINED_FILE = "combined.json"
HISTORICAL_FILE = "historical_results.json"   # add later
OUTFILE = "referee_trends.json"

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    combined = load_json(COMBINED_FILE, {}).get("data", [])
    hist = load_json(HISTORICAL_FILE, {}).get("data", [])

    # If no historical data yet, write empty safe file
    if not hist:
        payload = {
            "timestamp": stamp,
            "count": 0,
            "data": [],
            "note": "historical_results.json not found yet. Add labeled results to enable trends.",
        }
        with open(OUTFILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"⚠️  Wrote empty {OUTFILE} (no historical results yet)")
        return

    # Expected historical schema per game (you’ll build this later):
    # {
    #   "sport_key": "...",
    #   "matchup": "...",
    #   "commence_time": "...",
    #   "referees": ["Name A","Name B",...],
    #   "home_team": "...",
    #   "away_team": "...",
    #   "home_score": 0,
    #   "away_score": 0,
    #   "total_line": 0,
    #   "spread": 0,
    #   "su_fav_correct": true/false,
    #   "ats_fav_correct": true/false,
    #   "ou_over": true/false,
    #   "penalties_total": 0
    # }

    stats = defaultdict(lambda: {
        "games": 0,
        "SU_fav_hit": 0,
        "ATS_fav_hit": 0,
        "OU_over_hit": 0,
        "penalties_avg": 0.0,
    })

    for g in hist:
        refs = g.get("referees") or []
        if not refs:
            continue

        su = bool(g.get("su_fav_correct"))
        ats = bool(g.get("ats_fav_correct"))
        over = bool(g.get("ou_over"))

        pens = g.get("penalties_total")
        pens = float(pens) if pens is not None else 0.0

        for r in refs:
            s = stats[r]
            s["games"] += 1
            s["SU_fav_hit"] += int(su)
            s["ATS_fav_hit"] += int(ats)
            s["OU_over_hit"] += int(over)
            # running average penalties
            s["penalties_avg"] = ((s["penalties_avg"] * (s["games"] - 1)) + pens) / s["games"]

    out = []
    for ref_name, s in stats.items():
        gcount = s["games"]
        out.append({
            "referee": ref_name,
            "games": gcount,
            "SU_fav_pct": round(100 * s["SU_fav_hit"] / gcount, 2) if gcount else 0,
            "ATS_fav_pct": round(100 * s["ATS_fav_hit"] / gcount, 2) if gcount else 0,
            "Over_pct": round(100 * s["OU_over_hit"] / gcount, 2) if gcount else 0,
            "penalties_avg": round(s["penalties_avg"], 2),
        })

    payload = {
        "timestamp": stamp,
        "count": len(out),
        "data": sorted(out, key=lambda x: x["games"], reverse=True),
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {OUTFILE} with {len(out)} referee trend rows")

if __name__ == "__main__":
    main()
