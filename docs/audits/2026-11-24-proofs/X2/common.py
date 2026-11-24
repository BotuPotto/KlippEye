"""Shared helpers for the X2 runs: start the fakes and the real backend, sample the process, stop everything."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def http(method, url, body=None, timeout=10, headers=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=dict({"Content-Type": "application/json"}, **(headers or {})))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except ValueError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def wait_port(url, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        code, _ = http("GET", url, timeout=2)
        if code is not None:
            return True
        time.sleep(0.3)
    return False


def start_fake(role, port, profile="corexy", log=None):
    out = open(log or os.devnull, "a")
    p = subprocess.Popen([PY, "-I", os.path.join(HERE, "fake_pi.py"), role, str(port), profile], stdout=out, stderr=subprocess.STDOUT)
    wait_port("http://127.0.0.1:%d/_state" % port, 90)
    return p


def new_data(values=None):
    d = tempfile.mkdtemp(prefix="x2data.")
    open(os.path.join(d, "no-repair"), "w").close()   # never let repair.sh touch the repository
    if values is not None:
        with open(os.path.join(d, "monitor.json"), "w") as f:
            json.dump({"formato": 1, "values": values}, f)
    return d


def start_backend(data, port, moon_port, fast=None, log=None, live=True):
    env = dict(os.environ, KLIPPEYE_DATA=data, KLIPPEYE_PORT=str(port), X2_MOONRAKER="http://127.0.0.1:%d" % moon_port, PYTHONUNBUFFERED="1")
    if fast:
        env["X2_FAST"] = str(fast)
    if not live:
        env["KLIPPEYE_LIVE"] = "0"
    out = open(log or os.devnull, "a")
    p = subprocess.Popen([PY, os.path.join(HERE, "launch_backend.py")], env=env, stdout=out, stderr=subprocess.STDOUT)
    return p


def stop(p, sig=signal.SIGTERM):
    if p and p.poll() is None:
        p.send_signal(sig)
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(5)


def tree_sizes(root):
    """{relative path of every file: size} under root."""
    out = {}
    for base, _, files in os.walk(root):
        for name in files:
            path = os.path.join(base, name)
            try:
                out[os.path.relpath(path, root)] = os.path.getsize(path)
            except OSError:
                pass
    return out


def proc_sample(pid):
    import psutil
    p = psutil.Process(pid)
    with p.oneshot():
        mem = p.memory_info()
        return {"rss_mb": round(mem.rss / 2**20, 2), "vms_mb": round(mem.vms / 2**20, 1), "threads": p.num_threads(), "fds": p.num_fds(),
                "tcp": len(p.net_connections(kind="tcp")) if hasattr(p, "net_connections") else len(p.connections(kind="tcp")),
                "cpu_s": round(sum(p.cpu_times()[:2]), 1)}
