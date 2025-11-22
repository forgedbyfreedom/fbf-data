#!/usr/bin/env python3
"""
gpu_backend.py

Optional GPU/CPU abstraction.
- If cupy is installed and a CUDA device is available, uses GPU arrays.
- Otherwise falls back to numpy.
"""

from __future__ import annotations
import os

BACKEND = "numpy"
xp = None

def _try_cupy():
    global BACKEND, xp
    try:
        import cupy  # type: ignore
        # basic device test
        _ = cupy.zeros((1,))
        xp = cupy
        BACKEND = "cupy"
        return True
    except Exception:
        return False

def _use_numpy():
    global BACKEND, xp
    import numpy
    xp = numpy
    BACKEND = "numpy"

if os.environ.get("FBF_FORCE_CPU", "").lower() in ("1","true","yes"):
    _use_numpy()
else:
    if not _try_cupy():
        _use_numpy()

def backend_name() -> str:
    return BACKEND
