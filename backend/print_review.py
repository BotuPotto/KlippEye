"""
How each print went, in the person's words (1.103): when a print ends (finished or cancelled) the dashboard asks «How did it
go?»: went fine, or a problem (which kinds, and from about which picture). It is optional (the setting "print_review").

The answers are the examples the AI monitor learns from (the local model, a later release) and catch the failures nobody
was warned about, that the alarms alone never see. Each print keeps a few small pictures of its own (one a minute at most,
48 at most: when full every other one goes and the pause doubles), so they are there even when the recordings are off.

    <root>/<id>/review.json   {id, file, started, ended, end_state, thumbs: [{n, t, progress, layer}], answer}
    <root>/<id>/0001.jpg ...  the pictures (320 x 214)

answer: None (not answered yet), {"outcome": "ok" | "failed" | "skipped", "problems": [...], "failed_at": time | None, "time"}.
Only the standard library, plus the OpenCV module the caller passes (none: no pictures, the question is still asked).
"""

import json
import os
import re
import shutil
import threading
import time

ACTIVE_STATES = ("printing", "paused")
# the ones that ruin a print (what the AI monitor must catch), then the defects of quality; the order the dashboard shows
PROBLEMS = ("spaghetti", "detached", "layer_shift", "nozzle_blob", "clog", "warping",
            "stringing", "under_extrusion", "over_extrusion", "elephant_foot", "ghosting", "overhangs", "supports", "rough_surface", "other")
OUTCOMES = ("ok", "failed", "skipped")
THUMB_WIDTH, THUMB_HEIGHT, THUMB_QUALITY = 320, 214, 70
THUMB_EVERY_S = 60       # the first pause between two pictures (doubles every time the print fills its pictures)
MAX_THUMBS = 48
KEEP = 60                # prints kept (the oldest go)
MIN_PRINT_S = 120        # a print shorter than this (a test, a quick cancel) is not asked about
ASK_FOR_S = 48 * 3600    # a print not answered in two days is no longer asked about
ID_RE = re.compile(r"^\d{8}-\d{6}(-[A-Za-z0-9_.-]{1,60})?$")


def _slug(filename):
    base = os.path.splitext(os.path.basename(filename or ""))[0]
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", base)[:60].strip("_")


class PrintReviews:
    def __init__(self, root, cv2=None):
        self.root = root
        self.cv2 = cv2
        self.enabled = True
        self.lock = threading.RLock()
        self.current = None      # the review of the print running now
        self.every = THUMB_EVERY_S
        self.next_thumb = 0.0
        self._close_left_open()

    # ------------------------------------------------------------------ files
    def ids(self):
        try:
            return sorted(name for name in os.listdir(self.root) if ID_RE.match(name) and os.path.isdir(os.path.join(self.root, name)))
        except OSError:
            return []

    def load(self, rid):
        if not ID_RE.match(rid or ""):
            return None
        try:
            with open(os.path.join(self.root, rid, "review.json"), encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def _save(self, review):
        folder = os.path.join(self.root, review["id"])
        try:
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, "review.json.tmp"), "w", encoding="utf-8") as handle:
                json.dump(review, handle, ensure_ascii=False)
            os.replace(os.path.join(folder, "review.json.tmp"), os.path.join(folder, "review.json"))
        except OSError as error:
            print("[REVIEW] not saved: %s" % error)

    def _close_left_open(self):
        """A print the service was watching when it stopped: kept open, so the same print going on is followed again."""
        for rid in self.ids()[-3:]:
            review = self.load(rid)
            if review and review.get("ended") is None:
                self.current = review

    def _prune(self):
        ids = self.ids()
        for rid in ids[:-KEEP] if len(ids) > KEEP else []:
            if self.current and self.current["id"] == rid:
                continue
            shutil.rmtree(os.path.join(self.root, rid), ignore_errors=True)

    # ------------------------------------------------------------------ settings
    def configure(self, enabled):
        with self.lock:
            self.enabled = bool(enabled)

    # ------------------------------------------------------------------ the print
    def observe(self, state, filename, now):
        """Called at every round of the monitor: opens the review of a print that starts, closes it when the print ends."""
        with self.lock:
            if state in ACTIVE_STATES:
                if self.current and self.current.get("file") != (filename or ""):
                    self._close("another file", now)
                if self.current and self.current.get("ended") is None:
                    return
                if not self.enabled:
                    return
                rid = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
                if _slug(filename):
                    rid += "-" + _slug(filename)
                self.current = {"id": rid, "file": filename or "", "started": round(now, 2), "ended": None, "end_state": None, "thumbs": [], "answer": None}
                self.every, self.next_thumb = THUMB_EVERY_S, 0.0
                self._save(self.current)
                self._prune()
            elif self.current:
                self._close(state or "standby", now)

    def _close(self, why, now):
        review = self.current
        self.current = None
        if review is None:
            return
        review["ended"] = round(now, 2)
        review["end_state"] = why
        self._save(review)

    def add_frame(self, frame, now, meta=None):
        """One small picture of the print, now and then (an OpenCV image). -> True when kept."""
        with self.lock:
            review = self.current
            if not (review and self.enabled and self.cv2 is not None) or review.get("ended") is not None or now < self.next_thumb:
                return False
            try:
                small = self.cv2.resize(frame, (THUMB_WIDTH, THUMB_HEIGHT), interpolation=self.cv2.INTER_AREA)
                ok, data = self.cv2.imencode(".jpg", small, [int(self.cv2.IMWRITE_JPEG_QUALITY), THUMB_QUALITY])
                if not ok:
                    return False
                n = (review["thumbs"][-1]["n"] + 1) if review["thumbs"] else 1
                folder = os.path.join(self.root, review["id"])
                os.makedirs(folder, exist_ok=True)
                with open(os.path.join(folder, "%04d.jpg" % n), "wb") as handle:
                    handle.write(data.tobytes())
            except Exception as error:  # noqa: BLE001 - the monitor goes on
                print("[REVIEW] picture not kept: %s" % error)
                return False
            meta = meta or {}
            review["thumbs"].append({"n": n, "t": round(now, 2), "progress": meta.get("progress"), "layer": meta.get("layer")})
            self.next_thumb = now + self.every
            if len(review["thumbs"]) > MAX_THUMBS:
                # full: every other picture goes (the first and the last stay), and the pause doubles
                keep = review["thumbs"][::2]
                if keep[-1] is not review["thumbs"][-1]:
                    keep.append(review["thumbs"][-1])
                kept = {t["n"] for t in keep}
                for t in review["thumbs"]:
                    if t["n"] not in kept:
                        try:
                            os.remove(os.path.join(self.root, review["id"], "%04d.jpg" % t["n"]))
                        except OSError:
                            pass
                review["thumbs"] = keep
                self.every *= 2
            self._save(review)
            return True

    # ------------------------------------------------------------------ the question
    def pending(self, now=None):
        """The last print that ended and has not been answered yet (or None): what the dashboard asks about."""
        now = time.time() if now is None else now
        with self.lock:
            if not self.enabled or (self.current and self.current.get("ended") is None):
                return None
            for rid in reversed(self.ids()):
                review = self.load(rid)
                if not review or review.get("ended") is None:
                    continue
                if review.get("answer") is not None:
                    return None   # only the last print is asked about: an older one is past
                if now - review["ended"] > ASK_FOR_S or review["ended"] - review["started"] < MIN_PRINT_S:
                    return None
                return review
            return None

    def answer(self, rid, outcome, problems=None, failed_at=None):
        """The person's answer. -> the review. KeyError: no such print; ValueError: an answer that does not fit."""
        if outcome not in OUTCOMES:
            raise ValueError("outcome must be ok, failed or skipped")
        problems = [p for p in (problems or []) if p in PROBLEMS] if outcome == "failed" else []
        with self.lock:
            review = self.load(rid)
            if review is None:
                raise KeyError(rid)
            if outcome == "failed" and failed_at is not None:
                end = review.get("ended") or time.time()
                if not isinstance(failed_at, (int, float)) or isinstance(failed_at, bool) or not (review["started"] - 1 <= failed_at <= end + 1):
                    raise ValueError("failed_at must be a moment of the print")
                failed_at = round(float(failed_at), 2)
            else:
                failed_at = None
            review["answer"] = {"outcome": outcome, "problems": sorted(set(problems), key=PROBLEMS.index), "failed_at": failed_at, "time": round(time.time())}
            self._save(review)
            return review

    def picture(self, rid, n):
        """The path of one small picture of a print, or None."""
        if not ID_RE.match(rid or "") or not isinstance(n, int) or n < 1:
            return None
        path = os.path.join(self.root, rid, "%04d.jpg" % n)
        return path if os.path.isfile(path) else None
