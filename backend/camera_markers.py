"""
The markers of the camera calibration (roadmap phase 4a), for printers where Z moves the bed: things on the bed whose
position is known exactly, to be tapped in the picture with the bed lowered (the nozzle alone stays at one height for a
camera fixed to the frame, so it is not enough).

Two ways:
  * PRINTED markers (recommended): markers_stl() makes an STL with six small square pyramids spread over the bed; the
    person slices it with their own settings and prints it. Wherever the slicer put them, read_markers() finds them in the
    G-code that was printed: the layers above the first millimetre are only the pyramids (skirt, brim and purge lines are
    first-layer only), so their extrusions form six groups; the centre of each group is the tip's X, Y and its highest
    extrusion is the tip's height. The tip of a pyramid is a sharp point: easy to tap.
  * quick BLOBS: blob_script() makes the printer itself leave six small discs of filament (a spiral), with the nozzle and
    bed temperatures chosen by the person, retraction and a Z hop between them (no strings).
"""
import math
import re
import struct

MARKER_COUNT = 6
GRID_X = (0.2, 0.5, 0.8)
GRID_Y = (0.25, 0.75)
PYRAMID_BASE = 16.0   # mm
PYRAMID_HEIGHT = 10.0
CLUSTER_RADIUS = 25.0
ABOVE_FIRST_LAYERS = 1.0   # mm above the first layer: only the pyramids are there
BLOB_DIAMETER = 7.0
BLOB_HEIGHT = 0.6
BLOB_LAYER = 0.3


def marker_positions(minimum, maximum):
    """Where the six markers go: a 3 x 2 grid well inside the bed (20/50/80 % of X, 25/75 % of Y)."""
    x0, y0, x1, y1 = minimum[0], minimum[1], maximum[0], maximum[1]
    xs = [round(x0 + (x1 - x0) * f, 1) for f in GRID_X]
    ys = [round(y0 + (y1 - y0) * f, 1) for f in GRID_Y]
    return [(x, y) for y in ys for x in xs]


def _pyramid(cx, cy, base, height):
    """The 6 triangles (4 sides + 2 for the square base) of a square pyramid, outward normals."""
    h = base / 2.0
    a, b, c, d = (cx - h, cy - h, 0.0), (cx + h, cy - h, 0.0), (cx + h, cy + h, 0.0), (cx - h, cy + h, 0.0)
    tip = (cx, cy, height)
    return [(a, b, tip), (b, c, tip), (c, d, tip), (d, a, tip), (a, c, b), (a, d, c)]


def markers_stl(minimum, maximum, base=PYRAMID_BASE, height=PYRAMID_HEIGHT):
    """A binary STL with six pyramids at marker_positions(), in the printer's coordinates."""
    triangles = []
    for x, y in marker_positions(minimum, maximum):
        triangles += _pyramid(x, y, base, height)
    out = [b"KlippEye camera calibration markers".ljust(80, b" "), struct.pack("<I", len(triangles))]
    for p1, p2, p3 in triangles:
        u = [p2[i] - p1[i] for i in range(3)]
        v = [p3[i] - p1[i] for i in range(3)]
        n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        length = math.sqrt(sum(c * c for c in n)) or 1.0
        out.append(struct.pack("<12fH", *([c / length for c in n] + list(p1) + list(p2) + list(p3) + [0])))
    return b"".join(out)


class NotSix(ValueError):
    """Not six groups: the text is fixed (translated by the backend), `values` fills it."""

    def __init__(self, found):
        ValueError.__init__(self, "the markers file was not recognised: {found} markers found instead of 6")
        self.values = {"found": found}


_WORD = re.compile(r"([A-Za-z])\s*(-?\d*\.?\d+)")


def extrusions(text):
    """The extruding moves of a G-code text: (x, y, z) at the end of each. Understands G90/G91, M82/M83, G92 and G2/G3
    (their end point)."""
    pos = {"X": 0.0, "Y": 0.0, "Z": 0.0, "E": 0.0}
    absolute, absolute_e = True, True
    out = []
    for raw in text.splitlines():
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        words = _WORD.findall(line)
        if not words:
            continue
        cmd = (words[0][0] + words[0][1]).upper()
        if cmd == "G90":
            absolute = True
        elif cmd == "G91":
            absolute = False
        elif cmd == "M82":
            absolute_e = True
        elif cmd == "M83":
            absolute_e = False
        elif cmd == "G92":
            for letter, value in words[1:]:
                if letter.upper() in pos:
                    pos[letter.upper()] = float(value)
        elif cmd in ("G0", "G1", "G2", "G3"):
            extruded = 0.0
            for letter, value in words[1:]:
                letter = letter.upper()
                if letter in ("X", "Y", "Z"):
                    pos[letter] = float(value) if absolute else pos[letter] + float(value)
                elif letter == "E":
                    if absolute_e:
                        extruded = float(value) - pos["E"]
                        pos["E"] = float(value)
                    else:
                        extruded = float(value)
            if extruded > 1e-6:
                out.append((pos["X"], pos["Y"], pos["Z"]))
    return out


def read_markers(text, count=MARKER_COUNT):
    """The markers printed by a G-code: [(x, y, tip height)] sorted like marker_positions (front row first, left to right).
    Raises ValueError when they are not `count` well separated groups."""
    points = extrusions(text)
    if not points:
        raise ValueError("this file extrudes nothing")
    first = min(z for _, _, z in points)
    upper = [p for p in points if p[2] >= first + ABOVE_FIRST_LAYERS]
    if not upper:
        raise ValueError("this file has no markers: print the KlippEye markers file")
    groups = []   # [sum x, sum y, n, min x, max x, min y, max y, max z]
    for x, y, z in upper:
        for g in groups:
            if math.hypot(x - g[0] / g[2], y - g[1] / g[2]) < CLUSTER_RADIUS:
                g[0] += x
                g[1] += y
                g[2] += 1
                g[3], g[4], g[5], g[6], g[7] = min(g[3], x), max(g[4], x), min(g[5], y), max(g[6], y), max(g[7], z)
                break
        else:
            groups.append([x, y, 1, x, x, y, y, z])
    groups = [g for g in groups if g[2] >= 3]
    if len(groups) != count:
        raise NotSix(len(groups))
    markers = [((g[3] + g[4]) / 2.0, (g[5] + g[6]) / 2.0, g[7]) for g in groups]
    markers.sort(key=lambda m: (round(m[1] / CLUSTER_RADIUS), m[0]))
    return [(round(x, 2), round(y, 2), round(z, 2)) for x, y, z in markers]


def blob_script(positions, nozzle_temperature, bed_temperature, diameter=BLOB_DIAMETER):
    """G-code that leaves a small disc of filament at each position: a spiral from the outside in at BLOB_LAYER, two
    passes; retraction, Z hop and a quick travel between them, so no strings."""
    flow = 0.4 * BLOB_LAYER / (math.pi * 1.75 ** 2 / 4)   # mm of 1.75 filament per mm of a 0.4 line
    lines = ["M140 S%d" % bed_temperature, "M104 S%d" % nozzle_temperature, "M190 S%d" % bed_temperature, "M109 S%d" % nozzle_temperature,
             "G90", "M83", "G0 Z10 F900", "G1 E3 F300", "G1 E-1 F2400"]
    for x, y in positions:
        lines += ["G0 X%.2f Y%.2f F9000" % (x + diameter / 2.0, y), "G0 Z%.2f F900" % BLOB_LAYER, "G1 E1 F1800"]
        prev = (x + diameter / 2.0, y)
        for layer in range(2):
            z = BLOB_LAYER * (layer + 1)
            lines.append("G1 Z%.2f F600" % z)
            radius = diameter / 2.0
            while radius > 0.3:
                for k in range(1, 17):
                    a = 2 * math.pi * k / 16
                    r = radius - 0.4 * k / 16
                    px, py = x + r * math.cos(a), y + r * math.sin(a)
                    lines.append("G1 X%.2f Y%.2f E%.4f F1200" % (px, py, math.hypot(px - prev[0], py - prev[1]) * flow * 1.2))
                    prev = (px, py)
                radius -= 0.4
        lines += ["G1 E-1 F2400", "G0 Z5 F1200"]   # retract and lift before the next one
    lines += ["G0 Z10 F900", "M104 S0", "M140 S0", "M82", "M400"]
    return "\n".join(lines)
