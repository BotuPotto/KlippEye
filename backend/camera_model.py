"""
The camera model of KlippEye's AI monitor (roadmap phase 4): where a point of the printer (X, Y, Z in mm, the coordinates
Klipper uses) appears in the camera picture. With it the monitor can draw the toolhead and the gantry over the picture
(and leave them out of the comparison) and know where the part is supposed to be.

How it is found ("Calibrate the camera" in the dashboard): the nozzle is moved to about twelve points at two heights and
each time the person taps the tip of the nozzle in the picture. From those pairs (point in mm -> point in the picture) this
file finds the camera: its position and direction, the focal length, the centre of the picture and the bending of the lens.
Points at two heights are needed: four points on the bed are not enough for a point in the air (the nozzle tip is one).

Two lens models are tried and the better one is kept:
  * "fisheye" (equidistant, like OpenCV's cv2.fisheye): r = f * theta * (1 + k1 theta^2 + k2 theta^4), for wide lenses;
  * "pinhole" with radial distortion: r = f * tan(theta) * (1 + k1 tan^2 + k2 tan^4), for ordinary ones.
Everything is numpy only: no OpenCV needed, and the same numbers on the Raspberry and in the tests.

Pixel coordinates are those of the camera's own picture (width W, height H); the model also answers in fractions of the
picture (0..1), which is what the dashboard and the monitor (which shrinks the picture) use.
"""
import math

try:
    import numpy as np
except ImportError:  # the backend still starts without it (1.23.0): the calibration says what to install
    np = None

MODELS = ("fisheye", "pinhole")
MIN_POINTS = 8
GOOD_RMS = 0.006   # fraction of the picture diagonal: about 13 px on a 1920x1080 picture
FAIR_RMS = 0.012


def rodrigues(rvec):
    """Rotation vector -> rotation matrix."""
    rvec = np.asarray(rvec, float)
    theta = float(np.linalg.norm(rvec))
    if theta < 1e-12:
        return np.eye(3)
    k = rvec / theta
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(theta) * kx + (1 - math.cos(theta)) * kx @ kx


def rotation_to_vector(rot):
    """Rotation matrix -> rotation vector."""
    cos = max(-1.0, min(1.0, (np.trace(rot) - 1) / 2))
    theta = math.acos(cos)
    if theta < 1e-9:
        return np.zeros(3)
    if math.pi - theta < 1e-6:  # 180 degrees: the axis from the symmetric part
        axis = np.sqrt(np.maximum((np.diag(rot) + 1) / 2, 0))
        axis[1] = math.copysign(axis[1], rot[0, 1] + rot[1, 0]) if axis[0] else axis[1]
        axis[2] = math.copysign(axis[2], rot[0, 2] + rot[2, 0]) if axis[0] else axis[2]
        return axis / np.linalg.norm(axis) * theta
    v = np.array([rot[2, 1] - rot[1, 2], rot[0, 2] - rot[2, 0], rot[1, 0] - rot[0, 1]])
    return v / (2 * math.sin(theta)) * theta


def project_params(params, points, model):
    """params = [f, cx, cy, k1, k2, rx, ry, rz, tx, ty, tz]; points (N, 3) in mm -> (N, 2) pixels and (N,) depth."""
    f, cx, cy, k1, k2 = params[:5]
    rot = rodrigues(params[5:8])
    cam = np.asarray(points, float) @ rot.T + params[8:11]
    z = cam[:, 2]
    zs = np.where(np.abs(z) < 1e-9, 1e-9, z)
    a, b = cam[:, 0] / zs, cam[:, 1] / zs
    r = np.sqrt(a * a + b * b)
    if model == "fisheye":
        theta = np.arctan2(np.sqrt(cam[:, 0] ** 2 + cam[:, 1] ** 2), z)  # also right behind 90 degrees
        rd = theta * (1 + k1 * theta ** 2 + k2 * theta ** 4)
    else:
        rd = r * (1 + k1 * r ** 2 + k2 * r ** 4)
    scale = np.where(r > 1e-12, rd / np.where(r > 1e-12, r, 1), 1.0)
    u = f * a * scale + cx
    v = f * b * scale + cy
    return np.stack([u, v], axis=1), z


def _unproject_guess(pixels, f, cx, cy, model):
    """Pixels -> normalised pinhole coordinates (x/z, y/z), with no distortion other than the model's base."""
    d = (np.asarray(pixels, float) - [cx, cy]) / f
    rd = np.linalg.norm(d, axis=1)
    if model == "fisheye":
        theta = np.minimum(rd, math.radians(85))
        r = np.tan(theta)
    else:
        r = rd
    scale = np.where(rd > 1e-12, r / np.where(rd > 1e-12, rd, 1), 1.0)
    return d * scale[:, None]


def _pose_dlt(points, normalised):
    """Camera pose from >= 6 points (not all on a plane) and their normalised coordinates: R, t by the direct linear method."""
    rows = []
    for (x, y, z), (a, b) in zip(points, normalised):
        p = [x, y, z, 1.0]
        rows.append(p + [0, 0, 0, 0] + [-a * c for c in p])
        rows.append([0, 0, 0, 0] + p + [-b * c for c in p])
    _, _, vt = np.linalg.svd(np.asarray(rows))
    m = vt[-1].reshape(3, 4)
    rot, t = m[:, :3], m[:, 3]
    scale = np.cbrt(np.linalg.det(rot))
    if abs(scale) < 1e-12:
        raise ValueError("points on one plane")
    rot, t = rot / scale, t / scale
    u, _, vt2 = np.linalg.svd(rot)
    rot = u @ vt2
    if np.linalg.det(rot) < 0:
        rot, t = -rot, -t
    if np.mean(np.asarray(points) @ rot[2] + t[2]) < 0:  # the points must be in front of the camera
        rot = np.diag([-1, -1, 1]) @ rot
        t = np.diag([-1, -1, 1]) @ t
    return rot, t


def _residuals(params, points, pixels, model):
    projected, z = project_params(params, points, model)
    res = (projected - pixels).ravel()
    behind = np.repeat(z <= 0, 2)
    return np.where(behind, 1e4, res)


def _levenberg_marquardt(params, points, pixels, model, iterations=200):
    params = np.asarray(params, float)
    lam = 1e-3
    res = _residuals(params, points, pixels, model)
    cost = float(res @ res)
    steps = np.maximum(np.abs(params) * 1e-6, 1e-6)
    for _ in range(iterations):
        jac = np.empty((res.size, params.size))
        for i in range(params.size):
            d = np.zeros_like(params)
            d[i] = steps[i]
            jac[:, i] = (_residuals(params + d, points, pixels, model) - _residuals(params - d, points, pixels, model)) / (2 * steps[i])
        jtj, jtr = jac.T @ jac, jac.T @ res
        improved = False
        for _ in range(10):
            try:
                delta = np.linalg.solve(jtj + lam * np.diag(np.diag(jtj) + 1e-9), -jtr)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            trial = params + delta
            trial_res = _residuals(trial, points, pixels, model)
            trial_cost = float(trial_res @ trial_res)
            if trial_cost < cost:
                params, res, improved = trial, trial_res, True
                lam = max(lam / 3, 1e-9)
                done = cost - trial_cost < 1e-10 * max(cost, 1e-12)
                cost = trial_cost
                break
            lam *= 10
        if not improved or done:
            break
    return params, cost


def fit(points, pixels, width, height):
    """Finds the camera from pairs: points (N, 3) in mm, pixels (N, 2) in the picture (W x H).
    -> dict with the model, its parameters and how good it is (rms in pixels and as a fraction of the diagonal,
    the error of each point). Raises ValueError when it cannot be done (too few points, all on one plane...)."""
    points = np.asarray(points, float)
    pixels = np.asarray(pixels, float)
    if len(points) < MIN_POINTS:
        raise ValueError("at least 8 points are needed")
    if np.ptp(points[:, 2]) < 10:
        raise ValueError("the points must be at two heights at least 10 mm apart")
    if np.linalg.matrix_rank(points - points.mean(axis=0), tol=1e-6) < 3:
        raise ValueError("the points are all on one plane")
    best = None
    diag = math.hypot(width, height)
    for model in MODELS:
        # focal lengths to start from: very wide (fisheye ~180 degrees) to ordinary (~60 degrees)
        for f0 in (width / math.pi, width / 2.4, width / 1.6, width / 1.1):
            for k0 in (0.0, -0.1):
                start_center = (width / 2.0, height / 2.0)
                try:
                    norm = _unproject_guess(pixels, f0, *start_center, model)
                    rot, t = _pose_dlt(points, norm)
                except (ValueError, np.linalg.LinAlgError):
                    continue
                p0 = np.r_[f0, start_center, k0, 0.0, rotation_to_vector(rot), t]
                params, cost = _levenberg_marquardt(p0, points, pixels, model)
                projected, z = project_params(params, points, model)
                if np.any(z <= 0) or params[0] <= 0:
                    continue
                err = np.linalg.norm(projected - pixels, axis=1)
                rms = float(np.sqrt(np.mean(err ** 2)))
                if best is None or rms < best["rms_px"] - 1e-9:
                    best = {"model": model, "params": [float(x) for x in params], "rms_px": rms, "errors_px": [float(e) for e in err]}
    if best is None:
        raise ValueError("no camera fits these points: check that each tap is on the nozzle tip")
    best.update(width=int(width), height=int(height), points=len(points), rms=best["rms_px"] / diag,
                quality="good" if best["rms_px"] / diag <= GOOD_RMS else "fair" if best["rms_px"] / diag <= FAIR_RMS else "poor")
    best["camera_position"] = [float(x) for x in camera_position(best)]
    return best


def camera_position(calibration):
    """Where the camera is, in the printer's coordinates (mm)."""
    p = np.asarray(calibration["params"], float)
    rot = rodrigues(p[5:8])
    return -rot.T @ p[8:11]


def project(calibration, points):
    """Points (N, 3) in mm -> (N, 2) fractions of the picture (0..1, may fall outside), and (N,) True when in front of the camera."""
    pixels, z = project_params(np.asarray(calibration["params"], float), np.atleast_2d(np.asarray(points, float)), calibration["model"])
    return pixels / [calibration["width"], calibration["height"]], z > 0


def box_corners(x0, x1, y0, y1, z0, z1):
    return np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], float)


def convex_hull(points):
    """2D convex hull (Andrew's monotone chain): list of (x, y), counter-clockwise."""
    pts = sorted(set((round(float(x), 6), round(float(y), 6)) for x, y in points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def box_outline(calibration, corners, steps=4):
    """The outline in the picture (fractions, convex polygon) of a box given by its 8 corners. The edges are sampled
    (`steps` points each) so that the bending of a fisheye lens is followed. None when the box is behind the camera."""
    corners = np.asarray(corners, float)
    edges = []
    for i in range(8):
        for j in range(i + 1, 8):
            if np.sum(np.abs(corners[i] - corners[j]) > 1e-9) == 1:  # the 12 edges of the box
                for s in np.linspace(0, 1, steps + 1):
                    edges.append(corners[i] + (corners[j] - corners[i]) * s)
    uv, front = project(calibration, np.asarray(edges))
    if not np.any(front):
        return None
    return convex_hull(uv[front])
