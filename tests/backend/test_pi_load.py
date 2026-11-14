"""Release 1.129: KlippEye leaves room to Klipper on the Raspberry (OpenCV on at most 2 cores, always one free; the backend
at a lower priority) and the benchmark times the local model and the networks that could replace it."""
import os
import subprocess
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(ROOT, "backend"), os.path.join(ROOT, "scripts")]
import monitor_core  # noqa: E402
import benchmark  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   -> " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


saved = os.environ.pop("KLIPPEYE_CV_THREADS", None)
check("OpenCV's cores: 1 on a single core, 1 on two (one left free), 2 on four or more",
      [monitor_core.opencv_threads(c) for c in (1, 2, 4, 8)] == [1, 1, 2, 2], [monitor_core.opencv_threads(c) for c in (1, 2, 4, 8)])
os.environ["KLIPPEYE_CV_THREADS"] = "3"
check("... KLIPPEYE_CV_THREADS chooses another number", monitor_core.opencv_threads(4) == 3)
os.environ["KLIPPEYE_CV_THREADS"] = "99"
check("... a number out of range is ignored", monitor_core.opencv_threads(4) == 2)
os.environ.pop("KLIPPEYE_CV_THREADS")
if saved is not None:
    os.environ["KLIPPEYE_CV_THREADS"] = saved
check("... and set when OpenCV is loaded", not monitor_core.HAS_CV2 or monitor_core.cv2.getNumThreads() == monitor_core.opencv_threads())

unit = open(os.path.join(ROOT, "systemd", "klippeye.service")).read()
check("the service runs at a lower priority than Klipper (Nice=10)", "\nNice=10\n" in unit)
code = ("import os, sys; sys.path.insert(0, %r); sys.argv = ['x'];\n"
        "src = open(%r).read(); start = src.index('BACKEND_NICE = '); end = src.index('if __name__ == \"__main__\":')\n"
        "ns = {'os': os}; exec(src[start:end], ns); print(ns['lower_priority'](), ns['lower_priority']())") % (
    os.path.join(ROOT, "backend"), os.path.join(ROOT, "backend", "klippeye_backend.py"))
out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
check("a backend installed before (no Nice in its service file) lowers its own priority, once", out.stdout.split() == ["10", "10"], out.stdout + out.stderr)

folder = tempfile.mkdtemp()
shutil.copy(os.path.join(ROOT, "models", "base", "model.onnx"), os.path.join(folder, "copy.onnx"))
open(os.path.join(folder, "broken.onnx"), "w").write("not a network")
cost = benchmark.model_cost(ROOT, folder, rounds=2)
rows = {r["model"]: r for r in cost.get("models", [])}
check("benchmark: the model in use and each .onnx of the folder, timed with 1 core and with the cores allowed",
      "in use (MobileNetV3-Small)" in rows and "copy" in rows and set(rows["copy"]["ms"]) == set(cost["threads"]) and 1 in cost["threads"], cost)
check("... a check is up to 3 views; its share of one core at the monitor's pace",
      abs(rows["copy"]["check_ms"] - rows["copy"]["ms"][cost["allowed"]] * 3) < 0.2 and rows["copy"]["core_percent"] > 0, rows.get("copy"))
check("... a file OpenCV cannot run is said, not a crash", "error" in rows.get("broken", {}), rows.get("broken"))
text = "\n".join(benchmark.model_report(cost))
check("... the report: one line per network", "copy" in text and "OpenCV cannot run it" in text and "per check" in text, text)
heavy = {"system": {"cpu_percent": 10, "memory_mb": 4000, "memory_available_mb": 3000, "temperature_max": 50, "throttled": None},
         "groups": {"KlippEye": {"processes": 1}}, "monitor": {}, "local": {"interval_s": 3.0, "models": [{"model": "big", "check_ms": 1200.0, "core_percent": 40.0}]}}
check("... a network too heavy for this Raspberry is said in the verdict", any("big" in n for n in benchmark.verdict(heavy)), benchmark.verdict(heavy))
shutil.rmtree(folder)

print("\n%d FAIL" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
