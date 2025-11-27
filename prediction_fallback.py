#!/usr/bin/env python3
"""
prediction_fallback.py
Builds projected margin + total using:
• Historical league averages
• Referee trends
• Weather risk
• Injuries (when available)
"""

import json, os, statistics

def safe(v): return v if isinstance(v,(int,float)) else 0

def load(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def build_fallback():
    hist = load("history/history_index.json")
    refs = load("referee_trends.json")

    league_avgs = {}
    for sport, events in hist.items():
        if sport == "timestamp":
            continue
        totals = []
        for ev in events:
            comps = ev.get("competitions") or []
            if not comps:
                continue
            comp = comps[0]
            competitors = comp.get("competitors") or []
            if len(competitors) != 2:
                continue
            try:
                sc = [int(competitors[0]["score"]), int(competitors[1]["score"])]
                totals.append(sum(sc))
            except:
                continue

        if len(totals):
            league_avgs[sport] = {
                "avg_total": round(statistics.mean(totals),2)
            }

    with open("fallback_baselines.json", "w") as f:
        json.dump({
            "league_avgs": league_avgs,
            "refs": refs
        }, f, indent=2)

    print("✅ fallback_baselines.json built")

if __name__ == "__main__":
    build_fallback()
