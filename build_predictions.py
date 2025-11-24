#!/usr/bin/env python3
"""
build_predictions.py
-------------------------
Loads combined.json and ML models.
Outputs predictions.json with:
- predicted_margin
- predicted_total
- spread_pick
- total_pick
- confidence (simple edge metric)
"""

import os, json, pickle, math
import pandas as pd

COMBINED_FILE = "combined.json"
OUTFILE = "predictions.json"
MODEL_DIR = "models"
SPREAD_MODEL_PATH = os.path.join(MODEL_DIR, "spread_model.pkl")
TOTAL_MODEL_PATH  = os.path.join(MODEL_DIR, "total_model.pkl")
SCHEMA_PATH        = os.path.join(MODEL_DIR, "feature_schema.json")

def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)

def make_feature_row(g):
    sport = g.get("sport")
    odds = g.get("odds") or {}
    spread = odds.get("spread")
    total  = odds.get("total")

    return {
        "spread": spread if spread is not None else 0,
        "total":  total  if total  is not None else 0,
        "is_nfl":   1 if sport=="nfl" else 0,
        "is_ncaaf": 1 if sport=="ncaaf" else 0,
        "is_nba":   1 if sport=="nba" else 0,
        "is_ncaab": 1 if sport=="ncaab" else 0,
        "is_nhl":   1 if sport=="nhl" else 0,
    }

def main():
    combined = load_json(COMBINED_FILE)
    if not combined or not combined.get("data"):
        print("⚠️ combined.json missing or empty.")
        return

    if not os.path.exists(SPREAD_MODEL_PATH) or not os.path.exists(TOTAL_MODEL_PATH):
        print("⚠️ Models missing. Run train_model.py after historical builds.")
        # still write empty preds so dashboard doesn’t break
        with open(OUTFILE, "w") as f:
            json.dump({"timestamp": combined.get("timestamp"), "count": 0, "data": []}, f, indent=2)
        return

    spread_model = pickle.load(open(SPREAD_MODEL_PATH, "rb"))
    total_model  = pickle.load(open(TOTAL_MODEL_PATH, "rb"))
    schema = load_json(SCHEMA_PATH) or {"feature_cols": []}
    cols = schema["feature_cols"]

    preds_out = []
    for g in combined["data"]:
        odds = g.get("odds") or {}
        spread = odds.get("spread")
        total  = odds.get("total")
        fav_details = odds.get("details") or ""
        fav_abbr = fav_details.split(" ")[0] if fav_details else None

        fr = make_feature_row(g)
        X = pd.DataFrame([fr])[cols].fillna(0)

        predicted_margin = float(spread_model.predict(X)[0])
        predicted_total  = float(total_model.predict(X)[0])

        # Determine spread pick based on predicted margin vs line
        spread_pick = None
        confidence = 0.0
        if spread is not None and fav_abbr:
            edge = predicted_margin - float(spread)
            confidence = min(0.95, max(0.05, abs(edge)/10.0))
            if edge > 0:
                spread_pick = fav_abbr
            else:
                # opposite side (dog)
                home_abbr = (g.get("home_team") or {}).get("abbr")
                away_abbr = (g.get("away_team") or {}).get("abbr")
                if fav_abbr == home_abbr:
                    spread_pick = away_abbr
                else:
                    spread_pick = home_abbr

        total_pick = None
        if total is not None:
            if predicted_total > float(total):
                total_pick = "OVER"
            else:
                total_pick = "UNDER"

        preds_out.append({
            "id": g.get("id"),
            "sport": g.get("sport"),
            "predicted_margin": round(predicted_margin, 2),
            "predicted_total": round(predicted_total, 2),
            "spread_pick": spread_pick,
            "total_pick": total_pick,
            "confidence": round(confidence, 3)
        })

    payload = {
        "timestamp": combined.get("timestamp"),
        "count": len(preds_out),
        "data": preds_out
    }

    with open(OUTFILE, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"[✅] predictions.json built ({len(preds_out)} games).")

if __name__ == "__main__":
    main()
