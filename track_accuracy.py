#!/usr/bin/env python3
"""
track_accuracy.py
Tracks accuracy for SU, ATS, O/U from 11/26/2025 forward.
Outputs per-sport AND cumulative accuracy into accuracy.json.
"""

import json, os, requests
from datetime import datetime, timezone

OUTPUT = "accuracy.json"
DATE_CUTOFF = datetime(2025, 11, 27)

LEAGUE_MAP = {
    "nfl": "football/leagues/nfl",
    "ncaaf": "football/leagues/college-football",
    "nba": "basketball/leagues/nba",
    "ncaab": "basketball/leagues/mens-college-basketball",
    "nhl": "hockey/leagues/nhl",
}

def get(url):
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except:
        return None

def parse_game_date(g):
    raw = g.get("date_local") or g.get("date_utc")
    if not raw:
        return None
    try:
        return datetime.strptime(raw.replace(" ET", ""), "%Y-%m-%d %I:%M %p")
    except:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except:
            return None

def get_score_map(ev):
    try:
        comps = ev["competitions"][0]["competitors"]
        out = {}
        for c in comps:
            name = c["team"]["displayName"]
            out[name] = int(c.get("score", 0))
        return out
    except:
        return {}

def main():
    if not os.path.exists("combined.json"):
        print("❌ missing combined.json")
        return

    with open("combined.json") as f:
        games = json.load(f).get("data", [])

    # Initialize stats buckets
    stats = {
        "ALL": {"SU": {"w":0,"t":0}, "ATS":{"w":0,"t":0}, "OU":{"w":0,"t":0}},
        "NFL": {"SU": {"w":0,"t":0}, "ATS":{"w":0,"t":0}, "OU":{"w":0,"t":0}},
        "NCAAF":{"SU":{"w":0,"t":0}, "ATS":{"w":0,"t":0}, "OU":{"w":0,"t":0}},
        "NBA": {"SU":{"w":0,"t":0}, "ATS":{"w":0,"t":0}, "OU":{"w":0,"t":0}},
        "NCAAB":{"SU":{"w":0,"t":0}, "ATS":{"w":0,"t":0}, "OU":{"w":0,"t":0}},
        "NHL": {"SU":{"w":0,"t":0}, "ATS":{"w":0,"t":0}, "OU":{"w":0,"t":0}},
    }

    for g in games:
        sport_key = g.get("sport", "").lower()
        sport = sport_key.upper()

        if sport not in stats:
            continue

        g_date = parse_game_date(g)
        if not g_date or g_date < DATE_CUTOFF:
            continue

        fav = g.get("favorite_team")
        dog = g.get("dog_team")
        spread = g.get("fav_spread")
        total = g.get("total")

        league_path = LEAGUE_MAP.get(sport_key)
        if not league_path:
            continue

        # Pull ESPN event list
        events = get(f"https://sports.core.api.espn.com/v2/sports/{league_path}/events")
        if not events or "items" not in events:
            continue

        # Match game
        event_json = None
        for ev in events["items"]:
            ref = ev.get("$ref")
            if not ref:
                continue
            data = get(ref)
            if not data:
                continue

            name = data.get("name", "")
            if fav and fav in name and dog and dog in name:
                event_json = data
                break

        if not event_json:
            continue

        scores = get_score_map(event_json)
        if fav not in scores or dog not in scores:
            continue

        fav_s = scores[fav]
        dog_s = scores[dog]
        total_s = fav_s + dog_s

        # SU
        su_ok = fav_s > dog_s
        stats["ALL"]["SU"]["t"] += 1
        stats[sport]["SU"]["t"] += 1
        stats["ALL"]["SU"]["w"] += int(su_ok)
        stats[sport]["SU"]["w"] += int(su_ok)

        # ATS — only count if spread exists AND ATS pick was made
        if spread is not None and g.get("ats_pick_team"):
            ats_ok = (fav_s - dog_s) > abs(spread)
            stats["ALL"]["ATS"]["t"] += 1
            stats[sport]["ATS"]["t"] += 1
            stats["ALL"]["ATS"]["w"] += int(ats_ok)
            stats[sport]["ATS"]["w"] += int(ats_ok)

        # TOTAL — only count if O/U pick exists
        if total is not None and g.get("total_pick"):
            ou_ok = (total_s > total) if g["total_pick"].lower() == "over" else (total_s < total)
            stats["ALL"]["OU"]["t"] += 1
            stats[sport]["OU"]["t"] += 1
            stats["ALL"]["OU"]["w"] += int(ou_ok)
            stats[sport]["OU"]["w"] += int(ou_ok)

    # Convert to percentages
    out = {"timestamp": datetime.now(timezone.utc).isoformat(), "sports": {}}
    for k, v in stats.items():
        out["sports"][k] = {
            "SU": round((v["SU"]["w"] / v["SU"]["t"] * 100), 2) if v["SU"]["t"] else 0,
            "ATS": round((v["ATS"]["w"] / v["ATS"]["t"] * 100), 2) if v["ATS"]["t"] else 0,
            "OU": round((v["OU"]["w"] / v["OU"]["t"] * 100), 2) if v["OU"]["t"] else 0,
        }

    with open(OUTPUT, "w") as f:
        json.dump(out, f, indent=2)

    print("✅ Wrote accuracy.json")
