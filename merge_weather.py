import json


def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def normalize_combined(combined):
    if isinstance(combined, dict) and "data" in combined:
        return combined, combined["data"]
    if isinstance(combined, list):
        return {"timestamp": None, "count": len(combined), "data": combined}, combined
    return {"timestamp": None, "count": 0, "data": []}, []


def main():
    combined_raw = load_json("combined.json", [])
    combined_obj, games = normalize_combined(combined_raw)

    weather_raw = load_json("weather_raw.json", {})
    risk = load_json("weather_risk1.json", {})

    for g in games:
        if not isinstance(g, dict):
            continue
        gid = g.get("game_id") or g.get("id")
        if not gid:
            continue

        w = weather_raw.get(gid, {})
        r = risk.get(gid, {})

        g["weather"] = w if isinstance(w, dict) else {"error": "bad_weather"}
        g["weatherRisk"] = r if isinstance(r, dict) else {"overallRisk": 0, "error": "bad_risk"}

    combined_obj["count"] = len(games)
    save_json("combined.json", combined_obj)
    print(f"✅ Weather merged into combined.json ({len(games)} games).")


if __name__ == "__main__":
    main()
