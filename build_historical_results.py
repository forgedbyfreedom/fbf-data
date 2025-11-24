#!/usr/bin/env python3
"""
build_historical_results.py
---------------------------------
Builds a 5-year historical dataset using ESPN Core API.

Outputs:
- historical_results.json

Each record includes:
- sport
- event_id
- date_utc
- home/away teams
- final scores
- spread / total (when present)
- favorite
- ATS result (home/away/push/none)
- OU result (over/under/push/none)

NOTE:
ESPN historical odds availability varies by sport/season. This script:
- uses odds if ESPN provides them
- otherwise leaves spread/total as None and ATS/OU as "none"
"""

import json, os, time, math, datetime as dt
from typing import Dict, Any, List, Optional
import requests

OUTFILE = "historical_results.json"

SPORTS = {
    "nfl": {
        "events_url": "http://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{season}/types/2/events?limit=500",
        "season_type": 2,  # regular season type already in url
    },
    "ncaaf": {
        "events_url": "http://sports.core.api.espn.com/v2/sports/football/leagues/college-football/seasons/{season}/types/2/events?limit=500",
        "season_type": 2,
    },
    "nba": {
        "events_url": "http://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/{season}/types/2/events?limit=500",
        "season_type": 2,
    },
    "ncaab": {
        "events_url": "http://sports.core.api.espn.com/v2/sports/basketball/leagues/mens-college-basketball/seasons/{season}/types/2/events?limit=500",
        "season_type": 2,
    },
    "nhl": {
        "events_url": "http://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl/seasons/{season}/types/2/events?limit=500",
        "season_type": 2,
    },
}

HEADERS = {
    "User-Agent": "fbf-data-historical (contact@forgedbyfreedom.com)"
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

def get_json(url: str, tries: int = 3, sleep: float = 0.6) -> Optional[Dict[str, Any]]:
    for i in range(tries):
        try:
            r = SESSION.get(url, timeout=20)
            if r.status_code == 200:
                return r.json()
            time.sleep(sleep)
        except Exception:
            time.sleep(sleep)
    return None

def safe_float(x):
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None

def parse_competitors(comp: Dict[str, Any]) -> Dict[str, Any]:
    competitors = comp.get("competitors", [])
    home, away = None, None

    for c in competitors:
        if c.get("homeAway") == "home":
            home = c
        elif c.get("homeAway") == "away":
            away = c

    def pack(team_blob):
        if not team_blob:
            return {"id": None, "name": None, "abbr": None, "score": None}
        team = team_blob.get("team", {}) or {}
        return {
            "id": str(team.get("id")) if team.get("id") else None,
            "name": team.get("displayName") or team.get("name"),
            "abbr": team.get("abbreviation"),
            "score": safe_float(team_blob.get("score")),
        }

    return {"home": pack(home), "away": pack(away)}

def parse_odds(comp: Dict[str, Any]) -> Dict[str, Any]:
    odds_list = comp.get("odds") or []
    if not odds_list or not isinstance(odds_list, list):
        return {"spread": None, "total": None, "favorite": None, "details": None, "provider": None}

    # take first odds provider
    o = odds_list[0] or {}
    details = o.get("details")
    spread = safe_float(o.get("spread"))
    total = safe_float(o.get("overUnder")) or safe_float(o.get("total"))
    provider = o.get("provider", {}).get("name") if isinstance(o.get("provider"), dict) else o.get("provider")

    favorite = None
    if details and isinstance(details, str):
        favorite = details.split(" ")[0].strip()

    return {
        "spread": spread,
        "total": total,
        "favorite": favorite,
        "details": details,
        "provider": provider
    }

def compute_ats(home_score, away_score, spread, favorite_abbr, home_abbr, away_abbr):
    if spread is None or home_score is None or away_score is None or not favorite_abbr:
        return "none"

    # ESPN convention: details like "SF -7" means favorite is SF giving 7
    # We store spread as positive number for favorite giving points.
    fav_is_home = (favorite_abbr == home_abbr)
    fav_is_away = (favorite_abbr == away_abbr)
    if not (fav_is_home or fav_is_away):
        return "none"

    margin = (home_score - away_score)
    fav_margin = margin if fav_is_home else -margin

    if fav_margin > spread:
        return f"{favorite_abbr}_covers"
    if math.isclose(fav_margin, spread, abs_tol=0.01):
        return "push"
    return f"{favorite_abbr}_fails"

def compute_ou(home_score, away_score, total):
    if total is None or home_score is None or away_score is None:
        return "none"
    pts = home_score + away_score
    if pts > total:
        return "over"
    if math.isclose(pts, total, abs_tol=0.01):
        return "push"
    return "under"

def fetch_event_detail(event_url: str) -> Optional[Dict[str, Any]]:
    ev = get_json(event_url)
    if not ev:
        return None

    # competitions are refs, follow first
    comps_ref = ev.get("competitions")
    if isinstance(comps_ref, dict) and comps_ref.get("$ref"):
        comps = get_json(comps_ref["$ref"])
    else:
        comps = comps_ref

    if not comps or "items" not in comps:
        return None

    comp_url = comps["items"][0].get("$ref")
    if not comp_url:
        return None

    comp = get_json(comp_url)
    if not comp:
        return None

    # only final games
    status = comp.get("status", {}).get("type", {}).get("name")
    if status not in ("STATUS_FINAL", "STATUS_COMPLETED"):
        return None

    teams = parse_competitors(comp)
    odds = parse_odds(comp)

    date_utc = comp.get("date") or ev.get("date")
    home = teams["home"]
    away = teams["away"]

    home_score = home["score"]
    away_score = away["score"]

    ats = compute_ats(
        home_score, away_score,
        odds["spread"],
        odds["favorite"],
        home["abbr"], away["abbr"]
    )
    ou = compute_ou(home_score, away_score, odds["total"])

    return {
        "event_id": str(ev.get("id") or comp.get("id")),
        "date_utc": date_utc,
        "home_team": home,
        "away_team": away,
        "spread": odds["spread"],
        "total": odds["total"],
        "favorite": odds["favorite"],
        "odds_details": odds["details"],
        "odds_provider": odds["provider"],
        "ats_result": ats,
        "ou_result": ou
    }

def fetch_events_for_season(sport_key: str, season_year: int) -> List[Dict[str, Any]]:
    sport = SPORTS[sport_key]
    url = sport["events_url"].format(season=season_year)
    out = []

    while url:
        page = get_json(url)
        if not page:
            break

        items = page.get("items") or []
        for it in items:
            ref = it.get("$ref")
            if not ref:
                continue
            detail = fetch_event_detail(ref)
            if detail:
                detail["sport"] = sport_key
                detail["season"] = season_year
                out.append(detail)

        nxt = page.get("next", {})
        url = nxt.get("$ref")

        time.sleep(0.25)

    return out

def main():
    now = dt.datetime.utcnow()
    end_year = now.year
    start_year = end_year - 4  # 5 seasons inclusive

    all_rows = []
    for sport_key in SPORTS.keys():
        print(f"[ℹ️] Fetching historical for {sport_key} seasons {start_year}-{end_year} ...")
        for season in range(start_year, end_year + 1):
            rows = fetch_events_for_season(sport_key, season)
            print(f"   ✅ {sport_key} {season}: {len(rows)} final games")
            all_rows.extend(rows)

    payload = {
        "timestamp": now.strftime("%Y%m%d_%H%M"),
        "count": len(all_rows),
        "start_year": start_year,
        "end_year": end_year,
        "data": all_rows
    }

    with open(OUTFILE, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"[✅] Wrote {OUTFILE} with {len(all_rows)} games.")

if __name__ == "__main__":
    main()
