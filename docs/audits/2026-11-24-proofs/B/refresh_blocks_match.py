import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof: FalseAlarms.refresh() holds the memory's lock while it runs the model on every stale picture, and match()
(called by the monitor's loop at every local look) needs that lock.
Run: python3 -I refresh_blocks_match.py"""
import os, sys, tempfile, threading, time
sys.path.insert(0, ROOT + "/backend")
import numpy as np, cv2
import false_alarms

d = tempfile.mkdtemp()
fa = false_alarms.FalseAlarms(d, np, cv2)
os.makedirs(os.path.join(d, "personal", "false_alarms"), exist_ok=True)
for i in range(20):
    fa.add(np.ones(4) + i, 50, "person", "a%d" % i, "old", picture=np.zeros((36, 54, 3), np.uint8))
def describe(picture):          # a model forward on a Raspberry: 0.2 s each (300 kept alarms = 60 s)
    time.sleep(0.2)
    return np.ones(4, dtype=np.float32)
t = threading.Thread(target=fa.refresh, args=("new", describe)); t.start()
time.sleep(0.3)
start = time.time()
fa.match(np.ones(4), 50, "new")   # what _local_look does at every look
print("match() waited %.1f s for refresh (20 alarms x 0.2 s); 300 alarms would be ~60 s of no local looks" % (time.time() - start))
t.join()
