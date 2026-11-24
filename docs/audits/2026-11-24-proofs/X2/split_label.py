#!/usr/bin/env python3
"""A restart in the middle of a print splits its recording in two (run_kill.py «recording»: 10 restarts -> 11 recordings
of one print, while «How did the print go?» keeps one review). The answer «failed at <moment>» then labels no recording.

The data folder below is what the backend leaves after a restart 2 h into a print: recording A (0-2 h, «interrupted
(power cut or restart)»), recording B (2 h - 3 h), one review (0-3 h). The person answers «failed» at 2.5 h (inside B).

    python3 -I .superpowers/audit/proofs/X2/split_label.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import http, new_data, start_backend, start_fake, stop, wait_port  # noqa: E402

MP, BP = 17601, 18601
B = "http://127.0.0.1:%d" % BP
T = time.time() - 3 * 3600
data = new_data({"record": True, "enabled": False})


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f)


def sid(t):
    return time.strftime("%Y%m%d-%H%M%S", time.localtime(t)) + "-long_part"


A, Bs, R = sid(T), sid(T + 7200), sid(T)
for rec, start, end, state in ((A, T, T + 7200, "interrupted (power cut or restart)"), (Bs, T + 7200, T + 10800, "complete")):
    write(os.path.join(data, "recordings", rec, "session.json"),
          {"id": rec, "file": "long_part.gcode", "started": start, "ended": end, "end_state": state, "frames": 1, "bytes": 10,
           "release": "1.137.0", "config": {}, "label": {"outcome": None, "failed_at": None}, "truncated": False, "live_triggers": [], "alerts": [], "cpu": {}})
    with open(os.path.join(data, "recordings", rec, "frames.jsonl"), "w") as f:
        f.write(json.dumps({"n": 1, "t": start + 1}) + "\n")
write(os.path.join(data, "reviews", R, "review.json"),
      {"id": R, "file": "long_part.gcode", "started": T, "ended": T + 10800, "end_state": "complete", "thumbs": [], "answer": None})

moon = start_fake("moonraker", MP)
http("POST", "http://127.0.0.1:%d/_ctl" % MP, {"print_state": "complete"})
back = start_backend(data, BP, MP, log="/tmp/x2-split.log")
assert wait_port(B + "/api/print/detector/status", 60)
code, body = http("POST", B + "/api/print/review/%s" % R, {"outcome": "failed", "failed_at": T + 9000})
print("answer:", code, (body or {}).get("ok") if isinstance(body, dict) else body)
for rec in (A, Bs):
    label = json.load(open(os.path.join(data, "recordings", rec, "session.json")))["label"]
    print("recording %s (%s): label %s" % (rec, "0-2 h" if rec == A else "2-3 h, the failure", label))
stop(back)
stop(moon)
print("log:", [l for l in open("/tmp/x2-split.log") if "REVIEW" in l])
