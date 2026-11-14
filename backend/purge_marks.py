"""
The marks of the purge (1.125): what is printed on the bed before the real print starts and is not the part.

A purge line (an adaptive one next to the print area, the slicer's own, a blob), a skirt, a dropped blob: the local model
was trained on whole pictures labelled «failed» or «fine», and a thread of filament lying on the bed beside the part looks
to it like spaghetti. Seen at every look, for the whole print.

KlippEye keeps the picture of the bed taken when the print starts (heating, the bed still empty) and compares it with the
first picture of the real print. What changed on the bed, outside the parts (with a margin) and outside the toolhead and
the gantry (where they were in both pictures), are the marks of the purge. From then on, until the end of the print:
  - the local model judges the picture with those marks covered by the empty bed of the first picture;
  - the motion detection ignores them (a purge line pulled off by hand is no failure).
Only with a usable camera calibration and the print's objects: without them the part's own first layer could not be told
apart from a purge line, and hiding it would hide a part come off.

Only numpy and the OpenCV module the caller passes.
"""

DIFF = 28          # a point whose grey level changed more than this between the two pictures is changed
PART_GUARD = 0.02  # a margin around the parts (fraction of the picture's width): their first layer is never a mark
MIN_PX = 30        # a changed patch smaller than this (at the size compared) is noise
GROW = 0.012       # the marks are grown by this much (fraction of the width): their edge and shadow too
MAX_SHARE = 0.12   # more than this share of the bed changed: the light changed, not a purge; nothing is marked


def find(cv2, np, before, after, watched, expected, machine=None):
    """The marks of the purge at the size of `watched` (uint8, 255 = a mark), or None (nothing found, or not trusted).
    before, after: the two pictures (BGR, any size); watched: the bed; expected: the parts; machine: the toolhead and
    the gantry in both pictures (or None). Masks at one size."""
    if before is None or after is None or watched is None or expected is None:
        return None
    height, width = watched.shape[:2]

    def grey(picture):
        small = cv2.resize(picture, (width, height), interpolation=cv2.INTER_AREA)
        return cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)

    changed = cv2.threshold(cv2.absdiff(grey(before), grey(after)), DIFF, 255, cv2.THRESH_BINARY)[1]
    changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    guard = max(3, int(round(PART_GUARD * width)))
    allowed = watched.copy()
    allowed[cv2.dilate(expected, np.ones((guard, guard), np.uint8)) > 0] = 0
    if machine is not None:
        if machine.shape[:2] != (height, width):
            machine = cv2.resize(machine, (width, height), interpolation=cv2.INTER_NEAREST)
        allowed[machine > 0] = 0
    bed = cv2.countNonZero(allowed)
    if bed < 100:
        return None
    marks = cv2.bitwise_and(changed, allowed)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(marks)
    keep = np.zeros_like(marks)
    for index in range(1, count):
        if stats[index, cv2.CC_STAT_AREA] >= MIN_PX:
            keep[labels == index] = 255
    found = cv2.countNonZero(keep)
    if not found or found > MAX_SHARE * bed:
        return None
    grow = max(3, int(round(GROW * width)))
    return cv2.bitwise_and(cv2.dilate(keep, np.ones((grow, grow), np.uint8)), watched)


def cover(cv2, np, frame, before, marks):
    """`frame` with the marks covered by the same points of `before` (the empty bed): a new picture, `frame` unchanged."""
    if marks is None or before is None or frame is None:
        return frame
    height, width = frame.shape[:2]
    big = cv2.resize(marks, (width, height), interpolation=cv2.INTER_NEAREST) if marks.shape[:2] != (height, width) else marks
    empty = cv2.resize(before, (width, height), interpolation=cv2.INTER_AREA) if before.shape[:2] != (height, width) else before
    out = frame.copy()
    out[big > 0] = empty[big > 0]
    return out


def share(np, marks, watched):
    """How much of the bed the marks take (0..1)."""
    if marks is None or watched is None:
        return 0.0
    bed = float(np.count_nonzero(watched))
    return float(np.count_nonzero(marks)) / bed if bed else 0.0
