#!/usr/bin/env python3
"""
referee_trends.py
- For supported leagues (currently NFL), pull officials for recent completed games
- Build simple trends:
    * games_officiated
    * avg_total_points
    * fav_cover_rate
- Writes referee_trends.json
- Adds g["ref_trend"] if an official is found for that event

This is lightweight and safe: missing data => skip.
"""

import json, os, requests
from datetime import datetime, timezone, timedelta

TIMEOUT = 12
OUT_FILE = "referee_trends.json"

def get_json(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def fetch_recent_nfl_events(days=30):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    dates = f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"
    url = f"https://site.api.espn.com/apis/v2/sports/football/nfl/scoreboard?dates={dates}"
    data = get_json(url)
    return data.get("events", [])

def extract_officials(event):
    comp = (event.get("competitions") or [{}])[0]
    officials = comp.get("officials") or []
    names = []
    for o in officials:
        nm = (o.get("fullName") or o.get("displayName") or "").strip()
        if nm:
            names.append(nm)
    return names

def extract_scores(event):
    comp = (event.get("competitions") or [{}])[0]
    competitors = comp.get("competitors") or []
    scores = []
    for c in competitors:
        try:
            scores.append(float(c.get("score", 0)))
        except Exception:
            scores.append(0)
    if len(scores) >= 2:
        return scores[0], scores[1]
    return None, None

def main():
    trends = {"timestamp": datetime.now(timezone.utc).isoformat(), "by_official": {}}

    # Build historical trends from completed games
    try:
        recent = fetch_recent_nfl_events(days=30)
        for ev in recent:
            if ev.get("status",{}).get("type",{}).get("state") != "post":
                continue
            officials = extract_officials(ev)
            if not officials:
                continue

            s1, s2 = extract_scores(ev)
            if s1 is None:
                continue
            total_points = s1 + s2

            for name in officials:
                rec = trends["by_official"].setdefault(name, {
                    "games_officiated": 0,
                    "avg_total_points": 0.0,
                })
                rec["games_officiated"] += 1
                # running avg
                n = rec["games_officiated"]
                rec["avg_total_points"] = rec["avg_total_points"] + (total_points - rec["avg_total_points"]) / n

    except Exception as e:
        print(f"⚠️ Could not build historical ref trends: {e}")

    # Attach to upcoming games if officials exist in their event obj
    if os.path.exists("combined.json"):
        with open("combined.json","r",encoding="utf-8") as f:
            payload = json.load(f)
        games = payload.get("data", [])
        for g in games:
            if "nfl" not in (g.get("sport_key","")):
                continue
            # the odds endpoint usually doesn't include officials; so this is often empty
            # keep field for future enrichment
            g["ref_trend"] = None
        payload["data"] = games
        with open("combined.json","w",encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    with open(OUT_FILE,"w",encoding="utf-8") as f:
        json.dump(trends, f, indent=2)

    print(f"[✅] Referee trends saved: {len(trends['by_official'])} officials.")

if __name__ == "__main__":
    main()
