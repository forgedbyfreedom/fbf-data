#!/usr/bin/env python3
"""
fetch_espn_all.py

Hardened ESPN data fetcher:
- Real browser headers to avoid bot blocking
- Retry logic + backoff
- Whitelist calendar for upcoming dates
- Resolves TEAM, VENUE, ODDS, OFFICIALS
- Special UFC handling: each bout = separate game record
- Supports: NFL, NCAAF, NBA, NCAAB, NCAAW, MLB, NHL, UFC
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
    "ncaaw": "basketball/leagues/womens-college-basketball",
    "mlb":   "baseball/leagues/mlb",
    "nhl":   "hockey/leagues/nhl",
    "ufc":   "mma/leagues/ufc",
}

# Sports where each event has multiple competitions (bouts/fights)
MULTI_COMP_SPORTS = {"ufc"}

BASE = "https://sports.core.api.espn.com/v2/sports"

# caches reduce API calls
TEAM_CACHE = {}
VENUE_CACHE = {}
ODDS_CACHE = {}
OFFICIALS_CACHE = {}
ATHLETE_CACHE = {}

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
            if attempt < RETRIES - 1:
                time.sleep(BACKOFF * (attempt + 1))
            else:
                print(f"[ERR] GET failed: {url} -- {ex}")
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
#  RESOLVERS (TEAM, VENUE, ODDS, OFFICIALS, ATHLETE)
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


def resolve_athlete(ref):
    """Resolve an athlete $ref (used by UFC/MMA)."""
    if not ref:
        return None
    if ref in ATHLETE_CACHE:
        return ATHLETE_CACHE[ref]
    ATHLETE_CACHE[ref] = get_json(ref)
    return ATHLETE_CACHE[ref]


# ------------------------------------------------------------
#  EVENT EXTRACTION - TEAM SPORTS
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


# ------------------------------------------------------------
#  EVENT EXTRACTION - UFC/MMA (athlete-based)
# ------------------------------------------------------------
def extract_ufc_fighters(comp):
    """Extract two fighters from a UFC bout competition."""
    competitors = comp.get("competitors") or []
    if len(competitors) < 2:
        return None, None

    fighters = []
    for c in competitors:
        # UFC uses athlete refs, not team refs
        athlete_ref = (c.get("athlete") or {}).get("$ref")
        athlete = resolve_athlete(athlete_ref) if athlete_ref else None

        if athlete:
            name = athlete.get("displayName") or athlete.get("fullName") or "Unknown"
            fighter = {
                "id": str(athlete.get("id", "")),
                "name": name,
                "abbr": name.split()[-1].upper()[:4] if name else "UNK",
                "slug": athlete.get("slug", ""),
                "logo": (athlete.get("headshot") or {}).get("href") or "",
            }
        else:
            fighter = {
                "id": str(c.get("id", "")),
                "name": "Unknown Fighter",
                "abbr": "UNK",
                "slug": "",
                "logo": "",
            }
        fighters.append((fighter, c.get("winner", False)))

    # Fighter 1 = "home" (red corner), Fighter 2 = "away" (blue corner)
    return fighters[0][0], fighters[1][0]


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
#  GAME RECORD BUILDERS
# ------------------------------------------------------------
def format_local_time(dt_utc_str):
    try:
        dt = datetime.fromisoformat(dt_utc_str.replace("Z", "+00:00"))
        local = dt.astimezone(NY_TZ)
        return local.strftime("%Y-%m-%d %I:%M %p ET")
    except:
        return dt_utc_str


def build_game_record(sport_key, ev):
    """Build a single game record for team sports."""
    comp = extract_competition(ev)
    if not comp:
        return None

    home_team, away_team, home_score, away_score = extract_scores_and_teams(comp)
    if not home_team or not away_team:
        return None

    odds = extract_odds_from_comp(comp)
    venue = extract_venue_from_comp(comp)
    officials = resolve_officials((comp.get("officials") or {}).get("$ref"))

    dt_utc = ev.get("date")

    return {
        "sport": sport_key,
        "id": ev.get("id"),
        "name": ev.get("name"),
        "shortName": ev.get("shortName"),
        "date_utc": dt_utc,
        "date_local": format_local_time(dt_utc),
        "home_team": home_team,
        "away_team": away_team,
        "home_score": home_score,
        "away_score": away_score,
        "total_points": (home_score or 0) + (away_score or 0),
        "odds": odds,
        "venue": venue,
        "officials": officials,
    }


def build_ufc_records(ev):
    """Build one record per bout for UFC events."""
    comps = ev.get("competitions") or []
    if not comps:
        return []

    dt_utc = ev.get("date")
    event_name = ev.get("name") or "UFC Event"
    records = []

    # Get venue from the first competition (shared across all bouts)
    venue = extract_venue_from_comp(comps[0])

    for i, comp in enumerate(comps):
        fighter1, fighter2 = extract_ufc_fighters(comp)
        if not fighter1 or not fighter2:
            continue

        odds = extract_odds_from_comp(comp)

        # Use bout date if available, else event date
        bout_date = comp.get("date") or dt_utc
        bout_name = comp.get("description") or f"{fighter1['name']} vs {fighter2['name']}"

        # Card segment (main card, prelims, early prelims)
        segment = comp.get("cardSegment") or ""
        match_num = comp.get("matchNumber")

        # Check winner status
        status = comp.get("status") or {}
        if isinstance(status, dict) and "$ref" in status:
            status_data = get_json(status["$ref"]) or {}
        else:
            status_data = status
        status_name = status_data.get("type", {}).get("name") if isinstance(status_data, dict) else None

        # Scores for UFC: winner=True on competitor
        competitors = comp.get("competitors") or []
        home_score = None
        away_score = None
        if status_name in ("STATUS_FINAL", "STATUS_COMPLETED"):
            home_score = 1 if (competitors[0].get("winner") if len(competitors) > 0 else False) else 0
            away_score = 1 if (competitors[1].get("winner") if len(competitors) > 1 else False) else 0

        records.append({
            "sport": "ufc",
            "id": f"{ev.get('id')}_{comp.get('id', i)}",
            "name": bout_name,
            "shortName": f"{fighter1['abbr']} vs {fighter2['abbr']}",
            "date_utc": bout_date,
            "date_local": format_local_time(bout_date),
            "event_name": event_name,
            "card_segment": segment,
            "match_number": match_num,
            "home_team": fighter1,   # red corner
            "away_team": fighter2,   # blue corner
            "home_score": home_score,
            "away_score": away_score,
            "total_points": 0,
            "odds": odds,
            "venue": venue,
            "officials": [],
        })

    return records


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
    print(f"  [{key}] {len(data)} games -> {fn}")
    return fn


def main():
    today_local = datetime.now(NY_TZ).date()
    combined = []

    for key, path in LEAGUES.items():
        print(f"[fetch] {key}...")

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
        if key in MULTI_COMP_SPORTS:
            # UFC: each event has multiple bouts
            for ev in evs:
                games.extend(build_ufc_records(ev))
        else:
            # Team sports: one game per event
            for ev in evs:
                rec = build_game_record(key, ev)
                if rec:
                    games.append(rec)

        games.sort(key=lambda g: g.get("date_utc") or "")
        write_latest_file(key, games)

        combined.extend(games)

    combined.sort(key=lambda g: g.get("date_utc") or "")
    combined_payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "count": len(combined),
        "data": combined,
    }

    with open("combined.json", "w") as f:
        json.dump(combined_payload, f, indent=2)

    # Summary
    sport_counts = {}
    for g in combined:
        s = g.get("sport", "?")
        sport_counts[s] = sport_counts.get(s, 0) + 1

    print(f"\nWrote combined.json ({len(combined)} total)")
    for s, c in sorted(sport_counts.items()):
        print(f"  {s}: {c}")


if __name__ == "__main__":
    main()
