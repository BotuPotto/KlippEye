import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof: when fine examples outnumber KEPT_MAX, every keep_examples() call re-copies and re-evicts them.
Run: python3 -I keep_churn.py"""
import json, os, sys, tempfile, time
sys.path.insert(0, ROOT + "/backend")
import numpy as np, cv2
import personal_layer

d = tempfile.mkdtemp()
rec = os.path.join(d, "recordings", "20261101-100000-big")
os.makedirs(rec)
img = np.zeros((36, 54, 3), np.uint8)
N = 4 * 4600          # a 15 h fine print at one check per 3 s is 18000 pictures; 4600 fine examples
for n in range(1, N + 1):
    cv2.imwrite(os.path.join(rec, "%06d.jpg" % n), img)
with open(os.path.join(rec, "frames.jsonl"), "w") as f:
    for n in range(1, N + 1):
        f.write(json.dumps({"n": n, "t": 1000 + 3 * n}) + "\n")
json.dump({"id": "20261101-100000-big", "started": 1000, "ended": 1000 + 3 * N, "label": {"outcome": "ok", "failed_at": None}},
          open(os.path.join(rec, "session.json"), "w"))

writes = [0]
real = cv2.imwrite
def counting(*a, **k):
    writes[0] += 1
    return real(*a, **k)
cv2.imwrite = counting
for run in (1, 2, 3):
    writes[0] = 0
    t = time.time()
    kept = personal_layer.keep_examples(d, cv2, now=2000 + run)
    print("run %d: kept %d (limit %d), pictures decoded+re-encoded this run: %d, %.1f s" % (run, kept, personal_layer.KEPT_MAX, writes[0], time.time() - t))
