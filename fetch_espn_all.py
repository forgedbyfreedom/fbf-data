#!/usr/bin/env python3
"""
fetch_espn_all.py

Unified ESPN odds fetcher (NEXT 7 DAYS).

Fixes:
- ESPN /events root often defaults to a different season unless dates are supplied.
- This version pulls the ESPN calendar, finds upcoming dates, and queries events
  for the next 7 days.
- Resolves $ref for teams and odds safely.

Outputs:
  *_latest.json per league (nfl_latest.json, nba_latest.json, etc.)
  combined.json

Requirements:
  pip install requests
"""

import json, time
from datetime import datetime, timezone, timedelta
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
        elif isinstance(cur, list) and isinstance(p, int) and 0 <= p < len(cur):
            cur = cur[p]
        else:
            return default
    return cur

def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

def yyyymmdd(d: datetime):
    return d.strftime("%Y%m%d")

def get_next_7_calendar_dates(sport_key, league_path):
    """
    ESPN calendar endpoint:
      /calendar

    We take dates from now (UTC) through +6 days.
    ESPN wants YYYYMMDD as ints in the calendar list.
    """
    cal_url = f"https://sports.core.api.espn.com/v2/sports/{league_path}/calendar"
    cal = get_json(cal_url)

    dates = cal.get("entries") or cal.get("items") or []
    # ESPN gives "date": "20251122" etc. sometimes nested
    parsed = []
    for e in dates:
        d = e.get("date") or safe(e, ["value"], None) or safe(e, ["date"], None)
        if d:
            try:
                parsed.append(str(d))
            except:
                pass

    # If calendar doesn't return usable entries, fall back to plain 7-day range
    now = datetime.now(timezone.utc)
    target = {yyyymmdd(now + timedelta(days=i)) for i in range(7)}

    if parsed:
        keep = [d for d in parsed if d in target]
        if keep:
            return keep

    return sorted(list(target))

def fetch_events_index_for_dates(league_path, date_list):
    """
    ESPN events endpoint supports:
      /events?dates=YYYYMMDD-YYYYMMDD
    We'll use a single contiguous range from min to max.
    """
    if not date_list:
        return []

    date_list = sorted(date_list)
    start = date_list[0]
    end = date_list[-1]

    events_url = f"https://sports.core.api.espn.com/v2/sports/{league_path}/events?dates={start}-{end}"
    data = get_json(events_url)
    return data.get("items", []) or []

def resolve_team_name(team_obj):
    """
    team may be a dict with $ref only.
    """
    if not team_obj:
        return ""
    if isinstance(team_obj, dict):
        if "displayName" in team_obj:
            return team_obj.get("displayName") or ""
        ref = team_obj.get("$ref")
        if ref:
            try:
                t = get_json(ref)
                return t.get("displayName") or t.get("name") or ""
            except:
                return ""
    return ""

def resolve_odds(comp):
    """
    competitions[0].odds is usually a $ref to odds collection.
    We follow it, take first item (priority provider).
    Returns a normalized dict.
    """
    odds_ref = safe(comp, ["odds", "$ref"], None) or comp.get("odds", {}).get("$ref")
    if not odds_ref:
        return {}

    try:
        odds_list = get_json(odds_ref)
        items = odds_list.get("items") or []
        if not items:
            return {}
        first_ref = items[0].get("$ref")
        if not first_ref:
            return {}
        o = get_json(first_ref)

        provider = safe(o, ["provider", "name"], "ESPN").lower()
        spread = o.get("spread")
        over_under = o.get("overUnder")
        details = o.get("details")  # e.g. "BUF -4.5"

        home_team_odds = o.get("homeTeamOdds") or {}
        away_team_odds = o.get("awayTeamOdds") or {}

        # Determine favorite by boolean flag if present
        fav_is_away = bool(away_team_odds.get("favorite"))
        fav_is_home = bool(home_team_odds.get("favorite"))

        return {
            "provider": provider,
            "spread": float(spread) if spread is not None else None,
            "total": float(over_under) if over_under is not None else None,
            "details": details,
            "fav_is_home": fav_is_home,
            "fav_is_away": fav_is_away,
        }
    except Exception:
        return {}

def parse_event(event):
    comp = safe(event, ["competitions", 0], {})
    competitors = comp.get("competitors", []) or []
    if len(competitors) < 2:
        return None

    home_c = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
    away_c = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

    home_team = resolve_team_name(home_c.get("team"))
    away_team = resolve_team_name(away_c.get("team"))

    if not home_team or not away_team:
        return None

    commence = event.get("date") or safe(comp, ["date"], None)
    matchup = f"{away_team}@{home_team}"

    odds = resolve_odds(comp)
    spread = odds.get("spread")
    total = odds.get("total")
    provider = odds.get("provider") or "espn"

    fav_team = dog_team = None
    fav_spread = dog_spread = None

    if spread is not None:
        try:
            # ESPN spread is positive magnitude, favorite flag tells side
            if odds.get("fav_is_home"):
                fav_team = home_team
                dog_team = away_team
                fav_spread = -abs(float(spread))
                dog_spread = abs(float(spread))
            elif odds.get("fav_is_away"):
                fav_team = away_team
                dog_team = home_team
                fav_spread = -abs(float(spread))
                dog_spread = abs(float(spread))
            else:
                # fallback: negative means home favored (rare in this feed)
                fav_team = home_team if float(spread) < 0 else away_team
                dog_team = away_team if fav_team == home_team else home_team
                fav_spread = float(spread) if fav_team == home_team else -float(spread)
                dog_spread = -fav_spread
        except Exception:
            pass

    return {
        "sport_key": None,  # set by caller
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
        "event_id": event.get("id"),
    }

def fetch_league(sport_key, league_path):
    # 1) Get next 7 day date window from ESPN calendar
    date_list = get_next_7_calendar_dates(sport_key, league_path)

    # 2) Get events index constrained to that window
    items = fetch_events_index_for_dates(league_path, date_list)

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
