#!/usr/bin/env python3
"""
fetch_espn_all.py  (NEXT 7 DAYS VERSION)

Unified ESPN odds fetcher.
- Pulls events + odds from ESPN Core API by league.
- Uses ESPN events "dates" range so it's never empty.
- Resolves team $ref so home/away names always exist.
- Produces per-league *_latest.json and combined.json.

Date window:
  TODAY (UTC) through TODAY+7 days (inclusive)
  Includes games earlier today (Option 2)

Requirements:
  pip install requests
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta
import requests

TIMEOUT = 15
OUT_COMBINED = "combined.json"

LEAGUES = {
    "americanfootball_nfl":   "football/leagues/nfl",
    "americanfootball_ncaaf": "football/leagues/college-football",
    "basketball_nba":         "basketball/leagues/nba",
    "basketball_ncaab":       "basketball/leagues/mens-college-basketball",
    "icehockey_nhl":          "hockey/leagues/nhl",
    "baseball_mlb":           "baseball/leagues/mlb",
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
        elif isinstance(cur, list) and isinstance(p, int) and 0 <= p < len(cur):
            cur = cur[p]
        else:
            return default
    return cur

def normalize_team_name(name):
    return (name or "").strip()

def fetch_team_name(team_obj):
    """
    Team is often just: {"$ref": ".../teams/34"}
    So we follow the ref if displayName missing.
    """
    if not team_obj:
        return ""
    # if expanded already
    dn = team_obj.get("displayName") or team_obj.get("name")
    if dn:
        return normalize_team_name(dn)

    ref = team_obj.get("$ref")
    if ref:
        try:
            tdata = get_json(ref.replace("http://", "https://"))
            dn2 = tdata.get("displayName") or tdata.get("name")
            return normalize_team_name(dn2)
        except Exception:
            return ""
    return ""

def fetch_best_odds(comp):
    """
    competitions[0].odds is a $ref to an odds collection.
    That collection returns items[$ref] for providers.
    We take the first provider item.
    """
    odds_ref = safe(comp, ["odds", "$ref"], None)
    if not odds_ref:
        return None

    try:
        odds_index = get_json(odds_ref.replace("http://", "https://"))
        items = odds_index.get("items") or []
        if not items:
            return None

        first_ref = items[0].get("$ref")
        if not first_ref:
            return None

        od = get_json(first_ref.replace("http://", "https://"))

        provider = safe(od, ["provider", "name"], "ESPN").lower()
        over_under = od.get("overUnder")
        spread_val = od.get("spread")

        # favorite side detection usually in awayTeamOdds/homeTeamOdds
        away_odds = od.get("awayTeamOdds") or {}
        home_odds = od.get("homeTeamOdds") or {}
        away_fav = away_odds.get("favorite") is True
        home_fav = home_odds.get("favorite") is True

        return {
            "provider": provider,
            "overUnder": float(over_under) if over_under is not None else None,
            "spread": float(spread_val) if spread_val is not None else None,
            "away_favorite": away_fav,
            "home_favorite": home_fav,
            "details": od.get("details"),
        }
    except Exception:
        return None

def parse_event(event, sport_key):
    comp = safe(event, ["competitions", 0], {})
    competitors = comp.get("competitors", []) or []
    if len(competitors) < 2:
        return None

    # Identify home/away competitors
    home_c = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
    away_c = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

    home_team = fetch_team_name(home_c.get("team") or {})
    away_team = fetch_team_name(away_c.get("team") or {})
    if not home_team or not away_team:
        return None

    commence = event.get("date") or comp.get("date")

    odds = fetch_best_odds(comp) or {}
    spread = odds.get("spread")
    total = odds.get("overUnder")
    provider = odds.get("provider", "espn")

    # Determine favorite/dog based on favorite flags if possible
    fav_team = dog_team = None
    fav_spread = dog_spread = None

    if spread is not None:
        try:
            spread = float(spread)

            if odds.get("home_favorite"):
                fav_team = home_team
                dog_team = away_team
                # ESPN odds spread usually positive number for favorite side shown in details.
                fav_spread = -abs(spread)
                dog_spread = abs(spread)
            elif odds.get("away_favorite"):
                fav_team = away_team
                dog_team = home_team
                fav_spread = -abs(spread)
                dog_spread = abs(spread)
            else:
                # fallback: negative -> home favored (rare with this feed)
                fav_team = home_team if spread < 0 else away_team
                dog_team = away_team if fav_team == home_team else home_team
                fav_spread = spread if fav_team == home_team else -spread
                dog_spread = -fav_spread
        except Exception:
            pass

    matchup = f"{away_team}@{home_team}"

    return {
        "sport_key": sport_key,
        "matchup": matchup,
        "home_team": home_team,
        "away_team": away_team,
        "commence_time": commence,
        "favorite": f"{fav_team} {fav_spread:+g}" if fav_team and fav_spread is not None else None,
        "underdog": f"{dog_team} {dog_spread:+g}" if dog_team and dog_spread is not None else None,
        "fav_team": fav_team,
        "dog_team": dog_team,
        "fav_spread": fav_spread,
        "dog_spread": dog_spread,
        "spread": fav_spread,
        "total": total,
        "book": provider,
        "event_id": event.get("id"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

def date_range_yyyymmdd(days_ahead=7):
    """
    returns ("YYYYMMDD", "YYYYMMDD") in UTC inclusive
    """
    start = datetime.now(timezone.utc).date()
    end = start + timedelta(days=days_ahead)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

def fetch_league(sport_key, league_path):
    start_d, end_d = date_range_yyyymmdd(7)

    events_url = (
        f"https://sports.core.api.espn.com/v2/sports/{league_path}/events"
        f"?dates={start_d}-{end_d}&lang=en&region=us"
    )

    data = get_json(events_url)
    items = data.get("items", []) or []

    games = []
    for it in items:
        ref = it.get("$ref")
        if not ref:
            continue
        try:
            ev = get_json(ref.replace("http://", "https://"))
            g = parse_event(ev, sport_key)
            if g:
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
        try:
            games = fetch_league(sport_key, league_path)
        except Exception as e:
            print(f"⚠️ {sport_key} fetch failed: {e}")
            games = []

        # output like nfl_latest.json, nba_latest.json, etc.
        short = sport_key.split("_")[-1]
        latest_path = f"{short}_latest.json"

        write_json(latest_path, {"timestamp": ts, "data": games})
        print(f"✅ Wrote {latest_path} ({len(games)} games)")

        all_games.extend(games)
        time.sleep(0.25)

    combined = {
        "timestamp": ts,
        "count": len(all_games),
        "data": all_games,
    }
    write_json(OUT_COMBINED, combined)
    print(f"✅ Wrote {OUT_COMBINED} ({len(all_games)} games)")

if __name__ == "__main__":
    main()
