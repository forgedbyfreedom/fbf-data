#!/usr/bin/env python3
"""
build_historical_results.py
---------------------------------
Builds a 3-year historical dataset using ESPN Core API.
Supports incremental mode: only fetches seasons not already stored.

Outputs: historical_results.json

Each record includes:
- sport, event_id, date_utc
- home/away teams with scores
- spread / total (when present)
- favorite, ATS result, OU result
"""

import json, os, time, math, datetime as dt
from typing import Dict, Any, List, Optional
import requests

OUTFILE = "historical_results.json"
YEARS_BACK = 3  # 3 seasons instead of 5 to reduce runtime

SPORTS = {
    "nfl": {
        "events_url": "http://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{season}/types/2/events?limit=500",
    },
    "ncaaf": {
        "events_url": "http://sports.core.api.espn.com/v2/sports/football/leagues/college-football/seasons/{season}/types/2/events?limit=500",
    },
    "nba": {
        "events_url": "http://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/{season}/types/2/events?limit=500",
    },
    "ncaab": {
        "events_url": "http://sports.core.api.espn.com/v2/sports/basketball/leagues/mens-college-basketball/seasons/{season}/types/2/events?limit=500",
    },
    "nhl": {
        "events_url": "http://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl/seasons/{season}/types/2/events?limit=500",
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

    status = comp.get("status", {}).get("type", {}).get("name")
    if status not in ("STATUS_FINAL", "STATUS_COMPLETED"):
        return None

    teams = parse_competitors(comp)
    odds = parse_odds(comp)

    # Parse officials
    officials = []
    officials_ref = comp.get("officials")
    if isinstance(officials_ref, dict) and officials_ref.get("$ref"):
        off_data = get_json(officials_ref["$ref"])
        if off_data and "items" in off_data:
            for item in off_data["items"]:
                ref_url = item.get("$ref")
                if ref_url:
                    ref_data = get_json(ref_url)
                    if ref_data:
                        officials.append({
                            "name": ref_data.get("fullName") or ref_data.get("displayName"),
                            "position": ref_data.get("position", {}).get("displayName") if isinstance(ref_data.get("position"), dict) else None,
                        })
    elif isinstance(officials_ref, list):
        for o in officials_ref:
            if isinstance(o, dict):
                officials.append({
                    "name": o.get("fullName") or o.get("displayName") or o.get("name"),
                    "position": o.get("position"),
                })

    date_utc = comp.get("date") or ev.get("date")
    home = teams["home"]
    away = teams["away"]

    ats = compute_ats(
        home["score"], away["score"],
        odds["spread"], odds["favorite"],
        home["abbr"], away["abbr"]
    )
    ou = compute_ou(home["score"], away["score"], odds["total"])

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
        "ou_result": ou,
        "officials": officials,
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
    start_year = end_year - YEARS_BACK

    # Incremental mode: load existing data and skip already-fetched seasons
    existing = {}
    existing_rows = []
    if os.path.exists(OUTFILE):
        try:
            with open(OUTFILE, "r") as f:
                old = json.load(f)
            existing_rows = old.get("data", [])
            for r in existing_rows:
                s = r.get("sport")
                y = r.get("season")
                if s and y:
                    existing.setdefault(s, set()).add(y)
            print(f"[historical] Loaded {len(existing_rows)} existing records")
        except Exception:
            pass

    new_rows = []
    for sport_key in SPORTS.keys():
        for season in range(start_year, end_year + 1):
            if season in existing.get(sport_key, set()):
                print(f"  [skip] {sport_key} {season} (already fetched)")
                continue

            print(f"  [fetch] {sport_key} {season} ...")
            rows = fetch_events_for_season(sport_key, season)
            print(f"    -> {len(rows)} final games")
            new_rows.extend(rows)

    all_rows = existing_rows + new_rows

    payload = {
        "timestamp": now.strftime("%Y%m%d_%H%M"),
        "count": len(all_rows),
        "start_year": start_year,
        "end_year": end_year,
        "data": all_rows
    }

    with open(OUTFILE, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"[historical] Wrote {OUTFILE}: {len(all_rows)} total ({len(new_rows)} new)")


if __name__ == "__main__":
    main()
