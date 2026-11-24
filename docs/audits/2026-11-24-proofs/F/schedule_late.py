"""Proof: a scheduled print whose time passed while the service (or the Pi) was off starts as soon as it is back,
however late. print_schedule.py's docstring says a print that could not start at its time is not started later."""
import os, sys, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../backend"))
import print_schedule

def write_json(path, data, private=False):
    with open(path, "w") as f:
        json.dump(data, f)

clock = {"t": 1_000_000.0}
store = print_schedule.PrintSchedule(tempfile.mkdtemp(), write_json, clock=lambda: clock["t"])
store.add("benchy.gcode", clock["t"] + 3600)            # 03:00, set one hour ahead
clock["t"] += 3600 + 6 * 3600                           # power cut at 02:59, the Pi is back 6 hours later
started = []
print(store.tick(lambda: {"klippy": "ready", "print": "standby"}, started.append))
print("print started:", started, "- hours late:", 6)
