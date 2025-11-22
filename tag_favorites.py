#!/usr/bin/env python3
"""
tag_favorites.py
Reads combined.json and adds:
- fav_team, dog_team
- fav_spread, dog_spread
- favorite, underdog (strings w/ spreads)
- spread (fav spread)
Writes combined.json back in-place.
"""

import json, os
from datetime import datetime, timezone

def main():
    if not os.path.exists("combined.json"):
        print("❌ combined.json missing")
        return

    with open("combined.json","r",encoding="utf-8") as f:
        payload = json.load(f)

    games = payload.get("data", [])
    for g in games:
        lines = g.get("lines") or []
        if len(lines) < 2:
            continue

        # normalize missing spreads to None
        spreads = [(ln.get("team"), ln.get("spread")) for ln in lines]
        spreads = [(t, s if isinstance(s,(int,float)) else None) for t,s in spreads]

        # prefer actual negative/positive. if None or 0s, skip favorite tagging.
        valid = [(t,s) for t,s in spreads if s is not None]
        if len(valid) < 2:
            continue

        fav = min(valid, key=lambda x: x[1])   # most negative
        dog = max(valid, key=lambda x: x[1])

        fav_team, fav_spread = fav
        dog_team, dog_spread = dog

        g["fav_team"] = fav_team
        g["dog_team"] = dog_team
        g["fav_spread"] = float(fav_spread)
        g["dog_spread"] = float(dog_spread)
        g["spread"] = float(fav_spread)
        g["favorite"] = f"{fav_team} {fav_spread:+.1f}".replace("+", "+")
        g["underdog"] = f"{dog_team} {dog_spread:+.1f}".replace("+", "+")
        g["tagged_at"] = datetime.now(timezone.utc).isoformat()

    payload["data"] = games
    with open("combined.json","w",encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"[✅] Tagged favorites for {len(games)} games.")

if __name__ == "__main__":
    main()
