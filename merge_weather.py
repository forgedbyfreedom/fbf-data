import json

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)

def main():
    combined = load_json("combined.json", [])
    weather_raw = load_json("weather_raw.json", {})
    weather_risk = load_json("weather_risk1.json", {})

    if isinstance(combined, dict) and "data" in combined:
        data = combined["data"]
    else:
        data = combined

    for g in data:
        if not isinstance(g, dict):
            continue

        gid = g.get("game_id") or g.get("id")
        if not gid:
            continue

        g["weather"] = weather_raw.get(gid, {})
        g["weatherRisk"] = weather_risk.get(gid, {})

    if isinstance(combined, dict) and "data" in combined:
        combined["data"] = data
        save_json("combined.json", combined)
        print(f"[✅] Weather merged into combined.json ({len(data)} games).")
    else:
        save_json("combined.json", data)
        print(f"[✅] Weather merged into combined.json ({len(data)} games).")

if __name__ == "__main__":
    main()
