"""
Collects the pictures the local model is trained on into one list (ml/work/manifest.csv): path, label (1 = failed print,
0 = fine), group (pictures of the same print or photo stay together in the split), source.

Sources, any number of each:
  --folders DIR    DIR/**/fail/*.jpg and DIR/**/ok/*.jpg (any picture format): pictures you sorted yourself.
  --auto DIR       every dataset ml/download.py put in DIR (ml/data): each one in YOLO format or in class folders.
  --yolo DIR       a dataset exported in YOLO format (Roboflow Universe → Download → «YOLOv8»): data.yaml with the class
                   names, train/valid/test with images/ and labels/. A picture with a box of a failure class is «failed»,
                   and each such box is also cut out with its surroundings (small spaghetti become large); a picture whose
                   boxes are only of a normal print (nozzle, part, print…) is «fine»; one with only defects of quality
                   (stringing, zits…) is left out; with --empty-is-ok a picture without boxes counts as «fine».
                   --fail-classes NAME,NAME... : the classes that are failures (default: by their names, see FAILURE).
  --classes DIR    a dataset of class folders (Roboflow «folder» export: train/<class>/*.jpg): the classes by their names.
  --klippeye DIR   KlippEye's data folder copied from the Raspberry (the folder with recordings/ and reviews/): the
                   labelled recordings and the answers to «How did the print go?». Fine prints give «fine» pictures; a
                   failed print gives «failed» pictures from FAILED_AFTER seconds after its moment on, «fine» before it.

Usage: python ml/datasets.py --yolo ~/data/spaghetti --klippeye ~/klippeye-data --out ml/work
"""
import argparse
import csv
import glob
import json
import os
import random
import re
import sys

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
# the classes of the datasets, by their names: a failure that ruins the print (what the monitor must catch), a defect of
# quality (the print goes on: left out, neither failed nor fine), a normal print or a part of the printer (fine)
FAILURE = re.compile(r"spag|fail|error|detach|blob|shift|warp|clog|nest|knot|collaps|broken|defect|bad|fault|anomal|adhes|curl|messy|mess", re.I)
QUALITY = re.compile(r"string|zit|under|over|gap|ring|ghost|crack|bridg|line|rough|elephant|seam|pillow|hair|z.?wobble|banding|burn", re.I)
NORMAL = re.compile(r"^(ok|good|normal|nominal|success\w*|fine|correct|no.?defect\w*|nozzle|print|printing|printed|object|part|parts|model|bed|extruder|"
                    r"extrusor|head|hotend|printhead|print.?head|toolhead|tool|nozzle.?tip|person|hand)$", re.I)


def kind_of(name, fail_classes=()):
    """-> 1 (a failure), 0 (fine: a normal print or a part of the printer), None (a defect of quality: left out)."""
    name = str(name).strip()
    if fail_classes:
        return 1 if name.lower() in fail_classes else 0 if NORMAL.match(name) else None
    if NORMAL.match(name):
        return 0
    if QUALITY.search(name) and not re.search(r"spag|detach|fail", name, re.I):
        return None
    return 1  # spaghetti, failure, error, defect… and names nobody knows: counted as failures
FAILED_AFTER = 60          # a failure is clear this many seconds after the moment the person chose
OK_EVERY = 4               # of a fine recording, one picture in OK_EVERY (they are much alike)
CROP_MARGIN = 0.6          # a box is cut out with this much of its size around it


def images_in(folder):
    return sorted(p for p in glob.glob(os.path.join(folder, "**", "*"), recursive=True) if p.lower().endswith(IMAGE_EXT))


def from_folders(root):
    rows = []
    for path in images_in(root):
        parts = [p.lower() for p in os.path.relpath(path, root).split(os.sep)[:-1]]
        label = 1 if "fail" in parts or "failed" in parts else 0 if "ok" in parts or "good" in parts else None
        if label is not None:
            rows.append((path, label, "folder:" + path, "folders"))
    return rows


def _yaml_names(text):
    """The class names of a YOLO data.yaml, without a YAML module: «names: [a, b]» or a «names:» list / mapping."""
    match = re.search(r"^names:\s*\[(.*?)\]", text, re.M | re.S)
    if match:
        return [n.strip().strip("'\"") for n in match.group(1).split(",") if n.strip()]
    # a block list may be indented or not («names:\n- a\n- b», as Roboflow writes it), or a mapping «  0: a»
    match = re.search(r"^names:[ \t]*\n((?:(?:[ \t]+\S.*|-[ \t].*)(?:\n|$))+)", text, re.M)
    names = []
    for line in (match.group(1).splitlines() if match else []):
        line = line.strip()
        if line.startswith("- "):
            names.append(line[2:].strip().strip("'\""))
        elif ":" in line:
            names.append(line.split(":", 1)[1].strip().strip("'\""))
    return names


def from_yolo(root, work, fail_classes, empty_is_ok, cv2):
    yaml = next(iter(glob.glob(os.path.join(root, "**", "data.yaml"), recursive=True)), None)
    names = _yaml_names(open(yaml, encoding="utf-8").read()) if yaml else []
    kinds = {i: kind_of(n, fail_classes) for i, n in enumerate(names)}
    failing = {i for i, k in kinds.items() if k == 1}
    quality = {i for i, k in kinds.items() if k is None}
    print("[yolo] %s: failures %s, quality (left out) %s, normal %s" % (
        os.path.basename(root.rstrip(os.sep)), [names[i] for i in sorted(failing)], [names[i] for i in sorted(quality)], [names[i] for i in sorted(kinds) if kinds[i] == 0]))
    rows = []
    crops = os.path.join(work, "crops")
    os.makedirs(crops, exist_ok=True)
    for path in images_in(root):
        if os.sep + "images" + os.sep not in path:
            continue
        label_file = os.path.splitext(path.replace(os.sep + "images" + os.sep, os.sep + "labels" + os.sep))[0] + ".txt"
        boxes = []
        if os.path.isfile(label_file):
            for line in open(label_file, encoding="utf-8"):
                parts = line.split()
                if len(parts) >= 5 and parts[0].isdigit():
                    values = [float(v) for v in parts[1:]]
                    if len(values) > 4:  # a polygon (segmentation): its bounding box
                        xs, ys = values[0::2], values[1::2]
                        values = [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(xs) - min(xs), max(ys) - min(ys)]
                    boxes.append((int(parts[0]), values[:4]))
        fails = [b for c, b in boxes if c in failing]
        group = "yolo:" + os.path.basename(path).split(".rf.")[0]   # Roboflow's augmented copies of one photo stay together
        if fails:
            rows.append((path, 1, group, "yolo"))
            image = cv2.imread(path) if cv2 is not None else None
            if image is not None:
                h, w = image.shape[:2]
                for k, (cx, cy, bw, bh) in enumerate(fails[:3]):
                    side = max(bw * w, bh * h) * (1 + 2 * CROP_MARGIN)
                    side = max(side, min(w, h) * 0.25)
                    x0, y0 = int(max(0, cx * w - side / 2)), int(max(0, cy * h - side / 2))
                    x1, y1 = int(min(w, cx * w + side / 2)), int(min(h, cy * h + side / 2))
                    if x1 - x0 > 16 and y1 - y0 > 16:
                        out = os.path.join(crops, "%s_%d.jpg" % (re.sub(r"[^A-Za-z0-9_.-]+", "_", os.path.basename(path))[:80], k))
                        cv2.imwrite(out, image[y0:y1, x0:x1])
                        rows.append((out, 1, group, "yolo-crop"))
        elif boxes and not [c for c, _ in boxes if c in quality]:
            rows.append((path, 0, group, "yolo"))   # only a normal print and the printer's parts
        elif not boxes and empty_is_ok:
            rows.append((path, 0, group, "yolo"))
    return rows


def from_classes(root, fail_classes=()):
    """A dataset of class folders: <root>/<split>/<class>/*.jpg (or <root>/<class>/*.jpg)."""
    rows, seen = [], {}
    for path in images_in(root):
        parent = os.path.basename(os.path.dirname(path))
        if parent.lower() in ("images", "labels"):
            continue
        kind = seen.setdefault(parent, kind_of(parent, fail_classes))
        if kind is not None:
            rows.append((path, kind, "cls:" + os.path.basename(path).split(".rf.")[0], "classes"))
    print("[classes] %s: %s" % (os.path.basename(root.rstrip(os.sep)), {k: ("failed" if v == 1 else "fine" if v == 0 else "left out") for k, v in seen.items()}))
    return rows


def from_auto(root, work, fail_classes, empty_is_ok, cv2):
    """Every dataset in `root` (one folder each, as ml/download.py writes them)."""
    rows = []
    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        if not os.path.isdir(folder):
            continue
        if glob.glob(os.path.join(folder, "**", "data.yaml"), recursive=True):
            rows += from_yolo(folder, work, fail_classes, empty_is_ok, cv2)
        else:
            rows += from_classes(folder, fail_classes)
    return rows


def from_klippeye(root):
    rows = []
    # the recordings with a label (Recordings → a print → «it went fine» / «it failed from here»)
    for session_file in glob.glob(os.path.join(root, "recordings", "*", "session.json")):
        folder = os.path.dirname(session_file)
        try:
            session = json.load(open(session_file, encoding="utf-8"))
            frames = [json.loads(line) for line in open(os.path.join(folder, "frames.jsonl"), encoding="utf-8") if line.strip()]
        except (OSError, ValueError):
            continue
        label = (session.get("label") or {})
        outcome, failed_at = label.get("outcome"), label.get("failed_at")
        if outcome not in ("ok", "failed"):
            continue
        for i, frame in enumerate(frames):
            path = os.path.join(folder, "%06d.jpg" % frame.get("n", 0))
            if not os.path.isfile(path):
                continue
            if outcome == "ok" or (failed_at is not None and frame.get("t", 0) < failed_at):
                if i % OK_EVERY == 0:
                    rows.append((path, 0, "rec:" + session.get("id", folder), "klippeye"))
            elif failed_at is not None and frame.get("t", 0) >= failed_at + FAILED_AFTER:
                rows.append((path, 1, "rec:" + session.get("id", folder), "klippeye"))
    # the answers to «How did the print go?» (their small pictures)
    for review_file in glob.glob(os.path.join(root, "reviews", "*", "review.json")):
        folder = os.path.dirname(review_file)
        try:
            review = json.load(open(review_file, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        answer = review.get("answer") or {}
        outcome, failed_at = answer.get("outcome"), answer.get("failed_at")
        if outcome not in ("ok", "failed"):
            continue
        for thumb in review.get("thumbs") or []:
            path = os.path.join(folder, "%04d.jpg" % thumb.get("n", 0))
            if not os.path.isfile(path):
                continue
            t = thumb.get("t", 0)
            if outcome == "ok" or (failed_at is not None and t < failed_at):
                rows.append((path, 0, "rev:" + review.get("id", folder), "klippeye"))
            elif failed_at is not None and t >= failed_at + FAILED_AFTER:
                rows.append((path, 1, "rev:" + review.get("id", folder), "klippeye"))
            # failed without a moment: which pictures show it is not known, they are left out
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--auto", action="append", default=[])
    parser.add_argument("--classes", action="append", default=[])
    parser.add_argument("--folders", action="append", default=[])
    parser.add_argument("--yolo", action="append", default=[])
    parser.add_argument("--klippeye", action="append", default=[])
    parser.add_argument("--fail-classes", default="")
    parser.add_argument("--empty-is-ok", action="store_true")
    parser.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))
    parser.add_argument("--val", type=float, default=0.15, help="the share of groups kept aside to measure the model")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    try:
        import cv2
    except ImportError:
        cv2 = None
        print("OpenCV not installed: the boxes of YOLO datasets are not cut out (pip install opencv-python-headless)")
    os.makedirs(args.out, exist_ok=True)
    rows = []
    for folder in args.folders:
        rows += from_folders(folder)
    fail_classes = {c.strip().lower() for c in args.fail_classes.split(",") if c.strip()}
    for folder in args.yolo:
        rows += from_yolo(folder, args.out, fail_classes, args.empty_is_ok, cv2)
    for folder in args.classes:
        rows += from_classes(folder, fail_classes)
    for folder in args.auto:
        rows += from_auto(folder, args.out, fail_classes, args.empty_is_ok, cv2)
    for folder in args.klippeye:
        rows += from_klippeye(folder)
    if not rows:
        print("No pictures found: see --help for the folders each source expects.")
        return 1
    groups = sorted({r[2] for r in rows})
    random.Random(args.seed).shuffle(groups)
    held = set(groups[: max(1, int(len(groups) * args.val))]) if len(groups) > 1 else set()
    path = os.path.join(args.out, "manifest.csv")
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["path", "label", "group", "source", "split"])
        for row in rows:
            writer.writerow(list(row) + ["val" if row[2] in held else "train"])
    fails = sum(1 for r in rows if r[1] == 1)
    print("%d pictures (%d failed, %d fine) in %d groups -> %s" % (len(rows), fails, len(rows) - fails, len(groups), path))
    if not fails or fails == len(rows):
        print("Both kinds are needed: add pictures of fine prints (--klippeye, --folders .../ok) or of failed ones.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
