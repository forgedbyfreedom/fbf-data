#!/usr/bin/env python3
"""
fetch_injuries.py
- Reads combined.json
- Pulls injuries for home/away teams using ESPN Core API team endpoints
- Writes injuries.json
- Adds per-game injury counts + lists into combined.json

Notes:
ESPN Core API provides injuries under team -> injuries endpoint for many leagues.
We do best-effort; if a league doesn't expose injuries, it will skip.
"""

import json, os, requests
from datetime import datetime, timezone

TIMEOUT = 12
OUT_FILE = "injuries.json"

LEAGUE_MAP = {
    "americanfootball_nfl": "football/leagues/nfl",
    "americanfootball_ncaaf": "football/leagues/college-football",
    "basketball_nba": "basketball/leagues/nba",
    "basketball_ncaab": "basketball/leagues/mens-college-basketball",
    "basketball_ncaaw": "basketball/leagues/womens-college-basketball",
    "icehockey_nhl": "hockey/leagues/nhl",
    "baseball_mlb": "baseball/leagues/mlb",
}

def get_json(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def team_lookup_url(league_path, team_name):
    # ESPN search endpoint to find team id
    q = requests.utils.quote(team_name)
    return f"https://site.api.espn.com/apis/v2/sports/{league_path}/teams?search={q}"

def fetch_team_id(league_path, team_name):
    try:
        data = get_json(team_lookup_url(league_path, team_name))
        items = data.get("sports",[{}])[0].get("leagues",[{}])[0].get("teams",[])
        if not items:
            return None
        # best fuzzy match
        for it in items:
            t = it.get("team",{})
            if team_name.lower() in (t.get("displayName","").lower()):
                return t.get("id")
        return items[0].get("team",{}).get("id")
    except Exception:
        return None

def fetch_injuries_for_team(league_path, team_id):
    if not team_id:
        return []
    url = f"https://sports.core.api.espn.com/v2/sports/{league_path}/teams/{team_id}/injuries"
    try:
        data = get_json(url)
        items = data.get("items", [])
        injuries = []
        for ref in items:
            ref_url = ref.get("$ref")
            if not ref_url:
                continue
            inj = get_json(ref_url)
            athlete = (inj.get("athlete") or {}).get("displayName")
            status = (inj.get("status") or {}).get("name")
            detail = inj.get("details") or ""
            injuries.append({
                "athlete": athlete,
                "status": status,
                "details": detail
            })
        return injuries
    except Exception:
        return []

def summarize(injuries):
    out = {"out":0, "doubtful":0, "questionable":0, "probable":0, "other":0}
    for i in injuries:
        s = (i.get("status") or "").lower()
        if "out" in s:
            out["out"] += 1
        elif "doubt" in s:
            out["doubtful"] += 1
        elif "question" in s:
            out["questionable"] += 1
        elif "probable" in s:
            out["probable"] += 1
        else:
            out["other"] += 1
    out["total"] = sum(out.values())
    return out

def main():
    if not os.path.exists("combined.json"):
        print("❌ combined.json missing")
        return

    with open("combined.json","r",encoding="utf-8") as f:
        payload = json.load(f)

    games = payload.get("data", [])
    master = {"timestamp": datetime.now(timezone.utc).isoformat(), "data": {}}

    for g in games:
        sport_key = g.get("sport_key","")
        league_path = LEAGUE_MAP.get(sport_key)
        if not league_path:
            continue

        for side in ["home_team","away_team"]:
            team_name = g.get(side)
            if not team_name:
                continue
            if team_name in master["data"]:
                continue

            team_id = fetch_team_id(league_path, team_name)
            injuries = fetch_injuries_for_team(league_path, team_id)
            master["data"][team_name] = {
                "team_id": team_id,
                "injuries": injuries,
                "summary": summarize(injuries),
            }

        home = g.get("home_team")
        away = g.get("away_team")
        if home in master["data"]:
            g["home_injuries"] = master["data"][home]["summary"]
        if away in master["data"]:
            g["away_injuries"] = master["data"][away]["summary"]

    with open(OUT_FILE,"w",encoding="utf-8") as f:
        json.dump(master, f, indent=2)

    payload["data"] = games
    with open("combined.json","w",encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"[✅] Injuries updated for {len(master['data'])} teams.")

if __name__ == "__main__":
    main()
