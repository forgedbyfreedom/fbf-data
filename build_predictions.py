#!/usr/bin/env python3
"""
build_predictions.py

Creates predictions.json:
- Rule baseline
- ML overlay if models exist

Safe if models missing.
"""

import os, json, math
import numpy as np
from datetime import datetime, timezone
from joblib import load

from feature_engineering import build_feature_rows, FEATURES

OUTFILE = "predictions.json"
MODELS_DIR = "models"

def load_model(name):
    path = os.path.join(MODELS_DIR, f"{name}.joblib")
    if os.path.exists(path):
        try:
            return load(path)
        except Exception:
            return None
    return None

def clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))

def main():
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    rows = build_feature_rows()

    su_m = load_model("su")
    ats_m = load_model("ats")
    ou_m = load_model("ou")

    data = []
    for r in rows:
        spread = r["spread"]
        total = r["total"]

        # -------- Rule baseline (very simple)
        rule_su = 50 + min(18, abs(spread)*2.0)
        rule_su = rule_su if spread < 0 else 100-rule_su

        rule_ats = 52  # neutral baseline
        rule_ou = 52 if total else None

        # -------- ML overlay
        X = np.array([[r[f] for f in FEATURES]], dtype=float)

        ml_su = float(su_m.predict_proba(X)[0,1])*100 if su_m else None
        ml_ats = float(ats_m.predict_proba(X)[0,1])*100 if ats_m else None
        ml_ou = float(ou_m.predict_proba(X)[0,1])*100 if ou_m else None

        # -------- Final ensemble
        su_final = ml_su if ml_su is not None else rule_su
        ats_final = ml_ats if ml_ats is not None else rule_ats
        ou_final = ml_ou if ml_ou is not None else rule_ou

        data.append({
            "event_id": r["event_id"],
            "matchup": r["matchup"],
            "sport_key": r["sport_key"],
            "commence_time": r["commence_time"],
            "fav_team": r["fav_team"],
            "dog_team": r["dog_team"],
            "spread": spread,
            "total": total,

            "SU_conf": round(su_final, 1),
            "ATS_conf": round(ats_final, 1),
            "OU_conf": round(ou_final, 1) if ou_final is not None else None,

            "SU_pick": f"{r['fav_team']} ML" if su_final >= 50 else f"{r['dog_team']} ML",
            "ATS_pick": f"{r['fav_team']} {spread:+g}" if ats_final >= 50 else f"{r['dog_team']} {(-spread):+g}",
            "OU_pick": ("Over" if ou_final and ou_final >= 50 else "Under") + f" {total:g}" if total else None,

            "source_rule": {
                "SU_conf": round(rule_su,1),
                "ATS_conf": round(rule_ats,1),
                "OU_conf": round(rule_ou,1) if rule_ou is not None else None
            },
            "source_ml": {
                "SU_conf": round(ml_su,1) if ml_su is not None else None,
                "ATS_conf": round(ml_ats,1) if ml_ats is not None else None,
                "OU_conf": round(ml_ou,1) if ml_ou is not None else None
            }
        })

    payload = {
        "timestamp": ts,
        "count": len(data),
        "data": data
    }

    with open(OUTFILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"✅ Wrote {OUTFILE} ({len(data)} predictions)")

if __name__ == "__main__":
    main()
