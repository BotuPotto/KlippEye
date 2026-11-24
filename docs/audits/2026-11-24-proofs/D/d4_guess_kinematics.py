import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof D4: guess_z_moves on printers other than the owner's. Expected values from how each machine moves."""
import os, sys
sys.path.insert(0, os.path.join(os.environ.get("KE_ROOT", ROOT + ""), "backend"))
import camera_calibration as cc
cases = [
    ("CoreXZ (X and Z on the gantry, bed slings in Y)", {"printer": {"kinematics": "corexz"}}, "toolhead"),
    ("cartesian cube, bed moves in Z, one Z motor", {"printer": {"kinematics": "cartesian"}}, "bed"),
    ("CoreXY with one Z motor, bed moves in Z", {"printer": {"kinematics": "corexy"}}, "bed"),
    ("delta", {"printer": {"kinematics": "delta"}}, "toolhead"),
    ("CoreXY with quad gantry level", {"printer": {"kinematics": "corexy"}, "quad_gantry_level": {}}, "toolhead"),
]
for name, settings, want in cases:
    got = cc.guess_z_moves(settings)
    print("%-55s guess %-8s real %-8s %s" % (name, got, want, "" if got == want else "<- WRONG"))
