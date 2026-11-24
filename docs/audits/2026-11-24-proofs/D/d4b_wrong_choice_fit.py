import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof D4b: what the fit rates when the Z choice is wrong (D4's cartesian cube guessed «toolhead»): the 12 toolhead
taps claim frame z 5 and 60, but the nozzle never moves in Z in the frame (the bed does), so the taps of a pair land on
the same pixel. True camera: the fisheye of test_calibration_auto.py; tap noise 1 px."""
import os, sys
sys.path.insert(0, os.path.join(os.environ.get("KE_ROOT", ROOT + ""), "backend"))
import numpy as np
import camera_model as cm
import camera_calibration as cc
W, H = 1280, 720
def look_at(cam, target):
    fwd = np.asarray(target, float) - cam; fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0]); right /= np.linalg.norm(right)
    rot = np.stack([right, np.cross(fwd, right), fwd]); return rot, -rot @ cam
ROT, T = look_at(np.array([175.0, -70.0, 110.0]), [175.0, 210.0, -60.0])
CAM = {"model": "fisheye", "width": W, "height": H, "params": [W / 3.0, W / 2 + 12, H / 2 - 8, 0.02, -0.01] + list(cm.rotation_to_vector(ROT)) + list(T)}
ts = cc.targets("toolhead", [0, 0, 0], [350, 350, 300])
claimed = [[t["x"], t["y"], t["z"]] for t in ts]
real = [[t["x"], t["y"], 0.0] for t in ts]
for seed in range(5):
    px = cm.project(CAM, real)[0] * [W, H] + np.random.default_rng(seed).normal(0, 1.0, (len(real), 2))
    pts = [{"frame": c, "u": p[0] / W, "v": p[1] / H} for c, p in zip(claimed, px)]
    try:
        fit = cm.fit(claimed, px, W, H)
        print("seed %d: %s, rms %.1f px, bed slinger check %s" % (seed, fit["quality"], fit["rms_px"], cc.bed_moves_in_y(pts, H / W)))
    except ValueError as e:
        print("seed %d: refused: %s" % (seed, e))
