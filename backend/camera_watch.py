"""
Has the camera moved since it was calibrated? (roadmap phase 4: "a calibration is valid until the camera moves")

When the calibration is saved, a picture of the camera is kept (camera_reference.jpg). Later a new picture is compared with
it: the corners and edges that are found in both (OpenCV ORB features) are matched, and the shift that most of them share
(RANSAC, so the toolhead, the part and the reflections that changed do not count) tells whether the camera moved:
  * "ok"       most features are where they were (shift below MOVED_PX);
  * "moved"    they all moved together: the calibration no longer fits the picture;
  * "unknown"  too few features in common to say (dark picture, light off, lens covered): nothing is concluded.
Pixels are those of a 960 px wide copy of the picture, whatever the camera's resolution.
"""
import math

WORK_WIDTH = 960
MOVED_PX = 6.0        # at 960 px wide: about 12 px on a 1920 px picture
MOVED_DEGREES = 0.6
MIN_INLIERS = 25
CORRECT_MAX_PX = 48.0       # 1.127: a move up to this (at 960 px wide: 5% of the picture)...
CORRECT_MAX_DEGREES = 3.0   # ...and this much turned is corrected by itself; more: calibrate again
AGREE_PX = 3.0              # two looks agree when the centre goes to places this close...
AGREE_DEGREES = 0.4         # ...and they are turned about the same


def small(result):
    """Whether a "moved" look is small enough to be corrected (1.127)."""
    return (result.get("state") == "moved" and result.get("matrix") is not None and (result.get("shift_px") or 0) <= CORRECT_MAX_PX
            and abs(result.get("rotation_deg") or 0) <= CORRECT_MAX_DEGREES)


def agree(one, other):
    """Whether two looks found the same movement (centre within AGREE_PX at 960 px wide, rotation within AGREE_DEGREES)."""
    if not one or not other or one.get("matrix") is None or other.get("matrix") is None:
        return False
    a, b = one["matrix"], other["matrix"]
    du = (a[0][0] * 0.5 + a[0][1] * 0.5 + a[0][2]) - (b[0][0] * 0.5 + b[0][1] * 0.5 + b[0][2])
    dv = (a[1][0] * 0.5 + a[1][1] * 0.5 + a[1][2]) - (b[1][0] * 0.5 + b[1][1] * 0.5 + b[1][2])
    return math.hypot(du * WORK_WIDTH, dv * WORK_WIDTH) <= AGREE_PX and abs((one.get("rotation_deg") or 0) - (other.get("rotation_deg") or 0)) <= AGREE_DEGREES


def apply(matrix, uv):
    """Points (fractions, N x 2) moved by a correction matrix (fractions)."""
    return [[matrix[0][0] * u + matrix[0][1] * v + matrix[0][2], matrix[1][0] * u + matrix[1][1] * v + matrix[1][2]] for u, v in uv]


def _prepare(cv2, image):
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scale = WORK_WIDTH / float(gray.shape[1])
    gray = cv2.resize(gray, (WORK_WIDTH, max(1, int(round(gray.shape[0] * scale)))), interpolation=cv2.INTER_AREA)
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)


def compare(cv2, np, reference, current):
    """-> {"state": "ok" | "moved" | "unknown", "shift_px", "rotation_deg", "inliers", "matches"}"""
    ref, cur = _prepare(cv2, reference), _prepare(cv2, current)
    if ref.shape != cur.shape:
        return {"state": "moved", "shift_px": None, "rotation_deg": None, "inliers": 0, "matches": 0, "why": "the picture has another size"}
    orb = cv2.ORB_create(nfeatures=1500, fastThreshold=12)
    k1, d1 = orb.detectAndCompute(ref, None)
    k2, d2 = orb.detectAndCompute(cur, None)
    if d1 is None or d2 is None or len(k1) < MIN_INLIERS or len(k2) < MIN_INLIERS:
        return {"state": "unknown", "shift_px": None, "rotation_deg": None, "inliers": 0, "matches": 0, "why": "too few details in the picture"}
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs = matcher.knnMatch(d1, d2, k=2)
    good = [m for m, *rest in (p for p in pairs if len(p) >= 1) if not rest or m.distance < 0.8 * rest[0].distance]
    if len(good) < MIN_INLIERS:
        return {"state": "unknown", "shift_px": None, "rotation_deg": None, "inliers": 0, "matches": len(good), "why": "too few details in common"}
    src = np.float32([k1[m.queryIdx].pt for m in good])
    dst = np.float32([k2[m.trainIdx].pt for m in good])
    # the details that did not move at all: when most of the scene is still, the camera is still
    still = int(np.sum(np.linalg.norm(dst - src, axis=1) < 2.0))
    matrix, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0, maxIters=2000)
    if matrix is None or inliers is None:
        return {"state": "unknown", "shift_px": None, "rotation_deg": None, "inliers": 0, "matches": len(good), "why": "no common movement found"}
    count = int(inliers.sum())
    rotation = math.degrees(math.atan2(matrix[1, 0], matrix[0, 0]))
    # how far the centre of the picture goes with that movement
    h, w = ref.shape
    centre = np.array([w / 2.0, h / 2.0, 1.0])
    shift = float(np.linalg.norm(matrix @ centre - centre[:2]))
    # 1.127: the movement as fractions of the picture (u' = a u + b v + c, v' = d u + e v + f), to correct a small one
    sx, sy = float(w), float(h)
    fractions = [[float(matrix[0, 0]), float(matrix[0, 1]) * sy / sx, float(matrix[0, 2]) / sx],
                 [float(matrix[1, 0]) * sx / sy, float(matrix[1, 1]), float(matrix[1, 2]) / sy]]
    result = {"shift_px": round(shift, 1), "rotation_deg": round(rotation, 2), "inliers": count, "matches": len(good), "still": still,
              "matrix": [[round(v, 6) for v in row] for row in fractions]}
    if still >= MIN_INLIERS and still >= 0.5 * count:
        return dict(result, state="ok")
    if count < MIN_INLIERS:
        return dict(result, state="unknown", why="too few details agree")
    moved = shift > MOVED_PX or abs(rotation) > MOVED_DEGREES
    return dict(result, state="moved" if moved else "ok")
