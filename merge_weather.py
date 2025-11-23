#!/usr/bin/env python3
import json

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def main():
    combined = load_json("combined.json", {})
    games = combined.get("data") or []   # ✅ NEW FORMAT

    raw = load_json("weather_raw.json", {})
    risk = load_json("weather_risk1.json", {})

    out_games = []

    for g in games:
        if not isinstance(g, dict):
            continue

        gid = g.get("id") or g.get("game_id")
        if not gid:
            continue

        g["weather"] = raw.get(gid, {})
        g["weatherRisk"] = risk.get(gid, {})

        existing = set(g.get("flags") or [])
        new = set(g["weatherRisk"].get("tags") or [])
        g["flags"] = sorted(list(existing | new))

        out_games.append(g)

    combined["data"] = out_games
    combined["count"] = len(out_games)

    with open("combined.json", "w") as f:
        json.dump(combined, f, indent=2)

    print(f"[✅] Weather merged into combined.json ({len(out_games)} games).")

if __name__ == "__main__":
    main()
