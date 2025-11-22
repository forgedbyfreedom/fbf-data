#!/usr/bin/env python3
"""
predictions_model.py

Trains ML models for SU / ATS / OU once labeled history exists.

Inputs:
- historical_results.json (YOU add builder later)
- power_ratings.json (optional)
- referee_trends.json (optional)
- weather.json (optional)

Outputs:
- models/su_model.pkl
- models/ats_model.pkl
- models/ou_model.pkl
- models/model_meta.json

Safe if historical_results.json missing.

Dependencies:
- pandas, numpy, scikit-learn, joblib
"""

import json, os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from sklearn.ensemble import RandomForestClassifier
import joblib

HIST_FILE = "historical_results.json"
PR_FILE   = "power_ratings.json"
REF_FILE  = "referee_trends.json"
WX_FILE   = "weather.json"

MODEL_DIR = "models"
META_FILE = os.path.join(MODEL_DIR, "model_meta.json")

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def power_by_team(payload):
    out = {}
    for r in payload.get("data", []):
        tn = (r.get("team_name") or r.get("team") or "").lower()
        if tn:
            out[tn] = float(r.get("rating", 0))
    return out

def main():
    hist = load_json(HIST_FILE, [])
    if not hist:
        os.makedirs(MODEL_DIR, exist_ok=True)
        meta = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trained": False,
            "note": "historical_results.json missing; no training performed"
        }
        with open(META_FILE, "w") as f:
            json.dump(meta, f, indent=2)
        print("⚠️ No historical_results.json — skipping ML training")
        return

    pr = power_by_team(load_json(PR_FILE, {}))

    rows = []
    for r in hist:
        fav = (r.get("favorite_team") or "").lower()
        dog = (r.get("underdog_team") or "").lower()
        spread = float(r.get("fav_spread") or 0)
        total = float(r.get("total") or 0)
        fav_score = r.get("fav_score")
        dog_score = r.get("dog_score")

        if fav_score is None or dog_score is None:
            continue

        pr_edge = pr.get(fav, 0) - pr.get(dog, 0)

        su_label = int(fav_score > dog_score)
        ats_label = int((fav_score - dog_score) > abs(spread))
        ou_label = int((fav_score + dog_score) > total) if total else None

        rows.append({
            "spread": spread,
            "total": total,
            "pr_edge": pr_edge,
            "su_label": su_label,
            "ats_label": ats_label,
            "ou_label": ou_label
        })

    df = pd.DataFrame(rows).dropna(subset=["su_label","ats_label"])
    if df.empty:
        print("⚠️ Not enough labeled rows to train")
        return

    os.makedirs(MODEL_DIR, exist_ok=True)

    features = ["spread","total","pr_edge"]

    # --- SU model ---
    X = df[features]
    y = df["su_label"]
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=7)
    su_model = RandomForestClassifier(n_estimators=300, random_state=7)
    su_model.fit(Xtr, ytr)
    su_acc = accuracy_score(yte, su_model.predict(Xte))
    joblib.dump(su_model, os.path.join(MODEL_DIR, "su_model.pkl"))

    # --- ATS model ---
    y = df["ats_label"]
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=7)
    ats_model = RandomForestClassifier(n_estimators=300, random_state=7)
    ats_model.fit(Xtr, ytr)
    ats_acc = accuracy_score(yte, ats_model.predict(Xte))
    joblib.dump(ats_model, os.path.join(MODEL_DIR, "ats_model.pkl"))

    # --- OU model ---
    df_ou = df.dropna(subset=["ou_label"])
    ou_acc = None
    if not df_ou.empty:
        X = df_ou[features]
        y = df_ou["ou_label"]
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=7)
        ou_model = RandomForestClassifier(n_estimators=300, random_state=7)
        ou_model.fit(Xtr, ytr)
        ou_acc = accuracy_score(yte, ou_model.predict(Xte))
        joblib.dump(ou_model, os.path.join(MODEL_DIR, "ou_model.pkl"))

    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trained": True,
        "rows": len(df),
        "features": features,
        "su_accuracy": round(float(su_acc), 4),
        "ats_accuracy": round(float(ats_acc), 4),
        "ou_accuracy": round(float(ou_acc), 4) if ou_acc is not None else None
    }

    with open(META_FILE, "w") as f:
        json.dump(meta, f, indent=2)

    print("✅ ML models trained & saved to models/")

if __name__ == "__main__":
    main()
