"""Zone E probes. python3 .superpowers/audit/zone-E/probe.py  (temp data folder, fake Moonraker on a free port)"""
import importlib.util, os, sys, tempfile, threading, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tests", "backend", "stubs"))
seen = []
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _any(self):
        seen.append((self.command, self.path)); body = b'{"result":"ok"}'
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    do_GET = do_POST = do_DELETE = _any
srv = ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["KLIPPEYE_DATA"] = tempfile.mkdtemp(prefix="zoneE_")
spec = importlib.util.spec_from_file_location("kb", os.path.join(ROOT, "backend", "klippeye_backend.py"))
kb = importlib.util.module_from_spec(spec); sys.modules["kb"] = kb; spec.loader.exec_module(kb)
kb.MOONRAKER_URL = "http://127.0.0.1:%d" % srv.server_port
kb.CAMERA_NGINX_URL = kb.MOONRAKER_URL + "/webcam"
c = kb.app.test_client()
H_ = {"Host": "raspberrypi.local"}

print("== 1. nginx auth subrequest (always GET) for a cross-site form POST upload, no password")
evil = dict(H_, Origin="http://evil.example", **{"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"})
print("  the same POST sent to 8085 directly:", c.post("/server/files/upload", headers=evil).status_code, "(refused)")
print("  GET /api/auth/check with the same headers (what nginx asks):", c.get("/api/auth/check", headers=evil).status_code, "(204 = nginx lets the upload reach Moonraker)")
print("  ... a browser without Sec-Fetch headers:", c.get("/api/auth/check", headers=dict(H_, Origin="http://evil.example")).status_code)

print("== 2. '#' and '?' in a file name through the Moonraker proxy")
seen.clear()
c.get("/server/files/gcodes/part%20%232.gcode", headers=H_)
c.delete("/server/files/gcodes/part%3Fv%3D2.gcode", headers=H_)
print("  Moonraker received:", seen)

print("== 3. guest_may")
import access
for m, p, a in [("GET", "/server/files/directory", {"path": "gcodes/../config"}), ("GET", "/server/files/list", {"root": "gcodes/../config"}),
                ("POST", "/webcam/api/config", None), ("POST", "/webcam/api/restart", None), ("POST", "/webcamfoo", None)]:
    print("  ", m, p, a, "->", access.guest_may(m, p, a))

print("== 4. port-80 site: which locations carry auth_request")
sys.path.insert(0, os.path.join(ROOT, "scripts")); import web_front
text = web_front.site_text(["    location /webcam/ {\n        proxy_pass http://127.0.0.1:8080/;\n    }"])
import re
for block in re.findall(r"location ([^{]+)\{(.*?)\n    \}", text, re.S):
    print("   location %-24s auth_request: %s" % (block[0].strip(), "auth_request" in block[1]))

print("== 5. slicer with the password on: the connection test passes, the upload is refused")
c.post("/api/auth/password", json={"new": "segreta123"}, headers=H_)
s = kb.app.test_client()
slicer = dict(H_, **{"X-Api-Key": "anything", "User-Agent": "Slicer/2.1"})
print("  GET /api/version:", s.get("/api/version", headers=slicer).status_code, " POST /api/files/local:", s.post("/api/files/local", headers=slicer, data=b"G28").status_code)

print("== 6. access.json that exists but cannot be opened (an OSError, not a damaged file)")
import builtins
real_open = builtins.open
def failing_open(path, *a, **k):
    if str(path).endswith("access.json") and "r" in (a[0] if a else k.get("mode", "r")):
        raise PermissionError(13, "Permission denied")
    return real_open(path, *a, **k)
before = kb.ACCESS.load()["enabled"]
kb.ACCESS._cache = None
builtins.open = failing_open
try:
    kb.ACCESS.load()
finally:
    builtins.open = real_open
kb.ACCESS._cache = None
print("  password on before:", before, " after one failed read, on disk:", json.load(real_open(kb.ACCESS.path))["enabled"])

print("== 7. guest may read the whole printer.cfg through Klipper's configfile object")
print("  guest_may GET /printer/objects/query?configfile ->", access.guest_may("GET", "/printer/objects/query", {"configfile": ""}))
