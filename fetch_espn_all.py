#!/usr/bin/env python3
"""
fetch_espn_all.py
Unified ESPN ODDS API fetcher for:
NFL, NCAAF (FBS), NBA, NCAAB, NCAAW, MLB, NHL, UFC

Outputs:
- nfl.json, ncaaf.json, nba.json, ncaab.json, ncaaw.json, mlb.json, nhl.json, mixedmartialarts.json
- combined.json

Canonical per-event:
{
  "sport_key": "...",
  "matchup": "Away@Home",
  "home_team": "...",
  "away_team": "...",
  "commence_time": "...",
  "lines": [
     {"team": "...", "spread": -x.x},
     {"team": "...", "spread":  x.x}
  ],
  "total": 47.5,
  "book": "ESPN",
  "event_id": "...",
  "fetched_at": "..."
}
"""

import json, re, requests
from datetime import datetime, timezone

TIMEOUT = 12

ESPN_ODDS_ENDPOINTS = {
    "nfl":  ("https://site.api.espn.com/apis/v2/sports/football/nfl/odds", "nfl.json"),
    "ncaaf":("https://site.api.espn.com/apis/v2/sports/football/college-football/odds", "ncaaf.json"),
    "nba":  ("https://site.api.espn.com/apis/v2/sports/basketball/nba/odds", "nba.json"),
    "ncaab":("https://site.api.espn.com/apis/v2/sports/basketball/mens-college-basketball/odds", "ncaab.json"),
    "ncaaw":("https://site.api.espn.com/apis/v2/sports/basketball/womens-college-basketball/odds", "ncaaw.json"),
    "mlb":  ("https://site.api.espn.com/apis/v2/sports/baseball/mlb/odds", "mlb.json"),
    "nhl":  ("https://site.api.espn.com/apis/v2/sports/hockey/nhl/odds", "nhl.json"),
    "ufc":  ("https://site.api.espn.com/apis/v2/sports/mma/ufc/odds", "mixedmartialarts.json"),
}

def safe_float(x):
    try:
        if x is None:
            return None
        if isinstance(x, str):
            x = x.replace("½", ".5")
            x = re.sub(r"[^\d\.\-\+]", "", x)
        return float(x)
    except Exception:
        return None

def get_json(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def parse_details_to_spreads(details, team_names):
    if not details:
        return None
    m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*$", details.strip().replace("½", ".5"))
    if not m:
        return None
    spread_val = safe_float(m.group(1))
    if spread_val is None:
        return None
    team_text = details[:m.start()].strip()

    fav_team = None
    for tn in team_names:
        if tn.lower() in team_text.lower() or team_text.lower() in tn.lower():
            fav_team = tn
            break
    if fav_team is None:
        return None

    dog_team = [t for t in team_names if t != fav_team]
    if not dog_team:
        return None
    dog_team = dog_team[0]
    return {fav_team: spread_val, dog_team: -spread_val}

def extract_event_record(sport_key, event):
    comp = (event.get("competitions") or [{}])[0]
    competitors = comp.get("competitors") or []
    if len(competitors) < 2:
        return None

    team_names = []
    home_team = away_team = None

    for c in competitors:
        t = c.get("team") or c.get("athlete") or {}
        name = (
            t.get("displayName")
            or t.get("shortDisplayName")
            or c.get("displayName")
            or "Unknown"
        )
        team_names.append(name)
        if c.get("homeAway") == "home":
            home_team = name
        if c.get("homeAway") == "away":
            away_team = name

    spreads_by_team = {}
    for c, name in zip(competitors, team_names):
        o = c.get("odds") or {}
        spread = safe_float(o.get("spread"))
        if spread is not None:
            spreads_by_team[name] = spread

    if len(spreads_by_team) < 2:
        comp_odds = comp.get("odds") or {}
        details = comp_odds.get("details") or ""
        parsed = parse_details_to_spreads(details, team_names)
        if parsed:
            spreads_by_team.update(parsed)

    lines = [{"team": name, "spread": spreads_by_team.get(name)} for name in team_names]

    comp_odds = comp.get("odds") or {}
    total = safe_float(comp_odds.get("overUnder") or comp_odds.get("total"))
    if total is None:
        for c in competitors:
            o = c.get("odds") or {}
            total = safe_float(o.get("overUnder") or o.get("total"))
            if total is not None:
                break

    if home_team and away_team:
        matchup = f"{away_team}@{home_team}"
    else:
        matchup = f"{team_names[0]} vs {team_names[1]}"

    provider = (comp_odds.get("provider") or {}).get("name") or "ESPN"

    return {
        "sport_key": sport_key,
        "matchup": matchup,
        "home_team": home_team or team_names[1],
        "away_team": away_team or team_names[0],
        "commence_time": event.get("date") or comp.get("date"),
        "lines": lines,
        "total": total,
        "book": provider,
        "event_id": event.get("id"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

def fetch_sport(sport_key, url):
    data = get_json(url)
    events = data.get("events") or []
    out = []
    for ev in events:
        rec = extract_event_record(sport_key, ev)
        if rec:
            out.append(rec)
    return out

def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    combined = []
    errors = {}

    for sport_key, (url, filename) in ESPN_ODDS_ENDPOINTS.items():
        try:
            print(f"[⏱️] Fetching {sport_key} odds → {url}")
            recs = fetch_sport(sport_key, url)
            print(f"   → {len(recs)} events.")
            combined.extend(recs)

            with open(filename, "w", encoding="utf-8") as f:
                json.dump({"timestamp": timestamp, "data": recs}, f, indent=2)

        except Exception as e:
            errors[sport_key] = str(e)
            print(f"⚠️  {sport_key} failed: {e}")

    payload = {
        "timestamp": timestamp,
        "source": "ESPN_ODDS_API",
        "data": combined,
        "errors": errors or None,
    }
    with open("combined.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"[✅] Saved combined.json with {len(combined)} events at {timestamp}.")

if __name__ == "__main__":
    main()
