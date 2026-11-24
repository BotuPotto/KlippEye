#!/usr/bin/env python3
"""A delta has no gantry, but machine_shape.json gets the default gantry «on» for every printer (seen in run_configs.py:
the delta's machine_shape.json has gantry.on = true). With a calibrated camera, how much of the round bed does the
monitor leave out at one check, toolhead alone vs toolhead + the default gantry?

    python3 -I .superpowers/audit/proofs/X2/delta_gantry.py
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import camera_model as cm  # noqa: E402
import machine_masks  # noqa: E402

W, H = 1280, 720


def look_at(cam, target):
    fwd = np.asarray(target, float) - cam
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    rot = np.stack([right, np.cross(fwd, right), fwd])
    return rot, -rot @ cam


# a delta, bed radius 120 mm centred on 0,0; camera on the frame in front, looking at the bed centre
ROT, T = look_at(np.array([0.0, -260.0, 220.0]), [0.0, 0.0, 0.0])
CAL = {"params": [900.0, W / 2.0, H / 2.0, 0.0, 0.0] + list(cm.rotation_to_vector(ROT)) + list(T), "model": "pinhole", "width": W,
       "height": H, "quality": "good", "z_moves": "toolhead"}
shape = machine_masks.clean_shape({})          # what a new install gets: the defaults
x_range = [-120.0, 120.0]                # what limits() stores for this delta (run_configs.py: x_range [-120, 120])
print("default gantry:", shape["gantry"])

# the round bed in the picture
bed = np.zeros((H, W), np.uint8)
ring = [[120 * np.cos(a), 120 * np.sin(a), 0.0] for a in np.linspace(0, 2 * np.pi, 120)]
pix, _ = cm.project(CAL, ring)
cv2.fillPoly(bed, [np.array([[u * W, v * H] for u, v in pix], np.int32)], 255)
bed_px = int((bed > 0).sum())

for y in (-60.0, 0.0, 60.0):
    pos = [[0.0, y, 5.0], [10.0, y, 5.0]]   # the nozzle at the bed's middle, 5 mm up, two readings of one check
    tool_only = machine_masks.mask(cv2, np, CAL, dict(shape, gantry=dict(shape["gantry"], on=False)), pos, W, H, x_range)
    with_gantry = machine_masks.mask(cv2, np, CAL, shape, pos, W, H, x_range)
    a = int(((tool_only > 0) & (bed > 0)).sum()) if tool_only is not None else 0
    b = int(((with_gantry > 0) & (bed > 0)).sum()) if with_gantry is not None else 0
    print("nozzle at y=%+.0f: bed left out, toolhead only %.1f%%, with the default gantry %.1f%%" % (y, 100.0 * a / bed_px, 100.0 * b / bed_px))
