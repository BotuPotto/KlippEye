"""
Finding the nozzle tip in the camera picture by itself (roadmap phase 6a, part 5, release 1.29.0): the "automatic" part of the
camera calibration.

The person taps the nozzle tip once, by hand (with the magnified view): KlippEye keeps a small picture around that point, the
TEMPLATE. At every other point it looks for the same picture again:
  1. where to look: the toolhead is the part of the picture that changes when the toolhead moves away (the printer moves it
     sideways for a moment and back); the search is limited to that region, so the bed or the frame cannot be taken for it;
  2. what: the template, at a few sizes (the nozzle looks bigger near the camera, smaller far away), compared with the picture
     (normalised correlation: light and contrast do not matter much);
  3. the best match above MIN_SCORE is the proposal; the person can accept it or tap the point again. "Calculate" then shows
     any proposal that does not fit the others (the red numbers), to be redone by hand.
Pictures are numpy arrays as OpenCV decodes them (BGR); positions are fractions of the picture (u right, v down).
"""

TEMPLATE_FRACTION = 0.06     # the template's side, as a fraction of the picture width (about 32 px on 540)
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


def moving_region(cv2, np, here, away):
    """Where the picture `here` differs from `away` (the toolhead moved off): a 0/255 mask, grown a little; None when almost
    nothing changed (the toolhead is out of view, or the camera did not take a new picture)."""
    a, b = _gray(cv2, here), _gray(cv2, away)
    if a.shape != b.shape:
        return None
    diff = cv2.absdiff(cv2.GaussianBlur(a, (5, 5), 0), cv2.GaussianBlur(b, (5, 5), 0))
    _, mask = cv2.threshold(diff, DIFF_LEVEL, 255, cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    if cv2.countNonZero(mask) < MIN_REGION * mask.size:
        return None
    grow = max(3, int(round(REGION_GROW * mask.shape[1])))
    return cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1)))


def find(cv2, np, image, patch, region=None):
    """The template `patch` in `image`, at the sizes of SCALES, inside `region` when given.
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
        _, score, _, (x, y) = cv2.minMaxLoc(scores)
        if score > best["score"]:
            best = {"found": False, "score": float(score), "u": (x + half) / float(w), "v": (y + half) / float(h), "scale": scale}
    best["found"] = best["score"] >= MIN_SCORE
    if best["u"] is not None:
        best["u"], best["v"], best["score"] = round(best["u"], 5), round(best["v"], 5), round(best["score"], 3)
    return best
