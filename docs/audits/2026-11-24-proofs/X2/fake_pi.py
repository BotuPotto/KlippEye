#!/usr/bin/env python3
"""Fake Moonraker (HTTP + /websocket) or fake camera, one role per process, for the X2 audit pass.

    python3 fake_pi.py moonraker PORT [PROFILE]    PROFILE: corexy (default), nocam, nomesh, slinger, delta
    python3 fake_pi.py camera PORT

Control while it runs: POST /_ctl with a JSON object merged into the state (camera: {"mode": "ok"|"503"|"hang"|"tiny"}).
The camera serves 1280x720 JPEGs: a textured bed, a part that grows, a toolhead that moves, sensor noise. With
{"spaghetti": true} strands appear outside the part. Pictures are made in advance (cheap to serve).
"""
import base64
import hashlib
import json
import struct
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROLE, PORT = sys.argv[1], int(sys.argv[2])
PROFILE = sys.argv[3] if len(sys.argv) > 3 else "corexy"
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
STATE = {"mode": "ok", "spaghetti": False, "print_state": "printing", "t0": time.time(), "db": {}, "hits": 0}
LOCK = threading.Lock()

# ---------------------------------------------------------------------------------------------- the printer's config
CONFIGS = {
    "corexy": {"printer": {"kinematics": "corexy", "max_velocity": 500}, "stepper_x": {"position_min": 0, "position_max": 350},
               "stepper_y": {"position_min": 0, "position_max": 350}, "stepper_z": {"position_min": -5, "position_max": 340},
               "bed_mesh": {"mesh_min": [10, 10], "mesh_max": [340, 340]}, "extruder": {}, "heater_bed": {}},
    "slinger": {"printer": {"kinematics": "cartesian"}, "stepper_x": {"position_min": 0, "position_max": 235},
                "stepper_y": {"position_min": 0, "position_max": 235}, "stepper_z": {"position_min": 0, "position_max": 250},
                "bed_mesh": {"mesh_min": [10, 10], "mesh_max": [225, 225]}, "extruder": {}, "heater_bed": {}},
    "delta": {"printer": {"kinematics": "delta", "delta_radius": 140, "print_radius": 120, "minimum_z_position": -5},
              "stepper_a": {"position_endstop": 300, "arm_length": 300}, "stepper_b": {"arm_length": 300},
              "stepper_c": {"arm_length": 300}, "extruder": {}, "heater_bed": {}},
}
CONFIGS["nomesh"] = {k: v for k, v in CONFIGS["corexy"].items() if k != "bed_mesh"}
CONFIGS["nocam"] = CONFIGS["corexy"]
CONFIG = CONFIGS[PROFILE]
if PROFILE == "delta":
    LIMITS = ([-120.0, -120.0, -5.0], [120.0, 120.0, 300.0])
elif PROFILE == "slinger":
    LIMITS = ([0.0, 0.0, 0.0], [235.0, 235.0, 250.0])
else:
    LIMITS = ([0.0, 0.0, -5.0], [350.0, 350.0, 340.0])


def objects():
    t = time.time() - STATE["t0"]
    x = LIMITS[0][0] + (LIMITS[1][0] - LIMITS[0][0]) * (0.5 + 0.3 * __import__("math").sin(t / 2.0))
    y = LIMITS[0][1] + (LIMITS[1][1] - LIMITS[0][1]) * (0.5 + 0.3 * __import__("math").cos(t / 3.0))
    z = 0.2 + (t / 3600.0) * 20
    prog = min(0.99, 0.05 + t / 200000.0)
    out = {
        "print_stats": {"state": STATE["print_state"], "filename": "long_part.gcode", "total_duration": 600 + t, "print_duration": 500 + t,
                        "filament_used": t, "message": "", "info": {"current_layer": int(z / 0.2), "total_layer": 400}},
        "display_status": {"progress": prog, "message": None},
        "virtual_sdcard": {"file_position": int(prog * 1e7), "file_size": 10000000, "is_active": True, "progress": prog},
        "extruder": {"temperature": 210.0, "target": 210.0, "power": 0.4, "pressure_advance": 0.04},
        "heater_bed": {"temperature": 60.0, "target": 60.0, "power": 0.3},
        "toolhead": {"position": [x, y, z, 100.0], "homed_axes": "xyz", "axis_minimum": LIMITS[0] + [0], "axis_maximum": LIMITS[1] + [0],
                     "max_velocity": 500, "max_accel": 10000, "print_time": t, "estimated_print_time": t},
        "motion_report": {"live_position": [x, y, z, 100.0], "live_velocity": 100.0},
        "gcode_move": {"speed_factor": 1.0, "extrude_factor": 1.0, "homing_origin": [0, 0, 0, 0], "gcode_position": [x, y, z, 0]},
        "webhooks": {"state": "ready", "state_message": "Printer is ready"},
        "idle_timeout": {"state": "Printing"},
        "fan": {"speed": 1.0},
        "configfile": {"settings": CONFIG, "config": CONFIG, "save_config_pending": False},
        "exclude_object": {"objects": [{"name": "part_1", "center": [175, 175], "polygon": [[150, 150], [200, 150], [200, 200], [150, 200]]}],
                           "excluded_objects": [], "current_object": "part_1"},
    }
    if PROFILE != "nomesh" and "bed_mesh" in CONFIG:
        out["bed_mesh"] = {"profile_name": "default", "mesh_min": CONFIG["bed_mesh"]["mesh_min"], "mesh_max": CONFIG["bed_mesh"]["mesh_max"],
                           "probed_matrix": [[0.0] * 5 for _ in range(5)], "mesh_matrix": [[0.0] * 5 for _ in range(5)], "profiles": {}}
    return out


def settings_doc():
    with LOCK:
        doc = dict(STATE["db"].get("settings") or {})
    if PROFILE != "nocam" and "camera" not in doc:
        doc["camera"] = {"snapshot": STATE.get("snapshot", "")}
    return doc


# ---------------------------------------------------------------------------------------------- the camera's pictures
FRAMES = []


def make_frames():
    import numpy as np
    import cv2
    rng = np.random.default_rng(1)
    H, W = 720, 1280
    base = np.full((H, W, 3), (60, 60, 70), np.uint8)
    cv2.rectangle(base, (200, 260), (1080, 700), (40, 40, 40), -1)              # the bed
    tex = rng.integers(0, 12, (H, W, 1), dtype=np.uint8)
    base = cv2.add(base, np.repeat(tex, 3, axis=2))
    cv2.rectangle(base, (0, 0), (1280, 120), (90, 90, 90), -1)                   # the frame on top
    for i in range(240):
        img = base.copy()
        grow = 10 + i // 8
        cv2.rectangle(img, (600, 560 - grow), (680, 560), (30, 30, 200), -1)    # the part, growing
        hx = int(640 + 300 * np.sin(i / 6.0))
        cv2.rectangle(img, (hx - 60, 300), (hx + 60, 480), (20, 20, 20), -1)    # the toolhead
        cv2.rectangle(img, (0, 280), (1280, 300), (110, 110, 110), -1)          # the gantry
        noise = rng.normal(0, 3, (H, W, 3))
        img = np.clip(img.astype(np.int16) + noise.astype(np.int16), 0, 255).astype(np.uint8)
        ok_plain, plain = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        spag = img.copy()
        for k in range(12):
            p = [(int(300 + 40 * k + 30 * np.sin(j + k)), int(600 + 8 * j + 20 * np.cos(j * k))) for j in range(10)]
            cv2.polylines(spag, [np.array(p, np.int32)], False, (40, 40, 220), 3)
        ok_spag, bad = cv2.imencode(".jpg", spag, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        FRAMES.append((plain.tobytes(), bad.tobytes()))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_POST(self):
        body = self._body()
        path = urllib.parse.urlparse(self.path).path
        if path == "/_ctl":
            with LOCK:
                STATE.update(json.loads(body or b"{}"))
            return self._send(200, {"ok": True})
        if path == "/server/database/item":
            data = json.loads(body or b"{}")
            with LOCK:
                STATE["db"][data.get("key")] = data.get("value")
            return self._send(200, {"result": {"namespace": data.get("namespace"), "key": data.get("key"), "value": data.get("value")}})
        if path == "/printer/gcode/script":
            return self._send(200, {"result": "ok"})
        return self._send(200, {"result": "ok"})

    def do_GET(self):
        with LOCK:
            STATE["hits"] += 1
        url = urllib.parse.urlparse(self.path)
        path, qs = url.path, url.query
        if ROLE == "camera":
            mode = STATE["mode"]
            if mode == "hang":
                time.sleep(30)
                return self._send(503, b"{}")
            if mode == "503":
                return self._send(503, b"{}")
            i = int((time.time() - STATE["t0"]) / 1.0) % len(FRAMES)
            data = FRAMES[i][1 if STATE["spaghetti"] else 0]
            if mode == "tiny":
                data = data[:500]
            return self._send(200, data, "image/jpeg")
        if path == "/websocket" and self.headers.get("Upgrade", "").lower() == "websocket":
            return self._websocket()
        if path == "/_state":
            return self._send(200, STATE if False else {"hits": STATE["hits"], "db": STATE["db"]})
        if path == "/printer/objects/query":
            names = [p.split("=")[0] for p in qs.split("&") if p]
            allo = objects()
            return self._send(200, {"result": {"eventtime": time.time(), "status": {n: allo[n] for n in names if n in allo}}})
        if path == "/printer/objects/list":
            return self._send(200, {"result": {"objects": list(objects())}})
        if path == "/printer/info":
            return self._send(200, {"result": {"state": "ready", "state_message": "Printer is ready", "hostname": "fakepi", "software_version": "v0.12"}})
        if path == "/server/info":
            return self._send(200, {"result": {"klippy_connected": True, "klippy_state": "ready", "components": ["database", "file_manager", "webcam"],
                                               "moonraker_version": "v0.9", "api_version": [1, 5, 0]}})
        if path == "/server/database/item":
            key = urllib.parse.parse_qs(qs).get("key", [""])[0]
            if key == "settings":
                return self._send(200, {"result": {"namespace": "klippeye", "key": key, "value": settings_doc()}})
            with LOCK:
                if key in STATE["db"]:
                    return self._send(200, {"result": {"namespace": "klippeye", "key": key, "value": STATE["db"][key]}})
            return self._send(404, {"error": {"code": 404, "message": "Key not found"}})
        if path == "/server/webcams/list":
            cams = [] if PROFILE == "nocam" else [{"name": "cam", "snapshot_url": STATE.get("snapshot", ""), "stream_url": "/webcam/?action=stream", "service": "mjpegstreamer"}]
            return self._send(200, {"result": {"webcams": cams}})
        if path.startswith("/server/files/list"):
            return self._send(200, {"result": [{"path": "long_part.gcode", "modified": 1700000000.0, "size": 10000000, "permissions": "rw"}]})
        if path.startswith("/server/files/metadata"):
            return self._send(200, {"result": {"filename": "long_part.gcode", "size": 10000000, "estimated_time": 200000,
                                               "first_layer_height": 0.2, "layer_height": 0.2, "object_height": 80}})
        if path.startswith("/server/files/gcodes/"):
            return self._send(200, b"; fake\nEXCLUDE_OBJECT_DEFINE NAME=part_1 CENTER=175,175 POLYGON=[[150,150],[200,150],[200,200],[150,200]]\nG1 X10 Y10\n", "text/plain")
        if path.startswith("/server/history/list"):
            return self._send(200, {"result": {"count": 0, "jobs": []}})
        if path.startswith("/machine/system_info"):
            return self._send(200, {"result": {"system_info": {"cpu_info": {"cpu_count": 4}, "service_state": {}}}})
        if path.startswith("/machine/proc_stats"):
            return self._send(200, {"result": {"moonraker_stats": [], "throttled_state": {"bits": 0, "flags": []}, "cpu_temp": 45}})
        return self._send(404, {"error": {"code": 404, "message": "Not found"}})

    # -------------------------------------------------------------------------------- a small Moonraker websocket
    def _ws_send(self, data):
        payload = json.dumps(data).encode()
        n = len(payload)
        head = bytes([0x81, n]) if n < 126 else (bytes([0x81, 126]) + struct.pack(">H", n) if n < 65536 else bytes([0x81, 127]) + struct.pack(">Q", n))
        self.wfile.write(head + payload)
        self.wfile.flush()

    def _websocket(self):
        key = self.headers.get("Sec-WebSocket-Key", "").encode()
        accept = base64.b64encode(hashlib.sha1(key + GUID.encode()).digest()).decode()
        self.wfile.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n" % accept).encode())
        self.wfile.flush()
        self.close_connection = True
        subscribed = []
        stop = threading.Event()

        def beat():
            while not stop.wait(1.0):
                try:
                    allo = objects()
                    diff = {n: allo[n] for n in subscribed if n in allo and n in ("print_stats", "toolhead", "motion_report", "display_status", "virtual_sdcard")}
                    self._ws_send({"jsonrpc": "2.0", "method": "notify_status_update", "params": [diff, time.time()]})
                    self._ws_send({"jsonrpc": "2.0", "method": "notify_proc_stat_update", "params": [{"cpu_temp": 45}]})
                except OSError:
                    return
        threading.Thread(target=beat, daemon=True).start()
        try:
            while True:
                first = self.rfile.read(2)
                if len(first) < 2:
                    return
                size = first[1] & 0x7F
                if size == 126:
                    size = struct.unpack(">H", self.rfile.read(2))[0]
                elif size == 127:
                    size = struct.unpack(">Q", self.rfile.read(8))[0]
                mask = self.rfile.read(4)
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(self.rfile.read(size)))
                op = first[0] & 0x0F
                if op == 0x8:
                    return
                if op == 0x9:
                    continue
                if op != 0x1:
                    continue
                msg = json.loads(payload)
                if msg.get("method") == "printer.objects.subscribe":
                    asked = list((msg.get("params") or {}).get("objects") or {})
                    subscribed[:] = asked
                    allo = objects()
                    self._ws_send({"jsonrpc": "2.0", "id": msg.get("id"), "result": {"eventtime": time.time(), "status": {n: allo[n] for n in asked if n in allo}}})
                elif "id" in msg:
                    self._ws_send({"jsonrpc": "2.0", "id": msg.get("id"), "result": {}})
        except (OSError, ValueError):
            return
        finally:
            stop.set()


if __name__ == "__main__":
    if ROLE == "camera":
        make_frames()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.daemon_threads = True
    print("fake %s %s on %d" % (ROLE, PROFILE, PORT), flush=True)
    server.serve_forever()
