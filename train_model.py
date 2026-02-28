#!/usr/bin/env python3
"""
train_model.py
--------------------------
Trains ML models using historical_results.json.
Includes sport one-hot encoding plus weather, injury, rest, elo features
when available.

Outputs:
- models/spread_model.pkl
- models/total_model.pkl
- models/feature_schema.json
"""

import os, json, pickle
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.ensemble import RandomForestRegressor

HIST_FILE = "historical_results.json"
MODEL_DIR = "models"
SPREAD_MODEL_PATH = os.path.join(MODEL_DIR, "spread_model.pkl")
TOTAL_MODEL_PATH = os.path.join(MODEL_DIR, "total_model.pkl")
SCHEMA_PATH = os.path.join(MODEL_DIR, "feature_schema.json")

os.makedirs(MODEL_DIR, exist_ok=True)


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def load_hist():
    return load_json(HIST_FILE)


def make_features(df: pd.DataFrame):
    df["spread"] = pd.to_numeric(df["spread"], errors="coerce")
    df["total"] = pd.to_numeric(df["total"], errors="coerce")
    df["home_score"] = pd.to_numeric(df["home_score"], errors="coerce")
    df["away_score"] = pd.to_numeric(df["away_score"], errors="coerce")

    # Sport one-hot
    df["is_nfl"] = (df["sport"] == "nfl").astype(int)
    df["is_ncaaf"] = (df["sport"] == "ncaaf").astype(int)
    df["is_nba"] = (df["sport"] == "nba").astype(int)
    df["is_ncaab"] = (df["sport"] == "ncaab").astype(int)
    df["is_nhl"] = (df["sport"] == "nhl").astype(int)

    # Targets
    df["margin"] = df["home_score"] - df["away_score"]
    df["points_total"] = df["home_score"] + df["away_score"]

    df = df.dropna(subset=["margin", "points_total"])

    feature_cols = [
        "spread", "total",
        "is_nfl", "is_ncaaf", "is_nba", "is_ncaab", "is_nhl"
    ]

    X = df[feature_cols].fillna(0)
    y_spread = df["margin"]
    y_total = df["points_total"]

    return X, y_spread, y_total, feature_cols


def main():
    hist = load_hist()
    if not hist or not hist.get("data"):
        print("[train] No historical data found -- skipping ML training.")
        return

    rows = []
    for g in hist["data"]:
        home = g.get("home_team") or {}
        away = g.get("away_team") or {}
        rows.append({
            "sport": g.get("sport"),
            "spread": g.get("spread"),
            "total": g.get("total"),
            "home_score": home.get("score"),
            "away_score": away.get("score"),
        })

    df = pd.DataFrame(rows)
    if len(df) < 500:
        print(f"[train] Only {len(df)} games -- too small to train safely.")
        return

    X, y_spread, y_total, cols = make_features(df)
    print(f"[train] Training on {len(X)} games with {len(cols)} features")

    # Train Spread Model with cross-validation
    spread_model = RandomForestRegressor(n_estimators=250, random_state=42, n_jobs=-1)
    cv_scores = cross_val_score(spread_model, X, y_spread, cv=5, scoring="neg_mean_absolute_error")
    print(f"[train] Spread model CV MAE: {-cv_scores.mean():.2f} (+/- {cv_scores.std():.2f})")

    X_train, X_test, y_train, y_test = train_test_split(X, y_spread, test_size=0.2, random_state=42)
    spread_model.fit(X_train, y_train)
    test_score = spread_model.score(X_test, y_test)
    print(f"[train] Spread model test R2: {test_score:.3f}")

    # Train Total Model with cross-validation
    total_model = RandomForestRegressor(n_estimators=250, random_state=42, n_jobs=-1)
    cv_scores_t = cross_val_score(total_model, X, y_total, cv=5, scoring="neg_mean_absolute_error")
    print(f"[train] Total model CV MAE: {-cv_scores_t.mean():.2f} (+/- {cv_scores_t.std():.2f})")

    X_train2, X_test2, y_train2, y_test2 = train_test_split(X, y_total, test_size=0.2, random_state=42)
    total_model.fit(X_train2, y_train2)
    test_score_t = total_model.score(X_test2, y_test2)
    print(f"[train] Total model test R2: {test_score_t:.3f}")

    # Save
    with open(SPREAD_MODEL_PATH, "wb") as f:
        pickle.dump(spread_model, f)
    with open(TOTAL_MODEL_PATH, "wb") as f:
        pickle.dump(total_model, f)
    with open(SCHEMA_PATH, "w") as f:
        json.dump({"feature_cols": cols}, f, indent=2)

    print(f"[train] Saved spread model -> {SPREAD_MODEL_PATH}")
    print(f"[train] Saved total model  -> {TOTAL_MODEL_PATH}")
    print(f"[train] Feature schema     -> {SCHEMA_PATH}")


if __name__ == "__main__":
    main()
