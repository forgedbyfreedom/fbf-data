import json
import math


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


def team_key(team_obj):
    if not isinstance(team_obj, dict):
        return None
    return (team_obj.get("abbr") or team_obj.get("slug") or team_obj.get("name") or "").strip().upper()


def logistic(x):
    return 1 / (1 + math.exp(-x))


def sport_home_adv(sport):
    s = (sport or "").lower()
    if s in ("nfl", "ncaaf"):
        return 2.2
    if s in ("nba", "ncaab"):
        return 2.0
    if s == "nhl":
        return 1.2
    if s == "mlb":
        return 0.5
    return 1.5


def main():
    combined_raw = load_json("combined.json", [])
    combined_obj, games = normalize_combined(combined_raw)

    ratings = load_json("power_ratings.json", {})
    if isinstance(ratings, dict) and "teams" in ratings:
        ratings = ratings["teams"]

    picks_available = 0

    for g in games:
        if not isinstance(g, dict):
            continue

        sport = g.get("sport")
        odds = g.get("odds") or {}
        spread = odds.get("spread")

        home = team_key(g.get("home_team"))
        away = team_key(g.get("away_team"))

        hr = ratings.get(home) if isinstance(ratings, dict) else None
        ar = ratings.get(away) if isinstance(ratings, dict) else None

        pred = {}

        if hr is not None and ar is not None and spread is not None:
            try:
                hr = float(hr)
                ar = float(ar)
                spread = float(spread)
            except Exception:
                hr = ar = spread = None

        if hr is not None and ar is not None and spread is not None:
            # Expected margin home minus away (ratings scale)
            exp_margin = (hr - ar) + sport_home_adv(sport)

            # win prob based on margin scale (tune divisor slightly)
            win_prob_home = logistic(exp_margin / 6.5)

            # ATS edge vs spread
            # ESPN spread is "favorite -X" in details, but spread field already +/-.
            # If spread is negative, home favored; if positive, away favored.
            # We'll compute implied margin for home as (-spread)
            implied_home_margin = -spread
            edge_pts = exp_margin - implied_home_margin

            pick_side = None
            confidence = None

            if abs(edge_pts) >= 2.0:
                if edge_pts > 0:
                    pick_side = "HOME_ATS"
                    confidence = win_prob_home
                else:
                    pick_side = "AWAY_ATS"
                    confidence = 1 - win_prob_home

            if pick_side:
                picks_available += 1
                pred = {
                    "expectedMargin": round(exp_margin, 2),
                    "edgePts": round(edge_pts, 2),
                    "pickSide": pick_side,
                    "confidence": round(confidence, 3),
                    "recommendedTeam": g["home_team"]["abbr"] if pick_side == "HOME_ATS" else g["away_team"]["abbr"]
                }

        g["prediction"] = pred

    combined_obj["data"] = games
    combined_obj["count"] = len(games)
    save_json("combined.json", combined_obj)

    save_json("predictions.json", combined_obj)
    print(f"✅ predictions.json built ({len(games)} games). Picks available: {picks_available}")


if __name__ == "__main__":
    main()
