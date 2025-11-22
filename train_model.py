#!/usr/bin/env python3
"""
train_model.py
Optional ML step.
- If we have enough labeled history in performance_log.json + run_history,
  train a simple classifier to predict SU win vs spread & context.

Safe no-op if no data yet.
Outputs: model.pkl
"""

import os, json, joblib
from datetime import datetime, timezone

try:
    import pandas as pd
    from sklearn.model_selection import train_test_split
    from sklearn.ensemble import RandomForestClassifier
except Exception as e:
    print(f"⚠️ sklearn/pandas missing: {e}. Skipping training.")
    raise SystemExit(0)

MODEL_OUT = "model.pkl"

def main():
    if not os.path.exists("combined.json"):
        print("❌ combined.json missing")
        return

    # No labeled dataset yet — placeholder: you’ll extend by storing past game results.
    # For now, just exit safely.
    print("ℹ️ No labeled training dataset implemented yet. Skipping.")
    return

if __name__ == "__main__":
    print(f"[🤖] ML training check at {datetime.now(timezone.utc).isoformat()}")
    main()
