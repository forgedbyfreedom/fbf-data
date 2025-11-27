#!/usr/bin/env python3
"""
build_ref_trends.py
Uses history to compute referee O/U bias + home-team bias.
Output: referee_trends.json
"""

import json, os
from collections import defaultdict

OUT = "referee_trends.json"

def load_history():
    if not os.path.exists("history/history_index.json"):
        print("❌ Run build_historical.py first")
        exit()
    with open("history/history_index.json") as f:
        return json.load(f)

def build_trends():
    hist = load_history()
    refs = defaultdict(lambda: {
        "games": 0,
        "avg_total": 0.0,
        "home_cover_bias": 0.0
    })

    for sport, events in hist.items():
        if sport == "timestamp":
            continue

        for ev in events:
            comps = ev.get("competitions", [])
            if not comps:
                continue

            comp = comps[0]
            officials = comp.get("officials") or []
            competitors = comp.get("competitors") or []

            if len(competitors) != 2:
                continue

            scores = []
            for c in competitors:
                try:
                    scores.append(int(c.get("score", 0)))
                except:
                    scores.append(0)

            if len(scores) != 2:
                continue

            total = sum(scores)
            margin = scores[0] - scores[1]

            for ref in officials:
                name = ref.get("displayName")
                if not name:
                    continue

                r = refs[name]
                r["games"] += 1
                r["avg_total"] += total
                r["home_cover_bias"] += 1 if margin > 0 else -1

    for name, r in refs.items():
        g = r["games"]
        if g > 0:
            r["avg_total"] = round(r["avg_total"] / g, 2)
            r["home_cover_bias"] = round(r["home_cover_bias"] / g, 3)

    with open(OUT, "w") as f:
        json.dump(refs, f, indent=2)

    print(f"✅ Built {OUT} with {len(refs)} referees")

if __name__ == "__main__":
    build_trends()
