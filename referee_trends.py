#!/usr/bin/env python3
"""
referee_trends.py

Builds referee_trends.json from historical_results.json (if present).
Tracks:
- ATS bias (fav cover %)
- O/U bias (over %)
- Home win %

Safe if no history yet.
"""

import json, os
from collections import defaultdict
from datetime import datetime, timezone

HIST_FILE = "historical_results.json"
OUTFILE = "referee_trends.json"

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    hist = load_json(HIST_FILE, {}).get("data", [])
    if not hist:
        payload = {
            "timestamp": ts,
            "count": 0,
            "data": [],
            "note": "No historical_results.json yet. Trends will populate after games finish."
        }
        with open(OUTFILE, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"⚠️ Wrote empty {OUTFILE} (no history)")
        return

    agg = defaultdict(lambda: {"games":0, "home_wins":0, "fav_covers":0, "overs":0})

    for g in hist:
        ref = g.get("referee") or g.get("ref_crew") or "UNKNOWN"
        a = agg[ref]

        a["games"] += 1
        if g.get("home_win"):
            a["home_wins"] += 1
        if g.get("fav_cover"):
            a["fav_covers"] += 1
        if g.get("over"):
            a["overs"] += 1

    out = []
    for ref, a in agg.items():
        games = a["games"] or 1
        out.append({
            "referee": ref,
            "games": a["games"],
            "home_win_pct": round(a["home_wins"]/games*100, 2),
            "fav_cover_pct": round(a["fav_covers"]/games*100, 2),
            "over_pct": round(a["overs"]/games*100, 2),
        })

    payload = {"timestamp": ts, "count": len(out), "data": out}
    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {OUTFILE} ({len(out)} crews)")

if __name__ == "__main__":
    main()
