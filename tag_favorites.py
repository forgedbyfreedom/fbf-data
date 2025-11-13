#!/usr/bin/env python3
import json, os, datetime

# All league JSON files we standardize
DATA_FILES = [
    "nfl.json", "ncaaf.json", "ncaab.json", "ncaaw.json",
    "mlb.json", "nhl.json", "mixedmartialarts.json"
]

def load_json(path):
    if not os.path.exists(path):
        return {"data": []}
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump({
            "timestamp": datetime.datetime.utcnow().strftime("%Y%m%d_%H%M"),
            "data": data
        }, f, indent=2)

def process_game(game):
    """
    Convert ESPN odds into clean format:

      favorite: "Team -X.X"
      underdog: "Team +X.X"
      total: number

    Spread is never stored separately.
    We always attach the spread to team names.
    """

    away = game.get("away_team")
    home = game.get("home_team")

    # Extract spread consistently
    spread = None
    for key in ["fav_spread", "spread", "spread_full"]:
        if isinstance(game.get(key), (int, float)):
            spread = float(game.get(key))

    # Extract O/U total
    total = None
    if isinstance(game.get("total"), (int, float)):
        total = float(game.get("total"))

    # Determine favorite/underdog
    if spread is not None:
        # Negative = favorite
        if spread < 0:
            # ESPN sometimes stores favorite_team
            fav_team = game.get("favorite_team")
            if fav_team == home:
                favorite = f"{home} {spread}"
                underdog = f"{away} +{abs(spread)}"
            else:
                favorite = f"{away} {spread}"
                underdog = f"{home} +{abs(spread)}"
        else:
            # If ESPN gives positive spread, we invert
            favorite = f"{away} -{abs(spread)}"
            underdog = f"{home} +{abs(spread)}"
    else:
        # No odds provided → give 0 spread but still fill fields
        favorite = f"{home} -0.0"
        underdog = f"{away} +0.0"

    return {
        "sport_key": game.get("sport_key"),
        "matchup": game.get("matchup"),
        "home_team": home,
        "away_team": away,
        "favorite": favorite,
        "underdog": underdog,
        "total": total,
        "commence_time": game.get("commence_time"),
        "book": game.get("book"),
        "fetched_at": game.get("fetched_at")
    }

def main():
    print(f"[🏈] Tagging favorites at {datetime.datetime.utcnow().isoformat()}Z...")

    combined = []

    for filename in DATA_FILES:
        source = load_json(filename)
        processed = [process_game(game) for game in source.get("data", [])]

        save_json(filename, processed)
        combined.extend(processed)
        print(f"[💾] Saved → {filename} ({len(processed)} games)")

    save_json("combined.json", combined)
    print("[💾] Saved → combined.json")
    print("[✅] Tagging complete.")

if __name__ == "__main__":
    main()

