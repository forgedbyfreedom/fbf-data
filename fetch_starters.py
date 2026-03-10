#!/usr/bin/env python3
"""
fetch_starters.py
Fetches confirmed starting pitchers (MLB) and goalies (NHL) from ESPN.
Starter identity significantly impacts game lines.

For MLB: ERA, WHIP, K/9, W-L record
For NHL: save%, GAA, wins

Output: starters_data.json

Run AFTER: fetch_espn_all.py
Run BEFORE: merge_features.py
"""

import json, re, time
from datetime import datetime, timezone
import requests

COMBINED = "combined.json"
OUTPUT = "starters_data.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# ESPN API endpoints for rosters/probable pitchers
MLB_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
NHL_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"


def get_json(url, tries=2):
    for i in range(tries):
        try:
            r = SESSION.get(url, timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(0.5)
    return None


def safe_float(x):
    try:
        return float(x) if x is not None else None
    except (ValueError, TypeError):
        return None


def fetch_mlb_starters():
    """Fetch probable pitchers from ESPN MLB scoreboard."""
    starters = {}
    data = get_json(MLB_SCOREBOARD)
    if not data:
        return starters

    events = data.get("events", [])
    for ev in events:
        event_id = str(ev.get("id", ""))
        comps = ev.get("competitions", [])
        if not comps:
            continue
        comp = comps[0]

        for competitor in comp.get("competitors", []):
            home_away = competitor.get("homeAway", "")
            team = competitor.get("team", {})
            team_abbr = team.get("abbreviation", "")

            # Look for probable pitcher in roster/leaders
            probables = competitor.get("probables", [])
            if probables:
                pitcher = probables[0]
                athlete = pitcher.get("athlete", {})
                stats = pitcher.get("statistics", [])

                # Parse stats
                stat_dict = {}
                for s in stats:
                    if isinstance(s, dict):
                        stat_dict[s.get("abbreviation", "")] = s.get("displayValue", "")

                starter_info = {
                    "name": athlete.get("displayName", ""),
                    "id": str(athlete.get("id", "")),
                    "team_abbr": team_abbr,
                    "home_away": home_away,
                    "era": safe_float(stat_dict.get("ERA")),
                    "whip": safe_float(stat_dict.get("WHIP")),
                    "wins": stat_dict.get("W", ""),
                    "losses": stat_dict.get("L", ""),
                    "record": stat_dict.get("W-L", ""),
                    "ip": safe_float(stat_dict.get("IP")),
                    "so": safe_float(stat_dict.get("SO") or stat_dict.get("K")),
                }

                # Compute K/9 if we have SO and IP
                if starter_info["so"] and starter_info["ip"] and starter_info["ip"] > 0:
                    starter_info["k_per_9"] = round(9 * starter_info["so"] / starter_info["ip"], 1)

                key = f"{event_id}_{home_away}"
                starters[key] = starter_info

    return starters


def fetch_nhl_starters():
    """Fetch confirmed/probable goalies from ESPN NHL scoreboard."""
    starters = {}
    data = get_json(NHL_SCOREBOARD)
    if not data:
        return starters

    events = data.get("events", [])
    for ev in events:
        event_id = str(ev.get("id", ""))
        comps = ev.get("competitions", [])
        if not comps:
            continue
        comp = comps[0]

        for competitor in comp.get("competitors", []):
            home_away = competitor.get("homeAway", "")
            team = competitor.get("team", {})
            team_abbr = team.get("abbreviation", "")

            # Look for probable goalie
            probables = competitor.get("probables", [])
            if probables:
                goalie = probables[0]
                athlete = goalie.get("athlete", {})
                stats = goalie.get("statistics", [])

                stat_dict = {}
                for s in stats:
                    if isinstance(s, dict):
                        stat_dict[s.get("abbreviation", "")] = s.get("displayValue", "")

                starter_info = {
                    "name": athlete.get("displayName", ""),
                    "id": str(athlete.get("id", "")),
                    "team_abbr": team_abbr,
                    "home_away": home_away,
                    "save_pct": safe_float(stat_dict.get("SV%") or stat_dict.get("SVPCT")),
                    "gaa": safe_float(stat_dict.get("GAA")),
                    "wins": stat_dict.get("W", ""),
                    "losses": stat_dict.get("L", ""),
                    "record": stat_dict.get("W-L", "") or stat_dict.get("REC", ""),
                }

                key = f"{event_id}_{home_away}"
                starters[key] = starter_info

    return starters


def main():
    mlb_starters = fetch_mlb_starters()
    nhl_starters = fetch_nhl_starters()

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mlb": mlb_starters,
        "nhl": nhl_starters,
    }

    with open(OUTPUT, "w") as f:
        json.dump(output, f, indent=2)

    print(f"[starters] MLB: {len(mlb_starters)} probable pitchers, NHL: {len(nhl_starters)} probable goalies")


if __name__ == "__main__":
    main()
