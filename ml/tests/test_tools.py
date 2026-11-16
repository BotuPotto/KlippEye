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
import hard_cases  # noqa: E402
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
pasted = hard_cases.paste(rows, os.path.join(root, "pasted"), 1.0, cv2, np)
_crop_groups = {r[2] for r in rows if r[3] in ("yolo-crop", "yolo-bg")}
check("1.134: paste: as many public failures (failed) as pieces of clean bed (fine), each with its piece's group, the picture changed",
      pasted and sum(r[1] for r in pasted) * 2 == len(pasted) and {r[2] for r in pasted} <= _crop_groups
      and all(cv2.imread(r[0]) is not None for r in pasted), [(r[1], r[3]) for r in pasted])

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
prints = evaluate.labelled_prints.prints_of(paths["klippeye"])
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

# ---------------------------------------------------------------- 1.130: a model for every printer
import download  # noqa: E402

check("1.130: «Successful Print», «Normal print», «No defect» are fine; «Print Failure» failed",
      [datasets.kind_of(n) for n in ("Successful Print", "Normal print", "good_print", "No Defect", "Print Failure")] == [0, 0, 0, 0, 1],
      [datasets.kind_of(n) for n in ("Successful Print", "Normal print", "good_print", "No Defect", "Print Failure")])
check("pictures nobody labelled («Unlabeled», «background») are left out, not counted as failures",
      [datasets.kind_of(n) for n in ("Unlabeled", "background", "None")] == [None] * 3)
check("licences: CC BY 4.0, MIT, public domain shareable; ShareAlike, NonCommercial, private not; not written: neither",
      [download.licence_is_open(t) for t in ("CC BY 4.0", "MIT", "Public Domain")] == [True] * 3
      and [download.licence_is_closed(t) for t in ("CC BY-SA 4.0", "CC BY-NC 4.0", "Private", "CC BY 4.0", "see the dataset's page")] == [True, True, True, False, False])

multi = os.path.join(root, "multi", "train")
os.makedirs(multi)
for i in range(5):
    cv2.imwrite(os.path.join(multi, "m%d_jpg.rf.%d.jpg" % (i, i)), np.full((40, 40, 3), 90, np.uint8))
with open(os.path.join(multi, "_classes.csv"), "w") as handle:
    handle.write("filename, Print Failure, Successful Print\n" + "".join("m%d_jpg.rf.%d.jpg,%d,%d\n" % (i, i, f, o) for i, (f, o) in enumerate([(1, 0), (0, 1), (0, 1), (0, 0), (1, 1)])))
rows = datasets.from_multiclass(os.path.join(root, "multi"))
check("multi-label (Roboflow «multiclass»): failure -> failed, only «Successful Print» -> fine, nothing -> left out, both -> failed",
      sorted(r[1] for r in rows) == [0, 0, 1, 1] and all(r[3] == "multiclass" for r in rows), [(os.path.basename(r[0]), r[1]) for r in rows])

# the Bambu timelapses: pictures taken from each video, a print whose end looks failed left out, failed.txt honoured
videos = []
for name, bad in (("printA", False), ("printB", False), ("printC", True)):
    path = os.path.join(root, "videos", "contributor", name + ".avi")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 10, (96, 64))
    for k in range(40):
        frame = np.full((64, 96, 3), 70 + k, np.uint8)
        if bad and k > 30:
            frame[:] = 255
        writer.write(frame)
    writer.release()
    videos.append(path)


class Judge:
    threshold = 0.5

    def predict(self, image):
        return (0.9 if image.mean() > 200 else 0.1), None


real_load = local_model.load
local_model.load = lambda folder, cv2_, np_: Judge()
data = os.path.join(root, "data")
line = download.bambu(data, root, 0.5, videos=videos)
local_model.load = real_load
frames = os.path.join(data, download.BAMBU_FOLDER, "frames")
kept = sorted(os.listdir(frames))
check("Bambu: %d pictures from each timelapse, the last one kept apart to look at, a print whose end looks failed left out" % download.BAMBU_FRAMES,
      len(kept) == 2 and all(len(os.listdir(os.path.join(frames, k))) == download.BAMBU_FRAMES for k in kept)
      and len(os.listdir(os.path.join(data, download.BAMBU_FOLDER, "last-pictures"))) == 3 and "printC" in open(os.path.join(data, download.BAMBU_FOLDER, "doubtful.txt")).read()
      and line and "CC BY 4.0" in line, (kept, line))
with open(os.path.join(data, download.BAMBU_FOLDER, "failed.txt"), "a") as handle:
    handle.write(kept[0] + "\n")
rows = datasets.from_auto(data, os.path.join(root, "work2"), set(), False, cv2)
check("... read by --auto as prints going well (fine), one group per print, the ones in failed.txt left out",
      rows and all(r[1] == 0 and r[3] == "frames" for r in rows) and {r[2] for r in rows} == {"frames:" + kept[1]}, {r[2] for r in rows})

# the look-alikes
fine_rows = [(p, 0, "g%d" % i, "folders") for i, p in enumerate(sorted(datasets.images_in(os.path.join(paths["sorted"], "mine", "ok"))))]
failed_rows = [(p, 1, "f%d" % i, "folders") for i, p in enumerate(sorted(datasets.images_in(os.path.join(paths["sorted"], "mine", "fail"))))]
drawn = hard_cases.make(fine_rows + failed_rows, os.path.join(root, "hard"), 0.5, cv2, np)
on_fine = [r for r in drawn if r[1] == 0]
on_failed = [r for r in drawn if r[1] == 1]
check("look-alikes: drawn on half the fine pictures (fine) and on a few failed ones (still failed), every kind, the group of their picture",
      len(on_fine) == len(fine_rows) // 2 and 0 < len(on_failed) <= len(on_fine) * 0.2 + 1 and {r[3] for r in drawn} == {"hard-" + k for k in hard_cases.KINDS}
      and {r[2] for r in on_fine} <= {r[2] for r in fine_rows}, (len(on_fine), len(on_failed), {r[3] for r in drawn}))
first = cv2.imread(fine_rows[0][0])
changed = [float(np.mean(cv2.absdiff(hard_cases.draw(first, k, "s", cv2, np), first))) for k in hard_cases.KINDS]
check("... each kind changes the picture, a little (a detail, not a new picture)", all(0.05 < c < 25 for c in changed), changed)
check("... the same seed draws the same", np.array_equal(hard_cases.draw(first, "strand", "s", cv2, np), hard_cases.draw(first, "strand", "s", cv2, np)))

out = os.path.join(root, "work3")
code = datasets.main(["--folders", paths["sorted"], "--hard-cases", "0.3", "--mine", os.path.join(HERE, "..", "..", "models", "base"), "--out", out])
manifest = list(csv.DictReader(open(os.path.join(out, "manifest.csv"))))
check("datasets.py --hard-cases --mine: look-alikes in the list, a weight per picture (fine pictures the model doubts weigh more)",
      code == 0 and any(r["source"].startswith("hard-") for r in manifest) and all(r["weight"] in ("1", "2", "3") for r in manifest), (code, manifest[:2]))

print("%d FAIL" % len(FAILS))
sys.exit(1 if FAILS else 0)
