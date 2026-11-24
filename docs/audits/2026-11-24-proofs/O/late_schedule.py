import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Zone O proof: tests/backend/test_print_schedule.py has no case where the first tick comes hours after the scheduled time
(the Pi was off). The code starts the print anyway, and nothing in the tests says that this is wanted or not.
Run: python3 -I late_schedule.py"""
import json, os, sys, tempfile
sys.path.insert(0, ROOT + "/backend")
import print_schedule as ps
w = lambda p, d: open(p, "w").write(json.dumps(d))
t = [1_800_000_000]
s = ps.PrintSchedule(tempfile.mkdtemp(), w, lambda: t[0])
s.add("benchy.gcode", t[0] + 3600)
t[0] += 3600 * 6          # the Pi was off for 6 hours: the first tick after the scheduled time
started = []
changed = s.tick(lambda: {"klippy": "ready", "print": "standby"}, started.append)
print("started 6 h late:", started, [c["status"] for c in changed])
