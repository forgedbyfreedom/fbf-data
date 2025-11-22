#!/usr/bin/env python3
"""
merge_injuries.py

Merges injuries into a single injuries.json.
Safe on blank repo:
- If no sources exist, creates empty injuries.json.

Suggested future sources:
- injuries_raw/nfl.json
- injuries_raw/ncaaf.json
etc.

Output schema:
{
  "timestamp": "...",
  "data": {
     "Team Name": [{"player":"", "status":"", "detail":""}, ...],
     ...
  }
}
"""

import json, os, glob
from datetime import datetime, timezone

RAW_DIR = "injuries_raw"
OUTFILE = "injuries.json"

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    injuries = {}

    raw_files = glob.glob(os.path.join(RAW_DIR, "*.json"))
    if not raw_files:
        payload = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
            "data": {},
            "note": "No injuries_raw/*.json sources found yet.",
        }
        with open(OUTFILE, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"⚠️  Wrote empty {OUTFILE}")
        return

    for rf in raw_files:
        data = load_json(rf, {})
        teams = data.get("data") if isinstance(data, dict) else data
        if not teams:
            continue

        for team_name, plist in teams.items():
            if team_name not in injuries:
                injuries[team_name] = []
            if isinstance(plist, list):
                injuries[team_name].extend(plist)

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "data": injuries,
        "sources": [os.path.basename(x) for x in raw_files],
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {OUTFILE} for {len(injuries)} teams")

if __name__ == "__main__":
    main()
