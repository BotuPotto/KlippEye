"""A fake Moonraker + fake camera on one local port, controlled by the test (state dict)."""
import json, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import cv2, numpy as np

W, H = 1080, 720


def frame(rect=None, rect2=None, base=100):
    img = np.full((H, W, 3), base, np.uint8)
    for r in (rect, rect2):
        if r:
            x, y, w, h = r
            img[y:y + h, x:x + w] = 255
    return img


def jpeg(img):
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    return buf.tobytes()


class Fake:
    def __init__(self):
        self.state = {
            "print_state": "printing", "progress": 0.5, "file_position": 5000, "file_size": 10000, "total_duration": 500.0,
            "hotend": 210.0, "hotend_target": 210.0, "bed": 60.0, "bed_target": 60.0, "z": 5.0,
            "frames": [jpeg(frame())],  # served in turn, then the last one forever
            # the toolhead (camera calibration): machine position, homed axes, limits; render(state) -> JPEG replaces the frames
            "position": [175.0, 175.0, 10.0], "homed": "xyz", "axis_min": [0.0, 0.0, -5.0], "axis_max": [350.0, 350.0, 340.0],
            "render": None, "gcode_fail": None, "settings": {"printer": {"kinematics": "corexy"}, "z_tilt": {}},
        }
        self.scripts = []
        self.posts = []
        self.snapshots = 0
        self.status_calls = 0
        self.lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                s = fake.state
                if self.path.startswith("/webcam/snapshot") and s.get("render"):
                    return self._send(200, s["render"](s), "image/jpeg")
                if self.path.startswith("/webcam/snapshot"):
                    with fake.lock:
                        i = min(fake.snapshots, len(s["frames"]) - 1)
                        fake.snapshots += 1
                    return self._send(200, s["frames"][i], "image/jpeg")
                if self.path.startswith("/printer/objects/query"):
                    fake.status_calls += 1
                    doc = {"result": {"status": {
                        "print_stats": {"state": s["print_state"], "total_duration": s["total_duration"], "filename": s.get("filename", "test.gcode"),
                                        "info": {"current_layer": s.get("layer", 3), "total_layer": 40}},
                        "extruder": {"temperature": s["hotend"], "target": s["hotend_target"]},
                        "heater_bed": {"temperature": s["bed"], "target": s["bed_target"]},
                        "display_status": {"progress": s["progress"]},
                        "virtual_sdcard": {"file_position": s["file_position"], "file_size": s["file_size"]},
                        "toolhead": {"position": [120.5, 80.25, s["z"], 0]} if "toolhead=" not in self.path else
                                    {"position": list(s["position"]) + [0], "homed_axes": s["homed"], "axis_minimum": s["axis_min"] + [0], "axis_maximum": s["axis_max"] + [0]},
                        "webhooks": {"state": "ready"},
                        "motion_report": {"live_position": [121.0, 80.5, s["z"], 0]},
                        "configfile": {"settings": s["settings"]},
                    }}}
                    return self._send(200, json.dumps(doc).encode())
                if self.path.startswith("/printer/info"):
                    return self._send(200, json.dumps({"result": {"state": "ready"}}).encode())
                if self.path.startswith("/server/files/list"):   # the G-code files: s["gcodes"] = {path: text}
                    files = [{"path": k, "modified": 1700000000.0 + i, "size": len(v), "permissions": "rw"} for i, (k, v) in enumerate((s.get("gcodes") or {}).items())]
                    return self._send(200, json.dumps({"result": files}).encode())
                if self.path.startswith("/server/files/gcodes/"):
                    name = urllib.parse.unquote(self.path[len("/server/files/gcodes/"):])
                    if name in (s.get("gcodes") or {}):
                        return self._send(200, s["gcodes"][name].encode(), "text/plain")
                    return self._send(404, b"{}")
                if self.path == "/server/files/config/moonraker.conf" and s.get("moonraker_conf") is not None:
                    return self._send(200, s["moonraker_conf"].encode(), "text/plain")
                self._send(404, b"{}")

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n)
                fake.posts.append(self.path)
                if self.path == "/printer/gcode/script":
                    script = json.loads(body or b"{}").get("script", "")
                    fake.scripts.append(script)
                    if fake.state.get("gcode_fail"):
                        return self._send(400, json.dumps({"error": {"message": fake.state["gcode_fail"]}}).encode())
                    fake.run_gcode(script)
                    return self._send(200, b'{"result":"ok"}')
                if self.path == "/server/files/upload":   # Moonraker's file upload (multipart): keep the file's text
                    marker = b'filename="moonraker.conf"'
                    if marker in body:
                        part = body.split(marker, 1)[1].split(b"\r\n\r\n", 1)[1]
                        boundary = body.split(b"\r\n", 1)[0]
                        fake.state["moonraker_conf"] = part.split(b"\r\n" + boundary, 1)[0].decode()
                self._send(200, b'{"result":"ok"}')

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def run_gcode(self, script):
        """Moves the fake toolhead as Klipper would (G0/G1 X Y Z, G90/G91, G28); the rest is only remembered."""
        relative = False
        for line in script.splitlines():
            words = line.split(";")[0].split()
            if not words:
                continue
            cmd = words[0].upper()
            if cmd == "G90":
                relative = False
            elif cmd == "G91":
                relative = True
            elif cmd == "G28":
                self.state["homed"] = "xyz"
                self.state["position"] = [0.0, 0.0, 0.0]
            elif cmd in ("G0", "G1"):
                pos = list(self.state["position"])
                for w in words[1:]:
                    axis = "XYZ".find(w[0].upper())
                    if axis >= 0:
                        value = float(w[1:])
                        pos[axis] = pos[axis] + value if relative else value
                self.state["position"] = pos

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def close(self):
        self.server.shutdown()


def sliced_markers(minimum, maximum, dx=0.0, dy=0.0, purge=True, count=6):
    """What a slicer makes of KlippEye's markers STL, moved by (dx, dy) on the bed: a purge line and a skirt on the first
    layer, then each pyramid as shrinking squares, 0.2 mm layers, relative extrusion, retractions between them."""
    import camera_markers
    out = ["; generated by FakeSlicer", "G28", "M83", "G90", "G1 Z0.2 F600"]
    if purge:
        out += ["G1 X5 Y5", "G1 X150 Y5 E12", "G1 X150 Y5.4 E0.1"]
    out += ["G1 X30 Y40", "G1 X320 Y40 E9", "G1 X320 Y320 E9", "G1 X30 Y320 E9", "G1 X30 Y40 E9"]   # skirt
    for layer in range(1, int(round(camera_markers.PYRAMID_HEIGHT / 0.2)) + 1):
        z = round(0.2 * layer, 2)
        out.append("G1 Z%.2f" % z)
        half = camera_markers.PYRAMID_BASE / 2 * (1 - z / camera_markers.PYRAMID_HEIGHT) + 0.2
        for x, y in camera_markers.marker_positions(minimum, maximum)[:count]:
            x, y = x + dx, y + dy
            out += ["G1 E-0.8", "G0 X%.3f Y%.3f" % (x - half, y - half), "G1 E0.8"]
            for px, py in ((x + half, y - half), (x + half, y + half), (x - half, y + half), (x - half, y - half)):
                out.append("G1 X%.3f Y%.3f E%.4f" % (px, py, 0.03 * half))
    return "\n".join(out + ["M104 S0"])
