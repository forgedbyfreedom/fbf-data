#!/usr/bin/env python3
"""
fetch_espn_odds_detailed.py
Pulls live spreads, totals, and favorites from ESPN internal APIs.
"""

import json, requests, time
from datetime import datetime, timezone

BASE = "https://site.api.espn.com/apis/site/v2/sports"
SPORTS = {
    "americanfootball_nfl": "football/nfl",
    "americanfootball_ncaaf": "football/college-football",
    "basketball_nba": "basketball/nba",
    "baseball_mlb": "baseball/mlb",
    "icehockey_nhl": "hockey/nhl",
    "mma_mixedmartialarts": "mma",
}

def get_json(url):
    """Helper to safely fetch JSON from ESPN"""
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️  Failed {url}: {e}")
        return None

def extract_odds(event):
    """Extract odds details for a given ESPN event"""
    try:
        comp = event["competitions"][0]
        competitors = comp["competitors"]
        home = [t for t in competitors if t["homeAway"] == "home"][0]
        away = [t for t in competitors if t["homeAway"] == "away"][0]
        home_team = home["team"]["displayName"]
        away_team = away["team"]["displayName"]

        # Access competition odds endpoint
        odds_url = comp.get("odds", [{}])[0].get("links", [{}])[0].get("href")
        if not odds_url:
            return None
        odds_data = get_json(odds_url)
        if not odds_data or "items" not in odds_data:
            return None

        best_line = odds_data["items"][0]
        details = best_line.get("details", "")
        over_under = best_line.get("overUnder")
        provider = best_line["provider"]["name"]

        # Determine spread and favorite
        spread = None
        fav_team = None
        dog_team = None
        if " " in details:
            try:
                parts = details.split()
                spread_val = float(parts[-1])
                if spread_val < 0:
                    fav_team = parts[0]
                    dog_team = home_team if fav_team == away_team else away_team
                    spread = spread_val
                else:
                    fav_team = home_team if parts[0] == away_team else away_team
                    dog_team = home_team if fav_team == away_team else away_team
                    spread = -spread_val
            except Exception:
                pass

        return {
            "sport_key": event["id"].split("/")[0] if "id" in event else "",
            "matchup": f"{away_team}@{home_team}",
            "home_team": home_team,
            "away_team": away_team,
            "favorite_team": fav_team,
            "dog_team": dog_team,
            "fav_spread": spread,
            "total": over_under,
            "book": provider,
            "commence_time": event["date"],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        print(f"⚠️ Error parsing event: {e}")
        return None

def main():
    all_data = []
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    for key, path in SPORTS.items():
        print(f"[⏱️] Fetching {key} odds...")
        sb_url = f"{BASE}/{path}/scoreboard"
        sb_data = get_json(sb_url)
        if not sb_data or "events" not in sb_data:
            print(f"⚠️  No events found for {key}")
            continue

        for event in sb_data["events"]:
            odds = extract_odds(event)
            if odds:
                odds["sport_key"] = key
                all_data.append(odds)

        print(f"   → {len(all_data)} total games so far.\n")

    combined = {"timestamp": timestamp, "data": all_data}
    with open("combined.json", "w") as f:
        json.dump(combined, f, indent=2)
    print(f"[✅] Saved combined.json with {len(all_data)} games.")

if __name__ == "__main__":
    main()

