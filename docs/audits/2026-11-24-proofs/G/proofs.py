import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
import os, sys, time, threading
sys.path.insert(0, ROOT + "/notifier")
import klippeye_notifier as vn

def sim(settings):
    w = vn.Watcher(vn.merge(vn.DEFAULT_CONFIG, {}))
    t = [1000.0]
    def step(state="printing", ai=None, info=None, dt=2.0):
        t[0] += dt
        snap = vn.Snapshot(klippy="ready", print_state=state, ai=ai, settings=settings, info=info or {})
        out = w.step(snap, t[0])
        return [n.kind for n in out]
    return w, step

def V(k, a): return vn.AiVerdict(key=k, action=a)

# P1: queue: print A completes and B starts between two polls (Moonraker job_queue default: no transition delay)
S = {"ai": {"autoPause": True, "confirmations": 2}, "notify": {"rules": [{"id": "p50", "kind": "progress", "value": 50}]}}
w, step = sim(S)
step("standby", V("none", ""))
step("printing", V("none", ""), {"file": "a.gcode", "progress": 0.1, "print_duration": 60})
print("A 60%:", step("printing", V("none", ""), {"file": "a.gcode", "progress": 0.6, "print_duration": 600}))
print("A last verdict PAUSE:", step("printing", V("k1", "PAUSE"), {"file": "a.gcode", "progress": 0.99, "print_duration": 1000}))
# A completes, queue starts B immediately: poll sees printing again with a new file
b = step("printing", V("none", ""), {"file": "b.gcode", "progress": 0.0, "print_duration": 1})
print("A->B in one poll: notices", b, "(expected 'complete')")
print("B 60%:", step("printing", V("none", ""), {"file": "b.gcode", "progress": 0.6, "print_duration": 600}), "(expected 'custom' for the 50% rule)")
print("B auto_done/levels carried:", w.auto_done, w.ai_levels)

# P2: AI notice switched off + auto pause on -> the automatic pause is silent
S2 = {"ai": {"autoPause": True, "confirmations": 1}, "notifications": {"ai_pause": False}}
w, step = sim(S2)
step("standby", V("none", "")); step("printing", V("none", ""))
step("printing", V("k1", "PAUSE"))
acts = w.take_actions(); print("P2 action:", [a.kind for a in acts])
w.report_action("pause", True)
out = step("paused", V("k1", "PAUSE"))
for _ in range(5): out += step("paused", V("k1", "PAUSE"))
print("P2 notices after the automatic pause (paused switch ON, AI switch off):", out)
S3 = {"ai": {"autoCancel": True, "confirmations": 1}, "notifications": {"ai_cancel": False}}
w, step = sim(S3)
step("standby", V("none", "")); step("printing", V("none", "")); step("printing", V("k1", "CANCEL"))
w.take_actions(); w.report_action("cancel", True)
out = step("cancelled", V("k1", "CANCEL")) + step("standby", V("none", ""))
print("P2b notices after the automatic cancel (cancelled switch ON):", out)

# P3: outbox head-of-line: one channel always failing (retryable) delays every later notice on the healthy channel
got = []
class FakeCh(vn.Channels):
    def __init__(self):
        self.path=None; self.stamp=None; self._said_none=False; self.config={}
        def good(n): got.append((round(time.time()-t0,2), n.kind))
        def bad(n): raise vn.SendError("dns", retry=True)
        self.senders = [("ntfy", good), ("firebase", bad)]
    def refresh(self): pass
ch = FakeCh()
ob = vn.Outbox(ch.send, give_up_seconds=3.0); ob.retry_first = 0.2
t0 = time.time(); ob.start()
ob.put(vn.Notice("ai_pause", "first")); time.sleep(0.05); ob.put(vn.Notice("error", "second"))
time.sleep(4.5); ob.stop.set()
print("P3 ntfy deliveries (s after start, kind):", got, "-> the second waits for the first to give up (3 h in the real config)")
