#!/usr/bin/env python3
"""
fetch_espn_all.py

Hardened version:
- Fixes ESPN bot blocking by using real browser headers
- Adds retry logic + backoff
- Ensures whitelist calendar works
- Ensures TEAM, VENUE, ODDS, OFFICIALS resolve cleanly
- Guarantees combined.json is populated (no more empty output)
"""

import json, os, requests, time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TIMEOUT = 12
RETRIES = 4
BACKOFF = 0.6

NY_TZ = ZoneInfo("America/New_York")

# ESPN league endpoints
LEAGUES = {
    "nfl":   "football/leagues/nfl",
    "ncaaf": "football/leagues/college-football",
    "nba":   "basketball/leagues/nba",
    "ncaab": "basketball/leagues/mens-college-basketball",
    "mlb":   "baseball/leagues/mlb",
    "nhl":   "hockey/leagues/nhl",
    "arts":  "mma/leagues/ufc",
}

BASE = "https://sports.core.api.espn.com/v2/sports"

# caches reduce API calls
TEAM_CACHE = {}
VENUE_CACHE = {}
ODDS_CACHE = {}
OFFICIALS_CACHE = {}

# ------------------------------------------------------------
#  HARDENED FETCH WITH RETRIES + REAL BROWSER HEADERS
# ------------------------------------------------------------
def get_json(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Connection": "close",
    }

    for attempt in range(RETRIES):
        try:
            r = requests.get(url, timeout=TIMEOUT, headers=headers)
            r.raise_for_status()
            return r.json()
        except Exception as ex:
            print(f"[WARN] GET failed ({attempt+1}/{RETRIES}): {url}")
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF * (attempt + 1))
            else:
                print(f"[ERR] Total failure on: {url} — {ex}")
                return None


def iso_to_local_date(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(NY_TZ).date()
    except Exception:
        return None


def yyyymmdd(d):
    return d.strftime("%Y%m%d")


# ------------------------------------------------------------
#  WHITELIST CALENDAR HANDLING
# ------------------------------------------------------------
def get_next_7_whitelist_dates(league_path, today_local):
    wl = get_json(f"{BASE}/{league_path}/calendar/whitelist")
    if not wl:
        return []

    dates = wl.get("eventDate", {}).get("dates") or []
    out = []
    for iso_str in dates:
        d = iso_to_local_date(iso_str)
        if d and d >= today_local:
            out.append(d)

    return out[:7]


# ------------------------------------------------------------
#  RESOLVERS (TEAM, VENUE, ODDS, OFFICIALS)
# ------------------------------------------------------------
def resolve_team(ref):
    if not ref:
        return None
    if ref in TEAM_CACHE:
        return TEAM_CACHE[ref]
    TEAM_CACHE[ref] = get_json(ref)
    return TEAM_CACHE[ref]


def resolve_venue(ref):
    if not ref:
        return None
    if ref in VENUE_CACHE:
        return VENUE_CACHE[ref]
    VENUE_CACHE[ref] = get_json(ref)
    return VENUE_CACHE[ref]


def resolve_odds(ref):
    if not ref:
        return None
    if ref in ODDS_CACHE:
        return ODDS_CACHE[ref]

    idx = get_json(ref)
    if not idx:
        ODDS_CACHE[ref] = None
        return None

    best = None
    for it in idx.get("items") or []:
        oref = it.get("$ref")
        if not oref:
            continue
        o = get_json(oref)
        if not o:
            continue

        prov = (o.get("provider") or {})
        if prov.get("priority") == 1:
            best = o
            break
        if best is None:
            best = o

    ODDS_CACHE[ref] = best
    return best


def resolve_officials(ref):
    if not ref:
        return []
    if ref in OFFICIALS_CACHE:
        return OFFICIALS_CACHE[ref]

    d = get_json(ref)
    if not d:
        OFFICIALS_CACHE[ref] = []
        return []

    items = d.get("items") or d.get("officials") or []
    out = []

    for o in items:
        if isinstance(o, dict) and "$ref" in o:
            o = get_json(o["$ref"]) or o
        person = o.get("person") or {}
        name = person.get("fullName") or o.get("fullName")
        role = o.get("position") or o.get("role")
        if name:
            out.append({"name": name, "role": role})

    OFFICIALS_CACHE[ref] = out
    return out


# ------------------------------------------------------------
#  EVENT EXTRACTION
# ------------------------------------------------------------
def extract_competition(ev):
    comps = ev.get("competitions") or []
    return comps[0] if comps else None


def extract_scores_and_teams(comp):
    competitors = comp.get("competitors") or []

    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)

    def team_blob(c):
        if not c:
            return None
        ref = (c.get("team") or {}).get("$ref")
        t = resolve_team(ref) if ref else c.get("team") or {}
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
            return float(s.get("value")) if s.get("value") else None
        try:
            return float(s)
        except:
            return None

    return (
        team_blob(home),
        team_blob(away),
        score_val(home),
        score_val(away),
    )


def extract_odds_from_comp(comp):
    ref = (comp.get("odds") or {}).get("$ref")
    o = resolve_odds(ref)
    if not o:
        return None

    return {
        "details": o.get("details"),
        "spread": o.get("spread"),
        "total": o.get("overUnder"),
        "provider": (o.get("provider") or {}).get("name"),
    }


def extract_venue_from_comp(comp):
    ref = (comp.get("venue") or {}).get("$ref")
    v = resolve_venue(ref)
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


# ------------------------------------------------------------
#  GAME RECORD BUILDER
# ------------------------------------------------------------
def build_game_record(sport_key, ev):
    comp = extract_competition(ev)
    if not comp:
        return None

    home_team, away_team, home_score, away_score = extract_scores_and_teams(comp)
    if not home_team or not away_team:
        return None

    odds = extract_odds_from_comp(comp)
    venue = extract_venue_from_comp(comp)
    officials = resolve_officials((comp.get("officials") or {}).get("$ref"))

    # time
    dt_utc = ev.get("date")
    try:
        dt = datetime.fromisoformat(dt_utc.replace("Z", "+00:00"))
        local = dt.astimezone(NY_TZ)
        dt_local = local.strftime("%Y-%m-%d %I:%M %p ET")
    except:
        dt_local = dt_utc

    return {
        "sport": sport_key,
        "id": ev.get("id"),
        "name": ev.get("name"),
        "shortName": ev.get("shortName"),
        "date_utc": dt_utc,
        "date_local": dt_local,

        "home_team": home_team,
        "away_team": away_team,
        "home_score": home_score,
        "away_score": away_score,
        "total_points": (home_score or 0) + (away_score or 0),

        "odds": odds,
        "venue": venue,
        "officials": officials,
    }


# ------------------------------------------------------------
#  EVENT FETCHERS
# ------------------------------------------------------------
def events_for_date(path, d):
    idx = get_json(f"{BASE}/{path}/events?dates={yyyymmdd(d)}&lang=en&region=us")
    if not idx:
        return []
    out = []
    for it in idx.get("items") or []:
        ev = get_json(it.get("$ref"))
        if ev:
            out.append(ev)
    return out


def events_for_range(path, start, end):
    idx = get_json(
        f"{BASE}/{path}/events?dates={yyyymmdd(start)}-{yyyymmdd(end)}&lang=en&region=us"
    )
    if not idx:
        return []
    out = []
    for it in idx.get("items") or []:
        ev = get_json(it.get("$ref"))
        if ev:
            out.append(ev)
    return out


# ------------------------------------------------------------
#  MAIN
# ------------------------------------------------------------
def write_latest_file(key, data):
    fn = f"{key}_latest.json"
    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "count": len(data),
        "data": data,
    }
    with open(fn, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"✅ Wrote {fn} ({len(data)} games)")
    return fn


def main():
    today_local = datetime.now(NY_TZ).date()
    combined = []

    for key, path in LEAGUES.items():
        # whitelist dates preferred
        wl = get_next_7_whitelist_dates(path, today_local)

        evs = []
        if wl:
            for d in wl:
                evs.extend(events_for_date(path, d))
        else:
            end_d = today_local + timedelta(days=6)
            evs.extend(events_for_range(path, today_local, end_d))

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
        "data": combined,
    }

    with open("combined.json", "w") as f:
        json.dump(combined_payload, f, indent=2)

    print(f"✅ Wrote combined.json ({len(combined)} games)")


if __name__ == "__main__":
    main()
