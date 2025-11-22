#!/usr/bin/env python3
"""
build_predictions.py  (ADVANCED + FIXED)

Creates predictions.json with:
- Rule-based baseline (always available)
- ML overlay if models exist in /models
- Confidence grades (low/med/high)
- Explainability for LR-style models (coef * value)
- Debug snapshot of feature inputs per game

Inputs (best-effort):
- combined.json (required for games via feature_engineering)
- weather.json
- referee_trends.json
- injuries.json
- models/su.joblib, models/ats.joblib, models/ou.joblib (optional)

Safe if any inputs/models missing.
"""

import os
import json
import math
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import numpy as np
from joblib import load

# feature_engineering.py must define:
# - FEATURES: list of feature names in correct order
# - build_feature_rows(): list of dict rows
try:
    from feature_engineering import build_feature_rows, FEATURES
except Exception:
    FEATURES = []
    def build_feature_rows():
        return []

OUTFILE = "predictions.json"
MODELS_DIR = "models"


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def load_model(name: str):
    """Load a model from models/{name}.joblib if present."""
    path = os.path.join(MODELS_DIR, f"{name}.joblib")
    if not os.path.exists(path):
        return None
    try:
        return load(path)
    except Exception:
        return None


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def safe_float(x, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def grade(conf: Optional[float]) -> Optional[str]:
    if conf is None:
        return None
    if conf < 56:
        return "low"
    if conf < 70:
        return "med"
    return "high"


def model_explain_lr(model, X_row: np.ndarray, feature_names: List[str]):
    """
    If model is LogisticRegression or Pipeline ending with LR,
    return top +/- contributions by coef * value.
    """
    try:
        clf = model
        # unwrap sklearn Pipeline if present
        if hasattr(model, "named_steps") and "clf" in model.named_steps:
            clf = model.named_steps["clf"]

        if not hasattr(clf, "coef_"):
            return None

        coefs = clf.coef_[0]
        vals = X_row[0]
        contrib = coefs * vals

        idx = np.argsort(np.abs(contrib))[::-1][:6]
        out = []
        for i in idx:
            out.append({
                "feature": feature_names[i],
                "value": float(vals[i]),
                "coef": float(coefs[i]),
                "contribution": float(contrib[i]),
            })
        return out
    except Exception:
        return None


# ---------------------------------------------------------
# Rule baselines
# ---------------------------------------------------------

def rule_baseline_su(spread: Optional[float], is_home_fav: Optional[float]) -> float:
    """
    SU baseline:
      - logistic-ish curve on abs(spread)
      - slight home favorite bump
    Assumes spread is from favorite POV (negative for favorite).
    """
    if spread is None:
        return 50.0

    s = abs(spread)

    # 0 -> 50%, 7 -> ~64%, 14 -> ~74%
    base = 50.0 + (24.0 * (1.0 - math.exp(-s / 6.5)))

    # If spread positive, that means dog is favored in our schema
    if spread > 0:
        base = 100.0 - base

    if is_home_fav:
        base += 2.0

    return clamp(base)


def rule_baseline_ats(spread: Optional[float]) -> float:
    """
    ATS baseline:
      - closer spreads slightly favor chalk
      - big spreads reduce confidence
    """
    if spread is None:
        return 52.0
    s = abs(spread)
    base = 54.0 - min(6.0, s * 0.35)
    return clamp(base)


def rule_baseline_ou(
    total: Optional[float],
    temp: Optional[float],
    wind: Optional[float],
    precip: Optional[float],
) -> Optional[float]:
    """
    OU baseline:
      - wind/precip lower over likelihood
      - warm temps slightly help overs
    """
    if total is None:
        return None

    base = 52.0

    if wind is not None:
        base -= min(5.0, wind * 0.08)

    if precip is not None:
        base -= min(4.0, precip * 0.9)

    if temp is not None:
        if temp >= 18:
            base += 2.0
        elif temp <= 2:
            base -= 2.0

    return clamp(base)


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    rows = build_feature_rows()
    if not rows:
        payload = {
            "timestamp": ts,
            "count": 0,
            "features_used": FEATURES,
            "models_present": {"su": False, "ats": False, "ou": False},
            "data": [],
            "note": "No feature rows produced (combined.json empty or missing)."
        }
        with open(OUTFILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print("⚠️ No feature rows → empty predictions.json")
        return

    su_m = load_model("su")
    ats_m = load_model("ats")
    ou_m = load_model("ou")

    data: List[Dict[str, Any]] = []

    for r in rows:
        # -------------------------
        # Extract features safely
        # -------------------------
        spread = safe_float(r.get("spread"))
        total = safe_float(r.get("total"))

        is_home_fav = safe_float(r.get("is_home_fav"), 0.0) or 0.0

        temp_c = safe_float(r.get("temp_c"))
        wind_kph = safe_float(r.get("wind_kph"))
        precip_mm = safe_float(r.get("precip_mm"))

        # -------------------------
        # RULE BASELINES
        # -------------------------
        rule_su = rule_baseline_su(spread, is_home_fav)
        rule_ats = rule_baseline_ats(spread)
        rule_ou = rule_baseline_ou(total, temp_c, wind_kph, precip_mm)

        # -------------------------
        # ML OVERLAY (if models exist)
        # -------------------------
        ml_su = ml_ats = ml_ou = None
        su_explain = ats_explain = ou_explain = None

        if FEATURES:
            X = np.array([[safe_float(r.get(f), 0.0) for f in FEATURES]], dtype=float)

            if su_m:
                try:
                    ml_su = float(su_m.predict_proba(X)[0, 1]) * 100.0
                    su_explain = model_explain_lr(su_m, X, FEATURES)
                except Exception:
                    ml_su = None

            if ats_m:
                try:
                    ml_ats = float(ats_m.predict_proba(X)[0, 1]) * 100.0
                    ats_explain = model_explain_lr(ats_m, X, FEATURES)
                except Exception:
                    ml_ats = None

            if ou_m and total is not None:
                try:
                    ml_ou = float(ou_m.predict_proba(X)[0, 1]) * 100.0
                    ou_explain = model_explain_lr(ou_m, X, FEATURES)
                except Exception:
                    ml_ou = None

        # -------------------------
        # ENSEMBLE / FINAL
        # If ML exists, blend 70/30 ML/rule.
        # -------------------------
        def blend(rule_v: Optional[float], ml_v: Optional[float]) -> Optional[float]:
            if rule_v is None and ml_v is None:
                return None
            if ml_v is None:
                return rule_v
            if rule_v is None:
                return ml_v
            return clamp(0.7 * ml_v + 0.3 * rule_v)

        su_final = blend(rule_su, ml_su) or rule_su
        ats_final = blend(rule_ats, ml_ats) or rule_ats
        ou_final = blend(rule_ou, ml_ou) if rule_ou is not None else None

        fav_team = r.get("fav_team")
        dog_team = r.get("dog_team")

        # -------------------------
        # Picks
        # -------------------------
        su_pick = f"{fav_team} ML" if su_final >= 50 else f"{dog_team} ML"

        ats_pick = None
        if spread is not None:
            if ats_final >= 50:
                ats_pick = f"{fav_team} {spread:+g}"
            else:
                ats_pick = f"{dog_team} {(-spread):+g}"

        ou_pick = None
        if total is not None and ou_final is not None:
            ou_pick = ("Over" if ou_final >= 50 else "Under") + f" {total:g}"

        entry: Dict[str, Any] = {
            "event_id": r.get("event_id"),
            "matchup": r.get("matchup"),
            "sport_key": r.get("sport_key"),
            "commence_time": r.get("commence_time"),

            "fav_team": fav_team,
            "dog_team": dog_team,
            "spread": spread,
            "total": total,

            # Final outputs
            "SU_conf": round(su_final, 1),
            "ATS_conf": round(ats_final, 1),
            "OU_conf": round(ou_final, 1) if ou_final is not None else None,

            "SU_grade": grade(su_final),
            "ATS_grade": grade(ats_final),
            "OU_grade": grade(ou_final) if ou_final is not None else None,

            "SU_pick": su_pick,
            "ATS_pick": ats_pick,
            "OU_pick": ou_pick,

            # Source breakdown
            "source_rule": {
                "SU_conf": round(rule_su, 1),
                "ATS_conf": round(rule_ats, 1),
                "OU_conf": round(rule_ou, 1) if rule_ou is not None else None,
            },
            "source_ml": {
                "SU_conf": round(ml_su, 1) if ml_su is not None else None,
                "ATS_conf": round(ml_ats, 1) if ml_ats is not None else None,
                "OU_conf": round(ml_ou, 1) if ml_ou is not None else None,
            },

            # Explainability (if LR)
            "explain": {
                "SU_top_features": su_explain,
                "ATS_top_features": ats_explain,
                "OU_top_features": ou_explain,
            },

            # Debug snapshot
            "debug_features": {f: safe_float(r.get(f), 0.0) for f in FEATURES} if FEATURES else None,
        }

        data.append(entry)

    payload = {
        "timestamp": ts,
        "count": len(data),
        "features_used": FEATURES,
        "models_present": {
            "su": bool(su_m),
            "ats": bool(ats_m),
            "ou": bool(ou_m),
        },
        "data": data,
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {OUTFILE} ({len(data)} predictions)")


if __name__ == "__main__":
    main()
