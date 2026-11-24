import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof D2b: like d2, but the error is measured over a 15x15 grid of the whole bed (0..350 mm, frame z 0), only at points
that the true camera sees inside the picture; and inside the tapped area (20..80% x, 25..75% y). Tap noise sigma px."""
import os, sys
sys.path.insert(0, os.path.join(os.environ.get("KE_ROOT", ROOT + ""), "backend"))
import numpy as np
import camera_model as cm
import camera_markers
W, H = 1280, 720
def look_at(cam, target):
    fwd = np.asarray(target, float) - cam; fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0]); right /= np.linalg.norm(right)
    rot = np.stack([right, np.cross(fwd, right), fwd]); return rot, -rot @ cam
ROT, T = look_at(np.array([175.0, -70.0, 110.0]), [175.0, 210.0, -60.0])
CAM = {"model": os.environ.get("TRUE_MODEL","fisheye"), "width": W, "height": H, "params": [W / float(os.environ.get("FDIV","3.0")), W / 2 + 12, H / 2 - 8, 0.02, -0.01] + list(cm.rotation_to_vector(ROT)) + list(T)}
pos = camera_markers.marker_positions([0, 0, 0], [350, 350, 300])
frame = [[x, y, 0.0] for x, y in pos] + [[x, y, 10.0 - 60.0] for x, y in pos]
truth_px = cm.project(CAM, frame)[0] * [W, H]
g = np.linspace(0, 350, 15)
bed = np.array([[x, y, 0.0] for x in g for y in g])
tuv = cm.project(CAM, bed)[0]
seen = np.all((tuv >= 0) & (tuv <= 1), axis=1)
inner = seen & (bed[:, 0] >= 70) & (bed[:, 0] <= 280) & (bed[:, 1] >= 87.5) & (bed[:, 1] <= 262.5)
diag = np.hypot(W, H)
for sigma in (0.0, 1.0, 2.0, 3.0):
    rows = []
    for seed in range(20):
        taps = truth_px + np.random.default_rng(seed).normal(0, sigma, truth_px.shape)
        fit = cm.fit(frame, taps, W, H)
        err = np.linalg.norm((cm.project(fit, bed)[0] - tuv) * [W, H], axis=1)
        rows.append((fit["quality"], fit["model"], fit["rms_px"], np.max(err[inner]), np.max(err[seen])))
    good = [r for r in rows if r[0] == "good"]
    wrong = [r for r in good if r[4] > 0.03 * diag]
    print("sigma %.0f px: %2d/20 good; of those %2d have a seen bed point off > %.0f px; pinhole picked %d/20; "
          "max err inside tapped area median %.0f px, whole seen bed median %.0f px"
          % (sigma, len(good), len(wrong), 0.03 * diag, sum(r[1] == "pinhole" for r in rows),
             np.median([r[3] for r in rows]), np.median([r[4] for r in rows])))
