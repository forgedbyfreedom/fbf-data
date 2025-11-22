#!/usr/bin/env python3
"""
fetch_espn_all.py

Unified ESPN odds fetcher.
- Pulls upcoming events + odds from ESPN Core API by league.
- Produces per-league *_latest.json and combined.json.

Safe if ESPN changes fields: skips gracefully.
"""

import json, os, time
from datetime import datetime, timezone
import requests

TIMEOUT = 12
OUT_COMBINED = "combined.json"

LEAGUES = {
    "americanfootball_nfl": "football/leagues/nfl",
    "americanfootball_ncaaf": "football/leagues/college-football",
    "basketball_nba": "basketball/leagues/nba",
    "basketball_ncaab": "basketball/leagues/mens-college-basketball",
    "icehockey_nhl": "hockey/leagues/nhl",
    "baseball_mlb": "baseball/leagues/mlb",
    "mma_mixed_martial_arts": "mma/leagues/ufc",
}

def get_json(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def safe(o, path, default=None):
    cur = o
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur

def parse_event(event):
    comp = safe(event, ["competitions", 0], {})
    competitors = comp.get("competitors", [])
    if len(competitors) < 2:
        return None

    home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
    away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

    home_team = safe(home, ["team","displayName"], "")
    away_team = safe(away, ["team","displayName"], "")
    if not home_team or not away_team:
        return None

    commence = event.get("date") or safe(comp, ["date"], None)

    odds = safe(comp, ["odds", 0], {}) or {}
    spread = odds.get("spread")
    over_under = odds.get("overUnder")
    provider = safe(odds, ["provider","name"], "ESPN").lower()

    # Determine favorite/dog based on spread sign
    fav_team = None
    dog_team = None
    fav_spread = None
    dog_spread = None

    if spread is not None:
        try:
            spread = float(spread)
            # ESPN spread is usually from home perspective in some feeds
            # We'll infer using "favorite" field if present
            fav_field = odds.get("favorite")
            if fav_field:
                fav_team = fav_field
                dog_team = away_team if fav_team == home_team else home_team
                fav_spread = spread if fav_team == home_team else -spread
                dog_spread = -fav_spread
            else:
                # fallback: negative spread => home favored
                fav_team = home_team if spread < 0 else away_team
                dog_team = away_team if fav_team == home_team else home_team
                fav_spread = spread if fav_team == home_team else -spread
                dog_spread = -fav_spread
        except Exception:
            pass

    matchup = f"{away_team}@{home_team}"

    return {
        "sport_key": None,  # filled at caller
        "matchup": matchup,
        "home_team": home_team,
        "away_team": away_team,
        "favorite": f"{fav_team} {fav_spread:+g}" if fav_team and fav_spread is not None else None,
        "underdog": f"{dog_team} {dog_spread:+g}" if dog_team and dog_spread is not None else None,
        "fav_team": fav_team,
        "dog_team": dog_team,
        "fav_spread": fav_spread,
        "dog_spread": dog_spread,
        "spread": fav_spread,
        "total": float(over_under) if over_under is not None else None,
        "commence_time": commence,
        "book": provider,
        "event_id": event.get("id"),
    }

def fetch_league(sport_key, league_path):
    events_url = f"https://sports.core.api.espn.com/v2/sports/{league_path}/events"
    data = get_json(events_url)
    items = data.get("items", [])

    games = []
    for it in items:
        ref = it.get("$ref")
        if not ref:
            continue
        try:
            ev = get_json(ref)
            g = parse_event(ev)
            if not g:
                continue
            g["sport_key"] = sport_key
            g["fetched_at"] = datetime.now(timezone.utc).isoformat()
            games.append(g)
        except Exception:
            continue

    return games

def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

def main():
    all_games = []
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    for sport_key, league_path in LEAGUES.items():
        games = []
        try:
            games = fetch_league(sport_key, league_path)
        except Exception as e:
            print(f"⚠️ {sport_key} fetch failed: {e}")

        latest_path = f"{sport_key.split('_')[-1]}_latest.json"
        write_json(latest_path, {"timestamp": ts, "data": games})
        print(f"✅ Wrote {latest_path} ({len(games)} games)")

        all_games.extend(games)

        time.sleep(0.2)

    combined = {
        "timestamp": ts,
        "count": len(all_games),
        "data": all_games,
    }
    write_json(OUT_COMBINED, combined)
    print(f"✅ Wrote {OUT_COMBINED} ({len(all_games)} games)")

if __name__ == "__main__":
    main()
