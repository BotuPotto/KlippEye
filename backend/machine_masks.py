"""
The machine masks of KlippEye's AI monitor (roadmap phase 4b): the parts of the camera picture where the toolhead and the
gantry are, so that the monitor does not take them for a problem.

With the camera calibration (camera_model.py, camera_calibration.py) every point of the printer has its place in the picture.
The SHAPE says how big the moving parts are, in mm around the nozzle tip:
  * the toolhead: a box from `left` to `right` (X), from `front` to `back` (Y), from `below` the tip to `top` above it;
  * the gantry (the bar that carries the toolhead: on a VzBot or a Voron it crosses the whole printer in X and moves in Y with
    the toolhead): a bar over the whole X range, starting `behind` mm behind the nozzle (Y), `depth` mm deep, from `low` to
    `high` mm above the nozzle. On printers where Z moves the bed the bar stays at the nozzle's height; where Z moves the
    toolhead it goes up and down with it: in both cases its place is fixed with respect to the nozzle.
The person adjusts the shape on the live picture (Settings -> Camera calibration) until the drawing covers the parts.

polygons() gives the outlines in the picture (fractions 0..1) for one position of the nozzle, or for all the positions
between two corners (the toolhead moves while the picture is taken: the box then covers its whole way); mask() turns the
outlines of one check (where the toolhead was just before and just after the picture) into the black-and-white picture the
monitor uses (monitor_core.FrameJudge.judge(ignore=...)).
The same code runs live (the backend) and on the recordings (scripts/replay.py).
"""
import camera_model

DEFAULT_SHAPE = {
    "toolhead": {"left": 30.0, "right": 30.0, "front": 35.0, "back": 35.0, "top": 70.0, "below": 2.0},
    "gantry": {"on": True, "behind": 20.0, "depth": 40.0, "low": 15.0, "high": 60.0},
}
LIMITS = {"left": (0, 300), "right": (0, 300), "front": (0, 300), "back": (0, 300), "top": (0, 400), "below": (0, 50),
          "behind": (-150, 300), "depth": (0, 300), "low": (-50, 400), "high": (-50, 400)}
GANTRY_PIECES = 10        # the bar is drawn in pieces, so that the bending of a fisheye lens is followed closely
GANTRY_OVERHANG = 30.0    # mm beyond the X range on both sides (carriages, belts)
MARGIN_FRACTION = 0.012   # a margin around the masks (fraction of the picture width): about 6 px on 540


class ShapeError(ValueError):
    """A wrong size: the text is fixed (translated by the backend), `values` fills it."""

    def __init__(self, key, low, high):
        ValueError.__init__(self, "each size must be {low} to {high} mm")
        self.values = {"low": low, "high": high}
        self.key = key


def from_toolhead_box(box):
    """The shape from the old size of the toolhead (1.13, 1.14: width, depth, height, centred on the nozzle)."""
    shape = clean_shape(None)
    if isinstance(box, dict):
        try:
            w, d, h = float(box.get("width", 60)) / 2.0, float(box.get("depth", 70)) / 2.0, float(box.get("height", 70))
            shape["toolhead"].update(left=w, right=w, front=d, back=d, top=h)
        except (TypeError, ValueError):
            pass
    return shape


def clean_shape(data):
    """A complete, valid shape from what was given (missing values: the defaults). Raises ValueError on a wrong value."""
    data = data if isinstance(data, dict) else {}
    out = {}
    for part, defaults in DEFAULT_SHAPE.items():
        given = data.get(part) if isinstance(data.get(part), dict) else {}
        values = {}
        for key, default in defaults.items():
            value = given.get(key, default)
            if key == "on":
                values[key] = bool(value)
                continue
            low, high = LIMITS[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
                raise ShapeError(key, low, high)
            values[key] = round(float(value), 1)
        out[part] = values
    if out["gantry"]["high"] <= out["gantry"]["low"]:
        out["gantry"]["high"] = out["gantry"]["low"] + 1.0
    if isinstance(data.get("x_range"), (list, tuple)) and len(data["x_range"]) == 2:
        out["x_range"] = [float(data["x_range"][0]), float(data["x_range"][1])]
    return out


def nozzle_frame(z_moves, position):
    """Where the nozzle tip is in the calibration's coordinates (Z moves the bed: the nozzle is always at height 0)."""
    x, y, z = position[:3]
    return (float(x), float(y), 0.0) if z_moves == "bed" else (float(x), float(y), float(z))


def polygons(calibration, shape, position, x_range=None, to=None):
    """The outlines in the picture (fractions) of the toolhead and of the gantry with the nozzle at `position` (machine X, Y,
    Z), or anywhere between `position` and `to` (two corners: lowest and highest X, Y, Z).
    -> {"toolhead": [polygon], "gantry": [polygon, ...]} (each polygon a list of (u, v); empty when not in view)."""
    tx, ty, tz = nozzle_frame(calibration.get("z_moves"), position)
    hx, hy, hz = nozzle_frame(calibration.get("z_moves"), to) if to is not None else (tx, ty, tz)
    tool = shape["toolhead"]
    box = camera_model.box_corners(tx - tool["left"], hx + tool["right"], ty - tool["front"], hy + tool["back"], tz - tool["below"], hz + tool["top"])
    head = camera_model.box_outline(calibration, box)
    out = {"toolhead": [head] if head and len(head) > 2 else [], "gantry": []}
    gantry = shape["gantry"]
    if gantry.get("on"):
        x0, x1 = x_range or shape.get("x_range") or (tx - 200.0, tx + 200.0)
        x0, x1 = x0 - GANTRY_OVERHANG, x1 + GANTRY_OVERHANG
        y0, y1 = ty + gantry["behind"], hy + gantry["behind"] + max(gantry["depth"], 1.0)
        z0, z1 = tz + gantry["low"], hz + gantry["high"]
        step = (x1 - x0) / GANTRY_PIECES
        for i in range(GANTRY_PIECES):
            piece = camera_model.box_outline(calibration, camera_model.box_corners(x0 + i * step, x0 + (i + 1) * step, y0, y1, z0, z1), steps=2)
            if piece and len(piece) > 2:
                out["gantry"].append(piece)
    return out


def mask(cv2, np, calibration, shape, positions, width, height, x_range=None):
    """The picture (`width` x `height`, uint8: 255 = leave out) of the toolhead and the gantry at the positions of one check
    (and on the way between them). None when no position is known."""
    spots = [p for p in positions if p and len(p) >= 3 and all(isinstance(v, (int, float)) for v in p[:3])]
    if not spots:
        return None
    low = [min(float(p[i]) for p in spots) for i in range(3)]
    high = [max(float(p[i]) for p in spots) for i in range(3)]
    out = np.zeros((height, width), np.uint8)
    for polygon in [p for part in polygons(calibration, shape, low, x_range, high).values() for p in part]:
        pts = np.array([[u * width, v * height] for u, v in polygon], np.float32)
        pts = np.clip(pts, -4 * width, 5 * width).astype(np.int32)
        cv2.fillPoly(out, [pts], 255)
    margin = max(1, int(round(MARGIN_FRACTION * width)))
    return cv2.dilate(out, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * margin + 1, 2 * margin + 1)))
