import json, os

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default

def main():
    games = load_json("combined.json", [])
    raw = load_json("weather_raw.json", {})
    risk = load_json("weather_risk1.json", {})

    for g in games:
        gid = g.get("game_id") or g.get("id")
        if not gid:
            continue

        g["weather"] = raw.get(gid, {})
        g["weatherRisk"] = risk.get(gid, {})

        # convenience flags at top-level
        tags = set((g["weatherRisk"].get("tags") or []))
        g["flags"] = sorted(list(tags.union(set(g.get("flags") or []))))

    with open("combined.json", "w") as f:
        json.dump(games, f, indent=2)

    print("[✅] Weather merged into combined.json")

if __name__ == "__main__":
    main()
