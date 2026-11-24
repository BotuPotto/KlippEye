"""Wrong passwords sent at the same time all get checked: the wait is set only after they fail."""
import importlib.util, os, sys, tempfile, threading
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tests", "backend", "stubs"))
os.environ["KLIPPEYE_DATA"] = tempfile.mkdtemp(prefix="zoneE_t_")
spec = importlib.util.spec_from_file_location("kb", os.path.join(ROOT, "backend", "klippeye_backend.py"))
kb = importlib.util.module_from_spec(spec); sys.modules["kb"] = kb; spec.loader.exec_module(kb)
H = {"Host": "raspberrypi.local"}
kb.app.test_client().post("/api/auth/password", json={"new": "segreta123"}, headers=H)
for i in range(6):   # already past the 5 free tries: the next one must wait
    kb.app.test_client().post("/api/auth/login", json={"password": "wrong%d" % i}, headers=H)
kb.ACCESS_THROTTLE.failures["127.0.0.1"] = (6, 0)   # the wait has just run out
codes = []
def one(i):
    codes.append(kb.app.test_client().post("/api/auth/login", json={"password": "burst%d" % i}, headers=H).status_code)
threads = [threading.Thread(target=one, args=(i,)) for i in range(12)]
[t.start() for t in threads]; [t.join() for t in threads]
print("12 wrong passwords at once after the wait ran out: checked (401) %d, told to wait (429) %d" % (codes.count(401), codes.count(429)))
