"""
"Calibrate the camera" (roadmap phase 4): the steps behind the dashboard page, the saved calibration and the check that the
camera has not moved since. The maths is in camera_model.py (the camera) and camera_watch.py (has it moved?).

Coordinates. The camera is fixed to the frame, so the model works in FRAME coordinates (mm):
  * printers where Z moves the toolhead (Voron 2.4, Prusa, Ender...): the nozzle is at (X, Y, Z), the bed at height 0;
  * printers where Z moves the bed (VzBot, Voron Trident, RatRig V-Core...): the nozzle is always at height 0 in the frame
    and the bed surface is at -Z (it goes down as Z grows); a part of height h is at h - Z.
The person says which kind (the page guesses it from Klipper's configuration).

The points (about twelve, at two heights, never all on one plane):
  * Z moves the toolhead: the nozzle tip at a 3x2 grid of the bed, low (Z 5) and high (Z 60 or so): 12 taps;
  * Z moves the bed: six markers on the bed (camera_markers.py: printed pyramids, whose positions are read from the G-code
    that printed them, or quick blobs left by the printer itself); the nozzle tip just above each marker (6 taps, height 0),
    then the bed goes down and the person taps the 6 marker tips (height h - Z): 12 taps.
On disk, in the data folder: camera.json (the saved calibration), camera_draft.json (the points being taken: they survive a
reload of the page), camera_reference.jpg (the picture at calibration time, to notice when the camera moves),
machine_shape.json (the size of the toolhead and of the gantry, adjusted on the live picture: machine_masks.py; it stays when
the camera is calibrated again).
"""
import json
import os
import threading
import time

import camera_markers
import camera_model
import camera_watch
import homing_safety
import machine_masks
import nozzle_finder
import print_zone

Z_MOVES = ("bed", "toolhead")
GRID_X = (0.15, 0.5, 0.85)
GRID_Y = (0.2, 0.8)
LOW_Z_TOOLHEAD = 5.0
HIGH_Z = 60.0
NOZZLE_OVER_MARKER = 3.0   # mm between the nozzle tip and the top of a marker when the nozzle is tapped
MAX_GCODE_BYTES = 50 * 1024 ** 2
TRAVEL_FEED = 6000
Z_FEED = 900
DEFAULT_TOOLHEAD = {"width": 60, "depth": 70, "height": 70}   # mm around the nozzle (box from the tip upwards)
WATCH_EVERY_S = 600
WATCH_SOON_S = 60          # 1.127: while a small move of the camera waits to be confirmed
CORRECT_AFTER = 3          # 1.127: looks in a row that must find the same small move before it is corrected
BUSY_STATES = ("printing", "paused")
FIND_SHIFT = 90.0     # mm the toolhead moves aside while the nozzle is looked for (more than its width: the two do not overlap)
SETTLE_S = 1.2            # after a move, before the picture: the camera's stream is a little late
IDLE_DURING_CALIBRATION_S = 3600   # 1.29.1: the motors stay on this long during the calibration (Klipper's idle timeout)
SETTINGS_TTL_S = 60        # Klipper's configuration is read again after this long
BED_FROM_MESH_MM = 10.0    # 1.127: the bed worked out from the mesh area, this much wider on each side (the probe stays off the edges)


def _pair(value):
    """A Klipper "x, y" setting (a list, or a text "x,y") -> [x, y] or None."""
    if isinstance(value, str):
        value = value.split(",")
    try:
        x, y = (float(v) for v in value)
        return [x, y]
    except (TypeError, ValueError):
        return None


def bed_from_mesh(settings, travel=None):
    """1.127: the bed from Klipper's [bed_mesh] (mesh_min / mesh_max, or mesh_origin and mesh_radius on a round bed), a
    little wider (the probe stays off the edges), inside the travel when known; None without a mesh.
    The travel itself (position_min..max) often goes beyond the plate: a purge bucket, a brush, the frame."""
    mesh = (settings or {}).get("bed_mesh") or {}
    low, high = _pair(mesh.get("mesh_min")), _pair(mesh.get("mesh_max"))
    if (low is None or high is None) and mesh.get("mesh_radius") is not None:
        try:
            radius = float(mesh["mesh_radius"])
            centre = _pair(mesh.get("mesh_origin")) or [0.0, 0.0]
            low, high = [centre[0] - radius, centre[1] - radius], [centre[0] + radius, centre[1] + radius]
        except (TypeError, ValueError):
            return None
    if low is None or high is None or high[0] - low[0] < 10 or high[1] - low[1] < 10:
        return None
    low = [low[0] - BED_FROM_MESH_MM, low[1] - BED_FROM_MESH_MM]
    high = [high[0] + BED_FROM_MESH_MM, high[1] + BED_FROM_MESH_MM]
    if travel:
        low = [max(low[0], travel[0][0]), max(low[1], travel[0][1])]
        high = [min(high[0], travel[1][0]), min(high[1], travel[1][1])]
    return [[round(low[0], 1), round(low[1], 1)], [round(high[0], 1), round(high[1], 1)]]


class HomingRisk(Exception):
    """1.29.1: homing could hit the markers on the bed: `risks` says how (homing_safety.check); the page asks to confirm."""

    def __init__(self, risks):
        Exception.__init__(self, "homing could hit the markers on the bed")
        self.text, self.values, self.risks = "homing could hit the markers on the bed", {}, risks


class NotReady(Exception):
    """The printer cannot do this now (printing, not homed, Klipper not ready): the message says why.
    The text is fixed English (translated by the backend); `values` fill its {placeholders}."""

    def __init__(self, text, **values):
        Exception.__init__(self, text)
        self.text, self.values = text, values


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def guess_z_moves(settings):
    """From Klipper's configuration (configfile.settings): quad_gantry_level = a gantry moving in Z (Voron 2.4);
    z_tilt with a corexy or several Z motors = a bed moving in Z (VzBot, Trident, V-Core); otherwise the toolhead (i3 style)."""
    settings = settings or {}
    if "quad_gantry_level" in settings:
        return "toolhead"
    kinematics = str((settings.get("printer") or {}).get("kinematics", "")).lower()
    if "z_tilt" in settings or "z_tilt_ng" in settings or kinematics in ("corexy", "hybrid_corexy", "corexz"):
        return "bed"
    return "toolhead"


def frame_point(z_moves, x, y, z, kind, height=0.0):
    """Machine position -> frame coordinates. kind "nozzle": the nozzle tip; "mark": the top of a marker `height` mm tall
    on the bed, seen with the machine at Z = z (bed lowered by z when Z moves the bed)."""
    if kind == "mark":
        return [x, y, height - z] if z_moves == "bed" else [x, y, height]
    # "nozzle", and "detail" (1.128): a detail of the toolhead is at an unknown offset from the tip: the tip's place here
    return [x, y, 0.0] if z_moves == "bed" else [x, y, z]


METHODS = ("detail", "markers")   # 1.128: Z moves the bed: a detail of the toolhead (nothing printed), or markers on the bed
DETAIL_Z = 20.0                    # 1.128: the bed this far under the nozzle while the detail points are taken
WALK_PROBE = 4.0                   # 1.128: the first two small moves (mm) that tell how the picture moves per mm
WALK_STEP = 25.0                   # ... then this far at a time towards the next place
WALK_FIRST = 0.025                 # how far (widths of the picture) the point is looked for after the first small moves
WALK_WINDOW = 0.03                 # ... and after each step
WALK_KEEP = 0.7                    # a match this good gives the picture looked for next (how the point looks there)


def _gap(a, b, ratio):
    """The distance between two places in the picture (fractions), in widths of the picture (ratio: height / width)."""
    return ((a[0] - b[0]) ** 2 + ((a[1] - b[1]) * ratio) ** 2) ** 0.5


def targets(z_moves, minimum, maximum, markers=None, method="markers"):
    """The points to take, in order (little travel). Each: id, kind, x, y, z (the machine Z to go to), height (markers).
    Z moves the bed: with method "detail" (1.128) the nozzle tip and a detail of the toolhead at six places, nothing on
    the bed; with "markers", nothing until the markers are known (printed and read from their G-code, or blobs)."""
    x0, y0, x1, y1 = minimum[0], minimum[1], maximum[0], maximum[1]
    xs = [round(x0 + (x1 - x0) * f, 1) for f in GRID_X]
    ys = [round(y0 + (y1 - y0) * f, 1) for f in GRID_Y]
    grid = [(x, y) for y in ys for x in (xs if ys.index(y) % 2 == 0 else list(reversed(xs)))]
    high = round(min(HIGH_Z, max(20.0, (maximum[2] - minimum[2]) * 0.4)), 1)
    out = []
    if z_moves == "toolhead":
        for n, (x, y) in enumerate(grid, 1):
            out.append({"id": "low%d" % n, "kind": "nozzle", "x": x, "y": y, "z": LOW_Z_TOOLHEAD, "step": 1})
        for n, (x, y) in enumerate(reversed(grid), 1):
            out.append({"id": "high%d" % n, "kind": "nozzle", "x": x, "y": y, "z": high, "step": 2})
    elif method == "detail":
        for n, (x, y) in enumerate(grid, 1):
            out.append({"id": "tip%d" % n, "kind": "nozzle", "x": x, "y": y, "z": DETAIL_Z, "step": 1, "pair": n})
            out.append({"id": "feat%d" % n, "kind": "detail", "x": x, "y": y, "z": DETAIL_Z, "step": 1, "pair": n})
    elif markers:
        for n, (x, y, h) in enumerate(markers, 1):
            out.append({"id": "tip%d" % n, "kind": "nozzle", "x": x, "y": y, "z": round(h + NOZZLE_OVER_MARKER, 2), "height": h, "step": 1})
        for n, (x, y, h) in enumerate(markers, 1):
            out.append({"id": "mark%d" % n, "kind": "mark", "x": x, "y": y, "z": high, "height": h, "step": 2})
    return out


class CameraCalibration:
    def __init__(self, data_dir, query, gcode, snapshot, cv2=None, np=None, files=None, read_file=None):
        """query(objects) -> Klipper status dict; gcode(script, timeout) -> raises on failure; snapshot() -> JPEG bytes;
        files() -> [{path, modified, size}] of the G-code files; read_file(path) -> its text."""
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, "camera.json")
        self.draft_path = os.path.join(data_dir, "camera_draft.json")
        self.template_path = os.path.join(data_dir, "camera_tip.png")   # 1.29: the nozzle tip as tapped once, to find it again
        self.detail_path = os.path.join(data_dir, "camera_detail.png")  # 1.128: the detail of the toolhead as tapped once
        self.reference_path = os.path.join(data_dir, "camera_reference.jpg")
        self.query, self.gcode, self.snapshot = query, gcode, snapshot
        self.cv2, self.np = cv2, np
        self.files, self.read_file = files, read_file
        self.lock = threading.RLock()
        self.saved = _read_json(self.path)
        self.shape_path = os.path.join(data_dir, "machine_shape.json")
        self.shape = None
        self._limits = (0.0, None)   # (when read, the X range of the printer) for the gantry
        self.draft = _read_json(self.draft_path) or {}
        self.watch = (self.saved or {}).get("watch") or {"state": "unknown"}
        self.marks = {"state": "idle"}
        self._marks_thread = None
        self.auto = {"state": "idle"}   # 1.29: finding the nozzle at every point by itself
        self._settings = (0.0, None)
        self._idle_was = None   # Klipper's idle timeout before the calibration made it longer
        self._auto_thread = None
        self._auto_stop = False
        self.last_watch = 0.0
        self.moves = []   # 1.127: the looks that found the same small movement, waiting to be confirmed

    # ---------------------------------------------------------------- the printer
    def printer(self):
        status = self.query("toolhead=position,homed_axes,axis_minimum,axis_maximum&print_stats=state&webhooks=state")
        tool = status.get("toolhead") or {}
        return {"state": (status.get("print_stats") or {}).get("state", ""), "klipper": (status.get("webhooks") or {}).get("state", ""),
                "homed": str(tool.get("homed_axes") or ""), "position": [round(float(v), 2) for v in (tool.get("position") or [0, 0, 0])[:3]],
                "minimum": [float(v) for v in (tool.get("axis_minimum") or [0, 0, 0])[:3]],
                "maximum": [float(v) for v in (tool.get("axis_maximum") or [0, 0, 0])[:3]]}

    def _ready_to_move(self, printer):
        if printer["klipper"] and printer["klipper"] != "ready":
            raise NotReady("Klipper is not ready")
        if printer["state"] in BUSY_STATES:
            raise NotReady("the printer is printing")
        if not all(axis in printer["homed"] for axis in "xyz"):
            raise NotReady("home the printer first")
        self._keep_motors()

    def guess(self):
        try:
            settings = self.query("configfile=settings").get("configfile", {}).get("settings", {})
        except Exception:
            settings = {}
        return guess_z_moves(settings)

    # ---------------------------------------------------------------- the draft
    def _save_draft(self):
        _write_json(self.draft_path, self.draft)

    def z_moves(self):
        return self.draft.get("z_moves") or (self.saved or {}).get("z_moves") or None

    def method(self):
        """1.128: how the second height is given when Z moves the bed: "detail" or "markers" (drafts from before: markers)."""
        if self.z_moves() != "bed":
            return None
        return self.draft.get("method") or "markers"

    def set_options(self, z_moves=None, toolhead=None, method=None):
        with self.lock:
            if z_moves is not None:
                if z_moves not in Z_MOVES:
                    raise ValueError("z_moves must be bed or toolhead")
                if z_moves != self.draft.get("z_moves"):
                    self.draft = {"z_moves": z_moves, "points": {}, "toolhead": self.draft.get("toolhead"),
                                  "method": "detail" if z_moves == "bed" else None}   # 1.128: nothing to print by default
            if toolhead is not None:
                clean = {}
                for key in DEFAULT_TOOLHEAD:
                    value = toolhead.get(key, DEFAULT_TOOLHEAD[key])
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 10 <= value <= 300:
                        raise ValueError("the toolhead size must be 10 to 300 mm")
                    clean[key] = float(value)
                self.draft["toolhead"] = clean
            if method is not None:   # 1.128: Z moves the bed: a detail of the toolhead, or markers on the bed
                if method not in METHODS:
                    raise ValueError("the method must be detail or markers")
                if method != self.method():
                    self.draft.update(method=method, points={}, proposals={})
                    self.draft.pop("fit", None)
            self.draft.setdefault("points", {})
            self._save_draft()
            return self.draft

    def reset(self):
        self.restore_idle()
        with self.lock:
            self.draft = {}
            for path in (self.draft_path, self.template_path, self.detail_path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def target_list(self, printer=None):
        z_moves = self.z_moves()
        if not z_moves:
            return []
        printer = printer or self.printer()
        markers = (self.draft.get("markers") or {}).get("points")
        return targets(z_moves, printer["minimum"], printer["maximum"], markers, self.method())

    def _target(self, target_id, printer):
        for t in self.target_list(printer):
            if t["id"] == target_id:
                return t
        raise ValueError("unknown point")

    # ---------------------------------------------------------------- 1.29.1: homing with the markers on the bed
    def settings(self):
        """Klipper's configuration (configfile.settings), read at most once a minute."""
        when, known = self._settings
        if known is None or time.time() - when > SETTINGS_TTL_S:
            try:
                known = self.query("configfile=settings").get("configfile", {}).get("settings", {}) or {}
            except Exception:
                known = known or {}
            self._settings = (time.time(), known)
        return known

    def homing_place(self):
        return homing_safety.homing_place(self.settings())

    def marker_layout(self, printer=None):
        """Where the markers of the STL go: the usual grid, or one that keeps them out of where homing touches.
        -> (positions, moved)."""
        printer = printer or self.printer()
        return homing_safety.safe_layout(printer["minimum"], printer["maximum"], self.homing_place(), self.get_shape()["toolhead"])

    def homing_summary(self, printer):
        """For the page: where Z is homed, whether the markers of the STL were moved away from it, the risks now."""
        place = self.homing_place()
        risks, expected = self.homing_risks(printer)
        moved = self.marker_layout(printer)[1]
        probe = place.get("probe")
        return {"how": place["how"], "xy": place["xy"], "z_hop": place["z_hop"], "probe": {"name": probe[0], "x_offset": probe[1], "y_offset": probe[2]} if probe else None,
                "layout_moved": moved, "risks": risks, "expected": expected}

    def homing_risks(self, printer=None):
        """With the markers on the bed (read from their G-code; else, Z moving the bed, those the STL would print), what
        could go wrong when homing. -> (risks, the markers are only expected)."""
        if self.z_moves() != "bed":
            return [], False
        printer = printer or self.printer()
        markers = (self.draft.get("markers") or {}).get("points")
        expected = not markers
        if expected:
            markers = [[x, y, camera_markers.PYRAMID_HEIGHT] for x, y in self.marker_layout(printer)[0]]
        elif (self.draft.get("markers") or {}).get("source") == "blobs":
            return [], False   # 0.6 mm discs: nothing to hit
        return homing_safety.check(self.settings(), markers, self.get_shape()["toolhead"], printer["homed"]), expected

    def _keep_motors(self):
        """The motors stay on during the calibration (a long idle timeout); restore_idle() puts back Klipper's own."""
        if self._idle_was is not None:
            return
        try:
            was = (self.settings().get("idle_timeout") or {}).get("timeout", 600)
            self.gcode("SET_IDLE_TIMEOUT TIMEOUT=%d" % IDLE_DURING_CALIBRATION_S, 10)
            self._idle_was = int(float(was))
        except Exception as error:
            print("[CAMERA] idle timeout not changed: %s" % error)

    def restore_idle(self):
        if self._idle_was is None:
            return
        try:
            self.gcode("SET_IDLE_TIMEOUT TIMEOUT=%d" % self._idle_was, 10)
        except Exception as error:
            print("[CAMERA] idle timeout not restored: %s" % error)
        self._idle_was = None

    def home(self, force=False):
        printer = self.printer()
        if printer["state"] in BUSY_STATES:
            raise NotReady("the printer is printing")
        risks, expected = self.homing_risks(printer)
        if risks and not force:
            for risk in risks:
                risk["expected"] = expected
            raise HomingRisk(risks)
        self._keep_motors()
        self.gcode("G28", 180)

    def goto(self, target_id):
        """Moves the nozzle to a point (first up, then across, then down: nothing is dragged over the bed)."""
        printer = self.printer()
        self._ready_to_move(printer)
        t = self._target(target_id, printer)
        z_moves = self.z_moves()
        if t["kind"] == "mark":
            # the nozzle out of the way (the back of the bed, high), the bed down: the blobs are visible
            x, y = (printer["minimum"][0] + printer["maximum"][0]) / 2, printer["maximum"][1] - 5
        else:
            x, y = t["x"], t["y"]
        tallest = max([p[2] for p in (self.draft.get("markers") or {}).get("points") or []] + [0.0])
        safe = max(t["z"], printer["position"][2], 10.0, tallest + 5.0)   # travel well above the markers
        script = "G90\nG0 Z%.2f F%d\nG0 X%.2f Y%.2f F%d\nG0 Z%.2f F%d\nM400" % (safe, Z_FEED, x, y, TRAVEL_FEED, t["z"], Z_FEED)
        self.gcode(script, 120)
        with self.lock:
            self.draft["at"] = target_id
            self._save_draft()
        return {"target": t, "z_moves": z_moves}

    def jog(self, dx, dy, dz):
        printer = self.printer()
        self._ready_to_move(printer)
        for d in (dx, dy, dz):
            if not isinstance(d, (int, float)) or isinstance(d, bool) or abs(d) > 50:
                raise ValueError("a step is at most 50 mm")
        self.gcode("G91\nG0 X%.2f Y%.2f F%d\nG0 Z%.2f F%d\nG90\nM400" % (dx, dy, TRAVEL_FEED, dz, Z_FEED), 60)

    def add_point(self, target_id, u, v):
        """The tap: (u, v) fractions of the picture where the nozzle tip (or the blob) is. The machine position is read
        now: it is the real one, even after a nudge by hand. A nozzle tapped by hand also becomes the template that
        finds the nozzle at the other points by itself (1.29)."""
        for value in (u, v):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError("u and v must be fractions of the picture (0..1)")
        printer = self.printer()
        t = self._target(target_id, printer)
        point = self._store_point(t, printer["position"], u, v)
        if t["kind"] in ("nozzle", "detail") and point.get("source") is None:
            self._save_template(u, v, t["kind"])
        return point

    def _store_point(self, t, position, u, v, source="tap"):
        x, y, z = position
        if t["kind"] == "mark":
            x, y = t["x"], t["y"]  # the marker is where it was printed; the nozzle is parked elsewhere
        point = {"kind": t["kind"], "machine": [x, y, z], "frame": frame_point(self.z_moves(), x, y, z, t["kind"], t.get("height", 0.0)),
                 "u": round(u, 5), "v": round(v, 5), "time": int(time.time())}
        if source != "tap":
            point["source"] = source
        with self.lock:
            self.draft.setdefault("points", {})[t["id"]] = point
            (self.draft.get("proposals") or {}).pop(t["id"], None)
            self.draft.pop("fit", None)
            self._save_draft()
        return point

    # ---------------------------------------------------------------- 1.29: the nozzle found by itself
    def _template_path(self, kind="nozzle"):
        return self.detail_path if kind == "detail" else self.template_path

    def _save_template(self, u, v, kind="nozzle"):
        if self.cv2 is None:
            return
        try:
            _, image = self._picture()
            patch = nozzle_finder.template(self.cv2, self.np, image, u, v)
            if patch is not None:
                self.cv2.imwrite(self._template_path(kind), patch)
        except Exception as error:
            print("[CAMERA] template not kept: %s" % error)

    def has_template(self, kind="nozzle"):
        return os.path.isfile(self._template_path(kind))

    def template_png(self, kind="nozzle"):
        """1.128: the small picture tapped first (to show the person which detail to tap again), PNG bytes or None."""
        try:
            with open(self._template_path(kind), "rb") as handle:
                return handle.read()
        except OSError:
            return None

    def can_find(self):
        """Whether the points can be looked for by themselves: the nozzle tapped by hand once (and, with a detail of the
        toolhead, the detail too: 1.128)."""
        return self.has_template("nozzle") and (self.method() != "detail" or self.has_template("detail"))

    # ---------------------------------------------------------------- 1.128: where a point should be, from those taken
    def _known(self):
        """The points taken and the proposals found so far: {id: {"u", "v", "machine", "kind"}}."""
        out = {}
        for pid, p in (self.draft.get("proposals") or {}).items():
            if p.get("found"):
                out[pid] = {"u": p["u"], "v": p["v"], "machine": p["machine"], "kind": p.get("kind")}
        for pid, p in (self.draft.get("points") or {}).items():
            out[pid] = {"u": p["u"], "v": p["v"], "machine": p["machine"], "kind": p["kind"]}
        return out

    def predict(self, t, printer=None):
        """Where the point `t` should appear (fractions) and how far from there it may be: {"u", "v", "radius"} or None.
        From the points of the same kind on the same plane (same machine Z), at least 3 not all in a row: an affine map (the
        window wider when it does not fit them well: a lens that bends). The search is limited to there: a reflection or the background far away cannot be taken."""
        if self.cv2 is None:
            return None
        known = self._known()
        same = [k for pid, k in known.items() if pid != t["id"] and k.get("kind") == t["kind"] and abs(float(k["machine"][2]) - float(t["z"])) < 0.6]
        guess = None
        if len(same) >= 3:   # two, or all in a row: the picture may be mirrored, nothing sure (the step to the detail still is)
            src = self.np.array([[k["machine"][0], k["machine"][1]] for k in same], float)
            dst = self.np.array([[k["u"], k["v"]] for k in same], float)
            spread = self.np.linalg.svd(src - src.mean(axis=0), compute_uv=False)
            if spread[0] > 0 and spread[-1] / spread[0] >= 0.15:
                rows = self.np.hstack([src, self.np.ones((len(src), 1))])
                matrix = self.np.linalg.lstsq(rows, dst, rcond=None)[0]   # an affine map, least squares
                miss = float(self.np.max(self.np.linalg.norm(rows @ matrix - dst, axis=1))) if len(src) > 3 else 0.0
                q = self.np.array([t["x"], t["y"], 1.0]) @ matrix
                guess = {"u": float(q[0]), "v": float(q[1]), "radius": min(0.15, 0.07 + 2 * miss)}
        if guess and not (-0.2 <= guess["u"] <= 1.2 and -0.2 <= guess["v"] <= 1.2):
            return None
        return guess

    def _fresh_picture(self):
        time.sleep(SETTLE_S)
        self.snapshot()   # the stream may still show the moment before: the second picture is the one used
        return self._picture()[1]

    def find_tip(self, target_id):
        """Goes to a nozzle point and looks for the nozzle tip with the template: the toolhead moves aside for a moment
        (to see where it is), then back. -> the proposal {u, v, score, found}, kept in the draft until accepted.
        1.128: only near where the points taken say it should be, or where it was followed to from a place known; with a
        detail of the toolhead, the tip and the detail of the same place are looked for together."""
        if self.cv2 is None:
            raise NotReady("OpenCV is missing on the Raspberry")
        printer = self.printer()
        t = self._target(target_id, printer)
        if t["kind"] not in ("nozzle", "detail"):
            raise ValueError("only the nozzle points can be found by themselves")
        taken = self.draft.get("points") or {}
        group = [t]
        if self.method() == "detail" and t.get("pair"):
            group = [o for o in self.target_list(printer) if o.get("pair") == t["pair"] and (o["id"] == target_id or o["id"] not in taken)]
        patches = {}
        for o in group:
            patch = self.cv2.imread(self._template_path(o["kind"]), self.cv2.IMREAD_GRAYSCALE) if self.has_template(o["kind"]) else None
            if patch is None:
                if self.method() == "detail":
                    raise ValueError("tap the nozzle tip and the detail of the toolhead by hand at the first place: KlippEye then finds both at the others")
                raise ValueError("tap the nozzle by hand at one point first: KlippEye then finds it at the others")
            patches[o["id"]] = patch
        walked = self._walk(group, printer)   # 1.128: followed there from the nearest place known; else where the others say
        expected = {o["id"]: walked.get(o["id"]) or self.predict(o, printer) for o in group}
        self.goto(target_id)
        printer = self.printer()
        position = printer["position"]
        here = self._fresh_picture()
        # two places aside: what changed against BOTH is the toolhead here (against one only, the place it went to counts too)
        (x0, y0), (x1, y1) = printer["minimum"][:2], printer["maximum"][:2]
        # one place on each side when there is room; else two on the same side, far enough apart not to overlap each other
        far = 2 * FIND_SHIFT + 20.0
        spots = [(position[0] + d, position[1]) for d in (FIND_SHIFT, -FIND_SHIFT) if x0 <= position[0] + d <= x1]
        if len(spots) < 2:
            spots += [(position[0] + d, position[1]) for d in (far, -far) if x0 <= position[0] + d <= x1]
        if len(spots) < 2:
            spots += [(position[0], position[1] + d) for d in (FIND_SHIFT, -FIND_SHIFT, far, -far) if y0 <= position[1] + d <= y1]
        aways = []
        for sx, sy in spots[:2]:
            self.gcode("G90\nG0 X%.2f Y%.2f F%d\nM400" % (sx, sy, TRAVEL_FEED), 60)
            aways.append(self._fresh_picture())
        self.gcode("G90\nG0 X%.2f Y%.2f F%d\nM400" % (position[0], position[1], TRAVEL_FEED), 60)
        region = nozzle_finder.toolhead_region(self.cv2, self.np, here, aways)
        results = {o["id"]: self._look(here, (expected[o["id"]] or {}).get("patch", patches[o["id"]]), region, expected[o["id"]]) for o in group}
        now = int(time.time())
        with self.lock:
            for o in group:
                r, e = results[o["id"]], expected[o["id"]]
                self.draft.setdefault("proposals", {})[o["id"]] = {
                    "u": r["u"], "v": r["v"], "score": r["score"], "found": r["found"], "moved": region is not None, "machine": position, "time": now,
                    "kind": o["kind"], "expected": [round(e["u"], 4), round(e["v"], 4), round(e["radius"], 4)] if e else None,
                    "lost": bool(r.get("lost"))}
            self._save_draft()
            return dict(self.draft["proposals"][target_id])

    def _look(self, here, patch, region, expected, strict=False):
        """The template looked for in the toolhead's region, and only near `expected` when given: {u, v, score, found}."""
        if expected and expected.get("lost"):
            return {"u": None, "v": None, "score": 0.0, "found": False, "lost": True}
        if expected:
            window = self.np.zeros(here.shape[:2], self.np.uint8)
            hh, ww = here.shape[:2]
            self.cv2.circle(window, (int(expected["u"] * ww), int(expected["v"] * hh)), max(4, int(expected["radius"] * ww)), 255, -1)
            inside = self.cv2.bitwise_and(region, window) if region is not None else window
            region = inside if (strict or self.cv2.countNonZero(inside)) else window
            if not self.cv2.countNonZero(region):
                return {"u": None, "v": None, "score": 0.0, "found": False}
        near = (expected["u"], expected["v"], expected["radius"]) if expected else None
        result = dict(nozzle_finder.find(self.cv2, self.np, here, patch, region, near))
        if expected and result.get("u") is not None and _gap((result["u"], result["v"]), (expected["u"], expected["v"]), here.shape[0] / float(here.shape[1])) > expected["radius"]:
            result["found"] = False
        return result

    def _walk(self, group, printer):
        """1.128: where the points of `group` (the same place) appear, followed from the nearest place already known a few
        mm at a time: each small move is looked for only next to where the moves before say it went, so a reflection or the
        background a little further away is never taken. -> {id: {"u", "v", "radius"}} for those followed to the end."""
        t = group[0]
        tallest = max([p[2] for p in (self.draft.get("markers") or {}).get("points") or []] + [0.0])
        if self.z_moves() != "bed" and t["z"] < max(10.0, tallest + 5.0):
            return {}   # never dragged across the bed low down
        known = self._known()
        level = (lambda k: True) if self.z_moves() == "bed" else (lambda k: abs(float(k["machine"][2]) - float(t["z"])) < 0.6)
        starts = [k for k in known.values() if k.get("kind") == t["kind"] and level(k)]
        if not starts:
            return {}
        start = min(starts, key=lambda k: (k["machine"][0] - t["x"]) ** 2 + (k["machine"][1] - t["y"]) ** 2)
        sx, sy = float(start["machine"][0]), float(start["machine"][1])
        follow = {}
        for o in group:   # each point of the group known at the start place
            here = next((k for k in known.values() if k.get("kind") == o["kind"] and abs(k["machine"][0] - sx) < 0.6 and abs(k["machine"][1] - sy) < 0.6), None)
            patch = self.cv2.imread(self._template_path(o["kind"]), self.cv2.IMREAD_GRAYSCALE) if self.has_template(o["kind"]) else None
            if here and patch is not None:
                follow[o["id"]] = {"uv": self.np.array([here["u"], here["v"]], float), "patch": patch, "jac": None}
        goal = self.np.array([t["x"], t["y"]], float)
        at = self.np.array([sx, sy])
        if not follow or self.np.linalg.norm(goal - at) < 1.0:
            return {}
        self.gcode("G90\nG0 Z%.2f F%d\nG0 X%.2f Y%.2f F%d\nG0 Z%.2f F%d\nM400"
                   % (max(t["z"], printer["position"][2], 10.0, tallest + 5.0), Z_FEED, sx, sy, TRAVEL_FEED, t["z"], Z_FEED), 120)
        ahead = (goal - at) / self.np.linalg.norm(goal - at)
        side = self.np.array([-ahead[1], ahead[0]])
        (x0, y0), (x1, y1) = printer["minimum"][:2], printer["maximum"][:2]
        if not (x0 <= sx + side[0] * WALK_PROBE <= x1 and y0 <= sy + side[1] * WALK_PROBE <= y1):
            side = -side

        def look(spot, window):
            self.gcode("G90\nG0 X%.2f Y%.2f F%d\nM400" % (spot[0], spot[1], TRAVEL_FEED), 60)
            picture = self._fresh_picture()
            seen = {}
            for pid, f in follow.items():
                if f.get("lost"):
                    continue
                guess = f["uv"] + (f["jac"] @ (spot - at) if f["jac"] is not None else 0.0)
                r = self._look(picture, f["patch"], None, {"u": float(guess[0]), "v": float(guess[1]), "radius": window}, strict=True)
                if r["found"]:
                    seen[pid] = self.np.array([r["u"], r["v"]], float)
                    fresh = nozzle_finder.template(self.cv2, self.np, picture, r["u"], r["v"])
                    if fresh is not None and r["score"] >= WALK_KEEP:   # how it looks here: what is behind it changes on the way
                        f["patch"] = fresh
                else:   # lost on the way: not looked for anywhere else at the end (the person taps it)
                    f["lost"] = True
                    f["uv"] = self.np.array([float(guess[0]), float(guess[1])])
            return seen if any(not f.get("lost") for f in follow.values()) else None

        def lost():   # nothing followed to the end: nothing to look for there
            return {pid: {"u": float(f["uv"][0]), "v": float(f["uv"][1]), "radius": WALK_WINDOW, "lost": True} for pid, f in follow.items()}

        # two small moves (ahead and aside) tell how the picture moves per mm
        moves = {}
        for name, way in (("ahead", ahead), ("side", side)):
            seen = look(at + way * WALK_PROBE, WALK_FIRST)
            if seen is None:
                return lost()
            moves[name] = seen
        for pid, f in follow.items():
            if f.get("lost"):
                continue
            d = self.np.column_stack([moves["ahead"][pid] - f["uv"], moves["side"][pid] - f["uv"]]) / WALK_PROBE
            f["jac"] = d @ self.np.linalg.inv(self.np.column_stack([ahead, side]))
        while True:
            left = goal - at
            spot = goal if self.np.linalg.norm(left) <= WALK_STEP else at + left / self.np.linalg.norm(left) * WALK_STEP
            seen = look(spot, WALK_WINDOW)
            if seen is None:
                return lost()
            for pid, f in follow.items():   # how the picture moves per mm, kept up to date as the lens bends
                if pid not in seen:
                    continue
                moved, step = seen[pid] - f["uv"], spot - at
                f["jac"] = f["jac"] + self.np.outer(moved - f["jac"] @ step, step) / float(step @ step)
                f["uv"] = seen[pid]
            at = spot
            if self.np.linalg.norm(goal - at) < 0.5:
                return {pid: {"u": float(f["uv"][0]), "v": float(f["uv"][1]), "radius": WALK_WINDOW, "lost": bool(f.get("lost")), "patch": f["patch"]}
                        for pid, f in follow.items()}

    def find_all(self):
        """Every nozzle point not taken yet, one after the other, in the background (self.auto says how far it is)."""
        if self._auto_thread and self._auto_thread.is_alive():
            return self.auto
        if not self.can_find():
            if self.method() == "detail":
                raise ValueError("tap the nozzle tip and the detail of the toolhead by hand at the first place: KlippEye then finds both at the others")
            raise ValueError("tap the nozzle by hand at one point first: KlippEye then finds it at the others")
        printer = self.printer()
        self._ready_to_move(printer)
        todo = [t["id"] for t in self.target_list(printer) if t["kind"] in ("nozzle", "detail") and t["id"] not in (self.draft.get("points") or {})]
        self._auto_stop = False

        def run():
            found = 0
            began = int(time.time())
            for n, target_id in enumerate(todo):
                done = (self.draft.get("proposals") or {}).get(target_id)
                if done and done.get("time", 0) >= began:   # 1.128: looked at with the other point of the same place
                    found += bool(done.get("found"))
                    continue
                if self._auto_stop:
                    self.auto = {"state": "stopped", "done": n, "total": len(todo), "found": found, "time": int(time.time())}
                    return
                self.auto = {"state": "running", "done": n, "total": len(todo), "found": found, "current": target_id}
                try:
                    found += bool(self.find_tip(target_id)["found"])
                except Exception as error:
                    self.auto = {"state": "error", "done": n, "total": len(todo), "found": found, "message": str(error)[:300], "current": target_id}
                    return
            self.auto = {"state": "done", "done": len(todo), "total": len(todo), "found": found, "time": int(time.time())}
        self.auto = {"state": "running", "done": 0, "total": len(todo), "found": 0}
        self._auto_thread = threading.Thread(target=run, name="camera-find", daemon=True)
        self._auto_thread.start()
        return self.auto

    def stop_finding(self):
        self._auto_stop = True
        return self.auto

    def accept(self, ids=None):
        """The proposals found (all, or `ids`) become points, with the machine position of when they were found."""
        printer = self.printer()
        proposals = dict(self.draft.get("proposals") or {})
        taken = []
        for t in self.target_list(printer):
            p = proposals.get(t["id"])
            if p and p.get("found") and (ids is None or t["id"] in ids):
                self._store_point(t, p["machine"], p["u"], p["v"], source="found")
                taken.append(t["id"])
        return {"accepted": taken}

    def forget_point(self, target_id):
        with self.lock:
            self.draft.get("points", {}).pop(target_id, None)
            self.draft.pop("fit", None)
            self._save_draft()

    # ---------------------------------------------------------------- the markers (Z moves the bed)
    def markers_stl(self):
        """The STL of the six pyramids to print, for this printer's bed."""
        printer = self.printer()
        return camera_markers.markers_stl(printer["minimum"], printer["maximum"], positions=self.marker_layout(printer)[0])

    def gcode_files(self):
        """The newest G-code files on the printer (to choose the one of the markers), newest first."""
        files = sorted(self.files() if self.files else [], key=lambda f: f.get("modified") or 0, reverse=True)
        files = [f for f in files if str(f.get("path", "")).lower().endswith((".gcode", ".gco", ".g"))]
        return [{"path": f.get("path"), "modified": f.get("modified"), "size": f.get("size")} for f in files[:30]]

    def _set_markers(self, markers):
        with self.lock:
            self.draft["markers"] = markers
            self.draft["points"] = {}   # new markers: the points are taken again
            self.draft.pop("fit", None)
            self._save_draft()

    def use_marker_file(self, path):
        """Reads where the printed pyramids are from the G-code that printed them."""
        if self.z_moves() != "bed":
            raise ValueError("the markers are only for printers where Z moves the bed")
        if not isinstance(path, str) or not path or ".." in path.split("/"):
            raise ValueError("choose the file that printed the markers")
        known = {f["path"]: f for f in self.gcode_files()}
        if path in known and (known[path].get("size") or 0) > MAX_GCODE_BYTES:
            raise ValueError("this file is too big to be the markers file")
        text = self.read_file(path)
        points = camera_markers.read_markers(text)
        self._set_markers({"source": "file", "file": path, "points": [list(p) for p in points], "time": int(time.time())})
        return self.draft["markers"]

    def make_marks(self, temperature=210, bed_temperature=60):
        """The quick way: the printer leaves a small disc of filament at each grid point (temperatures chosen by the
        person, retraction and Z hop between them), then cools down. In the background; the state is in self.marks."""
        for value, low, high in ((temperature, 170, 300), (bed_temperature, 0, 120)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
                raise ValueError("temperatures: nozzle 170 to 300 °C, bed 0 to 120 °C")
        printer = self.printer()
        self._ready_to_move(printer)
        if self.z_moves() != "bed":
            raise ValueError("the markers are only for printers where Z moves the bed")
        if self._marks_thread and self._marks_thread.is_alive():
            return self.marks
        positions = camera_markers.marker_positions(printer["minimum"], printer["maximum"])
        script = camera_markers.blob_script(positions, int(temperature), int(bed_temperature))

        def run():
            self.marks = {"state": "running", "started": int(time.time())}
            try:
                self.gcode(script, 1800)
                self._set_markers({"source": "blobs", "points": [[x, y, camera_markers.BLOB_HEIGHT] for x, y in positions], "time": int(time.time()),
                                   "temperatures": [int(temperature), int(bed_temperature)]})
                self.marks = {"state": "done", "time": int(time.time())}
            except Exception as error:
                try:
                    self.gcode("M104 S0\nM140 S0", 10)
                except Exception:
                    pass
                self.marks = {"state": "error", "message": str(error)[:300]}
        self._marks_thread = threading.Thread(target=run, name="camera-marks", daemon=True)
        self._marks_thread.start()
        self.marks = {"state": "running", "started": int(time.time())}
        return self.marks

    # ---------------------------------------------------------------- fitting and saving
    def _picture(self):
        data = self.snapshot()
        image = self.cv2.imdecode(self.np.frombuffer(data, self.np.uint8), self.cv2.IMREAD_COLOR) if data else None
        if image is None:
            raise NotReady("no picture from the camera")
        return data, image

    def fit(self):
        with self.lock:
            points = list((self.draft.get("points") or {}).items())
        if len(points) < camera_model.MIN_POINTS:
            raise ValueError("at least 8 points are needed")
        _, image = self._picture()
        height, width = image.shape[:2]
        details = [(pid, p) for pid, p in points if p["kind"] == "detail"]
        if details:   # 1.128: the detail of the toolhead: its offset from the tip is found with the camera
            fixed = [(pid, p) for pid, p in points if p["kind"] != "detail"]
            points = fixed + details
            result = camera_model.fit_offset([p["frame"] for _, p in fixed], [[p["u"] * width, p["v"] * height] for _, p in fixed],
                                             [p["frame"] for _, p in details], [[p["u"] * width, p["v"] * height] for _, p in details], width, height)
        else:
            frame = [p["frame"] for _, p in points]
            pixels = [[p["u"] * width, p["v"] * height] for _, p in points]
            result = camera_model.fit(frame, pixels, width, height)
        median = sorted(result["errors_px"])[len(points) // 2]
        result["point_errors"] = {pid: round(err, 1) for (pid, _), err in zip(points, result["errors_px"])}
        result["redo"] = [pid for (pid, _), err in zip(points, result["errors_px"]) if err > max(3 * median, 0.01 * (width ** 2 + height ** 2) ** 0.5)]
        result["z_moves"] = self.z_moves()
        with self.lock:
            self.draft["fit"] = result
            self._save_draft()
        return result

    def save(self):
        with self.lock:
            result = self.draft.get("fit")
        if not result:
            raise ValueError("calculate the calibration first")
        if result["quality"] == "poor":
            raise ValueError("the calibration is not good enough: redo the points marked in red")
        data, image = self._picture()
        if (image.shape[1], image.shape[0]) != (result["width"], result["height"]):
            raise ValueError("the camera picture changed size: calculate again")
        with open(self.reference_path + ".tmp", "wb") as f:
            f.write(data)
        os.replace(self.reference_path + ".tmp", self.reference_path)
        with self.lock:
            saved = {"version": 1, "saved": int(time.time()), "z_moves": result["z_moves"], "model": result["model"], "params": result["params"],
                     "width": result["width"], "height": result["height"], "rms_px": result["rms_px"], "rms": result["rms"], "quality": result["quality"],
                     "points": self.draft.get("points"), "toolhead": self.draft.get("toolhead") or dict(DEFAULT_TOOLHEAD),
                     "camera_position": result["camera_position"], "watch": {"state": "ok", "time": int(time.time())}}
            if result.get("offset") is not None:   # 1.128: where the detail of the toolhead is, from the nozzle tip (mm)
                saved.update(method="detail", offset=[round(float(c), 2) for c in result["offset"]])
            _write_json(self.path, saved)
            self.saved = saved
            self.watch = saved["watch"]
            self.moves = []   # 1.127: a new calibration and a new reference picture: no move pending, no correction
            self.reset()
        return saved

    def forget(self):
        with self.lock:
            self.saved = None
            self.watch = {"state": "unknown"}
            for path in (self.path, self.reference_path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    # ---------------------------------------------------------------- has the camera moved?
    def check_moved(self):
        if not self.saved:
            return {"state": "none"}
        reference = self.cv2.imread(self.reference_path)
        if reference is None:
            return {"state": "unknown", "why": "the reference picture is missing"}
        try:
            _, image = self._picture()
        except NotReady as error:
            return {"state": "unknown", "why": str(error)}
        result = camera_watch.compare(self.cv2, self.np, reference, image)
        result["time"] = int(time.time())
        with self.lock:
            self._judge_move(result)
            self.saved["watch"] = self.watch
            _write_json(self.path, self.saved)
        self.last_watch = time.time()
        return self.watch

    def _judge_move(self, result):
        """1.127: what a look at the camera means (under the lock).
          - still ("ok"): no correction (the camera is back where it was);
          - moved a little, the same way in CORRECT_AFTER looks in a row (camera_watch.small / agree): the movement becomes a
            correction of the projections (saved["shift_fix"]; calibration() hands it on as "correction": the calibration
            itself is not changed) and the state is
            "corrected"; a look that agrees with the correction in use keeps it;
          - moved a lot, or a little but not yet confirmed: "moved" as before (masks and zones off: calibrate again), and
            the camera is looked at again soon (WATCH_SOON_S) while a small movement waits to be confirmed;
          - an unclear look ("unknown") changes nothing."""
        state = result["state"]
        correction = self.saved.get("shift_fix")
        if state == "unknown":
            if self.watch.get("state") not in ("moved", "corrected"):
                self.watch = result
            return
        if state == "ok":
            self.saved.pop("shift_fix", None)
            self.moves = []
            self.watch = result
            return
        if correction and camera_watch.agree(result, correction):
            self.watch = dict(result, state="corrected")
            return
        if camera_watch.small(result):
            self.moves = [m for m in self.moves if camera_watch.agree(m, result)] + [result]
            if len(self.moves) >= CORRECT_AFTER:
                self.saved["shift_fix"] = {"matrix": result["matrix"], "shift_px": result["shift_px"], "rotation_deg": result["rotation_deg"],
                                            "time": result["time"], "looks": len(self.moves)}
                self.moves = []
                self.watch = dict(result, state="corrected")
                return
        else:
            self.moves = []
        self.saved.pop("shift_fix", None)
        self.watch = dict(result, waiting=len(self.moves)) if self.moves else result

    def calibration(self):
        """1.127: the saved calibration as the masks and zones use it: with the correction of a small move of the camera."""
        saved = self.saved
        fix = (saved or {}).get("shift_fix")
        if not saved or not fix:
            return saved
        return dict(saved, correction=fix["matrix"])

    def undo_correction(self):
        """1.127: the person does not trust the correction: it goes, and the camera counts as moved (calibrate again)."""
        with self.lock:
            if not self.saved or not self.saved.get("shift_fix"):
                return self.watch
            self.saved.pop("shift_fix", None)
            self.moves = []
            self.watch = dict(self.watch, state="moved", undone=True)
            self.saved["watch"] = self.watch
            _write_json(self.path, self.saved)
        return self.watch

    def maybe_check(self):
        """Called often by the monitor: looks again every WATCH_EVERY_S seconds (1.127: every WATCH_SOON_S while a small move
        waits to be confirmed)."""
        every = WATCH_SOON_S if self.moves else WATCH_EVERY_S
        if self.saved and time.time() - self.last_watch > every:
            self.last_watch = time.time()
            try:
                self.check_moved()
            except Exception as error:
                print("[CAMERA] check not done: %s" % error)

    def usable(self):
        """True when the saved calibration can be trusted: masks and zones use it only then (never half masks)."""
        return bool(self.saved) and self.saved.get("quality") in ("good", "fair") and self.watch.get("state") != "moved"
        # 1.127: "corrected" (moved a little, corrected by itself) is usable

    # ---------------------------------------------------------------- what the page draws over the picture
    def overlay(self, use_draft=False):
        """The nozzle, the toolhead box and the bed outline at the printer's current position, as fractions of the picture."""
        calibration = (self.draft.get("fit") if use_draft else None) or self.calibration()
        if not calibration:
            return None
        z_moves = calibration.get("z_moves") or self.z_moves() or "toolhead"
        printer = self.printer()
        x, y, z = printer["position"]
        tip = frame_point(z_moves, x, y, z, "nozzle")
        shape = self.get_shape()
        parts = machine_masks.polygons(dict(calibration, z_moves=z_moves), shape, [x, y, z], [printer["minimum"][0], printer["maximum"][0]])
        bed_z = -z if z_moves == "bed" else 0.0
        area = self.bed_area()[0] if not use_draft else None   # 1.127: the bed the monitor watches
        (bx0, by0), (bx1, by1) = area if area else (printer["minimum"][:2], printer["maximum"][:2])
        bed = []
        for (ax, ay), (cx, cy) in (((bx0, by0), (bx1, by0)), ((bx1, by0), (bx1, by1)), ((bx1, by1), (bx0, by1)), ((bx0, by1), (bx0, by0))):
            for s in [i / 12.0 for i in range(12)]:
                bed.append([ax + (cx - ax) * s, ay + (cy - ay) * s, bed_z])
        bed_uv, bed_front = camera_model.project(calibration, bed)
        nozzle_uv, nozzle_front = camera_model.project(calibration, [tip])
        detail = None
        if calibration.get("offset"):   # 1.128: the detail of the toolhead that was tapped, where the calibration puts it
            d_uv, d_front = camera_model.project(calibration, [[tip[i] + float(calibration["offset"][i]) for i in range(3)]])
            detail = [round(float(c), 4) for c in d_uv[0]] if d_front[0] else None
        return {"position": printer["position"], "z_moves": z_moves, "detail": detail,
                "nozzle": [round(float(c), 4) for c in nozzle_uv[0]] if nozzle_front[0] else None,
                "toolhead": [[round(a, 4), round(b, 4)] for a, b in (parts["toolhead"][0] if parts["toolhead"] else [])],
                "gantry": [[[round(a, 4), round(b, 4)] for a, b in piece] for piece in parts["gantry"]],
                "shape": shape,
                "handles": machine_masks.handles(dict(calibration, z_moves=z_moves), shape, [x, y, z], [printer["minimum"][0], printer["maximum"][0]]),
                "bed": [[round(float(a), 4), round(float(b), 4)] for (a, b), f in zip(bed_uv, bed_front) if f]}

    # ---------------------------------------------------------------- the shape of the toolhead and the gantry (masks)
    def get_shape(self):
        """The shape of the moving parts: the one adjusted by the person, else made from the toolhead size of the calibration."""
        if self.shape is None:
            stored = _read_json(self.shape_path)
            try:
                self.shape = machine_masks.clean_shape(stored) if stored else None
            except ValueError:
                self.shape = None
            if self.shape is None:
                self.shape = machine_masks.from_toolhead_box((self.saved or {}).get("toolhead") or self.draft.get("toolhead"))
        return self.shape

    def set_shape(self, data):
        """Changes some sizes (the others stay): {"toolhead": {...}, "gantry": {...}}."""
        current = self.get_shape()
        merged = {}
        for part in machine_masks.DEFAULT_SHAPE:
            given = data.get(part) if isinstance(data, dict) else None
            merged[part] = dict(current[part], **given) if isinstance(given, dict) else dict(current[part])
        for key in ("x_range", "limits", "bed", "bed_auto"):
            if key in current:
                merged[key] = current[key]
        if isinstance(data, dict) and "bed" in data:   # 1.127: the bed area set by the person; None: worked out again
            if data["bed"] is None:
                merged.pop("bed", None)
            elif machine_masks.clean_area(data["bed"]) is None:
                raise machine_masks.ShapeError("bed", machine_masks.BED_MIN_MM, 10000)
            else:
                merged["bed"] = data["bed"]
        shape = machine_masks.clean_shape(merged)
        with self.lock:
            self.shape = shape
            _write_json(self.shape_path, shape)
        return shape

    def limits(self):
        """The travel of the printer, ([x min, y min], [x max, y max]): read from Klipper at most every ten minutes and kept in
        machine_shape.json (the gantry spans the X travel; the watched area is the bed), so that the replay knows it too."""
        when, known = self._limits
        if known is None or time.time() - when > WATCH_EVERY_S:
            try:
                printer = self.printer()
                known = ([float(printer["minimum"][0]), float(printer["minimum"][1])], [float(printer["maximum"][0]), float(printer["maximum"][1])])
                self._limits = (time.time(), known)
                shape = self.get_shape()
                if shape.get("limits") != [known[0], known[1]] or shape.get("x_range") != [known[0][0], known[1][0]]:
                    with self.lock:
                        shape["x_range"] = [known[0][0], known[1][0]]
                        shape["limits"] = [known[0], known[1]]
                        _write_json(self.shape_path, shape)
            except Exception:
                stored = self.get_shape().get("limits")
                known = known or ((stored[0], stored[1]) if stored else None)
                self._limits = (time.time(), known)
        return known

    def bed_area(self):
        """1.127: the bed the monitor watches, ([x min, y min], [x max, y max]) in mm, and where it comes from: "person"
        (set on the calibration page), "mesh" (Klipper's bed_mesh, a little wider), "travel" (the toolhead's travel, which
        often goes beyond the plate). (None, None) when nothing is known. The one worked out is kept in machine_shape.json
        («bed_auto») for the replay."""
        shape = self.get_shape()
        if shape.get("bed"):
            return (shape["bed"][0], shape["bed"][1]), "person"
        travel = self.limits()
        try:
            mesh = bed_from_mesh(self.settings(), travel)
        except Exception:
            mesh = None
        if mesh is None and shape.get("bed_auto"):
            mesh = shape["bed_auto"]
        if mesh:
            if shape.get("bed_auto") != mesh:
                with self.lock:
                    shape["bed_auto"] = mesh
                    _write_json(self.shape_path, shape)
            return (mesh[0], mesh[1]), "mesh"
        return (travel, "travel") if travel else (None, None)

    def x_range(self):
        known = self.limits()
        return [known[0][0], known[1][0]] if known else self.get_shape().get("x_range")

    def zone_masks(self, objects, z, width, height):
        """Phase 4c: (watched, expected, settled) pictures for the monitor with the machine at Z = z (print_zone.masks), or None when
        the calibration cannot be trusted, the bed size is not known or there are no objects."""
        known = self.bed_area()[0]
        if not objects or not known or not self.usable() or self.cv2 is None:
            return None
        return print_zone.masks(self.cv2, self.np, self.calibration(), objects, z, known[0], known[1], width, height)

    def monitor_mask(self, positions, width, height):
        """The machine mask for one check of the monitor (positions: where the toolhead was before and after the picture),
        or None when the calibration cannot be trusted (never half masks) or no position is known."""
        if not self.usable() or self.cv2 is None:
            return None
        return machine_masks.mask(self.cv2, self.np, self.calibration(), self.get_shape(), positions, width, height, self.x_range())

    def summary(self):
        saved = self.saved
        brief = None
        if saved:
            brief = {k: saved.get(k) for k in ("saved", "z_moves", "model", "rms_px", "rms", "quality", "toolhead", "camera_position", "width", "height", "shift_fix",
                                             "method", "offset")}
            brief["points"] = len(saved.get("points") or {})
        area, source = self.bed_area() if saved else (None, None)
        travel = self.limits() if saved else None
        return {"saved": brief, "watch": self.watch, "usable": self.usable(), "draft": self.draft, "marks": self.marks, "shape": self.get_shape(),
                "auto": self.auto, "template": self.has_template(), "detail_template": self.has_template("detail"),
                "can_find": self.can_find(), "method": self.method(),
                "bed": {"area": [list(area[0]), list(area[1])] if area else None, "source": source,
                        "travel": [list(travel[0]), list(travel[1])] if travel else None}}
