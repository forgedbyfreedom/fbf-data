#!/usr/bin/env python3
import json, os

PATH = os.path.expanduser("~/Documents/fbf-data/combined.json")

def main():
    with open(PATH, "r", encoding="utf-8") as f:
        root = json.load(f)
    data = root.get("data", [])

    out = []
    for g in data:
        m = (g.get("matchup") or "")
        parts = m.split("@")
        if len(parts) != 2:
            out.append(g); continue
        away, home = parts[0].strip(), parts[1].strip()
        g["away_team"] = away
        g["home_team"] = home

        # Use team-specific spreads if present (preferred)
        hs = g.get("home_spread")
        as_ = g.get("away_spread")
        if isinstance(hs, (int,float)) and hs < 0:
            g["favorite_team"], g["dog_team"], g["fav_spread"] = home, away, float(hs)
        elif isinstance(as_, (int,float)) and as_ < 0:
            g["favorite_team"], g["dog_team"], g["fav_spread"] = away, home, float(as_)
        else:
            # Legacy single spread; DO NOT GUESS. Leave explicit fields empty
            # so the UI won’t infer incorrectly.
            g.pop("favorite_team", None)
            g.pop("dog_team", None)
            g.pop("fav_spread", None)

        out.append(g)

    root["data"] = out
    bk = PATH.replace(".json", "_backup_before_tag.json")
    with open(bk, "w", encoding="utf-8") as f: json.dump(root, f, indent=2)
    with open(PATH, "w", encoding="utf-8") as f: json.dump(root, f, indent=2)
    print(f"✅ Wrote explicit favorites (team-level spreads only) to {PATH}")
    print(f"🟡 Backup: {bk}")

if __name__ == "__main__":
    main()

