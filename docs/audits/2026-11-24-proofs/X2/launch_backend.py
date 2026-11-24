#!/usr/bin/env python3
"""Runs the real backend/klippeye_backend.py as __main__ with the fake Moonraker's address.

    KLIPPEYE_DATA=... KLIPPEYE_PORT=... X2_MOONRAKER=http://127.0.0.1:P [X2_FAST=0.2] python3 launch_backend.py

The only change to the program is the Moonraker constant (hard-coded in the source). X2_FAST=s makes every pause of the
monitor loop at most s seconds (a long print in less time); nothing else is touched.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
PATH = os.path.join(ROOT, "backend", "klippeye_backend.py")
src = open(PATH, encoding="utf-8").read()
moon = os.environ["X2_MOONRAKER"]
old = 'MOONRAKER_URL = "http://127.0.0.1:7125"'
assert old in src
src = src.replace(old, 'MOONRAKER_URL = %r' % moon, 1)
fast = os.environ.get("X2_FAST")
if fast:
    marker = 'if __name__ == "__main__":'
    patch = ("_x2_nap = LightDetector._nap\n"
             "LightDetector._nap = lambda self, g, s: _x2_nap(self, g, min(s, %s))\n" % float(fast))
    i = src.rindex(marker)
    src = src[:i] + patch + src[i:]
dump = os.environ.get("X2_DUMP")
if dump:   # SIGUSR1: the threads' names and the most common object types, for finding what grows
    import collections, gc, json, signal, threading

    trace = os.environ.get("X2_TRACE") == "1"
    if trace:
        import tracemalloc
        tracemalloc.start(6)
    _first = {}

    def _dump(*_):
        names = collections.Counter(t.name.split("-")[0] if t.name.startswith("Thread-") else t.name for t in threading.enumerate())
        objs = gc.get_objects()
        types = collections.Counter(type(o).__name__ for o in objs)
        big = sorted(((len(o), type(o).__name__, repr(list(o)[:2] if isinstance(o, (list, collections.deque)) else list(o)[:3])[:120])
                      for o in objs if isinstance(o, (list, dict, collections.deque, set)) and len(o) > 300), reverse=True)[:12]
        row = {"threads": dict(names), "types": dict(types.most_common(25)), "objects": sum(types.values()), "big": big}
        if trace:
            snap = tracemalloc.take_snapshot().filter_traces([tracemalloc.Filter(False, tracemalloc.__file__)])
            if "s" not in _first:
                _first["s"] = snap
            diff = snap.compare_to(_first["s"], "traceback")
            row["traced_mb"] = round(tracemalloc.get_traced_memory()[0] / 2**20, 2)
            row["grow"] = [[round(d.size_diff / 1024, 1), d.count_diff, " <- ".join("%s:%d" % (os.path.basename(f.filename), f.lineno) for f in d.traceback[-4:])]
                           for d in diff[:12]]
        with open(dump, "a") as fh:
            fh.write(json.dumps(row) + "\n")
    signal.signal(signal.SIGUSR1, _dump)
sys.path.insert(0, os.path.dirname(PATH))
sys.argv = [PATH]
code = compile(src, PATH, "exec")
exec(code, {"__name__": "__main__", "__file__": PATH, "__builtins__": __builtins__})
