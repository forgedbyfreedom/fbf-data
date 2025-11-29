#!/usr/bin/env python3
import requests
import json
import time

OUTFILE = "injuries.json"

def fetch_json(url):
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        return None
    return None

def fetch_espn_injuries():
    base = "https://site.api.espn.com/apis/v2/sports"
    sports = [
        ("football", "nfl"),
        ("football", "ncaaf"),
        ("basketball", "nba"),
        ("basketball", "ncb")
    ]

    injuries = []
    for cat, lg in sports:
        url = f"{base}/{cat}/{lg}/news/injuries"
        data = fetch_json(url)
        if not data or "injuries" not in data:
            continue
        for team in data["injuries"]:
            tname = team.get("team", {}).get("displayName")
            for item in team.get("injuries", []):
                injuries.append({
                    "team": tname,
                    "player": item.get("athlete", {}).get("displayName"),
                    "status": item.get("status"),
                    "desc": item.get("details")
                })
    return injuries

def fetch_yahoo():
    url = "https://yahoo.com/sports/feeds/injuries"
    return []   # placeholder—Yahoo requires HTML parse; handled in A3 below

def fetch_rotowire():
    url = "https://feeds.rotowire.com/pdfs/injuries.json"
    data = fetch_json(url)
    if not data:
        return []
    injuries = []
    for sport, teams in data.items():
        for team in teams:
            for item in team.get("players", []):
                injuries.append({
                    "team": team.get("team"),
                    "player": item.get("name"),
                    "status": item.get("injury_status"),
                    "desc": item.get("injury_notes")
                })
    return injuries

def main():
    # Try ESPN first
    espn = fetch_espn_injuries()
    if espn:
        print(f"[ESPN] Got {len(espn)} injuries")
        final = espn
    else:
        print("⚠️ ESPN failed, trying Rotowire...")
        rw = fetch_rotowire()
        if rw:
            print(f"[Rotowire] Got {len(rw)} injuries")
            final = rw
        else:
            print("⚠️ Rotowire failed, falling back to empty injury list")
            final = []

    with open(OUTFILE, "w") as f:
        json.dump(final, f, indent=2)

    print(f"✅ Wrote {OUTFILE} ({len(final)} injuries)")

if __name__ == "__main__":
    main()
