#!/usr/bin/env python3
"""
train_model.py

Trains 3 models:
- SU (favorite wins)
- ATS (favorite covers)
- OU (over)

Uses historical_results.json for labels.
Safe if history empty.
"""

import os, json
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from joblib import dump
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from feature_engineering import build_feature_rows

HIST_FILE = "historical_results.json"
MODELS_DIR = "models"

FEATURES = [
    "spread","total","is_home_fav",
    "home_injuries","away_injuries",
    "temp_c","wind_kph","precip_mm",
    "ref_home_win_pct","ref_over_pct","ref_fav_cover_pct"
]

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    os.makedirs(MODELS_DIR, exist_ok=True)
    history = load_json(HIST_FILE, {}).get("data", [])
    if not history:
        print("⚠️ No historical results yet. Skipping training.")
        return

    hist_by_id = {h.get("event_id"): h for h in history if h.get("event_id")}
    rows = build_feature_rows()

    labeled = []
    for r in rows:
        h = hist_by_id.get(r["event_id"])
        if not h:
            continue
        if h.get("fav_score") is None or h.get("dog_score") is None:
            continue
        labeled.append({
            **r,
            "y_su": 1 if h.get("fav_score",0) > h.get("dog_score",0) else 0,
            "y_ats": 1 if h.get("fav_cover") else 0,
            "y_ou": 1 if h.get("over") else 0 if h.get("over") is not None else None
        })

    df = pd.DataFrame(labeled).dropna(subset=["y_su","y_ats"])
    if len(df) < 50:
        print(f"⚠️ Not enough labeled games yet ({len(df)}). Need ~50+.")
        return

    X = df[FEATURES].astype(float)

    def train_one(target, name):
        y = df[target].astype(int)
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=200))
        ])
        model.fit(X_train, y_train)
        acc = model.score(X_test, y_test)

        dump(model, os.path.join(MODELS_DIR, f"{name}.joblib"))
        print(f"✅ Trained {name} model — holdout acc {acc:.3f}")

        return acc

    acc_su = train_one("y_su", "su")
    acc_ats = train_one("y_ats", "ats")

    if df["y_ou"].notna().sum() > 30:
        df_ou = df.dropna(subset=["y_ou"])
        X_ou = df_ou[FEATURES].astype(float)
        y_ou = df_ou["y_ou"].astype(int)
        X_train, X_test, y_train, y_test = train_test_split(X_ou, y_ou, test_size=0.2, random_state=42)
        model_ou = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=200))
        ])
        model_ou.fit(X_train, y_train)
        acc_ou = model_ou.score(X_test, y_test)
        dump(model_ou, os.path.join(MODELS_DIR, "ou.joblib"))
        print(f"✅ Trained ou model — holdout acc {acc_ou:.3f}")

    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "games_labeled": len(df),
        "features": FEATURES,
    }
    with open(os.path.join(MODELS_DIR, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

if __name__ == "__main__":
    main()
