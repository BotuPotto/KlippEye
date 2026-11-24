#!/usr/bin/env python3
"""X2 run 3: the backend killed (SIGKILL) at random moments while it writes, then started again.

    python3 run_kill.py [rounds per kind=8] [kinds=settings,ai,false,label,recording,shape]

Each kind keeps its own data folder across its rounds (as a real Pi would). After each kill: does it start again, is
every file whole, is what was acknowledged (HTTP 200) still there? Writes out/kill.json.
"""
import glob
import json
import os
import random
import shutil
import signal
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import http, new_data, start_backend, start_fake, stop, wait_port  # noqa: E402

ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 8
KINDS = (sys.argv[2] if len(sys.argv) > 2 else "settings,ai,false,label,recording,shape").split(",")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)
MP, CP, BP = 17301, 17302, 18301
B = "http://127.0.0.1:%d" % BP
random.seed(7)

cam = start_fake("camera", CP)
moon = start_fake("moonraker", MP)
http("POST", "http://127.0.0.1:%d/_ctl" % MP, {"snapshot": "http://127.0.0.1:%d/?action=snapshot" % CP})
PROVIDERS = ["groq", "gemini", "openai", "anthropic", "mistral", "openrouter", "meta", "together", "fireworks"]


def seed_alerts(data, n=40):
    """n alarms in the history, each with its picture (a camera frame), as the monitor writes them."""
    import urllib.request
    folder = os.path.join(data, "alerts")
    os.makedirs(folder, exist_ok=True)
    jpg = urllib.request.urlopen("http://127.0.0.1:%d/?action=snapshot" % CP, timeout=10).read()
    lines = []
    for i in range(n):
        stamp = "20261120-10%02d%02d" % (i // 60, i % 60)
        with open(os.path.join(folder, stamp + "-now.jpg"), "wb") as f:
            f.write(jpg)
        lines.append(json.dumps({"id": stamp, "time": "2026-11-20 10:00:00", "image": stamp + "-now.jpg", "action": "PAUSE",
                                 "outcome": "local model", "confidence": 90, "local_score": 90}))
    with open(os.path.join(folder, "history.jsonl"), "w") as f:
        f.write("\n".join(lines) + "\n")
    return [json.loads(l)["id"] for l in lines]


def files_ok(data):
    """Every .json / .jsonl / .npz under data parses (a .jsonl may have a cut LAST line only). -> list of problems."""
    import numpy as np
    bad = []
    for path in glob.glob(os.path.join(data, "**", "*"), recursive=True):
        if not os.path.isfile(path):
            continue
        rel = os.path.relpath(path, data)
        try:
            if path.endswith(".json"):
                json.load(open(path))
            elif path.endswith(".jsonl"):
                lines = open(path).read().split("\n")
                for k, line in enumerate(lines):
                    if line.strip():
                        try:
                            json.loads(line)
                        except ValueError:
                            bad.append("%s: line %d of %d cut%s" % (rel, k + 1, len(lines), "" if k >= len(lines) - 2 else " (NOT the last)"))
            elif path.endswith(".npz"):
                np.load(path)["vectors"]
            elif path.endswith(".jpg") and os.path.getsize(path) < 100:
                bad.append("%s: %d bytes" % (rel, os.path.getsize(path)))
        except Exception as e:  # noqa: BLE001
            bad.append("%s: %s" % (rel, str(e)[:80]))
    return bad


def tmp_left(data):
    return [os.path.relpath(p, data) for p in glob.glob(os.path.join(data, "**", ".tmp*"), recursive=True) + glob.glob(os.path.join(data, "**", "*.tmp"), recursive=True)]


def writer(kind, data, acked, stop_flag, ctx):
    i = 0
    while not stop_flag.is_set():
        i += 1
        if kind == "settings":
            value = 5 + (i % 96)
            ctx["inflight"] = value
            code, _ = http("POST", B + "/api/backend/config", {"values": {"sensitivity": value}}, timeout=30)
            if code == 200:
                acked.append(value)
        elif kind == "ai":
            p = PROVIDERS[i % len(PROVIDERS)]
            key = "k%s%026d" % (p[:3], i)
            ctx["inflight"] = (p, key)
            code, _ = http("POST", B + "/api/ai/config", {"key": {"provider": p, "api_key": key}}, timeout=30)
            if code == 200:
                acked.append((p, key))
        elif kind == "false":
            aid = ctx["todo"][ctx["next"] % len(ctx["todo"])]
            label = "false" if (ctx["next"] // len(ctx["todo"])) % 2 == 0 else None
            ctx["inflight"] = (aid, label)
            code, body = http("POST", B + "/api/print/alerts/%s/label" % aid, {"label": label}, timeout=30)
            if code == 200:
                acked.append((aid, label))
                ctx["state"][aid] = label
                ctx["next"] += 1
        elif kind == "label":
            sid = ctx.get("sid")
            if not sid:
                code, body = http("GET", B + "/api/recordings", timeout=5)
                recs = (body or {}).get("sessions") if isinstance(body, dict) else None
                if recs:
                    ctx["sid"], ctx["started"] = recs[0]["id"], recs[0].get("started")
                time.sleep(0.2)
                continue
            outcome = ["ok", "failed", None][i % 3]
            body = {"outcome": outcome}
            if outcome == "failed":
                body["failed_at"] = (ctx.get("started") or time.time() - 5) + 1
            ctx["inflight"] = (sid, outcome)
            code, _ = http("POST", B + "/api/recordings/%s/label" % sid, body, timeout=5)
            if code == 200:
                acked.append((sid, outcome))
        elif kind == "shape":
            left = 20 + (i % 40)
            ctx["inflight"] = left
            code, _ = http("POST", B + "/api/camera/shape", {"toolhead": {"left": left}}, timeout=5)
            if code == 200:
                acked.append(left)
        elif kind == "recording":
            time.sleep(0.2)


def verify(kind, data, acked, ctx):
    out = {}
    if kind == "settings" and acked:
        v = json.load(open(os.path.join(data, "monitor.json")))["values"]["sensitivity"]
        out["ok"] = v in (acked[-1], ctx.get("inflight"))
        out["value"], out["last_acked"] = v, acked[-1]
    elif kind == "ai" and acked:
        cfg = json.load(open(os.path.join(data, "ai.json")))
        keys = cfg.get("keys") or {}
        last = {}
        for p, k in acked:
            last[p] = k
        inflight = (ctx.get("inflight") or (None, None))[1]
        lost = [p for p, k in last.items() if keys.get(p) not in (k, inflight)]
        out["ok"] = not lost
        out["lost"] = lost
        out["mode"] = oct(os.stat(os.path.join(data, "ai.json")).st_mode & 0o777)
    elif kind == "false":
        import numpy as np
        items_path = os.path.join(data, "personal", "false_alarms.json")
        vec_path = os.path.join(data, "personal", "false_alarms.npz")
        items = json.load(open(items_path))["items"] if os.path.exists(items_path) else []
        rows = len(np.load(vec_path)["vectors"]) if os.path.exists(vec_path) else 0
        out["items_on_disk"], out["rows_on_disk"] = len(items), rows
        want = {a for a, l in ctx["state"].items() if l == "false"}
        fl = ctx.get("inflight") or (None, None)
        out["want_false"] = len(want)
        # what the backend has after restart (it drops everything when the two files disagree)
        code, body = http("GET", B + "/api/local_model", timeout=10)
        fa = (body or {}).get("false_alarms") if isinstance(body, dict) else None
        out["loaded"] = fa
        out["in_step"] = len(items) == rows
        kept = {it.get("key") for it in items}
        out["acked_lost"] = sorted(a for a in want - kept if a != fl[0])
        out["acked_back"] = sorted(a for a in kept - want if a != fl[0])
        out["ok"] = out["in_step"] and not out["acked_lost"] and not out["acked_back"]
    elif kind == "label" and acked:
        sid = acked[-1][0]
        s = json.load(open(os.path.join(data, "recordings", sid, "session.json")))
        got = (s.get("label") or {}).get("outcome")
        out["ok"] = got in (acked[-1][1], (ctx.get("inflight") or (None, None))[1])
        out["got"], out["last_acked"] = got, acked[-1][1]
    elif kind == "shape" and acked:
        s = json.load(open(os.path.join(data, "machine_shape.json")))
        v = (s.get("toolhead") or {}).get("left")
        out["ok"] = v in (acked[-1], ctx.get("inflight"))
        out["value"], out["last_acked"] = v, acked[-1]
    elif kind == "recording":
        recs = []
        for folder in sorted(glob.glob(os.path.join(data, "recordings", "2*"))):
            sid = os.path.basename(folder)
            try:
                s = json.load(open(os.path.join(folder, "session.json")))
            except Exception as e:  # noqa: BLE001
                recs.append({"sid": sid, "session": "bad: %s" % e})
                continue
            lines = [l for l in open(os.path.join(folder, "frames.jsonl")).read().split("\n") if l.strip()] if os.path.exists(os.path.join(folder, "frames.jsonl")) else []
            jpgs = len(glob.glob(os.path.join(folder, "[0-9]*.jpg")))
            recs.append({"sid": sid, "frames_in_session": s.get("frames"), "lines": len(lines), "jpgs": jpgs, "ended": s.get("ended"), "end_state": s.get("end_state")})
        out["recordings"] = recs
        code, body = http("GET", B + "/api/recordings", timeout=10)
        listed = (body or {}).get("sessions") if isinstance(body, dict) else []
        out["listed"] = [{"id": r.get("id"), "frames": r.get("frames"), "ended": r.get("ended"), "end_state": r.get("end_state")} for r in listed or []]
        out["ok"] = all(isinstance(r.get("frames_in_session"), int) for r in recs)
    return out


results = {}
for kind in KINDS:
    values = {"warmup_seconds": 0, "check_interval": 1, "record": kind in ("label", "recording"), "print_review": True}
    data = new_data(values)
    ctx = {"all_acked": []}
    if kind == "false":
        ctx["todo"] = seed_alerts(data)
        ctx["next"], ctx["state"] = 0, {}
    rounds = []
    log = os.path.join(OUT, "kill-%s.log" % kind)
    if os.path.exists(log):
        os.remove(log)
    for r in range(ROUNDS):
        back = start_backend(data, BP, MP, log=log)
        t0 = time.time()
        up = wait_port(B + "/api/print/detector/status", 60)
        start_s = round(time.time() - t0, 1)
        row = {"round": r, "started": up, "start_s": start_s}
        if r > 0:   # the state the previous kill left, read by the backend that just started
            row["after_previous_kill"] = verify(kind, data, prev_acked, ctx) if up else {"ok": False, "why": "did not start"}
        if not up:
            row["log_tail"] = open(log).read()[-1500:]
            rounds.append(row)
            stop(back, signal.SIGKILL)
            break
        acked, flag = [], threading.Event()
        threads = [threading.Thread(target=writer, args=(kind, data, acked, flag, ctx), daemon=True) for _ in range(1)]
        for t in threads:
            t.start()
        delay = random.uniform(1.0, 6.0) if kind != "recording" else random.uniform(3.0, 12.0)
        time.sleep(delay)
        back.send_signal(signal.SIGKILL)
        back.wait()
        flag.set()
        for t in threads:
            t.join(6)
        row["killed_after_s"] = round(delay, 2)
        row["acked"] = len(acked)
        row["bad_files"] = files_ok(data)
        row["tmp_left"] = len(tmp_left(data))
        prev_acked = acked if acked else (prev_acked if r > 0 else [])
        rounds.append(row)
        print(kind, json.dumps(row)[:400], flush=True)
    # last check: start once more and verify
    back = start_backend(data, BP, MP, log=log)
    up = wait_port(B + "/api/print/detector/status", 60)
    final = verify(kind, data, prev_acked, ctx) if up else {"ok": False, "why": "did not start"}
    final["started"] = up
    final["bad_files"] = files_ok(data)
    final["tmp_left"] = tmp_left(data)
    final["tracebacks"] = open(log).read().count("Traceback")
    stop(back)
    results[kind] = {"data": data, "rounds": rounds, "final": final}
    print(kind, "FINAL", json.dumps(final)[:1500], flush=True)
    json.dump(results, open(os.path.join(OUT, "kill.json"), "w"), indent=1)

stop(moon)
stop(cam)
