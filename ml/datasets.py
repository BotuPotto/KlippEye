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
import os
import random
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
import labelled_prints  # noqa: E402  (the prints judged in the dashboard: one reader for KlippEye and these tools)

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
FAILED_AFTER = labelled_prints.FAILED_AFTER   # a failure is clear this many seconds after the moment the person chose
OK_EVERY = 4               # of a fine recording, one picture in OK_EVERY (they are much alike)
CROP_MARGIN = 0.6          # a box is cut out with this much of its size around it
FAIL_CROPS = 2             # failure boxes cut out of one picture, at most
BACKGROUND_CROPS = 2       # pieces of the same picture away from every box, as fine examples (the public collections have
                           # almost only failed pictures: these teach what is not a failure, at the same scale as the boxes)
WHOLE_IF_COVERS = 0.2      # a failed picture is also kept whole when its biggest failure covers this much of it: a smaller
                           # one, seen whole, would teach «a whole picture of a printer is a failure»
MAX_PER_DATASET = 3000     # pictures from one collection, at most (whole groups, picked at random): no collection drowns the others


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
    names = []
    if yaml:
        with open(yaml, encoding="utf-8") as handle:
            names = _yaml_names(handle.read())
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
            with open(label_file, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
            for line in lines:
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
            if max(bw * bh for _, _, bw, bh in fails) >= WHOLE_IF_COVERS:
                rows.append((path, 1, group, "yolo"))
            image = cv2.imread(path) if cv2 is not None else None
            if image is not None:
                h, w = image.shape[:2]
                stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", os.path.basename(path))[:80]
                sides = []
                for k, (cx, cy, bw, bh) in enumerate(fails[:FAIL_CROPS]):
                    side = max(bw * w, bh * h) * (1 + 2 * CROP_MARGIN)
                    side = min(max(side, min(w, h) * 0.25), min(w, h))
                    x0, y0 = int(max(0, cx * w - side / 2)), int(max(0, cy * h - side / 2))
                    x1, y1 = int(min(w, cx * w + side / 2)), int(min(h, cy * h + side / 2))
                    if x1 - x0 > 16 and y1 - y0 > 16:
                        out = os.path.join(crops, "%s_%d.jpg" % (stem, k))
                        cv2.imwrite(out, image[y0:y1, x0:x1])
                        rows.append((out, 1, group, "yolo-crop"))
                        sides.append(side)
                rows += _background_crops(image, boxes, sides, crops, stem, group, cv2)
        elif boxes and not [c for c, _ in boxes if c in quality]:
            rows.append((path, 0, group, "yolo"))   # only a normal print and the printer's parts
        elif not boxes and empty_is_ok:
            rows.append((path, 0, group, "yolo"))
    return rows


def _background_crops(image, boxes, sides, crops, stem, group, cv2):
    """Up to BACKGROUND_CROPS square pieces of the picture, as big as its failure crops, that touch no box (any class,
    each grown by CROP_MARGIN): «fine» examples at the scale the model sees the failures at."""
    h, w = image.shape[:2]
    grown = []
    for _, (cx, cy, bw, bh) in boxes:
        mw, mh = bw * w * (1 + CROP_MARGIN), bh * h * (1 + CROP_MARGIN)
        grown.append((cx * w - mw / 2, cy * h - mh / 2, cx * w + mw / 2, cy * h + mh / 2))
    rng = random.Random(stem)
    out = []
    for k, wanted in enumerate(sides[:BACKGROUND_CROPS]):
        found = None
        for scale in (1.0, 0.75, 0.5):   # as big as the failure's crop, or smaller when the boxes leave no such room
            side = int(min(wanted * scale, w, h))
            if side < max(32, min(w, h) * 0.2):
                break
            for _ in range(25):
                x0, y0 = rng.randint(0, w - side), rng.randint(0, h - side)
                if all(x0 + side <= a or x0 >= c or y0 + side <= b or y0 >= d for a, b, c, d in grown):
                    found = (x0, y0, side)
                    break
            if found:
                break
        if found:
            x0, y0, side = found
            path = os.path.join(crops, "%s_bg%d.jpg" % (stem, k))
            cv2.imwrite(path, image[y0:y0 + side, x0:x0 + side])
            out.append((path, 0, group, "yolo-bg"))
    return out


def cap_groups(rows, limit, seed):
    """At most `limit` pictures, whole groups picked at random (the copies of one photo stay together)."""
    if limit <= 0 or len(rows) <= limit:
        return rows
    by_group = {}
    for row in rows:
        by_group.setdefault(row[2], []).append(row)
    groups = sorted(by_group)
    random.Random(seed).shuffle(groups)
    kept = []
    for group in groups:
        if len(kept) >= limit:
            break
        kept += by_group[group]
    return kept


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


def from_auto(root, work, fail_classes, empty_is_ok, cv2, limit=MAX_PER_DATASET, seed=7):
    """Every dataset in `root` (one folder each, as ml/download.py writes them), each to at most `limit` pictures."""
    rows = []
    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        if not os.path.isdir(folder):
            continue
        if glob.glob(os.path.join(folder, "**", "data.yaml"), recursive=True):
            found = from_yolo(folder, work, fail_classes, empty_is_ok, cv2)
        else:
            found = from_classes(folder, fail_classes)
        kept = cap_groups(found, limit, seed)
        print("    %d pictures (%d failed, %d fine)%s" % (len(kept), sum(r[1] for r in kept), len(kept) - sum(r[1] for r in kept),
                                                        " of %d" % len(found) if len(kept) < len(found) else ""))
        rows += kept
    return rows


def from_klippeye(root):
    """The prints judged in the dashboard (labelled recordings, answers to «How did the print go?»): a fine picture in
    OK_EVERY of a recording, every failed one; a failed print without a moment gives nothing (which pictures show it
    is not known)."""
    rows = []
    for one in labelled_prints.prints_of(root):
        recording = one["kind"] == "recording"
        group = ("rec:" if recording else "rev:") + str(one["id"])
        for index, (_, t, path) in enumerate(one["pictures"]):
            label = labelled_prints.label_at(one, t)
            if label is None or (recording and label == 0 and index % OK_EVERY):
                continue
            rows.append((path, label, group, "klippeye"))
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
    parser.add_argument("--max-per-dataset", type=int, default=MAX_PER_DATASET, help="pictures from one --auto collection, at most (0: all)")
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
        rows += from_auto(folder, args.out, fail_classes, args.empty_is_ok, cv2, args.max_per_dataset, args.seed)
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
