import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Hypothesis for D2: a weak prior pulling k1, k2 to 0 (extra residuals PRIOR_PX * k1, PRIOR_PX * k2) keeps the bed right.
Monkeypatches camera_model._residuals, then reruns d2c_param.py (TRUE_MODEL / FDIV env as there). PRIOR_PX env, default 200."""
import os, sys
sys.path.insert(0, os.path.join(os.environ.get("KE_ROOT", ROOT + ""), "backend"))
import numpy as np
import camera_model as cm
PRIOR = float(os.environ.get("PRIOR_PX", "200"))
_orig = cm._residuals
cm._residuals = lambda params, points, pixels, model: np.r_[_orig(params, points, pixels, model), PRIOR * params[3], PRIOR * params[4]]
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "d2c_param.py")).read())
