import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
# Zone A check 7: a lamp switched on that lights half the scene, and stays on. Does the motion detection trigger?
import sys; sys.path.insert(0, ROOT + "/backend")
import numpy as np
from monitor_core import FrameJudge
for boost in (False, True):
    j = FrameJudge(); j.verbose = False; j.boost = boost
    base = np.full((720, 1080, 3), 90, np.uint8)
    lit = base.copy(); lit[:, :540] = 170            # the left half lit by the lamp
    t, out = 0.0, []
    for k in range(80):
        t += 3
        if t < j.cooldown_until: continue
        frame = base if k < 40 else lit
        s, trig = j.judge(frame, b"", t)
        if k >= 40: out.append((round(t - 123, 0), None if s is None else round(s, 1), trig))
    print("boost=%s:" % boost, [o for o in out if o[2]] or "no trigger", "| first checks after the lamp:", out[:14])
