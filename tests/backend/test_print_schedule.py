"""Release 1.70: backend/print_schedule.py (scheduled prints): the list kept in the data folder, what is started at its
time and what is missed, and why. No network, no Flask: a fake clock, a fake printer."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "backend"))
import print_schedule as ps  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   -> " + str(extra)[:300]) if (extra != "" and not cond) else ""), flush=True)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class Printer:
    def __init__(self, klippy="ready", state="standby", refuse=None):
        self.klippy, self.state, self.refuse, self.started, self.reads = klippy, state, refuse, [], 0

    def read(self):
        self.reads += 1
        return {"klippy": self.klippy, "print": self.state}

    def start(self, name):
        if self.refuse:
            raise RuntimeError(self.refuse)
        self.started.append(name)
        self.state = "printing"


T0 = 1_800_000_000
folder = tempfile.mkdtemp()
clock = Clock(T0)
store = ps.PrintSchedule(folder, write_json, clock)

# names
check("a file's path is kept", ps.clean_filename("parts/benchy.gcode") == "parts/benchy.gcode")
check("the gcodes/ root and a leading slash are dropped", ps.clean_filename("/gcodes/benchy.gcode") == "benchy.gcode")
check("no way out of the folder, no empty names", all(ps.clean_filename(n) is None for n in ("../x.gcode", "a/../../b", "", None, "a//b", "a\nb")))

# adding
e1 = store.add("benchy.gcode", T0 + 3600)
check("added: waiting, its time in whole seconds", e1["status"] == "waiting" and e1["at"] == T0 + 3600 and e1["filename"] == "benchy.gcode")
check("kept in schedule.json in the data folder", json.load(open(os.path.join(folder, "schedule.json")))["entries"][0]["id"] == e1["id"])
for bad, at, why in (("../x", T0 + 60, "not a file of the printer"), ("a.gcode", "soon", "not a time"), ("a.gcode", T0 - 3600, "this time has passed"), ("a.gcode", T0 + 90 * 86400, "at most two months ahead")):
    try:
        store.add(bad, at)
        check("refused: " + why, False)
    except ps.ScheduleError as error:
        check("refused: " + why, str(error) == why, str(error))

# not yet its time
printer = Printer()
check("before its time nothing happens, the printer is not even asked", store.tick(printer.read, printer.start) == [] and printer.reads == 0)

# its time: started
clock.t = T0 + 3600
changed = store.tick(printer.read, printer.start)
check("at its time, printer ready and free: started", printer.started == ["benchy.gcode"] and changed and changed[0]["status"] == "started", changed)
check("... and marked so in the list", store.entries()[0]["status"] == "started")

# busy: missed, never started later
e2 = store.add("vase.gcode", T0 + 3700)
clock.t = T0 + 3700
changed = store.tick(printer.read, printer.start)
check("another print on at its time: missed (busy), not started", changed and changed[0]["status"] == "missed" and changed[0]["reason"] == "busy" and printer.started == ["benchy.gcode"], changed)
printer.state = "complete"
check("... and not started when the printer is free again", store.tick(printer.read, printer.start) == [] and printer.started == ["benchy.gcode"])

# Klipper not ready: waits the grace time, then missed
e3 = store.add("clip.gcode", T0 + 4000)
clock.t = T0 + 4000
printer.klippy = "startup"
check("Klipper starting at its time: it waits", store.tick(printer.read, printer.start) == [])
printer.klippy = "ready"
clock.t = T0 + 4000 + 120
check("... Klipper ready two minutes later: started then", [e["status"] for e in store.tick(printer.read, printer.start)] == ["started"] and printer.started[-1] == "clip.gcode")
printer.state = "complete"
e4 = store.add("late.gcode", T0 + 5000)
clock.t = T0 + 5000 + ps.NOT_READY_GRACE_S + 1
printer.klippy = "shutdown"
changed = store.tick(printer.read, printer.start)
check("Klipper still off after the grace time: missed (not_ready)", changed and changed[0]["reason"] == "not_ready", changed)

# Moonraker refuses
printer = Printer(refuse="File gone.gcode does not exist")
store.add("gone.gcode", clock.t + 10)
clock.t += 10
changed = store.tick(printer.read, printer.start)
check("Moonraker refuses: missed (error) with its words", changed and changed[0]["reason"] == "error" and "does not exist" in changed[0]["detail"], changed)

# two at the same minute
printer = Printer()
store.add("a.gcode", clock.t + 30)
store.add("b.gcode", clock.t + 30)
clock.t += 30
changed = store.tick(printer.read, printer.start)
check("two at the same time: the first prints, the second is missed (busy)", [(e["filename"], e["status"]) for e in changed] == [("a.gcode", "started"), ("b.gcode", "missed")] and printer.started == ["a.gcode"], changed)

# printer unreachable
def offline():
    raise OSError("connection refused")
store.add("c.gcode", clock.t + 5)
clock.t += 5
check("Moonraker not answering: it waits (grace time)", store.tick(offline, printer.start) == [])

# removing, forgetting
waiting = [e for e in store.entries() if e["status"] == "waiting"]
check("removing a waiting one", store.remove(waiting[0]["id"]) and not [e for e in store.entries() if e["id"] == waiting[0]["id"]])
check("removing an unknown one: false", store.remove("nope") is False)
clock.t += ps.KEEP_FINISHED_S + ps.NOT_READY_GRACE_S + 10
store.tick(printer.read, printer.start)
check("a day later the finished ones are forgotten", store.entries() == [], store.entries())

# a damaged file
open(os.path.join(folder, "schedule.json"), "w").write("{oops")
check("a damaged schedule.json reads as an empty list", store.entries() == [])
check("... and a new one can be added", store.add("x.gcode", clock.t + 100)["status"] == "waiting")

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
