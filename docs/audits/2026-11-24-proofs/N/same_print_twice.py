import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""One print that was recorded AND answered in "How did the print go?": evaluate.py counts it once (same_print_once),
ml/datasets.py --klippeye puts both in the manifest under two groups, so the group split can put one copy in training
and the other in the measuring set."""
import json, os, sys, tempfile
sys.path.insert(0, ROOT + "/ml")
import datasets, evaluate, labelled_prints
d = tempfile.mkdtemp(prefix="n-proof-")
rec = os.path.join(d, "recordings", "20261113-164121-benchy"); os.makedirs(rec)
rev = os.path.join(d, "reviews", "20261113-164124-benchy"); os.makedirs(rev)
frames = [{"n": i, "t": 1000 + i * 60} for i in range(8)]
for f in frames:
    open(os.path.join(rec, "%06d.jpg" % f["n"]), "wb").write(b"x")
    open(os.path.join(rev, "%04d.jpg" % f["n"]), "wb").write(b"x")
open(os.path.join(rec, "frames.jsonl"), "w").write("\n".join(json.dumps(f) for f in frames))
json.dump({"id": "20261113-164121-benchy", "started": 1000, "label": {"outcome": "ok"}}, open(os.path.join(rec, "session.json"), "w"))
json.dump({"id": "20261113-164124-benchy", "started": 1003, "thumbs": frames, "answer": {"outcome": "ok"}}, open(os.path.join(rev, "review.json"), "w"))
rows = datasets.from_klippeye(d)
print("groups in the training list:", sorted({r[2] for r in rows}))
print("evaluate.py counts the print:", len(evaluate.same_print_once(labelled_prints.prints_of(d))), "time(s)")
