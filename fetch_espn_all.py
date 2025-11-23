#!/usr/bin/env python3
"""
fetch_espn_all.py  (calendar/whitelist + next 7 on-days)

Fixes:
- combined.json empty because we were querying wrong date window / wrong season params.
- Now uses ESPN calendar whitelist when available (NFL, NCAAF, etc.)
- Falls back to next 7 days range if whitelist not offered.
- Resolves team $ref so displayName/abbr/logos are real.
- Pulls odds + officials + venue.

Outputs:
  nfl_latest.json
  ncaaf_latest.json
  nba_latest.json
  ncaab_latest.json
  ncaaw_latest.json  (optional)
  nhl_latest.json
  mlb_latest.json
  arts_latest.json   (ufc)
  combined.json
"""

import json, os, requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict

TIMEOUT = 12

LEAGUES = {
    "nfl":   "football/leagues/nfl",
    "ncaaf": "football/leagues/college-football",
    "nba":   "basketball/leagues/nba",
    "ncaab": "basketball/leagues/mens-college-basketball",
    # "ncaaw": "basketball/leagues/womens-college-basketball",  # uncomment if you want it live
    "mlb":   "baseball/leagues/mlb",
    "nhl":   "hockey/leagues/nhl",
    "arts":  "mma/leagues/ufc",
}

BASE = "https://sports.core.api.espn.com/v2/sports"

NY_TZ = ZoneInfo("America/New_York")

TEAM_CACHE = {}
VENUE_CACHE = {}
ODDS_CACHE = {}
OFFICIALS_CACHE = {}

def get_json(url):
    try:
        r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "fbf-data-bot/1.0"})
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def iso_to_local_date(iso_str):
    """ESPN whitelist dates are ISO Zulu. Convert to NY local date."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(NY_TZ).date()
    except Exception:
        return None

def yyyymmdd(d):
    return d.strftime("%Y%m%d")

def get_next_7_whitelist_dates(league_path, today_local):
    """
    Try to use /calendar/whitelist.
    Returns list[date] (NY local) or [] if not supported.
    """
    whitelist_url = f"{BASE}/{league_path}/calendar/whitelist"
    wl = get_json(whitelist_url)
    if not wl:
        return []

    dates = wl.get("eventDate", {}).get("dates") or []
    out = []
    for iso_str in dates:
        d = iso_to_local_date(iso_str)
        if not d:
            continue
        if d >= today_local and d not in out:
            out.append(d)

    return out[:7]

def resolve_team(team_ref):
    if not team_ref:
        return None
    if team_ref in TEAM_CACHE:
        return TEAM_CACHE[team_ref]
    t = get_json(team_ref)
    TEAM_CACHE[team_ref] = t
    return t

def resolve_venue(venue_ref):
    if not venue_ref:
        return None
    if venue_ref in VENUE_CACHE:
        return VENUE_CACHE[venue_ref]
    v = get_json(venue_ref)
    VENUE_CACHE[venue_ref] = v
    return v

def resolve_odds(odds_ref):
    if not odds_ref:
        return None
    if odds_ref in ODDS_CACHE:
        return ODDS_CACHE[odds_ref]

    idx = get_json(odds_ref)
    if not idx:
        ODDS_CACHE[odds_ref] = None
        return None

    # odds endpoint returns {"items":[{"$ref":...}, ...]}
    items = idx.get("items") or []
    best = None
    for it in items:
        ref = it.get("$ref")
        if not ref:
            continue
        o = get_json(ref)
        if o:
            # prefer priority 1 provider if present
            prov = (o.get("provider") or {})
            if prov.get("priority") == 1:
                best = o
                break
            if best is None:
                best = o

    ODDS_CACHE[odds_ref] = best
    return best

def resolve_officials(off_ref):
    if not off_ref:
        return []
    if off_ref in OFFICIALS_CACHE:
        return OFFICIALS_CACHE[off_ref]
    data = get_json(off_ref)
    if not data:
        OFFICIALS_CACHE[off_ref] = []
        return []
    # officials as list in "items" OR direct "officials"
    officials = data.get("items") or data.get("officials") or []
    out = []
    for o in officials:
        if isinstance(o, dict) and "$ref" in o:
            o = get_json(o["$ref"]) or o
        person = o.get("person") or {}
        name = person.get("fullName") or o.get("fullName") or o.get("displayName")
        role = o.get("position") or o.get("role") or "Official"
        if name:
            out.append({"name": name, "role": role})
    OFFICIALS_CACHE[off_ref] = out
    return out

def extract_competition(ev):
    comps = ev.get("competitions") or []
    return comps[0] if comps else None

def extract_scores_and_teams(comp):
    competitors = comp.get("competitors") or []
    home = away = None
    for c in competitors:
        if c.get("homeAway") == "home":
            home = c
        elif c.get("homeAway") == "away":
            away = c

    def team_blob(c):
        if not c:
            return None
        tref = (c.get("team") or {}).get("$ref")
        t = resolve_team(tref) if tref else (c.get("team") or {})
        if not t:
            return None
        return {
            "id": t.get("id"),
            "name": t.get("displayName") or t.get("name"),
            "abbr": t.get("abbreviation"),
            "slug": t.get("slug"),
            "logo": (t.get("logos") or [{}])[0].get("href"),
        }

    def score_val(c):
        if not c:
            return None
        s = c.get("score")
        if isinstance(s, dict) and "$ref" in s:
            s = get_json(s["$ref"]) or {}
            v = s.get("value")
            return float(v) if v is not None else None
        try:
            return float(s)
        except Exception:
            return None

    home_team = team_blob(home)
    away_team = team_blob(away)
    home_score = score_val(home)
    away_score = score_val(away)

    return home_team, away_team, home_score, away_score

def extract_odds(comp):
    odds_ref = (comp.get("odds") or {}).get("$ref")
    o = resolve_odds(odds_ref)
    if not o:
        return None

    spread = o.get("spread")
    total = o.get("overUnder")
    details = o.get("details")

    # Determine favorite by flag if present
    away_odds = o.get("awayTeamOdds") or {}
    home_odds = o.get("homeTeamOdds") or {}
    fav_side = None
    if away_odds.get("favorite") is True:
        fav_side = "away"
    elif home_odds.get("favorite") is True:
        fav_side = "home"

    return {
        "details": details,
        "spread": spread,
        "total": total,
        "fav_side": fav_side,
        "provider": (o.get("provider") or {}).get("name"),
    }

def extract_venue(comp):
    vref = (comp.get("venue") or {}).get("$ref")
    v = resolve_venue(vref)
    if not v:
        return None
    addr = v.get("address") or {}
    return {
        "name": v.get("fullName"),
        "city": addr.get("city"),
        "state": addr.get("state"),
        "indoor": v.get("indoor"),
        "grass": v.get("grass"),
    }

def events_for_date(league_path, d):
    """
    Query ESPN events for a single day using dates=YYYYMMDD.
    """
    url = f"{BASE}/{league_path}/events?dates={yyyymmdd(d)}&lang=en&region=us"
    idx = get_json(url)
    if not idx:
        return []
    items = idx.get("items") or []
    evs = []
    for it in items:
        ref = it.get("$ref")
        if not ref:
            continue
        ev = get_json(ref)
        if ev:
            evs.append(ev)
    return evs

def events_for_range(league_path, start_d, end_d):
    """
    Fallback: dates=YYYYMMDD-YYYYMMDD range.
    """
    url = f"{BASE}/{league_path}/events?dates={yyyymmdd(start_d)}-{yyyymmdd(end_d)}&lang=en&region=us"
    idx = get_json(url)
    if not idx:
        return []
    items = idx.get("items") or []
    evs = []
    for it in items:
        ref = it.get("$ref")
        if not ref:
            continue
        ev = get_json(ref)
        if ev:
            evs.append(ev)
    return evs

def build_game_record(sport_key, ev):
    comp = extract_competition(ev)
    if not comp:
        return None

    home_team, away_team, home_score, away_score = extract_scores_and_teams(comp)
    if not home_team or not away_team:
        return None

    odds = extract_odds(comp)
    venue = extract_venue(comp)

    off_ref = (comp.get("officials") or {}).get("$ref")
    officials = resolve_officials(off_ref)

    status_blob = comp.get("status") or ev.get("status") or {}
    status_type = (status_blob.get("type") or {})
    completed = bool(status_type.get("completed"))
    state = status_type.get("state") or status_type.get("description")

    game_dt = ev.get("date")
    try:
        dt_utc = datetime.fromisoformat(game_dt.replace("Z","+00:00"))
        dt_local = dt_utc.astimezone(NY_TZ)
        game_time_local = dt_local.strftime("%Y-%m-%d %I:%M %p ET")
    except Exception:
        game_time_local = game_dt

    rec = {
        "sport": sport_key,
        "id": ev.get("id"),
        "name": ev.get("name"),
        "shortName": ev.get("shortName"),
        "date_utc": game_dt,
        "date_local": game_time_local,
        "completed": completed,
        "state": state,

        "home_team": home_team,
        "away_team": away_team,
        "home_score": home_score,
        "away_score": away_score,
        "total_points": (home_score or 0) + (away_score or 0),

        "odds": odds,
        "venue": venue,
        "officials": officials,
    }
    return rec

def write_latest_file(key, data):
    fn = f"{key}_latest.json"
    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "count": len(data),
        "data": data
    }
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"✅ Wrote {fn} ({len(data)} games)")
    return fn

def main():
    today_local = datetime.now(NY_TZ).date()

    combined = []
    for key, league_path in LEAGUES.items():
        # 1) try whitelist
        wl_dates = get_next_7_whitelist_dates(league_path, today_local)

        evs = []
        if wl_dates:
            for d in wl_dates:
                evs.extend(events_for_date(league_path, d))
        else:
            # 2) fallback to range
            end_d = today_local + timedelta(days=6)
            evs = events_for_range(league_path, today_local, end_d)

        games = []
        for ev in evs:
            rec = build_game_record(key, ev)
            if rec:
                games.append(rec)

        games.sort(key=lambda g: g["date_utc"] or "")
        write_latest_file(key, games)
        combined.extend(games)

    combined.sort(key=lambda g: g["date_utc"] or "")
    combined_payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "count": len(combined),
        "data": combined
    }
    with open("combined.json", "w", encoding="utf-8") as f:
        json.dump(combined_payload, f, indent=2, ensure_ascii=False)
    print(f"✅ Wrote combined.json ({len(combined)} games)")

if __name__ == "__main__":
    main()
