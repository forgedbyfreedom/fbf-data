#!/usr/bin/env python3
"""
build_predictions.py

Reads combined.json and writes predictions.json
Always produces picks for all games.

Also writes a small summary for index.html to display:
- total predictions count
- high confidence pick count
"""

import json
from pathlib import Path
from datetime import datetime, timezone

from predictions_model import predict_games

BASE = Path(__file__).resolve().parent
COMBINED = BASE / "combined.json"
PRED_OUT = BASE / "predictions.json"


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def main():
    if not COMBINED.exists():
        raise FileNotFoundError("combined.json not found")

    combined = load_json(COMBINED)

    preds = predict_games(combined)

    high_conf = sum(1 for p in preds if p.get("high_confidence"))
    total = len(preds)

    out = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "total_games": total,
        "high_confidence": high_conf,
        "data": preds
    }

    with open(PRED_OUT, "w") as f:
        json.dump(out, f, indent=2)

    print(f"[✅] predictions.json built ({total} games, {high_conf} high-confidence).")


if __name__ == "__main__":
    main()
