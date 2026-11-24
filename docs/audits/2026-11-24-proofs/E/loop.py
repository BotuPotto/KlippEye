"""Port-80 mode: CAMERA_NGINX_URL is http://127.0.0.1/webcam, and nginx sends any path it has no location for
(/webcam2/, /webcam9/...) to `location /` = KlippEye. Emulated here by pointing CAMERA_NGINX_URL at KlippEye itself
(threaded werkzeug server standing in for nginx + waitress). One GET /webcam9/ then calls itself again and again."""
import importlib.util, os, sys, tempfile, threading, time, socket
import requests
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tests", "backend", "stubs"))
os.environ["KLIPPEYE_DATA"] = tempfile.mkdtemp(prefix="zoneE_loop_")
spec = importlib.util.spec_from_file_location("kb", os.path.join(ROOT, "backend", "klippeye_backend.py"))
kb = importlib.util.module_from_spec(spec); sys.modules["kb"] = kb; spec.loader.exec_module(kb)
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
kb.CAMERA_NGINX_URL = "http://127.0.0.1:%d/webcam" % port
hits = []
@kb.app.before_request
def count():
    from flask import request
    if request.path.startswith("/webcam"):
        hits.append(time.time())
from werkzeug.serving import make_server
srv = make_server("127.0.0.1", port, kb.app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
try:
    requests.get("http://127.0.0.1:%d/webcam9/" % port, timeout=3)
except requests.RequestException as e:
    print("first request:", type(e).__name__)
time.sleep(1)
print("requests to /webcam9 inside KlippEye after one request from outside: %d" % len(hits))
os._exit(0)
