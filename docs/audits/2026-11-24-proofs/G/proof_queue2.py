import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
import sys
sys.path.insert(0, ROOT + "/notifier")
import klippeye_notifier as vn
S = {"ai": {"autoPause": True, "confirmations": 2}}
w = vn.Watcher(vn.merge(vn.DEFAULT_CONFIG, {})); t = [1000.0]
def step(state, ai, f):
    t[0] += 2; return [n.kind for n in w.step(vn.Snapshot(klippy="ready", print_state=state, ai=ai, settings=S, info={"file": f}), t[0])]
V = vn.AiVerdict
step("standby", V("none", ""), "a"); step("printing", V("none", ""), "a")
step("printing", V("k1", "PAUSE"), "a")            # print A: one PAUSE (2 needed): nothing yet
step("printing", V("k1", "PAUSE"), "b")            # A ended, queue started B before either poll; the backend missed it too, so k1 stays
step("printing", V("k2", "PAUSE"), "b")            # the FIRST verdict of print B
print("actions after B's first PAUSE verdict (2 in a row required):", [a.kind for a in w.take_actions()])
