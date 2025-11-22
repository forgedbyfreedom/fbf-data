#!/usr/bin/env python3
"""
predictions_model.py

Machine-learning training layer.
Safe on a fresh repo:
- If no labeled historical data exists, writes models/model_meta.json and exits.

Expected future labeled data file:
historical_results.json
[
  {
    "sport_key": "...",
    "fav_team": "...",
    "dog_team": "...",
    "spread": -3.5,
    "total": 47.5,
    "fav_score": 24,
    "dog_score": 17
  },
  ...
]

Outputs:
- models/su_model.pkl
- models/ats_model.pkl
- models/ou_model.pkl
- models/model_meta.json
"""

import json, os, pickle
from datetime import datetime, timezone

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression

HIST_FILE = "historical_results.json"
MODELS_DIR = "models"
META_FILE = os.path.join(MODELS_DIR, "model_meta.json")

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def ensure_dir(p):
    if not os.path.exists(p):
        os.makedirs(p, exist_ok=True)

def build_features(rows):
    X_su, y_su = [], []
    X_ats, y_ats = [], []
    X_ou, y_ou = [], []

    for r in rows:
        spread = r.get("spread")
        total = r.get("total")
        fav_score = r.get("fav_score")
        dog_score = r.get("dog_score")

        if spread is None or total is None or fav_score is None or dog_score is None:
            continue

        spread = float(spread)
        total = float(total)
        fav_score = float(fav_score)
        dog_score = float(dog_score)

        # features
        feat = [spread, total]

        # labels
        su = 1 if fav_score > dog_score else 0
        ats = 1 if (fav_score - dog_score) > abs(spread) else 0
        ou = 1 if (fav_score + dog_score) > total else 0

        X_su.append(feat); y_su.append(su)
        X_ats.append(feat); y_ats.append(ats)
        X_ou.append(feat); y_ou.append(ou)

    return (
        np.array(X_su), np.array(y_su),
        np.array(X_ats), np.array(y_ats),
        np.array(X_ou), np.array(y_ou),
    )

def train_one(X, y):
    if len(X) < 50:
        return None, "insufficient_samples"
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    model = LogisticRegression(max_iter=200)
    model.fit(X_train, y_train)
    acc = float(model.score(X_test, y_test))
    return model, acc

def main():
    ensure_dir(MODELS_DIR)
    hist = load_json(HIST_FILE, [])

    if not hist or len(hist) < 50:
        meta = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trained": False,
            "reason": "historical_results.json missing or too small (need 50+ labeled games).",
            "games_available": len(hist) if hist else 0,
            "features": ["spread", "total"],
        }
        with open(META_FILE, "w") as f:
            json.dump(meta, f, indent=2)
        print("⚠️  No ML training performed:", meta["reason"])
        return

    X_su, y_su, X_ats, y_ats, X_ou, y_ou = build_features(hist)

    su_model, su_acc = train_one(X_su, y_su)
    ats_model, ats_acc = train_one(X_ats, y_ats)
    ou_model, ou_acc = train_one(X_ou, y_ou)

    if su_model:
        with open(os.path.join(MODELS_DIR, "su_model.pkl"), "wb") as f:
            pickle.dump(su_model, f)
    if ats_model:
        with open(os.path.join(MODELS_DIR, "ats_model.pkl"), "wb") as f:
            pickle.dump(ats_model, f)
    if ou_model:
        with open(os.path.join(MODELS_DIR, "ou_model.pkl"), "wb") as f:
            pickle.dump(ou_model, f)

    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trained": True,
        "games_used": int(len(X_su)),
        "features": ["spread", "total"],
        "su_accuracy": su_acc if su_model else None,
        "ats_accuracy": ats_acc if ats_model else None,
        "ou_accuracy": ou_acc if ou_model else None,
    }

    with open(META_FILE, "w") as f:
        json.dump(meta, f, indent=2)

    print("✅ ML training complete:", meta)

if __name__ == "__main__":
    main()
