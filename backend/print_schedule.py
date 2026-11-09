"""Release 1.70: prints that start by themselves at a chosen time (the «Schedule the print» of a file's menu).

The KlippEye service keeps the list in schedule.json (data folder) and looks at it every few seconds: a print whose time
has come starts when the printer is ready and free. Otherwise it is not started later on its own (the bed may hold the
print that kept the printer busy): it is marked «missed», with the reason, and the dashboard says so.

  waiting   not yet its time
  started   started at its time (`started` = when)
  missed    not started: `reason` busy (another print was on), not_ready (Klipper off, shut down, in error, for
            longer than the grace time), error (Moonraker refused: the file is gone, say; `detail` has its words)
  cancelled removed by the person before its time (kept only in the answer of that removal)

Finished entries (started, missed) are kept for a day after their time, so every device sees what happened.
This file knows nothing of Flask or of the network: the service gives it the printer's state and a function that starts
a print.
"""
import json
import os
import threading
import time
import uuid

SCHEDULE_FILE = "schedule.json"
MAX_ENTRIES = 50
NOT_READY_GRACE_S = 10 * 60   # Klipper restarting at the scheduled time: wait this long before giving up
KEEP_FINISHED_S = 24 * 3600
MAX_AHEAD_S = 60 * 24 * 3600  # two months
BUSY_STATES = ("printing", "paused")


class ScheduleError(ValueError):
    pass


def clean_filename(name):
    """A G-code file's path as Moonraker names it (relative to the gcodes folder), or None."""
    if not isinstance(name, str):
        return None
    name = name.strip().lstrip("/")
    if name.startswith("gcodes/"):
        name = name[len("gcodes/"):]
    if not name or len(name) > 512 or "\x00" in name or "\n" in name:
        return None
    if any(part in ("", ".", "..") for part in name.split("/")):
        return None
    return name


def decide(entry, now, state):
    """What to do with a waiting `entry` now. `state`: {klippy: ready|startup|shutdown|error|offline, print: print_stats
    state}. Answers "wait", "start" or ("missed", reason)."""
    if entry.get("status") != "waiting" or now < entry.get("at", 0):
        return "wait"
    if (state or {}).get("klippy") != "ready":
        return ("missed", "not_ready") if now - entry["at"] > NOT_READY_GRACE_S else "wait"
    if (state or {}).get("print") in BUSY_STATES:
        return ("missed", "busy")
    return "start"


class PrintSchedule:
    def __init__(self, data_dir, write_json, clock=time.time):
        self.path = os.path.join(data_dir, SCHEDULE_FILE)
        self.write_json = write_json
        self.clock = clock
        self.lock = threading.Lock()

    # --- the file ----------------------------------------------------------------------------------------------------
    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return []
        except (OSError, ValueError):
            return []  # a damaged file: start again from an empty list (it is rewritten at the next change)
        entries = data.get("entries") if isinstance(data, dict) else None
        return [e for e in entries if isinstance(e, dict) and e.get("id")] if isinstance(entries, list) else []

    def _write(self, entries):
        self.write_json(self.path, {"entries": entries})

    def _prune(self, entries, now):
        return [e for e in entries if e.get("status") == "waiting" or now - max(e.get("at", 0), e.get("finished", 0)) < KEEP_FINISHED_S]

    # --- what the dashboard asks -------------------------------------------------------------------------------------
    def entries(self):
        with self.lock:
            now = self.clock()
            return sorted(self._prune(self._read(), now), key=lambda e: e.get("at", 0))

    def add(self, filename, at):
        name = clean_filename(filename)
        if not name:
            raise ScheduleError("not a file of the printer")
        try:
            at = float(at)
        except (TypeError, ValueError):
            raise ScheduleError("not a time")
        now = self.clock()
        if at < now - 60:
            raise ScheduleError("this time has passed")
        if at > now + MAX_AHEAD_S:
            raise ScheduleError("at most two months ahead")
        with self.lock:
            entries = self._prune(self._read(), now)
            if len([e for e in entries if e.get("status") == "waiting"]) >= MAX_ENTRIES:
                raise ScheduleError("too many scheduled prints")
            entry = {"id": uuid.uuid4().hex[:12], "filename": name, "at": int(at), "created": int(now), "status": "waiting"}
            entries.append(entry)
            self._write(entries)
            return entry

    def remove(self, entry_id):
        """Takes a print off the list (a waiting one, or a finished one to forget it). True when it was there."""
        with self.lock:
            entries = self._read()
            kept = [e for e in entries if e.get("id") != entry_id]
            if len(kept) == len(entries):
                return False
            self._write(kept)
            return True

    # --- the service's clock -----------------------------------------------------------------------------------------
    def tick(self, read_state, start_print):
        """Once every few seconds: starts what is due. `read_state()` -> {klippy, print} (only called when something is
        due); `start_print(filename)` raises with the reason when Moonraker refuses. Answers the entries changed."""
        with self.lock:
            now = self.clock()
            entries = self._read()
            due = [e for e in entries if e.get("status") == "waiting" and e.get("at", 0) <= now]
            if not due:
                pruned = self._prune(entries, now)
                if len(pruned) != len(entries):
                    self._write(pruned)
                return []
            try:
                state = read_state()
            except Exception:
                state = {"klippy": "offline"}
            changed = []
            started_one = False
            for entry in sorted(due, key=lambda e: e.get("at", 0)):
                verdict = decide(entry, now, state)
                if verdict == "start" and started_one:
                    verdict = ("missed", "busy")  # two at the same time: the first one prints
                if verdict == "wait":
                    continue
                if verdict == "start":
                    try:
                        start_print(entry["filename"])
                        entry.update(status="started", finished=int(now))
                        started_one = True
                    except Exception as error:  # Moonraker's words: the file is gone, Klipper not ready…
                        entry.update(status="missed", reason="error", detail=str(error)[:200], finished=int(now))
                else:
                    entry.update(status="missed", reason=verdict[1], finished=int(now))
                changed.append(dict(entry))
            if changed:
                self._write(self._prune(entries, now))
            return changed
