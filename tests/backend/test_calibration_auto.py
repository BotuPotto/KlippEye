"""Release 1.29.0: the camera calibration finds the nozzle by itself (backend/nozzle_finder.py, CameraCalibration.find_tip,
find_all, accept) and the dots that change the toolhead's sizes on the live picture (machine_masks.handles). A fake printer
that moves when told and a fake fisheye camera that draws it; no network, no browser."""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
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
STATE = {"position": [175.0, 175.0, 20.0], "homed": "xyz", "still": False, "markers": [], "detail": None, "decoy": None}
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
    if STATE["detail"]:   # 1.128: a screw head on the toolhead, higher than the tip
        dx, dy, dz = STATE["detail"]
        p, f = px([[x + dx, y + dy, dz]])
        if f[0]:
            c = tuple(int(v) for v in p[0])
            cv2.circle(img, c, 7, (235, 235, 235), -1)
            cv2.line(img, (c[0] - 5, c[1]), (c[0] + 5, c[1]), (20, 20, 20), 2)
            cv2.line(img, (c[0], c[1] - 5), (c[0], c[1] + 5), (20, 20, 20), 2)
    if STATE["decoy"]:   # a reflection on the toolhead that looks like the tip
        dx, dy, dz = STATE["decoy"]
        p, f = px([[x + dx, y + dy, dz]])
        if f[0]:
            cv2.circle(img, tuple(int(v) for v in p[0]), 4, (40, 40, 250), -1)
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
            "print_stats": {"state": "standby"}, "webhooks": {"state": "ready"}}


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

print("== the nozzle found by itself")
try:
    cal.find_tip(targets[1]["id"])
    check("before any tap by hand: refused (tap the nozzle once first)", False)
except ValueError as error:
    check("before any tap by hand: refused (tap the nozzle once first)", "tap the nozzle by hand" in str(error))
cal.goto(targets[0]["id"])
u, v = truth(*STATE["position"][:2])
cal.add_point(targets[0]["id"], u, v)
check("a nozzle tapped by hand keeps the template", cal.has_template() and cal.summary()["template"] is True)
errors = []
for t in targets[1:6]:
    p = cal.find_tip(t["id"])
    tu, tv = truth(*p["machine"][:2])
    errors.append((t["id"], p["found"], round(abs(p["u"] - tu) * W, 1), round(abs(p["v"] - tv) * H, 1)))
check("the other 5 nozzle points found within 3 px of the real tip", all(e[1] and e[2] < 3 and e[3] < 3 for e in errors), errors)
check("... the printer went back to the point each time", STATE["position"][:2] == [targets[5]["x"], targets[5]["y"]], STATE["position"])
check("... and each proposal waits in the draft", len(cal.draft.get("proposals") or {}) == 5 and not any(t["id"] in cal.draft["points"] for t in targets[1:6]))
try:
    cal.find_tip(targets[6]["id"])
    check("a marker point is not looked for (only the nozzle)", False)
except ValueError as error:
    check("a marker point is not looked for (only the nozzle)", "only the nozzle" in str(error))
r = cal.accept([targets[1]["id"]])
check("accept one: it becomes a point, with the position of when it was found", r["accepted"] == [targets[1]["id"]] and cal.draft["points"][targets[1]["id"]]["source"] == "found"
      and cal.draft["points"][targets[1]["id"]]["machine"][:2] == [targets[1]["x"], targets[1]["y"]])
r = cal.accept()
check("accept all: the other four", sorted(r["accepted"]) == sorted(t["id"] for t in targets[2:6]) and not cal.draft.get("proposals"), r)
for t in targets[6:]:   # the markers, by hand
    cal.goto(t["id"])
    uv, _ = cm.project(CAM, [[t["x"], t["y"], t["height"] - STATE["position"][2]]])
    cal.add_point(t["id"], float(uv[0][0]), float(uv[0][1]))
fit = cal.fit()
check("with the points found, the calibration is good", fit["quality"] == "good" and not fit["redo"], (fit["quality"], fit["rms_px"], fit["redo"]))

print("== all at once, in the background")
for t in targets[1:6]:
    cal.forget_point(t["id"])
state = cal.find_all()
end = time.time() + 60
while cal.auto["state"] == "running" and time.time() < end:
    time.sleep(0.05)
check("find_all: done, the 5 nozzle points found", cal.auto["state"] == "done" and cal.auto["found"] == 5 and cal.auto["total"] == 5, cal.auto)
STATE["still"] = True   # a camera that shows always the same picture: the toolhead never seems to move
cal.forget_point(targets[1]["id"])
p = cal.find_tip(targets[1]["id"])
check("a picture that does not change: the toolhead is not seen moving, the whole picture is searched", p["moved"] is False, p)
STATE["still"] = False
cal.reset()
check("starting again forgets the template too", not cal.has_template())

print("== 1.128: nothing printed: the nozzle tip and a detail of the toolhead")
OFFSET = [14.0, -22.0, 32.0]
STATE.update(detail=OFFSET, decoy=[-24.0, 6.0, 18.0])
data3 = tempfile.mkdtemp()
cal3 = cc.CameraCalibration(data3, query, gcode, render, cv2, np)
cal3.set_options("bed")
check("Z moves the bed: the detail of the toolhead is the method by default", cal3.method() == "detail" and cal3.summary()["method"] == "detail")
pairs = cal3.target_list()
check("six places, each with the nozzle tip and the detail, at the same safe height, nothing printed",
      len(pairs) == 12 and [t["kind"] for t in pairs[:2]] == ["nozzle", "detail"] and all(t["z"] == cc.DETAIL_Z for t in pairs) and not cal3.draft.get("markers"),
      [(t["id"], t["kind"]) for t in pairs])


def tip_at(x, y):
    uv, _ = cm.project(CAM, [[x, y, 0.0]])
    return float(uv[0][0]), float(uv[0][1])


def detail_at(x, y):
    uv, _ = cm.project(CAM, [[x + OFFSET[0], y + OFFSET[1], OFFSET[2]]])
    return float(uv[0][0]), float(uv[0][1])


cal3.goto(pairs[0]["id"])
cal3.add_point(pairs[0]["id"], *tip_at(*STATE["position"][:2]))
try:
    cal3.find_all()
    check("the tip alone tapped: find_all refused (the detail too, at the first place)", False)
except ValueError as error:
    check("the tip alone tapped: find_all refused (the detail too, at the first place)", "detail of the toolhead" in str(error), error)
cal3.add_point(pairs[1]["id"], *detail_at(*STATE["position"][:2]))
check("both tapped: the two pictures kept, can find by itself", cal3.can_find() and cal3.template_png("detail") and cal3.template_png("nozzle"))
cal3.find_all()
end = time.time() + 90
while cal3.auto["state"] == "running" and time.time() < end:
    time.sleep(0.05)
check("find_all: the other 10 found (tip and detail together at each place)", cal3.auto["state"] == "done" and cal3.auto["found"] == 10 and cal3.auto["total"] == 10, cal3.auto)
bad = []
for t in pairs[2:]:
    p = cal3.draft["proposals"][t["id"]]
    want = (tip_at if t["kind"] == "nozzle" else detail_at)(*p["machine"][:2])
    if not p["found"] or abs(p["u"] - want[0]) * W > 3 or abs(p["v"] - want[1]) * H > 3:
        bad.append((t["id"], p["found"], round((p["u"] or 0) * W - want[0] * W, 1), round((p["v"] or 0) * H - want[1] * H, 1)))
check("... each within 3 px of the real place: never the reflection that looks like the tip", not bad, bad)
check("... from the third place on, the search was only where the others said", all(cal3.draft["proposals"][t["id"]]["expected"] for t in pairs[4:]))
cal3.accept()
fit = cal3.fit()
check("the calibration from the tips and the detail: good", fit["quality"] == "good" and not fit["redo"], (fit["quality"], fit["rms_px"], fit["redo"]))
check("... and the detail's height over the tip found by the camera (within 3 mm)", all(abs(a - b) < 3.0 for a, b in zip(fit["offset"], OFFSET)), fit["offset"])
probe = [[60.0, 300.0, -20.0], [300.0, 60.0, -20.0], [175.0, 175.0, -20.0]]   # on the bed, 20 mm under the nozzle
got, _ = cm.project(fit, probe)
want, _ = cm.project(CAM, probe)
err = float(np.max(np.linalg.norm((np.array(got) - np.array(want)) * [W, H], axis=1)))
check("... and the bed lands where it is in the picture (within 8 px)", err < 8.0, err)
cal3._picture = lambda: (cv2.imencode(".jpg", cv2.imdecode(np.frombuffer(render(), np.uint8), 1))[1].tobytes(), cv2.imdecode(np.frombuffer(render(), np.uint8), 1))
saved = cal3.save()
check("saved with the method and the offset", saved.get("method") == "detail" and saved.get("offset") and cal3.summary()["saved"]["offset"])
ov = cal3.overlay()
check("the live check draws the detail where it is", ov["detail"] and abs(ov["detail"][0] - detail_at(*STATE["position"][:2])[0]) * W < 6, (ov["detail"], detail_at(*STATE["position"][:2])))

data4 = tempfile.mkdtemp()
cal4 = cc.CameraCalibration(data4, query, gcode, render, cv2, np)
cal4.set_options("bed")
q = cal4.target_list()
for t in q[:4]:   # two places by hand
    cal4.goto(t["id"])
    cal4.add_point(t["id"], *(tip_at if t["kind"] == "nozzle" else detail_at)(*STATE["position"][:2]))
check("predict: two places only (or all in a row): no guess (the picture may be mirrored)", cal4.predict(q[4]) is None)
real = STATE["detail"]
STATE["detail"] = [OFFSET[0] + 60, OFFSET[1], OFFSET[2]]   # the detail gone; something alike far from where it should be
p = cal4.find_tip(q[4]["id"])
STATE["detail"] = real
lost = cal4.draft["proposals"][q[5]["id"]]
check("followed from the place known: the tip found, the detail lost on the way and the look-alike not taken",
      p["found"] and not lost["found"] and lost["lost"], (p, lost))
cal4.goto(q[6]["id"])
cal4.add_point(q[6]["id"], *tip_at(*STATE["position"][:2]))
e = cal4.predict(q[8])
want = tip_at(q[8]["x"], q[8]["y"])
check("predict: three places not in a row: a guess with a window", e and ((e["u"] - want[0]) ** 2 + ((e["v"] - want[1]) * H / W) ** 2) ** 0.5 < 0.15, (e, want))
cal4.set_options(method="markers")
check("switching to the markers: points forgotten, nothing to take until the markers are known", not cal4.draft.get("points") and cal4.method() == "markers" and cal4.target_list() == [])
try:
    cal4.set_options(method="paint")
    check("an unknown method: refused", False)
except ValueError:
    check("an unknown method: refused", True)
STATE.update(detail=None, decoy=None)

print("== the dots of the sizes")
calib = dict(CAM, z_moves="bed")
shape = machine_masks.clean_shape({"x_range": [0, 350]})
dots = {d["key"]: d for d in machine_masks.handles(calib, shape, [175.0, 175.0, 20.0], [0, 350])}
check("the dots: the 4 sides and the top of the toolhead, the upper and lower edge of the gantry", sorted(dots) == sorted(["toolhead.left", "toolhead.right", "toolhead.front", "toolhead.back", "toolhead.top", "gantry.high", "gantry.low"]), sorted(dots))
bigger = machine_masks.clean_shape(dict(shape, toolhead=dict(shape["toolhead"], top=shape["toolhead"]["top"] + 10)))
moved = {d["key"]: d for d in machine_masks.handles(calib, bigger, [175.0, 175.0, 20.0], [0, 350])}["toolhead.top"]
want = [dots["toolhead.top"]["at"][i] + dots["toolhead.top"]["per_mm"][i] * 10 for i in range(2)]
check("per_mm: 10 mm more height moves the top dot by 10 × per_mm", all(abs(moved["at"][i] - want[i]) < 0.002 for i in range(2)), (moved["at"], want))
check("... and the top dot goes up in the picture when the height grows", dots["toolhead.top"]["per_mm"][1] < 0)
left_dots = {d["key"]: d for d in machine_masks.handles(calib, shape, [80.0, 175.0, 20.0], [0, 350])}
right_dots = {d["key"]: d for d in machine_masks.handles(calib, shape, [280.0, 175.0, 20.0], [0, 350])}
check("the gantry's dots are on the side away from the toolhead", left_dots["gantry.high"]["at"][0] > left_dots["toolhead.top"]["at"][0] + 0.2
      and right_dots["gantry.high"]["at"][0] < right_dots["toolhead.top"]["at"][0] - 0.2, (left_dots["gantry.high"]["at"], right_dots["gantry.high"]["at"]))
check("no gantry dots when the gantry is off", not any(k.startswith("gantry") for k in (d["key"] for d in machine_masks.handles(calib, machine_masks.clean_shape({"gantry": {"on": False}}), [175.0, 175.0, 20.0]))))

print("== homing with the markers on the bed (1.29.1)")
import homing_safety as hs  # noqa: E402
TOOL = {"left": 30.0, "right": 30.0, "front": 35.0, "back": 35.0}
p = hs.homing_place({"safe_z_home": {"home_xy_position": "175, 175", "z_hop": "10"}, "stepper_z": {"endstop_pin": "probe:z_virtual_endstop"}, "bltouch": {"x_offset": -40.0, "y_offset": 10.0}})
check("safe_z_home (as a text or a list), with a BLTouch used as Z endstop: its offsets", p["how"] == "safe_z_home" and p["xy"] == [175.0, 175.0] and p["z_hop"] == 10.0 and p["probe"][:3] == ("bltouch", -40.0, 10.0), p)
check("a homing_override: the place cannot be known", hs.homing_place({"homing_override": {}, "safe_z_home": {"home_xy_position": [1, 2]}})["how"] == "override")
check("a Z endstop at the top (the bed goes down): nothing comes near the bed", hs.homing_place({"stepper_z": {"endstop_pin": "PA1", "position_endstop": 300, "position_max": 300}})["how"] == "top")
check("a Beacon homing Z at its own place", hs.homing_place({"beacon": {"x_offset": 0, "y_offset": 20, "home_xy_position": [150, 150]}, "stepper_z": {"endstop_pin": "probe:z_virtual_endstop"}})["xy"] == [150.0, 150.0])
check("no safe_z_home: where X and Y end their homing", hs.homing_place({"stepper_x": {"position_endstop": 350}, "stepper_y": {"position_endstop": 350}, "stepper_z": {"endstop_pin": "PA1", "position_endstop": 0, "position_max": 300}})["xy"] == [350.0, 350.0])
usual = camera_markers.marker_positions(MIN, MAX)
pos, moved = hs.safe_layout(MIN, MAX, {"xy": [175.0, 175.0]}, TOOL)
check("homing at the centre: the usual grid is clear, nothing moved", pos == usual and not moved)
spot = {"xy": [usual[0][0], usual[0][1]]}   # homing right where the first pyramid would be
pos, moved = hs.safe_layout(MIN, MAX, spot, TOOL)
check("homing where a pyramid would be: another grid, symmetric about the centre, none under the toolhead", moved and not hs.hits(pos, hs.footprints(spot, TOOL))
      and abs(sum(x for x, _ in pos) / 6 - 175.0) < 0.1 and abs(sum(y for _, y in pos) / 6 - 175.0) < 0.1, pos)
probe_spot = {"xy": [175.0, 175.0], "probe": ("bltouch", usual[1][0] - 175.0, usual[1][1] - 175.0, 8.0)}
check("a probe whose offset puts it on a pyramid: that is a hit too", [h_[2] for h_ in hs.hits(usual, hs.footprints(probe_spot, TOOL))] == ["probe"])
check("check(): a hit, with no z_hop and Z not homed also the warning about the height", [r["kind"] for r in hs.check({"safe_z_home": {"home_xy_position": spot["xy"]}}, [list(u_) + [10] for u_ in usual], TOOL, "")] == ["hit", "no_hop"])
check("check(): with z_hop and the usual layout: safe", hs.check({"safe_z_home": {"home_xy_position": [175, 175], "z_hop": 10}}, [list(u_) + [10] for u_ in usual], TOOL, "") == [])

STATE["homed"] = ""
data2 = tempfile.mkdtemp()
SCRIPTS.clear()
cal2 = cc.CameraCalibration(data2, query, gcode, render, cv2, np)
cal2.set_options("bed", method="markers")
SETTINGS["safe_z_home"] = {"home_xy_position": [usual[0][0], usual[0][1]], "z_hop": 10.0}
cal2._settings = (0.0, None)
cal2._set_markers({"source": "file", "points": [list(u_) + [10.0] for u_ in usual]})   # printed with the old, usual grid
try:
    cal2.home()
    check("home() with a pyramid where Z is homed: refused, with the risk", False)
except cc.HomingRisk as risk:
    check("home() with a pyramid where Z is homed: refused, with the risk", [r["kind"] for r in risk.risks] == ["hit"] and risk.risks[0]["x"] == usual[0][0] and not any("G28" in sc for sc in SCRIPTS), risk.risks)
cal2.home(force=True)
check("... home(force) after the person checked: G28, and the motors kept on (idle timeout 3600)", SCRIPTS[-1] == "G28" and "SET_IDLE_TIMEOUT TIMEOUT=3600" in SCRIPTS, SCRIPTS)
SETTINGS["idle_timeout"] = {"timeout": 900}
cal2.reset()
check("... and Klipper's own idle timeout put back at the end", SCRIPTS[-1] == "SET_IDLE_TIMEOUT TIMEOUT=600", SCRIPTS[-2:])
cal2._settings = (0.0, None)
stl_positions, moved = cal2.marker_layout()
check("the STL now keeps the pyramids away from that homing point", moved and not hs.hits(stl_positions, hs.footprints({"xy": SETTINGS["safe_z_home"]["home_xy_position"]}, cal2.get_shape()["toolhead"])))
stl = cal2.markers_stl()
check("... the STL is made at those positions", len(stl) == 84 + 36 * 50 and abs(np.frombuffer(stl[84 + 12:84 + 24], "<f4")[0] - (stl_positions[0][0] - camera_markers.PYRAMID_BASE / 2)) < 0.01, np.frombuffer(stl[84 + 12:84 + 24], "<f4").tolist())
cal2._set_markers({"source": "blobs", "points": [list(u_) + [0.6] for u_ in usual]})
check("blobs on the bed (0.6 mm): nothing to hit", cal2.homing_risks()[0] == [])
STATE["homed"] = "xyz"

print("\n%d FAIL" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
