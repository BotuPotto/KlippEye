import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
# Zone A proof 1: calibrated camera (bed view) + no usable local model -> local_judge raises, the motion trigger is lost.
import importlib.util, os, sys, tempfile
ROOT = ROOT + ""
sys.path.insert(0, ROOT + "/tests/backend"); sys.path.insert(0, ROOT + "/tests/backend/stubs")
import fakes
fake = fakes.Fake()
d = tempfile.mkdtemp(); os.environ["KLIPPEYE_DATA"] = d
spec = importlib.util.spec_from_file_location("kb", ROOT + "/backend/klippeye_backend.py")
kb = importlib.util.module_from_spec(spec); sys.modules["kb"] = kb; spec.loader.exec_module(kb)
kb.detector.stop()
kb.local_ai.model = None                      # no model (or one OpenCV cannot run)
det = kb.detector
det._bed_box = lambda z=None: (0.1, 0.3, 0.8, 0.6)   # as with a saved, usable calibration
det._online_ai_usable = lambda: True
det.ai_online = True
try:
    print("ask =", det._local_look(fakes.frame(), 1000.0, True))
except Exception as e:
    print("RAISES:", type(e).__name__, e)
