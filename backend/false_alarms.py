"""
What the local model learns live from its false alarms (1.125).

The base model is the same for everyone; on one printer, one scene can fool it for a whole print (a purge line next to
the part, a clip, a bed texture) and it then rates every picture «failed». The personal layer (personal_layer.py) learns
from labelled prints, but needs failed ones too. This memory needs only the false alarms:

  - the person marks an alarm «false» (print card or alarm list): the picture's embedding (how the model describes it,
    1024 numbers) is kept, with the model's score, until the person forgets it or marks the alarm «right» again;
  - the online AI answers «fine» to a question the local model asked (or took part in): kept for ONLINE_HOURS.

At every look, a picture whose embedding is close to a kept one (cosine >= SIM) and whose score is not much higher than
that one's (at most MARGIN points more) is a known false alarm: the look does not count as a doubt or as sure (no alarm,
no pause, no online question). A worse picture of the same scene (higher score), or another scene, counts as before.
Only for the model version the embeddings were made with.

On disk, in <data>/personal/ (apart from the recordings and the alarm list: deleting those forgets nothing):
false_alarms.npz (the embeddings), false_alarms.json (what each one is) and false_alarms/<key>.jpg, a small copy of each
picture the person marked: with a new base model the embeddings are made again from them (refresh()), so what the
person taught is not lost. Only numpy (and the OpenCV module the caller passes, for the small pictures).
"""
import json
import os
import threading
import time

SIM = 0.92           # this close (cosine of the embeddings) is the same scene
MARGIN = 15.0        # ... and up to this many points higher than the kept score is the same false alarm
ONLINE_HOURS = 6     # an online «fine» is kept this long (the scene of one print); the person's until forgotten
MAX_KEPT = 300       # the oldest go first
PICTURE_WIDTH = 320  # the small copy of a picture the person marked


class FalseAlarms:
    def __init__(self, data_dir, np, cv2=None):
        self.np, self.cv2 = np, cv2
        self.folder = os.path.join(data_dir, "personal")
        self.lock = threading.Lock()
        self.vectors = None   # n x E, unit length
        self.items = []       # [{"key", "source": "person" | "online", "score", "at", "until", "model"}]
        self._load()

    # ---------------------------------------------------------------- disk
    def _paths(self):
        return os.path.join(self.folder, "false_alarms.npz"), os.path.join(self.folder, "false_alarms.json")

    def _load(self):
        vectors_path, items_path = self._paths()
        try:
            with open(items_path, encoding="utf-8") as fh:
                items = json.load(fh).get("items") or []
            vectors = self.np.load(vectors_path)["vectors"]
            if len(items) == len(vectors):
                self.items, self.vectors = items, vectors.astype(self.np.float32)
        except (OSError, ValueError, KeyError):
            self.items, self.vectors = [], None

    def _save(self):
        vectors_path, items_path = self._paths()
        os.makedirs(self.folder, exist_ok=True)
        if not self.items:
            for path in (vectors_path, items_path):
                try:
                    os.remove(path)
                except OSError:
                    pass
            return
        with open(vectors_path + ".tmp", "wb") as fh:
            self.np.savez(fh, vectors=self.vectors)
        os.replace(vectors_path + ".tmp", vectors_path)
        with open(items_path + ".tmp", "w", encoding="utf-8") as fh:
            json.dump({"format": 1, "items": self.items}, fh)
        os.replace(items_path + ".tmp", items_path)

    # ---------------------------------------------------------------- changes
    def _unit(self, vector):
        v = self.np.asarray(vector, dtype=self.np.float32).reshape(-1)
        norm = float(self.np.linalg.norm(v))
        return v / norm if norm > 0 else None

    def _drop(self, keep):
        """Keeps the items for which keep[i] is True (under the lock); the small pictures of the others go."""
        for item, k in zip(self.items, keep):
            if not k and not any(o.get("key") == item.get("key") for o, kk in zip(self.items, keep) if kk):
                try:
                    os.remove(self._picture_path(item.get("key")))
                except OSError:
                    pass
        self.items = [item for item, k in zip(self.items, keep) if k]
        self.vectors = self.vectors[self.np.array(keep, dtype=bool)] if self.vectors is not None and any(keep) else None
        if not self.items:
            self.vectors = None

    def _picture_path(self, key):
        return os.path.join(self.folder, "false_alarms", "%s.jpg" % "".join(c for c in str(key) if c.isalnum() or c in "-_."))

    def add(self, vector, score, source, key, model, now=None, picture=None):
        """Keeps one false alarm. `key`: what it comes from (the alarm's id), to forget it with that alarm. `picture`
        (the person's ones): kept small, to describe it again with a new base model."""
        unit = self._unit(vector)
        if unit is None:
            return False
        if picture is not None and self.cv2 is not None:
            try:
                height, width = picture.shape[:2]
                scale = min(1.0, PICTURE_WIDTH / float(width))
                small = self.cv2.resize(picture, (int(width * scale), int(height * scale)), interpolation=self.cv2.INTER_AREA)
                os.makedirs(os.path.dirname(self._picture_path(key)), exist_ok=True)
                self.cv2.imwrite(self._picture_path(key), small, [self.cv2.IMWRITE_JPEG_QUALITY, 80])
            except Exception:  # without the copy it still works, until a new base model
                pass
        now = time.time() if now is None else now
        item = {"key": str(key), "source": source, "score": round(float(score), 1), "at": round(now), "model": model,
                "until": round(now + ONLINE_HOURS * 3600) if source == "online" else None}
        with self.lock:
            self._expire(now)
            if self.items:   # the same alarm again: replaced
                self._drop([i.get("key") != item["key"] or i.get("source") != source for i in self.items])
            self.items.append(item)
            self.vectors = unit[None, :] if self.vectors is None else self.np.vstack([self.vectors, unit[None, :]])
            if len(self.items) > MAX_KEPT:
                self._drop([index >= len(self.items) - MAX_KEPT for index in range(len(self.items))])
            self._save()
        return True

    def forget(self, key=None, near=None, model=None):
        """Forgets the false alarms of `key`, and those of the same scene as `near` (an alarm marked «right»: the scene was
        a real problem after all); without key and near: all of them. -> how many were forgotten."""
        with self.lock:
            if not self.items:
                return 0
            keep = [True] * len(self.items)
            if key is None and near is None:
                keep = [False] * len(self.items)
            if key is not None:
                keep = [k and item.get("key") != str(key) for k, item in zip(keep, self.items)]
            unit = self._unit(near) if near is not None else None
            if unit is not None and self.vectors is not None:
                close = self.vectors @ unit >= SIM
                keep = [k and not (bool(c) and item.get("model") == model) for k, c, item in zip(keep, close, self.items)]
            gone = keep.count(False)
            if gone:
                self._drop(keep)
                self._save()
            return gone

    def _expire(self, now):
        if self.items and any(item.get("until") and item["until"] < now for item in self.items):
            self._drop([not (item.get("until") and item["until"] < now) for item in self.items])
            self._save()

    def refresh(self, model, describe):
        """A new base model (`model`: its version): the person's false alarms described again from their small pictures
        (`describe(picture) -> embedding or None`); the online ones of the old model are dropped. -> how many were kept."""
        with self.lock:
            stale = [i for i, item in enumerate(self.items) if item.get("model") != model]
            if not stale:
                return len(self.items)
            keep = [True] * len(self.items)
            for index in stale:
                item, vector = self.items[index], None
                if item.get("source") == "person" and self.cv2 is not None:
                    picture = self.cv2.imread(self._picture_path(item.get("key")))
                    vector = describe(picture) if picture is not None else None
                unit = self._unit(vector) if vector is not None else None
                if unit is None or self.vectors.shape[1] != unit.shape[0]:
                    if unit is not None:   # another embedding size: all rows are made again below
                        item["_new"] = unit
                    else:
                        keep[index] = False
                    continue
                self.vectors[index] = unit
                item["model"] = model
            if any(item.get("_new") is not None for item in self.items):
                rows = [item.pop("_new") if item.get("_new") is not None else None for item in self.items]
                keep = [k and r is not None for k, r in zip(keep, rows)]
                self.vectors = self.np.stack([r for r in rows if r is not None]) if any(r is not None for r in rows) else None
                self.items = [dict(item, model=model) for item, k in zip(self.items, keep) if k]
            else:
                self._drop(keep)
            self._save()
            return len(self.items)

    # ---------------------------------------------------------------- use
    def match(self, vector, score, model, now=None):
        """The kept false alarm this look is like (same model, cosine >= SIM, score <= kept + MARGIN), or None."""
        if not self.items or vector is None:
            return None
        unit = self._unit(vector)
        if unit is None:
            return None
        now = time.time() if now is None else now
        with self.lock:
            self._expire(now)
            if self.vectors is None or self.vectors.shape[1] != unit.shape[0]:
                return None
            similarity = self.vectors @ unit
            best = None
            for index, item in enumerate(self.items):
                if item.get("model") != model or similarity[index] < SIM or float(score) > item["score"] + MARGIN:
                    continue
                if best is None or similarity[index] > best[0]:
                    best = (float(similarity[index]), item)
            if best is None:
                return None
            return dict(best[1], similarity=round(best[0], 3))

    def info(self, model=None):
        with self.lock:
            self._expire(time.time())
            mine = [item for item in self.items if model is None or item.get("model") == model]
            return {"person": sum(1 for item in mine if item.get("source") == "person"),
                    "online": sum(1 for item in mine if item.get("source") == "online")}
