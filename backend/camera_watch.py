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
    result = {"shift_px": round(shift, 1), "rotation_deg": round(rotation, 2), "inliers": count, "matches": len(good), "still": still}
    if still >= MIN_INLIERS and still >= 0.5 * count:
        return dict(result, state="ok")
    if count < MIN_INLIERS:
        return dict(result, state="unknown", why="too few details agree")
    moved = shift > MOVED_PX or abs(rotation) > MOVED_DEGREES
    return dict(result, state="moved" if moved else "ok")
