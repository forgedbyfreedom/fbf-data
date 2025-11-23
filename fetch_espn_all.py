#!/usr/bin/env python3
"""
fetch_espn_all.py

Unified ESPN odds fetcher.
- Pulls upcoming events + odds from ESPN Core API by league.
- Produces per-league *_latest.json and combined.json.

More robust vs ESPN schema shifts:
- Supports competitors/team being $ref
- Supports odds being inline, dict, list, or $ref
- Falls back across multiple name fields
"""

import json, time, os
from datetime import datetime, timezone
import requests

TIMEOUT = 12
OUT_COMBINED = "combined.json"
DEBUG = os.getenv("DEBUG", "0") == "1"

LEAGUES = {
    "americanfootball_nfl": "football/leagues/nfl",
    "americanfootball_ncaaf": "football/leagues/college-football",
    "basketball_nba": "basketball/leagues/nba",
    "basketball_ncaab": "basketball/leagues/mens-college-basketball",
    "icehockey_nhl": "hockey/leagues/nhl",
    "baseball_mlb": "baseball/leagues/mlb",
    "mma_mixed_martial_arts": "mma/leagues/ufc",
}

session = requests.Session()
session.headers.update({
    "User-Agent": "fbf-data-bot/1.0"
})

def get_json(url):
    r = session.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def safe(o, path, default=None):
    cur = o
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        elif isinstance(cur, list) and isinstance(p, int) and 0 <= p < len(cur):
            cur = cur[p]
        else:
            return default
    return cur

def resolve_ref(obj):
    """
    If obj is dict with '$ref', fetch and return JSON.
    Otherwise return obj unchanged.
    """
    if isinstance(obj, dict) and "$ref" in obj and isinstance(obj["$ref"], str):
        try:
            return get_json(obj["$ref"])
        except Exception:
            return obj
    return obj

def get_team_name(comp):
    """
    Extract a usable team name from a competitor.
    Handles team inline or team $ref.
    """
    team = comp.get("team") or {}
    team = resolve_ref(team)

    for keypath in (
        ["displayName"],
        ["shortDisplayName"],
        ["name"],
        ["nickname"],
    ):
        val = safe(team, keypath, None)
        if val:
            return val

    # Some feeds put name at competitor level
    for k in ("displayName", "shortDisplayName", "name"):
        if comp.get(k):
            return comp.get(k)

    return ""

def normalize_odds_block(comp):
    """
    Return a normalized odds dict (or {}).
    ESPN variants:
      - competitions[0].odds -> list
      - competitions[0].odds -> dict
      - competitions[0].odds -> {"$ref": "..."}
      - competitions[0].odds.items[0].$ref
    """
    odds = comp.get("odds")

    if odds is None:
        return {}

    odds = resolve_ref(odds)

    # If odds is dict with items, use first item
    if isinstance(odds, dict):
        items = odds.get("items")
        if isinstance(items, list) and items:
            first = resolve_ref(items[0])
            if isinstance(first, dict):
                return first
        # Or odds dict itself may contain spread/overUnder
        if any(k in odds for k in ("spread", "overUnder", "favorite", "provider")):
            return odds
        return {}

    # If odds is list, take first
    if isinstance(odds, list) and odds:
        first = resolve_ref(odds[0])
        if isinstance(first, dict):
            return first

    return {}

def parse_event(event):
    comp = safe(event, ["competitions", 0], None)
    if not isinstance(comp, dict):
        return None

    competitors = comp.get("competitors") or []
    if not isinstance(competitors, list) or len(competitors) < 2:
        return None

    # try to find home/away by homeAway
    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)

    # fallback if homeAway missing
    if home is None or away is None:
        home, away = competitors[0], competitors[1]

    home_team = get_team_name(home)
    away_team = get_team_name(away)
    if not home_team or not away_team:
        return None

    commence = event.get("date") or comp.get("date")

    odds = normalize_odds_block(comp)

    spread = odds.get("spread")
    over_under = odds.get("overUnder")
    provider = safe(odds, ["provider", "name"], "ESPN")
    if isinstance(provider, str):
        provider = provider.lower()
    else:
        provider = "espn"

    fav_team = None
    dog_team = None
    fav_spread = None
    dog_spread = None

    if spread is not None:
        try:
            spread_f = float(spread)
            fav_field = odds.get("favorite")

            # favorite might be abbrev; only trust if matches
            if isinstance(fav_field, str) and fav_field in (home_team, away_team):
                fav_team = fav_field
                dog_team = away_team if fav_team == home_team else home_team
                fav_spread = spread_f if fav_team == home_team else -spread_f
            else:
                # fallback rule: negative spread => home favored
                fav_team = home_team if spread_f < 0 else away_team
                dog_team = away_team if fav_team == home_team else home_team
                fav_spread = spread_f if fav_team == home_team else -spread_f

            dog_spread = -fav_spread
        except Exception:
            pass

    matchup = f"{away_team}@{home_team}"

    total_f = None
    if over_under is not None:
        try:
            total_f = float(over_under)
        except Exception:
            total_f = None

    return {
        "sport_key": None,  # filled at caller
        "matchup": matchup,
        "home_team": home_team,
        "away_team": away_team,

        # Display strings
        "favorite": f"{fav_team} {fav_spread:+g}" if fav_team and fav_spread is not None else None,
        "underdog": f"{dog_team} {dog_spread:+g}" if dog_team and dog_spread is not None else None,

        # Raw fields
        "fav_team": fav_team,
        "dog_team": dog_team,
        "fav_spread": fav_spread,
        "dog_spread": dog_spread,
        "spread": fav_spread,
        "total": total_f,

        "commence_time": commence,
        "book": provider,
        "event_id": event.get("id"),
    }

def fetch_league(sport_key, league_path):
    events_url = f"https://sports.core.api.espn.com/v2/sports/{league_path}/events"
    data = get_json(events_url)
    items = data.get("items", []) or []

    games = []
    for it in items:
        ref = it.get("$ref") if isinstance(it, dict) else None
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
        except Exception as e:
            if DEBUG:
                print(f"  skip event ref {ref}: {e}")
            continue

    if DEBUG:
        print(f"[debug] {sport_key}: parsed {len(games)} games from {len(items)} items")
    return games

def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

def main():
    all_games = []
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    for sport_key, league_path in LEAGUES.items():
        try:
            games = fetch_league(sport_key, league_path)
        except Exception as e:
            print(f"⚠️ {sport_key} fetch failed: {e}")
            games = []

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
