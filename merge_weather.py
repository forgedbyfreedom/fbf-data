import json
import os

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default


def main():
    combined = load_json("combined.json", {})
    games = combined.get("data", [])  # <-- NEW STRUCTURE
    raw = load_json("weather_raw.json", {})
    risk = load_json("weather_risk1.json", {})

    out = []

    for g in games:

        if not isinstance(g, dict):
            print(f"[⚠️] Skipping non-game entry: {g}")
            continue

        gid = g.get("game_id") or g.get("id")
        if not gid:
            print(f"[⚠️] Skipping entry without ID: {g}")
            continue

        g["weather"] = raw.get(gid, {})
        g["weatherRisk"] = risk.get(gid, {})

        existing = set(g.get("flags") or [])
        new = set(g["weatherRisk"].get("tags") or [])
        g["flags"] = sorted(list(existing | new))

        out.append(g)

    combined["data"] = out  # <-- write back to new structure

    with open("combined.json", "w") as f:
        json.dump(combined, f, indent=2)

    print(f"[✅] Weather merged into combined.json ({len(out)} games).")


if __name__ == "__main__":
    main()
