import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Release 1.29.0: the camera calibration finds the nozzle by itself (backend/nozzle_finder.py, CameraCalibration.find_tip,
find_all, accept) and the dots that change the toolhead's sizes on the live picture (machine_masks.handles). A fake printer
that moves when told and a fake fisheye camera that draws it; no network, no browser."""
import os
import sys
import tempfile
import time

HERE = os.path.join(os.environ.get("KE_ROOT", ROOT + ""), "tests", "backend")
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(ROOT, "backend"), os.path.join(HERE, "stubs")]
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import camera_model as cm  # noqa: E402
import camera_calibration as cc  # noqa: E402
import camera_markers  # noqa: E402
import machine_masks  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   -> " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


W, H = 1280, 720


def look_at(cam, target):
    fwd = np.asarray(target, float) - cam
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    rot = np.stack([right, np.cross(fwd, right), fwd])
    return rot, -rot @ cam


ROT, T = look_at(np.array([175.0, -70.0, 110.0]), [175.0, 210.0, -60.0])
CAM = {"model": "fisheye", "width": W, "height": H, "params": [W / 3.0, W / 2 + 12, H / 2 - 8, 0.02, -0.01] + list(cm.rotation_to_vector(ROT)) + list(T)}
BACK = cv2.GaussianBlur((np.random.default_rng(5).random((H, W)) * 120 + 40).astype(np.uint8), (7, 7), 0)
STATE = {"position": [175.0, 175.0, 20.0], "homed": "xyz", "still": False, "markers": []}
MIN, MAX = [0.0, 0.0, 0.0], [350.0, 350.0, 300.0]


def px(points):
    uv, front = cm.project(CAM, points)
    return (uv * [W, H]).astype(np.int32), front


def render():
    img = cv2.cvtColor(BACK, cv2.COLOR_GRAY2BGR)
    x, y, z = STATE["position"] if not STATE["still"] else [175.0, 175.0, 20.0]
    edge = [[a, b, -z] for a, b in [(0, 0), (350, 0), (350, 350), (0, 350)]]
    ring = []
    for i in range(4):
        for s in np.linspace(0, 1, 20):
            ring.append(np.array(edge[i]) + (np.array(edge[(i + 1) % 4]) - np.array(edge[i])) * s)
    pts, front = px(ring)
    cv2.fillPoly(img, [pts[front]], (60, 70, 120))
    for mx, my, mh in STATE["markers"]:
        p, f = px([[mx, my, mh - z]])
        if f[0]:
            cv2.circle(img, tuple(int(c) for c in p[0]), 5, (60, 220, 90), -1)
    outline = cm.box_outline(CAM, cm.box_corners(x - 30, x + 30, y - 35, y + 35, 1, 70))
    if outline:
        cv2.fillPoly(img, [(np.array(outline) * [W, H]).astype(np.int32)], (30, 30, 30))
    p, f = px([[x, y, 0.0]])
    if f[0]:
        cv2.circle(img, tuple(int(c) for c in p[0]), 4, (40, 40, 255), -1)
    return cv2.imencode(".jpg", img)[1].tobytes()


SCRIPTS = []


def gcode(script, timeout=30):
    SCRIPTS.append(script)
    relative = False
    for line in script.splitlines():
        words = line.split()
        if not words:
            continue
        if words[0] == "G90":
            relative = False
        elif words[0] == "G91":
            relative = True
        elif words[0] in ("G0", "G1"):
            pos = list(STATE["position"])
            for w in words[1:]:
                axis = "XYZ".find(w[0])
                if axis >= 0:
                    pos[axis] = pos[axis] + float(w[1:]) if relative else float(w[1:])
            STATE["position"] = pos


SETTINGS = {"printer": {"kinematics": "corexy"}, "z_tilt": {}, "safe_z_home": {"home_xy_position": [175.0, 175.0], "z_hop": 10.0}}


def query(objects):
    if objects.startswith("configfile"):
        return {"configfile": {"settings": SETTINGS}}
    return {"toolhead": {"position": STATE["position"] + [0], "homed_axes": STATE["homed"], "axis_minimum": MIN + [0], "axis_maximum": MAX + [0]},
            "print_stats": {"state": STATE.get("print", "standby")}, "webhooks": {"state": "ready"}}


def truth(x, y):
    uv, _ = cm.project(CAM, [[x, y, 0.0]])
    return float(uv[0][0]), float(uv[0][1])


cc.SETTLE_S = 0.0
data = tempfile.mkdtemp()
cal = cc.CameraCalibration(data, query, gcode, render, cv2, np)
cal.set_options("bed", method="markers")
markers = [[x, y, 10.0] for x, y in camera_markers.marker_positions(MIN, MAX)]
cal._set_markers({"source": "file", "points": markers})
STATE["markers"] = markers
targets = cal.target_list()
