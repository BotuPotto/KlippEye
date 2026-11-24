"""Release 1.148.0: the monitor's loop (audit findings 1, 2, 3, 28, 82): no crash without a model, no hang on a video stream,
a monitor that says when it cannot see, a light that stays on is no alarm, the replay leaves the purge out like the live
monitor. The service is loaded with its own data folder and a fake Moonraker and camera on a local port."""
import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import fakes  # noqa: E402

DATA = tempfile.mkdtemp(prefix="monitor_loop_")
os.environ["KLIPPEYE_DATA"] = DATA
fake = fakes.Fake()
spec = importlib.util.spec_from_file_location("kb", os.path.join(ROOT, "backend", "klippeye_backend.py"))
kb = importlib.util.module_from_spec(spec)
sys.modules["kb"] = kb
spec.loader.exec_module(kb)
import numpy as np  # noqa: E402
import requests  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   -> " + str(extra)[:300]) if (extra != "" and not cond) else ""), flush=True)


kb.detector.stop()
det = kb.detector

# --- 1: a calibrated camera (the first view is the bed, not «whole») and no local model: no crash --------------------------
kb.local_ai.model = None
det._bed_box = lambda z=None: (0.1, 0.3, 0.8, 0.6)
det._online_ai_usable = lambda: True
det.ai_online = True
try:
    ask, error = det._local_look(fakes.frame(), 1000.0, True), None
except Exception as e:  # noqa: BLE001
    ask, error = None, e
check("1.148.0: with a calibration and no usable local model a check does not raise (the motion trigger still reaches the AI)",
      error is None and ask is True, (ask, error))
del det._bed_box
del det._online_ai_usable

# --- 2: a snapshot address that is a video stream: refused or cut, never a hang --------------------------------------------
JPEG = fakes.jpeg(fakes.frame())


class Camera(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/photo"):
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(JPEG)))
            self.end_headers()
            self.wfile.write(JPEG)
            return
        self.send_response(200)
        # /mjpeg says what it is; /endless is a stream that calls itself a jpeg
        self.send_header("Content-Type", "multipart/x-mixed-replace;boundary=f" if self.path.startswith("/mjpeg") else "image/jpeg")
        self.end_headers()
        try:
            while True:
                self.wfile.write(b"--f\r\nContent-Type: image/jpeg\r\n\r\n" + b"\xff" * 200000 + b"\r\n")
                time.sleep(0.05)
        except OSError:
            pass


cam = ThreadingHTTPServer(("127.0.0.1", 0), Camera)
threading.Thread(target=cam.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % cam.server_address[1]
check("1.148.0: a photo address answers with the photo", kb.fetch_picture(base + "/photo", 2).content == JPEG)
for path, why in (("/mjpeg", "a multipart stream is refused"), ("/endless", "an endless answer is cut at a size")):
    started, error = time.time(), None
    try:
        kb.fetch_picture(base + path, 2)
    except requests.RequestException as e:
        error = e
    took = time.time() - started
    check("1.148.0: " + why + " at once, not after minutes", error is not None and took < 6, (error, took))

# --- 3: the monitor says when it cannot see ------------------------------------------------------------------------------------
kb.MOONRAKER_URL = "http://127.0.0.1:%d" % fake.port
kb.CAMERA_NGINX_URL = kb.MOONRAKER_URL + "/webcam"
kb._SNAPSHOT["at"] = 0
det.check_interval = 1


def wait_for(text, seconds):
    end = time.time() + seconds
    while time.time() < end and det.stats["status"] != text:
        time.sleep(0.25)
    return det.stats["status"]


fake.state["frames"] = [b"not a picture"]
det.start()
check("1.148.0: the camera does not answer with a picture: the status says so", wait_for("no picture from the camera", 12) == "no picture from the camera", det.stats["status"])
real_url = kb.MOONRAKER_URL
kb.MOONRAKER_URL = "http://127.0.0.1:1"
check("1.148.0: Moonraker does not answer: the status says so", wait_for("Moonraker does not answer", 12) == "Moonraker does not answer", det.stats["status"])
kb.MOONRAKER_URL = real_url
det.stop()

# --- 28: a light that stays on is a global change until the background follows it -----------------------------------------
from monitor_core import FrameJudge  # noqa: E402

judge = FrameJudge()
judge.verbose = False
judge.apply_config({})
base_picture = np.full((720, 1080, 3), 90, np.uint8)
lit = base_picture.copy()
lit[:, :540] = 170
t, triggers = 0.0, []
for k in range(80):
    t += judge.check_interval
    if t < judge.cooldown_until:
        continue
    _, triggered = judge.judge(base_picture if k < 40 else lit, b"", t)
    if triggered and k >= 40:
        triggers.append(k)
check("1.148.0: a lamp that lights half the scene and stays on is no alarm (the streak follows the background)", not triggers and judge.global_streak_max >= 13, (triggers, judge.global_streak_max))

# --- 82: the replay leaves the purge's marks out, as the live monitor does ----------------------------------------------------
import replay  # noqa: E402
from recorder import Recorder  # noqa: E402

blob = fakes.frame(rect=(230, 200, 90, 300), base=100)
empty = fakes.frame(base=100)
folder = os.path.join(tempfile.mkdtemp(prefix="replay_purge_"), "20261124-120000")
os.makedirs(folder)
rows = []
for n in range(1, 61):
    with open(os.path.join(folder, "%06d.jpg" % n), "wb") as f:
        f.write(fakes.jpeg(__import__("cv2").resize(empty if n <= 20 else blob, (540, 360))))
    rows.append({"n": n, "t": n * 3.0})
with open(os.path.join(folder, "frames.jsonl"), "w") as f:
    f.write("\n".join(json.dumps(r) for r in rows))
session = {"id": "20261124-120000"}
without = replay.replay_session(folder, session, {})
marks = np.zeros((360, 540), np.uint8)
marks[:, 100:200] = 255   # where the purge was; the change is inside it
import cv2  # noqa: E402

cv2.imwrite(os.path.join(folder, "purge.png"), marks)
with_marks = replay.replay_session(folder, session, {})
check("1.148.0: the replay of a recording with a purge.png does not count a change inside the purge's marks",
      without["alarms"] and not with_marks["alarms"], (without["alarms"], with_marks["alarms"]))
rec = Recorder(tempfile.mkdtemp(prefix="rec_"), cv2)
rec.enabled = True
rec.observe("printing", "x.gcode", time.time(), {})
rec.note_purge(marks)
kept = cv2.imread(os.path.join(rec.root, rec.session["id"], "purge.png"), cv2.IMREAD_GRAYSCALE)
check("1.148.0: the recorder keeps the purge mask once per recording", kept is not None and (kept == marks).all())

print("\n%d check(s) failed" % len(FAILS) if FAILS else "\nall checks passed")
sys.exit(1 if FAILS else 0)
