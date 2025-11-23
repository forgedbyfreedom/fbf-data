#!/usr/bin/env python3
"""
fetch_espn_all.py  (2025 ESPN Core format)

Unified ESPN odds fetcher.
- Pulls upcoming events + odds from ESPN Core API by league.
- Resolves team $ref objects (ESPN 2025 change).
- Resolves odds $ref (item list).
- Produces per-league *_latest.json and combined.json.

Safe vs missing fields: skips gracefully.
"""

import json
import time
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

# nicer filenames (prevents "arts_latest.json")
LATEST_FILES = {
    "americanfootball_nfl": "nfl_latest.json",
    "americanfootball_ncaaf": "ncaaf_latest.json",
    "basketball_nba": "nba_latest.json",
    "basketball_ncaab": "ncaab_latest.json",
    "icehockey_nhl": "nhl_latest.json",
    "baseball_mlb": "mlb_latest.json",
    "mma_mixed_martial_arts": "ufc_latest.json",
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
        elif isinstance(cur, list) and isinstance(p, int) and 0 <= p < len(cur):
            cur = cur[p]
        else:
            return default
    return cur

def resolve_ref(obj):
    """
    ESPN Core frequently returns:
      {"$ref": "http://sports.core.api.espn.com/v2/..."}
    If so, fetch and return the referenced JSON.
    Otherwise return obj unchanged.
    """
    if isinstance(obj, dict):
        ref = obj.get("$ref")
        if ref and isinstance(ref, str):
            try:
                return get_json(ref)
            except Exception:
                return None
    return obj

def extract_team_name(team_stub):
    """
    team_stub is usually {"$ref": ".../teams/34?..."}
    We resolve it and read displayName.
    """
    team_obj = resolve_ref(team_stub) or {}
    name = team_obj.get("displayName") or team_obj.get("shortDisplayName") or team_obj.get("name")
    return name or ""

def extract_competitors(comp):
    """
    Return (home_name, away_name) by resolving team $refs.
    """
    competitors = comp.get("competitors") or []
    if len(competitors) < 2:
        return None, None

    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if not home or not away:
        # fallback to order
        home, away = competitors[0], competitors[1]

    home_name = extract_team_name(home.get("team") or {})
    away_name = extract_team_name(away.get("team") or {})

    if not home_name or not away_name:
        return None, None

    return home_name, away_name

def fetch_best_odds_from_comp(comp):
    """
    comp["odds"] is a $ref to an odds collection like:
      {"count":2,"items":[{spread,overUnder,provider,awayTeamOdds{favorite},homeTeamOdds{favorite}}]}
    We resolve, take first item (priority order already sorted by ESPN),
    and normalize favorite/dog spreads.
    """
    odds_coll_stub = comp.get("odds")
    if not odds_coll_stub:
        return None

    odds_coll = resolve_ref(odds_coll_stub)
    if not odds_coll:
        return None

    items = odds_coll.get("items") or []
    if not items:
        return None

    odds_item = items[0]  # ESPN priority=1 is first in practice
    spread_abs = odds_item.get("spread")
    total = odds_item.get("overUnder")
    provider = safe(odds_item, ["provider", "name"], "ESPN").lower()

    away_fav = safe(odds_item, ["awayTeamOdds", "favorite"], None)
    home_fav = safe(odds_item, ["homeTeamOdds", "favorite"], None)

    try:
        spread_abs = float(spread_abs) if spread_abs is not None else None
    except Exception:
        spread_abs = None

    try:
        total = float(total) if total is not None else None
    except Exception:
        total = None

    return {
        "provider": provider,
        "spread_abs": spread_abs,
        "total": total,
        "away_fav": bool(away_fav) if away_fav is not None else None,
        "home_fav": bool(home_fav) if home_fav is not None else None,
        "details": odds_item.get("details"),
    }

def parse_event(event):
    comp_stub = safe(event, ["competitions", 0], None)
    if not comp_stub:
        return None

    comp = resolve_ref(comp_stub) or comp_stub or {}

    home_team, away_team = extract_competitors(comp)
    if not home_team or not away_team:
        return None

    commence = event.get("date") or comp.get("date")
    event_id = event.get("id")

    odds = fetch_best_odds_from_comp(comp) or {}
    spread_abs = odds.get("spread_abs")
    total = odds.get("total")
    provider = odds.get("provider", "espn")

    fav_team = dog_team = None
    fav_spread = dog_spread = None

    if spread_abs is not None:
        # Determine favorite based on away/home favorite flags
        if odds.get("away_fav") is True:
            fav_team = away_team
            dog_team = home_team
            fav_spread = -abs(spread_abs)
            dog_spread = abs(spread_abs)
        elif odds.get("home_fav") is True:
            fav_team = home_team
            dog_team = away_team
            fav_spread = -abs(spread_abs)
            dog_spread = abs(spread_abs)
        else:
            # fallback: if no fav flags, assume negative to home doesn't exist here,
            # so just mark spread from details if possible
            fav_spread = -abs(spread_abs)

    matchup = f"{away_team}@{home_team}"

    return {
        "sport_key": None,  # filled by caller
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
        "total": total,
        "commence_time": commence,
        "book": provider,
        "event_id": event_id,
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

        latest_path = LATEST_FILES.get(sport_key, f"{sport_key.split('_')[-1]}_latest.json")
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
