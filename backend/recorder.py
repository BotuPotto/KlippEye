"""
The recorder of KlippEye's AI print monitor: while a print runs, it keeps the pictures the monitor looked at (small, 540x360)
with what the printer was doing at that moment, so that the monitor can be MEASURED afterwards instead of guessed:
scripts/replay.py runs the monitor again on them and counts the alarms (see docs/GUIDE.md, "Measuring the monitor").

On disk, in <data folder>/recordings/<id>/ (one folder per print, <id> = start time + file name):
  session.json   the print: file, start and end, how it ended, the monitor settings in use, the live alarms and AI verdicts,
                 the person's label ("it went fine" / "it failed from here") and the measured CPU
  frames.jsonl   one line per picture: number, time, score, alarm, layer, position, progress
  000001.jpg ... the pictures
The recordings take at most the space chosen in the menu (record_max_mb): the oldest prints are deleted first. Recording
also stops while the disk has less than MIN_FREE_BYTES free. Nothing here may make the monitor fail: every error is logged
and the print goes on.
"""
import json
import os
import re
import shutil
import threading
import time

FRAME_WIDTH = 540   # the size the monitor's filter works at (monitor_core: half of 1080x720)
FRAME_HEIGHT = 360
JPEG_QUALITY = 80
MIN_FREE_BYTES = 1024 ** 3  # never fill the disk: below 1 GB free nothing is recorded
SAVE_EVERY = 20  # session.json is written again every N pictures (and at every event)
ID_RE = re.compile(r"^\d{8}-\d{6}(-[A-Za-z0-9._-]{1,40})?$")
OUTCOMES = ("ok", "failed")
ACTIVE_STATES = ("printing", "paused")  # a paused print is the same recording
ALERT_LINK_SECONDS = 600  # an AI verdict belongs to the recording of the alarm that caused it


def _slug(name):
    base = os.path.splitext(os.path.basename(str(name or "")))[0]
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-")[:40]


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def _folder_bytes(path):
    total = 0
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
    except OSError:
        pass
    return total


class Recorder:
    def __init__(self, root, cv2=None, release=""):
        self.root = root
        self.cv2 = cv2
        self.release = release
        self.lock = threading.RLock()
        self.enabled = False
        self.max_bytes = 2000 * 1024 ** 2
        self.session = None  # the session.json of the print being recorded
        self.frames_file = None
        self.status = "off"
        self.last_trigger = None  # (session id, time, frame) of the last live alarm
        self._sizes = None  # {id: bytes} of the folders, measured once and then kept up to date
        self.close_orphans()

    def close_orphans(self):
        """Recordings left open by a power cut or a restart of the backend (session.json without an end): closed at the
        time of their last picture, so that they no longer say "recording". -> how many."""
        closed = 0
        for sid in self.ids():
            session = self.load(sid)
            if not session or session.get("ended") is not None:
                continue
            last, count = session.get("started"), 0
            try:
                with open(os.path.join(self.root, sid, "frames.jsonl"), encoding="utf-8") as f:
                    for line in f:
                        try:
                            row = json.loads(line)
                        except ValueError:
                            continue
                        count += 1
                        if isinstance(row.get("t"), (int, float)):
                            last = row["t"]
            except OSError:
                pass
            session.update(ended=last, end_state="interrupted (power cut or restart)", frames=max(count, session.get("frames") or 0))
            self._save(session)
            closed += 1
            print("[RECORDER] recording %s was left open: closed (%d pictures)" % (sid, count))
        return closed

    # ------------------------------------------------------------------ settings
    def configure(self, enabled, max_mb):
        with self.lock:
            self.enabled = bool(enabled)
            self.max_bytes = int(max_mb) * 1024 ** 2
            if not self.enabled:
                self._close("recording switched off")
                self.status = "off"
            elif self.status == "off":
                self.status = "waiting for a print"

    # ------------------------------------------------------------------ the print
    def observe(self, state, filename, now, config=None):
        """Called at every round of the monitor with the printer's state: opens a recording when a print starts, closes it
        when the print ends (complete, cancelled, error...) or another file starts."""
        with self.lock:
            if not self.enabled:
                return
            if state in ACTIVE_STATES:
                if self.session and self.session.get("file") != (filename or ""):
                    self._close("another file", now)
                if not self.session:
                    self._open(filename, now, config)
            elif self.session:
                self._close(state or "standby", now)

    def _open(self, filename, now, config):
        sid = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
        slug = _slug(filename)
        if slug:
            sid += "-" + slug
        folder = os.path.join(self.root, sid)
        try:
            os.makedirs(folder, exist_ok=False)
        except FileExistsError:
            return  # the same second twice: the next round opens it
        except OSError as error:
            self.status = "cannot write the recordings: %s" % error
            print("[RECORDER] %s" % self.status)
            return
        self.session = {"id": sid, "file": filename or "", "started": now, "ended": None, "end_state": None, "frames": 0, "bytes": 0,
                        "release": self.release, "config": config or {}, "label": {"outcome": None, "failed_at": None},
                        "truncated": False, "live_triggers": [], "alerts": [], "cpu": {}}
        self.frames_file = os.path.join(folder, "frames.jsonl")
        self.status = "recording"
        self._save()
        print("[RECORDER] recording %s" % sid)

    def _close(self, why, now=None):
        if not self.session:
            return
        self.session["ended"] = time.time() if now is None else now
        self.session["end_state"] = why
        self._save()
        print("[RECORDER] recording %s ended (%s, %d pictures)" % (self.session["id"], why, self.session["frames"]))
        self.session = None
        self.frames_file = None
        if self.enabled:
            self.status = "waiting for a print"
        self._enforce_limit()

    def add_frame(self, frame, now, meta):
        """Keeps one picture the monitor looked at (an OpenCV image) with `meta` (score, alarm, layer...). -> its number, or None."""
        with self.lock:
            if not (self.enabled and self.session and self.cv2 is not None) or self.session.get("truncated"):
                return None
            try:
                if shutil.disk_usage(self.root).free < MIN_FREE_BYTES:
                    self.status = "paused: less than 1 GB free on the disk"
                    return None
                n = self.session["frames"] + 1
                small = self.cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=self.cv2.INTER_AREA)
                ok, data = self.cv2.imencode(".jpg", small, [int(self.cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
                if not ok:
                    return None
                folder = os.path.join(self.root, self.session["id"])
                with open(os.path.join(folder, "%06d.jpg" % n), "wb") as f:
                    f.write(data.tobytes())
                line = dict(meta, n=n, t=round(now, 2))
                with open(self.frames_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(line) + "\n")
                self.session["frames"] = n
                self.session["bytes"] += len(data) + len(json.dumps(line)) + 1
                self.status = "recording"
                if self._sizes is not None:
                    self._sizes[self.session["id"]] = self.session["bytes"]
                if n % SAVE_EVERY == 0:
                    self._save()
                    self._enforce_limit()
                return n
            except Exception as error:  # never stop the monitor
                self.status = "cannot record: %s" % error
                print("[RECORDER] %s" % self.status)
                return None

    def note_trigger(self, now):
        """A live alarm of the monitor (the moment it asks the AI)."""
        with self.lock:
            if not self.session:
                return
            frame = self.session["frames"]
            self.session["live_triggers"].append({"t": round(now, 2), "frame": frame})
            self.last_trigger = (self.session["id"], now, frame, time.time())
            self._save()

    def note_zone(self, zone):
        """The objects of the print (phase 4c: where the part is expected), so that the replay can use them too."""
        with self.lock:
            if self.session and isinstance(zone, dict):
                self.session["zone"] = {"source": zone.get("source"), "objects": zone.get("objects") or []}
                self._save()

    def note_cpu(self, check_ms, cpu_percent):
        with self.lock:
            if self.session:
                self.session["cpu"] = {"check_ms": round(check_ms, 1), "cpu_percent": round(cpu_percent, 1)}

    def attach_alert(self, event):
        """An entry of the alert history (AI verdict): linked to the recording of the alarm that caused it. Adds "session"
        and "frame" to `event` when there is one."""
        with self.lock:
            if not self.last_trigger or time.time() - self.last_trigger[3] > ALERT_LINK_SECONDS:
                return
            sid, t, frame, _ = self.last_trigger
            event["session"], event["frame"], event["trigger_time"] = sid, frame, round(t, 2)
            copy = {k: event.get(k) for k in ("id", "time", "outcome", "action", "summary", "confidence", "label")}
            copy.update(frame=frame, t=round(t, 2))
            session = self.session if self.session and self.session["id"] == sid else self.load(sid)
            if session is None:
                return
            session["alerts"].append(copy)
            self._save(session)

    def label_alert(self, sid, alert_id, label):
        with self.lock:
            session = self.session if self.session and self.session["id"] == sid else self.load(sid)
            if session is None:
                return False
            for alert in session["alerts"]:
                if alert.get("id") == alert_id:
                    alert["label"] = label
            self._save(session)
            return True

    # ------------------------------------------------------------------ reading, labels, deleting
    def _save(self, session=None):
        session = session or self.session
        if not session:
            return
        try:
            _write_json(os.path.join(self.root, session["id"], "session.json"), session)
        except OSError as error:
            print("[RECORDER] cannot save %s: %s" % (session["id"], error))

    def load(self, sid):
        if not ID_RE.match(sid or ""):
            return None
        with self.lock:
            if self.session and self.session["id"] == sid:
                return json.loads(json.dumps(self.session))
            try:
                with open(os.path.join(self.root, sid, "session.json"), encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, dict) else None
            except (OSError, ValueError):
                return None

    def frames(self, sid):
        """The lines of frames.jsonl of a recording (a damaged line is skipped)."""
        if not ID_RE.match(sid or ""):
            return []
        rows = []
        try:
            with open(os.path.join(self.root, sid, "frames.jsonl"), encoding="utf-8") as f:
                for line in f:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
        except OSError:
            pass
        return rows

    def frame_path(self, sid, n):
        if not ID_RE.match(sid or "") or not (isinstance(n, int) and n > 0):
            return None
        path = os.path.join(self.root, sid, "%06d.jpg" % n)
        return path if os.path.isfile(path) else None

    def ids(self):
        try:
            return sorted(name for name in os.listdir(self.root) if ID_RE.match(name) and os.path.isfile(os.path.join(self.root, name, "session.json")))
        except OSError:
            return []

    def sizes(self):
        with self.lock:
            if self._sizes is None:
                self._sizes = {sid: _folder_bytes(os.path.join(self.root, sid)) for sid in self.ids()}
            return dict(self._sizes)

    def summary(self):
        """Everything the dashboard's list needs, newest first."""
        sizes = self.sizes()
        rows = []
        for sid in reversed(self.ids()):
            s = self.load(sid)
            if not s:
                continue
            row = {k: s.get(k) for k in ("id", "file", "started", "ended", "end_state", "frames", "label", "truncated", "cpu")}
            row.update(bytes=sizes.get(sid, s.get("bytes", 0)), live_triggers=len(s.get("live_triggers") or []),
                       alerts=len(s.get("alerts") or []), recording=bool(self.session and self.session["id"] == sid))
            rows.append(row)
        try:
            free = shutil.disk_usage(self.root if os.path.isdir(self.root) else os.path.dirname(self.root)).free
        except OSError:
            free = None
        return {"enabled": self.enabled, "max_bytes": self.max_bytes, "used_bytes": sum(sizes.values()), "free_bytes": free,
                "status": self.status, "current": self.session["id"] if self.session else None, "sessions": rows}

    def set_label(self, sid, outcome, failed_at=None):
        """outcome "ok" (the print went fine), "failed" (it went wrong from `failed_at`, a time of the recording) or None."""
        if outcome not in OUTCOMES + (None,):
            raise ValueError("outcome must be ok, failed or null")
        with self.lock:
            session = self.session if self.session and self.session["id"] == sid else self.load(sid)
            if session is None:
                raise KeyError(sid)
            if outcome == "failed":
                if not isinstance(failed_at, (int, float)) or isinstance(failed_at, bool) or not (session["started"] - 1 <= failed_at <= (session.get("ended") or time.time()) + 1):
                    raise ValueError("failed_at must be a moment of the recording")
                failed_at = round(float(failed_at), 2)
            else:
                failed_at = None
            session["label"] = {"outcome": outcome, "failed_at": failed_at, "time": round(time.time())}
            self._save(session)
            return session["label"]

    def delete(self, sid):
        with self.lock:
            if not ID_RE.match(sid or "") or not os.path.isdir(os.path.join(self.root, sid)):
                return False
            if self.session and self.session["id"] == sid:
                self.session = None
                self.frames_file = None
                if self.enabled:
                    self.status = "waiting for a print"
            shutil.rmtree(os.path.join(self.root, sid), ignore_errors=True)
            if self._sizes is not None:
                self._sizes.pop(sid, None)
            return True

    def _enforce_limit(self):
        """Oldest recordings out until the total fits; the one being recorded stops growing if it alone is too big."""
        sizes = self.sizes()
        current = self.session["id"] if self.session else None
        total = sum(sizes.values())
        for sid in sorted(sizes):
            if total <= self.max_bytes:
                break
            if sid == current:
                continue
            total -= sizes[sid]
            self.delete(sid)
            print("[RECORDER] %s deleted: the recordings were over %d MB" % (sid, self.max_bytes // 1024 ** 2))
        if current and total > self.max_bytes and self.session:
            self.session["truncated"] = True
            self.status = "stopped: this print alone fills the space for the recordings"
            self._save()
