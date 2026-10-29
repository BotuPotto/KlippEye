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
import machine_masks

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
BUSY_STATES = ("printing", "paused")


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
    return [x, y, 0.0] if z_moves == "bed" else [x, y, z]


def targets(z_moves, minimum, maximum, markers=None):
    """The points to take, in order (little travel). Each: id, kind, x, y, z (the machine Z to go to), height (markers).
    Z moves the bed: nothing until the markers are known (printed and read from their G-code, or blobs)."""
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
        self.last_watch = 0.0

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

    def set_options(self, z_moves=None, toolhead=None):
        with self.lock:
            if z_moves is not None:
                if z_moves not in Z_MOVES:
                    raise ValueError("z_moves must be bed or toolhead")
                if z_moves != self.draft.get("z_moves"):
                    self.draft = {"z_moves": z_moves, "points": {}, "toolhead": self.draft.get("toolhead")}
            if toolhead is not None:
                clean = {}
                for key in DEFAULT_TOOLHEAD:
                    value = toolhead.get(key, DEFAULT_TOOLHEAD[key])
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 10 <= value <= 300:
                        raise ValueError("the toolhead size must be 10 to 300 mm")
                    clean[key] = float(value)
                self.draft["toolhead"] = clean
            self.draft.setdefault("points", {})
            self._save_draft()
            return self.draft

    def reset(self):
        with self.lock:
            self.draft = {}
            try:
                os.remove(self.draft_path)
            except OSError:
                pass

    def target_list(self, printer=None):
        z_moves = self.z_moves()
        if not z_moves:
            return []
        printer = printer or self.printer()
        markers = (self.draft.get("markers") or {}).get("points")
        return targets(z_moves, printer["minimum"], printer["maximum"], markers)

    def _target(self, target_id, printer):
        for t in self.target_list(printer):
            if t["id"] == target_id:
                return t
        raise ValueError("unknown point")

    def home(self):
        printer = self.printer()
        if printer["state"] in BUSY_STATES:
            raise NotReady("the printer is printing")
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
        now: it is the real one, even after a nudge by hand."""
        for value in (u, v):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError("u and v must be fractions of the picture (0..1)")
        printer = self.printer()
        t = self._target(target_id, printer)
        x, y, z = printer["position"]
        if t["kind"] == "mark":
            x, y = t["x"], t["y"]  # the marker is where it was printed; the nozzle is parked elsewhere
        point = {"kind": t["kind"], "machine": [x, y, z], "frame": frame_point(self.z_moves(), x, y, z, t["kind"], t.get("height", 0.0)),
                 "u": round(u, 5), "v": round(v, 5), "time": int(time.time())}
        with self.lock:
            self.draft.setdefault("points", {})[target_id] = point
            self.draft.pop("fit", None)
            self._save_draft()
        return point

    def forget_point(self, target_id):
        with self.lock:
            self.draft.get("points", {}).pop(target_id, None)
            self.draft.pop("fit", None)
            self._save_draft()

    # ---------------------------------------------------------------- the markers (Z moves the bed)
    def markers_stl(self):
        """The STL of the six pyramids to print, for this printer's bed."""
        printer = self.printer()
        return camera_markers.markers_stl(printer["minimum"], printer["maximum"])

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
            _write_json(self.path, saved)
            self.saved = saved
            self.watch = saved["watch"]
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
            if result["state"] != "unknown" or self.watch.get("state") != "moved":  # an unclear look does not clear a "moved"
                self.watch = result
            self.saved["watch"] = self.watch
            _write_json(self.path, self.saved)
        self.last_watch = time.time()
        return self.watch

    def maybe_check(self):
        """Called often by the monitor: looks again every WATCH_EVERY_S seconds."""
        if self.saved and time.time() - self.last_watch > WATCH_EVERY_S:
            self.last_watch = time.time()
            try:
                self.check_moved()
            except Exception as error:
                print("[CAMERA] check not done: %s" % error)

    def usable(self):
        """True when the saved calibration can be trusted: masks and zones use it only then (never half masks)."""
        return bool(self.saved) and self.saved.get("quality") in ("good", "fair") and self.watch.get("state") != "moved"

    # ---------------------------------------------------------------- what the page draws over the picture
    def overlay(self, use_draft=False):
        """The nozzle, the toolhead box and the bed outline at the printer's current position, as fractions of the picture."""
        calibration = (self.draft.get("fit") if use_draft else None) or self.saved
        if not calibration:
            return None
        z_moves = calibration.get("z_moves") or self.z_moves() or "toolhead"
        printer = self.printer()
        x, y, z = printer["position"]
        tip = frame_point(z_moves, x, y, z, "nozzle")
        shape = self.get_shape()
        parts = machine_masks.polygons(dict(calibration, z_moves=z_moves), shape, [x, y, z], [printer["minimum"][0], printer["maximum"][0]])
        bed_z = -z if z_moves == "bed" else 0.0
        (bx0, by0), (bx1, by1) = printer["minimum"][:2], printer["maximum"][:2]
        bed = []
        for (ax, ay), (cx, cy) in (((bx0, by0), (bx1, by0)), ((bx1, by0), (bx1, by1)), ((bx1, by1), (bx0, by1)), ((bx0, by1), (bx0, by0))):
            for s in [i / 12.0 for i in range(12)]:
                bed.append([ax + (cx - ax) * s, ay + (cy - ay) * s, bed_z])
        bed_uv, bed_front = camera_model.project(calibration, bed)
        nozzle_uv, nozzle_front = camera_model.project(calibration, [tip])
        return {"position": printer["position"], "z_moves": z_moves,
                "nozzle": [round(float(c), 4) for c in nozzle_uv[0]] if nozzle_front[0] else None,
                "toolhead": [[round(a, 4), round(b, 4)] for a, b in (parts["toolhead"][0] if parts["toolhead"] else [])],
                "gantry": [[[round(a, 4), round(b, 4)] for a, b in piece] for piece in parts["gantry"]],
                "shape": shape,
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
        if "x_range" in current:
            merged["x_range"] = current["x_range"]
        shape = machine_masks.clean_shape(merged)
        with self.lock:
            self.shape = shape
            _write_json(self.shape_path, shape)
        return shape

    def x_range(self):
        """The X travel of the printer (the gantry spans it), read from Klipper at most every ten minutes and kept in
        machine_shape.json, so that the replay of the recordings knows it too."""
        when, known = self._limits
        if known is None or time.time() - when > WATCH_EVERY_S:
            try:
                printer = self.printer()
                known = [float(printer["minimum"][0]), float(printer["maximum"][0])]
                self._limits = (time.time(), known)
                shape = self.get_shape()
                if shape.get("x_range") != known:
                    with self.lock:
                        shape["x_range"] = known
                        _write_json(self.shape_path, shape)
            except Exception:
                known = known or self.get_shape().get("x_range")
                self._limits = (time.time(), known)
        return known

    def monitor_mask(self, positions, width, height):
        """The machine mask for one check of the monitor (positions: where the toolhead was before and after the picture),
        or None when the calibration cannot be trusted (never half masks) or no position is known."""
        if not self.usable() or self.cv2 is None:
            return None
        return machine_masks.mask(self.cv2, self.np, self.saved, self.get_shape(), positions, width, height, self.x_range())

    def summary(self):
        saved = self.saved
        brief = None
        if saved:
            brief = {k: saved.get(k) for k in ("saved", "z_moves", "model", "rms_px", "rms", "quality", "toolhead", "camera_position", "width", "height")}
            brief["points"] = len(saved.get("points") or {})
        return {"saved": brief, "watch": self.watch, "usable": self.usable(), "draft": self.draft, "marks": self.marks, "shape": self.get_shape()}
