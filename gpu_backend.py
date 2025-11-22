#!/usr/bin/env python3
"""
gpu_backend.py

Auto-detects GPU libraries.
- If CuPy exists -> use it as np
- If cuML exists -> use it for ML
- Otherwise falls back to NumPy / scikit-learn

Usage:
    from gpu_backend import np, ML_BACKEND, is_gpu

    X = np.array(...)
    if ML_BACKEND == "cuml":
        ...
"""

def _try_import(name):
    try:
        mod = __import__(name)
        return mod
    except Exception:
        return None


# ---------- NumPy vs CuPy ----------
cupy = _try_import("cupy")
if cupy is not None:
    np = cupy
    is_gpu = True
else:
    import numpy as np
    is_gpu = False


# ---------- scikit-learn vs cuML ----------
cuml = _try_import("cuml")
if cuml is not None:
    ML_BACKEND = "cuml"
else:
    ML_BACKEND = "sklearn"


def to_cpu(x):
    """Convert CuPy arrays to NumPy safely."""
    if is_gpu:
        return x.get()
    return x
