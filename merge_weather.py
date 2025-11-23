import json
import os

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def main():
    games = load_json("combined.json", [])
    raw = load_json("weather_raw.json", {})
    risk = load_json("weather_risk1.json", {})

    out = []

    for g in games:

        # SAFETY: combined.json is corrupted at top with "timestamp", "count", "data"
        if not isinstance(g, dict):
            print(f"[⚠️] Skipping non-game entry: {g}")
            continue

        gid = g.get("game_id") or g.get("id")
        if not gid:
            print(f"[⚠️] Skipping entry without ID: {g}")
            continue

        # Merge fields
        g["weather"] = raw.get(gid, {})
        g["weatherRisk"] = risk.get(gid, {})

        # Merge tags
        existing = set(g.get("flags") or [])
        new = set(g["weatherRisk"].get("tags") or [])
        g["flags"] = sorted(list(existing | new))

        out.append(g)

    with open("combined.json", "w") as f:
        json.dump(out, f, indent=2)

    print(f"[✅] Weather merged into combined.json ({len(out)} valid games).")

if __name__ == "__main__":
    main()
