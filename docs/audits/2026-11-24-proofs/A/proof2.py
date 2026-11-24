import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
# Zone A proof 2: the camera stops answering in the middle of a print -> the status keeps saying it is watching.
import importlib.util, os, sys, tempfile, time
ROOT = ROOT + ""
sys.path.insert(0, ROOT + "/tests/backend"); sys.path.insert(0, ROOT + "/tests/backend/stubs")
import fakes
fake = fakes.Fake()
d = tempfile.mkdtemp(); os.environ["KLIPPEYE_DATA"] = d
spec = importlib.util.spec_from_file_location("kb", ROOT + "/backend/klippeye_backend.py")
kb = importlib.util.module_from_spec(spec); sys.modules["kb"] = kb; spec.loader.exec_module(kb)
kb.detector.stop()
kb.MOONRAKER_URL = fake.url if hasattr(fake, "url") else "http://127.0.0.1:%d" % fake.port
kb.CAMERA_NGINX_URL = kb.MOONRAKER_URL + "/webcam"
kb._SNAPSHOT["at"] = 0
det = kb.detector
det.check_interval = 1
det.start()
time.sleep(12)
print("camera working: status=%r frames_checked=%d" % (det.stats["status"], det.stats["frames_checked"]))
fake.state["frames"] = [b"not a picture"]       # the camera dies (or answers 200 with an error page)
time.sleep(20)
print("camera dead 20 s: status=%r frames_checked=%d" % (det.stats["status"], det.stats["frames_checked"]))
det.stop()
