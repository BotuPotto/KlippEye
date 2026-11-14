"""Release 1.107: backend/personal_layer.py (the local model's layer of each printer): which pictures become examples
(answered prints, labelled recordings, imported ones), training on their embeddings, the blend with the base model's
score, the cache per base model version, export and import. No network, no Flask: a fake model whose embedding says
how red a picture is."""
import io
import json
import os
import sys
import tempfile
import zipfile

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "backend"))
import personal_layer as pl  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   -> " + str(extra)[:300]) if (extra != "" and not cond) else ""), flush=True)


class FakeModel:
    """The base model: always «fine» (0.1); the embedding has the picture's red in its first numbers."""

    def __init__(self, version="v1"):
        self.version, self.calls = version, 0

    def predict(self, frame):
        self.calls += 1
        red = float(frame[:, :, 2].mean()) / 255.0
        vector = np.full(64, 0.05, dtype=np.float32)
        vector[:8] = red
        vector[8:16] = 1 - red
        return 0.1, vector


def picture(path, red, width=320, height=214):
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :, 2] = int(red * 255)
    image[:, :, 1] = int((1 - red) * 255)
    image = np.clip(image.astype(int) + np.random.randint(-10, 10, image.shape), 0, 255).astype(np.uint8)
    cv2.imwrite(path, image)


def review(data, rid, outcome, failed_at, count=24):
    folder = os.path.join(data, "reviews", rid)
    os.makedirs(folder)
    thumbs = []
    for n in range(1, count + 1):
        t = 1000 + n * 60
        bad = outcome == "failed" and failed_at is not None and t >= failed_at + pl.FAILED_AFTER
        picture(os.path.join(folder, "%04d.jpg" % n), 0.9 if bad else 0.1)
        thumbs.append({"n": n, "t": t})
    json.dump({"id": rid, "thumbs": thumbs, "answer": {"outcome": outcome, "failed_at": failed_at}}, open(os.path.join(folder, "review.json"), "w"))


np.random.seed(3)
data = tempfile.mkdtemp()

# ---- the examples
review(data, "r1", "ok", None)
review(data, "r2", "failed", 1000 + 12 * 60)        # fine up to picture 11, the failure from picture 13 on (12 is too close)
review(data, "r3", "failed", None)                   # failed, from when not known: no example
review(data, "r4", "skipped", None)
examples = pl.examples_of(data)
keys = {k: label for k, _, label in examples}
check("a print that went fine: every picture is fine", all(keys.get("rev/r1/%d" % n) == 0 for n in range(1, 25)))
check("a failed print: fine before the moment", all(keys.get("rev/r2/%d" % n) == 0 for n in range(1, 12)), keys)
check("... the minute after it is left out", "rev/r2/12" not in keys)
check("... failed from a minute after", all(keys.get("rev/r2/%d" % n) == 1 for n in range(13, 25)))
check("failed without a moment, or skipped: no example", not any(k.startswith(("rev/r3/", "rev/r4/")) for k in keys))

# a labelled recording: one fine picture in OK_EVERY, one failed in two
folder = os.path.join(data, "recordings", "s1")
os.makedirs(folder)
with open(os.path.join(folder, "frames.jsonl"), "w") as handle:
    for n in range(1, 41):
        picture(os.path.join(folder, "%06d.jpg" % n), 0.9 if n > 30 else 0.1, 640, 480)
        handle.write(json.dumps({"n": n, "t": 5000 + n * 10}) + "\n")
json.dump({"id": "s1", "label": {"outcome": "failed", "failed_at": 5000 + 24 * 10}}, open(os.path.join(folder, "session.json"), "w"))
rec = [(k, label) for k, _, label in pl.examples_of(data) if k.startswith("rec/")]
check("a labelled recording gives examples of both kinds", {0, 1} <= {label for _, label in rec}, rec)
check("... fewer than its pictures (one in a few)", 0 < len(rec) < 40, len(rec))

# ---- training
layer = pl.PersonalLayer(data, np, cv2)
check("a new layer: not trained, off", layer.info()["trained"] is False and layer.info()["enabled"] is False)
check("... it counts the examples there are", layer.info()["have"]["failed"] >= 12, layer.info())
model = FakeModel()
check("off: the base model's score is kept", layer.blend(0.1, np.ones(64), "v1") == 0.1)
info = layer.train(model)
check("trained on the examples", info.get("trained") and info["examples"] == len(pl.examples_of(data)), info)
check("... measured on the examples kept aside", (info.get("measured") or {}).get("right", 0) >= 0.9, info.get("measured"))
check("... its weight grows with the failed examples, at most BLEND_MAX", pl.BLEND_MIN <= info["weight"] <= pl.BLEND_MAX, info)
check("the weight: none below the minimum, then growing, then the most", pl.weight_for(pl.MIN_FAILED - 1) == 0 and pl.weight_for(pl.MIN_FAILED) == pl.BLEND_MIN
      and pl.weight_for(30) < pl.weight_for(50) and pl.weight_for(500) == pl.BLEND_MAX)
check("layer.json and the cache are written", os.path.isfile(os.path.join(data, "personal", "layer.json")) and os.path.isfile(os.path.join(data, "personal", "cache.npz")))
calls = model.calls
layer.train(model)
check("trained again with the same base model: the cache is used", model.calls == calls, model.calls - calls)

layer.configure(True)
red = model.predict(np.dstack([np.zeros((10, 10)), np.zeros((10, 10)), np.full((10, 10), 230)]).astype(np.uint8))[1]
green = model.predict(np.dstack([np.zeros((10, 10)), np.full((10, 10), 230), np.full((10, 10), 25)]).astype(np.uint8))[1]
check("on: a picture like the failed ones scores higher than the base model", layer.blend(0.1, red, "v1") > 0.3, layer.blend(0.1, red, "v1"))
check("... one like the fine ones stays low", layer.blend(0.1, green, "v1") < 0.15, layer.blend(0.1, green, "v1"))
check("another base model version: the base model's score alone", layer.blend(0.1, red, "v2") == 0.1)
check("no embedding: the base model's score alone", layer.blend(0.42, None, "v1") == 0.42)
check("an embedding of another size: the base model's score alone", layer.blend(0.42, np.ones(10), "v1") == 0.42)

again = pl.PersonalLayer(data, np, cv2)
again.configure(True)
check("read again from the disk: the same score", abs(again.blend(0.1, red, "v1") - layer.blend(0.1, red, "v1")) < 1e-9)

new_model = FakeModel("v2")
info = layer.train(new_model)
check("a new base model: the embeddings are computed again", new_model.calls == len(pl.examples_of(data)) and info["version"] == "v2", (new_model.calls, info))

# too few examples
small = tempfile.mkdtemp()
review(small, "only", "ok", None, 8)
few = pl.PersonalLayer(small, np, cv2)
info = few.train(FakeModel())
check("too few examples: no layer, the reason said", info["trained"] is False and "too few" in info["error"], info)
check("no model: said", "no local model" in few.train(None)["error"])

# ---- export / import
blob = layer.export("printer-a")
archive = zipfile.ZipFile(io.BytesIO(blob))
labels = json.loads(archive.read("labels.json"))
check("the export has the pictures and their labels", labels["format"] == 1 and len(labels["pictures"]) == len(pl.examples_of(data)) and set(labels["pictures"].values()) == {0, 1}, labels)
sizes = [cv2.imdecode(np.frombuffer(archive.read(n), np.uint8), cv2.IMREAD_COLOR).shape[1] for n in labels["pictures"]]
check("... small pictures (the recordings' ones made smaller)", max(sizes) <= pl.EXPORT_WIDTH, max(sizes))

other = tempfile.mkdtemp()
target = pl.PersonalLayer(other, np, cv2)
count = target.import_zip(blob, "file.zip")
check("imported on another printer", count == len(labels["pictures"]), count)
check("... listed with the printer it came from", target.imported() and target.imported()[0]["printer"] == "printer-a", target.imported())
info = target.train(FakeModel())
check("... and it trains on them", info["trained"] and info["examples"] == count, info)
check("an export does not carry what was imported", "pictures" in json.loads(zipfile.ZipFile(io.BytesIO(target.export("b"))).read("labels.json")) and
      not json.loads(zipfile.ZipFile(io.BytesIO(target.export("b"))).read("labels.json"))["pictures"])

for name, bad in (("not a zip", b"hello"), ("a zip without labels", None), ("labels of another format", "format")):
    if bad is None or bad == "format":
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("00000.jpg", b"\xff\xd8xx")
            if bad == "format":
                z.writestr("labels.json", json.dumps({"format": 9, "pictures": {"00000.jpg": 1}}))
        bad = buffer.getvalue()
    try:
        target.import_zip(bad, "x")
        check("refused: " + name, False)
    except ValueError:
        check("refused: " + name, True)

buffer = io.BytesIO()
with zipfile.ZipFile(buffer, "w") as z:
    z.writestr("../../evil.jpg", b"\xff\xd8evil")
    z.writestr("00001.jpg", b"not a jpeg")
    z.writestr("labels.json", json.dumps({"format": 1, "printer": "../x", "pictures": {"../../evil.jpg": 1, "00001.jpg": 1}}))
try:
    target.import_zip(buffer.getvalue(), "x")
    check("a zip with odd names and no real picture: refused", False)
except ValueError:
    check("a zip with odd names and no real picture: refused", True)
check("... nothing written outside its folder", not os.path.exists(os.path.join(other, "evil.jpg")) and not os.path.exists(os.path.join(other, "personal", "evil.jpg")))

target.forget_imported()
check("forgetting what was imported", target.imported() == [] and not [e for e in pl.examples_of(other)])

# ---- 1.125: the examples kept apart
import shutil  # noqa: E402

kept_data = tempfile.mkdtemp()
review(kept_data, "k1", "failed", 1000 + 12 * 60)
folder = os.path.join(kept_data, "recordings", "s9")
os.makedirs(folder)
with open(os.path.join(folder, "frames.jsonl"), "w") as handle:
    for n in range(1, 21):
        picture(os.path.join(folder, "%06d.jpg" % n), 0.9 if n > 14 else 0.1, 640, 480)
        handle.write(json.dumps({"n": n, "t": 5000 + n * 10}) + "\n")
json.dump({"id": "s9", "label": {"outcome": "failed", "failed_at": 5000 + 10 * 10}}, open(os.path.join(folder, "session.json"), "w"))
before = sorted((k, label) for k, _, label in pl.examples_of(kept_data))
kept = pl.keep_examples(kept_data, cv2)
check("1.125: every example gets a small copy apart", kept == len(before) and all(
    cv2.imread(p_).shape[1] <= pl.KEPT_WIDTH for p_ in [os.path.join(kept_data, "personal", "kept", n) for n in os.listdir(os.path.join(kept_data, "personal", "kept")) if n.endswith(".jpg")]), (kept, len(before)))
shutil.rmtree(folder)
shutil.rmtree(os.path.join(kept_data, "reviews", "k1"))
after = sorted((k, label) for k, _, label in pl.examples_of(kept_data))
check("... the recording and the answer deleted: the same examples, same keys and labels (from the copies)", after == before, (len(after), len(before)))
check("... and the copies are what is read now", all("/kept/" in p_ for _, p_, _ in pl.examples_of(kept_data)))
check("... keeping again changes nothing", pl.keep_examples(kept_data, cv2) == kept)
gone = pl.forget_kept(kept_data, "rec/s9/")
check("... a label taken away forgets that print's copies", gone > 0 and not any(k.startswith("rec/s9/") for k, _, _ in pl.examples_of(kept_data)), gone)
old_max = pl.KEPT_MAX
pl.KEPT_MAX = 15
pl.keep_examples(kept_data, cv2)
left = pl.examples_of(kept_data)
check("... over the limit: the oldest fine ones go, every failed one stays", len(left) == 15 and sum(1 for e in left if e[2] == 1) == sum(1 for k, label in before if label == 1 and k.startswith("rev/")), (len(left), sum(1 for e in left if e[2] == 1)))
pl.KEPT_MAX = old_max

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
