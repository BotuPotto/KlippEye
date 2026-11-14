"""
Finding the nozzle tip in the camera picture by itself (roadmap phase 6a, part 5, release 1.29.0): the "automatic" part of the
camera calibration.

The person taps the nozzle tip once, by hand (with the magnified view): KlippEye keeps a small picture around that point, the
TEMPLATE. At every other point it looks for the same picture again:
  1. where to look: the toolhead is the part of the picture that changes when the toolhead moves away (the printer moves it
     to two places aside for a moment and back: what changed against both is the toolhead where it was); the search is
     limited to that region, so a marker on the bed or the frame cannot be taken for it;
  2. what: the template, at a few sizes (the nozzle looks bigger near the camera, smaller far away), compared with the picture
     (normalised correlation: light and contrast do not matter much);
  3. the best match above MIN_SCORE is the proposal; the person can accept it or tap the point again. "Calculate" then shows
     any proposal that does not fit the others (the red numbers), to be redone by hand.
Pictures are numpy arrays as OpenCV decodes them (BGR); positions are fractions of the picture (u right, v down).
"""

TEMPLATE_FRACTION = 0.03     # the template's side, as a fraction of the picture width (about 16 px on 540, 38 on 1280): the tip, little around it
SCALES = (0.6, 0.7, 0.8, 0.9, 1.0, 1.12, 1.25, 1.4, 1.6)
MIN_SCORE = 0.55             # below this the match is not trusted: the point is left to the person
DIFF_LEVEL = 18              # grey levels: what counts as "changed" between two pictures
REGION_GROW = 0.04           # the changed region is grown by this fraction of the width (the tip is at its edge)
MIN_REGION = 0.002           # a changed region smaller than this (fraction of the picture) means the toolhead did not show


def _gray(cv2, image):
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image


def template(cv2, np, image, u, v):
    """The small grey picture around (u, v), centred on it. -> uint8 array (square, odd side) or None at the border."""
    gray = _gray(cv2, image)
    h, w = gray.shape[:2]
    half = max(6, int(round(TEMPLATE_FRACTION * w / 2)))
    x, y = int(round(u * w)), int(round(v * h))
    if x - half < 0 or y - half < 0 or x + half + 1 > w or y + half + 1 > h:
        return None
    return gray[y - half:y + half + 1, x - half:x + half + 1].copy()


def _changed(cv2, np, here, away):
    a, b = _gray(cv2, here), _gray(cv2, away)
    if a.shape != b.shape:
        return None
    diff = cv2.absdiff(cv2.GaussianBlur(a, (5, 5), 0), cv2.GaussianBlur(b, (5, 5), 0))
    _, mask = cv2.threshold(diff, DIFF_LEVEL, 255, cv2.THRESH_BINARY)
    return mask


def toolhead_region(cv2, np, here, aways):
    """Where the toolhead is in `here`: what differs from EVERY picture of `aways` (the toolhead moved to other places; against
    one picture only, the place it went to would count too), cleaned and grown a little (the tip is at the edge).
    -> a 0/255 mask, or None when almost nothing changed (the toolhead out of view, or the camera did not take a new picture)."""
    masks = [m for m in (_changed(cv2, np, here, away) for away in aways) if m is not None]
    if not masks:
        return None
    mask = masks[0]
    for other in masks[1:]:
        mask = cv2.bitwise_and(mask, other)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    if cv2.countNonZero(mask) < MIN_REGION * mask.size:
        return None
    grow = max(3, int(round(REGION_GROW * mask.shape[1])))
    return cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1)))


NEAR_COST = 0.3               # 1.128: a match at the edge of the window counts this much less than one where it was expected


def find(cv2, np, image, patch, region=None, near=None):
    """The template `patch` in `image`, at the sizes of SCALES, inside `region` when given.
    near (1.128): (u, v, radius) where it is expected: of two matches alike, the nearer wins (a reflection next to the tip).
    -> {"found": bool, "u", "v", "score", "scale"} (u, v: where the centre of the template is: the tip)."""
    gray = _gray(cv2, image)
    h, w = gray.shape[:2]
    best = {"found": False, "score": -1.0, "u": None, "v": None, "scale": None}
    for scale in SCALES:
        side = int(round(patch.shape[0] * scale)) | 1
        if side < 7 or side >= min(h, w):
            continue
        tpl = cv2.resize(patch, (side, side), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        if float(tpl.std()) < 2.0:   # a flat template matches anything
            continue
        scores = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
        half = side // 2
        if region is not None:
            inside = region[half:half + scores.shape[0], half:half + scores.shape[1]] > 0
            scores = np.where(inside, scores, -1.0)
        ranked = scores
        if near is not None:
            ys, xs = np.mgrid[0:scores.shape[0], 0:scores.shape[1]]
            far = ((xs + half - near[0] * w) ** 2 + (ys + half - near[1] * h) ** 2) / float((near[2] * w) ** 2)
            ranked = scores - NEAR_COST * far
        _, rank, _, (x, y) = cv2.minMaxLoc(ranked.astype(np.float32))
        score = float(scores[y, x])
        if best.get("rank", -9.0) < rank:
            best = {"found": False, "score": score, "u": (x + half) / float(w), "v": (y + half) / float(h), "scale": scale, "rank": rank}
    best.pop("rank", None)
    best["found"] = best["score"] >= MIN_SCORE
    if best["u"] is not None:
        best["u"], best["v"], best["score"] = round(best["u"], 5), round(best["v"], 5), round(best["score"], 3)
    return best
