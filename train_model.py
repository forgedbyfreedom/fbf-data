#!/usr/bin/env python3
"""
train_model.py

Trains 3 models:
- SU (favorite wins)
- ATS (favorite covers)
- OU (over hits)

This version is fully hardened:
✔ Safe if historical data missing
✔ Safe if some features missing
✔ Computes ATS labels correctly
✔ Avoids OU label errors
✔ Automatically handles indoor stadiums
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from joblib import dump
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from feature_engineering import build_feature_rows, FEATURES

HIST_FILE = "historical_results.json"
MODELS_DIR = "models"


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_float(x, default=None):
    """Convert safely to float."""
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return default
        return float(x)
    except Exception:
        return default


def compute_ats_label(fav_score, dog_score, spread):
    """
    True ATS result:
      If favorite - spread > underdog → favorite covered
    """
    if fav_score is None or dog_score is None:
        return None
    if spread is None:
        return None

    fav_adj = fav_score + spread
    return 1 if fav_adj > dog_score else 0


def compute_ou_label(fav_score, dog_score, total):
    """1 if game went over."""
    if fav_score is None or dog_score is None:
        return None
    if total is None:
        return None

    return 1 if (fav_score + dog_score) > total else 0


# ---------------------------------------------------------
# MAIN TRAINING LOGIC
# ---------------------------------------------------------

def main():
    print("🔧 Starting ML training...")
    os.makedirs(MODELS_DIR, exist_ok=True)

    hist_payload = load_json(HIST_FILE, {})
    history = hist_payload.get("data", [])

    if not history:
        print("⚠️ No historical results.json → skipping ML training.")
        return

    # Map event_id → result row
    hist_lookup = {
        h.get("event_id"): h for h in history if h.get("event_id")
    }

    # Build features from today's combined.json
    rows = build_feature_rows()
    if not rows:
        print("⚠️ No feature rows. Cannot train.")
        return

    labeled_rows = []

    for r in rows:
        evt = r.get("event_id")
        if evt not in hist_lookup:
            continue

        h = hist_lookup[evt]
        fav_score = safe_float(h.get("fav_score"))
        dog_score = safe_float(h.get("dog_score"))

        if fav_score is None or dog_score is None:
            continue

        spread = safe_float(r.get("spread"))
        total = safe_float(r.get("total"))

        ats = compute_ats_label(fav_score, dog_score, spread)
        ou = compute_ou_label(fav_score, dog_score, total)
        su = 1 if fav_score > dog_score else 0

        labeled_rows.append({
            **r,
            "y_su": su,
            "y_ats": ats,
            "y_ou": ou
        })

    # Convert to dataframe
    df = pd.DataFrame(labeled_rows)

    # Drop rows missing required labels
    df = df.dropna(subset=["y_su", "y_ats"])
    if df.empty:
        print("⚠️ No labeled samples → Cannot train ML models yet.")
        return

    if len(df) < 40:
        print(f"⚠️ Only {len(df)} labeled games → skipping training (need ~40+).")
        return

    # Ensure all features exist
    missing = [f for f in FEATURES if f not in df.columns]
    for m in missing:
        print(f"⚠️ Missing feature '{m}' — filling with 0.")
        df[m] = 0.0

    X = df[FEATURES].astype(float)

    def train_one(label, name):
        print(f"\n📘 Training model: {name} ...")

        if label not in df:
            print(f"⚠️ Missing label {label} → skipping")
            return None

        sub = df.dropna(subset=[label])
        if len(sub) < 40:
            print(f"⚠️ Not enough samples for {name} ({len(sub)}) → skipping.")
            return None

        Xs = sub[FEATURES].astype(float)
        ys = sub[label].astype(int)

        X_train, X_test, y_train, y_test = train_test_split(
            Xs, ys, test_size=0.22, random_state=42
        )

        model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(
                max_iter=800,
                solver="lbfgs",
                n_jobs=-1
            ))
        ])

        model.fit(X_train, y_train)

        acc = model.score(X_test, y_test)
        print(f"✅ {name} model accuracy: {acc:.3f}")

        outpath = os.path.join(MODELS_DIR, f"{name}.joblib")
        dump(model, outpath)
        print(f"💾 Saved model → {outpath}")

        return acc

    # Train 3 models
    acc_su = train_one("y_su", "su")
    acc_ats = train_one("y_ats", "ats")
    acc_ou = train_one("y_ou", "ou")

    # Write metadata
    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "samples": len(df),
        "features": FEATURES,
        "acc_su": acc_su,
        "acc_ats": acc_ats,
        "acc_ou": acc_ou
    }

    with open(os.path.join(MODELS_DIR, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n🎉 ML Training complete! {len(df)} labeled samples used.")
    print(f"📁 Models saved under: {MODELS_DIR}/")


if __name__ == "__main__":
    main()
