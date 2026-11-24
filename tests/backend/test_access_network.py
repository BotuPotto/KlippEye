"""Release 1.147.0: access and network (audit findings 8, 9, 10, 40 to 44, 86, and the logout race). The service is loaded
with its own data folder; no network, no real nginx (its answers are played by hand: the headers it adds)."""
import builtins
import importlib.util
import json
import os
import socket
import ssl
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
DATA = tempfile.mkdtemp(prefix="access_net_")
os.environ["KLIPPEYE_DATA"] = DATA
spec = importlib.util.spec_from_file_location("kb", os.path.join(ROOT, "backend", "klippeye_backend.py"))
kb = importlib.util.module_from_spec(spec)
sys.modules["kb"] = kb
spec.loader.exec_module(kb)
import access  # noqa: E402
import https_relay  # noqa: E402
import web_front  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   -> " + str(extra)[:300]) if (extra != "" and not cond) else ""), flush=True)


H = {"Host": "raspberrypi.local"}


def cookie_of(response):
    for line in response.headers.getlist("Set-Cookie"):
        if line.startswith(access.COOKIE_NAME + "="):
            return line.split("=", 1)[1].split(";", 1)[0]
    return ""


class device:
    """A browser that holds this cookie (the test client has no cookie jar of its own here: its jar would replace it)."""

    def __init__(self, token):
        self.client, self.cookie = kb.app.test_client(use_cookies=False), "%s=%s" % (access.COOKIE_NAME, token)

    def get(self, *a, **k):
        return self.client.get(*a, **dict(k, headers=dict(k.get("headers") or {}, Cookie=self.cookie)))

    def post(self, *a, **k):
        return self.client.post(*a, **dict(k, headers=dict(k.get("headers") or {}, Cookie=self.cookie)))


# --- 8 and 86: a failed read of access.json never turns the password off ---------------------------------------------------
owner = kb.app.test_client()
r = owner.post("/api/auth/password", json={"new": "segreta123"}, headers=H)
admin = cookie_of(r)
real_open = builtins.open


def failing_open(path, *a, **k):
    if str(path).endswith("access.json") and "r" in (a[0] if a else k.get("mode", "r")):
        raise PermissionError(13, "Permission denied")
    return real_open(path, *a, **k)


kb.ACCESS._stamp = None   # as if the file had changed: the next call reads it again
builtins.open = failing_open
try:
    during = kb.ACCESS.load()
finally:
    builtins.open = real_open
check("1.147.0: one failed read of access.json (not a damaged file): the password stays on, in memory and on disk",
      during["enabled"] is True and json.load(open(kb.ACCESS.path))["enabled"] is True, (during["enabled"], json.load(open(kb.ACCESS.path))["enabled"]))
fresh_store = access.Store(DATA)   # no copy in memory yet: there is nothing to keep
builtins.open = failing_open
try:
    error = None
    try:
        fresh_store.load()
    except OSError as e:
        error = e
finally:
    builtins.open = real_open
check("1.147.0: ... with no copy in memory the read fails loudly and writes nothing", error is not None and json.load(open(kb.ACCESS.path))["enabled"] is True)
kb.ACCESS._cache = None
kb.ACCESS._stamp = None
builtins.open = failing_open
try:
    code = kb.app.test_client().get("/api/version", headers=H).status_code
finally:
    builtins.open = real_open
check("1.147.0: ... and the service refuses requests meanwhile (401), it does not open", code == 401, code)
check("1.147.0: ... a request with the owner's cookie works again as soon as the file can be read", device(admin).get("/api/version", headers=H).status_code == 200)

# --- 9: nginx asks with a GET; the guard uses the method and the address of the real request ---------------------------
evil = dict(H, Origin="http://evil.example", **{"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"})
upload = {"X-Original-Method": "POST", "X-Original-URI": "/server/files/upload"}
c0 = kb.app.test_client()
kb.ACCESS.save(access.clear_password(kb.ACCESS.load()))   # no password: where another site could drive the printer
check("1.147.0: the check for a cross-site form POST upload (nginx asks with a GET, tells the real method): refused",
      c0.get("/api/auth/check", headers=dict(evil, **upload)).status_code == 403)
check("1.147.0: ... the same page's plain GET, and the dashboard's own upload, still pass",
      c0.get("/api/auth/check", headers=dict(H, Origin="http://raspberrypi.local", **upload)).status_code == 204
      and c0.get("/api/auth/check", headers=H).status_code == 204)

# --- 43: guests and the camera on port 80 ------------------------------------------------------------------------------------
c0.post("/api/auth/password", json={"new": "segreta123"}, headers=H)
c0.post("/api/auth/guest", json={"current": "segreta123", "new": "guarda1234"}, headers=H)
guest = cookie_of(kb.app.test_client().post("/api/auth/login", json={"password": "guarda1234"}, headers=H))
admin = cookie_of(kb.app.test_client().post("/api/auth/login", json={"password": "segreta123"}, headers=H))
cam = {"X-Original-Method": "GET", "X-Original-URI": "/webcam/?action=stream"}
check("1.147.0: a guest may ask for the camera through the check (their own request is a GET of /webcam/), not for an upload",
      device(guest).get("/api/auth/check", headers=dict(H, **cam)).status_code == 204
      and device(guest).get("/api/auth/check", headers=dict(H, **upload)).status_code == 403
      and device(admin).get("/api/auth/check", headers=dict(H, **upload)).status_code == 204
      and kb.app.test_client().get("/api/auth/check", headers=dict(H, **cam)).status_code == 401)
site = web_front.site_text([])
cams = web_front.camera_locations("server {\n    location /webcam/ {\n        proxy_pass http://m1/;\n    }\n    location /webcam2/ {\n        proxy_pass http://m2/;\n    }\n}\n")
site2 = web_front.site_text(cams)
blocks = [b for b in cams] + [site.split("# the camera, as the previous page had it")[1].split("# everything else")[0]]
check("1.147.0: nginx asks KlippEye before every camera block (the one made here and the copied ones), with the real method and address",
      site2.count("auth_request /_klippeye_auth;") == 5 and "location /webcam2/ {\n        auth_request /_klippeye_auth;" in site2 and "auth_request /_klippeye_auth;" in blocks[-1]
      and "proxy_set_header X-Original-Method $request_method;" in site and "proxy_set_header X-Original-URI $request_uri;" in site, site2[:900])

# --- 10: an unknown /webcamN path on port 80 does not call itself ---------------------------------------------------------
kb.ACCESS.save(access.clear_password(kb.ACCESS.load()))
sent = []


class Answer:
    status_code = 200
    headers = {}
    raw = None

    def iter_content(self, chunk_size=1):
        return iter([b"x"])

    def close(self):
        pass


kb.requests.get = lambda url, **kw: (sent.append((url, kw.get("headers") or {})), Answer())[1]
kb.app.test_client().get("/webcam9/", headers=H)
check("1.147.0: the camera request KlippEye sends on carries a hop mark", len(sent) == 1 and any(k.lower() == "x-klippeye-hop" for k in sent[0][1]), sent)
before = len(sent)
r = kb.app.test_client().get("/webcam9/", headers=dict(H, **{"X-KlippEye-Hop": "1"}))
check("1.147.0: ... and a request that comes back with the mark is answered 502 at once, not sent on again", r.status_code == 502 and len(sent) == before, (r.status_code, len(sent) - before))

# --- 41: # and ? in file names -------------------------------------------------------------------------------------------
urls = []


def capture(method, url, **kw):
    urls.append((method, url))
    raise kb.requests.RequestException("captured")


kb.requests.request = capture
c = kb.app.test_client()
c.get("/server/files/gcodes/part%20%232.gcode", headers=H)
c.delete("/server/files/gcodes/part%3Fv%3D2.gcode", headers=H)
c.get("/server/files/gcodes/plain.gcode?x=1", headers=H)
check("1.147.0: a # or ? in a file name reaches Moonraker quoted (the delete hits that file, not another)",
      [u.rsplit("/", 1)[1] for _, u in urls] == ["part%20%232.gcode", "part%3Fv%3D2.gcode", "plain.gcode?x=1"], urls)

# --- 42: passwords sent at the same moment ---------------------------------------------------------------------------------
kb.ACCESS.save(access.set_password(kb.ACCESS.load(), "segreta123"))
kb.ACCESS_THROTTLE.failures["127.0.0.1"] = (6, 0)   # the wait has just run out
codes = []


def one(i):
    codes.append(kb.app.test_client().post("/api/auth/login", json={"password": "burst%d" % i}, headers=H).status_code)


threads = [threading.Thread(target=one, args=(i,)) for i in range(12)]
[t.start() for t in threads]
[t.join() for t in threads]
check("1.147.0: 12 wrong passwords at the same moment after the wait: one is checked, the others told to wait", codes.count(401) == 1 and codes.count(429) == 11, codes)

# --- 44: a slicer's connection test with the password on ---------------------------------------------------------------------
slicer = dict(H, **{"X-Api-Key": "anything", "User-Agent": "OrcaSlicer/2.1"})
check("1.147.0: a slicer's connection test with the password on fails (401) like its upload would",
      kb.app.test_client().get("/api/version", headers=slicer).status_code == 401 and kb.app.test_client().post("/api/files/local", headers=slicer, data=b"G28").status_code == 401)

# --- 40: the HTTPS relay: one request per connection ------------------------------------------------------------------------
check("1.147.0: the relay asks the service to close after every answer, whatever the client's Upgrade header says",
      b"Connection: close" in https_relay.forward_head(b"POST /api/auth/login HTTP/1.1\r\nHost: x\r\nUpgrade: nothing\r\nConnection: keep-alive", "1.2.3.4")
      and b"Connection: close" in https_relay.forward_head(b"GET /websocket HTTP/1.1\r\nUpgrade: websocket\r\nConnection: Upgrade", "1.2.3.4"))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


received = []
bport, rport = free_port(), free_port()
srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", bport))
srv.listen(5)


def backend():
    conn, _ = srv.accept()
    buf = b""
    while True:
        data = conn.recv(65536)
        if not data:
            return
        buf += data
        while b"\r\n\r\n" in buf:
            head, buf = buf.split(b"\r\n\r\n", 1)
            received.append(head.decode())
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
            if b"connection: close" in head.lower():   # what a real HTTP server does
                conn.close()
                return


threading.Thread(target=backend, daemon=True).start()
cert, key = https_relay.ensure_certificate(tempfile.mkdtemp(), names=["localhost"], addresses=[])
relay = https_relay.HttpsRelay(rport, bport, cert, key, log=lambda *a: None)
relay.start()
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
tls = ctx.wrap_socket(socket.create_connection(("127.0.0.1", rport)), server_hostname="localhost")
tls.settimeout(3)
tls.sendall(b"POST /api/auth/login HTTP/1.1\r\nHost: x\r\nUpgrade: nothing\r\nConnection: keep-alive\r\nContent-Length: 0\r\n\r\n")
time.sleep(0.3)
tls.recv(1000)
try:
    tls.sendall(b"POST /api/auth/login HTTP/1.1\r\nHost: x\r\nX-Forwarded-For: 10.9.9.9\r\nContent-Length: 0\r\n\r\n")
except OSError:
    pass
time.sleep(0.3)
spoofed = [h for h in received if "10.9.9.9" in h]
check("1.147.0: a second request with its own X-Forwarded-For never reaches the service", len(received) == 1 and not spoofed, received)
relay.stop()

# --- the dashboard that asks to log out every other device is never sent to /login by its own requests in flight ----------------
kb.ACCESS.save(access.set_password(kb.ACCESS.load(), "segreta123"))
settings = kb.ACCESS.load()
mine = access.make_token(settings, now=time.time() - 50)       # this device's cookie (the one in flight)
other = access.make_token(settings, now=time.time() - 100)     # another device
same_second = access.make_token(settings, now=time.time() - 50)   # a device that logged in in the same second as this one
before = device(mine).get("/api/version", headers=H).status_code
r = device(mine).post("/api/auth/logout_all", headers=H)
new = cookie_of(r)
check("1.147.0: «log out the others»: the asking device gets a new cookie; the others are out at once",
      before == 200 and r.status_code == 200 and new and device(other).get("/api/version", headers=H).status_code == 401
      and device(same_second).get("/api/version", headers=H).status_code == 401
      and device(new).get("/api/version", headers=H).status_code == 200)
check("1.147.0: ... a request of the asking device that was already on its way with the old cookie still works (no sudden /login)",
      device(mine).get("/api/version", headers=H).status_code == 200)
kb.LOGOUT_GRACE_S = 0
mine2 = access.make_token(kb.ACCESS.load(), now=time.time() - 40)
device(mine2).post("/api/auth/logout_all", headers=H)
check("1.147.0: ... only for a few seconds", device(mine2).get("/api/version", headers=H).status_code == 401)

print("\n%d check(s) failed" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
