#!/usr/bin/env python3
"""
build_predictions.py

Updated to support new combined.json schema:
{
  "timestamp": "...",
  "count": N,
  "data": [...]
}

Outputs predictions.json
"""

import json
from datetime import datetime, timezone

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def main():
    combined = load_json("combined.json", {})
    games = combined.get("data") or []   # ✅ NEW FORMAT

    if not games:
        print("⚠ No combined.json data.")
        with open("predictions.json", "w") as f:
            json.dump({"timestamp": datetime.now(timezone.utc).isoformat(), "count": 0, "data": []}, f, indent=2)
        return

    # Load model output if present (safe)
    model_preds = load_json("model_predictions.json", {})
    if isinstance(model_preds, dict):
        model_data = model_preds.get("data") or model_preds
    else:
        model_data = {}

    out = []
    for g in games:
        if not isinstance(g, dict):
            continue

        gid = g.get("id") or g.get("game_id")
        if not gid:
            continue

        pred = model_data.get(gid, {})

        out.append({
            "id": gid,
            "sport": g.get("sport"),
            "date_utc": g.get("date_utc"),
            "date_local": g.get("date_local"),

            "home_team": g.get("home_team"),
            "away_team": g.get("away_team"),

            "odds": g.get("odds"),
            "weatherRisk": g.get("weatherRisk"),
            "injuries": g.get("injuries"),

            "prediction": pred
        })

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "count": len(out),
        "data": out
    }

    with open("predictions.json", "w") as f:
        json.dump(payload, f, indent=2)

    print(f"[✅] predictions.json built ({len(out)} games).")

if __name__ == "__main__":
    main()
