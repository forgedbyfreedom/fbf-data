#!/usr/bin/env python3
"""
train_model.py
--------------------------
Trains real ML models using historical_results.json.

Outputs:
- models/spread_model.pkl
- models/total_model.pkl
- models/feature_schema.json

If historical file too small, it skips safely.
"""

import os, json, pickle, math
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor

HIST_FILE = "historical_results.json"
MODEL_DIR = "models"
SPREAD_MODEL_PATH = os.path.join(MODEL_DIR, "spread_model.pkl")
TOTAL_MODEL_PATH = os.path.join(MODEL_DIR, "total_model.pkl")
SCHEMA_PATH = os.path.join(MODEL_DIR, "feature_schema.json")

os.makedirs(MODEL_DIR, exist_ok=True)

def load_hist():
    if not os.path.exists(HIST_FILE):
        return None
    with open(HIST_FILE, "r") as f:
        return json.load(f)

def make_features(df: pd.DataFrame):
    # Basic features only; you can expand later.
    df["spread"] = pd.to_numeric(df["spread"], errors="coerce")
    df["total"]  = pd.to_numeric(df["total"], errors="coerce")
    df["home_score"] = pd.to_numeric(df["home_score"], errors="coerce")
    df["away_score"] = pd.to_numeric(df["away_score"], errors="coerce")

    df["is_nfl"]   = (df["sport"] == "nfl").astype(int)
    df["is_ncaaf"] = (df["sport"] == "ncaaf").astype(int)
    df["is_nba"]   = (df["sport"] == "nba").astype(int)
    df["is_ncaab"] = (df["sport"] == "ncaab").astype(int)
    df["is_nhl"]   = (df["sport"] == "nhl").astype(int)

    # Targets:
    # spread target = (home_score - away_score)
    df["margin"] = df["home_score"] - df["away_score"]
    df["points_total"] = df["home_score"] + df["away_score"]

    # Remove rows missing targets
    df = df.dropna(subset=["margin", "points_total"])

    feature_cols = [
        "spread", "total",
        "is_nfl", "is_ncaaf", "is_nba", "is_ncaab", "is_nhl"
    ]

    X = df[feature_cols].fillna(0)
    y_spread = df["margin"]
    y_total  = df["points_total"]

    return X, y_spread, y_total, feature_cols

def main():
    hist = load_hist()
    if not hist or not hist.get("data"):
        print("⚠️ No historical data found — skipping ML training.")
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
        print(f"⚠️ Only {len(df)} games in historical file — too small to train safely.")
        return

    X, y_spread, y_total, cols = make_features(df)

    # Train Spread Model
    X_train, X_test, y_train, y_test = train_test_split(X, y_spread, test_size=0.2, random_state=42)
    spread_model = RandomForestRegressor(n_estimators=250, random_state=42, n_jobs=-1)
    spread_model.fit(X_train, y_train)

    # Train Total Model
    X_train2, X_test2, y_train2, y_test2 = train_test_split(X, y_total, test_size=0.2, random_state=42)
    total_model = RandomForestRegressor(n_estimators=250, random_state=42, n_jobs=-1)
    total_model.fit(X_train2, y_train2)

    with open(SPREAD_MODEL_PATH, "wb") as f:
        pickle.dump(spread_model, f)
    with open(TOTAL_MODEL_PATH, "wb") as f:
        pickle.dump(total_model, f)
    with open(SCHEMA_PATH, "w") as f:
        json.dump({"feature_cols": cols}, f, indent=2)

    print(f"[✅] Trained spread model → {SPREAD_MODEL_PATH}")
    print(f"[✅] Trained total model  → {TOTAL_MODEL_PATH}")
    print(f"[✅] Feature schema saved → {SCHEMA_PATH}")

if __name__ == "__main__":
    main()
