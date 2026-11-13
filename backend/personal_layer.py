"""
The local model's personal layer (1.107): what one printer learns from its own labelled pictures, on top of the model
that is the same for everyone. Optional (the setting "personal_learning", off by default).

The base model describes every picture with an embedding (1024 numbers, backend/local_model.py); the personal layer is a
small logistic regression on those numbers, trained in a few seconds on this printer's examples:
  - the small pictures of the prints answered in «How did the print go?» (print_review.py): a print that went fine gives
    fine pictures; a failed one with its moment gives fine pictures before it and failed ones from a minute after it;
  - the labelled recordings (recorder.py), one picture in OK_EVERY of a fine print;
  - the examples imported from another printer (export / import below).
Its score is blended with the base model's, more as the examples grow (BLEND_MAX at most): the base model keeps its say.

On disk, in <data>/personal/:
    cache.npz       the embeddings already computed {key -> vector} for one base model version (computed again when the
                    base model changes: only from the pictures, which are kept)
    layer.json      the trained layer: weights, bias, the model version, how many examples, how it was measured, when
    imported/<origin>/<n>.jpg + labels.json   the examples brought from another printer

Only the standard library and numpy (and the OpenCV module the caller passes, to read pictures).
"""
import glob
import io
import json
import os
import re
import shutil
import threading
import time
import zipfile

import labelled_prints

FAILED_AFTER = labelled_prints.FAILED_AFTER   # seconds after the person's moment from which the pictures show the failure
OK_EVERY = 4            # of a fine recording, one picture in OK_EVERY
MIN_FAILED, MIN_FINE = 5, 20   # fewer examples than these: no layer (the base model alone)
BLEND_MIN, BLEND_MAX = 0.25, 0.6   # the personal layer's weight in the final score: from MIN_FAILED failed examples ...
BLEND_FULL_AT = 60                 # ... up to this many, where it is the most
MAX_EXAMPLES = 3000     # at most this many in one training (every failed one, the fine ones evenly picked): the first
                        # training of a Raspberry 4 with many recordings takes a minute or two, the next ones a few seconds
EXPORT_MAX = 600        # pictures in an export (the failed ones first, then the fine ones)
EXPORT_WIDTH = 320      # their width (the recordings' pictures are made smaller)
ORIGIN_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _sigmoid(np, x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -60, 60)))


def examples_of(data_dir):
    """-> [(key, picture path, label 1 failed / 0 fine)] from the reviews, the recordings and the imported examples.
    Of a recording (a picture every few seconds, much alike) one fine picture in OK_EVERY and one failed in two."""
    out = []
    for one in labelled_prints.prints_of(data_dir):
        recording = one["kind"] == "recording"
        for index, (number, t, path) in enumerate(one["pictures"]):
            label = labelled_prints.label_at(one, t)
            if label is None or (recording and index % (2 if label else OK_EVERY)):
                continue
            out.append(("%s/%s/%d" % ("rec" if recording else "rev", one["id"], number), path, label))
    for labels_file in glob.glob(os.path.join(data_dir, "personal", "imported", "*", "labels.json")):
        folder = os.path.dirname(labels_file)
        try:
            labels = _read_json(labels_file)
        except (OSError, ValueError):
            continue
        for name, label in (labels.get("pictures") or {}).items():
            path = os.path.join(folder, os.path.basename(name))
            if label in (0, 1) and os.path.isfile(path):
                out.append(("imp/%s/%s" % (os.path.basename(folder), os.path.basename(name)), path, label))
    return out


def weight_for(failed):
    """The personal layer's weight in the final score for this many failed examples (0 below MIN_FAILED)."""
    if failed < MIN_FAILED:
        return 0.0
    share = min(1.0, (failed - MIN_FAILED) / float(BLEND_FULL_AT - MIN_FAILED))
    return round(BLEND_MIN + (BLEND_MAX - BLEND_MIN) * share, 3)


def fit(np, x, y, l2=1e-3, steps=400, lr=0.5):
    """Logistic regression with the two kinds weighed equally (full-batch gradient descent: a few thousand examples
    of 1024 numbers take a second). -> (weights, bias)."""
    n, d = x.shape
    w, b = np.zeros(d, dtype=np.float64), 0.0
    pos = max(1, int(y.sum()))
    neg = max(1, n - pos)
    weight = np.where(y == 1, n / (2.0 * pos), n / (2.0 * neg))
    for _ in range(steps):
        p = _sigmoid(np, x @ w + b)
        g = (p - y) * weight
        w -= lr * (x.T @ g / n + l2 * w)
        b -= lr * float(g.mean())
    return w, b


class PersonalLayer:
    def __init__(self, data_dir, np, cv2=None):
        self.data_dir, self.np, self.cv2 = data_dir, np, cv2
        self.folder = os.path.join(data_dir, "personal")
        self.lock = threading.Lock()
        self.layer = None          # {"w": array, "b", "version", ...}
        self.enabled = False
        self.training = False
        self.last_error = ""
        self._load()

    # ------------------------------------------------------------------ the layer on disk
    def _load(self):
        try:
            data = _read_json(os.path.join(self.folder, "layer.json"))
            data["w"] = self.np.array(data["w"], dtype=self.np.float64)
            self.layer = data
        except (OSError, ValueError, KeyError, TypeError):
            self.layer = None

    def info(self):
        layer = self.layer
        base = {"enabled": self.enabled, "training": self.training, "error": self.last_error, "imported": self.imported(),
                "needed": {"failed": MIN_FAILED, "fine": MIN_FINE}}
        examples = examples_of(self.data_dir)
        base["have"] = {"failed": sum(1 for e in examples if e[2] == 1), "fine": sum(1 for e in examples if e[2] == 0)}
        if not layer:
            return dict(base, trained=False)
        return dict(base, trained=True, **{k: layer.get(k) for k in ("version", "examples", "failed", "fine", "trained_at", "measured", "weight")})

    def configure(self, enabled):
        self.enabled = bool(enabled)

    # ------------------------------------------------------------------ the score
    def blend(self, base_score, embedding, model_version):
        """The final score: the base model's, mixed with the personal layer's when there is one for this base model."""
        layer = self.layer
        if not (self.enabled and layer and embedding is not None and layer.get("version") == model_version):
            return base_score
        try:
            x = self.np.asarray(embedding, dtype=self.np.float64)
            x = x / (self.np.linalg.norm(x) + 1e-9)
            personal = float(_sigmoid(self.np, float(x @ layer["w"] + layer["b"])))
        except Exception:  # noqa: BLE001 - a layer of another size: the base model alone
            return base_score
        weight = float(layer.get("weight") or 0)
        return (1 - weight) * base_score + weight * personal

    # ------------------------------------------------------------------ training
    def _embeddings(self, model, examples):
        """The embeddings of the examples, from the cache when the base model is the same; the others computed now."""
        np = self.np
        path = os.path.join(self.folder, "cache.npz")
        cache = {}
        try:
            stored = np.load(path, allow_pickle=False)
            if str(stored["__version__"]) == model.version:
                cache = {k: stored[k] for k in stored.files if k != "__version__"}
        except (OSError, KeyError, ValueError):
            cache = {}
        out, fresh = [], 0
        for key, picture, label in examples:
            safe = key.replace("/", "|")
            vector = cache.get(safe)
            if vector is None:
                image = self.cv2.imread(picture) if self.cv2 is not None else None
                if image is None:
                    continue
                _, vector = model.predict(image)
                if vector is None:
                    continue
                vector = np.asarray(vector, dtype=np.float32)
                cache[safe] = vector
                fresh += 1
            out.append((vector, label))
        if fresh:
            os.makedirs(self.folder, exist_ok=True)
            tmp = path + ".tmp.npz"
            np.savez_compressed(tmp, __version__=np.array(model.version), **cache)
            os.replace(tmp, path)
        return out

    def train(self, model):
        """Trains the layer on every example (the base model gives the embeddings). -> info(); no model or too few
        examples: the layer is removed and the reason said."""
        np = self.np
        if model is None:
            self.last_error = "no local model"
            return self.info()
        with self.lock:
            self.training = True
            try:
                examples = examples_of(self.data_dir)
                if len(examples) > MAX_EXAMPLES:
                    failed_ones = [e for e in examples if e[2] == 1][:MAX_EXAMPLES // 2]
                    fine_ones = [e for e in examples if e[2] == 0]
                    room = MAX_EXAMPLES - len(failed_ones)
                    examples = failed_ones + fine_ones[:: max(1, -(-len(fine_ones) // room))][:room]
                pairs = self._embeddings(model, examples)
                failed = sum(1 for _, label in pairs if label == 1)
                fine = len(pairs) - failed
                if failed < MIN_FAILED or fine < MIN_FINE:
                    self.layer = None
                    try:
                        os.remove(os.path.join(self.folder, "layer.json"))
                    except OSError:
                        pass
                    self.last_error = "too few examples: %d failed (at least %d), %d fine (at least %d)" % (failed, MIN_FAILED, fine, MIN_FINE)
                    return dict(self.info(), failed=failed, fine=fine)
                x = np.stack([v for v, _ in pairs]).astype(np.float64)
                x = x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-9)
                y = np.array([label for _, label in pairs], dtype=np.float64)
                # measured on one example in five kept aside (every fifth), then trained on all
                held = np.arange(len(y)) % 5 == 0
                w, b = fit(np, x[~held], y[~held])
                predicted = _sigmoid(np, x[held] @ w + b) >= 0.5
                truth = y[held] == 1
                measured = {"right": round(float((predicted == truth).mean()), 3) if held.any() else None,
                            "failed_caught": round(float(predicted[truth].mean()), 3) if truth.any() else None,
                            "false_alarms": round(float(predicted[~truth].mean()), 3) if (~truth).any() else None}
                w, b = fit(np, x, y)
                layer = {"version": model.version, "w": w.tolist(), "b": float(b), "examples": len(y), "failed": failed, "fine": fine,
                         "weight": weight_for(failed), "trained_at": round(time.time()), "measured": measured}
                os.makedirs(self.folder, exist_ok=True)
                with open(os.path.join(self.folder, "layer.json.tmp"), "w", encoding="utf-8") as handle:
                    json.dump(layer, handle)
                os.replace(os.path.join(self.folder, "layer.json.tmp"), os.path.join(self.folder, "layer.json"))
                layer["w"] = w
                self.layer = layer
                self.last_error = ""
                return self.info()
            except Exception as error:  # noqa: BLE001 - said on the page, the monitor goes on with the base model
                self.last_error = str(error)[:200]
                return self.info()
            finally:
                self.training = False

    # ------------------------------------------------------------------ export / import
    def export(self, printer_name=""):
        """A zip of the examples (the pictures, small, and their labels): valid with any base model. -> bytes."""
        examples = examples_of(self.data_dir)
        examples = [e for e in examples if not e[0].startswith("imp/")]   # what this printer learned, not what it imported
        failed = [e for e in examples if e[2] == 1]
        fine = [e for e in examples if e[2] == 0]
        chosen = failed[:EXPORT_MAX] + fine[: max(0, EXPORT_MAX - len(failed[:EXPORT_MAX]))]
        buffer = io.BytesIO()
        labels = {}
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for k, (_, picture, label) in enumerate(chosen):
                name = "%05d.jpg" % k
                content = self._small(picture)
                if content is None:
                    continue
                archive.writestr(name, content)
                labels[name] = label
            archive.writestr("labels.json", json.dumps({"format": 1, "printer": printer_name, "made": round(time.time()), "pictures": labels}))
        return buffer.getvalue()

    def _small(self, picture):
        """The JPEG bytes of a picture, at most EXPORT_WIDTH wide (None: unreadable)."""
        try:
            with open(picture, "rb") as handle:
                content = handle.read()
        except OSError:
            return None
        if self.cv2 is None:
            return content
        image = self.cv2.imread(picture)
        if image is None:
            return None
        height, width = image.shape[:2]
        if width <= EXPORT_WIDTH:
            return content
        small = self.cv2.resize(image, (EXPORT_WIDTH, max(1, round(height * EXPORT_WIDTH / width))), interpolation=self.cv2.INTER_AREA)
        ok, encoded = self.cv2.imencode(".jpg", small, [int(self.cv2.IMWRITE_JPEG_QUALITY), 80])
        return encoded.tobytes() if ok else content

    def imported(self):
        """-> [{"origin", "printer", "pictures"}] the examples brought from other printers."""
        out = []
        for labels_file in sorted(glob.glob(os.path.join(self.folder, "imported", "*", "labels.json"))):
            try:
                labels = _read_json(labels_file)
            except (OSError, ValueError):
                continue
            out.append({"origin": os.path.basename(os.path.dirname(labels_file)), "printer": labels.get("printer"), "pictures": len(labels.get("pictures") or {})})
        return out

    def import_zip(self, data, origin):
        """Adds the examples of a zip made by export() (another printer). -> how many pictures. ValueError: not one."""
        origin = ORIGIN_RE.sub("_", origin or "printer").strip("_")[:40] or "printer"
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
            labels = json.loads(archive.read("labels.json"))
        except (zipfile.BadZipFile, KeyError, ValueError):
            raise ValueError("not a file exported by KlippEye") from None
        pictures = labels.get("pictures") if isinstance(labels, dict) else None
        if not isinstance(pictures, dict) or labels.get("format") != 1:
            raise ValueError("not a file exported by KlippEye")
        origin = ORIGIN_RE.sub("_", str(labels.get("printer") or ""))[:40].strip("_") or origin
        folder = os.path.join(self.folder, "imported", origin + "-" + time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(folder, exist_ok=True)
        kept = {}
        for name, label in pictures.items():
            if not re.match(r"^\d{5}\.jpg$", name) or label not in (0, 1):
                continue
            try:
                content = archive.read(name)
            except KeyError:
                continue
            if content[:2] != b"\xff\xd8" or len(content) > 2 * 1024 * 1024:
                continue
            with open(os.path.join(folder, name), "wb") as handle:
                handle.write(content)
            kept[name] = label
        if not kept:
            shutil.rmtree(folder, ignore_errors=True)
            raise ValueError("the file has no pictures")
        with open(os.path.join(folder, "labels.json"), "w", encoding="utf-8") as handle:
            json.dump({"format": 1, "printer": labels.get("printer") or origin, "pictures": kept}, handle)
        return len(kept)

    def forget_imported(self):
        shutil.rmtree(os.path.join(self.folder, "imported"), ignore_errors=True)
