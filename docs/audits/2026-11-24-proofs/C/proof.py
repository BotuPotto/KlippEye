import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Zone C audit proofs: fake AI answers only, no network."""
import importlib.util, json, os, sys, tempfile, time, threading
ROOT = ROOT + ""
HERE = os.path.join(ROOT, "tests", "backend")
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "stubs"))
import fakes
fake = fakes.Fake()
n = [0]
def load():
    d = tempfile.mkdtemp(prefix="zc")
    with open(os.path.join(d, "brain.json"), "w") as f:
        json.dump({"values": {"enabled": False}}, f)
    os.environ["KLIPPEYE_DATA"] = d
    n[0] += 1
    spec = importlib.util.spec_from_file_location("zc%d" % n[0], os.path.join(ROOT, "backend", "klippeye_backend.py"))
    m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m)
    m.MOONRAKER_URL = fake.url; m.CAMERA_NGINX_URL = fake.url + "/webcam"
    m.AI_CONFIG_PATH = os.path.join(d, "ai.json")
    json.dump({"version": 2, "keys": {"groq": "g" * 30, "gemini": "AIza" + "x" * 30}, "monitor": {"provider": "groq", "model": ""},
               "logs": {"provider": "groq", "model": ""}, "monitor_backups": [{"provider": "gemini", "model": ""}]}, open(m.AI_CONFIG_PATH, "w"))
    cur = os.path.join(d, "a.jpg"); open(cur, "wb").write(fakes.jpeg(fakes.frame((230, 160, 100, 100))))
    m.AI_CONFIRM_DELAY_S = 0
    m.detector.last_ai_call = 0
    m.detector._ai_picture = lambda s, _c=cur: _c
    m.detector._local_on_file = lambda p: None
    m.moonraker_status = lambda q, timeout=3: {"print_stats": {"state": "printing", "filename": "x.gcode"}}
    return m, cur

def verdict(action, conf=90):
    return json.dumps({"observation": "x", "spaghetti": {"detected": True, "confidence": conf}, "action": action, "summary": "s"})

class R:
    def __init__(self, status=200, content=None, html=None, headers=None):
        self.status_code, self.ok, self.headers = status, status < 400, headers or {}
        self._c, self._html = content, html
        self.text = html if html is not None else ""
    def json(self):
        if self._html is not None:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return {"choices": [{"message": {"content": self._c}}]}

def run(title, plan):
    m, cur = load()
    calls = []
    def post(url, headers=None, json=None, timeout=None):
        who = "gemini" if "googleapis" in url else "groq"
        k = sum(1 for c in calls if c == who); calls.append(who)
        a = plan[who][min(k, len(plan[who]) - 1)]
        if isinstance(a, Exception):
            raise a
        return a
    m.requests.post = post
    m.detector.call_ai_analysis(cur, None, None)
    h = m.read_alert_history()
    la = m.detector.last_analysis
    print("==", title)
    print("   calls:", calls)
    print("   last_analysis action:", (la or {}).get("analysis", {}).get("action") if la else None, "| alerts recorded:", len(h), [x.get("outcome") for x in h])
    return m

# 1. a 200 whose body is not JSON (HTML from a proxy / a captive portal / a custom server) on the FIRST look
run("1a first look: Groq 200 with an HTML body, Gemini would answer", {"groq": [R(html="<html>Bad gateway</html>")], "gemini": [R(content=verdict("PAUSE"))]})
# 1b the same on the SECOND look of a stop
run("1b second look: Groq PAUSE, Gemini 200 HTML on the second look", {"groq": [R(content=verdict("PAUSE"))], "gemini": [R(html="<html>x</html>")]})
# 2. 429 with a short wait, then the retry fails to connect
m = None
import requests
run("2 Groq 429 'try again in 0.1s', then the retry cannot connect; Gemini would answer",
    {"groq": [R(429, headers={"retry-after": "0"}), requests.ConnectionError("reset")], "gemini": [R(content=verdict("CONTINUE"))]})
# 3. the action word
m, _ = load()
for a in ("CONTINUE|PAUSE|CANCEL", "PAUSE (do not cancel)", "Continue, no need to pause", "pause"):
    print("== 3 normalize_action(%r) -> %s" % (a, m.normalize_action(a)))
run("3b the AI copies the template's action text, defect at 90%", {"groq": [R(content=verdict("CONTINUE|PAUSE|CANCEL"))], "gemini": [R(content=verdict("PAUSE"))]})
