#!/usr/bin/env python3
"""
referee_trends.py

Builds referee_trends.json from labeled historical results.

Inputs (if present):
- historical_results.json  (YOU add this later)
  Format expected:
  [
    {
      "sport_key":"americanfootball_nfl",
      "referees":["John Doe","Jane Roe"],
      "favorite_team":"Team A",
      "underdog_team":"Team B",
      "fav_spread":-3.5,
      "total": 44.5,
      "fav_score":24,
      "dog_score":20
    }, ...
  ]

If file missing, writes empty trends w/ note.

Outputs:
- referee_trends.json
"""

import json, os, math
from datetime import datetime, timezone
from collections import defaultdict

HIST_FILE = "historical_results.json"
OUTFILE = "referee_trends.json"

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    hist = load_json(HIST_FILE, [])
    if not hist:
        payload = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
            "count": 0,
            "data": [],
            "note": "historical_results.json missing — trends will populate once labels exist",
        }
        with open(OUTFILE, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"⚠️ {OUTFILE} empty (no history)")
        return

    agg = defaultdict(lambda: {
        "games": 0,
        "fav_covers": 0,
        "overs": 0,
        "dog_wins": 0
    })

    for row in hist:
        refs = row.get("referees") or []
        if not refs:
            continue

        fav_score = row.get("fav_score")
        dog_score = row.get("dog_score")
        spread = row.get("fav_spread") or 0
        total = row.get("total") or 0

        if fav_score is None or dog_score is None:
            continue

        fav_margin = fav_score - dog_score
        fav_cover = fav_margin > abs(spread)
        dog_win = dog_score > fav_score
        over = (fav_score + dog_score) > total if total else None

        for rname in refs:
            a = agg[rname]
            a["games"] += 1
            a["fav_covers"] += int(fav_cover)
            a["dog_wins"] += int(dog_win)
            if over is not None:
                a["overs"] += int(over)

    out = []
    for rname, a in agg.items():
        g = a["games"]
        if g < 3:
            continue

        out.append({
            "referee": rname,
            "games": g,
            "fav_cover_rate": round(a["fav_covers"]/g, 4),
            "dog_win_rate": round(a["dog_wins"]/g, 4),
            "over_rate": round(a["overs"]/g, 4),
            "bias_fav": round((a["fav_covers"]/g) - 0.5, 4),
            "bias_over": round((a["overs"]/g) - 0.5, 4),
        })

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "count": len(out),
        "data": sorted(out, key=lambda x: (-x["games"], x["referee"])),
    }

    with open(OUTFILE, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"✅ Wrote {OUTFILE} with {len(out)} ref trend rows")

if __name__ == "__main__":
    main()
