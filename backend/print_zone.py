"""
The expected zone of KlippEye's AI monitor (roadmap phase 4c): where the printed part is allowed to be, so that the monitor
can watch the WHOLE bed and not only the edges of a rectangle.

Until 1.15 the monitor counted only the changes in the outer band of the watched area: the middle, where the part grows, was
never looked at, so a failure on the part itself (spaghetti, a part torn off) could go unseen. With the camera calibration
(camera_model.py) and the outline of the objects being printed, every check now knows:
  * the WATCHED area: the volume above the bed, from the bed surface up to a little above the nozzle, as seen by the camera;
  * the EXPECTED zone: the objects' outlines (with a margin) from the bed up to the height being printed now. Changes there
    are the print itself and do not count;
and a change that stays OUTSIDE the expected zone but inside the watched area (plastic where no part should be) is what the
monitor counts. The toolhead and the gantry are left out as before (machine_masks.py).

Where the outlines of the objects come from:
  1. Klipper's exclude_object (when the slicer labels the objects: PrusaSlicer, SuperSlicer, OrcaSlicer "Label objects",
     Cura with a plugin) gives one polygon per object;
  2. otherwise the G-code being printed is read once: its extrusions, drawn on a 5 mm grid, form groups (one per object);
     each group's outline (convex hull) is an object. Skirt and purge lines are first-layer only: they are left out by using
     only what is printed above the first layer when there is such a thing.
Without outlines (or without a usable calibration) the monitor works as before (outer band).
"""
import math

import camera_model
import camera_markers

ZONE_MARGIN_MM = 6.0       # around the objects (the part may be a little wider than its outline: elephant foot, brim)
ZONE_ABOVE_MM = 4.0        # above the height being printed
WATCH_ABOVE_MM = 40.0      # the watched volume goes up to this much above the nozzle (spaghetti hanging from it)
GRID_MM = 5.0
FIRST_LAYER_MM = 0.6       # what is printed below this height (first layer) may be skirt or purge


def objects_from_exclude(objects):
    """Klipper's exclude_object "objects" -> [{"name", "polygon": [[x, y], ...]}] (those with a polygon of 3+ points)."""
    out = []
    for item in objects or []:
        polygon = item.get("polygon") if isinstance(item, dict) else None
        if isinstance(polygon, list) and len(polygon) >= 3:
            try:
                out.append({"name": str(item.get("name", "")), "polygon": [[float(p[0]), float(p[1])] for p in polygon]})
            except (TypeError, ValueError, IndexError):
                continue
    return out


def objects_from_gcode(lines):
    """The objects of a G-code (a text, or its lines one by one: a big file is read as it streams), from its extrusions:
    [{"name", "polygon"}], biggest first. Empty when nothing is extruded.
    Each 5 mm cell of the bed keeps only the corners of what was extruded in it, so memory stays small whatever the file."""
    if isinstance(lines, str):
        lines = lines.splitlines()
    cells, upper, first = {}, {}, None
    for x, y, z in camera_markers.iter_extrusions(lines):
        if first is None:
            first = z
        key = (int(math.floor(x / GRID_MM)), int(math.floor(y / GRID_MM)))
        for target in (cells, upper) if z >= first + FIRST_LAYER_MM else (cells,):
            box = target.get(key)
            target[key] = [x, y, x, y] if box is None else [min(box[0], x), min(box[1], y), max(box[2], x), max(box[3], y)]
    use = upper if len(upper) >= 3 else cells
    seen, groups = set(), []
    for start in use:
        if start in seen:
            continue
        stack, members = [start], []
        seen.add(start)
        while stack:
            cell = stack.pop()
            x0, y0, x1, y1 = use[cell]
            members += [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    other = (cell[0] + dx, cell[1] + dy)
                    if other in use and other not in seen:
                        seen.add(other)
                        stack.append(other)
        groups.append(members)
    groups.sort(key=len, reverse=True)
    out = []
    for n, members in enumerate(groups, 1):
        hull = camera_model.convex_hull(members)
        if len(hull) >= 3:
            out.append({"name": "object %d" % n, "polygon": [[round(x, 2), round(y, 2)] for x, y in hull]})
    return out


def grow(polygon, margin):
    """A convex polygon made `margin` mm larger (each corner pushed out from the centre; good enough for a margin)."""
    cx = sum(p[0] for p in polygon) / len(polygon)
    cy = sum(p[1] for p in polygon) / len(polygon)
    out = []
    for x, y in polygon:
        d = math.hypot(x - cx, y - cy) or 1.0
        out.append([x + (x - cx) / d * margin, y + (y - cy) / d * margin])
    return out


def _densify(polygon, step=10.0):
    out = []
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
        pieces = max(1, int(math.hypot(x1 - x0, y1 - y0) // step) + 1)
        out += [[x0 + (x1 - x0) * k / pieces, y0 + (y1 - y0) * k / pieces] for k in range(pieces)]
    return out


def heights(z_moves, z):
    """(bed surface, nozzle) heights in the calibration's coordinates with the machine at Z = z."""
    return (-float(z), 0.0) if z_moves == "bed" else (0.0, float(z))


def prism_outline(calibration, polygon, bottom, top):
    """The outline in the picture (fractions) of a vertical prism: `polygon` (XY, mm) from `bottom` to `top`."""
    ring = _densify([list(p) for p in polygon])
    points = [[x, y, bottom] for x, y in ring] + [[x, y, top] for x, y in ring]
    uv, front = camera_model.project(calibration, points)
    visible = [(float(u), float(v)) for (u, v), f in zip(uv, front) if f]
    hull = camera_model.convex_hull(visible) if len(visible) >= 3 else []
    return hull if len(hull) >= 3 else None


def outlines(calibration, objects, z, bed_min, bed_max):
    """For the machine at Z = z: {"watched": [polygon], "expected": [polygon, ...]} in fractions of the picture."""
    z_moves = calibration.get("z_moves")
    bed, nozzle = heights(z_moves, z)
    watched = []
    # the watched volume in pieces (a 4 x 4 grid), so that the bending of the lens is followed
    xs = [bed_min[0] + (bed_max[0] - bed_min[0]) * k / 4.0 for k in range(5)]
    ys = [bed_min[1] + (bed_max[1] - bed_min[1]) * k / 4.0 for k in range(5)]
    for i in range(4):
        for j in range(4):
            piece = prism_outline(calibration, [[xs[i], ys[j]], [xs[i + 1], ys[j]], [xs[i + 1], ys[j + 1]], [xs[i], ys[j + 1]]], bed, nozzle + WATCH_ABOVE_MM)
            if piece:
                watched.append(piece)
    expected = []
    for item in objects or []:
        piece = prism_outline(calibration, grow(item["polygon"], ZONE_MARGIN_MM), bed, nozzle + ZONE_ABOVE_MM)
        if piece:
            expected.append(piece)
    return {"watched": watched, "expected": expected}


def masks(cv2, np, calibration, objects, z, bed_min, bed_max, width, height):
    """The two pictures (uint8, 255 = in) of outlines(): (watched, expected), at `width` x `height`."""
    parts = outlines(calibration, objects, z, bed_min, bed_max)
    result = []
    for key in ("watched", "expected"):
        out = np.zeros((height, width), np.uint8)
        for polygon in parts[key]:
            pts = np.clip(np.array([[u * width, v * height] for u, v in polygon], np.float32), -4 * width, 5 * width).astype(np.int32)
            cv2.fillPoly(out, [pts], 255)
        result.append(out)
    return result[0], result[1]
