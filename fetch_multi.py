#!/usr/bin/env python3
"""
fetch_multi.py
Rebuilds odds for all major leagues (NFL, NCAAF, NCAAM, NCAAW, MLB, NHL, UFC)
from ESPN public APIs — writes each to its own JSON and a combined.json file.
"""

import json, requests, os
from datetime import datetime, timezone

# ----------------------------
# ESPN API endpoints
# ----------------------------
SPORTS = {
    "americanfootball_nfl": "football/nfl",
    "americanfootball_ncaaf": "football/college-football",
    "basketball_ncaab": "basketball/mens-college-basketball",
    "basketball_ncaaw": "basketball/womens-college-basketball",
    "baseball_mlb": "baseball/mlb",
    "icehockey_nhl": "hockey/nhl",
    "mma_mixedmartialarts": "mma"
}

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

def fetch_league(sport_key, espn_path):
    url = f"{BASE_URL}/{espn_path}/scoreboard"
    print(f"[⏱️] Fetching {sport_key} → {url}")

    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"⚠️  Failed {sport_key}: {e}")
        return []

    events = data.get("events", [])
    results = []
    for ev in events:
        comp = ev.get("competitions", [{}])[0]
        oddslist = comp.get("odds", [])
        if not oddslist:
            continue

        odds = oddslist[0]
        details = odds.get("details", "")
        teams = comp.get("competitors", [])

        if len(teams) != 2:
            continue

        home = next((t["team"]["displayName"] for t in teams if t.get("homeAway") == "home"), "")
        away = next((t["team"]["displayName"] for t in teams if t.get("homeAway") == "away"), "")

        spread = None
        favorite = None
        dog = None

        # Detect favorite from ESPN's "details" field (e.g., "NE -3.5")
        if details:
            parts = details.split()
            for i, p in enumerate(parts):
                if p.startswith("-") or p.startswith("+"):
                    try:
                        spread_val = float(p.replace("+", ""))
                        spread = -abs(spread_val) if "-" in p else abs(spread_val)
                        favorite = parts[i - 1] if i > 0 else None
                    except Exception:
                        continue

        result = {
            "sport_key": sport_key,
            "matchup": f"{away}@{home}",
            "commence_time": ev.get("date"),
            "home_team": home,
            "away_team": away,
            "favorite_team": favorite or "unknown",
            "fav_spread": spread,
            "book": "ESPN",
            "fetched_at": datetime.now(timezone.utc).isoformat()
        }
        results.append(result)

    print(f"   → {len(results)} games found.")
    return results


def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    combined = []

    for key, path in SPORTS.items():
        data = fetch_league(key, path)
        combined.extend(data)
        out_path = os.path.join(OUT_DIR, f"{key.split('_')[-1]}.json")
        with open(out_path, "w") as f:
            json.dump({"timestamp": timestamp, "data": data}, f, indent=2)

    combined_path = os.path.join(OUT_DIR, "combined.json")
    with open(combined_path, "w") as f:
        json.dump({"timestamp": timestamp, "data": combined}, f, indent=2)

    print(f"[✅] Wrote {len(combined)} total games → {combined_path}")


if __name__ == "__main__":
    main()

