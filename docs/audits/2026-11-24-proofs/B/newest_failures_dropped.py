import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof: with more than MAX_EXAMPLES//2 failed examples, train() keeps the OLDEST ones and never learns the newest
failed prints. Run: python3 -I newest_failures_dropped.py"""
import json, os, sys, tempfile
sys.path.insert(0, ROOT + "/backend")
import numpy as np, cv2, personal_layer

d = tempfile.mkdtemp()
img = np.zeros((20, 20, 3), np.uint8)
def make(sid, frames, outcome, failed_at):
    rec = os.path.join(d, "recordings", sid); os.makedirs(rec)
    for n in range(1, frames + 1): cv2.imwrite(os.path.join(rec, "%06d.jpg" % n), img)
    with open(os.path.join(rec, "frames.jsonl"), "w") as f:
        for n in range(1, frames + 1): f.write(json.dumps({"n": n, "t": 3 * n}) + "\n")
    json.dump({"id": sid, "started": 0, "ended": 3 * frames, "label": {"outcome": outcome, "failed_at": failed_at}}, open(os.path.join(rec, "session.json"), "w"))
make("20261101-100000-fine", 400, "ok", None)
for k in range(6):   # six failed prints, 1400 pictures after the moment each: ~700 failed examples (one in two) each
    make("2026110%d-120000-fail%d" % (k + 2, k), 1500, "failed", 3 * 50)
class Model:
    version = "v1"
    def predict(self, im): return 0.5, np.random.rand(16).astype(np.float32)
pl = personal_layer.PersonalLayer(d, np, cv2)
info = pl.train(Model())
cache = np.load(os.path.join(pl.folder, "cache.npz"))
used = set(cache.files)
failed_prints = sorted({k.split("/")[1] for k, _, label in personal_layer.examples_of(d) if label == 1 and k.replace("/", "|") in used})
print("failed examples available:", sum(1 for e in personal_layer.examples_of(d) if e[2] == 1), "- trained on:", info.get("failed"))
print("prints whose FAILED pictures reached the layer:", failed_prints)
