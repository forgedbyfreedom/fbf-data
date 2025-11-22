#!/usr/bin/env python3
"""
build_injuries.py

Fetches injuries from ESPN where possible.
Currently supports:
- NFL
- NCAAF (best-effort)

Outputs injuries.json
Safe if endpoints fail.
"""

import json, os
from datetime import datetime, timezone
import requests

TIMEOUT = 12
OUTFILE = "injuries.json"

NFL_INJ_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
CF_INJ_URL  = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/injuries"

def get_json(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def parse_inj(payload, sport_key):
    out = []
    items = payload.get("injuries") or payload.get("items") or []
    for it in items:
        try:
            team = (it.get("team") or {}).get("displayName") or it.get("teamName")
            athletes = it.get("athletes") or it.get("entries") or []
            for a in athletes:
                athlete = a.get("athlete") or a
                out.append({
                    "sport_key": sport_key,
                    "team": team,
                    "player": athlete.get("displayName") or athlete.get("name"),
                    "status": a.get("status") or athlete.get("status"),
                    "detail": a.get("description") or a.get("injuryDescription"),
                    "updated": a.get("date") or a.get("lastModified"),
                })
        except Exception:
            continue
    return out

def main():
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    out, errors = [], []

    for sport_key, url in [
        ("americanfootball_nfl", NFL_INJ_URL),
        ("americanfootball_ncaaf", CF_INJ_URL),
    ]:
        try:
            data = get_json(url)
            out.extend(parse_inj(data, sport_key))
        except Exception as e:
            errors.append({"sport_key": sport_key, "reason": str(e)})

    payload = {
        "timestamp": ts,
        "count": len(out),
        "data": out,
        "errors": errors or None
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {OUTFILE} ({len(out)} injuries)")

if __name__ == "__main__":
    main()
