#!/usr/bin/env python3
"""
build_ref_trends.py

Creates a basic referee-trend file based on whatever referee
information exists in combined.json.

This is scaffolding:
- If combined.json doesn't yet contain referee data, it will still
  write an empty ref_trends.json so downstream scripts don't break.
- Once you merge ref data onto games (e.g. via some API), this
  script will start accumulating simple trends.

Output: ref_trends.json
"""

import json
import os
from datetime import datetime, timezone

INPUT = "combined.json"
OUTPUT = "ref_trends.json"

def main():
    if not os.path.exists(INPUT):
        print(f"❌ {INPUT} not found.")
        return

    with open(INPUT, "r") as f:
        root = json.load(f)

    games = root.get("data") or root.get("games") or root.get("combined") or []

    refs = {}  # key: ref name or id

    for g in games:
        # Expect something like g["officials"] or g["referees"]
        officials = (
            g.get("officials")
            or g.get("referees")
            or g.get("refs")
            or []
        )

        if not isinstance(officials, list):
            continue

        for o in officials:
            if isinstance(o, str):
                name = o.strip()
                ref_id = name
            elif isinstance(o, dict):
                name = o.get("name") or o.get("fullName") or o.get("displayName")
                ref_id = o.get("id") or name
            else:
                continue

            if not name:
                continue

            rec = refs.setdefault(
                ref_id,
                {
                    "id": ref_id,
                    "name": name,
                    "games": 0,
                    # these can be populated later when scores/ATS flags are merged
                    "home_covers": 0,
                    "home_fails": 0,
                    "overs": 0,
                    "unders": 0,
                },
            )
            rec["games"] += 1

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": INPUT,
        "refs": refs,
    }

    with open(OUTPUT, "w") as f:
        json.dump(out, f, indent=2)

    print(f"✅ Wrote {OUTPUT} (refs={len(refs)})")

if __name__ == "__main__":
    main()
