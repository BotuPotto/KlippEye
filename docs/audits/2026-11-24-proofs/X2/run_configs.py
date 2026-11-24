#!/usr/bin/env python3
"""X2 run 5: printers that are not the owner's, through the fake Moonraker's configfile / objects.

    python3 run_configs.py [profiles=corexy,nocam,nomesh,slinger,delta] [seconds printing=45]

For each: the backend on a fresh data folder while a print runs; every GET route without parameters (except the ones
that run tools or call AI services); the monitor's status; the error lines of its log. Writes out/configs.json.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import http, new_data, start_backend, start_fake, stop, wait_port  # noqa: E402

PROFILES = (sys.argv[1] if len(sys.argv) > 1 else "corexy,nocam,nomesh,slinger,delta").split(",")
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 45
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
MP, CP, BP = 17501, 17502, 18501
B = "http://127.0.0.1:%d" % BP
SKIP = ("/api/logs/analyze", "/api/diagnose", "/api/update/channel", "/api/print/analyze", "/api/recordings/measure", "/api/ai/models",
        "/api/logs/download", "/api/local_model/personal/export")
src = open(os.path.join(ROOT, "backend", "klippeye_backend.py")).read()
GETS = [p for p, m in re.findall(r'@app\.route\("([^"]+)"(?:,\s*methods=\[([^\]]*)\])?\)', src)
        if "<" not in p and (not m or '"GET"' in m) and p not in SKIP]

cam = start_fake("camera", CP)
results = {}
for profile in PROFILES:
    moon = start_fake("moonraker", MP, profile)
    if profile != "nocam":
        http("POST", "http://127.0.0.1:%d/_ctl" % MP, {"snapshot": "http://127.0.0.1:%d/?action=snapshot" % CP})
    data = new_data({"warmup_seconds": 0, "check_interval": 1, "record": True})
    log = os.path.join(OUT, "configs-%s.log" % profile)
    if os.path.exists(log):
        os.remove(log)
    back = start_backend(data, BP, MP, log=log)
    assert wait_port(B + "/api/print/detector/status", 60)
    time.sleep(SECONDS)
    row = {"routes": {}}
    for path in GETS:
        t = time.time()
        code, body = http("GET", B + path, timeout=30)
        row["routes"][path] = code
        if code is None or code >= 500:
            row.setdefault("errors", {})[path] = str(body)[:300]
        if time.time() - t > 5:
            row.setdefault("slow", {})[path] = round(time.time() - t, 1)
    _, st = http("GET", B + "/api/print/detector/status")
    stats = (st or {}).get("stats") or {}
    row["monitor"] = {k: stats.get(k) for k in ("status", "frames_checked", "anomalies", "real_print_reason", "zone", "masked", "purge")}
    _, cal = http("GET", B + "/api/camera/calibration")
    if isinstance(cal, dict):
        row["calibration"] = {k: cal.get(k) for k in ("usable", "bed", "limits", "z_moves", "kinematics", "bed_moves_in_y", "refused", "problem", "error")}
        row["calibration_keys"] = sorted(cal)
    _, lm = http("GET", B + "/api/local_model")
    if isinstance(lm, dict):
        row["local_model"] = {k: lm.get(k) for k in ("bed_view", "view", "enabled", "available")}
    try:
        row["machine_shape"] = json.load(open(os.path.join(data, "machine_shape.json")))
    except Exception as e:  # noqa: BLE001
        row["machine_shape"] = "missing: %s" % e
    text = open(log, errors="ignore").read()
    lines = [l for l in text.splitlines() if not re.search(r'" \d{3} -$', l)]
    row["log_errors"] = [l for l in lines if re.search(r"err|fail|Traceback|Exception|cannot", l, re.I)][:40]
    row["log_error_count"] = len([l for l in lines if re.search(r"err|fail|Traceback|Exception|cannot", l, re.I)])
    row["tracebacks"] = text.count("Traceback")
    stop(back)
    stop(moon)
    results[profile] = row
    print(profile, json.dumps({k: row[k] for k in ("monitor", "log_error_count", "tracebacks")})[:600], "errors:", list((row.get("errors") or {}).keys()), flush=True)
stop(cam)
json.dump(results, open(os.path.join(OUT, "configs.json"), "w"), indent=1)
