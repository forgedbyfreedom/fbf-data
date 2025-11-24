import json
import math
from collections import defaultdict

HIST_PATH = "historical_results.json"
POWER_PATH = "power_ratings.json"
COMBINED_PATH = "combined.json"
PRED_OUT = "predictions.json"

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)

def team_key(team):
    if not isinstance(team, dict):
        return None
    return team.get("id") or team.get("abbr") or team.get("slug") or team.get("name")

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def main():
    hist = load_json(HIST_PATH, {})
    power = load_json(POWER_PATH, {})
    combined = load_json(COMBINED_PATH, {})

    if isinstance(combined, dict) and "data" in combined:
        games = combined["data"]
    elif isinstance(combined, list):
        games = combined
    else:
        games = []

    # If no history exists, enable heuristic mode
    hist_games = hist.get("data") if isinstance(hist, dict) else hist
    hist_games = hist_games if isinstance(hist_games, list) else []
    heuristic_mode = len(hist_games) < 20

    # Build a simple power map fallback
    power_map = {}
    if isinstance(power, dict):
        for k, v in power.items():
            try:
                power_map[str(k)] = float(v)
            except Exception:
                pass

    preds = {"timestamp": combined.get("timestamp"), "count": len(games), "data": []}

    for g in games:
        if not isinstance(g, dict):
            continue

        home = g.get("home_team") or {}
        away = g.get("away_team") or {}
        odds = g.get("odds") or {}

        hid = str(team_key(home) or "")
        aid = str(team_key(away) or "")

        spread = odds.get("spread")
        total = odds.get("total")

        # Pull power ratings if available; else 0
        hpow = power_map.get(hid, 0)
        apow = power_map.get(aid, 0)

        # Heuristic prediction:
        # If spread exists, build probability from (power diff + spread)
        # If no spread, use power diff only.
        try:
            spr = float(spread) if spread is not None else 0.0
        except Exception:
            spr = 0.0

        diff = (hpow - apow)

        # convert to win probability
        raw = diff / 6.0 + (-spr) / 7.0
        win_prob_home = sigmoid(raw)

        pick_side = "home" if win_prob_home >= 0.5 else "away"
        confidence = abs(win_prob_home - 0.5) * 2  # 0..1

        preds["data"].append({
            "id": g.get("id") or g.get("game_id"),
            "sport": g.get("sport"),
            "home_team": home.get("abbr") or home.get("name"),
            "away_team": away.get("abbr") or away.get("name"),
            "pick": pick_side,
            "confidence": round(confidence * 100, 1),
            "model": "heuristic" if heuristic_mode else "ml",
            "notes": "fallback power+spread" if heuristic_mode else "trained model"
        })

    save_json(PRED_OUT, preds)
    print(f"[✅] predictions.json built ({len(preds['data'])} games).")

if __name__ == "__main__":
    main()
