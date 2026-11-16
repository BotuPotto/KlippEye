"""
The AI monitor's local model (roadmap «local model», 1.105): a small image classifier that runs on the Raspberry itself,
with OpenCV's own DNN module (no new package): it says how likely a picture shows a failed print (spaghetti, a part off
the bed...), and gives the picture's «embedding» (the numbers the model describes it with), which the personal layer of
each printer will learn from.

The model is made on a computer with ml/train.py (see ml/README.md) and is a folder:
    model.onnx   the network: input 1x3xSxS (RGB, normalised), outputs a logit (1x1) and the embedding (1xE)
    model.json   {"format": 1, "version", "size": S, "mean": [3], "std": [3], "threshold", "embedding": E, ...}

Only the standard library plus the OpenCV and numpy modules the caller passes (the backend's own).
1.133: when onnxruntime is installed it runs the network instead of OpenCV (twice as fast on a PC, the same results);
KLIPPEYE_RUNTIME=opencv keeps OpenCV. It is optional: without it nothing changes.
"""

import json
import math
import os
import threading

FORMAT = 1


class ModelError(Exception):
    pass


def _onnxruntime(path, threads):
    """An onnxruntime session for the model, or None (not installed, switched off, or it cannot run the file)."""
    if os.environ.get("KLIPPEYE_RUNTIME", "").strip().lower() == "opencv":
        return None
    try:
        import onnxruntime
    except ImportError:
        return None
    try:
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads, options.inter_op_num_threads = max(1, threads), 1   # as many cores as OpenCV may use
        return onnxruntime.InferenceSession(path, options, providers=["CPUExecutionProvider"])
    except Exception as error:  # noqa: BLE001 - onnxruntime's own errors: OpenCV runs it
        print("[LOCAL] onnxruntime cannot run the model, OpenCV does: %s" % str(error).splitlines()[0][:200])
        return None


def _sigmoid(x):
    x = max(-60.0, min(60.0, float(x)))
    return 1.0 / (1.0 + math.exp(-x))


class LocalModel:
    def __init__(self, folder, cv2, np):
        self._lock = threading.Lock()
        self.folder, self.cv2, self.np = folder, cv2, np
        try:
            with open(os.path.join(folder, "model.json"), encoding="utf-8") as handle:
                self.info = json.load(handle)
        except (OSError, ValueError) as error:
            raise ModelError("model.json not readable: %s" % error) from error
        if not isinstance(self.info, dict) or self.info.get("format") != FORMAT:
            raise ModelError("model.json of an unknown format")
        self.size = int(self.info.get("size") or 224)
        self.mean = np.array(self.info.get("mean") or [0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 1, 3)
        self.std = np.array(self.info.get("std") or [0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 1, 3)
        self.threshold = float(self.info.get("threshold") or 0.5)
        self.version = str(self.info.get("version") or "")
        try:
            self.net = cv2.dnn.readNetFromONNX(os.path.join(folder, "model.onnx"))
        except Exception as error:  # noqa: BLE001 - OpenCV's own errors
            raise ModelError("model.onnx not readable: %s" % error) from error
        self.outputs = list(self.net.getUnconnectedOutLayersNames())
        self.session = _onnxruntime(os.path.join(folder, "model.onnx"), cv2.getNumThreads())
        self.runtime = "onnxruntime" if self.session is not None else "opencv"

    def blob(self, frame_bgr):
        """A BGR picture (any size) -> the network's input."""
        cv2, np = self.cv2, self.np
        small = cv2.resize(frame_bgr, (self.size, self.size), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        return np.ascontiguousarray(((rgb - self.mean) / self.std).transpose(2, 0, 1)[None], dtype=np.float32)

    def predict(self, frame_bgr):
        """-> (score 0..1: how likely the picture shows a failure, embedding as a 1-D float32 array, or None).
        One picture at a time (the monitor and the personal layer's training share the network)."""
        blob = self.blob(frame_bgr)
        with self._lock:
            if self.session is not None:
                outs = self.session.run(None, {self.session.get_inputs()[0].name: blob})
            else:
                self.net.setInput(blob)
                outs = self.net.forward(self.outputs)
        logit, embedding = None, None
        for out in outs:
            flat = self.np.asarray(out, dtype=self.np.float32).reshape(-1)
            if flat.size == 1:
                logit = float(flat[0])
            else:
                embedding = flat
        if logit is None:
            raise ModelError("the model gave no score")
        return _sigmoid(logit), embedding


def load(folder, cv2, np):
    """The model in `folder`, or None when there is none (no model.onnx) — the monitor then works without it."""
    if not (folder and os.path.isfile(os.path.join(folder, "model.onnx")) and os.path.isfile(os.path.join(folder, "model.json"))):
        return None
    return LocalModel(folder, cv2, np)
