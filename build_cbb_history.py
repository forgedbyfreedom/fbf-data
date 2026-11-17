#!/usr/bin/env python3
"""
build_cbb_history.py
Men's (ncaab) and women's (ncaaw) college basketball results + pre-game
lines, in the same row schema as historical_results.json, stored one file per
league-season: cbb_history/<league>_<season>.json. Basketball is ~6,000 games
a league-season (35 MB for five seasons of both); one file per season means a
finished season is written once and never re-committed - only the small
current-season file changes nightly. Load with cbb_history_load() below.

Why a separate builder: a D1 basketball season is ~5,500 games per league,
and build_historical_results.py resolves 3-4 nested ESPN references per event.
This uses one scoreboard call per day (all D1 games, scores, neutral flag)
and one odds call per completed game.

Line used: ESPN's pre-game book line (provider "ESPN BET" / first non-live
provider). In-game "Live Odds" entries are ignored - a pick is only
meaningful against a line that existed before tip-off (MODEL_NOTES
2026-10-15).

Seasons follow ESPN's convention: season 2026 = the 2025-26 season.

Usage:
  python3 build_cbb_history.py                 # backfill missing seasons + refresh current
  python3 build_cbb_history.py ncaab 2024 2026 # explicit league/season range
"""
import json, os, sys, time, datetime as dt
import concurrent.futures as cf
import requests

from build_historical_results import compute_ats, compute_ou

DIR = "cbb_history"
LEAGUES = {"ncaab": "mens-college-basketball", "ncaaw": "womens-college-basketball"}
YEARS_BACK = 5
SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/{lg}/scoreboard?dates={d}&groups=50&limit=500"
ODDS = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/{lg}/events/{e}/competitions/{e}/odds"
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})


def get(url, tries=3):
    for k in range(tries):
        try:
            r = S.get(url, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1.5 * (k + 1))
    return None


def season_dates(season):
    """ESPN season N runs from early November of N-1 to early April of N."""
    d, end = dt.date(season - 1, 11, 1), dt.date(season, 4, 12)
    today = dt.date.today()
    while d <= min(end, today):
        yield d
        d += dt.timedelta(days=1)


def pregame_line(lg, eid):
    od = get(ODDS.format(lg=lg, e=eid)) or {}
    for o in od.get("items") or []:
        name = ((o.get("provider") or {}).get("name") or "")
        if "live" in name.lower():
            continue
        if o.get("spread") is None and o.get("overUnder") is None:
            continue
        return {"spread": o.get("spread"), "total": o.get("overUnder"),
                "details": o.get("details"), "provider": name}
    return None


def team(c):
    t = c.get("team") or {}
    try:
        score = int(c.get("score"))
    except (TypeError, ValueError):
        score = None
    return {"id": t.get("id"), "abbr": t.get("abbreviation"),
            "name": t.get("displayName"), "score": score}


def games_on(lg, d):
    sb = get(SITE.format(lg=lg, d=d.strftime("%Y%m%d"))) or {}
    out = []
    for ev in sb.get("events") or []:
        comp = (ev.get("competitions") or [{}])[0]
        if not ((comp.get("status") or {}).get("type") or {}).get("completed"):
            continue
        cs = comp.get("competitors") or []
        h = next((c for c in cs if c.get("homeAway") == "home"), None)
        a = next((c for c in cs if c.get("homeAway") == "away"), None)
        if not h or not a:
            continue
        out.append({"event_id": str(ev["id"]), "date_utc": ev.get("date"),
                    "home_team": team(h), "away_team": team(a),
                    "neutral_site": bool(comp.get("neutralSite")),
                    "conference_game": bool(comp.get("conferenceCompetition"))})
    return out


def build_season(key, season, known):
    lg = LEAGUES[key]
    days = list(season_dates(season))
    with cf.ThreadPoolExecutor(8) as ex:
        games = [g for day in ex.map(lambda d: games_on(lg, d), days) for g in day]
    games = [g for g in games if g["event_id"] not in known]
    print(f"  [{key} {season}] {len(days)} days, {len(games)} new completed games; fetching lines")

    def add_line(g):
        ln = pregame_line(lg, g["event_id"])
        hs, aw = g["home_team"]["score"], g["away_team"]["score"]
        spread = ln["spread"] if ln else None          # home-relative
        fav = None
        if spread not in (None, 0):
            fav = g["home_team"]["abbr"] if spread < 0 else g["away_team"]["abbr"]
        g.update({"spread": spread, "total": ln["total"] if ln else None,
                  "favorite": fav, "odds_details": ln["details"] if ln else None,
                  "odds_provider": ln["provider"] if ln else None,
                  "officials": [], "sport": key, "season": season})
        if hs is not None and aw is not None:
            g["ats_result"] = compute_ats(hs, aw, spread, fav, g["home_team"]["abbr"], g["away_team"]["abbr"])
            g["ou_result"] = compute_ou(hs, aw, g["total"])
        return g
    with cf.ThreadPoolExecutor(16) as ex:
        rows = list(ex.map(add_line, games))
    lined = sum(r["spread"] is not None for r in rows)
    print(f"  [{key} {season}] {len(rows)} games, {lined} with a pre-game spread")
    return rows


def current_season():
    t = dt.date.today()
    return t.year + 1 if t.month >= 8 else t.year


def path_for(key, season):
    return os.path.join(DIR, f"{key}_{season}.json")


def cbb_history_load(sports=("ncaab", "ncaaw"), seasons=None):
    """All stored basketball rows for the given leagues (and seasons)."""
    rows = []
    if not os.path.isdir(DIR):
        return rows
    for fn in sorted(os.listdir(DIR)):
        m = fn[:-5].rsplit("_", 1) if fn.endswith(".json") else None
        if not m or m[0] not in sports or (seasons and int(m[1]) not in seasons):
            continue
        rows.extend(json.load(open(os.path.join(DIR, fn))).get("data", []))
    return rows


def main():
    os.makedirs(DIR, exist_ok=True)
    cur = current_season()
    if len(sys.argv) == 4:
        plan = [(sys.argv[1], y) for y in range(int(sys.argv[2]), int(sys.argv[3]) + 1)]
    else:
        plan = [(k, y) for k in LEAGUES for y in range(cur - YEARS_BACK, cur + 1)]
    for key, season in plan:
        fn = path_for(key, season)
        mine = json.load(open(fn)).get("data", []) if os.path.exists(fn) else []
        if mine and season < cur and len(mine) > 3000:
            print(f"  [skip] {key} {season} ({len(mine)} stored)")
            continue
        known = {str(r.get("event_id")) for r in mine}
        new = build_season(key, season, known)
        if not new and mine:
            continue
        rows = sorted(mine + new, key=lambda r: r.get("date_utc") or "")
        json.dump({"sport": key, "season": season, "count": len(rows), "data": rows},
                  open(fn, "w"), separators=(",", ":"))
        print(f"[cbb_history] {fn}: {len(rows)} games ({len(new)} new)")


if __name__ == "__main__":
    main()
