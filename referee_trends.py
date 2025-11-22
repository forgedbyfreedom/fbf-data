#!/usr/bin/env python3
"""
referee_trends.py

Builds referee trends if referees.json (per-game assignments) exists.
If it doesn't exist yet, safely writes an empty trends file.

Expected referees.json flexible shape:
[
  {
    "referee": "Name",
    "sport_key": "...",
    "penalties_per_game": 12.3,
    "home_bias": 0.8,
    "over_bias": 0.6
  },
  ...
]

Outputs: referee_trends.json
"""

import json, os
from collections import defaultdict
from datetime import datetime, timezone

REF_FILE = "referees.json"
OUTFILE = "referee_trends.json"

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    refs = load_json(REF_FILE, [])
    if not refs:
        payload = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
            "count": 0,
            "data": [],
            "note": "referees.json missing or empty. Add ref assignments to enable trends.",
        }
        with open(OUTFILE, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"⚠️  Wrote empty {OUTFILE}")
        return

    agg = defaultdict(lambda: {"games":0, "pen":0.0, "home_bias":0.0, "over_bias":0.0})

    for r in refs:
        name = r.get("referee") or r.get("name")
        if not name:
            continue
        a = agg[name]
        a["games"] += 1
        a["pen"] += float(r.get("penalties_per_game") or 0)
        a["home_bias"] += float(r.get("home_bias") or 0)
        a["over_bias"] += float(r.get("over_bias") or 0)

    trends = []
    for name, a in agg.items():
        g = a["games"]
        trends.append({
            "referee": name,
            "games_sampled": g,
            "penalties_per_game_avg": round(a["pen"]/g, 2),
            "home_bias_avg": round(a["home_bias"]/g, 3),
            "over_bias_avg": round(a["over_bias"]/g, 3),
        })

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "count": len(trends),
        "data": sorted(trends, key=lambda x: -x["games_sampled"]),
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {OUTFILE} with {len(trends)} refs")

if __name__ == "__main__":
    main()
