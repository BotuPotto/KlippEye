"""The local model's tools without PyTorch (runs everywhere: tests/run_all.sh): the YOLO class names, the pictures each
source gives with their labels, the split by group, the alarms counted by ml/evaluate.py, backend/local_model.py with a
missing or broken model."""
import csv
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import datasets  # noqa: E402
import evaluate  # noqa: E402
import local_model  # noqa: E402
import synthetic  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   -> " + str(extra)[:400]) if not cond and extra != "" else ""))


root = tempfile.mkdtemp(prefix="ke-ml-")
paths = synthetic.make(root)

check("data.yaml names: a list on one line", datasets._yaml_names("names: ['spaghetti', \"print\"]\n") == ["spaghetti", "print"])
check("... a list on lines, a mapping", datasets._yaml_names("names:\n  - a\n  - b\nnc: 2\n") == ["a", "b"] and datasets._yaml_names("names:\n  0: x\n  1: y\n") == ["x", "y"])
check("... a list on lines not indented, as Roboflow writes it (the next key ends it)",
      datasets._yaml_names("names:\n- spaghetti\n- stringing\n- zits\nnc: 3\nroboflow:\n  workspace: x\n") == ["spaghetti", "stringing", "zits"])

rows = datasets.from_yolo(paths["yolo"], os.path.join(root, "work"), set(), False, cv2)
fails = [r for r in rows if r[1] == 1 and r[3] == "yolo"]
crops = [r for r in rows if r[3] == "yolo-crop"]
background = [r for r in rows if r[3] == "yolo-bg"]
check("YOLO: a photo with a small spaghetti box: its box cut out (not kept whole); one with only a «print» box is a fine print",
      len(fails) == 0 and len(crops) == 30 and all(os.path.isfile(r[0]) for r in crops) and len([r for r in rows if r[1] == 0 and r[3] == "yolo"]) == 30, (len(fails), len(crops), len(rows)))
check("... pieces of the failed photos away from every box: fine examples at the same scale",
      0 < len(background) <= 30 * datasets.BACKGROUND_CROPS and all(r[1] == 0 and os.path.isfile(r[0]) for r in background), len(background))
check("... Roboflow's copies of one photo share a group", all(r[2].startswith("yolo:photo") and ".rf." not in r[2] for r in rows))
every = datasets.from_yolo(paths["yolo"], os.path.join(root, "w2"), {"print"}, False, cv2)
check("... --fail-classes print: every photo has a failure cut out, none is a whole fine print",
      len({r[2] for r in every if r[3] == "yolo-crop"}) == len({r[2] for r in every}) and not [r for r in every if r[3] == "yolo" and r[1] == 0])
big = os.path.join(root, "big")
os.makedirs(os.path.join(big, "train", "images")); os.makedirs(os.path.join(big, "train", "labels"))
open(os.path.join(big, "data.yaml"), "w").write("names:\n- spaghetti\nnc: 1\n")
cv2.imwrite(os.path.join(big, "train", "images", "b.jpg"), synthetic.picture(True, __import__("random").Random(1))[0])
open(os.path.join(big, "train", "labels", "b.txt"), "w").write("0 0.5 0.5 0.6 0.6\n")
check("... a failure covering much of the photo: the photo is kept whole too",
      [r[3] for r in datasets.from_yolo(big, os.path.join(root, "w4"), set(), False, cv2) if r[1] == 1].count("yolo") == 1)
many = [("p%d" % i, i % 2, "g%d" % (i // 3), "x") for i in range(30)]
kept = datasets.cap_groups(many, 10, 7)
check("a cap per collection: whole groups, about the cap", 10 <= len(kept) < 13 and all(len([r for r in kept if r[2] == g]) == 3 for g in {r[2] for r in kept}), len(kept))
kinds = {n: datasets.kind_of(n) for n in ("spaghetti", "Spagetti", "failure", "detached", "layer_shift", "Warping", "blob", "defect", "error", "stringing",
                                         "zits", "under_extrusion", "nozzle", "Print", "part", "good", "normal", "extruder", "weird")}
check("class names: failures, defects of quality (left out), a normal print / the printer's parts",
      [n for n, k in kinds.items() if k == 1] == ["spaghetti", "Spagetti", "failure", "detached", "layer_shift", "Warping", "blob", "defect", "error", "weird"]
      and [n for n, k in kinds.items() if k is None] == ["stringing", "zits", "under_extrusion"], kinds)
cls_root = os.path.join(root, "cls")
for split, cls, n in (("train", "good", 4), ("train", "spaghetti", 3), ("valid", "stringing", 2), ("valid", "Normal", 1)):
    os.makedirs(os.path.join(cls_root, split, cls), exist_ok=True)
    for i in range(n):
        cv2.imwrite(os.path.join(cls_root, split, cls, "%s%d_jpg.rf.%d.jpg" % (cls, i, i)), synthetic.picture(False, __import__("random").Random(i))[0])
rows = datasets.from_classes(cls_root)
check("class folders: good / Normal fine, spaghetti failed, stringing left out", sorted((r[1]) for r in rows) == [0] * 5 + [1] * 3, [(r[0][-20:], r[1]) for r in rows])
auto_root = os.path.join(root, "auto")
os.makedirs(auto_root)
os.symlink(paths["yolo"], os.path.join(auto_root, "a__yolo"))
os.symlink(cls_root, os.path.join(auto_root, "b__cls"))
rows = datasets.from_auto(auto_root, os.path.join(root, "w3"), set(), False, cv2)
check("--auto: each downloaded dataset read as what it is (YOLO, class folders)", {r[3] for r in rows} == {"yolo", "yolo-crop", "yolo-bg", "classes"}, {r[3] for r in rows})

rows = datasets.from_folders(paths["sorted"])
check("folders: ok/ fine, fail/ failed", len([r for r in rows if r[1] == 0]) == 20 and len([r for r in rows if r[1] == 1]) == 20)

rows = datasets.from_klippeye(paths["klippeye"])
good = [r for r in rows if r[2] == "rec:20261101-100000-good"]
bad = [r for r in rows if r[2] == "rec:20261101-120000-bad"]
rev = [r for r in rows if r[2].startswith("rev:")]
check("KlippEye: a fine recording gives fine pictures (one in %d)" % datasets.OK_EVERY, len(good) == 15 and all(r[1] == 0 for r in good), len(good))
check("... a failed one: fine before its moment, failed from a minute after it, nothing in between",
      [r[1] for r in bad].count(0) == 8 and [r[1] for r in bad].count(1) == 25, ([r[1] for r in bad].count(0), [r[1] for r in bad].count(1)))
check("... a reviewed print: its pictures before the moment fine, from a minute after failed", [r[1] for r in rev] == [0] * 6 + [1] * 5, [r[1] for r in rev])

out = os.path.join(root, "work")
code = datasets.main(["--yolo", paths["yolo"], "--folders", paths["sorted"], "--klippeye", paths["klippeye"], "--out", out])
manifest = list(csv.DictReader(open(os.path.join(out, "manifest.csv"))))
groups = {}
for row in manifest:
    groups.setdefault(row["group"], set()).add(row["split"])
check("the manifest: every source, both kinds, a group never split between training and measuring",
      code == 0 and {r["source"] for r in manifest} == {"yolo", "yolo-crop", "yolo-bg", "folders", "klippeye"} and all(len(s) == 1 for s in groups.values())
      and {r["split"] for r in manifest} == {"train", "val"}, (code, len(manifest)))

check("alarms: over the threshold for N pictures in a row, then quiet for the cooldown",
      evaluate.alarms([(0, .9), (10, .9), (20, .2), (30, .95), (40, .95), (200, .99), (210, .99)], 0.8, 2, 120) == [10, 200]
      and evaluate.alarms([(0, .9), (10, .9)], 0.8, 1, 120) == [0])
prints = evaluate.prints_of(paths["klippeye"])
check("evaluate: the labelled prints of a data folder (two recordings, one review)", sorted(p["kind"] for p in prints) == ["recording", "recording", "review"])

check("local_model: no folder or no model.onnx: None (the monitor works without)", local_model.load("", cv2, np) is None and local_model.load(root, cv2, np) is None)
broken = os.path.join(root, "broken")
os.makedirs(broken)
open(os.path.join(broken, "model.onnx"), "wb").write(b"not a model")
open(os.path.join(broken, "model.json"), "w").write('{"format": 1, "size": 96}')
try:
    local_model.load(broken, cv2, np)
    raised = False
except local_model.ModelError:
    raised = True
check("... a broken model: ModelError (said, not a crash)", raised)
open(os.path.join(broken, "model.json"), "w").write('{"format": 9}')
try:
    local_model.load(broken, cv2, np)
    raised = False
except local_model.ModelError as error:
    raised = "format" in str(error)
check("... a model.json of another format: refused", raised)

print("%d FAIL" % len(FAILS))
sys.exit(1 if FAILS else 0)
