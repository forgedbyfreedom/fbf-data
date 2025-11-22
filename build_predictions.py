#!/usr/bin/env python3
"""
build_predictions.py

Creates predictions.json:
- Rule-based baseline predictions
- ML-enhanced predictions (if models available)

Safe:
✔ If models missing → rule-only predictions
✔ If features missing → skip gracefully
"""

import os, json, math
from datetime import datetime, timezone

import numpy as np
from joblib import load

from feature_engineering import build_feature_rows, FEATURES

OUTFILE = "predictions.json"
MODELS_DIR = "models"


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def load_model(name):
    """Load ML model safely."""
    path = os.path.join(MODELS_DIR, f"{name}.joblib")
    if os.path.exists(path):
        try:
            return load(path)
        except Exception:
            print(f"⚠️ Could not load model: {path}")
            return None
    return None


def clamp(x, lo=0, hi=100):
    """Keep predictions between 0–100%."""
    return max(lo, min(hi, x))


def safe_float(x, default=0.0):
    """Convert safely to float."""
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return default
        return float(x)
    except Exception:
        return default


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    # Build feature rows
    rows = build_feature_rows()
    if not rows:
        print("⚠️ No feature rows produced — writing empty predictions.json")
        with open(OUTFILE, "w") as f:
            json.dump({"timestamp": ts, "count": 0, "data": []}, f, indent=2)
        return

    # Load ML models
    su_m  = load_model("su")
    ats_m = load_model("ats")
    ou_m  = load_model("ou")

    data = []

    for r in rows:

        spread = safe_float(r.get("spread"), 0.0)
        total  = safe_float(r.get("total"), None)

        # -------------------------------
        # RULE BASELINE
        # -------------------------------
        rule_su = 50 + min(18, abs(spread) * 2.0)
        rule_su = rule_su if spread < 0 else 100 - rule_su
        rule_su = clamp(rule_su)

        rule_ats = 52  # baseline ATS edge
        rule_ou  = 52 if total else None

        # -------------------------------
        # ML PREDICTION
        # -------------------------------

        # Build feature vector in stable order
        try:
            X = np.array([[safe_float(r[f]) for f in FEATURES]], dtype=float)
        except Exception as e:
            print("⚠️ Feature mismatch for:", r.get("matchup"))
            X = None

        ml_su = None
        ml_ats = None
        ml_ou = None

        if X is not None and su_m:
            try:
                ml_su = float(su_m.predict_proba(X)[0, 1]) * 100
            except Exception:
                pass

        if X is not None and ats_m:
            try:
                ml_ats = float(ats_m.predict_proba(X)[0, 1]) * 100
            except Exception:
                pass

        if X is not None and ou_m and total:
            try:
                ml_ou = float(ou_m.predict_proba(X)[0, 1]) * 100
            except Exception:
                pass

        # -------------------------------
        # FINAL PREDICTION (ENSEMBLE)
        # -------------------------------
        su_final  = ml_su  if ml_su  is not None else rule_su
        ats_final = ml_ats if ml_ats is not None else rule_ats
        ou_final  = ml_ou  if ml_ou  is not None else rule_ou

        su_final = clamp(su_final)
        ats_final = clamp(ats_final)
        ou_final = clamp(ou_final) if ou_final is not None else None

        # -------------------------------
        # PICK FORMATTING
        # -------------------------------

        fav = r["fav_team"]
        dog = r["dog_team"]

        # SU
        su_pick = f"{fav} ML" if su_final >= 50 else f"{dog} ML"

        # ATS — ALWAYS display +spread for dog and -spread for fav
        if ats_final >= 50:
