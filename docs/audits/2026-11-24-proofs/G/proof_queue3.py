import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
import sys
sys.path.insert(0, ROOT + "/notifier")
import klippeye_notifier as vn
S = {"ai": {"autoPause": True, "confirmations": 1}}
w = vn.Watcher(vn.merge(vn.DEFAULT_CONFIG, {})); t = [1000.0]
def step(state, ai, f, dt=2):
    t[0] += dt; return [n.kind for n in w.step(vn.Snapshot(klippy="ready", print_state=state, ai=ai, settings=S, info={"file": f}), t[0])]
V = vn.AiVerdict
step("standby", V("none", ""), "a"); step("printing", V("none", ""), "a")
step("printing", V("k1", "PAUSE"), "a"); w.take_actions(); w.report_action("pause", True)
step("paused", V("k1", "PAUSE"), "a"); step("printing", V("k1", "PAUSE"), "a", dt=60)   # false alarm, the person resumes A
step("printing", V("none", ""), "b")   # A completes, the queue starts B between two polls
step("printing", V("k2", "PAUSE"), "b", dt=200)  # a real failure in B
print("B: actions on its first PAUSE verdict:", [a.kind for a in w.take_actions()], "(expected ['pause'])")
