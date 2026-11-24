import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof: a damaged npz (power cut: file replaced but data never reached the disk) is not handled.
Run: python3 -I corrupt_npz.py"""
import os, sys, tempfile, json
sys.path.insert(0, ROOT + "/backend")
import numpy as np
import false_alarms, personal_layer

# 1. false_alarms.npz zero-length / half written
d = tempfile.mkdtemp()
fa = false_alarms.FalseAlarms(d, np)
fa.add(np.ones(8), 50, "person", "a1", "m1")
fa.add(np.arange(8) + 1.0, 60, "person", "a2", "m1")
npz = os.path.join(d, "personal", "false_alarms.npz")
for label, content in (("zero-length", b""), ("half a zip", open(npz, "rb").read()[:40])):
    open(npz, "wb").write(content)
    try:
        false_alarms.FalseAlarms(d, np)
        print("false_alarms", label, ": loaded (empty)")
    except Exception as e:
        print("false_alarms", label, ": FalseAlarms() RAISES", type(e).__name__, e, "-> backend import fails at line 3174")

# 2. items and vectors out of step (a cut between the two writes)
d = tempfile.mkdtemp()
fa = false_alarms.FalseAlarms(d, np)
fa.add(np.ones(8), 50, "person", "a1", "m1")
old = open(os.path.join(d, "personal", "false_alarms.npz"), "rb").read()
fa.add(np.arange(8) + 1.0, 60, "person", "a2", "m1")
open(os.path.join(d, "personal", "false_alarms.npz"), "wb").write(old)   # npz of 1 row, json of 2 items
fb = false_alarms.FalseAlarms(d, np)
print("items on disk 2, vectors 1 -> loaded items:", len(fb.items), "(both lost; next add overwrites the files)")

# 3. cache.npz damaged: training fails for ever
d = tempfile.mkdtemp()
class M:  # a model that needs no OpenCV
    version = "v1"
    def predict(self, im): return 0.5, np.ones(4, dtype=np.float32)
pl = personal_layer.PersonalLayer(d, np)
os.makedirs(pl.folder, exist_ok=True)
open(os.path.join(pl.folder, "cache.npz"), "wb").write(b"")
try:
    pl._embeddings(M(), [("rec/x/1", "/nonexistent.jpg", 0)])
except Exception as e:
    print("personal cache.npz zero-length: _embeddings RAISES", type(e).__name__, e, "(train() catches it into last_error, every time; the file is never rewritten)")
