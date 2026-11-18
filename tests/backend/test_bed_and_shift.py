"""Release 1.127: the bed the AI monitor watches (from Klipper's mesh, or set by the person, instead of the toolhead's travel),
a small move of the camera corrected by itself from what stays still in the picture (never from the nozzle), and the same
margin on every side of the parts. No network, no browser: a fake printer and a synthetic picture moved with OpenCV."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(ROOT, "backend"), os.path.join(HERE, "stubs"), os.path.join(ROOT, "scripts")]
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import camera_calibration as cc  # noqa: E402
import camera_model as cm  # noqa: E402
import camera_watch as cw  # noqa: E402
import machine_masks  # noqa: E402
import print_zone  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   -> " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


W, H = 1280, 720
MIN, MAX = [-5.0, -10.0, 0.0], [355.0, 350.0, 340.0]   # the travel goes beyond a 350 x 350 plate (a brush at the back)
SETTINGS = {"printer": {"kinematics": "corexy"}, "bed_mesh": {"mesh_min": [20.0, 25.0], "mesh_max": [330.0, 325.0]}}


def query(objects):
    if objects.startswith("configfile"):
        return {"configfile": {"settings": SETTINGS}}
    return {"toolhead": {"position": [175.0, 175.0, 20.0, 0], "homed_axes": "xyz", "axis_minimum": MIN + [0], "axis_maximum": MAX + [0]},
            "print_stats": {"state": "standby"}, "webhooks": {"state": "ready"}}


def look_at(cam, target):
    fwd = np.asarray(target, float) - cam
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    rot = np.stack([right, np.cross(fwd, right), fwd])
    return rot, -rot @ cam


ROT, T = look_at(np.array([175.0, -120.0, 260.0]), [175.0, 175.0, 0.0])
PARAMS = [900.0, W / 2.0, H / 2.0, 0.0, 0.0] + list(cm.rotation_to_vector(ROT)) + list(T)
SAVED = {"params": PARAMS, "model": "pinhole", "width": W, "height": H, "quality": "good", "z_moves": "toolhead", "rms_px": 3.0, "rms": 0.002,
         "saved": 1700000000}

# ---- the bed from the mesh
check("1.127: the bed from the mesh: its area, 10 mm wider on each side, inside the travel",
      cc.bed_from_mesh(SETTINGS, ([-5, -10], [355, 350])) == [[10.0, 15.0], [340.0, 335.0]], cc.bed_from_mesh(SETTINGS, ([-5, -10], [355, 350])))
check("... a mesh written as text («20, 25»)", cc.bed_from_mesh({"bed_mesh": {"mesh_min": "20, 25", "mesh_max": "330,325"}}) == [[10.0, 15.0], [340.0, 335.0]])
check("... a round bed (mesh_radius)", cc.bed_from_mesh({"bed_mesh": {"mesh_radius": 100, "mesh_origin": "0,0"}}) == [[-110.0, -110.0], [110.0, 110.0]])
check("... no mesh: nothing", cc.bed_from_mesh({}) is None and cc.bed_from_mesh(None) is None)

data = tempfile.mkdtemp()
cal = cc.CameraCalibration(data, query, lambda script: None, lambda: None, cv2, np)
cal.saved = dict(SAVED)
area, source = cal.bed_area()
check("1.127: the watched bed is the mesh's, not the travel", source == "mesh" and area[0] == [10.0, 15.0] and area[1] == [340.0, 335.0], (area, source))
check("... and it is kept for the replay (bed_auto)", json.load(open(os.path.join(data, "machine_shape.json")))["bed_auto"] == [[10.0, 15.0], [340.0, 335.0]])
cal.set_shape({"bed": [[0, 0], [350, 340]]})
check("1.127: set by the person: used as it is", cal.bed_area() == (([0.0, 0.0], [350.0, 340.0]), "person"), cal.bed_area())
check("... the toolhead's sizes are not touched", cal.get_shape()["toolhead"] == machine_masks.DEFAULT_SHAPE["toolhead"])
try:
    cal.set_shape({"bed": [[0, 0], [10, 340]]})
    refused = False
except machine_masks.ShapeError:
    refused = True
check("... a bed narrower than 20 mm is refused", refused and cal.bed_area()[1] == "person")
cal.set_shape({"bed": None})
check("... «Work it out again by itself»: the mesh's again", cal.bed_area()[1] == "mesh")
SETTINGS.pop("bed_mesh")
cal._settings = (0.0, None)
check("... the mesh gone from Klipper: the one kept is used", cal.bed_area() == (([10.0, 15.0], [340.0, 335.0]), "mesh"))
data2 = tempfile.mkdtemp()
cal2 = cc.CameraCalibration(data2, query, lambda script: None, lambda: None, cv2, np)
cal2.saved = dict(SAVED)
check("... no mesh ever: the travel as before", cal2.bed_area() == (([-5.0, -10.0], [355.0, 350.0]), "travel"), cal2.bed_area())
summary = cal.summary()
check("... the page gets the area, where it comes from and the travel", summary["bed"]["source"] == "mesh" and summary["bed"]["travel"] == [[-5.0, -10.0], [355.0, 350.0]])
objects = [{"name": "a", "polygon": [[150, 150], [200, 150], [200, 200], [150, 200]]}]
watched, _, _ = cal.zone_masks(objects, 5.0, 540, 360)
travel_watched, _, _ = print_zone.masks(cv2, np, cal.saved, objects, 5.0, [-5, -10], [355, 350], 540, 360)
check("... the monitor watches less than the whole travel (the brush and the frame left out)", 0 < np.count_nonzero(watched) < np.count_nonzero(travel_watched),
      (np.count_nonzero(watched), np.count_nonzero(travel_watched)))

# ---- the same margin on every side
long_part = [[0, 0], [200, 0], [200, 10], [0, 10]]
grown = print_zone.grow(long_part, 6.0)
xs, ys = [p[0] for p in grown], [p[1] for p in grown]
check("1.127: a long thin part gets the margin on its long sides too (6 mm, not almost nothing)", min(ys) <= -6.0 and max(ys) >= 16.0 and min(xs) <= -6.0 and max(xs) >= 206.0,
      (min(xs), max(xs), min(ys), max(ys)))
check("... and not much more at the corners", min(ys) > -7.0 and max(xs) < 207.0)

# ---- a small move of the camera, corrected from what stays still
rng = np.random.default_rng(3)
scene = np.full((H, W, 3), 60, np.uint8)
for _ in range(260):
    x, y = int(rng.integers(0, W - 40)), int(rng.integers(0, H - 40))
    cv2.rectangle(scene, (x, y), (x + int(rng.integers(8, 40)), y + int(rng.integers(8, 40))), tuple(int(c) for c in rng.integers(0, 255, 3)), -1)
cv2.imwrite(cal.reference_path, scene)


def moved(dx, dy, degrees=0.0):
    matrix = cv2.getRotationMatrix2D((W / 2, H / 2), degrees, 1.0)
    matrix[0, 2] += dx
    matrix[1, 2] += dy
    return cv2.warpAffine(scene, matrix, (W, H), borderMode=cv2.BORDER_REFLECT)


now = {"picture": scene}
cal._picture = lambda: (None, now["picture"])
check("a still camera: ok", cal.check_moved()["state"] == "ok" and cal.usable())
now["picture"] = moved(18, -10, 0.5)
first = cal.check_moved()
check("1.127: moved a little: not corrected at the first look (waits for 3 that agree), not usable meanwhile, looked at again soon",
      first["state"] == "moved" and first.get("waiting") == 1 and not cal.usable() and not cal.saved.get("shift_fix"), first)
cal.check_moved()
third = cal.check_moved()
check("... three looks agree: corrected by itself, usable again, the calibration itself unchanged",
      third["state"] == "corrected" and cal.usable() and cal.saved.get("shift_fix") and cal.saved["params"] == PARAMS, third)
point = [[175.0, 175.0, 0.0], [60.0, 300.0, 0.0]]
plain, _ = cm.project(cal.saved, point)
fixed, _ = cm.project(cal.calibration(), point)
expected = np.array([[u * W, v * H] for u, v in plain.tolist()])
matrix = cv2.getRotationMatrix2D((W / 2, H / 2), 0.5, 1.0)
matrix[0, 2] += 18
matrix[1, 2] -= 10
truth = expected @ matrix[:, :2].T + matrix[:, 2]
error = float(np.max(np.linalg.norm(np.array(fixed) * [W, H] - truth, axis=1)))
check("... the corrected projection lands where the point moved to in the picture (within 3 px)", error < 3.0, error)
check("... the next look that agrees keeps it", cal.check_moved()["state"] == "corrected")
now["picture"] = scene
check("the camera back where it was: the correction goes", cal.check_moved()["state"] == "ok" and not cal.saved.get("shift_fix") and cal.usable())
now["picture"] = moved(18, -10, 0.5)
for _ in range(3):
    cal.check_moved()
cal.undo_correction()
check("1.127: «Do not trust it»: the correction goes and the camera counts as moved (calibrate again)", cal.watch["state"] == "moved" and not cal.usable()
      and not cal.saved.get("shift_fix"))
now["picture"] = moved(120, 70, 0)
for _ in range(3):
    big = cal.check_moved()
check("a big move: never corrected, calibrate again as before", big["state"] == "moved" and not big.get("waiting") and not cal.usable(), big)
now["picture"] = moved(18, -10, 0.5)
cal.check_moved()
now["picture"] = moved(-15, 12, -0.4)
other = cal.check_moved()
check("two small moves that do not agree: counting starts again", other.get("waiting") == 1 and not cal.saved.get("shift_fix"), other)

# ---- the replay knows the bed and the correction
import replay  # noqa: E402
now["picture"] = moved(18, -10, 0.5)
for _ in range(3):
    cal.check_moved()
cc._write_json(cal.path, cal.saved)
masks = replay.load_masks(data)
check("1.127: the replay watches the same bed and uses the correction", masks["limits"] == [[10.0, 15.0], [340.0, 335.0]] and masks["calibration"].get("correction") == cal.saved["shift_fix"]["matrix"],
      (masks["limits"], masks["calibration"].get("correction")))
check("camera_watch: small and agree", cw.small({"state": "moved", "matrix": [[1, 0, 0], [0, 1, 0]], "shift_px": 10, "rotation_deg": 1}) and not cw.small({"state": "moved", "matrix": [[1, 0, 0], [0, 1, 0]], "shift_px": 90, "rotation_deg": 1}))

print("\n%d FAIL" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
