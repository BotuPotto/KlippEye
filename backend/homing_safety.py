"""
Homing with the camera markers on the bed (release 1.29.1).

After the markers are printed many printers switch the motors off (M84 in the slicer's end G-code, or Klipper's idle timeout),
so the calibration has to home again with six 10 mm pyramids on the bed. On a printer whose bed moves in Z, homing Z brings
the bed up under the nozzle (or the probe) at one point: if a pyramid is there, the toolhead hits it.

From Klipper's own configuration (configfile.settings) this module works out where Z is homed:
  * [safe_z_home] home_xy_position (or the home position of a Beacon / Cartographer that homes Z itself);
  * without it, where X and Y end their homing (their position_endstop): Klipper homes Z there;
  * [homing_override]: a macro of the person's: the place cannot be known (the page asks to check);
  * a Z endstop at the top of the travel (bed going down to home): nothing comes near the bed.
What touches there: the underside of the toolhead around the nozzle (its size from the camera page, machine_masks) and, when
Z is homed with the probe, the probe at its x_offset / y_offset from the nozzle.

It answers two questions:
  * safe_layout(): where to put the six markers (a symmetric grid, so a slicer that centres the object keeps them in place)
    so that none is where homing touches;
  * check(): with the markers on the bed (read from their G-code, or expected from the STL), is homing safe? -> the risks.
"""

MARKER_HALF = 8.0          # half the base of a printed pyramid (camera_markers.PYRAMID_BASE / 2)
MARGIN = 6.0               # mm kept free around what touches
PROBE_HALF = 8.0           # half the size of a probe's tip (a BLTouch pin, a small coil)
EDDY_HALF = 15.0           # Beacon, Cartographer, eddy current coils: wider
GRIDS_X = ((0.2, 0.5, 0.8), (0.15, 0.5, 0.85), (0.25, 0.5, 0.75), (0.1, 0.5, 0.9), (0.3, 0.5, 0.7))
GRIDS_Y = ((0.25, 0.75), (0.2, 0.8), (0.3, 0.7), (0.15, 0.85), (0.35, 0.65), (0.1, 0.9))
PROBES = ("probe", "bltouch", "smart_effector", "dockable_probe", "beacon", "cartographer", "scanner", "mellow_fly")
EDDY = ("beacon", "cartographer", "scanner", "probe_eddy_current")


def _floats(value):
    """[x, y] from "175, 175" or [175.0, 175.0] (configfile.settings gives either, by Klipper version)."""
    if isinstance(value, (list, tuple)):
        items = value
    elif isinstance(value, str):
        items = [part for part in value.replace(" ", "").split(",") if part]
    else:
        return None
    try:
        out = [float(v) for v in items]
    except (TypeError, ValueError):
        return None
    return out if len(out) >= 2 else None


def _number(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _probe(settings):
    """(name, x_offset, y_offset, half size) of the probe, or None."""
    for name, section in settings.items():
        base = name.split()[0]
        if base in PROBES or base == "probe_eddy_current":
            if isinstance(section, dict):
                return (base, _number(section.get("x_offset"), 0.0), _number(section.get("y_offset"), 0.0), EDDY_HALF if base in EDDY else PROBE_HALF)
    return None


def homing_place(settings):
    """Where homing Z touches the bed: {"how": "safe_z_home" | "probe_home" | "endstops" | "override" | "top" | "unknown",
    "xy": [x, y] or None, "probe": (name, dx, dy, half) or None, "z_hop": mm or None}."""
    settings = settings or {}
    stepper_z = settings.get("stepper_z") or {}
    endstop = str(stepper_z.get("endstop_pin", "")).lower()
    probe = _probe(settings)
    uses_probe = "z_virtual_endstop" in endstop
    out = {"how": "unknown", "xy": None, "probe": probe if uses_probe else None, "z_hop": None}
    safe = settings.get("safe_z_home")
    if isinstance(safe, dict):
        out["z_hop"] = _number(safe.get("z_hop"), 0.0)
    if "homing_override" in settings:
        out["how"] = "override"
        return out
    # a Z endstop at the top: the bed goes down to home, nothing comes near it
    pos_endstop, pos_max = _number(stepper_z.get("position_endstop")), _number(stepper_z.get("position_max"))
    if not uses_probe and pos_endstop is not None and pos_max is not None and pos_endstop >= pos_max - 1.0:
        out["how"] = "top"
        return out
    if isinstance(safe, dict) and _floats(safe.get("home_xy_position")):
        out["how"], out["xy"] = "safe_z_home", _floats(safe.get("home_xy_position"))[:2]
        return out
    for name in ("beacon", "cartographer", "scanner"):   # probes that home Z themselves, at their own place
        section = settings.get(name)
        if isinstance(section, dict) and _floats(section.get("home_xy_position")):
            out["how"], out["xy"] = "probe_home", _floats(section.get("home_xy_position"))[:2]
            out["probe"] = _probe({name: section})
            return out
    x, y = _number((settings.get("stepper_x") or {}).get("position_endstop")), _number((settings.get("stepper_y") or {}).get("position_endstop"))
    if x is not None and y is not None:
        out["how"], out["xy"] = "endstops", [x, y]
    return out


def footprints(place, toolhead):
    """What comes down on the bed during homing, as rectangles (x0, y0, x1, y1): the toolhead around the nozzle (its size
    from the camera page) and the probe. Empty when nothing does or the place is not known."""
    if not place or not place.get("xy"):
        return []
    x, y = place["xy"]
    t = toolhead or {"left": 30.0, "right": 30.0, "front": 35.0, "back": 35.0}
    rects = [("toolhead", x - t["left"], y - t["front"], x + t["right"], y + t["back"])]
    if place.get("probe"):
        _, dx, dy, half = place["probe"]
        rects.append(("probe", x + dx - half, y + dy - half, x + dx + half, y + dy + half))
    return rects


def hits(markers, rects, half=MARKER_HALF, margin=MARGIN):
    """The markers ([x, y, ...]) that lie under one of the rectangles: [(x, y, what)]."""
    out = []
    for m in markers or []:
        mx, my = float(m[0]), float(m[1])
        for what, x0, y0, x1, y1 in rects:
            if mx + half + margin > x0 and mx - half - margin < x1 and my + half + margin > y0 and my - half - margin < y1:
                out.append((round(mx, 1), round(my, 1), what))
                break
    return out


def safe_layout(minimum, maximum, place, toolhead):
    """The six marker positions: the usual 3 x 2 grid if homing touches none of them, else the first symmetric grid of GRIDS
    that keeps them all clear (a slicer that centres the object keeps a symmetric grid where it is). -> (positions, moved)."""
    x0, y0, x1, y1 = minimum[0], minimum[1], maximum[0], maximum[1]
    rects = footprints(place, toolhead)
    first = None
    for gy in GRIDS_Y:
        for gx in GRIDS_X:
            positions = [(round(x0 + (x1 - x0) * fx, 1), round(y0 + (y1 - y0) * fy, 1)) for fy in gy for fx in gx]
            if first is None:
                first = positions
            if not hits(positions, rects):
                return positions, positions != first
    return first, False


def check(settings, markers, toolhead, homed):
    """Is it safe to home with these markers on the bed? -> [{"kind", ...}] (empty: safe). Kinds:
        "hit"       homing Z touches a marker: {x, y, what ("toolhead" | "probe"), how}
        "override"  [homing_override]: where it homes cannot be known
        "unknown"   the place of Z homing could not be worked out
        "no_hop"    X and Y are homed before Z at the nozzle's current height (no z_hop and Z not homed): it may be low"""
    place = homing_place(settings)
    if not markers or place["how"] == "top":
        return []
    risks = []
    if place["how"] == "override":
        risks.append({"kind": "override"})
    elif not place["xy"]:
        risks.append({"kind": "unknown"})
    else:
        for x, y, what in hits(markers, footprints(place, toolhead)):
            risks.append({"kind": "hit", "x": x, "y": y, "what": what, "how": place["how"], "at": place["xy"]})
    if "z" not in str(homed or "") and not place.get("z_hop"):
        risks.append({"kind": "no_hop"})
    return risks
