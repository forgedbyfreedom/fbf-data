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
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

OUTFILE = "historical_results.json"
YEARS_BACK = 3  # 3 seasons instead of 5 to reduce runtime

SPORTS = {
    "nfl": {
        "events_url": "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{season}/types/2/events?limit=500",
    },
    "ncaaf": {
        "events_url": "https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/seasons/{season}/types/2/events?limit=500",
    },
    "nba": {
        "events_url": "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/{season}/types/2/events?limit=500",
    },
    "ncaab": {
        "events_url": "https://sports.core.api.espn.com/v2/sports/basketball/leagues/mens-college-basketball/seasons/{season}/types/2/events?limit=500",
    },
    "nhl": {
        "events_url": "https://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl/seasons/{season}/types/2/events?limit=500",
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.espn.com/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def get_json(url: str, tries: int = 3) -> Optional[Dict[str, Any]]:
    for i in range(tries):
        try:
            r = SESSION.get(url, timeout=30)
            if r.status_code == 200:
                return r.json()
            print(f"  [warn] HTTP {r.status_code} for {url[:120]}")
            time.sleep(0.6 * (2 ** i))  # exponential backoff: 0.6, 1.2, 2.4
        except Exception as e:
            print(f"  [warn] Request failed (attempt {i+1}/{tries}): {type(e).__name__}: {e} — {url[:120]}")
            time.sleep(0.6 * (2 ** i))
    return None


def safe_float(x):
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def resolve_ref(obj):
    """If obj is a dict with $ref, resolve it. Otherwise return obj as-is."""
    if isinstance(obj, dict) and "$ref" in obj:
        return get_json(obj["$ref"].replace("http://", "https://")) or {}
    return obj or {}


def parse_competitors(comp: Dict[str, Any]) -> Dict[str, Any]:
    competitors = comp.get("competitors", [])
    # competitors might be a $ref itself
    if isinstance(competitors, dict) and "$ref" in competitors:
        competitors_data = get_json(competitors["$ref"].replace("http://", "https://"))
        competitors = (competitors_data or {}).get("items", [])
        # Resolve each competitor ref
        competitors = [resolve_ref(c) for c in competitors]

    home, away = None, None
    for c in competitors:
        if c.get("homeAway") == "home":
            home = c
        elif c.get("homeAway") == "away":
            away = c

    def pack(team_blob):
        if not team_blob:
            return {"id": None, "name": None, "abbr": None, "score": None}
        # Resolve team $ref
        team = team_blob.get("team", {})
        if isinstance(team, dict) and "$ref" in team:
            team = get_json(team["$ref"].replace("http://", "https://")) or {}
        # Resolve score $ref
        score_val = team_blob.get("score")
        if isinstance(score_val, dict) and "$ref" in score_val:
            score_data = get_json(score_val["$ref"].replace("http://", "https://")) or {}
            score_val = score_data.get("value") or score_data.get("displayValue")
        return {
            "id": str(team.get("id")) if team.get("id") else None,
            "name": team.get("displayName") or team.get("name"),
            "abbr": team.get("abbreviation"),
            "score": safe_float(score_val),
        }

    return {"home": pack(home), "away": pack(away)}


def parse_odds(comp: Dict[str, Any]) -> Dict[str, Any]:
    odds_ref = comp.get("odds") or []
    # odds can be a $ref
    if isinstance(odds_ref, dict) and "$ref" in odds_ref:
        odds_data = get_json(odds_ref["$ref"].replace("http://", "https://")) or {}
        odds_list = odds_data.get("items", [])
        # Resolve individual odds refs
        if odds_list and isinstance(odds_list[0], dict) and "$ref" in odds_list[0]:
            odds_list = [resolve_ref(o) for o in odds_list[:1]]
    elif isinstance(odds_ref, list):
        odds_list = odds_ref
    else:
        odds_list = []

    if not odds_list:
        return {"spread": None, "total": None, "favorite": None, "details": None, "provider": None}

    o = odds_list[0] or {}
    details = o.get("details")
    spread = safe_float(o.get("spread"))
    total = safe_float(o.get("overUnder")) or safe_float(o.get("total"))

    # Resolve provider $ref
    provider_obj = o.get("provider", {})
    if isinstance(provider_obj, dict) and "$ref" in provider_obj:
        provider_obj = resolve_ref(provider_obj)
    provider = provider_obj.get("name") if isinstance(provider_obj, dict) else provider_obj

    # Core API v2 nests odds in bettingOdds.teamOdds
    if spread is None or total is None:
        betting = o.get("bettingOdds", {})
        team_odds = betting.get("teamOdds", {})
        if team_odds:
            if spread is None:
                sh = team_odds.get("preMatchSpreadHandicapHome", {})
                spread = safe_float(sh.get("value")) if sh else None
            if total is None:
                th = team_odds.get("preMatchTotalHandicap", {})
                total = safe_float(th.get("value")) if th else None

    favorite = None
    if details and isinstance(details, str):
        favorite = details.split(" ")[0].strip()
    elif spread is not None and spread != 0:
        # Derive favorite from spread sign — negative spread = home favored
        # We'll set favorite later using team abbrs in fetch_event_detail
        pass

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
    # Ensure HTTPS for any $ref URLs returned by the API
    event_url = event_url.replace("http://", "https://")

    ev = get_json(event_url)
    if not ev:
        return None

    comps_ref = ev.get("competitions")

    # competitions can be: a list of dicts with $ref, a dict with $ref, or a dict with items
    comp = None
    if isinstance(comps_ref, list) and comps_ref:
        # List of competition objects (most common) — resolve $ref if needed
        first = comps_ref[0]
        if isinstance(first, dict) and "$ref" in first:
            comp = get_json(first["$ref"].replace("http://", "https://"))
        elif isinstance(first, dict):
            comp = first  # already resolved
    elif isinstance(comps_ref, dict):
        if "$ref" in comps_ref:
            comps_data = get_json(comps_ref["$ref"].replace("http://", "https://"))
            if comps_data and "items" in comps_data:
                comp_url = comps_data["items"][0].get("$ref")
                if comp_url:
                    comp = get_json(comp_url.replace("http://", "https://"))
        elif "items" in comps_ref:
            comp_url = comps_ref["items"][0].get("$ref")
            if comp_url:
                comp = get_json(comp_url.replace("http://", "https://"))

    if not comp:
        return None

    # Resolve status — can be a $ref
    status_obj = comp.get("status", {})
    status_obj = resolve_ref(status_obj)
    type_obj = status_obj.get("type", {})
    type_obj = resolve_ref(type_obj)
    status = type_obj.get("name")
    if status not in ("STATUS_FINAL", "STATUS_COMPLETED"):
        return None

    teams = parse_competitors(comp)
    odds = parse_odds(comp)

    # Parse officials
    officials = []
    officials_ref = comp.get("officials")
    if isinstance(officials_ref, dict) and officials_ref.get("$ref"):
        off_data = get_json(officials_ref["$ref"].replace("http://", "https://"))
        if off_data and "items" in off_data:
            for item in off_data["items"]:
                ref_url = item.get("$ref")
                if ref_url:
                    ref_data = get_json(ref_url.replace("http://", "https://"))
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

    # Derive favorite from spread if not set from details
    if not odds["favorite"] and odds["spread"] is not None and odds["spread"] != 0:
        # Spread is from home perspective: negative = home favored
        odds["favorite"] = home["abbr"] if odds["spread"] < 0 else away["abbr"]
        # Store spread as absolute value (standard convention)
        odds["spread"] = abs(odds["spread"])

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


def _fetch_one_event(args):
    """Worker for concurrent event fetching."""
    ref, sport_key, season_year = args
    detail = fetch_event_detail(ref)
    if detail:
        detail["sport"] = sport_key
        detail["season"] = season_year
    return detail


def fetch_events_for_season(sport_key: str, season_year: int) -> List[Dict[str, Any]]:
    sport = SPORTS[sport_key]
    url = sport["events_url"].format(season=season_year)
    all_refs = []
    page_num = 0

    # First collect all event refs
    while url:
        page_num += 1
        page = get_json(url)
        if not page:
            print(f"    [warn] Failed to fetch page {page_num} for {sport_key} {season_year}")
            break

        items = page.get("items") or []
        for it in items:
            ref = it.get("$ref")
            if ref:
                all_refs.append(ref.replace("http://", "https://"))

        if items:
            print(f"    page {page_num}: {len(items)} event refs collected ({len(all_refs)} total)")

        nxt = page.get("next", {})
        url = nxt.get("$ref")
        if url:
            url = url.replace("http://", "https://")
        time.sleep(0.15)

    if not all_refs:
        return []

    print(f"    Fetching {len(all_refs)} events with 6 concurrent workers...")

    # Fetch events concurrently (6 workers — polite but much faster)
    out = []
    args_list = [(ref, sport_key, season_year) for ref in all_refs]
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(_fetch_one_event, args): args for args in args_list}
        done = 0
        for future in as_completed(futures):
            done += 1
            try:
                detail = future.result()
                if detail:
                    out.append(detail)
            except Exception as e:
                print(f"    [warn] Event fetch error: {e}")
            if done % 50 == 0:
                print(f"    progress: {done}/{len(all_refs)} events processed, {len(out)} games fetched")

    return out


def main():
    now = dt.datetime.now(dt.timezone.utc)
    end_year = now.year
    start_year = end_year - YEARS_BACK

    # Incremental mode: load existing data and skip already-fetched seasons
    # But reset if existing data has 0 records (indicates previous failure)
    existing = {}
    existing_rows = []
    if os.path.exists(OUTFILE):
        try:
            with open(OUTFILE, "r") as f:
                old = json.load(f)
            existing_rows = old.get("data", [])
            if len(existing_rows) == 0:
                print(f"[historical] Existing file has 0 records — resetting for full fetch")
                existing_rows = []
                existing = {}
            else:
                for r in existing_rows:
                    s = r.get("sport")
                    y = r.get("season")
                    if s and y:
                        existing.setdefault(s, set()).add(y)
                print(f"[historical] Loaded {len(existing_rows)} existing records")
        except Exception as e:
            print(f"[historical] Error loading existing file: {e} — starting fresh")

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
