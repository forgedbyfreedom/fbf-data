#!/usr/bin/env python3
"""
referee_trends.py

Creates a baseline referee trends file from historical_results.json if present.
If historical_results.json is missing, writes an empty but valid referee_trends.json.

Output: referee_trends.json

This is a safe scaffold — you can enrich as you collect more labeled games.

Requires: pandas (already in your reqs)
"""

import json, os
from datetime import datetime, timezone
import pandas as pd

HIST_FILE = "historical_results.json"   # produced by build_historical_results.py
OUTFILE = "referee_trends.json"

def utc_ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

def main():
    if not os.path.exists(HIST_FILE):
        payload = {
            "timestamp": utc_ts(),
            "count": 0,
            "data": [],
            "note": "historical_results.json not found yet — trends will populate once labeled results exist."
        }
        with open(OUTFILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"⚠️  {HIST_FILE} missing. Wrote empty {OUTFILE}.")
        return

    with open(HIST_FILE, "r", encoding="utf-8") as f:
        hist = json.load(f).get("data", [])

    if not hist:
        payload = {"timestamp": utc_ts(), "count": 0, "data": [], "note": "no historical rows"}
        with open(OUTFILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"⚠️  No history rows. Wrote empty {OUTFILE}.")
        return

    df = pd.DataFrame(hist)

    # Expect columns (best-effort):
    # referee, total_points, total_line, fav_spread, fav_score, dog_score, ats_win, ou_win
    for col in ["referee", "total_points", "total_line", "ats_win", "ou_win"]:
        if col not in df.columns:
            df[col] = None

    grouped = df.dropna(subset=["referee"]).groupby("referee")

    trends = []
    for ref, g in grouped:
        games = len(g)
        if games == 0:
            continue

        ats_rate = float(g["ats_win"].mean()) if g["ats_win"].notna().any() else None
        ou_rate  = float(g["ou_win"].mean()) if g["ou_win"].notna().any() else None

        avg_total_pts = float(g["total_points"].mean()) if g["total_points"].notna().any() else None
        avg_total_line = float(g["total_line"].mean()) if g["total_line"].notna().any() else None

        trends.append({
            "referee": ref,
            "games": games,
            "ATS_cover_rate": round(ats_rate, 3) if ats_rate is not None else None,
            "Over_rate": round(ou_rate, 3) if ou_rate is not None else None,
            "avg_total_points": round(avg_total_pts, 2) if avg_total_pts is not None else None,
            "avg_total_line": round(avg_total_line, 2) if avg_total_line is not None else None,
        })

    payload = {
        "timestamp": utc_ts(),
        "count": len(trends),
        "data": sorted(trends, key=lambda x: (-x["games"], x["referee"]))
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {OUTFILE} with {len(trends)} referee trend rows")

if __name__ == "__main__":
    main()
