#!/usr/bin/env python3
"""
KlippEye push notifications.

Runs on the Raspberry next to Klipper and Moonraker and sends a push notification to the phone (through Firebase
Cloud Messaging, the service every Android app uses for push) when something happens:

    error      Klipper in shutdown / error, or a print ending in error
    complete   print finished
    cancelled  print cancelled
    paused     print paused
    runout     filament runout (the macro filament_change_state1 writes "Printer paused due to filament runout!")
    ai_pause   the AI print monitor recommends a pause (verdict PAUSE)
    ai_cancel  the AI print monitor recommends cancelling (verdict CANCEL)

It READS from Moonraker and from the backend (the Flask backend is not touched) and it needs nothing but Python 3:
no pip packages. The Google sign-in (OAuth2 with the service account key) is done here with the standard library only.

From version 1.1 it also follows the dashboard's settings menu. The dashboard keeps its settings in Moonraker's database
(namespace "klippeye", key "settings") and this service reads them every few seconds:
    · which notifications are on (they win over the "events" of notifier.json),
    · how the AI verdict is filtered (verdicts in a row, minimum confidence, which defects count),
    · whether it may pause / cancel the print by itself when the AI says so (both OFF unless the person switches them on),
    · from version 1.3, the language of the notifications ("language": English or Italian, see MESSAGES).
Pausing and cancelling are the only things it ever WRITES to the printer (Moonraker's /printer/print/pause and /cancel, which run
the PAUSE and CANCEL_PRINT macros like the dashboard buttons do), and it tells the dashboard it is alive by writing its own
key "notifier" (version, last sign of life, last automatic action) into the same namespace.

    python3 klippeye_notifier.py                 run (this is what the systemd service does)
    python3 klippeye_notifier.py --check         checks configuration, Moonraker, backend and the Google sign-in
    python3 klippeye_notifier.py --test          sends a test notification to the phone
    python3 klippeye_notifier.py --dry-run       runs, but prints the notifications instead of sending them

From version 1.2 it lives in ~/klippeye/notifier/ (the repository updated from the dashboard) and its settings in the data
folder (~/printer_data/klippeye/notifier.json). When an update replaces this very file the service notices it, checks that the
new file is valid Python and ends: systemd (Restart=always) starts the new version, so nobody has to restart it by hand.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import queue
import re
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

__version__ = "1.4"

LOG = logging.getLogger("klippeye-notifier")

# ---------------------------------------------------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------------------------------------------------

# The texts of the notifications, in each language the dashboard offers. The language is the one chosen in the dashboard
# (Settings -> Notifications, shared by every phone), else "language" in notifier.json, else English. A text written in
# notifier.json ("messages") always wins.
MESSAGES = {
    "en": {
        "error": "Printer error! Restart it.",
        "complete": "Print completed!",
        "cancelled": "Print cancelled!",
        "paused": "Printer paused!",
        "runout": "Filament run out, change the spool!",
        "ai_pause": "Print defects found, check and pause the print!",
        "ai_cancel": "Serious print defects found, check and cancel the print",
        # when the service paused / cancelled the print by itself (dashboard: AI monitor)
        "ai_pause_auto": "Print defects found: print paused automatically.",
        "ai_cancel_auto": "Serious print defects found: print cancelled automatically.",
        "test": "Test notification: everything works!",
    },
    "it": {
        "error": "Stampante in errore! Effettuare riavvio.",
        "complete": "Stampa completata!",
        "cancelled": "Stampa interrotta!",
        "paused": "Stampante in pausa!",
        "runout": "Filamento esaurito, effettuare cambio bobina!",
        "ai_pause": "Difetti di stampa rilevati, verificare e mettere in pausa la stampa!",
        "ai_cancel": "Difetti gravi di stampa rilevati, verificare e interrompere la stampa",
        "ai_pause_auto": "Difetti di stampa rilevati: stampa messa in pausa automaticamente.",
        "ai_cancel_auto": "Difetti gravi di stampa rilevati: stampa interrotta automaticamente.",
        "test": "Notifica di prova: tutto funziona!",
    },
}
LANGUAGES = tuple(MESSAGES)
DEFAULT_MESSAGES = MESSAGES["en"]


def message_text(config: Dict[str, Any], language: Optional[str], key: str) -> str:
    """The text of a notification: the one written in notifier.json, else the one of `language` (else of the file's, else English)."""
    custom = (config.get("messages") or {}).get(key)
    if isinstance(custom, str) and custom.strip():
        return custom
    for lang in (language, config.get("language"), "en"):
        if lang in MESSAGES:
            return MESSAGES[lang][key]
    return DEFAULT_MESSAGES[key]

DEFAULT_CONFIG: Dict[str, Any] = {
    # where to read from (the Raspberry itself)
    "moonraker_url": "http://127.0.0.1:7125",
    "brain_url": "http://127.0.0.1:8085",
    # Firebase: the key file downloaded from the Firebase console, and the private "topic" the phone listens to
    "service_account_file": "service-account.json",
    "project_id": "",  # empty: taken from the key file
    "topic": "",
    "title": "KlippEye",
    # which notifications are on
    "events": {key: True for key in ("error", "complete", "cancelled", "paused", "runout", "ai_pause", "ai_cancel")},
    "messages": {},  # your own texts, e.g. {"complete": "Done!"}: they win over the language's
    "language": "",  # "en", "it": used until the dashboard's choice is known
    # timing (seconds)
    "poll_seconds": 2,
    "ai_poll_seconds": 5,
    "settings_poll_seconds": 10,  # how often the dashboard's settings are read from Moonraker's database
    "heartbeat_seconds": 120,  # how often the service tells the dashboard it is alive
    "action_timeout_seconds": 90,  # pause / cancel run a Klipper macro that may take a while to finish
    "pause_grace_seconds": 4,  # a pause waits this long, in case a filament runout explains it
    "runout_pause_window_seconds": 90,
    "cooldown_seconds": {"error": 120, "runout": 60, "ai_pause": 180, "ai_cancel": 180, "paused": 15, "cancelled": 15, "complete": 15},
    "message_ttl_seconds": 6 * 3600,  # Google keeps a message this long when the phone is switched off / offline
    "retry_give_up_seconds": 3 * 3600,
    "retry_seconds": 5,  # first wait before sending again after a failure (then doubles, up to 60)
    # for tests only
    "fcm_url": "https://fcm.googleapis.com/v1/projects/{project}/messages:send",
}

# the Android notification channel (created by the app) and the importance of each kind of notification; the ids are
# the app's (alarms, warnings, print) and stay Italian until an app release renames them
KIND_CHANNEL = {
    "error": "allarmi",
    "runout": "allarmi",
    "ai_cancel": "allarmi",
    "ai_pause": "avvisi",
    "paused": "avvisi",
    "cancelled": "avvisi",
    "complete": "stampa",
    "test": "stampa",
}


def merge(defaults: Dict[str, Any], given: Dict[str, Any]) -> Dict[str, Any]:
    """`given` over `defaults`, one level of dictionaries deep (so a config may list only the messages it changes)."""
    result = dict(defaults)
    for key, value in given.items():
        if isinstance(value, dict) and isinstance(defaults.get(key), dict):
            result[key] = {**defaults[key], **value}
        else:
            result[key] = value
    return result


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        given = json.load(handle)
    unknown = [key for key in given if key not in DEFAULT_CONFIG and not key.startswith("_")]
    if unknown:
        LOG.warning("Unknown entries in %s (ignored): %s", path, ", ".join(unknown))
    config = merge(DEFAULT_CONFIG, given)
    base = os.path.dirname(os.path.abspath(path))
    if not os.path.isabs(config["service_account_file"]):
        config["service_account_file"] = os.path.join(base, config["service_account_file"])
    config["_token_file"] = os.path.join(base, "internal.token")  # written by the backend (1.2.0): needed when the password is on
    return config


def brain_headers(config: Dict[str, Any]) -> Dict[str, str]:
    """The internal token of the services on the Raspberry, if there is one (read every time: the backend may create it later)."""
    path = config.get("_token_file")
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            token = handle.read().strip()
    except OSError:
        return {}
    return {"X-KlippEye-Token": token} if token else {}


# ---------------------------------------------------------------------------------------------------------------------
# What happened: the watcher (pure logic, no network: it is given snapshots of the printer and says what to notify)
# ---------------------------------------------------------------------------------------------------------------------

@dataclass
class Notice:
    kind: str
    text: str


@dataclass
class AiVerdict:
    key: str  # changes with every new analysis
    action: str  # "CONTINUE" | "PAUSE" | "CANCEL" | "" (or CONTINUA / PAUSA / CANCELLA from an older backend)
    defects: Optional[Dict[str, Tuple[bool, float]]] = None  # {"spaghetti": (detected, confidence %), ...}; None: the verdict has no details


@dataclass
class Action:
    kind: str  # "pause" | "cancel"


@dataclass
class Snapshot:
    klippy: Optional[str] = None  # "ready" "startup" "shutdown" "error" "disconnected" ... (None: Moonraker not reachable)
    print_state: Optional[str] = None  # "standby" "printing" "paused" "complete" "cancelled" "error" (None: unknown)
    lines: List[Tuple[float, str]] = field(default_factory=list)  # recent console lines: (time, text)
    ai: Optional[AiVerdict] = None  # None: backend not reachable or nothing to say
    settings: Optional[Dict[str, Any]] = None  # the dashboard's settings document; {} = nothing stored yet; None = not known (keep the last)


KLIPPY_ERRORS = ("shutdown", "error")
RUNOUT_LINE = re.compile(r"paused due to filament runout", re.IGNORECASE)

# ---- the dashboard's settings (Moonraker database, namespace "klippeye", key "settings")
DASH_NAMESPACE = "klippeye"
DASH_NAMESPACE_LEGACY = "vzbot_dashboard"  # where the dashboard kept them before it was called KlippEye: still read until the dashboard has copied them
DASH_EVENTS = ("error", "complete", "cancelled", "paused", "runout", "ai_pause", "ai_cancel")
DASH_DEFECTS = ("spaghetti", "empty_bed", "layer_shift", "warping")
AI_CONFIRMATIONS = (1, 2, 3)
AI_CONFIDENCES = (0, 50, 70, 85)


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number_in(value: Any, allowed: Tuple[int, ...], default: int) -> int:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value in allowed else default


def dash_settings(raw: Any) -> Dict[str, Any]:
    """
    The part of the dashboard's settings this service uses, cleaned. The document is written by a browser, so nothing is
    trusted: a missing or wrong value is the default (every notification as in notifier.json, automatic actions OFF).
    """
    given = _dict(raw)
    notifications = _dict(given.get("notifications"))
    ai = _dict(given.get("ai"))
    defects = _dict(ai.get("defects"))
    return {
        "events": {name: notifications[name] for name in DASH_EVENTS if isinstance(notifications.get(name), bool)},
        "ai": {
            "auto_pause": ai.get("autoPause") is True,
            "auto_cancel": ai.get("autoCancel") is True,
            "confirmations": _number_in(ai.get("confirmations"), AI_CONFIRMATIONS, 1),
            "min_confidence": _number_in(ai.get("minConfidence"), AI_CONFIDENCES, 0),
            "defects": {name: defects.get(name) is not False for name in DASH_DEFECTS},
        },
        "language": given.get("language") if given.get("language") in LANGUAGES else None,
        "stamp": given.get("_t") if isinstance(given.get("_t"), (int, float)) and not isinstance(given.get("_t"), bool) else 0,
    }


class Watcher:
    """
    Compares each snapshot with the previous one. Nothing is notified for what is already true when it starts (a print
    that finished yesterday, a verdict of the last print): the first value of each thing is only remembered.
    It does not touch the printer: what it wants done (pause, cancel) is handed over through take_actions(), and how that went
    comes back through report_action().
    """

    AUTO_QUIET_S = 180.0  # after pausing / cancelling by itself, the pause / cancel notice of the state change is not sent too

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.dash = dash_settings({})
        self.klippy: Optional[str] = None
        self.print_state: Optional[str] = None
        self.last_line_time: Optional[float] = None
        self.ai_key: Optional[str] = None
        self.ai_ready = False
        self.ai_levels: List[int] = []  # what the last verdicts of this print recommended (0 none, 1 pause, 2 cancel)
        self.auto_done = {"pause": False, "cancel": False}  # each automatic action happens at most once per print
        self.auto_at: Dict[str, float] = {}  # when the service paused / cancelled by itself
        self.last_action: Optional[Dict[str, Any]] = None  # for the dashboard: {"kind", "ok", "at"}
        self.sent_at: Dict[str, float] = {}
        self.runout_notified_at = float("-inf")
        self.pending_pause: Optional[float] = None
        self._actions: List[Action] = []
        self._results: List[Tuple[str, bool]] = []
        self._lock = threading.Lock()

    # -- helpers
    def _enabled(self, kind: str) -> bool:
        chosen = self.dash["events"].get(kind)  # the dashboard's switch, when it has one
        return chosen if chosen is not None else bool(self.config["events"].get(kind, True))

    def _emit(self, kind: str, now: float, out: List[Notice], text_key: Optional[str] = None) -> bool:
        """Adds the notice unless it is switched off or the same kind went out a moment ago."""
        if not self._enabled(kind):
            return False
        cooldown = float(self.config["cooldown_seconds"].get(kind, 0))
        if now - self.sent_at.get(kind, float("-inf")) < cooldown:
            LOG.info("Notice '%s' not repeated (the same one just went out)", kind)
            return False
        self.sent_at[kind] = now
        key = text_key or kind
        out.append(Notice(kind, message_text(self.config, self.dash["language"], key)))
        return True

    def _recent_auto(self, action: str, now: float) -> bool:
        return now - self.auto_at.get(action, float("-inf")) < self.AUTO_QUIET_S

    # -- what to do, and how it went
    def take_actions(self) -> List[Action]:
        """The pause / cancel the service has decided on since the last call (the caller does them)."""
        with self._lock:
            actions, self._actions = self._actions, []
        return actions

    def report_action(self, kind: str, ok: bool) -> None:
        """Called (from any thread) when a pause / cancel has been tried."""
        with self._lock:
            self._results.append((kind, ok))

    # -- the step
    def step(self, snap: Snapshot, now: float) -> List[Notice]:
        out: List[Notice] = []
        self._settings(snap)
        self._results_of_actions(now, out)
        self._klippy(snap, now, out)
        self._lines(snap, now, out)  # before the print state: the runout line comes before the pause it causes
        self._print(snap, now, out)
        self._pause(snap, now, out)
        self._ai(snap, now, out)
        return out

    def _settings(self, snap: Snapshot) -> None:
        if snap.settings is None:
            return  # not known right now: what was last read stays
        fresh = dash_settings(snap.settings)
        if fresh != self.dash:
            LOG.info("Dashboard settings updated: notifications %s, language %s, automatic pause %s, automatic cancel %s, %d verdicts in a row, minimum confidence %d%%",
                     ", ".join("%s=%s" % (k, "yes" if v else "no") for k, v in sorted(fresh["events"].items())) or "as in notifier.json",
                     fresh["language"] or "not chosen yet",
                     "YES" if fresh["ai"]["auto_pause"] else "no", "YES" if fresh["ai"]["auto_cancel"] else "no",
                     fresh["ai"]["confirmations"], fresh["ai"]["min_confidence"])
        self.dash = fresh

    def _results_of_actions(self, now: float, out: List[Notice]) -> None:
        with self._lock:
            results, self._results = self._results, []
        for kind, ok in results:
            # Klipper may answer late or with an error although the macro did its job: what the print is doing now decides
            if not ok and self.print_state in (("paused",) if kind == "pause" else ("cancelled", "standby")):
                ok = True
            self.last_action = {"kind": kind, "ok": ok, "at": int(time.time())}
            if ok:
                self._emit("ai_cancel" if kind == "cancel" else "ai_pause", now, out, "ai_cancel_auto" if kind == "cancel" else "ai_pause_auto")
            else:
                LOG.error("The automatic action '%s' failed: over to you", kind)
                self.auto_done[kind] = False  # a later verdict may try again
                self._emit("ai_cancel" if kind == "cancel" else "ai_pause", now, out)  # the ordinary notice: "verify and ..."

    def _klippy(self, snap: Snapshot, now: float, out: List[Notice]) -> None:
        if snap.klippy is None:
            return  # Moonraker not reachable: nothing is known, nothing changes
        if self.klippy is not None and snap.klippy in KLIPPY_ERRORS and self.klippy not in KLIPPY_ERRORS:
            self._emit("error", now, out)
        self.klippy = snap.klippy
        if snap.klippy != "ready":
            # Klipper is down or restarting: what the print was doing is not known any more (after the restart the print
            # state is "standby", which must not be taken for a cancelled print)
            self.print_state = None
            self.pending_pause = None

    def _lines(self, snap: Snapshot, now: float, out: List[Notice]) -> None:
        if not snap.lines:
            if self.last_line_time is None and snap.klippy is not None:
                self.last_line_time = 0.0  # an empty console: every line from now on is new
            return
        newest = max(time_ for time_, _ in snap.lines)
        if self.last_line_time is None:
            self.last_line_time = newest  # what was already there when we started is not news
            return
        if newest < self.last_line_time - 5:
            self.last_line_time = newest  # the clock of the Raspberry went back (time sync): start over from here
            return
        fresh = [text for time_, text in snap.lines if time_ > self.last_line_time]
        self.last_line_time = max(self.last_line_time, newest)
        if any(RUNOUT_LINE.search(text) for text in fresh):
            if self._emit("runout", now, out):
                self.runout_notified_at = now

    def _print(self, snap: Snapshot, now: float, out: List[Notice]) -> None:
        state = snap.print_state
        if state is None or snap.klippy not in (None, "ready"):
            return
        previous = self.print_state
        if previous is not None and state != previous:
            if state != "paused":
                self.pending_pause = None  # it went on printing (or stopped) before the pause notice was due
            if state == "printing" and previous not in ("paused", "printing"):
                self.ai_levels = []  # a new print: the verdicts of the last one do not count, and the automatic actions are available again
                self.auto_done = {"pause": False, "cancel": False}
            if state == "complete":
                self._emit("complete", now, out)
            elif state == "cancelled" or (state == "standby" and previous in ("printing", "paused")):
                if not self._recent_auto("cancel", now):  # when the service cancelled by itself, its own notice says so
                    self._emit("cancelled", now, out)
            elif state == "error":
                self._emit("error", now, out)
            elif state == "paused" and previous == "printing":
                if not self._recent_auto("pause", now):
                    self.pending_pause = now
        self.print_state = state

    def _pause(self, snap: Snapshot, now: float, out: List[Notice]) -> None:
        """A pause is announced a few seconds late: if a filament runout caused it, that is the notice that goes out."""
        if self.pending_pause is None:
            return
        window = float(self.config["runout_pause_window_seconds"])
        if now - self.runout_notified_at <= window:
            self.pending_pause = None
        elif now - self.pending_pause >= float(self.config["pause_grace_seconds"]):
            self.pending_pause = None
            self._emit("paused", now, out)

    # -- the AI monitor
    def _level(self, verdict: AiVerdict) -> int:
        """0 nothing, 1 pause, 2 cancel: what the verdict recommends once the dashboard's filters have been applied."""
        action = verdict.action.upper()
        level = 2 if "CANCEL" in action else 1 if "PAUS" in action else 0  # CANCEL / PAUSE, also CANCELLA / PAUSA (before 1.6.0)
        ai = self.dash["ai"]
        filtering = ai["min_confidence"] > 0 or not all(ai["defects"].values())
        if level and filtering and verdict.defects:  # without details (a verdict in plain words) there is nothing to filter on
            counts = [name for name, (detected, confidence) in verdict.defects.items()
                      if detected and ai["defects"].get(name, True) and confidence >= ai["min_confidence"]]
            if not counts:
                LOG.info("AI verdict '%s' ignored: no defect passes the dashboard's filters", action)
                return 0
        return level

    def _ai(self, snap: Snapshot, now: float, out: List[Notice]) -> None:
        verdict = snap.ai
        if verdict is None:
            return
        if not self.ai_ready:
            self.ai_ready = True
            self.ai_key = verdict.key
            return
        if verdict.key == self.ai_key:
            return
        self.ai_key = verdict.key
        if self.print_state not in (None, "printing", "paused"):
            self.ai_levels = []
            return  # a verdict that arrives when no print is running is of no use
        self.ai_levels = (self.ai_levels + [self._level(verdict)])[-3:]
        need = self.dash["ai"]["confirmations"]
        recent = self.ai_levels[-need:]
        if len(recent) < need or min(recent) == 0:
            return  # not enough verdicts in a row yet
        level = min(recent)
        kind = "ai_cancel" if level == 2 else "ai_pause"
        ai = self.dash["ai"]
        act: Optional[str] = None
        if level == 2 and ai["auto_cancel"] and not self.auto_done["cancel"] and self.print_state in ("printing", "paused"):
            act = "cancel"
        elif ai["auto_pause"] and not self.auto_done["pause"] and self.print_state == "printing" and not (level == 2 and ai["auto_cancel"]):
            act = "pause"  # also for a CANCEL verdict while the automatic cancel is off: pausing is the careful half
        if act is None:
            self._emit(kind, now, out)
            return
        LOG.info("AI verdict '%s' confirmed (%d in a row): doing '%s' by myself", "CANCEL" if level == 2 else "PAUSE", need, act)
        self.auto_done[act] = True
        self.auto_at[act] = now
        with self._lock:
            self._actions.append(Action(act))


# ---------------------------------------------------------------------------------------------------------------------
# Reading the printer (Moonraker) and the AI monitor (the backend)
# ---------------------------------------------------------------------------------------------------------------------

def http_json(url: str, method: str = "GET", body: Any = None, headers: Optional[Dict[str, str]] = None,
              timeout: float = 5.0, form: bool = False) -> Tuple[int, Any]:
    """(status, decoded JSON or text). Network failures raise OSError; HTTP errors are returned, not raised."""
    data = None
    request_headers = dict(headers or {})
    if body is not None:
        if form:
            from urllib.parse import urlencode
            data = urlencode(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        else:
            data = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, method=method, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    text = raw.decode("utf-8", errors="replace")
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


def ai_action(response: Dict[str, Any]) -> str:
    """The action ("CONTINUE" | "PAUSE" | "CANCEL", or the Italian words of releases before 1.6.0) of a /api/print/last_analysis answer, as the dashboard reads it."""
    analysis = response.get("analysis")
    candidates: List[Any] = []
    if isinstance(analysis, dict):
        candidates.append(analysis.get("action"))
        inner = analysis.get("analysis")
        if isinstance(inner, dict):
            candidates.append(inner.get("action"))
        elif isinstance(inner, str):
            candidates.append(action_in_text(inner))
    elif isinstance(analysis, str):
        candidates.append(action_in_text(analysis))
    candidates.append(response.get("action"))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip().upper()
    return ""


def action_in_text(text: str) -> str:
    """The verdict is often JSON text (sometimes with words around it): the action is in it."""
    try:
        match = re.search(r"\{[\s\S]*\}", text)
        data = json.loads(match.group(0) if match else text)
        value = data.get("action") if isinstance(data, dict) else None
        return value if isinstance(value, str) else ""
    except ValueError:
        return ""


def json_in_text(text: str) -> Dict[str, Any]:
    """The JSON object inside a text (the AI often puts words around it); {} when there is none."""
    try:
        match = re.search(r"\{[\s\S]*\}", text)
        data = json.loads(match.group(0) if match else text)
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def ai_defects(response: Dict[str, Any]) -> Optional[Dict[str, Tuple[bool, float]]]:
    """
    {"spaghetti": (detected, confidence %), ...} of a /api/print/last_analysis answer, found where the dashboard looks for it
    (the verdict is an object, or text with a JSON object in it). None when the verdict carries no details.
    """
    analysis = response.get("analysis")
    candidates: List[Any] = []
    if isinstance(analysis, dict):
        candidates.append(analysis)
        inner = analysis.get("analysis")
        if isinstance(inner, dict):
            candidates.append(inner)
        elif isinstance(inner, str):
            candidates.append(json_in_text(inner))
    elif isinstance(analysis, str):
        candidates.append(json_in_text(analysis))
    candidates.append(response)
    for data in candidates:
        if not isinstance(data, dict):
            continue
        found: Dict[str, Tuple[bool, float]] = {}
        for name in DASH_DEFECTS:
            entry = data.get(name)
            if isinstance(entry, dict):
                confidence = entry.get("confidence")
                found[name] = (entry.get("detected") is True, float(confidence) if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) else 0.0)
        if found:
            return found
    return None


class PrinterReader:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.moonraker = config["moonraker_url"].rstrip("/")
        self.brain = config["brain_url"].rstrip("/")
        self.config = config
        self.ai_every = float(config["ai_poll_seconds"])
        self.settings_every = float(config["settings_poll_seconds"])
        self.action_timeout = float(config["action_timeout_seconds"])
        self._last_ai_at = float("-inf")
        self._last_settings_at = float("-inf")
        self._ai: Optional[AiVerdict] = None
        self._settings: Optional[Dict[str, Any]] = None
        self._reachable: Dict[str, bool] = {}

    def _note(self, name: str, ok: bool, what: str) -> None:
        """Says (once) when something becomes unreachable or comes back."""
        before = self._reachable.get(name)  # None: the first time
        if before != ok and not (before is None and ok):
            if ok:
                LOG.info("%s reachable again", what)
            else:
                LOG.warning("%s not reachable", what)
        self._reachable[name] = ok

    def snapshot(self, now: float) -> Snapshot:
        snap = Snapshot()
        try:
            status, info = http_json(self.moonraker + "/printer/info")
            ok = status == 200 and isinstance(info, dict)
            self._note("moonraker", ok, "Moonraker")
            if ok:
                snap.klippy = str((info.get("result") or {}).get("state") or "") or None
        except OSError:
            self._note("moonraker", False, "Moonraker")
        if snap.klippy == "ready":
            try:
                status, stats = http_json(self.moonraker + "/printer/objects/query?print_stats")
                if status == 200 and isinstance(stats, dict):
                    snap.print_state = ((stats.get("result") or {}).get("status") or {}).get("print_stats", {}).get("state") or None
            except OSError:
                pass
        if snap.klippy is not None:
            try:
                status, store = http_json(self.moonraker + "/server/gcode_store?count=100")
                if status == 200 and isinstance(store, dict):
                    for item in (store.get("result") or {}).get("gcode_store") or []:
                        if isinstance(item, dict) and isinstance(item.get("message"), str):
                            snap.lines.append((float(item.get("time") or 0), item["message"]))
            except (OSError, ValueError):
                pass
        if now - self._last_ai_at >= self.ai_every:
            self._last_ai_at = now
            self._ai = self._read_ai()
        snap.ai = self._ai
        if now - self._last_settings_at >= self.settings_every:
            self._last_settings_at = now
            fresh = self._read_settings()
            if fresh is not None:
                self._settings = fresh
        snap.settings = self._settings
        return snap

    def _database_url(self, key: str, namespace: str = DASH_NAMESPACE) -> str:
        return "%s/server/database/item?namespace=%s&key=%s" % (self.moonraker, namespace, key)

    def _read_settings(self) -> Optional[Dict[str, Any]]:
        """The dashboard's settings document; {} when nothing is stored yet; None when it could not be read (the last one stays)."""
        try:
            status, answer = http_json(self._database_url("settings"))
            if status == 404:  # nothing under the new name yet: the dashboard of the old name may have saved something
                status, answer = http_json(self._database_url("settings", DASH_NAMESPACE_LEGACY))
        except OSError:
            return None
        if status == 200 and isinstance(answer, dict):
            value = (answer.get("result") or {}).get("value")
            return value if isinstance(value, dict) else {}
        if status == 404:
            return {}  # Moonraker answered: there is no such key (yet)
        return None

    def act(self, kind: str) -> bool:
        """Pauses or cancels the print, as the dashboard buttons do (Moonraker runs the PAUSE / CANCEL_PRINT macro). True when Moonraker said yes."""
        try:
            status, answer = http_json("%s/printer/print/%s" % (self.moonraker, kind), "POST", timeout=self.action_timeout)
        except OSError as error:
            LOG.error("Action '%s': Moonraker not reachable (%s)", kind, error)
            return False
        if status != 200:
            LOG.error("Action '%s': Moonraker answered %s: %s", kind, status, answer)
        return status == 200

    def write_status(self, payload: Dict[str, Any]) -> bool:
        """Tells the dashboard the service is alive (key "notifier" of the same namespace)."""
        try:
            status, _ = http_json(self.moonraker + "/server/database/item", "POST", {"namespace": DASH_NAMESPACE, "key": "notifier", "value": payload})
        except OSError:
            return False
        return status == 200

    def _read_ai(self) -> Optional[AiVerdict]:
        try:
            status, response = http_json(self.brain + "/api/print/last_analysis", headers=brain_headers(self.config))
        except OSError:
            self._note("brain", False, "The backend (AI analysis)")
            return None
        ok = status == 200 and isinstance(response, dict)
        self._note("brain", ok, "The backend (AI analysis)")
        if not ok:
            return None
        if not (response.get("ok", True) and response.get("has_analysis")):
            return AiVerdict(key="none", action="")
        key = str(response.get("timestamp")) + "|" + json.dumps(response.get("analysis"), sort_keys=True, ensure_ascii=False)
        return AiVerdict(key=key, action=ai_action(response), defects=ai_defects(response))


# ---------------------------------------------------------------------------------------------------------------------
# Signing in to Google (service account, RS256) with the standard library only
# ---------------------------------------------------------------------------------------------------------------------

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def der_items(data: bytes) -> List[Tuple[int, bytes]]:
    """The (tag, content) of every DER element at the top level of `data`."""
    items = []
    position = 0
    while position < len(data):
        tag = data[position]
        length = data[position + 1]
        position += 2
        if length & 0x80:
            size = length & 0x7F
            length = int.from_bytes(data[position:position + size], "big")
            position += size
        items.append((tag, data[position:position + length]))
        position += length
    return items


def rsa_private_numbers(pem: str) -> Tuple[int, int]:
    """(modulus, private exponent) of an RSA private key in PEM ("BEGIN PRIVATE KEY" or "BEGIN RSA PRIVATE KEY")."""
    match = re.search(r"-----BEGIN (RSA )?PRIVATE KEY-----([A-Za-z0-9+/=\s]+)-----END (RSA )?PRIVATE KEY-----", pem)
    if not match:
        raise ValueError("the private key is not in the expected format")
    der = base64.b64decode("".join(match.group(2).split()))
    outer = der_items(der)
    if not outer or outer[0][0] != 0x30:
        raise ValueError("unreadable private key")
    fields = der_items(outer[0][1])
    if match.group(1) is None:
        # PKCS#8: version, algorithm, OCTET STRING holding the RSA key
        octets = [content for tag, content in fields if tag == 0x04]
        if not octets:
            raise ValueError("unreadable private key")
        fields = der_items(der_items(octets[0])[0][1])
    integers = [int.from_bytes(content, "big") for tag, content in fields if tag == 0x02]
    if len(integers) < 4:
        raise ValueError("unreadable private key")
    return integers[1], integers[3]  # version, n, e, d, ...


SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def rs256_sign(message: bytes, modulus: int, exponent: int) -> bytes:
    """RSASSA-PKCS1-v1_5 with SHA-256."""
    size = (modulus.bit_length() + 7) // 8
    digest_info = SHA256_PREFIX + hashlib.sha256(message).digest()
    padded = b"\x00\x01" + b"\xff" * (size - len(digest_info) - 3) + b"\x00" + digest_info
    return pow(int.from_bytes(padded, "big"), exponent, modulus).to_bytes(size, "big")


class GoogleToken:
    """Gives the access token for Firebase Cloud Messaging, asking Google for a new one when it is about to expire."""

    SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

    def __init__(self, key_file: str) -> None:
        with open(key_file, "r", encoding="utf-8") as handle:
            account = json.load(handle)
        for needed in ("client_email", "private_key"):
            if not account.get(needed):
                raise ValueError("the key file has no '%s': is it the right file?" % needed)
        self.email = account["client_email"]
        self.project_id = account.get("project_id", "")
        self.token_uri = account.get("token_uri") or "https://oauth2.googleapis.com/token"
        self._numbers = rsa_private_numbers(account["private_key"])
        self._token = ""
        self._expires = 0.0
        self._lock = threading.Lock()

    def _assertion(self, now: float) -> str:
        header = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
        claims = b64url(json.dumps({"iss": self.email, "scope": self.SCOPE, "aud": self.token_uri, "iat": int(now), "exp": int(now) + 3600}, separators=(",", ":")).encode())
        signing_input = (header + "." + claims).encode("ascii")
        return header + "." + claims + "." + b64url(rs256_sign(signing_input, *self._numbers))

    def get(self, force: bool = False) -> str:
        with self._lock:
            now = time.time()
            if force or not self._token or now >= self._expires - 120:
                body = {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": self._assertion(now)}
                status, answer = http_json(self.token_uri, "POST", body, timeout=15, form=True)
                if status != 200 or not isinstance(answer, dict) or not answer.get("access_token"):
                    detail = answer.get("error_description") or answer.get("error") if isinstance(answer, dict) else answer
                    raise SendError("Google did not accept the key (%s: %s)" % (status, detail), retry=status >= 500 or status == 429)
                self._token = answer["access_token"]
                self._expires = now + float(answer.get("expires_in") or 3000)
            return self._token


# ---------------------------------------------------------------------------------------------------------------------
# Sending (Firebase Cloud Messaging HTTP v1)
# ---------------------------------------------------------------------------------------------------------------------

class SendError(Exception):
    def __init__(self, message: str, retry: bool = True) -> None:
        super().__init__(message)
        self.retry = retry


def build_message(config: Dict[str, Any], notice: Notice) -> Dict[str, Any]:
    """The FCM message: a notification the phone shows by itself (also with the app closed), on the right channel."""
    return {
        "message": {
            "topic": config["topic"],
            "notification": {"title": config["title"], "body": notice.text},
            "data": {"type": notice.kind},
            "android": {
                "priority": "HIGH",
                "ttl": "%ds" % int(config["message_ttl_seconds"]),
                "collapse_key": notice.kind,
                "notification": {
                    "channel_id": KIND_CHANNEL.get(notice.kind, "avvisi"),
                    "tag": notice.kind,
                    "sound": "default",
                    "notification_priority": "PRIORITY_HIGH",
                    "visibility": "PUBLIC",
                },
            },
        }
    }


class FcmSender:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.token = GoogleToken(config["service_account_file"])
        self.project = config["project_id"] or self.token.project_id
        if not self.project:
            raise ValueError("the Firebase project name (project_id) is missing")
        if not config["topic"]:
            raise ValueError("the configuration file has no 'topic'")
        self.url = config["fcm_url"].format(project=self.project)

    def send(self, notice: Notice) -> None:
        payload = build_message(self.config, notice)
        for attempt in (1, 2):
            try:
                status, answer = http_json(self.url, "POST", payload, {"Authorization": "Bearer " + self.token.get(force=attempt == 2)}, timeout=20)
            except OSError as error:
                raise SendError("network not reachable (%s)" % error)
            if status == 200:
                return
            if status == 401 and attempt == 1:
                continue  # the token was refused: ask for a new one and try again
            detail = ""
            if isinstance(answer, dict):
                detail = (answer.get("error") or {}).get("message", "") if isinstance(answer.get("error"), dict) else str(answer)
            retry = status in (429, 500, 502, 503, 504)
            raise SendError("Firebase ha risposto %s: %s" % (status, detail or answer), retry=retry)


class Outbox:
    """Sends notices in the background, so a slow or missing internet never stops the watching; retries for a while."""

    def __init__(self, send: Callable[[Notice], None], give_up_seconds: float, dry_run: bool = False) -> None:
        self._send = send
        self.retry_first = 5.0
        self.give_up = give_up_seconds
        self.dry_run = dry_run
        self.queue: "queue.Queue[Tuple[Notice, float]]" = queue.Queue()
        self.pending = 0  # queued or being sent
        self._count = threading.Lock()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="outbox", daemon=True)
        self.sent: List[Notice] = []  # for tests and the log

    def start(self) -> None:
        self.thread.start()

    def put(self, notice: Notice) -> None:
        LOG.info("Notification: [%s] %s", notice.kind, notice.text)
        with self._count:
            self.pending += 1
        self.queue.put((notice, time.time()))

    def _done(self) -> None:
        with self._count:
            self.pending -= 1

    def _run(self) -> None:
        while not self.stop.is_set():
            try:
                notice, created = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._deliver(notice, created)
            finally:
                with self._count:
                    self.pending -= 1

    def _deliver(self, notice: Notice, created: float) -> None:
        """One notice: sent, or retried (5 s, 10 s ... up to 60 s) until it goes or it is too old."""
        delay = self.retry_first
        while not self.stop.is_set():
            try:
                if self.dry_run:
                    LOG.info("(dry run, not sent) %s", notice.text)
                else:
                    self._send(notice)
                    LOG.info("Sent: %s", notice.text)
                self.sent.append(notice)
                return
            except SendError as error:
                if not error.retry or time.time() - created > self.give_up:
                    LOG.error("Notification NOT sent (%s): %s", notice.text, error)
                    return
                LOG.warning("Sending failed (%s): retrying in %d s", error, delay)
                self.stop.wait(delay)
                delay = min(delay * 2, 60.0)
            except Exception as error:  # a bug must not kill the sender
                LOG.exception("Unexpected error while sending: %s", error)
                return

    def drain(self, timeout: float = 30.0) -> bool:
        """Waits until everything queued has been handled (tests); False if it did not finish in time."""
        end = time.time() + timeout
        while time.time() < end:
            with self._count:
                if self.pending == 0:
                    return True
            time.sleep(0.02)
        return False


# ---------------------------------------------------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------------------------------------------------

class Worker:
    """Does the slow things (pausing, cancelling, telling the dashboard) in the background: a macro that takes a minute never stops the watching."""

    def __init__(self) -> None:
        self.queue: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="worker", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def submit(self, job: Callable[[], None]) -> None:
        self.queue.put(job)

    def _run(self) -> None:
        while not self.stop.is_set():
            try:
                job = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                job()
            except Exception as error:  # a bug must not kill the worker
                LOG.exception("Unexpected error: %s", error)


class SelfWatch:
    """Tells when the program's own file has been replaced (an update): `changed()` is true once the new file is complete and valid."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.signature = self._signature()
        self.warned: Any = None

    def _signature(self) -> Optional[Tuple[int, int, int]]:
        try:
            info = os.stat(self.path)
            return (info.st_mtime_ns, info.st_size, info.st_ino)
        except OSError:
            return None

    def changed(self) -> bool:
        now = self._signature()
        if now is None or self.signature is None or now == self.signature:
            return False
        try:  # a file half written, or broken, must not stop a service that works: keep running and look again later
            with open(self.path, "r", encoding="utf-8") as handle:
                compile(handle.read(), self.path, "exec")
        except (OSError, SyntaxError, ValueError) as error:
            if self.warned != now:
                self.warned = now
                LOG.error("The file %s changed but is not valid (%s): going on with the one in use", self.path, error)
            return False
        return True


def run(config: Dict[str, Any], dry_run: bool, stop: threading.Event, outbox_sender: Optional[Callable[[Notice], None]] = None, watch_file: Optional[str] = None) -> Outbox:
    sender = outbox_sender
    if sender is None and not dry_run:
        sender = FcmSender(config).send
    outbox = Outbox(sender or (lambda notice: None), float(config["retry_give_up_seconds"]), dry_run)
    outbox.retry_first = float(config["retry_seconds"])
    outbox.start()
    worker = Worker()
    worker.start()
    watcher = Watcher(config)
    reader = PrinterReader(config)
    LOG.info("KlippEye notifier %s started (Moonraker %s, backend %s)%s", __version__, config["moonraker_url"], config["brain_url"], " [DRY RUN: sends nothing]" if dry_run else "")
    poll = float(config["poll_seconds"])
    heartbeat = float(config["heartbeat_seconds"])
    selfwatch = SelfWatch(watch_file) if watch_file else None
    reported: Tuple[Any, Any] = (None, None)
    reported_at = float("-inf")

    def do(action: Action) -> None:
        if dry_run:
            LOG.info("(dry run, not done) automatic action: %s", action.kind)
            watcher.report_action(action.kind, True)
            return
        LOG.info("Azione automatica: %s", action.kind)
        watcher.report_action(action.kind, reader.act(action.kind))

    try:
        while not stop.is_set():
            started = time.time()
            try:
                for notice in watcher.step(reader.snapshot(started), started):
                    outbox.put(notice)
                for action in watcher.take_actions():
                    worker.submit(lambda action=action: do(action))
                # tell the dashboard the service is alive: when something it shows changed, and every `heartbeat` seconds
                state = (watcher.dash["stamp"], json.dumps(watcher.last_action, sort_keys=True))
                if not dry_run and (state != reported or started - reported_at >= heartbeat):
                    reported, reported_at = state, started
                    payload = {"version": __version__, "seen": int(time.time()), "applied": watcher.dash["stamp"], "lastAction": watcher.last_action}
                    worker.submit(lambda payload=payload: reader.write_status(payload))
            except Exception as error:  # keep watching whatever happens
                LOG.exception("Error while checking: %s", error)
            if selfwatch is not None and selfwatch.changed():
                LOG.info("The program was updated (%s): stopping, systemd starts the new version", selfwatch.path)
                stop.set()
            stop.wait(max(0.2, poll - (time.time() - started)))
    finally:
        outbox.stop.set()
        worker.stop.set()
    return outbox


def command_check(config: Dict[str, Any]) -> int:
    problems = 0

    def report(ok: bool, good: str, bad: str, required: bool = True) -> None:
        nonlocal problems
        print(("  OK      " if ok else ("  ERROR   " if required else "  WARNING ")) + (good if ok else bad))
        if not ok and required:
            problems += 1

    print("Checking the KlippEye notifier %s" % __version__)
    token: Optional[GoogleToken] = None
    try:
        token = GoogleToken(config["service_account_file"])
        report(True, "Firebase key found (project: %s)" % (config["project_id"] or token.project_id), "")
    except (OSError, ValueError) as error:
        report(False, "", "Firebase key not usable: %s (file: %s)" % (error, config["service_account_file"]))
    report(bool(config["topic"]), "Topic set: %s" % config["topic"], "notifier.json has no \"topic\" (it must be the same as the app's)")
    try:
        status, info = http_json(config["moonraker_url"].rstrip("/") + "/printer/info")
        ok = status == 200 and isinstance(info, dict)
        report(ok, "Moonraker reached (Klipper: %s)" % (info.get("result") or {}).get("state") if ok else "", "Moonraker does not answer at %s (answer %s)" % (config["moonraker_url"], status))
    except OSError as error:
        report(False, "", "Moonraker not reachable at %s (%s). Check \"moonraker_url\"" % (config["moonraker_url"], error))
    try:
        status, response = http_json(config["brain_url"].rstrip("/") + "/api/print/last_analysis", headers=brain_headers(config))
        report(status == 200, "Backend reached (AI analysis)", "The backend answers %s at %s: the AI alerts will not arrive" % (status, config["brain_url"]), required=False)
    except OSError as error:
        report(False, "", "Backend not reachable at %s (%s): the AI alerts will not arrive" % (config["brain_url"], error), required=False)
    try:
        status, answer = http_json("%s/server/database/item?namespace=%s&key=settings" % (config["moonraker_url"].rstrip("/"), DASH_NAMESPACE))
        if status == 404:
            status, answer = http_json("%s/server/database/item?namespace=%s&key=settings" % (config["moonraker_url"].rstrip("/"), DASH_NAMESPACE_LEGACY))
        if status == 200 and isinstance(answer, dict):
            chosen = dash_settings((answer.get("result") or {}).get("value"))
            off = sorted(name for name, value in chosen["events"].items() if not value)
            report(True, "Dashboard settings read (notifications off: %s; language: %s; automatic pause: %s; automatic cancel: %s)"
                   % (", ".join(off) or "none", chosen["language"] or "not chosen yet", "yes" if chosen["ai"]["auto_pause"] else "no", "yes" if chosen["ai"]["auto_cancel"] else "no"), "")
        elif status == 404:
            report(True, "Dashboard settings: not saved from the menu yet (notifier.json applies, automatic actions off)", "")
        else:
            report(False, "", "Moonraker's database answers %s: the choices of the dashboard menu will not arrive" % status, required=False)
    except OSError:
        pass  # Moonraker's own problem is reported above
    if token is not None:
        try:
            token.get(force=True)
            report(True, "Google sign-in works (internet works and the key is valid)", "")
        except SendError as error:
            report(False, "", "Google sign-in failed: %s. Check internet and that the Raspberry's date and time are right" % error)
        except OSError as error:
            report(False, "", "Google not reachable (%s): does the Raspberry have internet?" % error)
    print("All good." if problems == 0 else "%d problem(s) to fix." % problems)
    return 0 if problems == 0 else 1


def dashboard_language(config: Dict[str, Any]) -> Optional[str]:
    """The notification language chosen in the dashboard, read once from Moonraker's database (None if not known)."""
    for namespace in (DASH_NAMESPACE, DASH_NAMESPACE_LEGACY):
        try:
            status, answer = http_json("%s/server/database/item?namespace=%s&key=settings" % (config["moonraker_url"].rstrip("/"), namespace))
        except OSError:
            return None
        if status == 200 and isinstance(answer, dict):
            return dash_settings((answer.get("result") or {}).get("value"))["language"]
    return None


def command_test(config: Dict[str, Any]) -> int:
    try:
        sender = FcmSender(config)
        sender.send(Notice("test", message_text(config, dashboard_language(config), "test")))
    except (OSError, ValueError, SendError) as error:
        print("Test notification NOT sent: %s" % error)
        return 1
    print("Test notification handed to Google. It should appear on the phone within a few seconds.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="KlippEye push notifications")
    parser.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "notifier.json"))
    parser.add_argument("--check", action="store_true", help="check the configuration and the connections")
    parser.add_argument("--test", action="store_true", help="send a test notification")
    parser.add_argument("--dry-run", action="store_true", help="watch, but print the notifications instead of sending them")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S", stream=sys.stdout)
    try:
        config = load_config(args.config)
    except (OSError, ValueError) as error:
        print("Cannot read %s: %s" % (args.config, error))
        return 2
    if args.check:
        return command_check(config)
    if args.test:
        return command_test(config)
    stop = threading.Event()
    for name in ("SIGINT", "SIGTERM"):
        signal.signal(getattr(signal, name), lambda *_: stop.set())
    try:
        run(config, args.dry_run, stop, watch_file=os.path.abspath(__file__))
    except (OSError, ValueError) as error:
        print("Cannot start: %s" % error)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
