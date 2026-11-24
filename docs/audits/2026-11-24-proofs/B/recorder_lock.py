import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof: Recorder.add_frame() (called by the monitor's loop) runs _enforce_limit() every 20 pictures while holding the
recorder's lock; that walks every folder the first time (sizes) and deletes whole recordings (rmtree), so the loop
waits for it. Run: python3 -I recorder_lock.py"""
import os, sys, tempfile, time, json
sys.path.insert(0, ROOT + "/backend")
import numpy as np, cv2, recorder

root = tempfile.mkdtemp()
big = os.path.join(root, "20261101-100000-old"); os.makedirs(big)
json.dump({"id": "20261101-100000-old", "started": 1, "ended": 2}, open(os.path.join(big, "session.json"), "w"))
for n in range(1, 28801):     # one day at one picture per 3 s
    with open(os.path.join(big, "%06d.jpg" % n), "wb") as f: f.write(b"\xff\xd8" + b"0" * 4000)
r = recorder.Recorder(root, cv2)
r.configure(True, 200)
r.max_bytes = 1000                       # the old recording is over the limit and must go
r.observe("printing", "p.gcode", 5000.0)
frame = np.zeros((360, 540, 3), np.uint8)
for i in range(19):
    r.add_frame(frame, 5000.0 + i, {})
t = time.time(); r.add_frame(frame, 5100.0, {})   # the 20th: sizes() walks 28800 files, then rmtree
print("the 20th add_frame took %.2f s here (tmpfs-like disk); the monitor's loop is the caller" % (time.time() - t))
print("old recording still there:", os.path.isdir(big))
