import json, os

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default

def main():
    games = load_json("combined.json", [])
    raw = load_json("weather_raw.json", {})
    risk = load_json("weather_risk1.json", {})  # <-- or weather_risk.json depending what you chose

    out = []

    for g in games:

        # ---------------------------------------
        # SAFETY GUARD — FIXES YOUR ERROR
        # ---------------------------------------
        if not isinstance(g, dict):
            print(f"[⚠️] Skipping corrupted combined.json entry: {g}")
            continue

        gid = g.get("game_id") or g.get("id")
        if not gid:
            print(f"[⚠️] Skipping entry with no game ID: {g}")
            continue

        # Merge weather fields
        g["weather"] = raw.get(gid, {})
        g["weatherRisk"] = risk.get(gid, {})

        # Combine tag sets safely
        existing = set(g.get("flags") or [])
        new = set(g["weatherRisk"].get("tags") or [])
        g["flags"] = sorted(list(existing | new))

        out.append(g)

    with open("combined.json", "w") as f:
        json.dump(out, f, indent=2)

    print(f"[✅] Weather merged into combined.json ({len(out)} games).")

if __name__ == "__main__":
    main()
