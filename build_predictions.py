#!/usr/bin/env python3
"""
build_predictions.py
---------------------
Runs prediction model over combined.json and outputs predictions.json
"""

import json
from pathlib import Path
from predictions_model import predict

COMBINED = Path("combined.json")
OUTFILE = Path("predictions.json")


def load_json(path, default=None):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default


def main():
    combined = load_json(COMBINED, {})
    if not combined or "data" not in combined:
        print("❌ combined.json missing or invalid")
        return

    output = {
        "timestamp": combined.get("timestamp"),
        "count": 0,
        "predictions": [],
    }

    for g in combined["data"]:
        p = predict(g)

        result = {
            "id": g.get("id"),
            "sport": g.get("sport"),
            "matchup": g.get("name"),
            "home": g.get("home_team", {}).get("abbr"),
            "away": g.get("away_team", {}).get("abbr"),
            "odds": g.get("odds", {}),
            "weather": g.get("weather"),
            "risk": g.get("weatherRisk"),
            "prediction": p,
        }

        # Highlight strong edges
        if p["confidence"] >= 70:
            result["highlight"] = True

        output["predictions"].append(result)

    output["count"] = len(output["predictions"])

    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"✅ Predictions generated for {output['count']} games.")


if __name__ == "__main__":
    main()
