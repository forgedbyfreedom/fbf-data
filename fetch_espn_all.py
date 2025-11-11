#!/usr/bin/env python3
"""
fetch_espn_all.py — ESPN scoreboard odds fetcher (7-day horizon)
Pulls live and upcoming odds from ESPN for multiple sports (NFL, NCAAF, NBA, MLB, NHL, MMA, etc.)
and writes both per-league JSONs and a combined.json file.
"""

import json, requests, time
from datetime import datetime, timezone, timedelta

SPORTS = {
    "americanfootball_nfl": "football/nfl",
    "americanfootball_ncaaf": "football/college-football",
    "basketball_ncaab": "basketball/mens-college-basketball",
    "basketball_ncaaw": "basketball/womens-college-basketball",
    "baseball_mlb": "baseball/mlb",
    "icehockey_nhl": "hockey/nhl",
    "mma_mixedmartialarts": "mma"
}

BASE = "https://site.api.espn.com/apis/site/v2/sports"
HEADERS = {"User-Agent": "ForgedByFreedomDataBot/2.2"}
timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
combined = {"timestamp": timestamp, "data": []}

def fetch_league(key, path):
    events = []
    # Fetch up to 7 days ahead
    for day_offset in range(0, 7):
        date = (datetime.now(timezone.utc) + timedelta(days=day_offset)).strftime("%Y%m%d")
        url = f"{BASE}/{path}/scoreboard?dates={date}"
        print(f"[⏱️] Fetching {key} {date} → {url}")
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 404:
                print(f"   → No {key} events for {date}.")
                continue
            r.raise_for_status()
        except Exception as e:
            print(f"⚠️  Failed {key} ({date}): {e}")
            continue

        blob = r.json()
        for ev in blob.get("events", []):
            comp = ev.get("competitions", [{}])[0]
            competitors = comp.get("competitors", [])
            if len(competitors) != 2:
                continue

            home = next((c for c in competitors if c.get("homeAway") == "home"), {})
            away = next((c for c in competitors if c.get("homeAway") == "away"), {})
            odds_list = comp.get("odds", [])
            if not odds_list:
                continue
            line = odds_list[0]

            home_spread = line.get("homeTeamOdds", {}).get("spread")
            away_spread = line.get("awayTeamOdds", {}).get("spread")
            total = line.get("overUnder")

            row = {
                "sport_key": key,
                "matchup": f"{away.get('team', {}).get('displayName', '')}@{home.get('team', {}).get('displayName', '')}",
                "away_team": away.get("team", {}).get("displayName"),
                "home_team": home.get("team", {}).get("displayName"),
                "away_spread": away_spread,
                "home_spread": home_spread,
                "total": float(total) if total else None,
                "commence_time": ev.get("date"),
                "book": line.get("provider", {}).get("name", "ESPN / Caesars"),
                "fetched_at": datetime.now(timezone.utc).isoformat()
            }

            if row["home_spread"] is not None or row["away_spread"] is not None:
                events.append(row)

        time.sleep(1.5)

    print(f"   → {len(events)} games found total for {key}.")
    return events

def main():
    total = 0
    for key, path in SPORTS.items():
        evs = fetch_league(key, path)
        total += len(evs)
        out_file = f"{key.split('_')[-1]}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump({"timestamp": timestamp, "data": evs}, f, indent=2)
        combined["data"].extend(evs)

    with open("combined.json", "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2)

    print(f"[✅] Wrote {total} games total → combined.json")

if __name__ == "__main__":
    main()
