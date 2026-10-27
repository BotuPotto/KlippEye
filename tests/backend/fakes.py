"""A fake Moonraker + fake camera on one local port, controlled by the test (state dict)."""
import json, threading, time
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
        }
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
                if self.path.startswith("/webcam/snapshot"):
                    with fake.lock:
                        i = min(fake.snapshots, len(s["frames"]) - 1)
                        fake.snapshots += 1
                    return self._send(200, s["frames"][i], "image/jpeg")
                if self.path.startswith("/printer/objects/query"):
                    fake.status_calls += 1
                    doc = {"result": {"status": {
                        "print_stats": {"state": s["print_state"], "total_duration": s["total_duration"], "filename": "test.gcode"},
                        "extruder": {"temperature": s["hotend"], "target": s["hotend_target"]},
                        "heater_bed": {"temperature": s["bed"], "target": s["bed_target"]},
                        "display_status": {"progress": s["progress"]},
                        "virtual_sdcard": {"file_position": s["file_position"], "file_size": s["file_size"]},
                        "toolhead": {"position": [0, 0, s["z"], 0]},
                    }}}
                    return self._send(200, json.dumps(doc).encode())
                if self.path.startswith("/printer/info"):
                    return self._send(200, json.dumps({"result": {"state": "ready"}}).encode())
                if self.path == "/server/files/config/moonraker.conf" and s.get("moonraker_conf") is not None:
                    return self._send(200, s["moonraker_conf"].encode(), "text/plain")
                self._send(404, b"{}")

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n)
                fake.posts.append(self.path)
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

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def close(self):
        self.server.shutdown()
