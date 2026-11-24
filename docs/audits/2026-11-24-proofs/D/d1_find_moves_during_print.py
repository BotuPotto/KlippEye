"""Proof D1: POST /api/camera/calibration/find (CameraCalibration.find_tip) moves the printer while a print runs:
_walk() sends G0 moves before goto() checks the print state."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import *  # noqa  (the fake printer and camera of tests/backend/test_calibration_auto.py)

cal.goto(targets[0]["id"])
u, v = truth(*STATE["position"][:2])
cal.add_point(targets[0]["id"], u, v)          # one tap by hand: template kept, draft has a point
STATE["print"] = "printing"                     # a print starts (the draft stays)
before = len(SCRIPTS)
try:
    cal.find_tip(targets[1]["id"])
    print("find_tip returned without error")
except Exception as error:
    print("find_tip raised:", type(error).__name__, error)
moves = [s for s in SCRIPTS[before:] if "G0" in s]
print("G-code sent while print_stats.state == printing:", len(moves))
for s in moves[:4]:
    print("   ", s.replace("\n", " | "))
print("PROVED" if moves else "not reproduced")
