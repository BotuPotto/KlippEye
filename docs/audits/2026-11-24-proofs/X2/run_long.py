#!/usr/bin/env python3
"""X2 run 1+2: a long print sped up, with Moonraker stopped and started and the camera not answering for a while.

    python3 run_long.py [minutes=22] [fast=0.2]

The backend's loop pauses at most `fast` s between checks (default check_interval 1 s, so ~4 checks a second instead
of one every 3 s). Two "browsers" poll what the dashboard polls. Every 20 s: memory, threads, files, data folder.
Writes out/long.json and out/long-backend.log.
"""
import json
import os
import random
import signal
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import http, new_data, proc_sample, start_backend, start_fake, stop, tree_sizes, wait_port  # noqa: E402

MIN = float(sys.argv[1]) if len(sys.argv) > 1 else 22
FAST = float(sys.argv[2]) if len(sys.argv) > 2 else 0.2
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)
MP, CP, BP = 17201, 17202, 18201
B = "http://127.0.0.1:%d" % BP
LOG = os.path.join(OUT, "long-backend.log")
DUMP = os.path.join(OUT, "long-dump.jsonl")
for f in (LOG, DUMP):
    if os.path.exists(f):
        os.remove(f)

data = new_data({"warmup_seconds": 0, "check_interval": 1, "record": True, "print_review": True})
cam = start_fake("camera", CP, log=os.path.join(OUT, "long-cam.log"))
moon = start_fake("moonraker", MP, log=os.path.join(OUT, "long-moon.log"))
http("POST", "http://127.0.0.1:%d/_ctl" % MP, {"snapshot": "http://127.0.0.1:%d/?action=snapshot" % CP})
os.environ["X2_DUMP"] = DUMP
back = start_backend(data, BP, MP, fast=FAST, log=LOG)
assert wait_port(B + "/api/print/detector/status", 60), "backend did not start"

T0 = time.time()
events, samples, errors = [], [], {"poll_fail": 0, "poll_ok": 0}
running = True


def at(frac):
    return T0 + MIN * 60 * frac


def browser(name):
    paths = ["/api/print/detector/status", "/api/print/last_analysis", "/printer/objects/query?print_stats&toolhead&extruder&heater_bed",
             "/api/recordings", "/api/print/alerts/history", "/server/info", "/api/local_model"]
    while running:
        for p in paths:
            code, _ = http("GET", B + p, timeout=15)
            errors["poll_ok" if code == 200 else "poll_fail"] += 1
        time.sleep(1.0 + random.random())


for i in range(2):
    threading.Thread(target=browser, args=("b%d" % i,), daemon=True).start()

plan = [  # (fraction of the run, what)
    (0.20, "spaghetti on"), (0.23, "spaghetti off"),
    (0.35, "moonraker stop"), (0.45, "moonraker start"),
    (0.55, "camera hang"), (0.62, "camera 503"), (0.66, "camera ok"),
    (0.75, "spaghetti on"), (0.78, "spaghetti off"),
]
done = set()


def apply(what):
    global moon
    if what == "moonraker stop":
        stop(moon, signal.SIGKILL)
    elif what == "moonraker start":
        moon = start_fake("moonraker", MP, log=os.path.join(OUT, "long-moon.log"))
        http("POST", "http://127.0.0.1:%d/_ctl" % MP, {"snapshot": "http://127.0.0.1:%d/?action=snapshot" % CP})
    elif what.startswith("camera "):
        http("POST", "http://127.0.0.1:%d/_ctl" % CP, {"mode": what.split()[1]})
    elif what == "spaghetti on":
        http("POST", "http://127.0.0.1:%d/_ctl" % CP, {"spaghetti": True})
    elif what == "spaghetti off":
        http("POST", "http://127.0.0.1:%d/_ctl" % CP, {"spaghetti": False})


def log_lines():
    try:
        with open(LOG, errors="ignore") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


next_sample = T0
end = at(1.0)
while time.time() < end:
    now = time.time()
    for frac, what in plan:
        if (frac, what) not in done and now >= at(frac):
            done.add((frac, what))
            apply(what)
            events.append({"t": round(now - T0, 1), "what": what})
            print("%6.0fs %s" % (now - T0, what), flush=True)
    if now >= next_sample:
        next_sample += 20
        s = {"t": round(now - T0, 1)}
        try:
            s.update(proc_sample(back.pid))
        except Exception as e:  # noqa: BLE001
            s["proc_error"] = str(e)
        code, st = http("GET", B + "/api/print/detector/status", timeout=15)
        if isinstance(st, dict):
            stats = st.get("stats") or {}
            s.update(frames=stats.get("frames_checked"), status=(stats.get("status") or "")[:90], anomalies=stats.get("anomalies"),
                     check_ms=stats.get("check_ms"))
        sizes = tree_sizes(data)
        s["files"] = len(sizes)
        s["bytes"] = sum(sizes.values())
        groups = {}
        for path, size in sizes.items():
            top = path.split(os.sep)[0]
            key = top if os.sep not in path else top + "/" + ("*" if not path.endswith(".json") and not path.endswith(".jsonl") else os.path.basename(path))
            g = groups.setdefault(key, [0, 0])
            g[0] += 1
            g[1] += size
        s["groups"] = groups
        s["log_lines"] = log_lines()
        back.send_signal(signal.SIGUSR1)
        samples.append(s)
        print("%6.0fs rss=%s thr=%s fds=%s tcp=%s frames=%s files=%d bytes=%d log=%d %s" % (
            s["t"], s.get("rss_mb"), s.get("threads"), s.get("fds"), s.get("tcp"), s.get("frames"), s["files"], s["bytes"], s["log_lines"],
            s.get("status", "")[:50]), flush=True)
    time.sleep(0.5)

running = False
largest = sorted(tree_sizes(data).items(), key=lambda kv: -kv[1])[:30]
result = {"minutes": MIN, "fast": FAST, "data": data, "events": events, "samples": samples, "polls": errors, "largest": largest,
          "alive": back.poll() is None}
stop(back)
stop(moon)
stop(cam)
json.dump(result, open(os.path.join(OUT, "long.json"), "w"), indent=1)
print("written", os.path.join(OUT, "long.json"), "data", data)
