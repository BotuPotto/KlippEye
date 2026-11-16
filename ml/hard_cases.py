"""The look-alikes of a failure that are NOT failures, drawn on pictures of prints that went well: a purge line at the
edge of the bed (as KAMP's line purge or a slicer's prime line draws it), a purge blob, a single loose strand, the
outline of a brim or a skirt. The public collections have almost none of them, so the model learned «a line of filament
on the bed = spaghetti». Each drawn picture is labelled «fine».

So that the model cannot learn «something drawn = fine» instead, the same kind of drawing is also put on some failed
pictures, which stay «failed» (ml/datasets.py --hard-cases).

Only OpenCV and NumPy: what is drawn is random but repeatable (a seed per picture)."""
import math
import os
import random

KINDS = ("purge_line", "purge_blob", "strand", "brim")
# filament colours: the usual ones, bright and dark (black and dark filament are known to give false alarms)
COLOURS = [(30, 30, 30), (235, 235, 235), (40, 40, 200), (200, 80, 30), (40, 160, 40), (20, 140, 240), (160, 60, 160),
           (60, 200, 230), (120, 120, 120), (30, 90, 160), (200, 200, 60), (90, 50, 30)]


def _shade(colour, k):
    return tuple(int(max(0, min(255, c * k))) for c in colour)


def _blend(image, layer, mask, cv2, np, softness):
    """`layer` over `image` where `mask` is, with soft edges (no hard border the model could learn)."""
    k = max(1, int(softness) | 1)
    alpha = cv2.GaussianBlur(mask.astype(np.float32) / 255.0, (k, k), 0)[..., None] * 0.95
    return (image * (1 - alpha) + layer * alpha).astype(np.uint8)


def _bed_point(rng, w, h):
    """A place on the lower part of the picture, where the bed usually is."""
    return rng.uniform(0.08, 0.92) * w, rng.uniform(0.45, 0.95) * h


def _thick_line(layer, mask, points, width, colour, cv2, np):
    pts = np.array(points, np.int32).reshape(-1, 1, 2)
    cv2.polylines(layer, [pts], False, _shade(colour, 0.75), width + 2, cv2.LINE_AA)
    cv2.polylines(layer, [pts], False, colour, width, cv2.LINE_AA)
    cv2.polylines(layer, [pts], False, _shade(colour, 1.35), max(1, width // 3), cv2.LINE_AA)   # the shine on top of a round line
    cv2.polylines(mask, [pts], False, 255, width + 2, cv2.LINE_AA)


def draw(image, kind, seed, cv2, np):
    """A copy of `image` (BGR) with one look-alike of the given kind drawn on it."""
    rng = random.Random(seed)
    h, w = image.shape[:2]
    side = min(w, h)
    layer = image.copy()
    mask = np.zeros((h, w), np.uint8)
    colour = rng.choice(COLOURS)
    if kind == "purge_line":   # straight, along an edge of the bed, one or two lines side by side
        width = max(2, int(side * rng.uniform(0.008, 0.02)))
        length = w * rng.uniform(0.2, 0.6)
        x0 = rng.uniform(0.05, 0.95 - length / w) * w
        y0 = rng.uniform(0.6, 0.95) * h
        tilt = rng.uniform(-0.12, 0.12)
        for n in range(rng.choice((1, 1, 2))):
            dy = n * width * 1.6
            steps = 12
            points = [(x0 + length * i / steps, y0 + dy + tilt * length * i / steps + rng.uniform(-0.3, 0.3) * width) for i in range(steps + 1)]
            _thick_line(layer, mask, points, width, colour, cv2, np)
        if rng.random() < 0.5:   # the small blob where the line starts
            cv2.circle(layer, (int(x0), int(y0)), int(width * 1.8), colour, -1, cv2.LINE_AA)
            cv2.circle(mask, (int(x0), int(y0)), int(width * 1.8), 255, -1, cv2.LINE_AA)
    elif kind == "purge_blob":   # a round heap, lighter on top
        cx, cy = _bed_point(rng, w, h)
        r = side * rng.uniform(0.02, 0.06)
        points = []
        for i in range(18):
            a = 2 * math.pi * i / 18
            k = rng.uniform(0.75, 1.15)
            points.append((cx + math.cos(a) * r * k, cy + math.sin(a) * r * k * 0.7))
        pts = np.array(points, np.int32)
        cv2.fillPoly(layer, [pts], colour, cv2.LINE_AA)
        cv2.ellipse(layer, (int(cx - r * 0.2), int(cy - r * 0.25)), (max(1, int(r * 0.45)), max(1, int(r * 0.25))), 0, 0, 360, _shade(colour, 1.4), -1, cv2.LINE_AA)
        cv2.fillPoly(mask, [pts], 255, cv2.LINE_AA)
    elif kind == "strand":   # one thin loose thread, gently curved (a single one: not a tangle)
        width = max(1, int(side * rng.uniform(0.002, 0.005)))
        x0, y0 = _bed_point(rng, w, h)
        length = side * rng.uniform(0.15, 0.4)
        a = rng.uniform(0, 2 * math.pi)
        bend = rng.uniform(-0.6, 0.6)
        points = []
        for i in range(25):
            t = i / 24.0
            angle = a + bend * t
            points.append((x0 + math.cos(angle) * length * t, y0 + math.sin(angle) * length * t * 0.6))
        _thick_line(layer, mask, points, width, colour, cv2, np)
    else:   # "brim": the thin outline of a brim or skirt around a part
        width = max(1, int(side * rng.uniform(0.004, 0.01)))
        cx, cy = _bed_point(rng, w, h)
        rw, rh = side * rng.uniform(0.1, 0.3), side * rng.uniform(0.05, 0.18)
        for ring in range(rng.choice((1, 2, 3))):
            grow = ring * width * 1.5
            box = [(cx - rw - grow, cy - rh - grow), (cx + rw + grow, cy - rh - grow), (cx + rw + grow, cy + rh + grow), (cx - rw - grow, cy + rh + grow), (cx - rw - grow, cy - rh - grow)]
            _thick_line(layer, mask, box, width, colour, cv2, np)
    layer = cv2.GaussianBlur(layer, (3, 3), 0) if rng.random() < 0.5 else layer   # as soft as a real camera
    return _blend(image, layer, mask, cv2, np, softness=max(3, side * 0.006))


def make(rows, out, share, cv2, np, seed=11, on_failed=0.15):
    """Look-alikes drawn on a share of the fine pictures (labelled fine) and on `on_failed` as many failed ones (still
    failed). rows: (path, label, group, source, ...) as ml/datasets.py makes them. -> the new rows (same group as the
    picture they come from, so a picture and its copy are never one in training and one in measuring)."""
    os.makedirs(out, exist_ok=True)
    rng = random.Random(seed)
    fine = [r for r in rows if r[1] == 0]
    failed = [r for r in rows if r[1] == 1]
    picked = [(r, 0) for r in rng.sample(fine, int(len(fine) * share))]
    picked += [(r, 1) for r in rng.sample(failed, min(len(failed), int(len(fine) * share * on_failed)))]
    new = []
    for n, (row, label) in enumerate(picked):
        image = cv2.imread(row[0])
        if image is None or min(image.shape[:2]) < 48:
            continue
        kind = KINDS[n % len(KINDS)]
        drawn = draw(image, kind, "%s:%d" % (row[0], seed), cv2, np)
        path = os.path.join(out, "%06d_%s.jpg" % (n, kind))
        cv2.imwrite(path, drawn, [cv2.IMWRITE_JPEG_QUALITY, 90])
        new.append((path, label, row[2], "hard-" + kind))
    return new
