"""The whole chain of the local model on synthetic pictures, with PyTorch (the CI's «Local model» job): the list of
pictures, a short training from nothing, the export checked against OpenCV, the measurement on a KlippEye data folder.
It does not say the model is good (a few minutes on drawings), only that every step works, fits the next and learns."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import datasets  # noqa: E402
import evaluate  # noqa: E402
import local_model  # noqa: E402
import synthetic  # noqa: E402
import train  # noqa: E402

root = tempfile.mkdtemp(prefix="ke-ml-smoke-")
paths = synthetic.make(root, n=80)
work, out = os.path.join(root, "work"), os.path.join(root, "model")
assert datasets.main(["--yolo", paths["yolo"], "--folders", paths["sorted"], "--klippeye", paths["klippeye"], "--out", work,
                      "--hard-cases", "0.3", "--mine", os.path.join(HERE, "..", "..", "models", "base")]) == 0
code = train.main(["--manifest", os.path.join(work, "manifest.csv"), "--out", out, "--epochs", "30", "--size", "96", "--batch", "16",
                   "--workers", "0", "--no-pretrained", "--lr", "3e-3"])
assert code == 0, "train.py: %s (2: OpenCV answers differently from PyTorch)" % code
info = json.load(open(os.path.join(out, "model.json")))
assert info["format"] == 1 and info["size"] == 96 and 0.3 <= info["threshold"] <= 0.99 and info["embedding"] == 1024, info
# 1.130: the scores made honest (the temperature inside the model), the threshold within the false alarms wanted
cal = info["measured"]["calibration_error"]
assert info["temperature"] > 0 and cal["after"] <= cal["before"] + 0.5, cal
assert "false_alarm_rate" in info["measured"], info["measured"]
assert abs(train.fit_temperature([4.0, -4.0, 4.0, -4.0], [1, 0, 0, 1]) - 8.0) < 0.5   # always half wrong: as unsure as can be
print("calibration:", cal, "threshold", info["threshold"])
model = local_model.load(out, cv2, np)
score, embedding = model.predict(cv2.imread(os.path.join(paths["klippeye"], "recordings", "20261101-100000-good", "000001.jpg")))
assert 0.0 <= score <= 1.0 and embedding.shape == (1024,), (score, embedding.shape)
report = os.path.join(root, "report.json")
assert evaluate.main(["--model", out, "--data", paths["klippeye"], "--json", report]) == 0
data = json.load(open(report))
assert len(data["prints"]) == 3 and len(data["table"]) >= 6, data["table"]
bad = [p for p in data["prints"] if p["id"].endswith("bad")][0]
good = [p for p in data["prints"] if p["id"].endswith("good")][0]
late = np.mean([s for t, s in bad["scored"][-20:]])
fine = np.mean([s for t, s in good["scored"]])
print("mean score: failed part %.3f, fine print %.3f" % (late, fine))
assert late > fine + 0.1, "even on drawings the model should tell a tangle from a tidy bed"
print("OK: the local model's chain works")
