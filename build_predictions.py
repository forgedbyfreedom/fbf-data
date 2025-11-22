#!/usr/bin/env python3
"""
build_predictions.py  (ADVANCED + FIXED)

Creates predictions.json with:
- Rule-based baseline
- ML overlay if models exist
- Confidence grades
- Explainability
- Debug snapshot of feature inputs
"""

import os
import json
import math
from datetime import datetime, timezone
from typing import Optional, List, Dict

import numpy as np
from joblib import load

# feature engine
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
    path = os.path.join(MODELS_DIR, f"{name}.joblib")
    if not os.path.exists(path):
        return None
    try:
        return load(path)
    except Exception:
        return None


def clamp(x: float, lo: float = 0.0, hi: float = 100.0):
    return max(lo, min(hi, x))


def safe_float(x, default=None):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def grade(conf: Optional[float]):
    if conf is None:
        return None
    if conf < 56:
        return "low"
    if conf < 70:
        return "med"
    return "high"


def model_explain_lr(model, X_row, feature_names: List[str]):
    """Return top contributing features if model is LogisticRegression."""
    try:
        clf = model
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
                "contribution": float(contrib[i])
            })
        return out
    except:
        return None


# ---------------------------------------------------------
# Rule baselines
# ---------------------------------------------------------

def rule_baseline_su(spread, is_home_fav):
    if spread is None:
        return clamp(50)

    s = abs(spread)

    base = 50.0 + (24.0 * (1.0 - math.exp(-s / 6.5)))
    if spread > 0:      # dog favored
        base = 100.0 - base

    if is_home_fav:
        base += 2.0

    return clamp(base)


def rule_baseline_ats(spread):
    if spread is None:
        return 52.0
    s = abs(spread)
    return clamp(54.0 - min(6.0, s * 0.35))


def rule_baseline_ou(total, temp_c, wind_kph, precip_mm):
    if total is None:
        return None

    base = 52.0
    if wind_kph:
        base -= min(5.0, wind_kph * 0.08)
    if precip_mm:
        base -= min(4.0, precip_mm * 0.9)
    if temp_c is not None:
        if temp_c >= 18:
            base += 2.0
        elif temp_c <= 2:
            base -= 2.0

    return clamp(base)


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    rows = build_feature_rows()
    if not rows:
        payload = {"timestamp": ts, "count": 0, "data": [], "note": "No feature rows"}
        with open(OUTFILE, "w") as f:
            json.dump(payload, f, indent=2)
        print("⚠️ No feature rows → empty predictions.json")
        return

    su_m = load_model("su")
    ats_m = load_model("ats")
    ou_m = load_model("ou")

    data = []

    for r in rows:
        spread = safe_float(r.get("spread"))
        total = safe_float(r.get("total"))
        is_home_fav = safe_float(r.get("is_home_fav"), 0.0)

        temp_c = safe_float(r.get("temp_c"))
        wind_kph = safe_float(r.get("wind_kph"))
        precip_mm = safe_float(r.get("precip_mm"))

        # RULES
        rule_su = rule_baseline_su(spread, is_home_fav)
        rule_ats = rule_baseline_ats(spread)
        rule_ou = rule_baseline_ou(total, temp_c, wind_kph, precip_mm)

        ml_su = ml_ats = ml_ou = None
        su_explain = ats_explain = ou_explain = None

        if FEATURES:
            X = np.array([[safe_float(r.get(f), 0.0) for f in FEATURES]])

            if su_m:
                try:
                    ml_su = float(su_m.predict_proba(X)[0][1] * 100)
                    su_explain = model_explain_lr(su_m, X, FEATURES)
                except:
                    ml_su = None

            if ats_m:
                try:
                    ml_ats = float(ats_m.predict_proba(X)[0][1] * 100)
                    ats_explain = model_explain_lr(ats_m, X, FEATURES)
                except:
                    ml_ats = None

            if ou_m and total is not None:
                try:
                    ml_ou = float(ou_m.predict_proba(X)[0][1] * 100)
                    ou_explain = model_explain_lr(ou_m, X, FEATURES)
                except:
                    ml_ou = None

        # BLEND (70% ML, 30% rule)
        def blend(rule_v, ml_v):
            if ml_v is None:
                return rule_v
            return clamp(0.7 * ml_v + 0.3 * rule_v)

        su_final = blend(rule_su, ml_su)
        ats_final = blend(rule_ats, ml_ats)
        ou_final = blend(rule_ou, ml_ou) if rule_ou is not None else None

        fav_team = r.get("fav_team")
        dog_team = r.get("dog_team")

        su_pick = f"{fav_team} ML" if su_final >= 50 else f"{dog_team} ML"
        ats_pick = None
        if spread is not None:
            ats_pick = f"{fav_team} {spread:+g}" if ats_final >= 50 else f"{dog_team} {(-spread):+g}"

        ou_pick = None
        if total is not None and ou_final is not None:
            ou_pick = ("Over" if ou_final >= 50 else "Under") + f" {total:g}"

        entry = {
            "event_id": r.get("event_id"),
            "matchup": r.get("matchup"),
            "sport_key": r.get("sport_key"),
            "commence_time": r.get("commence_time"),

            "fav_team": fav_team,
            "dog_team": dog_team,
            "spread": spread,
            "total": total,

            "SU_conf": round(su_final, 1),
            "ATS_conf": round(ats_final, 1),
            "OU_conf": round(ou_final, 1) if ou_final is not None else None,

            "SU_grade": grade(su_final),
            "ATS_grade": grade(ats_final),
            "OU_grade": grade(ou_final) if ou_final is not None else None,

            "SU_pick": su_pick,
            "ATS_pick": ats_pick,
            "OU_pick": ou_pick,

            "source_rule": {
                "SU_conf": round(rule_su, 1),
                "ATS_conf": round(rule_ats, 1),
                "OU_conf": round(rule_ou, 1) if rule_ou is not None else None
            },
            "source_ml": {
                "SU_conf": round(ml_su, 1) if ml_su else None,
                "ATS_conf": round(ml_ats, 1) if ml_ats else None,
                "OU_conf": round(ml_ou, 1) if ml_ou else None
            },

            "explain": {
                "SU_top_features": su_explain,
                "ATS_top_features": ats_explain,
                "OU_top_features": ou_explain,
            },

            "debug_features": {f: safe_float(r.get(f), 0.0) for f in FEATURES} if FEATURES else None
        }

        data.append(entry)

    payload = {
        "timestamp": ts,
        "count": len(data),
        "features_used": FEATURES,
        "models_present": {
            "su": bool(su_m),
            "ats": bool(ats_m),
            "ou": bool(ou_m)
        },
        "data": data
    }

    with open(OUTFILE, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"✅ Wrote predictions.json ({len(data)} games)")


if __name__ == "__main__":
    main()
