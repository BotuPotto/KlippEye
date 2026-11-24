import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
import sys
sys.path.insert(0, ROOT + "/notifier")
import klippeye_notifier as vn
S = {"ai": {"autoPause": True, "confirmations": 1}}
w = vn.Watcher(vn.merge(vn.DEFAULT_CONFIG, {})); t = [1000.0]; log = []
def step(state, ai, dt=2):
    t[0] += dt; out = [(n.kind, n.text) for n in w.step(vn.Snapshot(klippy="ready", print_state=state, ai=ai, settings=S), t[0])]; log.extend(out); return out
V = vn.AiVerdict
step("standby", V("none", "")); step("printing", V("none", ""))
step("printing", V("k1", "PAUSE")); w.take_actions(); w.report_action("pause", False)   # Moonraker busy: the pause failed
print("after the failed pause:", step("printing", V("k1", "PAUSE")))
step("printing", V("k2", "PAUSE"), dt=100); print("second try:", [a.kind for a in w.take_actions()]); w.report_action("pause", True)
out = step("paused", V("k2", "PAUSE"))
for _ in range(10): out += step("paused", V("k2", "PAUSE"))
print("after the successful automatic pause:", out)
