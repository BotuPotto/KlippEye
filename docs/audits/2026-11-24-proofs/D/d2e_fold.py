import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""D2 cause: in the «good» fits of d2b (sigma 1 px), is the lens function r(theta) folding back (not monotonic) inside
the angles the bed is seen at? Prints, per fit, the fold angle and the widest angle of a bed point."""
import os, sys, math
sys.path.insert(0, os.path.join(os.environ.get("KE_ROOT", ROOT + ""), "backend"))
import numpy as np
import camera_model as cm
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "d2b_bed_grid.py")).read().split("diag = ")[0]
exec(src)
folded = 0
for seed in range(20):
    taps = truth_px + np.random.default_rng(seed).normal(0, 1.0, truth_px.shape)
    fit = cm.fit(frame, taps, W, H)
    p = np.array(fit["params"]); rot = cm.rodrigues(p[5:8]); c = bed[seen] @ rot.T + p[8:11]
    ang = np.arctan2(np.hypot(c[:, 0], c[:, 1]), c[:, 2])
    x = ang if fit["model"] == "fisheye" else np.tan(np.minimum(ang, 1.55))
    xs = np.linspace(0, x.max(), 2000)
    k1, k2 = p[3], p[4]
    d = 1 + 3 * k1 * xs ** 2 + 5 * k2 * xs ** 4
    fold = xs[np.argmax(d <= 0)] if np.any(d <= 0) else None
    folded += fold is not None
    err = np.max(np.linalg.norm((cm.project(fit, bed)[0] - tuv) * [W, H], axis=1)[seen])
    print("seed %2d %-7s k1 %+.3f k2 %+.3f  fold %s  widest bed %.2f  max err %.0f px" % (seed, fit["model"], k1, k2, "%.2f" % fold if fold is not None else "none", x.max(), err))
print("%d of 20 fits fold back inside the bed's angles" % folded)
