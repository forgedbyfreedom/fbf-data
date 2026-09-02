#!/usr/bin/env python3
"""
fetch_injuries.py
-----------------
Pulls injury reports from ESPN's Core API, per team, for the teams actually
playing in combined.json.

Replaces an HTML scrape of espn.com and oddstrader.com that had gone stale:
on 2026-09-02 it returned 3 "injuries" whose player names were paragraphs of
prose lifted off the page ("The actual recovery time for each of these NFL
injuries depends on the severity..."), and 0 of 81 games carried an injury.

Two things worth knowing about the data:

  * More than half of ESPN's injury entries carry status "Active" - a player
    with a note, not a player who is unavailable. A raw row count is therefore
    meaningless. Only genuinely unavailable statuses are written out.
  * College football has no mandated injury report. A sample of 10 NCAAF teams
    returned 1 injury between them. Expect this file to be almost entirely NFL,
    and do not read an empty college injury list as a failure.

Every entry keeps its ESPN `date`, which is what makes the late-injury signal
possible: an injury reported after the line was set is the case where the
market may not have caught up.

Output: injuries.json
"""

import json, os, sys
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

COMBINED = "combined.json"
OUTPUT = "injuries.json"
TIMEOUT = 12
WORKERS = 8
MAX_REPORT_AGE_DAYS = 60   # older entries are stale carry-over, not this week's news

LEAGUE_PATHS = {
    "nfl": "football/leagues/nfl",
    "ncaaf": "football/leagues/college-football",
}
BASE = "https://sports.core.api.espn.com/v2/sports"

# Statuses that mean the player is actually unavailable or in doubt.
# "Active" is excluded on purpose - it is a note, not an absence.
UNAVAILABLE = {"out", "injured reserve", "suspension", "doubtful", "day-to-day"}
IN_DOUBT = {"questionable"}

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"),
    "Accept": "application/json",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def get_json(url):
    if not url:
        return None
    try:
        r = SESSION.get(url.replace("http://", "https://"), timeout=TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def normalize(name):
    import re
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def teams_in_play():
    """(sport, team_id, team_name, abbr) for every team on the current slate."""
    try:
        with open(COMBINED) as f:
            games = json.load(f).get("data", [])
    except Exception as e:
        print(f"[injuries] Could not read {COMBINED}: {e}")
        return []
    seen, out = set(), []
    for g in games:
        sport = (g.get("sport") or "").lower()
        if sport not in LEAGUE_PATHS:
            continue
        for side in ("home_team", "away_team"):
            t = g.get(side) or {}
            tid = t.get("id")
            if not tid:
                continue
            key = (sport, str(tid))
            if key in seen:
                continue
            seen.add(key)
            out.append((sport, str(tid), t.get("name") or "", t.get("abbr") or ""))
    return out


def fetch_team(sport, team_id, team_name, abbr):
    path = LEAGUE_PATHS[sport]
    idx = get_json(f"{BASE}/{path}/teams/{team_id}/injuries")
    if not idx or not idx.get("items"):
        return []

    rows = []
    refs = [it.get("$ref") for it in idx["items"] if it.get("$ref")]
    for item in (get_json(r) for r in refs):
        if not item:
            continue
        status = (item.get("status") or "").strip()
        s_low = status.lower()
        if s_low not in UNAVAILABLE and s_low not in IN_DOUBT:
            continue  # Active, or something we do not score

        # ESPN occasionally leaves an old entry on a team, still marked Out.
        # One such row on 2026-09-02 was reported in November 2022. Rare (1 of
        # 242), but it inflates a count that is supposed to describe this week.
        reported = item.get("date")
        if reported:
            try:
                when = datetime.fromisoformat(str(reported).replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - when).days > MAX_REPORT_AGE_DAYS:
                    continue
            except Exception:
                pass

        athlete = get_json((item.get("athlete") or {}).get("$ref")) or {}
        player = athlete.get("displayName") or athlete.get("fullName") or ""
        position = ((athlete.get("position") or {}).get("abbreviation")
                    if isinstance(athlete.get("position"), dict) else "") or ""

        rows.append({
            "sport": sport,
            "team": team_name,
            "team_norm": normalize(team_name),
            "team_abbr": abbr,
            "player": player,
            "position": position,
            "status": status,
            "unavailable": s_low in UNAVAILABLE,
            "reported_at": item.get("date"),
            "note": item.get("shortComment") or "",
        })
    return rows


def main():
    teams = teams_in_play()
    if not teams:
        print("[injuries] No teams on the slate - nothing to fetch.")
        return
    print(f"[injuries] Fetching injuries for {len(teams)} teams...")

    all_rows = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(fetch_team, *t): t for t in teams}
        done = 0
        for fut in as_completed(futures):
            done += 1
            try:
                all_rows.extend(fut.result())
            except Exception as e:
                print(f"    [warn] {futures[fut][2]}: {e}")
            if done % 20 == 0:
                print(f"    {done}/{len(teams)} teams, {len(all_rows)} injuries so far")

    by_sport = {}
    for r in all_rows:
        by_sport[r["sport"]] = by_sport.get(r["sport"], 0) + 1

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "espn-core-api",
        "count": len(all_rows),
        "by_sport": by_sport,
        "injuries": all_rows,
    }
    with open(OUTPUT, "w") as f:
        json.dump(payload, f, indent=2)

    unavailable = sum(1 for r in all_rows if r["unavailable"])
    print(f"[injuries] Wrote {OUTPUT}: {len(all_rows)} entries "
          f"({unavailable} unavailable, {len(all_rows) - unavailable} questionable) "
          f"across {len(teams)} teams | by sport: {by_sport}")
    if by_sport.get("ncaaf", 0) == 0:
        print("[injuries] No college injuries found. This is normal - NCAAF has "
              "no mandated injury report.")


if __name__ == "__main__":
    main()
