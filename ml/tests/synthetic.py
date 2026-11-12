"""Synthetic pictures for the tests of the local model's tools: a «bed» with tidy parts (fine) or with a tangle of lines
(spaghetti), a YOLO dataset, and a KlippEye data folder with a fine and a failed recording and a reviewed print."""
import json
import os
import random

import cv2
import numpy as np


def picture(failed, rng, w=320, h=214):
    image = np.full((h, w, 3), (rng.randint(40, 70),) * 3, np.uint8)
    cv2.rectangle(image, (10, h - 60), (w - 10, h - 10), (90, 90, 95), -1)                     # the bed
    for _ in range(rng.randint(1, 3)):                                                            # tidy parts
        x, y = rng.randint(30, w - 90), rng.randint(h - 110, h - 70)
        cv2.rectangle(image, (x, y), (x + rng.randint(25, 60), h - 30), (rng.randint(150, 230), 120, 60), -1)
    box = None
    if failed:                                                                                     # a tangle of thin lines
        cx, cy = rng.randint(70, w - 70), rng.randint(70, h - 50)
        points = [(cx + rng.randint(-50, 50), cy + rng.randint(-35, 35)) for _ in range(40)]
        for a, b in zip(points, points[1:]):
            cv2.line(image, a, b, (230, 230, 230), 1, cv2.LINE_AA)
        box = ((cx) / w, (cy) / h, 100 / w, 70 / h)
    noise = rng.randint(3, 9)
    image = cv2.add(image, np.random.default_rng(rng.randint(0, 10 ** 6)).integers(0, noise, image.shape, dtype=np.uint8))
    return image, box


def make(root, n=60, seed=3):
    rng = random.Random(seed)
    # a YOLO dataset: class 0 spaghetti, 1 print (not a failure)
    yolo = os.path.join(root, "yolo")
    for split in ("train", "valid"):
        os.makedirs(os.path.join(yolo, split, "images"), exist_ok=True)
        os.makedirs(os.path.join(yolo, split, "labels"), exist_ok=True)
    open(os.path.join(yolo, "data.yaml"), "w").write("train: ../train/images\nval: ../valid/images\nnc: 2\nnames: ['spaghetti', 'print']\n")
    for i in range(n):
        split = "valid" if i % 5 == 0 else "train"
        failed = i % 2 == 0
        image, box = picture(failed, rng)
        name = "photo%03d_jpg.rf.%04d" % (i, rng.randint(0, 9999))
        cv2.imwrite(os.path.join(yolo, split, "images", name + ".jpg"), image)
        with open(os.path.join(yolo, split, "labels", name + ".txt"), "w") as handle:
            if box:
                handle.write("0 %.4f %.4f %.4f %.4f\n" % box)
            handle.write("1 0.5 0.8 0.3 0.2\n")
    # folders sorted by hand
    for label in ("ok", "fail"):
        folder = os.path.join(root, "sorted", "mine", label)
        os.makedirs(folder, exist_ok=True)
        for i in range(n // 3):
            cv2.imwrite(os.path.join(folder, "%s%02d.jpg" % (label, i)), picture(label == "fail", rng)[0])
    # KlippEye's data folder: a fine recording, a failed one, a reviewed print
    data = os.path.join(root, "klippeye")
    t0 = 1793000000.0
    for sid, outcome, failed_from in (("20261101-100000-good", "ok", None), ("20261101-120000-bad", "failed", 30)):
        folder = os.path.join(data, "recordings", sid)
        os.makedirs(folder, exist_ok=True)
        lines = []
        for k in range(1, 61):
            t = t0 + k * 10
            failed = failed_from is not None and k >= failed_from
            cv2.imwrite(os.path.join(folder, "%06d.jpg" % k), cv2.resize(picture(failed, rng)[0], (540, 360)))
            lines.append(json.dumps({"n": k, "t": t, "score": 1.0}))
        open(os.path.join(folder, "frames.jsonl"), "w").write("\n".join(lines) + "\n")
        json.dump({"id": sid, "file": sid + ".gcode", "started": t0, "ended": t0 + 610, "frames": 60,
                   "label": {"outcome": outcome, "failed_at": (t0 + failed_from * 10) if failed_from else None}},
                  open(os.path.join(folder, "session.json"), "w"))
    folder = os.path.join(data, "reviews", "20261102-090000-cube")
    os.makedirs(folder, exist_ok=True)
    thumbs = []
    for k in range(1, 13):
        cv2.imwrite(os.path.join(folder, "%04d.jpg" % k), picture(k >= 7, rng)[0])
        thumbs.append({"n": k, "t": t0 + k * 60, "progress": k * 8, "layer": k})
    json.dump({"id": "20261102-090000-cube", "file": "cube.gcode", "started": t0, "ended": t0 + 800, "end_state": "cancelled", "thumbs": thumbs,
               "answer": {"outcome": "failed", "problems": ["spaghetti"], "failed_at": t0 + 6.5 * 60, "time": 0}},
              open(os.path.join(folder, "review.json"), "w"))
    return {"yolo": yolo, "sorted": os.path.join(root, "sorted"), "klippeye": data}
