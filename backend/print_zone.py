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
1.70: the part itself is no longer a blind spot. What is already printed (the objects' own outlines, without the margin,
from the bed up to SETTLED_BELOW_MM under the height being printed now) does not change any more: the background is the
picture of the last minute, so a change that stays there (a string, spaghetti hanging in front of the part, the part
moving) counts like plastic outside the parts. Only the slice being printed now (with the margin) is left out.

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
SETTLED_BELOW_MM = 2.0     # 1.70: the part below the height being printed minus this is settled (it does not change any more)
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


def grow(polygon, margin, corners=8):
    """The polygon made `margin` mm larger all around (1.127: the same margin on every side; before, the corners were
    pushed out from the centre, so a long thin part got almost no margin on its long sides). The result is the convex
    outline of the polygon with a circle of `margin` around each corner (corners rounded with `corners` points)."""
    if margin <= 0:
        return [list(p) for p in polygon]
    ring = []
    for x, y in polygon:
        for k in range(corners):
            angle = 2 * math.pi * k / corners
            ring.append((x + margin * math.cos(angle) / math.cos(math.pi / corners), y + margin * math.sin(angle) / math.cos(math.pi / corners)))
    return [[round(x, 3), round(y, 3)] for x, y in camera_model.convex_hull(ring)]


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
    expected, settled, growing = [], [], []
    for item in objects or []:
        wide = grow(item["polygon"], ZONE_MARGIN_MM)
        piece = prism_outline(calibration, wide, bed, nozzle + ZONE_ABOVE_MM)
        if piece:
            expected.append(piece)
        if nozzle - SETTLED_BELOW_MM > bed:
            done = prism_outline(calibration, item["polygon"], bed, nozzle - SETTLED_BELOW_MM)
            slice_now = prism_outline(calibration, wide, nozzle - SETTLED_BELOW_MM, nozzle + ZONE_ABOVE_MM)
            if done:
                settled.append(done)
            if slice_now:
                growing.append(slice_now)
    return {"watched": watched, "expected": expected, "settled": settled, "growing": growing}


def part_mask(cv2, np, calibration, objects, z, width, height):
    """The part already printed as the camera sees it (uint8, 255 = part) at `width` x `height`: each object's own outline
    (no margin) from the bed up to the nozzle at Z = z. 1.123: to know when the toolhead hides it."""
    bed, nozzle = heights(calibration.get("z_moves"), z)
    out = np.zeros((height, width), np.uint8)
    if nozzle <= bed:
        return out
    for item in objects or []:
        polygon = prism_outline(calibration, item["polygon"], bed, nozzle)
        if polygon:
            pts = np.clip(np.array([[u * width, v * height] for u, v in polygon], np.float32), -4 * width, 5 * width).astype(np.int32)
            cv2.fillPoly(out, [pts], 255)
    return out


def masks(cv2, np, calibration, objects, z, bed_min, bed_max, width, height):
    """The pictures (uint8, 255 = in) of outlines() at `width` x `height`: (watched, expected, settled). `settled` (1.70) is
    the part already printed as the camera sees it, without the slice being printed now: watched like the rest of the bed."""
    parts = outlines(calibration, objects, z, bed_min, bed_max)
    result = {}
    for key in ("watched", "expected", "settled", "growing"):
        out = np.zeros((height, width), np.uint8)
        for polygon in parts[key]:
            pts = np.clip(np.array([[u * width, v * height] for u, v in polygon], np.float32), -4 * width, 5 * width).astype(np.int32)
            cv2.fillPoly(out, [pts], 255)
        result[key] = out
    settled = cv2.bitwise_and(result["settled"], cv2.bitwise_not(result["growing"]))
    return result["watched"], result["expected"], settled
