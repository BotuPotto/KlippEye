"""
KlippEye backend - serves the dashboard (Flask), runs the AI print monitor (OpenCV) and bridges to Moonraker.

Part of the KlippEye project (folder ~/klippeye, see README.md): this file is in backend/, the dashboard in frontend/, the
release in VERSION. It grew out of the "V18" backend of the VzBot days (real data and commands, camera, ZeroTier, fixes for
Groq's 404 and 413) with what release 1.0 and later added:

  * the AI monitor thresholds (sensitivity, how many anomalies, how often, start after N seconds, watched area...) are
    settings: read and changed through /api/backend/config (the dashboard has the menu) and saved in
    <data folder>/monitor.json. A missing or damaged file means "default values": it never stops the start;
  * /api/version tells the release, the interface level (API_LEVEL) and the commit; the release comes from VERSION;
  * the data folder (default ~/printer_data/klippeye, changed with KLIPPEYE_DATA)
    keeps what belongs to the Raspberry and not to the code: settings, AI key (mode 600), notifications. Code updates
    (Moonraker's update manager) never touch it;
  * the bridge to Moonraker waits up to 10 minutes for long operations (/machine/update/...) instead of 10 seconds;
  * the Android app: the APK built by GitHub reaches the repository's apk/ folder with the KlippEye update and the backend
    offers it to the phone (/api/app/version says which version, /app/KlippEye.apk is the file);
  * texts for people are in English and translated with the dashboard's dictionaries (bt()).
"""
from flask import Flask, request, Response, jsonify, send_file
import gzip
try:  # optional since 1.2.0: only needed with KLIPPEYE_CORS (development)
    from flask_cors import CORS
except ImportError:
    CORS = None
import requests
import os
import re
import sys
import json
import math
import copy
import hashlib
import time
import tempfile
import shutil
import threading
import subprocess
import urllib.parse

app = Flask(__name__)
# CORS: no longer open to every site (1.2.0). The dashboard and the app talk to the backend from its own origin; see ACCESS.

MOONRAKER_URL = "http://127.0.0.1:7125"
CAMERA_NGINX_URL = "http://127.0.0.1/webcam"
PORT = int(os.environ.get("KLIPPEYE_PORT") or 8085)  # always 8085 (the variable is for the tests only)

# === BASE: release, data folder, saved settings ===========================================
BRAIN_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BRAIN_DIR)  # ~/klippeye: the repository folder (backend/, frontend/, VERSION...)
API_LEVEL = 2  # goes up when the "language" between backend and dashboard changes (the dashboard says which one it needs)
START_TS = time.time()


def _read_release():
    """The release is written in VERSION (next to backend/, frontend/...). Without the file (backend copied alone): 'sviluppo' (development)."""
    try:
        with open(os.path.join(REPO_DIR, "VERSION"), encoding="utf-8") as f:
            value = f.read().strip()
        if re.fullmatch(r"[0-9A-Za-z.+_-]{1,32}", value):
            return value
    except OSError:
        pass
    return "sviluppo"


RELEASE = _read_release()


def _default_data_dir():
    chosen = (os.environ.get("KLIPPEYE_DATA") or "").strip()
    if chosen:
        return os.path.abspath(os.path.expanduser(chosen))
    home = os.path.expanduser("~")
    if os.path.isdir(os.path.join(home, "printer_data")):
        return os.path.join(home, "printer_data", "klippeye")
    return os.path.join(home, "klippeye_data")


DATA_DIR = _default_data_dir()


def _migrate_data_names():
    """Release 1.3.0 gives the files in the data folder English names: the old ones are renamed once (nothing is lost)."""
    renames = [("brain.json", "monitor.json"), ("allarmi", "alerts"), (os.path.join("alerts", "storico.jsonl"), os.path.join("alerts", "history.jsonl"))]
    for old, new in renames:
        old_path, new_path = os.path.join(DATA_DIR, old), os.path.join(DATA_DIR, new)
        try:
            if os.path.exists(old_path) and not os.path.exists(new_path):
                os.replace(old_path, new_path)
                print("[DATA] renamed %s -> %s" % (old, new))
        except OSError as error:
            print("[DATA] cannot rename %s -> %s: %s" % (old, new, error))


_migrate_data_names()


def _adopt_old_files():
    """Before release 1.0 the AI key and the chosen calibrations lived in the home folder: copied once into the data folder."""
    home = os.path.expanduser("~")
    for olds, new in ((["vzbot_ai_config.json"], "ai.json"),
                      ([os.path.join("printer_data", "config", "vzbot_calibration_selected.json"), "vzbot_calibration_selected.json"], "calibration_selected.json")):
        new_path = os.path.join(DATA_DIR, new)
        for old in olds:
            old_path = os.path.join(home, old)
            try:
                if os.path.isfile(old_path) and not os.path.exists(new_path):
                    os.makedirs(DATA_DIR, exist_ok=True)
                    shutil.copy2(old_path, new_path)
                    os.chmod(new_path, 0o600)
                    print("[DATA] copied %s -> %s" % (old_path, new_path))
            except OSError as error:
                print("[DATA] cannot copy %s: %s" % (old_path, error))


_adopt_old_files()
MONITOR_CONFIG_PATH = os.path.join(DATA_DIR, "monitor.json")   # the AI monitor thresholds (brain.json before 1.3.0)
BRAIN_CONFIG_PATH = MONITOR_CONFIG_PATH   # old name of the variable, kept for code that still uses it


def write_json_atomic(path, data, private=False):
    """Writes a temporary file and swaps it in: a power cut never leaves half a file."""
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600 if private else 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# === ACCESS (1.2.0): optional password, network checks, permissions of the secrets ===================================
# The Flask-free part lives in backend/access.py (also used by `klippeye password` and `klippeye access`).
# Always on (also without a password), can be turned off with `klippeye access network-checks off`:
#   * host name: answer only when the Raspberry is called by an IP address, a home-network name or a name added by hand
#     (an internet domain that "points" at the Raspberry cannot drive it: protection against DNS rebinding);
#   * origin: a command (POST, PUT, DELETE) sent by a page of another site is refused; so are other-site requests that
#     are not a plain page navigation (Sec-Fetch-Site: cross-site).
# With the password on, a request also needs the session cookie or the internal token of the services on the Raspberry.
sys.path.insert(0, BRAIN_DIR)
import access  # noqa: E402
import hmac as _hmac  # noqa: E402
from flask import redirect as _redirect  # noqa: E402

ACCESS = access.Store(DATA_DIR)
ACCESS_THROTTLE = access.Throttle()
ACCESS_PUBLIC = {"/login", "/api/auth/status", "/api/auth/login", "/api/app/version", "/app/KlippEye.apk"}
ACCESS_CROSS_SITE_OK = ("/app/",)   # the APK may be downloaded from an outside link
_CORS_ORIGINS = [o.strip() for o in (os.environ.get("KLIPPEYE_CORS") or "").split(",") if o.strip()]  # development only
if _CORS_ORIGINS and CORS is not None:
    CORS(app, resources={r"/*": {"origins": _CORS_ORIGINS}})

# Messages of the refusals: English, with the Italian version for Italian browsers (the dashboard shows its own text by "error" code).
ACCESS_TEXT = {
    "en": {
        "host": "KlippEye only answers when called by the Raspberry's IP address or a home-network name. To use the name '%(host)s', run on the Raspberry:  klippeye access host-add %(host)s",
        "origin_cmd": "Command refused: it comes from a page that is not the KlippEye dashboard (%(origin)s).",
        "origin_read": "Request refused: it comes from another site.",
        "login": "Login required: open the dashboard and enter the password.",
        "wait": "Too many wrong attempts: try again in %(seconds)d seconds.",
        "password": "Wrong password.",
        "title": "KlippEye · Login", "lead": "This printer is protected by a password.", "label": "Password", "button": "Log in",
        "hint": "Forgot the password? On the Raspberry: <code>klippeye password remove</code>",
    },
    "it": {
        "host": "KlippEye risponde solo se lo chiami con l'indirizzo IP del Raspberry o con un nome della rete di casa. Per usare il nome '%(host)s' scrivi sul Raspberry:  klippeye access host-add %(host)s",
        "origin_cmd": "Comando rifiutato: arriva da una pagina che non e' la dashboard di KlippEye (%(origin)s).",
        "origin_read": "Richiesta rifiutata: arriva da un altro sito.",
        "login": "Serve l'accesso: apri la dashboard e inserisci la password.",
        "wait": "Troppi tentativi sbagliati: riprova tra %(seconds)d secondi.",
        "password": "Password sbagliata.",
        "title": "KlippEye · Accesso", "lead": "Questa stampante è protetta da una password.", "label": "Password", "button": "Accedi",
        "hint": "Password dimenticata? Sul Raspberry: <code>klippeye password remove</code>",
    },
}


LANGUAGES = ("en", "it")
LANGUAGE_NAMES = {"en": "English", "it": "Italian"}
LANG_COOKIE = "klippeye_lang"  # set by the dashboard: the language it is shown in on that device


def _lang():
    """The language of the person making this request: the dashboard's choice (cookie), else the browser's."""
    try:
        chosen = request.cookies.get(LANG_COOKIE)
        if chosen in LANGUAGES:
            return chosen
        return "it" if (request.accept_languages.best_match(["en", "it"]) or "en") == "it" else "en"
    except Exception:
        return "en"


# Texts for people come in English and are translated with the dashboard's own dictionaries
# (frontend/src/i18n/<lang>.json): one translation for both. frontend/tools/i18n.py check requires every bt() text.
I18N_DIR = os.path.join(REPO_DIR, "frontend", "src", "i18n")
_I18N = {}


def _dictionary(lang):
    if lang not in _I18N:
        try:
            with open(os.path.join(I18N_DIR, lang + ".json"), encoding="utf-8") as handle:
                _I18N[lang] = json.load(handle)
        except (OSError, ValueError):
            _I18N[lang] = {}
    return _I18N[lang]


def btn(text):
    """Marks an English text for the dictionaries without translating it now (bt() translates it later)."""
    return text


def bt(text, lang="en", **values):
    """`text` (English) in `lang`, with {placeholders} filled in."""
    translated = _dictionary(lang).get(text, text) if lang != "en" else text
    for name, value in values.items():
        translated = translated.replace("{" + name + "}", str(value))
    return translated


_SHARED_LANGUAGE = {"value": "en", "at": float("-inf")}


def shared_language():
    """The language chosen for the notifications in the dashboard (shared by every phone): what the AI monitor writes in.
    Read from Moonraker's database at most once a minute; English until a dashboard has saved one."""
    now = time.time()
    if now - _SHARED_LANGUAGE["at"] >= 60:
        _SHARED_LANGUAGE["at"] = now
        try:
            answer = requests.get(MOONRAKER_URL + "/server/database/item?namespace=klippeye&key=settings", timeout=2).json()
            value = ((answer.get("result") or {}).get("value") or {}).get("language")
            if value in LANGUAGES:
                _SHARED_LANGUAGE["value"] = value
        except Exception:
            pass
    return _SHARED_LANGUAGE["value"]


def _text(key, **values):
    return ACCESS_TEXT[_lang()][key] % values if values else ACCESS_TEXT[_lang()][key]


def _secure_data_files():
    """Data folder 700 and secrets 600: files copied by hand with loose permissions are fixed (and logged)."""
    fixed = []
    try:
        if os.path.isdir(DATA_DIR) and os.stat(DATA_DIR).st_mode & 0o077:
            os.chmod(DATA_DIR, 0o700)
            fixed.append(DATA_DIR)
    except OSError:
        pass
    names = ["ai.json", "access.json", "internal.token", "notifier.json", "service-account.json"]
    try:
        with open(os.path.join(DATA_DIR, "notifier.json"), encoding="utf-8") as f:
            key = json.load(f).get("service_account_file")
        if isinstance(key, str) and key:
            names.append(key if os.path.isabs(key) else os.path.join(DATA_DIR, key))
    except (OSError, ValueError, AttributeError):
        pass
    for name in names:
        path = name if os.path.isabs(name) else os.path.join(DATA_DIR, name)
        try:
            if os.path.isfile(path) and os.stat(path).st_mode & 0o077:
                os.chmod(path, 0o600)
                fixed.append(path)
        except OSError:
            pass
    if fixed:
        print("[ACCESS] permissions restricted to the service user: " + ", ".join(fixed))
    return fixed


try:
    ACCESS.load()
    ACCESS.internal_token()
    _secure_data_files()
except Exception as _e:  # a data folder that cannot be written must not stop the dashboard
    print("[ACCESS] settings not available: %s" % _e)


def _access_settings():
    try:
        return ACCESS.load()
    except Exception as e:
        print("[ACCESS] cannot read %s: %s" % (ACCESS.path, e))
        return access.default_settings()


def _is_internal():
    given = request.headers.get(access.HEADER_INTERNAL, "")
    if not given:
        return False
    try:
        return _hmac.compare_digest(given, ACCESS.internal_token())
    except Exception:
        return False


def _logged_in(settings):
    return (not settings.get("enabled")) or _is_internal() or access.token_valid(settings, request.cookies.get(access.COOKIE_NAME))


def _refuse(status, code, message):
    response = jsonify({"ok": False, "error": code, "message": message})
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    if code == "login":
        response.headers["X-KlippEye-Login"] = "1"
    return response


@app.before_request
def _access_guard():
    settings = _access_settings()
    internal = _is_internal()
    if settings.get("network_checks", True) and not internal:
        if not access.host_allowed(request.host, settings.get("allowed_hosts")):
            return _refuse(403, "host", _text("host", host=access.split_host(request.host)))
        origin = request.headers.get("Origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin not in _CORS_ORIGINS and not access.origin_matches(origin, request.host):
            return _refuse(403, "origin", _text("origin_cmd", origin=origin[:80]))
        if request.headers.get("Sec-Fetch-Site") == "cross-site" and not request.path.startswith(ACCESS_CROSS_SITE_OK):
            navigation = request.method == "GET" and request.headers.get("Sec-Fetch-Mode") == "navigate"
            if not navigation:
                return _refuse(403, "origin", _text("origin_read"))
    if not settings.get("enabled") or internal or request.path in ACCESS_PUBLIC:
        return None
    if access.token_valid(settings, request.cookies.get(access.COOKIE_NAME)):
        return None
    if request.method == "GET" and request.path == "/":
        return _redirect("/login", code=303)
    return _refuse(401, "login", _text("login"))


def _set_access_cookie(response, settings):
    response.set_cookie(access.COOKIE_NAME, access.make_token(settings), max_age=access.TOKEN_DAYS * 86400, httponly=True,
                        samesite="Strict", secure=request.is_secure, path="/")
    return response


def _check_password_or_wait(settings, password):
    """(ok, error response or None). Slows down whoever tries passwords in a row."""
    ip = request.remote_addr or "?"
    wait = ACCESS_THROTTLE.wait_seconds(ip)
    if wait > 0:
        return False, _refuse(429, "wait", _text("wait", seconds=wait))
    if access.verify_password(settings, password):
        ACCESS_THROTTLE.ok(ip)
        return True, None
    ACCESS_THROTTLE.failed(ip)
    return False, _refuse(401, "password", _text("password"))


LOGIN_PAGE = """<!doctype html><html lang="%(lang)s"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><title>%(title)s</title><style>
:root{--bg:#120e1f;--card:#1d1730;--line:#33294f;--ink:#f1edff;--muted:#a99fcc;--acc:#b79cff;--bad:#ff8a80}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--bg);color:var(--ink);
font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding:16px}
form{width:100%%;max-width:360px;background:var(--card);border:1px solid var(--line);border-radius:24px;padding:28px 22px}
h1{margin:0 0 4px;font-size:24px}h1 span{color:var(--acc)}p{margin:0 0 20px;color:var(--muted);font-size:14px;line-height:1.45}
label{display:block;font-size:13px;color:var(--muted);margin-bottom:6px}
input{width:100%%;font-size:17px;padding:13px 14px;border-radius:14px;border:1px solid var(--line);background:#0d0a17;color:var(--ink)}
input:focus{outline:2px solid var(--acc);outline-offset:1px}
button{width:100%%;margin-top:16px;font-size:16px;font-weight:600;padding:13px;border:0;border-radius:999px;background:var(--acc);color:#1a1033;cursor:pointer}
.err{color:var(--bad);font-size:14px;margin:12px 0 0;min-height:1em}.hint{margin-top:18px;font-size:12px;color:var(--muted)}
code{background:#0d0a17;padding:1px 5px;border-radius:6px}</style></head><body>
<form method="post" action="/login" autocomplete="on"><h1>Klipp<span>Eye</span></h1><p>%(lead)s</p>
<label for="pw">%(label)s</label><input id="pw" name="password" type="password" autocomplete="current-password" autofocus required>
<button type="submit">%(button)s</button><div class="err" role="alert">%(error)s</div>
<div class="hint">%(hint)s</div></form></body></html>"""


def _login_page(error="", status=200):
    from html import escape
    t = ACCESS_TEXT[_lang()]
    page = LOGIN_PAGE % {"lang": _lang(), "title": t["title"], "lead": escape(t["lead"]), "label": t["label"], "button": t["button"],
                         "hint": t["hint"], "error": escape(error)}
    response = Response(page, status=status, mimetype="text/html")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"
    response.headers["Vary"] = "Accept-Language"
    return response


@app.route("/login", methods=["GET", "POST"])
def access_page():
    settings = _access_settings()
    if not settings.get("enabled"):
        return _redirect("/", code=303)
    if request.method == "GET":
        return _redirect("/", code=303) if _logged_in(settings) else _login_page()
    ok, error = _check_password_or_wait(settings, request.form.get("password", ""))
    if not ok:
        return _login_page(error.get_json().get("message", _text("password")), status=error.status_code)
    return _set_access_cookie(_redirect("/", code=303), settings)


@app.route("/api/auth/status", methods=["GET"])
def access_status():
    settings = _access_settings()
    response = jsonify({"ok": True, "enabled": bool(settings.get("enabled")), "logged_in": _logged_in(settings),
                        "network_checks": bool(settings.get("network_checks", True)), "allowed_hosts": list(settings.get("allowed_hosts") or []),
                        "min_length": access.MIN_PASSWORD})
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/auth/login", methods=["POST"])
def access_login():
    settings = _access_settings()
    if not settings.get("enabled"):
        return jsonify({"ok": True, "enabled": False})
    body = request.get_json(silent=True) or {}
    ok, error = _check_password_or_wait(settings, body.get("password", ""))
    if not ok:
        return error
    return _set_access_cookie(jsonify({"ok": True, "enabled": True}), settings)


@app.route("/api/auth/logout", methods=["POST"])
def access_logout():
    response = jsonify({"ok": True})
    response.delete_cookie(access.COOKIE_NAME, path="/")
    return response


@app.route("/api/auth/password", methods=["POST"])
def access_set_password():
    """Turns the password on or changes it (the current one is needed). The device that changes it stays in, the others are logged out."""
    settings = _access_settings()
    body = request.get_json(silent=True) or {}
    new = body.get("new", "")
    problem = access.check_new_password(new)
    if problem:
        return _refuse(400, "weak", problem)
    if settings.get("enabled"):
        ok, error = _check_password_or_wait(settings, body.get("current", ""))
        if not ok:
            return error
    settings = access.set_password(settings, new)
    ACCESS.save(settings)
    print("[ACCESS] password %s from %s" % ("changed" if body.get("current") else "set", request.remote_addr))
    return _set_access_cookie(jsonify({"ok": True, "enabled": True}), settings)


@app.route("/api/auth/disable", methods=["POST"])
def access_disable():
    settings = _access_settings()
    if not settings.get("enabled"):
        return jsonify({"ok": True, "enabled": False})
    ok, error = _check_password_or_wait(settings, (request.get_json(silent=True) or {}).get("current", ""))
    if not ok:
        return error
    ACCESS.save(access.clear_password(settings))
    print("[ACCESS] password removed from %s" % request.remote_addr)
    response = jsonify({"ok": True, "enabled": False})
    response.delete_cookie(access.COOKIE_NAME, path="/")
    return response


@app.route("/api/auth/logout_all", methods=["POST"])
def access_logout_all():
    settings = _access_settings()
    settings["generation"] = int(settings.get("generation") or 1) + 1
    ACCESS.save(settings)
    response = jsonify({"ok": True})
    return _set_access_cookie(response, settings) if settings.get("enabled") else response
# === end ACCESS ========================================================================================================


# The thresholds of the AI monitor. The backend is the only source of the limits: the dashboard draws the menu from this
# list (labels, units, minimums and maximums), so a new threshold appears in the menu without touching the dashboard.
# Labels and help texts are in English; the dashboard shows them in its own language (frontend/src/i18n/*.json).
CONFIG_GROUPS = [
    {"id": "monitor", "title": "Monitor", "note": ""},
    {"id": "rilevamento", "title": "Motion detection",
     "note": "Every few seconds the backend compares the camera picture with the earlier ones: if enough of it changes, and it happens several times, it asks the AI to look at the picture. With the camera calibrated it looks at the whole bed outside the parts; without, only at the outer band of a rectangle."},
    {"id": "filtro", "title": "False alarms",
     "note": "The filter compares the current picture with a «background» made of several pictures of the last minutes (the passing toolhead is not part of it) and counts only the changes that stay for several checks in a row. It also ignores light changes."},
    {"id": "area", "title": "Watched area", "note": "The rectangle where the backend looks for suspicious movement. By default it is the central 60% of the picture. With the camera calibrated and the objects of the print known, the whole bed is watched instead (False alarms → Watch the whole bed)."},
    {"id": "tempi", "title": "Pauses and usage", "note": "The AI analysis uses an online service: these pauses avoid calling it too often."},
    {"id": "avvio", "title": "When it starts checking",
     "note": "During heating, mesh or purge the real print has not started yet: the monitor waits."},
    {"id": "ia", "title": "AI model", "note": ""},
    {"id": "recording", "title": "Recording",
     "note": "While a print runs the backend keeps the pictures the monitor looked at (small, about 30 KB each) with layer, position and score, so that the monitor can be measured afterwards. The oldest prints are deleted when the space is full."},
]

CONFIG_SPEC = [
    {"key": "enabled", "type": "bool", "default": True, "group": "monitor", "label": "Monitor on",
     "help": "When off, the backend does not watch the camera and does not call the AI."},
    {"key": "sensitivity", "type": "int", "default": 35, "min": 5, "max": 100, "step": 1, "unit": "", "group": "rilevamento",
     "label": "Change threshold",
     "help": "How much the brightness of a point must change between two pictures to count as movement. HIGHER = less sensitive (fewer false alarms); lower = more sensitive."},
    {"key": "score_threshold", "type": "float", "default": 2.5, "min": 0.5, "max": 30, "step": 0.5, "decimals": 1, "unit": "%", "group": "rilevamento",
     "label": "Movement at the edges",
     "help": "How much of the outer band of the area must move for the check to be suspicious. Lower = more sensitive."},
    {"key": "trigger_count", "type": "int", "default": 3, "min": 1, "max": 10, "step": 1, "unit": "", "group": "rilevamento",
     "label": "Suspicious checks before the alarm",
     "help": "How many suspicious checks are needed to ask the AI for an analysis. Every normal check takes one away."},
    {"key": "check_interval", "type": "int", "default": 3, "min": 1, "max": 30, "step": 1, "unit": "s", "group": "rilevamento",
     "label": "How often it looks at the camera",
     "help": "Longer = less work for the Raspberry, but a problem is noticed later."},
    {"key": "border", "type": "int", "default": 25, "min": 10, "max": 45, "step": 1, "unit": "%", "group": "rilevamento",
     "label": "Width of the outer band",
     "help": "The movement that counts is the one at the edges of the watched area (spaghetti in the air), not the one in the middle where it prints. Measured in % of the area."},
    {"key": "persistent_filter", "type": "bool", "default": True, "group": "filtro", "label": "Ignore passing movements (recommended)",
     "help": "On: only what changes and stays counts (spaghetti, part come off); the passing toolhead, shadows and light changes do not trigger the alarm. Off: the older detection (a movement at the edges is enough)."},
    {"key": "machine_masks", "type": "bool", "default": True, "group": "filtro", "label": "Leave out the toolhead and the gantry",
     "help": "With a good camera calibration (Settings → Camera calibration) the monitor knows where the toolhead and the gantry are at every check and does not look there. Without a calibration, or when the camera has moved, it has no effect."},
    {"key": "expected_zone", "type": "bool", "default": True, "group": "filtro", "label": "Watch the whole bed, except where the parts are",
     "help": "With a good camera calibration the monitor knows where the objects of the print are (from Klipper's exclude_object or from the G-code) and watches the whole bed around them, not only the edges of the watched area: plastic that appears where no part should be counts. Without a calibration it has no effect."},
    {"key": "persist_checks", "type": "int", "default": 3, "min": 2, "max": 6, "step": 1, "unit": "", "group": "filtro",
     "label": "Checks in a row the change must stay for",
     "help": "Higher = fewer false alarms but a problem is noticed a few seconds later (checks × interval)."},
    {"key": "reference_seconds", "type": "int", "default": 60, "min": 20, "max": 300, "step": 10, "unit": "s", "group": "filtro",
     "label": "Time covered by the background",
     "help": "The background is made from the pictures of the last N seconds. Longer = the toolhead and slow movements weigh less, but a long-lasting problem is «absorbed» later."},
    {"key": "global_change", "type": "float", "default": 30, "min": 5, "max": 100, "step": 5, "decimals": 0, "unit": "%", "group": "filtro",
     "label": "Light change: ignore if more than this changes",
     "help": "If more than this part of the whole picture changes at once (light on or off, camera moved, toolhead right in front of the lens) the check is ignored. If it lasts more than about thirty seconds it counts as a real change."},
    {"key": "ai_min_confidence", "type": "int", "default": 70, "min": 30, "max": 95, "step": 5, "unit": "%", "group": "ia",
     "label": "Minimum AI confidence to report a problem",
     "help": "The only confidence threshold of KlippEye. If the AI suggests PAUSE or CANCEL but no defect reaches it, the verdict becomes CONTINUE (it stays written in the history, in orange). Higher = fewer false alarms but a real failure may be let through: above 85% the AI rarely stops a print."},
    {"key": "ai_send_reference", "type": "bool", "default": True, "group": "ia", "label": "Also send the earlier picture to the AI",
     "help": "The AI sees «before» and «now» and judges whether something serious changed: it makes fewer mistakes. It uses more data per call; if the service refuses two pictures, it sends one."},
    {"key": "roi", "type": "area", "default": [20, 20, 60, 60], "group": "area", "label": "Watched area",
     "help": "Left, top, width and height in % of the picture."},
    {"key": "cooldown", "type": "int", "default": 90, "min": 10, "max": 3600, "step": 10, "unit": "s", "group": "tempi",
     "label": "Pause after an alarm",
     "help": "After an alarm the monitor waits this long before watching again."},
    {"key": "ai_cooldown", "type": "int", "default": 120, "min": 30, "max": 3600, "step": 10, "unit": "s", "group": "tempi",
     "label": "Pause between two AI analyses",
     "help": "Minimum time between two calls to the online service. Longer = less usage and less risk of hitting limits."},
    {"key": "warmup_seconds", "type": "int", "default": 90, "min": 0, "max": 1800, "step": 10, "unit": "s", "group": "avvio",
     "label": "Wait after the print starts",
     "help": "Checking starts only after these seconds of printing (heating, mesh and purge do not count)."},
    {"key": "min_progress", "type": "float", "default": 2, "min": 0, "max": 20, "step": 0.5, "decimals": 1, "unit": "%", "group": "avvio",
     "label": "Minimum progress",
     "help": "Checking starts only when the print has progressed at least this much."},
    {"key": "hotend_tolerance", "type": "int", "default": 8, "min": 2, "max": 50, "step": 1, "unit": "°C", "group": "avvio",
     "label": "Maximum nozzle deviation",
     "help": "If the nozzle is further than this from its target temperature, the real print has not started yet."},
    {"key": "record", "type": "bool", "default": False, "group": "recording", "label": "Record the prints",
     "help": "Keeps the monitor's pictures of every print in the data folder: with them you mark the alarms and measure how many are false (Settings → Recordings)."},
    {"key": "record_max_mb", "type": "int", "default": 2000, "min": 200, "max": 50000, "step": 100, "unit": "MB", "group": "recording",
     "label": "Space for the recordings",
     "help": "A four-hour print takes about 150 MB. Over this limit the oldest prints are deleted; with less than 1 GB free on the disk nothing is recorded."},
    {"key": "ai_model", "type": "text", "default": "", "maxlen": 80, "pattern": r"[A-Za-z0-9._:/@+-]*", "group": "ia",
     "label": "AI model (optional)",
     "help": "Empty = the default of the chosen service. Write it only if the service retires the model (error 404 or 'model not found')."},
]
SPEC_BY_KEY = {spec["key"]: spec for spec in CONFIG_SPEC}


def config_defaults():
    return {spec["key"]: copy.deepcopy(spec["default"]) for spec in CONFIG_SPEC}


def coerce_config_value(spec, raw):
    """Checks a value and brings it to the right form. Raises ValueError with the reason (in English: the dashboard shows it)."""
    kind = spec["type"]
    if kind == "bool":
        if isinstance(raw, bool):
            return raw
        raise ValueError("must be yes or no")
    if kind in ("int", "float"):
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            raise ValueError("must be a number")
        try:
            number = float(raw.strip().replace(",", ".")) if isinstance(raw, str) else float(raw)
        except ValueError:
            raise ValueError("must be a number")
        if not math.isfinite(number):
            raise ValueError("must be a number")
        if kind == "int":
            if abs(number - round(number)) > 1e-9:
                raise ValueError("must be a whole number")
            number = int(round(number))
        else:
            number = round(number, spec.get("decimals", 2))
        if number < spec["min"] or number > spec["max"]:
            raise ValueError("must be between %s and %s" % (spec["min"], spec["max"]))
        return number
    if kind == "text":
        if not isinstance(raw, str):
            raise ValueError("must be a text")
        text = raw.strip()
        if len(text) > spec.get("maxlen", 80) or not re.fullmatch(spec.get("pattern", r"[^\x00-\x1f]*"), text):
            raise ValueError("has characters that are not allowed or is too long")
        return text
    if kind == "area":
        if not isinstance(raw, (list, tuple)) or len(raw) != 4:
            raise ValueError("needs four numbers: left, top, width, height")
        parts = []
        for item in raw:
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
                raise ValueError("needs four numbers: left, top, width, height")
            parts.append(round(float(item), 1))
        x, y, w, h = parts
        if x < 0 or y < 0 or w < 10 or h < 10 or x + w > 100.05 or y + h > 100.05:
            raise ValueError("the area must be inside the picture and at least 10% wide and high")
        return [x, y, w, h]
    raise ValueError("unknown type")


class backendConfig:
    """The thresholds in use and the file where they stay. Everything goes through here, always under the lock."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.values = config_defaults()
        self.saved = False  # there is a file we read or wrote
        self.save_error = ""
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                document = json.load(f)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as error:
            self._set_aside("unreadable (%s)" % error)
            return
        stored = document.get("values") if isinstance(document, dict) and isinstance(document.get("values"), dict) else document
        if not isinstance(stored, dict):
            self._set_aside("is not a list of settings")
            return
        for spec in CONFIG_SPEC:
            if spec["key"] not in stored:
                continue
            try:
                self.values[spec["key"]] = coerce_config_value(spec, stored[spec["key"]])
            except ValueError as error:
                print("[CONFIG] %s: '%s' ignored (%s), using %r" % (self.path, spec["key"], error, self.values[spec["key"]]))
        self.saved = True

    def _set_aside(self, why):
        """A damaged file must not stop the backend: it is set aside (it can be looked at) and the default values are used."""
        target = "%s.damaged-%d" % (self.path, int(time.time()))
        try:
            os.replace(self.path, target)
        except OSError:
            target = "(not moved)"
        print("[CONFIG] %s %s: using the default values. Copy: %s" % (self.path, why, target))

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.values)

    def update(self, changes):
        """Applies `changes` {key: value}. Returns (errors, changed keys); with an error nothing changes."""
        errors, clean = {}, {}
        for key, raw in changes.items():
            spec = SPEC_BY_KEY.get(key)
            if spec is None:
                errors[key] = "unknown setting"
                continue
            try:
                clean[key] = coerce_config_value(spec, raw)
            except ValueError as error:
                errors[key] = str(error)
        if errors:
            return errors, []
        with self.lock:
            changed = [key for key, value in clean.items() if self.values.get(key) != value]
            for key in changed:
                self.values[key] = clean[key]
            if changed or not self.saved:
                self._save()
        return {}, changed

    def reset(self, keys=None):
        defaults = config_defaults()
        wanted = [key for key in (keys if keys else defaults) if key in defaults]
        return self.update({key: defaults[key] for key in wanted})

    def _save(self):
        try:
            write_json_atomic(self.path, {"formato": 1, "values": self.values})
            self.saved, self.save_error = True, ""
        except OSError as error:
            self.save_error = str(error)
            print("[CONFIG] cannot save %s: %s" % (self.path, error))


brain_config = backendConfig(BRAIN_CONFIG_PATH)


def _git_info(_cache={"at": 0.0, "value": None}):
    """Commit and branch of the repository (best effort, remembered for a minute). None when it is not a git repository."""
    now = time.time()
    if now - _cache["at"] < 60 and _cache["at"]:
        return _cache["value"]
    value = None
    try:
        def run(*args):
            return subprocess.run(["git", "-C", REPO_DIR] + list(args), capture_output=True, text=True, timeout=3).stdout.strip()
        commit = run("rev-parse", "--short", "HEAD")
        if commit:
            value = {"commit": commit, "branch": run("rev-parse", "--abbrev-ref", "HEAD")}
    except Exception:
        value = None
    _cache["at"], _cache["value"] = now, value
    return value
# === fine BASE =========================================================================================

# === IMAGE QUALITY CONFIG - V17 ===
AI_IMAGE_WIDTH = 1080
AI_IMAGE_HEIGHT = 720
AI_IMAGE_QUALITY = 85  # jpeg quality
from monitor_core import OPENCV_WIDTH, OPENCV_HEIGHT, REFERENCE_SAMPLES, FrameJudge  # noqa: E402  (the judging part of the monitor)
# V18: everything at 1080x720 - more CPU but the most detail


FRONTEND_CANDIDATES = [
    os.path.join(REPO_DIR, "frontend", "klippeye_frontend.html"),  # ~/klippeye/frontend/
]

def find_frontend():
    for p in FRONTEND_CANDIDATES:
        if os.path.exists(p):
            return p
    return None

# === SELF-REPAIR: after a power loss a program file can be left empty or half written ============================
# scripts/repair.sh compares the files with the "good" copy git keeps on the Raspberry (no internet) and restores only the damaged
# ones. It runs before the backend (ExecStartPre line of the service), when the backend starts (below) and when the dashboard page
# turns out empty or truncated (index). Off when the file <data dir>/no-repair exists.
REPAIR_SCRIPT = os.path.join(REPO_DIR, "scripts", "repair.sh")
REPAIR_MARK_PATH = os.path.join(DATA_DIR, "repair.json")
REPAIR_MARK_LEGACY = os.path.join(DATA_DIR, "ripristino.json")   # name before 1.3.0 (repair.sh renames it)
REPAIR_MIN_GAP = 5  # minimum seconds between two checks started by a damaged page (the emergency page reloads every 8)
_repair_lock = threading.Lock()
_repair_state = {"last": 0.0}


def frontend_ok(path):
    """The dashboard is one HTML file: if it is tiny or does not end with </html> it is empty or truncated (power lost while writing)."""
    try:
        size = os.path.getsize(path)
        if size < 64:
            return False
        with open(path, "rb") as fh:
            fh.seek(max(0, size - 512))
            tail = fh.read()
        return b"</html>" in tail.lower()
    except OSError:
        return False


def run_repair(extra=(), force=False):
    """Runs scripts/repair.sh. True if it ran (not when skipped by the rate limit or because the script is missing)."""
    if not os.path.isfile(REPAIR_SCRIPT):
        return False
    with _repair_lock:
        if not force and time.time() - _repair_state["last"] < REPAIR_MIN_GAP:
            return False
        _repair_state["last"] = time.time()
        try:
            subprocess.run(["bash", REPAIR_SCRIPT, "--quiet", *extra], cwd=REPO_DIR, timeout=90,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           env=dict(os.environ, KLIPPEYE_DATA=DATA_DIR))
            return True
        except Exception as e:
            print(f"[REPAIR] check failed: {e}")
            return False


def read_repair_mark():
    """The last restore: {"time", "restored": [...], "failed": [...]} or None."""
    for path in (REPAIR_MARK_PATH, REPAIR_MARK_LEGACY):
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
            return d if isinstance(d, dict) else None
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            return None
    return None


def _repair_at_startup():
    time.sleep(2)  # first the backend starts listening
    if run_repair(force=True):
        run_repair(("--enable-at-start",), force=True)
        mark = read_repair_mark()
        if mark and time.time() - mark.get("time", 0) < 600:
            print(f"[REPAIR] {time.strftime('%H:%M:%S')} restored: {mark.get('restored')} - failed: {mark.get('failed')}")


EMERGENCY_PAGE = """<!doctype html><html lang="%(lang)s"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="8"><title>KlippEye</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#120d22;color:#e8e1ff;font:16px/1.5 system-ui,sans-serif;text-align:center;padding:24px;box-sizing:border-box}
h1{font-size:20px;margin:0 0 8px}p{margin:6px 0;color:#b9afd6;max-width:420px}</style></head><body><div>
<h1>%(title)s</h1>
<p>%(lead)s</p>
<p>%(hint)s</p></div></body></html>"""


def emergency_page():
    lang = _lang()
    return EMERGENCY_PAGE % {
        "lang": lang,
        "title": bt("KlippEye is putting its files back in order", lang),
        "lead": bt("After a sudden power loss the dashboard page is damaged. It is being restored by itself: this page reloads every few seconds.", lang),
        "hint": bt("If nothing changes, open Mainsail → Machine → Update Manager → klippeye → Recover (hard).", lang),
    }

# The operations Moonraker answers only when the work is done (updates, service restarts): 10 seconds are not enough.
LONG_MOONRAKER_PATHS = ("machine/update/", "machine/services/")

def proxy_moonraker(path):
    try:
        url = f"{MOONRAKER_URL}/{path}"
        if request.query_string:
            url += "?" + request.query_string.decode()
        # forward headers except host
        headers = {k:v for k,v in request.headers if k.lower() not in ['host','content-length','connection']}
        wait = (5, 600) if path.startswith(LONG_MOONRAKER_PATHS) else 10
        r = requests.request(request.method, url, data=request.get_data(), headers=headers, timeout=wait, stream=True)
        # copy content type
        return Response(r.iter_content(chunk_size=8192), status=r.status_code, content_type=r.headers.get('Content-Type','application/json'), headers=dict(r.headers))
    except Exception as e:
        return jsonify({"error": str(e)}), 502

_PAGE_CACHE = {"key": None}


def serve_frontend(path):
    """The dashboard page, gzip-compressed when the browser accepts it (about a quarter of the size: it opens faster on a
    slow network or a phone). Compressed once per file version, with an ETag so an unchanged page is not sent again."""
    st = os.stat(path)
    key = (path, st.st_mtime_ns, st.st_size)
    if _PAGE_CACHE["key"] != key:
        with open(path, "rb") as fh:
            raw = fh.read()
        _PAGE_CACHE.update(key=key, raw=raw, gz=gzip.compress(raw, 6), etag='"%s"' % hashlib.sha256(raw).hexdigest()[:20])
    headers = {"ETag": _PAGE_CACHE["etag"], "Cache-Control": "no-cache", "Vary": "Accept-Encoding"}
    if _PAGE_CACHE["etag"] in [tag.strip() for tag in request.headers.get("If-None-Match", "").split(",")]:
        return Response(status=304, headers=headers)
    if "gzip" in request.headers.get("Accept-Encoding", "").lower():
        headers["Content-Encoding"] = "gzip"
        return Response(_PAGE_CACHE["gz"], mimetype="text/html", headers=headers)
    return Response(_PAGE_CACHE["raw"], mimetype="text/html", headers=headers)


@app.route("/")
def index():
    f = find_frontend()
    if f and not frontend_ok(f):
        ran = run_repair()    # empty or truncated page (power cut): put it back now, before serving it
        f = find_frontend()
        print(f"[REPAIR] {time.strftime('%H:%M:%S')} the page {os.path.basename(str(f))} is damaged: check {'done' if ran else 'skipped (another one just ran)'}")
        if not f or not frontend_ok(f):
            return Response(emergency_page(), status=503, mimetype="text/html", headers={"Retry-After": "8", "Cache-Control": "no-store"})
    if f:
        return serve_frontend(f)
    run_repair()              # missing file: the same
    f = find_frontend()
    if f and frontend_ok(f):
        return serve_frontend(f)
    return "frontend/klippeye_frontend.html not found in " + REPO_DIR, 404

@app.route("/api/health")
def health():
    out = {}
    try:
        r = requests.get(f"{MOONRAKER_URL}/printer/info", timeout=2)
        out["moonraker"] = f"ok ({r.status_code})" if r.ok else f"fail {r.status_code}"
    except Exception as e:
        out["moonraker"] = f"fail {e}"
    try:
        r = requests.get(f"{CAMERA_NGINX_URL}/snapshot", timeout=2, stream=True)
        out["camera_snapshot"] = f"ok ({r.status_code})"
    except Exception as e:
        out["camera_snapshot"] = f"fail {e}"
    try:
        r = requests.get(f"{CAMERA_NGINX_URL}/webrtc", timeout=2)
        out["camera_webrtc"] = f"ok ({r.status_code})"
    except Exception as e:
        out["camera_webrtc"] = f"ok fallback"
    return jsonify(out)

@app.route("/api/printer")
@app.route("/api/status")
def api_printer():
    try:
        url = f"{MOONRAKER_URL}/printer/objects/query?heater_bed&extruder&print_stats&heater_fan&toolhead&gcode_move&virtual_sdcard&display_status&extruder&heater_bed"
        r = requests.get(url, timeout=3)
        data = r.json()
        status = data.get("result", {}).get("status", {})
        info = requests.get(f"{MOONRAKER_URL}/printer/info", timeout=2).json().get("result", {})
        return jsonify({
            "state": info.get("state", "ready"),
            "heater_bed": status.get("heater_bed", {}),
            "extruder": status.get("extruder", {}),
            "print_stats": status.get("print_stats", {}),
            "toolhead": status.get("toolhead", {}),
            "virtual_sdcard": status.get("virtual_sdcard", {}),
            "display_status": status.get("display_status", {}),
            "raw": status
        })
    except Exception as e:
        return jsonify({"error": str(e), "state": "error"}), 500

@app.route("/api/gcode", methods=["POST", "OPTIONS"])
def api_gcode():
    """Takes {script: 'G28'} from the dashboard and sends it to Moonraker's POST /printer/gcode/script"""
    if request.method == "OPTIONS":
        return "", 200
    try:
        body = request.get_json(force=True, silent=True) or {}
        script = body.get("script") or body.get("gcode") or request.data.decode() if request.data else ""
        if not script:
            # also try the query parameter
            script = request.args.get("script", "")
        if not script:
            return jsonify({"error": "no script"}), 400
        # Manda a Moonraker
        mr_url = f"{MOONRAKER_URL}/printer/gcode/script"
        r = requests.post(mr_url, json={"script": script}, timeout=5)
        # Moonraker ritorna result: ok
        try:
            j = r.json()
        except:
            j = {"result": r.text}
        return jsonify({"result": j.get("result", "ok"), "moonraker_status": r.status_code, "sent": script})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Proxy Moonraker standard
@app.route("/printer/<path:path>", methods=["GET","POST","PUT","DELETE"])
@app.route("/server/<path:path>", methods=["GET","POST","PUT","DELETE"])
@app.route("/machine/<path:path>", methods=["GET","POST","PUT","DELETE"])
@app.route("/printer", methods=["GET","POST"])
@app.route("/server", methods=["GET","POST"])
def moonraker_proxy(path=""):
    full = request.path.lstrip("/")
    # gcode/script has its own handler
    return proxy_moonraker(full)

# Proxy Camera via nginx (FIX ZeroTier) - handles /webcam/, /webcam, and /webcam/<path>
@app.route("/webcam/")
@app.route("/webcam")
@app.route("/webcam/<path:path>")
def webcam_proxy(path=""):
    try:
        url = f"{CAMERA_NGINX_URL}/{path}" if path else f"{CAMERA_NGINX_URL}/"
        if request.query_string:
            url += "?" + request.query_string.decode()
        # For MJPEG stream, need stream=True and preserve content type
        r = requests.get(url, timeout=15, stream=True)
        # Copy headers
        headers = {}
        ct = r.headers.get('Content-Type')
        if ct:
            headers['Content-Type'] = ct
        # For MJPEG, it's multipart/x-mixed-replace
        return Response(r.iter_content(chunk_size=8192), status=r.status_code, content_type=r.headers.get('Content-Type'), headers=headers)
    except Exception as e:
        return jsonify({"error": str(e)}), 502











# === MACROS SYSTEM V34 - the V30 method that found ALL the macros + default params ===
import glob as globmod
import re as re_global
import os

# Where the macro files, Shake&Tune and the logs are: asked to Moonraker (its file roots), never a fixed user folder
# (printer_paths.py: any user, several printers, the old ~/klipper_config layout).
import printer_paths  # noqa: E402


def _config_dir():
    return printer_paths.config_dir(MOONRAKER_URL, requests)


def _logs_dir():
    return printer_paths.logs_dir(MOONRAKER_URL, requests)


def _macro_dirs():
    return printer_paths.macro_dirs(MOONRAKER_URL, requests)


def _shaketune_dirs():
    return printer_paths.shaketune_dirs(MOONRAKER_URL, requests)


def extract_params_with_defaults(gcode_text):
    params = []
    default_re = re_global.compile(r'params\.([A-Za-z0-9_]+)[^\n]*?\|\s*default\s*\(\s*([^),\n]+)', re_global.IGNORECASE)
    found_with_default = {}
    for m in default_re.finditer(gcode_text):
        name = m.group(1).upper()
        default_val = m.group(2).strip().strip('"').strip("'")
        found_with_default[name] = default_val
    simple_re = re_global.compile(r'params\.([A-Za-z0-9_]+)', re_global.IGNORECASE)
    seen = set()
    for m in simple_re.finditer(gcode_text):
        name = m.group(1).upper()
        if name not in seen:
            seen.add(name)
            params.append({
                'name': name,
                'default': found_with_default.get(name, ''),
                'type': 'text'
            })
    for p in params:
        d = p['default']
        if d:
            try:
                float(d)
                p['type'] = 'float' if '.' in d else 'int'
            except:
                pass
    return params

def get_files_from_moonraker_config():
    try:
        import requests as req
        r = req.get("http://127.0.0.1:7125/server/files/list?root=config", timeout=3)
        if r.ok:
            data = r.json()
            files = data.get('result', [])
            filtered = []
            for f in files:
                p = f.get('path','').split("/")[-1]
                if p.lower().startswith('printer-') and p.lower().endswith('.cfg'):
                    continue
                if 'crowsnest.conf.' in p.lower() or 'crownest.conf.' in p.lower():
                    continue
                filtered.append(f)
            return filtered, f"ok {len(files)}"
        return [], "fail"
    except Exception as e:
        return [], str(e)

def get_macros_from_moonraker_both():
    macros_map = {}
    status = []
    try:
        import requests as req
        try:
            r = req.get("http://127.0.0.1:7125/printer/objects/query?configfile", timeout=4)
            if r.ok:
                config = r.json().get('result', {}).get('status', {}).get('configfile', {}).get('config', {})
                for key in config.keys():
                    if key.lower().startswith('gcode_macro '):
                        name = key[len('gcode_macro '):].strip()
                        if name.startswith('_'):
                            continue
                        gcode = config[key].get('gcode','')
                        params = extract_params_with_defaults(gcode)
                        macros_map[name] = {
                            "name": name,
                            "file": config[key].get('filename','configfile'),
                            "filepath": config[key].get('filename',''),
                            "description": config[key].get('description',''),
                            "gcode": gcode,
                            "params": params,
                            "has_params": len(params) > 0,
                            "source": "configfile"
                        }
                status.append(f"configfile {len([k for k in config.keys() if k.lower().startswith('gcode_macro ')])}")
        except Exception as e:
            status.append(f"configfile fail {e}")
        try:
            r = req.get("http://127.0.0.1:7125/printer/objects/list", timeout=3)
            if r.ok:
                objs = r.json().get('result', [])
                names = [o[len('gcode_macro '):].strip() for o in objs if o.lower().startswith('gcode_macro ')]
                names = [n for n in names if not n.startswith('_')]
                for name in names:
                    if name not in macros_map:
                        macros_map[name] = {
                            "name": name,
                            "file": "live (Shaketune?)",
                            "filepath": "",
                            "description": "from objects/list (injected live)",
                            "gcode": "",
                            "params": [],
                            "has_params": False,
                            "source": "objects/list"
                        }
                status.append(f"objects/list {len(names)}")
        except Exception as e:
            status.append(f"objects/list fail {e}")
    except Exception as e:
        status.append(f"exception {e}")
    return macros_map, " | ".join(status)

def parse_macros_from_file(filepath):
    macros = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            s = line.strip()
            if s.lower().startswith('[gcode_macro'):
                try:
                    inner = s[1:-1] if s.startswith('[') and s.endswith(']') else s[1:].split(']')[0]
                    parts = inner.split(None, 1)
                    if len(parts) < 2:
                        continue
                    name = parts[1].strip().split(']')[0].strip()
                    if not name or name.startswith('_'):
                        continue
                    sec = ''.join(lines[i+1:i+300])
                    next_sec = sec.find('\n[')
                    if next_sec != -1:
                        sec = sec[:next_sec]
                    params = extract_params_with_defaults(sec)
                    desc_m = re_global.search(r'description\s*:\s*(.+)', sec, re_global.IGNORECASE)
                    desc = desc_m.group(1).strip()[:300] if desc_m else ""
                    macros.append({
                        "name": name,
                        "file": os.path.basename(filepath),
                        "filepath": filepath,
                        "description": desc,
                        "params": params,
                        "has_params": len(params) > 0,
                        "gcode": sec[:1000]
                    })
                except:
                    continue
    except:
        pass
    return macros

def scan_shaketune_folders():
    found = []
    for base in _shaketune_dirs():
        if not os.path.exists(base):
            continue
        for root, dirs, files in os.walk(base):
            for fname in files:
                low = fname.lower()
                if low.endswith('.cfg') or low.endswith('.conf') or low.endswith('.py'):
                    fp = os.path.join(root, fname)
                    try:
                        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read(200000)
                            if 'AXES_SHAPER_CALIBRATION' in content or 'gcode_macro' in content.lower():
                                found.extend(parse_macros_from_file(fp))
                                if 'axes_shaper_calibration' in content.lower():
                                    for name in ['AXES_SHAPER_CALIBRATION','AXES_MAP_CALIBRATION','COMPARE_BELTS_RESPONSES','CREATE_VIBRATIONS_PROFILE','EXCITATE_AXIS_AT_FREQ','MEASURE_AXES_NOISE','BELT_TUNING']:
                                        if name not in [m['name'] for m in found]:
                                            found.append({
                                                "name": name,
                                                "file": os.path.basename(fp),
                                                "filepath": fp,
                                                "description": "Shaketune (from the folder scan)",
                                                "params": [],
                                                "has_params": False,
                                                "gcode": ""
                                            })
                    except:
                        continue
    return found

@app.route("/api/macros/list", methods=["GET"])
def api_macros_list():
    try:
        moon_files, files_status = get_files_from_moonraker_config()
        macros_map, moon_status = get_macros_from_moonraker_both()
        
        base_dir = _config_dir()
        for bd in _macro_dirs():
            if os.path.exists(bd):
                base_dir = bd
                break

        searched_files = []
        all_from_files = []
        files_with_keyword = []
        
        files_to_scan = set()
        for f in moon_files:
            fp = f.get('path','')
            if fp.lower().endswith('.cfg') or fp.lower().endswith('.conf'):
                full = os.path.join(base_dir, fp)
                if os.path.exists(full):
                    files_to_scan.add(full)
        
        for base in _shaketune_dirs():
            if os.path.exists(base):
                for root, dirs, files in os.walk(base):
                    for fname in files:
                        if fname.lower().endswith('.cfg') or fname.lower().endswith('.conf'):
                            files_to_scan.add(os.path.join(root, fname))
        
        if len(files_to_scan) < 10:
            for root, dirs, files in os.walk(base_dir):
                if '.git' in root:
                    continue
                for fname in files:
                    if fname.lower().endswith('.cfg') or fname.lower().endswith('.conf'):
                        files_to_scan.add(os.path.join(root, fname))
        
        for fp in files_to_scan:
            searched_files.append(fp)
            try:
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(200000)
                    if '[gcode_macro' in content.lower():
                        files_with_keyword.append(fp)
                        all_from_files.extend(parse_macros_from_file(fp))
            except:
                continue
        
        for m in all_from_files:
            if m["name"] not in macros_map:
                macros_map[m["name"]] = {
                    "name": m["name"],
                    "file": m["file"],
                    "filepath": m["filepath"],
                    "description": m["description"],
                    "gcode": m.get("gcode",""),
                    "params": m.get("params",[]),
                    "has_params": m.get("has_params", False),
                    "source": "filesystem"
                }
        
        shaketune_macros = scan_shaketune_folders()
        for m in shaketune_macros:
            if m["name"] not in macros_map:
                macros_map[m["name"]] = {
                    "name": m["name"],
                    "file": m["file"],
                    "filepath": m["filepath"],
                    "description": m["description"],
                    "gcode": "",
                    "params": m.get("params",[]),
                    "has_params": m.get("has_params", False),
                    "source": "shaketune_scan"
                }
        
        result = sorted(macros_map.values(), key=lambda x: x["name"].lower())
        
        return jsonify({
            "ok": True,
            "count": len(result),
            "moonraker_status": moon_status,
            "files_list_via_moonraker": len(moon_files),
            "base_dir": base_dir,
            "files_scanned": len(searched_files),
            "files_with_macro_keyword": len(files_with_keyword),
            "shaketune_found": len(shaketune_macros),
            "macros": result
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500

@app.route("/api/macros/run", methods=["POST"])
def api_macros_run():
    try:
        body = request.get_json(force=True, silent=True) or {}
        macro = body.get("macro", "").strip()
        params = body.get("params", {})
        if not macro:
            return jsonify({"error": "macro name required"}), 400
        if params:
            param_str = " ".join([f"{k.upper()}={v}" for k,v in params.items() if str(v).strip()!=""])
            gcode = f"{macro} {param_str}".strip()
        else:
            gcode = macro
        r = requests.post(f"{MOONRAKER_URL}/printer/gcode/script", json={"script": gcode}, timeout=5)
        return jsonify({"ok": True, "sent": gcode, "moonraker_status": r.status_code})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# === CALIBRATION SELECTED SYNC - cross-device ===
import json

# In the data folder (before release 1.0 it was elsewhere: _adopt_old_files() copies it here once).
CALIBRATION_SELECTED_FILE = os.path.join(DATA_DIR, "calibration_selected.json")

def load_calibration_selected():
    for fp in [CALIBRATION_SELECTED_FILE]:
        try:
            if os.path.exists(fp):
                with open(fp, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict) and 'selected' in data:
                        return data['selected']
        except:
            continue
    return []

def save_calibration_selected(selected):
    data = {"selected": selected, "timestamp": __import__('time').time()}
    for fp in [CALIBRATION_SELECTED_FILE]:
        try:
            dir_path = os.path.dirname(fp)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(data, f)
            # write only to the first path that works
            break
        except Exception as e:
            continue
    return True

@app.route("/api/calibration/selected", methods=["GET"])
def api_calibration_selected_get():
    try:
        selected = load_calibration_selected()
        return jsonify({"ok": True, "selected": selected, "count": len(selected)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "selected": []}), 500

@app.route("/api/calibration/selected", methods=["POST"])
def api_calibration_selected_post():
    try:
        body = request.get_json(force=True, silent=True) or {}
        selected = body.get('selected', [])
        if not isinstance(selected, list):
            return jsonify({"ok": False, "error": "selected must be list"}), 400
        # Pulisci
        selected = [str(s).strip() for s in selected if str(s).strip()]
        save_calibration_selected(selected)
        return jsonify({"ok": True, "selected": selected, "count": len(selected)})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500

# === LOGS SYSTEM V27 ===


@app.route("/api/logs/list", methods=["GET"])
def api_logs_list():
    try:
        if not os.path.exists(_logs_dir()):
            return jsonify({"error": f"logs dir not found: {_logs_dir()}", "files": []}), 404
        files = []
        for name in os.listdir(_logs_dir()):
            # ignora *.log.* (vecchi log rotati)
            if ".log." in name:
                continue
            full = os.path.join(_logs_dir(), name)
            if not os.path.isfile(full):
                continue
            try:
                stat = os.stat(full)
                files.append({
                    "name": name,
                    "size": stat.st_size,
                    "size_h": f"{stat.st_size/1024:.1f} KB" if stat.st_size<1024*1024 else f"{stat.st_size/1024/1024:.1f} MB",
                    "modified": int(stat.st_mtime),
                    "modified_str": __import__('datetime').datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m %H:%M")
                })
            except Exception as e:
                files.append({"name": name, "error": str(e)})
        # sort by modified desc (newest first)
        files.sort(key=lambda x: x.get("modified",0), reverse=True)
        return jsonify({"dir": _logs_dir(), "files": files, "count": len(files)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/logs/content", methods=["GET"])
def api_logs_content():
    try:
        fname = request.args.get("file") or request.args.get("name") or ""
        if not fname:
            return jsonify({"error": "file param required"}), 400
        # sicurezza: no path traversal
        if "/" in fname or "\\" in fname or ".." in fname:
            return jsonify({"error": "invalid filename"}), 400
        if ".log." in fname:
            return jsonify({"error": "rotated log not allowed"}), 400
        full = os.path.join(_logs_dir(), fname)
        if not os.path.exists(full):
            return jsonify({"error": "file not found"}), 404
        # read the last N lines
        try:
            max_lines = int(request.args.get("lines", "2000"))
        except:
            max_lines = 2000
        max_lines = max(50, min(max_lines, 10000))
        # read the file efficiently from the end
        try:
            with open(full, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                # take the last max_lines
                if len(lines) > max_lines:
                    lines = lines[-max_lines:]
                content = "".join(lines)
        except Exception as e:
            return jsonify({"error": f"read error: {e}"}), 500
        return jsonify({
            "file": fname,
            "path": full,
            "lines": len(lines),
            "total_lines_approx": len(lines),
            "size": os.path.getsize(full),
            "content": content
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/logs/download", methods=["GET"])
def api_logs_download():
    try:
        fname = request.args.get("file") or ""
        if not fname or "/" in fname or ".." in fname or ".log." in fname:
            return jsonify({"error": "invalid"}), 400
        full = os.path.join(_logs_dir(), fname)
        if not os.path.exists(full):
            return jsonify({"error": "not found"}), 404
        return send_file(full, as_attachment=True, download_name=fname)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === END LOGS ===


# === AUTO AI ANALYSIS V4 - solution B ===
import json

AI_CONFIG_PATH = os.path.join(DATA_DIR, "ai.json")  # release 1.0: in the data folder, mode 600 (it is a password)

def load_ai_config():
    """The AI provider and key ({"provider", "api_key", "model"}), or None when none was entered."""
    try:
        with open(AI_CONFIG_PATH, "r") as f:
            j = json.load(f)
        if "api_key" in j or "key" in j:
            j["api_key"] = j.get("api_key") or j.get("key")
            j["provider"] = j.get("provider", "openai")
            j["model"] = j.get("model", "gpt-4o-mini")
            return j
    except Exception:
        pass
    return None

def get_logs_combined(max_files=25, lines_per_file=400, max_chars=12000):
    """Takes ALL the .log files (not *.log.*), klippy and moonraker first"""
    if not os.path.exists(_logs_dir()):
        return "", []
    files=[]
    try:
        for name in os.listdir(_logs_dir()):
            if ".log." in name:  # esclude rotati tipo klippy.log.2024-10-01
                continue
            if not name.endswith('.log'):
                # files without the .log extension? no, only .log
                # but also .log files with odd prefixes
                if '.log' not in name:
                    continue
            full=os.path.join(_logs_dir(),name)
            if not os.path.isfile(full):
                continue
            try:
                stat=os.stat(full)
                # priority: klippy and moonraker first
                priority = 0
                low = name.lower()
                if 'klippy' in low:
                    priority = 100
                elif 'moonraker' in low and 'telegram' not in low:
                    priority = 90
                elif 'crowsnest' in low:
                    priority = 80
                elif 'mainsail' in low and 'error' in low:
                    priority = 70
                elif 'klipperscreen' in low:
                    priority = 60
                files.append((name,full,stat.st_mtime,stat.st_size,priority))
            except:
                pass
        # sort by priority desc, then by mtime desc
        files.sort(key=lambda x: (x[4], x[2]), reverse=True)
        # take them ALL (max_files is high)
        files=files[:max_files]
    except Exception as e:
        print(f"[LOGS] list error: {e}")
        files=[]
    combined=""
    used=[]
    total_chars=0
    for name,full,mtime,size,priority in files:
        try:
            with open(full,'r',encoding='utf-8',errors='ignore') as f:
                lines=f.readlines()
                # lines by priority - FIX 413: cut down a lot for the Groq TPM limit
                if 'klippy' in name.lower():
                    want_lines = 1200
                    want_chars = 4000
                elif 'moonraker' in name.lower() and 'telegram' not in name.lower():
                    want_lines = 800
                    want_chars = 2500
                elif 'crowsnest' in name.lower() or 'mainsail-error' in name.lower():
                    want_lines = 500
                    want_chars = 1500
                else:
                    want_lines = 300
                    want_chars = 1000

                if len(lines)>want_lines:
                    lines=lines[-want_lines:]
                chunk="".join(lines)
                if len(chunk)>want_chars:
                    chunk=chunk[-want_chars:]
                # an empty file is said so
                if not chunk.strip():
                    chunk="(empty file - 0 bytes of useful content)"

                header=f"\n\n===== FILE: {name} ({len(lines)} lines taken, {size} bytes in total, priority {priority}) =====\n"
                entry=header+chunk
                # controlla se superiamo max_chars totale
                if total_chars+len(entry) > max_chars and 'klippy' not in name.lower() and 'moonraker' not in name.lower():
                    # a file that is not critical is skipped when over the limit,
                    # klippy and moonraker always go in
                    if total_chars > max_chars*0.8:
                        continue
                combined+=entry
                total_chars+=len(entry)
                used.append(name)
        except Exception as e:
            combined+=f"\n\n===== FILE: {name} READ ERROR: {e} =====\n"
            used.append(name)

    # still too long: cut, keeping the start (with the list of files) and the end
    if len(combined)>max_chars:
        # mantieni primi 500 char (lista) + ultimi max_chars-500
        combined = combined[:800] + "\n...[CUT FOR LENGTH, KEEPING THE LAST LOGS]...\n" + combined[-(max_chars-800):]

    print(f"[LOGS] Combinati {len(used)} file: {used} - tot chars {len(combined)}")
    return combined, used

@app.route("/api/ai/config", methods=["GET","POST"])
def api_ai_config():
    try:
        if request.method=="GET":
            cfg=load_ai_config()
            if not cfg:
                return jsonify({"configured": False, "message": bt("No configuration found. Enter the key from the dashboard (Config > System logs > gear) or create {path} with {\"api_key\": \"...\", \"provider\": \"openai\"}", _lang(), path=AI_CONFIG_PATH)})
            # never show the whole key
            safe={"provider":cfg.get("provider"),"model":cfg.get("model"),"key_preview": ("…"+cfg.get("api_key","")[-4:]) if cfg.get("api_key") else "", "configured": True}
            return jsonify(safe)
        else:
            body=request.get_json(force=True,silent=True) or {}
            key=body.get("api_key") or body.get("key") or ""
            if body.get("delete") is True:   # "Delete the key" in the dashboard
                try:
                    os.remove(AI_CONFIG_PATH)
                except FileNotFoundError:
                    pass
                return jsonify({"ok": True, "deleted": True})
            provider=body.get("provider","openai")
            model=body.get("model","gpt-4o-mini")
            if not key or len(key)<20:
                return jsonify({"error": bt("API key too short", _lang())}), 400
            cfg={"provider":provider,"api_key":key,"model":model}
            # release 1.0: one place only (data folder), readable only by the service user
            try:
                write_json_atomic(AI_CONFIG_PATH, cfg, private=True)
            except OSError as e:
                return jsonify({"error": bt("cannot save the key in {path}: {error}", _lang(), path=AI_CONFIG_PATH, error=e)}), 500
            return jsonify({"ok":True,"saved_to":[AI_CONFIG_PATH]})
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.route("/api/logs/analyze", methods=["POST","GET"])
def api_logs_analyze():
    try:
        cfg=load_ai_config()
        if not cfg or not cfg.get("api_key"):
            return jsonify({
                "error": bt("API key not set", _lang()),
                "howto": bt("Enter the key from the dashboard (Config > System logs > gear) or create the file {path} with: {\"api_key\": \"sk-...\", \"provider\": \"openai\", \"model\": \"gpt-4o-mini\"}, or POST {\"api_key\": \"...\"} to /api/ai/config", _lang(), path=AI_CONFIG_PATH),
                "configured": False
            }), 400

        # Supporto singolo file ?file=klippy.log
        single_file = request.args.get('file') or (request.json.get('file') if request.is_json else None)
        is_single = False
        if single_file:
            safe_name = os.path.basename(single_file)
            full = os.path.join(_logs_dir(), safe_name)
            if ".log." in safe_name or not os.path.isfile(full):
                return jsonify({"error": bt("File {name} not found", _lang(), name=safe_name)}), 404
            try:
                with open(full,'r',encoding='utf-8',errors='ignore') as f:
                    lines = f.readlines()
                    want = 3500 if 'klippy' in safe_name.lower() else 2500
                    if len(lines) > want:
                        lines = lines[-want:]
                    content = "".join(lines)[-18000:]
                    if not content.strip():
                        content = "(empty file)"
                combined = f"===== FILE: {safe_name} ({len(lines)} lines, single analysis) =====\n" + content
                used_files = [safe_name]
                is_single = True
            except Exception as e:
                return jsonify({"error": bt("Cannot read {name}: {error}", _lang(), name=safe_name, error=e)}), 500
        else:
            # FIX 413 - cut from 30000 to 12000 characters to stay under Groq's 8000 tokens per minute (gpt-oss-120b)
            # 12000 characters ~ 3000 tokens, leaving room for the prompt
            combined, used_files = get_logs_combined(max_files=20, lines_per_file=400, max_chars=12000)
            if not combined:
                return jsonify({"error": bt("no log found", _lang())}), 404

        language = _lang()
        if is_single:
            prompt = f"""You are an expert in Klipper and Moonraker.
Analyse ONLY this single log file: {used_files[0]}

Content (last lines):
{combined}

Task for a single file:
1) Kind of log and what it records
2) General state of this service
3) Critical errors in THIS file only
4) For each error: cause + immediate fix
5) If there are no errors, say so clearly

Answer in {LANGUAGE_NAMES.get(language, "English")}, short markdown, about this file only.
"""
        else:
            prompt = f"""You are an expert in Klipper, Moonraker and Crowsnest.
Analyse these system logs taken from Klipper's logs folder (all the files, not only klippy.log).

Files included: {', '.join(used_files)}

Content (last lines):
{combined}

Task:
1) Find relevant errors, warnings and stack traces (TMC, heater, probe, MCU, move out of range, crowsnest, moonraker, etc.)
2) Explain the likely cause of each error
3) Suggest concrete fixes: G-code commands, files to check (printer.cfg, etc.), wiring, PID, TMC current, etc.
4) Say whether FIRMWARE_RESTART, a Klipper restart or a hardware check is needed
5) Give priorities: what to fix first
6) End with a short "Conclusion" section

Answer in {LANGUAGE_NAMES.get(language, "English")}, technical but clear, with bullet points and commands ready to copy. If you see no critical errors, say so explicitly.
"""

        provider=cfg.get("provider","openai").lower()
        model=cfg.get("model","gpt-4o-mini")
        api_key=cfg.get("api_key")

        # AI call - openai, meta, groq, together, openrouter, etc. (all OpenAI-compatible)
        provider = provider.lower()
        # Fix: a GPT model saved while using Groq/Meta is corrected automatically
        if provider in ["groq","meta","llama","llama.com","together","openrouter","fireworks"]:
            if model and "gpt-" in model.lower():
                print(f"[AI-FIX] Model {model} not valid for {provider}, using the default Llama")
                model = None

        # Mappa provider -> endpoint base e modello default
        provider_map = {
            "openai": ("https://api.openai.com/v1/chat/completions", model or "gpt-4o-mini"),
            "meta": ("https://api.llama.com/compat/v1/chat/completions", model or "Llama-4-Maverick-17B-128E-Instruct-FP8"),
            "llama": ("https://api.llama.com/compat/v1/chat/completions", model or "Llama-4-Maverick-17B-128E-Instruct-FP8"),
            "llama.com": ("https://api.llama.com/compat/v1/chat/completions", model or "Llama-4-Maverick-17B-128E-Instruct-FP8"),
            "groq": ("https://api.groq.com/openai/v1/chat/completions", model or "openai/gpt-oss-20b"),  # FIX 413: gpt-oss-120b has a TPM of 8000, too low: a model with a higher TPM
            "together": ("https://api.together.xyz/v1/chat/completions", model or "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"),
            "openrouter": ("https://openrouter.ai/api/v1/chat/completions", model or "meta-llama/llama-3.3-70b-instruct"),
            "fireworks": ("https://api.fireworks.ai/inference/v1/chat/completions", model or "accounts/fireworks/models/llama-v3p3-70b-instruct"),
        }
        endpoint, final_model = provider_map.get(provider, (f"https://api.openai.com/v1/chat/completions", model or "gpt-4o-mini"))
        # extra safety: a gpt model with groq becomes llama
        if provider=="groq" and final_model.lower() in ["llama-3.1-8b-instant","llama3-70b-8192","llama3-8b-8192"]:
            final_model="openai/gpt-oss-20b"
        # an old llama on groq becomes the new one
        if provider=="groq" and "gpt-oss" in final_model:
            final_model="openai/gpt-oss-20b"  # FIX 413
        if provider in ["meta","llama"] and "gpt" in final_model.lower():
            final_model="Llama-4-Maverick-17B-128E-Instruct-FP8"


        # the Meta API needs another base_url with api.meta.ai (new)
        if provider in ["meta","llama"] and "api.meta.ai" in endpoint:
            endpoint = "https://api.meta.ai/v1/chat/completions"

        try:
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type":"application/json"}
            # Alcuni provider vogliono extra header
            if provider=="openrouter":
                headers["HTTP-Referer"]="https://klippeye.local"
                headers["X-Title"]="KlippEye Logs Analyzer"

            r=requests.post(endpoint,
                headers=headers,
                json={
                    "model": final_model,
                    "messages":[
                        {"role":"system","content":"You are an expert in Klipper, Moonraker and Crowsnest."},
                        {"role":"user","content":prompt}
                    ],
                    "temperature":0.3,
                    "max_tokens":2000
                },
                timeout=35
            )
            if not r.ok:
                return jsonify({"error": f"{provider} API error {r.status_code}: {r.text[:800]}", "used_files": used_files, "endpoint": endpoint, "model": final_model}), 500
            j=r.json()
            # both choices[0].message.content and other shapes
            try:
                answer=j["choices"][0]["message"]["content"]
            except:
                answer=str(j)[:2000]
            return jsonify({
                "ok": True,
                "provider": provider,
                "model": final_model,
                "endpoint": endpoint,
                "used_files": used_files,
                "prompt_chars": len(prompt),
                "analysis": answer
            })
        except Exception as e:
            return jsonify({"error": f"{provider} call failed: {e}", "used_files": used_files, "endpoint": endpoint}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === END AUTO AI ===



# === OPENCV LIGHTWEIGHT SPAGHETTI DETECTOR V11 - 6-11% CPU (V18 1080p) - OPTIONAL IMPORT ===
import threading
import time
from collections import deque
from monitor_core import HAS_CV2, cv2, np  # noqa: E402
from recorder import Recorder  # noqa: E402  (the pictures of the prints, to measure the monitor)
import print_zone  # noqa: E402  (phase 4c: where the objects of the print are)
if not HAS_CV2:
    print("[OPENCV] cv2/numpy not installed, detector off - install with: sudo apt install python3-opencv")

# --- alert history: what the monitor saw and what the AI said, with the pictures (to see how many were real) ---
ALERT_HISTORY_DIR = os.path.join(DATA_DIR, "alerts")
ALERT_HISTORY_KEEP = 40  # events with pictures
_history_lock = threading.Lock()


def record_alert(event, image_path=None, reference_path=None):
    """Adds an event to <data>/alerts/history.jsonl and copies the pictures next to it. Must never make the monitor fail."""
    try:
        with _history_lock:
            os.makedirs(ALERT_HISTORY_DIR, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            event = dict(event, time=time.strftime("%Y-%m-%d %H:%M:%S"), id=stamp)
            try:
                recorder.attach_alert(event)  # the recording of the print this alarm belongs to, if it is being recorded
            except Exception as error:
                print(f"[RECORDER] alert not linked: {error}")
            for key, path, suffix in (("image", image_path, "now"), ("reference", reference_path, "before")):
                if path and os.path.isfile(path):
                    name = "%s-%s.jpg" % (stamp, suffix)
                    shutil.copyfile(path, os.path.join(ALERT_HISTORY_DIR, name))
                    event[key] = name
            log = os.path.join(ALERT_HISTORY_DIR, "history.jsonl")
            lines = []
            try:
                with open(log, encoding="utf-8") as fh:
                    lines = [l for l in fh.read().splitlines() if l.strip()]
            except OSError:
                pass
            lines.append(json.dumps(event, ensure_ascii=False))
            lines = lines[-ALERT_HISTORY_KEEP:]
            with open(log + ".tmp", "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
            os.replace(log + ".tmp", log)
            keep = set()
            for line in lines:
                try:
                    entry = json.loads(line)
                    keep.update(n for n in (entry.get("image"), entry.get("reference")) if n)
                except ValueError:
                    pass
            for name in os.listdir(ALERT_HISTORY_DIR):
                if name.endswith(".jpg") and name not in keep:
                    try:
                        os.remove(os.path.join(ALERT_HISTORY_DIR, name))
                    except OSError:
                        pass
    except Exception as error:
        print(f"[ALERTS] cannot write the alert history: {error}")


_ALERT_KEYS_1_1 = {"esito": "outcome", "osservazione": "observation", "con_foto_di_prima": "with_reference", "filtro": "filter",
                   "action_originale": "original_action"}   # history written by 1.1.x


def _english_alert(entry):
    if isinstance(entry, dict):
        for old, new in _ALERT_KEYS_1_1.items():
            if old in entry and new not in entry:
                entry[new] = entry.pop(old)
    return entry


def read_alert_history(limit=20):
    try:
        with open(os.path.join(ALERT_HISTORY_DIR, "history.jsonl"), encoding="utf-8") as fh:
            rows = []
            for line in fh.read().splitlines():
                try:
                    rows.append(_english_alert(json.loads(line)))
                except ValueError:
                    pass
        return rows[-limit:][::-1]
    except OSError:
        return []


def prune_alert_images(keep=10, pattern="/tmp/klippeye_alert_*.jpg"):
    """Keeps the last `keep` alert pictures in /tmp and removes the others (each is ~100 KB and they used to pile up)."""
    try:
        import glob
        files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        for old in files[keep:]:
            try:
                os.remove(old)
            except OSError:
                pass
    except Exception:
        pass


AI_DEFECT_KEYS = ("spaghetti", "empty_bed", "layer_shift", "warping")


AI_ACTIONS = ("CONTINUE", "PAUSE", "CANCEL")


def normalize_action(value):
    """The AI's advice as CONTINUE / PAUSE / CANCEL, also when written the Italian way (CONTINUA / PAUSA / CANCELLA,
    releases before 1.6.0 and answers in Italian); "" when there is none."""
    text = str(value or "").upper()
    if "CANCEL" in text:
        return "CANCEL"
    if "PAUS" in text:
        return "PAUSE"
    if "CONTIN" in text or text.strip():
        return "CONTINUE"
    return ""


def build_ai_prompt(score, state, filename, progress, hotend, ref_age=None, language="en"):
    """The text for the AI: neutral (it does not say "it is spaghetti"), it explains what the camera sees, what a defect is
    and what is not, and asks to describe before deciding. The free texts come back in `language`."""
    pictures = ("I am sending TWO pictures: the first is BEFORE (about %d seconds ago), the second is NOW. Compare them: what counts is what changed and stays." % (ref_age or 0)
                if ref_age is not None else "I am sending ONE picture (now).")
    return f"""You are watching a 3D print (a Klipper printer). The camera is fixed, very close and above the bed, in a corner: the print head, its cables and parts of the gantry often appear in the picture.

The local check noticed a change that stays in the picture (score {score}%), but it is usually harmless: print head, the part growing, shadows, reflections. We do NOT know whether there is a problem.

{pictures}

TELEMETRY: state {state}; file {filename}; progress {progress:.1f}%; nozzle {hotend:.0f} C.

REAL PROBLEMS (only if you see them clearly):
- spaghetti: tangled filament or filament detached from the part, strands in the air, a nest on the bed or around the nozzle;
- part detached from the bed, moved or fallen;
- layer shift (the part has a sharp sideways step);
- obvious warping (corners lifted from the bed);
- empty bed ONLY if progress is above 5% and no part can be seen.

NOT PROBLEMS: the print head and its wiring, the gantry, skirt, brim and purge line, supports, visible infill, the part rising layer after layer, reflections, shadows, thin hairs (stringing).

How to proceed: 1) describe in one sentence what you see; 2) report a defect only if it is obvious; when in doubt the answer is CONTINUE. Confidence is the probability in % that the defect is real: below 50 if you are not sure.

Write "observation", "note" and "summary" in {LANGUAGE_NAMES.get(language, "English")}; keep the keys and the action words in English.

Answer ONLY with valid JSON:
{{
  "observation": "what you see, one sentence",
  "spaghetti": {{"detected": true/false, "confidence": 0-100, "note": "detail"}},
  "empty_bed": {{"detected": true/false, "confidence": 0-100}},
  "layer_shift": {{"detected": true/false, "confidence": 0-100}},
  "warping": {{"detected": true/false, "confidence": 0-100}},
  "action": "CONTINUE|PAUSE|CANCEL",
  "summary": "short sentence, at most 20 words"
}}
"""


def apply_min_confidence(parsed, minimum, language="en"):
    """If the AI suggests PAUSE/CANCEL but no defect has the minimum confidence, the verdict becomes CONTINUE (the original
    stays written in "original_action"). -> (verdict, downgraded)"""
    action = normalize_action(parsed.get("action"))
    if minimum <= 0 or action not in ("PAUSE", "CANCEL"):
        return parsed, False
    defects = [v for k, v in parsed.items() if k in AI_DEFECT_KEYS and isinstance(v, dict)]
    if not defects:
        return parsed, False  # an answer without details cannot be filtered
    for d in defects:
        confidence = d.get("confidence")
        if d.get("detected") is True and isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and confidence >= minimum:
            return parsed, False
    out = dict(parsed)
    out["original_action"] = action
    out["action"] = "CONTINUE"
    out["summary"] = bt("No defect is sure enough (threshold {threshold}%).", language, threshold=minimum) + " " + str(parsed.get("summary", ""))
    return out, True


class LightDetector(FrameJudge):
    """The live monitor: a thread that, while a real print runs, takes a camera picture every few seconds, has it judged
    (FrameJudge, monitor_core.py) and on a trigger saves the picture and asks the AI."""

    def __init__(self):
        FrameJudge.__init__(self)
        self.enabled = True  # AUTO-ENABLED
        self.running = False
        self.thread = None
        self.generation = 0  # every start() opens a new one: an old loop still asleep understands by itself that it must end
        self.last_ai_call = 0
        self.last_alert_img_path = None
        self.last_analysis = None  # last AI result, formatted
        self.meta = {}  # what the printer was doing at the last round (layer, position, progress): goes with the recorded picture
        self.next_cool_frame = 0.0
        self.cpu_mark = None  # (wall time, process CPU time) at the start of the current measuring window
        self.check_ms = None
        self.zone = {}  # phase 4c: {"file", "source": "exclude_object" | "gcode" | None, "objects": [...], "why"}
        self.zone_reading = None  # the file whose G-code is being read for the zone
        self._zone_cache = (None, None)  # ((objects id, Z), masks)

    def _measure(self, judge_seconds):
        """How heavy the monitor is: the time of one check (decoding + judging, averaged) and the CPU the whole backend used
        over the last minute, in % of one core. Both go to the status (/api/print/detector/status) and to the recording."""
        ms = judge_seconds * 1000.0
        self.check_ms = ms if self.check_ms is None else self.check_ms * 0.9 + ms * 0.1
        self.stats["check_ms"] = round(self.check_ms, 1)
        now, cpu = time.time(), sum(os.times()[:2])
        if self.cpu_mark is None:
            self.cpu_mark = (now, cpu)
        elif now - self.cpu_mark[0] >= 60:
            self.stats["cpu_percent"] = round(100.0 * (cpu - self.cpu_mark[1]) / (now - self.cpu_mark[0]), 1)
            self.cpu_mark = (now, cpu)
            recorder.note_cpu(self.check_ms, self.stats["cpu_percent"])

    def _record_during_cooldown(self):
        """After an alarm the monitor rests, but the recording goes on (a replay with a shorter pause needs those pictures)."""
        now = time.time()
        if now < self.next_cool_frame or recorder.session is None:
            return
        self.next_cool_frame = now + self.check_interval
        try:
            r = requests.get(f"{CAMERA_NGINX_URL}/snapshot", timeout=4)
            frame = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR) if r.ok and len(r.content) >= 1000 else None
            if frame is not None:
                recorder.add_frame(frame, now, dict(self.meta, score=None, trig=False, cool=True))
        except Exception as error:
            print(f"[RECORDER] picture during the pause not taken: {error}")

    def _uses_calibration(self):
        return (self.machine_masks or self.expected_zone) and camera_cal.usable()

    def _position_now(self, key):
        """Klipper's live position of the toolhead into self.meta[key] (just before / just after the picture)."""
        try:
            status = requests.get(f"{MOONRAKER_URL}/printer/objects/query?motion_report=live_position", timeout=2).json()["result"]["status"]
            live = (status.get("motion_report") or {}).get("live_position") or []
            self.meta[key] = [round(float(v), 1) for v in live[:3]] if len(live) >= 3 else self.meta.get(key)
        except Exception:
            if key == "live2":
                self.meta[key] = None

    def _machine_mask(self):
        """The machine mask of this check (phase 4b): the toolhead and the gantry where they were just before the picture
        and just after it (self.meta["live"], ["live2"]), and on the way between, at the size the monitor looks at.
        None without a usable calibration."""
        self.meta["masked"] = False
        if not self.machine_masks or not camera_cal.usable():
            return None
        try:
            mask = camera_cal.monitor_mask([self.meta.get("live"), self.meta.get("live2")], OPENCV_WIDTH // 2, OPENCV_HEIGHT // 2)
        except Exception as error:
            print(f"[OPENCV] machine mask not made: {error}")
            return None
        self.meta["masked"] = mask is not None
        return mask

    def _update_zone(self, filename, exclude):
        """Where the objects of this print are (phase 4c, print_zone.py): Klipper's exclude_object when the slicer labels
        them, otherwise the G-code of the print, read once in the background."""
        objects = print_zone.objects_from_exclude((exclude or {}).get("objects"))
        if objects:
            if self.zone.get("source") != "exclude_object" or self.zone.get("objects") != objects:
                self.zone = {"file": filename, "source": "exclude_object", "objects": objects}
                recorder.note_zone(self.zone)
            return
        if not filename or self.zone.get("file") == filename or self.zone_reading == filename:
            return
        self.zone_reading = filename

        def read():
            try:
                with requests.get(f"{MOONRAKER_URL}/server/files/gcodes/" + urllib.parse.quote(filename), timeout=60, stream=True) as r:
                    r.raise_for_status()
                    found = print_zone.objects_from_gcode(r.iter_lines(decode_unicode=True))
                zone = {"file": filename, "source": "gcode" if found else None, "objects": found, "why": "" if found else "the G-code extrudes nothing"}
            except Exception as error:
                zone = {"file": filename, "source": None, "objects": [], "why": str(error)[:200]}
            if self.zone_reading == filename:
                self.zone = zone
                self.zone_reading = None
                recorder.note_zone(zone)
                print(f"[OPENCV] expected zone of {filename}: {len(zone['objects'])} object(s) from {zone['source'] or 'nothing'}")
        threading.Thread(target=read, name="print-zone", daemon=True).start()

    def _zone_masks(self):
        """(watched, expected) pictures of this check, or None (the outer band, as before)."""
        self.meta["zone"] = False
        objects = self.zone.get("objects")
        position = self.meta.get("live") or self.meta.get("pos")
        if not self.expected_zone or not objects or not position:
            self.stats["zone"] = None
            return None
        key = (id(objects), round(float(position[2]), 1))
        if self._zone_cache[0] != key:
            try:
                self._zone_cache = (key, camera_cal.zone_masks(objects, float(position[2]), OPENCV_WIDTH // 2, OPENCV_HEIGHT // 2))
            except Exception as error:
                print(f"[OPENCV] expected zone not made: {error}")
                self._zone_cache = (key, None)
        zone = self._zone_cache[1]
        self.meta["zone"] = zone is not None
        self.stats["zone"] = self.zone.get("source") if zone is not None else None
        return zone

    def set_roi(self, x, y, w, h):
        self.roi = (x,y,w,h)

    def start(self):
        if not HAS_CV2:
            print("[OPENCV] Cannot start: cv2 missing")
            return
        if self.running:
            return
        self.enabled = True
        self.running = True
        self.generation += 1
        self.thread = threading.Thread(target=self.loop, args=(self.generation,), daemon=True)
        self.thread.start()
        print("[OPENCV] Light detector started")

    def stop(self):
        self.enabled = False
        self.running = False
        self.generation += 1
        self.stats["status"] = "stopped"
        print("[OPENCV] Light detector stopped")

    def _nap(self, generation, seconds):
        """Sleeps `seconds` but wakes up at once when the detector was stopped or restarted: an old loop does not linger."""
        end = time.time() + seconds
        while time.time() < end and self.running and generation == self.generation:
            time.sleep(min(0.1, max(0.0, end - time.time())))

    def loop(self, generation=None):
        if generation is None:
            generation = self.generation
        while self.running and generation == self.generation:
            try:
                if not HAS_CV2:
                    self.stats["status"] = "cv2 not installed"
                    self._nap(generation, 5)
                    continue
                if not self.enabled:
                    self._nap(generation, 1)
                    continue
                # Cooldown check
                if time.time() < self.cooldown_until:
                    self.stats["status"] = f"cooldown {int(self.cooldown_until - time.time())}s"
                    self._record_during_cooldown()
                    self._nap(generation, 1)
                    continue
                # Check if printing
                # === SOLUTION 5 - HYBRID - IS THE REAL PRINT RUNNING ===
                try:
                    pr = requests.get(f"{MOONRAKER_URL}/printer/objects/query?print_stats&extruder&display_status&virtual_sdcard&toolhead&heater_bed&motion_report=live_position&exclude_object=objects", timeout=3).json()
                    status = pr.get("result",{}).get("status",{})
                    ps = status.get("print_stats",{})
                    extr = status.get("extruder",{})
                    disp = status.get("display_status",{})
                    v_sd = status.get("virtual_sdcard",{})
                    tool = status.get("toolhead",{})
                    bed = status.get("heater_bed",{})
                    state = ps.get("state","")
                    recorder.observe(state, ps.get("filename", ""), time.time(), brain_config.snapshot())
                    camera_cal.maybe_check()  # has the camera moved since its calibration? (every 10 minutes)

                    if state != "printing":
                        self._reset_reference()  # a new print starts with a new background
                        if state not in ("paused",):
                            self.zone, self.zone_reading = {}, None  # the next print has its own objects
                        self.stats["status"] = f"idle (state={state})"
                        self.stats["real_print_started"] = False
                        self.stats["real_print_reason"] = f"state={state}"
                        self._nap(generation, 5)
                        continue

                    # has the real print started?
                    progress = disp.get("progress",0)  # 0-1
                    temp_h = extr.get("temperature",0)
                    target_h = extr.get("target",0)
                    temp_b = bed.get("temperature",0)
                    target_b = bed.get("target",0)
                    file_pos = v_sd.get("file_position",0)
                    file_size = v_sd.get("file_size",1)
                    file_progress = file_pos / file_size if file_size>0 else 0
                    total_dur = ps.get("total_duration",0)

                    # criteria of a real print
                    reasons = []
                    real_started = True

                    # 1. progress above the threshold (2% by default; the file half of that)
                    if progress < self.min_progress/100 and file_progress < self.min_progress/200:
                        real_started = False
                        reasons.append(f"progress {progress*100:.1f}% <{self.min_progress:g}%")
                    # 2. hotend close to its target
                    if target_h > 0 and abs(temp_h - target_h) > self.hotend_tol:
                        real_started = False
                        reasons.append(f"hotend {temp_h:.0f}/{target_h:.0f}C not at temperature")
                    # 3. bed close to its target, if it has one
                    if target_b > 0 and abs(temp_b - target_b) > 10:
                        # the bed does not block, it is only written down
                        reasons.append(f"bed {temp_b:.0f}/{target_b:.0f}C not at temperature")
                    # 4. at least N seconds of printing (90 by default: heating + mesh often take < 60 s)
                    if total_dur < self.warmup:
                        real_started = False
                        reasons.append(f"duration {total_dur:.0f}s <{self.warmup}s")
                    # 5. toolhead Z: still high (>10 mm) probably means mesh/homing
                    try:
                        z_pos = tool.get("position",[0,0,0])[2] if tool.get("position") else 0
                        if z_pos > 15:
                            reasons.append(f"Z={z_pos:.1f}mm high (mesh?)")
                    except:
                        pass

                    self.stats["real_print_started"] = real_started
                    info = ps.get("info") or {}
                    position = tool.get("position") or []
                    live = (status.get("motion_report") or {}).get("live_position") or []
                    self.meta = {"layer": info.get("current_layer"), "layers": info.get("total_layer"),
                                 "pos": [round(float(v), 1) for v in position[:3]] if len(position) >= 3 else None,
                                 "live": [round(float(v), 1) for v in live[:3]] if len(live) >= 3 else None,  # where the toolhead really is (phase 4: masks)
                                 "progress": round(float(progress) * 100, 1)}
                    self.stats["real_print_reason"] = "; ".join(reasons) if reasons else "ok - real print"
                    if self.expected_zone and camera_cal.usable():
                        self._update_zone(ps.get("filename", ""), status.get("exclude_object"))
                    self.stats["progress"] = progress
                    self.stats["file_progress"] = file_progress
                    self.stats["total_duration"] = total_dur

                    if not real_started:
                        self.stats["status"] = f"heating/mesh - waiting for the real print ({'; '.join(reasons)[:80]})"
                        self._nap(generation, 3)
                        continue

                except Exception as e:
                    print(f"[DETECTOR] real_print check err: {e}")
                    self._nap(generation, 3)
                    continue

                # Get snapshot low-res
                try:
                    calibrated = self._uses_calibration()
                    if calibrated:
                        self._position_now("live")  # where the toolhead is right before the picture...
                    r = requests.get(f"{CAMERA_NGINX_URL}/snapshot", timeout=4)
                    if calibrated:
                        self._position_now("live2")  # ...and right after it (it moves while the picture is taken)
                    if not r.ok or len(r.content) < 1000:
                        self._nap(generation, 2)
                        continue
                    decode_started = time.time()
                    img_arr = np.frombuffer(r.content, np.uint8)
                    frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
                    decode_seconds = time.time() - decode_started
                    if frame is None:
                        self._nap(generation, 2)
                        continue
                except Exception as e:
                    print(f"[OPENCV] snapshot fail: {e}")
                    self._nap(generation, 3)
                    continue

                now = time.time()
                ignore = self._machine_mask()
                zone = self._zone_masks()
                score, triggered = self.judge(frame, r.content, now, ignore, zone)
                recorder.add_frame(frame, now, dict(self.meta, score=None if score is None else round(score, 2), trig=triggered))
                self._measure(time.time() - now + decode_seconds)  # decoding, judging and (when on) recording
                if score is None:  # the comparison is not ready yet, or this check is to be ignored (light change)
                    self._nap(generation, self.check_interval)
                    continue

                if triggered:
                    recorder.note_trigger(now)
                    # save a full-resolution picture for the AI
                    try:
                        prune_alert_images(keep=20)  # old alert pictures do not pile up for ever (now + before)
                        full_path = f"/tmp/klippeye_alert_{int(time.time())}.jpg"
                        # download again and resize to 1080x720 for the AI - V17 against false positives
                        r_full = requests.get(f"{CAMERA_NGINX_URL}/snapshot", timeout=5)
                        if r_full.ok:
                            try:
                                # resize to 1080x720, quality 85%, for the detail of the bed
                                img_arr_full = np.frombuffer(r_full.content, np.uint8)
                                frame_full = cv2.imdecode(img_arr_full, cv2.IMREAD_COLOR)
                                if frame_full is not None:
                                    resized = cv2.resize(frame_full, (AI_IMAGE_WIDTH, AI_IMAGE_HEIGHT), interpolation=cv2.INTER_AREA)
                                    cv2.imwrite(full_path, resized, [int(cv2.IMWRITE_JPEG_QUALITY), AI_IMAGE_QUALITY])
                                else:
                                    with open(full_path, 'wb') as f:
                                        f.write(r_full.content)
                            except:
                                with open(full_path, 'wb') as f:
                                    f.write(r_full.content)
                            self.last_alert_img_path = full_path
                            print(f"[OPENCV] Saved alert image {full_path}")
                            # call the AI analysis in the background (the loop does not wait)
                            ref_path, ref_age = self._save_reference(full_path)
                            threading.Thread(target=self.call_ai_analysis, args=(full_path, ref_path, ref_age), daemon=True).start()
                    except Exception as e:
                        print(f"[OPENCV] save alert fail: {e}")

                self._nap(generation, self.check_interval)  # a check every 3 s by default (dashboard: Monitor thresholds > How often it looks at the camera)

            except Exception as e:
                print(f"[OPENCV] loop error: {e}")
                self._nap(generation, 3)

    def _save_reference(self, adesso_path):
        """The "before" picture for the AI: the oldest of the background ones (~reference_seconds ago). -> (path, age in seconds) or (None, None)."""
        if not (self.ai_send_reference and self.persistent_filter and self.ref_jpegs):
            return None, None
        try:
            taken, raw = self.ref_jpegs[0]
            frame = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                return None, None
            path = adesso_path[:-4] + "_prima.jpg"
            resized = cv2.resize(frame, (AI_IMAGE_WIDTH, AI_IMAGE_HEIGHT), interpolation=cv2.INTER_AREA)
            cv2.imwrite(path, resized, [int(cv2.IMWRITE_JPEG_QUALITY), AI_IMAGE_QUALITY])
            return path, int(time.time() - taken)
        except Exception as error:
            print(f"[OPENCV] earlier picture not saved: {error}")
            return None, None

    def call_ai_analysis(self, img_path, ref_path=None, ref_age=None):
        """Asks the AI to look at the picture (and, if there is one, at how it was before) when the monitor triggers, with nobody involved."""
        score = self.stats.get("last_score", 0)
        try:
            now = time.time()
            if now - self.last_ai_call < self.ai_cooldown:
                # the AI is resting (pause between two analyses): this alarm is not lost, the monitor rests until the AI can
                # look again and then checks afresh (before 1.19 the alarm was written as "skipped" and the monitor rested
                # its own pause on top: a real failure could wait three or four minutes for its analysis)
                free_at = min(self.last_ai_call, now) + self.ai_cooldown   # a clock that went back cannot freeze the monitor
                self.cooldown_until = max(self.cooldown_until, free_at)
                print(f"[OPENCV] AI resting, the monitor waits {int(free_at - now)}s and looks again")
                return
            self.last_ai_call = now
            print(f"[OPENCV] calling the AI for {img_path}")

            # read the picture as base64
            if not os.path.exists(img_path):
                print(f"[OPENCV] picture not found {img_path}")
                return
            with open(img_path, 'rb') as f:
                img_b64 = base64.b64encode(f.read()).decode('utf-8')
            ref_b64 = None
            if ref_path and os.path.exists(ref_path):
                with open(ref_path, 'rb') as f:
                    ref_b64 = base64.b64encode(f.read()).decode('utf-8')

            # Telemetria
            telemetry = {}
            try:
                pr = requests.get(f"{MOONRAKER_URL}/printer/objects/query?print_stats&extruder&heater_bed&display_status&virtual_sdcard", timeout=3).json()
                telemetry = pr.get("result",{}).get("status",{})
            except Exception as e:
                telemetry = {}

            print_stats = telemetry.get("print_stats",{})
            display = telemetry.get("display_status",{})
            extruder = telemetry.get("extruder",{})
            state = print_stats.get("state","unknown")
            filename = print_stats.get("filename","")
            progress = display.get("progress",0)*100
            temp_h = extruder.get("temperature",0)

            cfg = load_ai_config()
            if not cfg.get("api_key"):
                print("[OPENCV] No API key for the AI call")
                record_alert({"outcome": "skipped: no AI key", "score": score}, img_path, ref_path)
                return

            provider = cfg.get("provider","groq").lower()
            api_key = cfg.get("api_key")
            endpoint = "https://api.groq.com/openai/v1/chat/completions"
            final_model = "qwen/qwen3.8-27b"
            if provider == "openai":
                endpoint = "https://api.openai.com/v1/chat/completions"
                final_model = "gpt-4o-mini"
            if self.ai_model:  # chosen in the dashboard (Monitor thresholds): wins over the service's default
                final_model = self.ai_model

            headers = {"Authorization": f"Bearer {api_key}", "Content-Type":"application/json"}

            language = shared_language()

            def ask(with_reference):
                prompt = build_ai_prompt(score, state, filename, progress, temp_h, ref_age if with_reference else None, language)
                content = [{"type": "text", "text": prompt}]
                for b64 in ([ref_b64, img_b64] if with_reference else [img_b64]):
                    content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
                payload = {
                    "model": final_model,
                    "messages": [
                        {"role": "system", "content": "You are a careful 3D printing expert: you report a defect only when you see it clearly. Answer ONLY with valid JSON as asked."},
                        {"role": "user", "content": content},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 900,
                    "response_format": {"type": "json_object"},
                }
                return requests.post(endpoint, headers=headers, json=payload, timeout=40)

            used_reference = bool(ref_b64)
            r = ask(used_reference)
            if not r.ok and used_reference:
                # some services/models accept one picture only (or have a data limit): try again with the current picture only
                print(f"[OPENCV] the AI refused two pictures ({r.status_code}): trying with one")
                used_reference = False
                r = ask(False)
            if not r.ok:
                print(f"[OPENCV] IA error {r.status_code}: {r.text[:500]}")
                record_alert({"outcome": f"AI error {r.status_code}", "score": score, "model": final_model}, img_path, ref_path)
                return
            j = r.json()
            answer = j["choices"][0]["message"]["content"] if "choices" in j else str(j)
            print(f"[OPENCV] AI answer: {answer[:500]}")

            # Parsa JSON
            parsed = None
            try:
                parsed = json.loads(answer)
                if isinstance(parsed, dict) and "spaghetti" not in parsed:
                    for v in parsed.values():  # sometimes the answer is inside another object
                        if isinstance(v, dict) and "spaghetti" in v:
                            parsed = v
                            break
            except Exception:
                try:
                    m = re.search(r'\{[\s\S]*"spaghetti"[\s\S]*\}', answer)
                    if m:
                        parsed = json.loads(m.group(0))
                except Exception:
                    parsed = None

            if isinstance(parsed, dict):
                parsed = dict(parsed, action=normalize_action(parsed.get("action")) or "CONTINUE")
                if "observation" not in parsed and "osservazione" in parsed:  # an answer the old way
                    parsed["observation"] = parsed.pop("osservazione")
                parsed, downgraded = apply_min_confidence(parsed, self.ai_min_confidence, language)
                self.last_analysis = {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "model": final_model,
                    "progress": progress,
                    "filename": filename,
                    "image_path": img_path,
                    "with_reference": used_reference,
                    "analysis": parsed,
                    "raw": answer
                }
                self.stats["status"] = f"AI: {parsed.get('action','?')} - {str(parsed.get('summary',''))[:40]}"
                print(f"[OPENCV] AI analysis saved: {parsed}")
                confidences = [d.get("confidence") for k, d in parsed.items() if k in AI_DEFECT_KEYS and isinstance(d, dict) and d.get("detected") is True]
                record_alert({
                    "outcome": "analysed" + (" (downgraded: confidence below the minimum)" if downgraded else ""),
                    "score": score, "progress": round(progress, 1), "filename": filename, "model": final_model,
                    "action": parsed.get("action"), "original_action": parsed.get("original_action"),
                    "confidence": max([c for c in confidences if isinstance(c, (int, float))] or [0]),
                    "summary": parsed.get("summary"), "observation": parsed.get("observation"),
                    "with_reference": used_reference, "filter": self.persistent_filter,
                }, img_path, ref_path if used_reference else None)
            else:
                self.last_analysis = {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "model": final_model,
                    "progress": progress,
                    "analysis": {"action": "PAUSE", "summary": answer[:200], "raw": True},
                    "raw": answer
                }
                record_alert({"outcome": "AI answer not readable", "score": score, "model": final_model, "summary": answer[:200]}, img_path, ref_path)

        except Exception as e:
            print(f"[OPENCV] AI call fail: {e}")
            import traceback; traceback.print_exc()

RECORDINGS_DIR = os.path.join(DATA_DIR, "recordings")
recorder = Recorder(RECORDINGS_DIR, cv2 if HAS_CV2 else None, RELEASE)
detector = LightDetector()
detector.apply_config(brain_config.snapshot())  # the saved thresholds (or the defaults) apply from the first check
recorder.configure(brain_config.snapshot()["record"], brain_config.snapshot()["record_max_mb"])


def set_brain_config(changes):
    """Changes thresholds: checks them, saves them in monitor.json and puts them in use. -> (errors, changed keys)."""
    errors, changed = brain_config.update(changes)
    if errors:
        return errors, changed
    values = brain_config.snapshot()
    detector.apply_config(values)
    recorder.configure(values["record"], values["record_max_mb"])
    if "enabled" in changed:
        if values["enabled"]:
            detector.start()
        else:
            detector.stop()
    return errors, changed


# === UPDATE CHANNEL: which commits Moonraker's update manager installs ===========================================
# "stable": only the releases tagged vX.Y.Z on GitHub (the release workflow tags a release once all its tests passed);
# "dev": every change of the branch as soon as it is on GitHub. It is the "channel:" line of the [update_manager klippeye]
# section of moonraker.conf, read and written through Moonraker's own file API (the same Mainsail uses to edit it), after
# which Moonraker restarts to read it again.
UPDATE_CHANNELS = ("stable", "dev")
_UM_SECTION = re.compile(r"^\[update_manager\s+klippeye\s*\]\s*$")


def _update_section(lines):
    """(start, end) line indexes of KlippEye's update manager section (end excluded), or None."""
    start = None
    for i, line in enumerate(lines):
        if start is None:
            if _UM_SECTION.match(line):
                start = i
        elif re.match(r"^\s*\[", line):
            return start, i
    return (start, len(lines)) if start is not None else None


def update_channel_of(conf):
    """The channel written for KlippEye in moonraker.conf ("dev" when there is no channel line, Moonraker's own default), or None."""
    lines = conf.split("\n")
    where = _update_section(lines)
    if where is None:
        return None
    for line in lines[where[0] + 1:where[1]]:
        m = re.match(r"^\s*channel\s*[:=]\s*(\S+)", line)
        if m:
            return m.group(1).strip().lower()
    return "dev"


def with_update_channel(conf, channel):
    """moonraker.conf with KlippEye's channel set to `channel` (the line is replaced, or added after "type:")."""
    lines = conf.split("\n")
    where = _update_section(lines)
    if where is None:
        raise ValueError("no [update_manager klippeye] section")
    start, end = where
    for i in range(start + 1, end):
        if re.match(r"^\s*channel\s*[:=]", lines[i]):
            lines[i] = "channel: " + channel
            return "\n".join(lines)
    at = next((i + 1 for i in range(start + 1, end) if re.match(r"^\s*type\s*[:=]", lines[i])), start + 1)
    lines.insert(at, "channel: " + channel)
    return "\n".join(lines)


def _read_moonraker_conf():
    r = requests.get(MOONRAKER_URL + "/server/files/config/moonraker.conf", timeout=8)
    r.raise_for_status()
    return r.text


@app.route("/api/update/channel", methods=["GET"])
def api_update_channel():
    try:
        channel = update_channel_of(_read_moonraker_conf())
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": bt("Cannot read moonraker.conf: {error}", _lang(), error=e)}), 502
    return jsonify({"ok": True, "channel": channel, "listed": channel is not None, "channels": list(UPDATE_CHANNELS)})


@app.route("/api/update/channel", methods=["POST"])
def api_update_channel_set():
    lang = _lang()
    channel = str((request.get_json(silent=True) or {}).get("channel", "")).lower()
    if channel not in UPDATE_CHANNELS:
        return jsonify({"ok": False, "error": bt("Unknown update channel.", lang)}), 400
    try:
        state = requests.get(MOONRAKER_URL + "/printer/objects/query?print_stats=state", timeout=4).json()
        if state["result"]["status"]["print_stats"]["state"] in ("printing", "paused"):
            return jsonify({"ok": False, "error": bt("The printer is printing: change the update channel when the print ends (Moonraker restarts).", lang)}), 409
    except Exception:  # noqa: BLE001 - Klipper not ready: nothing is printing
        pass
    try:
        conf = _read_moonraker_conf()
        if update_channel_of(conf) is None:
            return jsonify({"ok": False, "error": bt("moonraker.conf has no [update_manager klippeye] section: run scripts/install.sh again.", lang)}), 409
        if update_channel_of(conf) == channel:
            return jsonify({"ok": True, "channel": channel, "changed": False})
        try:  # a copy of the file as it was, next to the installer's backups
            backup = os.path.join(DATA_DIR, "backup", "moonraker.conf-%s" % time.strftime("%Y%m%d-%H%M%S"))
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            with open(backup, "w", encoding="utf-8") as fh:
                fh.write(conf)
        except OSError:
            pass
        r = requests.post(MOONRAKER_URL + "/server/files/upload", data={"root": "config"},
                          files={"file": ("moonraker.conf", with_update_channel(conf, channel).encode("utf-8"), "text/plain")}, timeout=15)
        r.raise_for_status()
        requests.post(MOONRAKER_URL + "/server/restart", timeout=10)
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": bt("Cannot change moonraker.conf: {error}", lang, error=e)}), 502
    print(f"[UPDATE] channel set to {channel}; Moonraker restarts")
    return jsonify({"ok": True, "channel": channel, "changed": True})


DIAGNOSE_SCRIPT = os.path.join(REPO_DIR, "scripts", "diagnose.py")


@app.route("/api/diagnose", methods=["GET"])
def api_diagnose():
    """The diagnostic report of scripts/diagnose.py as a text file (no secrets in it: see the script)."""
    if not os.path.isfile(DIAGNOSE_SCRIPT):
        return jsonify({"ok": False, "error": bt("scripts/diagnose.py is missing: update KlippEye.", _lang())}), 404
    try:
        r = subprocess.run([sys.executable, DIAGNOSE_SCRIPT, "--repo", REPO_DIR, "--data", DATA_DIR,
                            "--backend", "http://127.0.0.1:%d" % PORT, "--moonraker", MOONRAKER_URL],
                           capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
        text = r.stdout or r.stderr
    except Exception as e:  # noqa: BLE001
        text = "The diagnostic report failed: %s\n" % e
    name = "klippeye-diagnose-%s.txt" % time.strftime("%Y%m%d-%H%M")
    return Response(text, mimetype="text/plain", headers={"Content-Disposition": 'attachment; filename="%s"' % name, "Cache-Control": "no-store"})


@app.route("/api/version", methods=["GET"])
def api_version():
    """Who am I: release (VERSION file), interface level, repository commit, how long I have been up."""
    return jsonify({
        "ok": True,
        "release": RELEASE,
        "api": API_LEVEL,
        "git": _git_info(),
        "started": int(START_TS),
        "uptime": int(time.time() - START_TS),
        "python": sys.version.split()[0],
        "has_cv2": HAS_CV2,
        "data_dir": DATA_DIR,
        "frontend": find_frontend(),
        "repair": read_repair_mark(),  # the last self-repair of the files (after a power loss), if any
    })


# === ANDROID APP: the APK GitHub builds (apk/KlippEye.apk + apk/version.json) ===============================
APK_DIR = os.path.join(REPO_DIR, "apk")
APK_PATH = os.path.join(APK_DIR, "KlippEye.apk")
APK_INFO_PATH = os.path.join(APK_DIR, "version.json")
APK_MIMETYPE = "application/vnd.android.package-archive"
_APK_VERSION_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{1,2})$")
_APK_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_apk_cache = {"key": None, "value": None}
_apk_lock = threading.Lock()


def _apk_code(version):
    """1.2.3 -> 10203: the same formula as android/app/build.gradle (None when the format is wrong)."""
    match = _APK_VERSION_RE.match(version or "")
    return int(match.group(1)) * 10000 + int(match.group(2)) * 100 + int(match.group(3)) if match else None


def _apk_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_apk_info():
    """
    What the backend offers the phone: {"available": True, "version", "code", "size", "sha256", "built", "url"} or
    {"available": False, "reason": ...} (the reason in English, marked with btn() for the dictionaries). apk/version.json
    is written by GitHub together with the APK; here the two must agree (size and SHA-256 of the real file), so half an
    update or a damaged file never reaches the phone. The check (a few tenths of a second) is redone only when the files change.
    """
    try:
        info_stat, apk_stat = os.stat(APK_INFO_PATH), os.stat(APK_PATH)
    except OSError:
        return {"available": False, "reason": btn("no app published")}
    key = (info_stat.st_mtime_ns, info_stat.st_size, apk_stat.st_mtime_ns, apk_stat.st_size)
    with _apk_lock:
        if _apk_cache["key"] == key:
            return _apk_cache["value"]
        value = _read_apk_info_uncached(apk_stat.st_size)
        _apk_cache["key"], _apk_cache["value"] = key, value
        return value


def _read_apk_info_uncached(apk_size):
    try:
        with open(APK_INFO_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"available": False, "reason": btn("apk/version.json cannot be read")}
    if not isinstance(data, dict):
        return {"available": False, "reason": btn("apk/version.json is not valid")}
    version, sha = data.get("version"), str(data.get("sha256") or "").lower()
    if not isinstance(version, str) or _apk_code(version) is None or not _APK_SHA_RE.match(sha):
        return {"available": False, "reason": btn("apk/version.json is not valid")}
    if data.get("size") != apk_size:
        return {"available": False, "reason": btn("the APK does not match version.json (half an update?)")}
    try:
        actual = _apk_sha256(APK_PATH)
    except OSError:
        return {"available": False, "reason": btn("the APK cannot be read")}
    if actual != sha:
        return {"available": False, "reason": btn("the APK does not match version.json (different fingerprint)")}
    built = data.get("built")
    return {
        "available": True,
        "version": version,
        "code": _apk_code(version),
        "size": apk_size,
        "sha256": sha,
        "built": built if isinstance(built, str) and len(built) <= 40 else "",
        "url": "/app/KlippEye.apk",
    }


@app.route("/api/app/version", methods=["GET"])
def api_app_version():
    """The Android app the backend can give the phone (see read_apk_info). Never cached: an update changes it."""
    info = read_apk_info()
    if info.get("reason"):
        info = dict(info, reason=bt(info["reason"], _lang()))
    response = jsonify(dict(info, ok=True))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/app/KlippEye.apk", methods=["GET"])
def app_apk():
    """The app file. Given only when it matches version.json (size and fingerprint), else 404 with the reason."""
    info = read_apk_info()
    if not info["available"]:
        return jsonify({"ok": False, "error": bt(info["reason"], _lang())}), 404
    response = send_file(APK_PATH, mimetype=APK_MIMETYPE, as_attachment=True, download_name="KlippEye-%s.apk" % info["version"], conditional=True, max_age=0)
    response.headers["Cache-Control"] = "no-store"
    return response
# === fine APP ANDROID ==================================================================================


# === PRINTER LOGOS: the repository's logos/ folder ==================================================
# The dashboard can show the VzBot, Voron or RatRig logo in its top bar (Settings -> Printer). The official files go in
# logos/ (voron.svg, ratrig.png...) and arrive with the normal update: the dashboard is not rebuilt.
LOGOS_DIR = os.path.join(REPO_DIR, "logos")
LOGO_BRANDS = ("vzbot", "voron", "ratrig")
LOGO_FILE_RE = re.compile(r"^(vzbot|voron|ratrig)\.(svg|png|webp)$")
LOGO_MIMETYPES = {"svg": "image/svg+xml", "png": "image/png", "webp": "image/webp"}
LOGO_MAX_BYTES = 2 * 1024 * 1024
LOGO_EXT_ORDER = ("svg", "png", "webp")  # with two files of the same brand the first wins


def list_logo_files():
    """The logos there are, one file per brand: ["voron.svg", ...] (other names, folders and files too big are ignored)."""
    try:
        names = os.listdir(LOGOS_DIR)
    except OSError:
        return []
    found = {}
    for name in names:
        match = LOGO_FILE_RE.match(name)
        path = os.path.join(LOGOS_DIR, name)
        if not match or os.path.islink(path) or not os.path.isfile(path):
            continue
        try:
            if not 0 < os.path.getsize(path) <= LOGO_MAX_BYTES:
                continue
        except OSError:
            continue
        brand, ext = match.group(1), match.group(2)
        if brand not in found or LOGO_EXT_ORDER.index(ext) < LOGO_EXT_ORDER.index(found[brand].rsplit(".", 1)[1]):
            found[brand] = name
    return [found[brand] for brand in LOGO_BRANDS if brand in found]


@app.route("/api/logos", methods=["GET"])
def api_logos():
    response = jsonify({"ok": True, "files": list_logo_files()})
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/logos/<name>", methods=["GET"])
def logo_file(name):
    """A logo of the logos/ folder (only the expected names: vzbot|voron|ratrig . svg|png|webp)."""
    if name not in list_logo_files():
        return jsonify({"ok": False, "error": "logo not found"}), 404
    response = send_file(os.path.join(LOGOS_DIR, name), mimetype=LOGO_MIMETYPES[name.rsplit(".", 1)[1]], conditional=True, max_age=0)
    # an SVG opened by itself must not be able to run scripts; inside an <img> it cannot anyway
    response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-cache"
    return response
# === end PRINTER LOGOS ===========================================================================


def brain_config_reply(ok=True, status=200, **extra):
    body = {
        "ok": ok,
        "api": API_LEVEL,
        "values": brain_config.snapshot(),
        "saved": brain_config.saved,
        "save_error": brain_config.save_error,
    }
    body.update(extra)
    return jsonify(body), status


@app.route("/api/backend/config", methods=["GET"])
def api_brain_config_get():
    """The AI monitor thresholds with all it takes to draw the menu (labels, limits, defaults)."""
    return brain_config_reply(
        defaults=config_defaults(),
        groups=CONFIG_GROUPS,
        spec=[{k: v for k, v in spec.items() if k != "pattern"} for spec in CONFIG_SPEC],
        path=BRAIN_CONFIG_PATH,
        running=detector.running,
        has_cv2=HAS_CV2,
    )


@app.route("/api/backend/config", methods=["POST"])
def api_brain_config_set():
    """{"values": {key: value, ...}}: only the given keys. When a value is wrong nothing changes (400 + errors)."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return brain_config_reply(False, 400, errors={"_": "a JSON object is needed"})
    changes = body.get("values") if isinstance(body.get("values"), dict) else body
    errors, changed = set_brain_config(changes)
    if errors:
        return brain_config_reply(False, 400, errors=errors)
    return brain_config_reply(changed=changed)


@app.route("/api/backend/config/reset", methods=["POST"])
def api_brain_config_reset():
    """Back to the defaults: all of them, or only {"keys": [...]}."""
    body = request.get_json(silent=True) or {}
    keys = body.get("keys") if isinstance(body.get("keys"), list) else None
    defaults = config_defaults()
    errors, changed = set_brain_config({key: defaults[key] for key in (keys or defaults) if key in defaults})
    if errors:
        return brain_config_reply(False, 400, errors=errors)
    return brain_config_reply(changed=changed)


@app.route("/api/print/detector/start", methods=["POST"])
def api_detector_start():
    data = request.get_json(silent=True) or {}
    changes = {"enabled": True}
    sens = data.get("sensitivity")
    if sens is not None:
        try:
            changes["sensitivity"] = max(5, min(100, int(sens)))
        except (TypeError, ValueError):
            pass
    set_brain_config(changes)
    detector.start()
    return jsonify({"ok": True, "enabled": detector.enabled, "stats": detector.stats})

@app.route("/api/print/detector/stop", methods=["POST"])
def api_detector_stop():
    set_brain_config({"enabled": False})
    detector.stop()
    return jsonify({"ok": True, "enabled": detector.enabled})

@app.route("/api/print/detector/status", methods=["GET"])
def api_detector_status():
    return jsonify({
        "ok": True,
        "enabled": detector.enabled,
        "running": detector.running,
        "has_cv2": HAS_CV2,
        "stats": detector.stats,
        "real_print_started": detector.stats.get("real_print_started", False),
        "real_print_reason": detector.stats.get("real_print_reason", ""),
        "progress": detector.stats.get("progress", 0),
        "roi": detector.roi,
        "sensitivity": detector.sensitivity,
        "last_alert_img": detector.last_alert_img_path
    })

@app.route("/api/print/detector/config", methods=["POST"])
def api_detector_config():
    # Old endpoint, kept the same for whoever uses it: it now goes through the settings, so the change stays saved.
    # (The dashboard menu uses /api/backend/config.) roi = [x,y,w,h] in pixels of the 1080x720 picture.
    data = request.get_json(silent=True) or {}
    changes = {}
    try:
        if "sensitivity" in data:
            changes["sensitivity"] = max(5, min(100, int(data["sensitivity"])))
        if "cooldown" in data:
            changes["cooldown"] = max(10, min(3600, int(data["cooldown"])))
        if "roi" in data:
            x, y, w, h = map(int, data["roi"])
            changes["roi"] = [x * 100.0 / OPENCV_WIDTH, y * 100.0 / OPENCV_HEIGHT, w * 100.0 / OPENCV_WIDTH, h * 100.0 / OPENCV_HEIGHT]
    except (TypeError, ValueError):
        pass
    if changes:
        errors, _ = set_brain_config(changes)
        if errors:  # a value that is not acceptable (e.g. an area outside the picture): left as it was, like the old try/except did
            for key in errors:
                changes.pop(key, None)
            if changes:
                set_brain_config(changes)
    return jsonify({"ok": True, "sensitivity": detector.sensitivity, "roi": detector.roi})

@app.route("/api/print/alerts", methods=["GET"])
def api_print_alerts():
    try:
        path = detector.last_alert_img_path
        if not path or not os.path.exists(path):
            return jsonify({"ok": True, "has_alert": False, "stats": detector.stats})
        with open(path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
        return jsonify({
            "ok": True,
            "has_alert": True,
            "stats": detector.stats,
            "image_b64": b64,
            "image_path": path
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/print/alerts/history", methods=["GET"])
def api_alert_history():
    """The monitor's last alerts (with the AI verdict and the picture names), newest first."""
    try:
        limit = max(1, min(ALERT_HISTORY_KEEP, int(request.args.get("limit", 20))))
    except ValueError:
        limit = 20
    return jsonify({"ok": True, "alerts": read_alert_history(limit)})


@app.route("/api/print/alerts/image/<name>", methods=["GET"])
def api_alert_image(name):
    if not re.fullmatch(r"\d{8}-\d{6}-(now|before|adesso|prima)\.jpg", name):   # adesso/prima: pictures saved by 1.1.x
        return jsonify({"ok": False, "error": "invalid name"}), 404
    path = os.path.join(ALERT_HISTORY_DIR, name)
    if not os.path.isfile(path):
        return jsonify({"ok": False, "error": "picture not found"}), 404
    return send_file(path, mimetype="image/jpeg", max_age=0)


@app.route("/api/print/last_analysis", methods=["GET"])
def api_print_last_analysis():
    """The last AI analysis as JSON, for the dashboard"""
    try:
        if not detector.last_analysis:
            return jsonify({"ok": True, "has_analysis": False, "stats": detector.stats})
        la = detector.last_analysis
        return jsonify({
            "ok": True,
            "has_analysis": True,
            "timestamp": la.get("timestamp"),
            "model": la.get("model"),
            "progress": la.get("progress"),
            "filename": la.get("filename"),
            "analysis": la.get("analysis"),
            "raw": la.get("raw","")[:1000],
            "stats": detector.stats
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

ALERT_LABELS = ("false", "right")


def label_alert(alert_id, label):
    """The person's verdict on an alarm: "false" (false alarm), "right" (there was a problem) or None (not said).
    Written in the alert history and in the recording of that print. -> the entry, or None when there is no such alarm."""
    with _history_lock:
        log = os.path.join(ALERT_HISTORY_DIR, "history.jsonl")
        try:
            with open(log, encoding="utf-8") as fh:
                lines = [l for l in fh.read().splitlines() if l.strip()]
        except OSError:
            return None
        found = None
        for index, line in enumerate(lines):
            try:
                entry = _english_alert(json.loads(line))
            except ValueError:
                continue
            if entry.get("id") == alert_id:
                if label is None:
                    entry.pop("label", None)
                else:
                    entry["label"] = label
                lines[index] = json.dumps(entry, ensure_ascii=False)
                found = entry
        if found is None:
            return None
        with open(log + ".tmp", "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        os.replace(log + ".tmp", log)
    if found.get("session"):
        recorder.label_alert(found["session"], alert_id, label)
    return found


@app.route("/api/print/alerts/<alert_id>/label", methods=["POST"])
def api_alert_label(alert_id):
    """{"label": "false" | "right" | null}: was this alarm a false alarm or a real problem?"""
    body = request.get_json(silent=True)
    label = body.get("label") if isinstance(body, dict) else "?"
    if label not in ALERT_LABELS + (None,) or not re.fullmatch(r"\d{8}-\d{6}", alert_id):
        return jsonify({"ok": False, "error": "label must be false, right or null"}), 400
    entry = label_alert(alert_id, label)
    if entry is None:
        return jsonify({"ok": False, "error": "no such alarm"}), 404
    return jsonify({"ok": True, "alert": entry})


# === RECORDINGS: the pictures of the prints, to measure the monitor (recorder.py, scripts/replay.py) ================
REPLAY_SCRIPT = os.path.join(REPO_DIR, "scripts", "replay.py")
MEASURE_PATH = os.path.join(RECORDINGS_DIR, "measure.json")
_measure = {"process": None, "started": None}
_measure_lock = threading.Lock()


def _no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/recordings", methods=["GET"])
def api_recordings():
    """The recordings (newest first), the space they take and what the recorder is doing."""
    return _no_store(jsonify(dict(recorder.summary(), ok=True)))


@app.route("/api/recordings/<sid>", methods=["GET"])
def api_recording(sid):
    """One recording: its session.json and the list of its pictures (number, time, score, alarm, layer, progress)."""
    session = recorder.load(sid)
    if session is None:
        return jsonify({"ok": False, "error": "no such recording"}), 404
    frames = [{k: f.get(k) for k in ("n", "t", "score", "trig", "cool", "layer", "layers", "progress")} for f in recorder.frames(sid)]
    return _no_store(jsonify({"ok": True, "session": session, "frames": frames}))


@app.route("/api/recordings/<sid>/frames/<int:n>.jpg", methods=["GET"])
def api_recording_frame(sid, n):
    path = recorder.frame_path(sid, n)
    if path is None:
        return jsonify({"ok": False, "error": "no such picture"}), 404
    return send_file(path, mimetype="image/jpeg", max_age=3600)


@app.route("/api/recordings/<sid>/label", methods=["POST"])
def api_recording_label(sid):
    """{"outcome": "ok" | "failed" | null, "failed_at": time (seconds, only with "failed")}: how the print really went."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "a JSON object is needed"}), 400
    try:
        label = recorder.set_label(sid, body.get("outcome"), body.get("failed_at"))
    except KeyError:
        return jsonify({"ok": False, "error": "no such recording"}), 404
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    return jsonify({"ok": True, "label": label})


@app.route("/api/recordings/<sid>", methods=["DELETE"])
def api_recording_delete(sid):
    if not recorder.delete(sid):
        return jsonify({"ok": False, "error": "no such recording"}), 404
    return jsonify({"ok": True})


def _measure_state():
    process = _measure["process"]
    if process is not None and process.poll() is None:
        return {"state": "running", "started": _measure["started"]}
    try:
        with open(MEASURE_PATH, encoding="utf-8") as f:
            result = json.load(f)
        return {"state": "done" if result.get("ok") else "error", "started": _measure["started"], "result": result}
    except (OSError, ValueError):
        return {"state": "error" if process is not None else "idle", "started": _measure["started"]}


@app.route("/api/recordings/measure", methods=["GET"])
def api_measure_get():
    """The last measurement of the monitor on the recordings (scripts/replay.py --json)."""
    return _no_store(jsonify(dict(_measure_state(), ok=True)))


@app.route("/api/recordings/measure", methods=["POST"])
def api_measure_start():
    """Runs the monitor again on every recording with the thresholds in use, at low priority (it takes a minute or two).
    The answer comes with GET."""
    with _measure_lock:
        if _measure_state()["state"] == "running":
            return jsonify({"ok": True, "state": "running"})
        if not os.path.isfile(REPLAY_SCRIPT):
            return jsonify({"ok": False, "error": "scripts/replay.py is missing"}), 500
        try:
            os.makedirs(RECORDINGS_DIR, exist_ok=True)
            try:
                os.remove(MEASURE_PATH)
            except OSError:
                pass
            command = [sys.executable, REPLAY_SCRIPT, "--data", DATA_DIR, "--current", "--json", MEASURE_PATH]
            if shutil.which("nice"):
                command = ["nice", "-n", "15"] + command
            _measure["process"] = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _measure["started"] = int(time.time())
        except OSError as error:
            return jsonify({"ok": False, "error": str(error)}), 500
    return jsonify({"ok": True, "state": "running"})
# === end RECORDINGS ===================================================================================================


# === CAMERA CALIBRATION (phase 4): camera_calibration.py, camera_model.py, camera_watch.py ===========================
import camera_calibration as _camcal  # noqa: E402


def _klipper_query(objects):
    r = requests.get(f"{MOONRAKER_URL}/printer/objects/query?{objects}", timeout=5)
    r.raise_for_status()
    return r.json()["result"]["status"]


def _klipper_gcode(script, timeout):
    r = requests.post(f"{MOONRAKER_URL}/printer/gcode/script", json={"script": script}, timeout=timeout)
    if not r.ok:
        try:
            message = r.json()["error"]["message"]
        except Exception:
            message = "HTTP %s" % r.status_code
        raise _camcal.NotReady("Klipper refused the command: {message}", message=message)


def _camera_snapshot():
    r = requests.get(f"{CAMERA_NGINX_URL}/snapshot", timeout=5)
    return r.content if r.ok and len(r.content) > 1000 else None


CAMERA_MESSAGES = (  # what camera_calibration.py and camera_model.py may answer, for the dictionaries (bt translates them)
    btn("Klipper is not ready"), btn("the printer is printing"), btn("home the printer first"), btn("z_moves must be bed or toolhead"),
    btn("the toolhead size must be 10 to 300 mm"), btn("each size must be {low} to {high} mm"), btn("unknown point"), btn("a step is at most 50 mm"),
    btn("u and v must be fractions of the picture (0..1)"), btn("the markers are only for printers where Z moves the bed"),
    btn("choose the file that printed the markers"), btn("this file is too big to be the markers file"),
    btn("temperatures: nozzle 170 to 300 °C, bed 0 to 120 °C"), btn("this file extrudes nothing"),
    btn("this file has no markers: print the KlippEye markers file"), btn("the markers file was not recognised: {found} markers found instead of 6"),
    btn("no picture from the camera"), btn("at least 8 points are needed"), btn("calculate the calibration first"),
    btn("the calibration is not good enough: redo the points marked in red"), btn("the camera picture changed size: calculate again"),
    btn("the points must be at two heights at least 10 mm apart"), btn("the points are all on one plane"),
    btn("no camera fits these points: check that each tap is on the nozzle tip"), btn("the camera is not calibrated"),
    btn("Klipper refused the command: {message}"),
)
def _gcode_files():
    r = requests.get(f"{MOONRAKER_URL}/server/files/list?root=gcodes", timeout=10)
    r.raise_for_status()
    return r.json().get("result") or []


def _read_gcode(path):
    r = requests.get(f"{MOONRAKER_URL}/server/files/gcodes/" + urllib.parse.quote(path), timeout=60, stream=True)
    if r.status_code == 404:
        raise ValueError("choose the file that printed the markers")
    r.raise_for_status()
    data = b""
    for chunk in r.iter_content(1024 * 1024):
        data += chunk
        if len(data) > _camcal.MAX_GCODE_BYTES:
            raise ValueError("this file is too big to be the markers file")
    return data.decode("utf-8", "replace")


camera_cal = _camcal.CameraCalibration(DATA_DIR, _klipper_query, _klipper_gcode, _camera_snapshot, cv2 if HAS_CV2 else None, np,
                                       files=_gcode_files, read_file=_read_gcode)


def _camera_call(work):
    """Runs one calibration step: 409 when the printer cannot do it now, 400 when the request is wrong, 502 when Klipper or
    the camera do not answer."""
    try:
        return jsonify(dict(work() or {}, ok=True))
    except _camcal.NotReady as error:
        return jsonify({"ok": False, "error": bt(error.text, _lang(), **error.values)}), 409
    except ValueError as error:
        return jsonify({"ok": False, "error": bt(str(error), _lang(), **getattr(error, "values", {}))}), 400
    except requests.RequestException as error:
        return jsonify({"ok": False, "error": bt("Klipper does not answer: {error}", _lang(), error=error)}), 502


def _camera_body():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


@app.route("/api/camera/calibration", methods=["GET"])
def api_camera_calibration():
    """The saved calibration, the points being taken, the points to take and the printer (homed, limits, position)."""
    def work():
        out = camera_cal.summary()
        try:
            printer = camera_cal.printer()
            out["printer"] = printer
            out["targets"] = camera_cal.target_list(printer)
            out["guess"] = camera_cal.guess() if not camera_cal.z_moves() else None
        except Exception as error:
            out["printer"] = None
            out["printer_error"] = str(error)[:200]
            out["targets"] = []
        out["has_cv2"] = HAS_CV2
        return out
    response = _camera_call(work)
    if isinstance(response, Response):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/camera/calibration/options", methods=["POST"])
def api_camera_options():
    body = _camera_body()
    return _camera_call(lambda: {"draft": camera_cal.set_options(body.get("z_moves"), body.get("toolhead"))})


@app.route("/api/camera/calibration/home", methods=["POST"])
def api_camera_home():
    return _camera_call(lambda: camera_cal.home())


@app.route("/api/camera/calibration/goto", methods=["POST"])
def api_camera_goto():
    body = _camera_body()
    return _camera_call(lambda: camera_cal.goto(str(body.get("target", ""))))


@app.route("/api/camera/calibration/jog", methods=["POST"])
def api_camera_jog():
    body = _camera_body()
    return _camera_call(lambda: camera_cal.jog(body.get("dx", 0), body.get("dy", 0), body.get("dz", 0)))


@app.route("/api/camera/calibration/marks", methods=["POST"])
def api_camera_marks():
    """The quick markers: {"nozzle": °C, "bed": °C}; the printer leaves six small discs of filament."""
    body = _camera_body()
    return _camera_call(lambda: {"marks": camera_cal.make_marks(body.get("nozzle", 210), body.get("bed", 60))})


@app.route("/api/camera/calibration/markers", methods=["POST"])
def api_camera_markers():
    """{"file": path}: the G-code that printed the markers; where the six pyramids are is read from it."""
    body = _camera_body()
    return _camera_call(lambda: {"markers": camera_cal.use_marker_file(body.get("file"))})


@app.route("/api/camera/gcode-files", methods=["GET"])
def api_camera_gcode_files():
    return _camera_call(lambda: {"files": camera_cal.gcode_files()})


@app.route("/api/camera/markers.stl", methods=["GET"])
def api_camera_markers_stl():
    """The six pyramids to print (sized for this printer's bed): slice it with your usual settings and print it."""
    try:
        data = camera_cal.markers_stl()
    except Exception as error:
        return jsonify({"ok": False, "error": bt("Klipper does not answer: {error}", _lang(), error=error)}), 502
    return Response(data, mimetype="model/stl", headers={"Content-Disposition": 'attachment; filename="klippeye-camera-markers.stl"', "Cache-Control": "no-store"})


@app.route("/api/camera/calibration/point", methods=["POST"])
def api_camera_point():
    body = _camera_body()
    return _camera_call(lambda: {"point": camera_cal.add_point(str(body.get("target", "")), body.get("u"), body.get("v"))})


@app.route("/api/camera/calibration/forget", methods=["POST"])
def api_camera_forget_point():
    body = _camera_body()
    return _camera_call(lambda: camera_cal.forget_point(str(body.get("target", ""))))


@app.route("/api/camera/calibration/fit", methods=["POST"])
def api_camera_fit():
    if not HAS_CV2:
        return jsonify({"ok": False, "error": bt("OpenCV is missing on the Raspberry", _lang())}), 500
    return _camera_call(lambda: {"fit": camera_cal.fit()})


@app.route("/api/camera/calibration/save", methods=["POST"])
def api_camera_save():
    return _camera_call(lambda: {"saved": camera_cal.save() and camera_cal.summary()["saved"]})


@app.route("/api/camera/calibration/reset", methods=["POST"])
def api_camera_reset():
    return _camera_call(lambda: camera_cal.reset())


@app.route("/api/camera/calibration", methods=["DELETE"])
def api_camera_forget():
    return _camera_call(lambda: camera_cal.forget())


# === PRINTER FUNCTIONS (phase 5b): the macros KlippEye writes into klippeye_macros.cfg ==================================
import printer_macros  # noqa: E402

MACRO_MESSAGES = (  # what printer_macros.py may answer, for the dictionaries (bt translates them)
    btn("the macro is empty"), btn("the macro is too long"), btn("only [gcode_macro NAME] sections can be saved here"),
    btn("{name} is not a valid macro name"), btn("the macro must be called {name}"),
    btn("{name} is announced as a filament change: it cannot also be created here"), btn("too many macros"),
    btn("{name} already exists in your configuration: choose another name"),
    btn("{name} is not a command of your printer: Klipper would not start with it"),
    btn("Klipper does not answer: it must be running to check the macros"),
    btn("the configuration folder was not found: {folder}"), btn("printer.cfg was not found in {folder}"), btn("unknown function"),
)


def _klipper_commands():
    r = requests.get(f"{MOONRAKER_URL}/printer/gcode/help", timeout=5)
    r.raise_for_status()
    return list((r.json().get("result") or {}).keys())


printer_macros_store = printer_macros.PrinterMacros(DATA_DIR, _config_dir, _klipper_commands)


def _macros_call(work):
    try:
        return jsonify(dict(work() or {}, ok=True))
    except printer_macros.MacroError as error:
        return jsonify({"ok": False, "error": bt(str(error), _lang(), **error.values)}), 400
    except OSError as error:
        return jsonify({"ok": False, "error": str(error)}), 500


@app.route("/api/printer-macros", methods=["GET"])
def api_printer_macros():
    """The macros KlippEye made (and the ones it announces as a filament change), and whether printer.cfg includes them."""
    return _macros_call(printer_macros_store.summary)


@app.route("/api/printer-macros/template", methods=["GET"])
def api_printer_macros_template():
    """The macro KlippEye proposes for a function (park, wipe, load, unload, light_on, light_off), to edit before saving."""
    def work():
        name, text = printer_macros.template(request.args.get("kind", ""))
        return {"name": name, "text": text}
    return _macros_call(work)


@app.route("/api/printer-macros/macro", methods=["POST"])
def api_printer_macros_macro():
    """{name, text}: creates or replaces one of KlippEye's macros; text null removes it. Klipper reads it at its next restart."""
    body = request.get_json(silent=True) or {}
    return _macros_call(lambda: printer_macros_store.set_macro(body.get("name"), body.get("text")))


@app.route("/api/printer-macros/wraps", methods=["POST"])
def api_printer_macros_wraps():
    """{names: [...]}: the macros that announce a filament change to the notification service (see printer_macros.py)."""
    body = request.get_json(silent=True) or {}
    names = body.get("names")
    return _macros_call(lambda: printer_macros_store.set_wraps(names if isinstance(names, list) else []))


# === NOTIFICATION CHANNELS (phase 5c): ntfy set up from the dashboard, Firebase shown =====================================
import notify_channels  # noqa: E402

NOTIFY_MESSAGES = (  # what notify_channels.py may answer, for the dictionaries (bt translates them)
    btn("notifier.json is damaged: fix it or delete it ({error})"), btn("the server address must start with http:// or https://"),
    btn("the access token has characters that are not allowed"), btn("the address of the dashboard must start with http:// or https://"),
)
notify_store = notify_channels.NotifyChannels(DATA_DIR, REPO_DIR, write_json_atomic)


def _notify_call(work):
    try:
        return jsonify(dict(work() or {}, ok=True))
    except notify_channels.ChannelError as error:
        return jsonify({"ok": False, "error": bt(str(error), _lang(), **error.values)}), 400
    except OSError as error:
        return jsonify({"ok": False, "error": str(error)}), 500


@app.route("/api/notifications/channels", methods=["GET"])
def api_notify_channels():
    """Where the notifications go: ntfy (server, private topic, the link that subscribes the ntfy app) and Firebase."""
    return _notify_call(notify_store.summary)


@app.route("/api/notifications/ntfy", methods=["POST"])
def api_notify_ntfy():
    """{enabled, new_topic, server, token, click}: only the keys given change. The service picks the change up by itself."""
    body = request.get_json(silent=True) or {}
    return _notify_call(lambda: notify_store.set_ntfy(body if isinstance(body, dict) else {}))


@app.route("/api/notifications/app", methods=["GET"])
def api_notify_app():
    """For the KlippEye app (1.3.0+): the ntfy topic to listen to and, only where Firebase is set up, the Firebase topic."""
    return _notify_call(notify_store.for_app)


@app.route("/api/notifications/test", methods=["POST"])
def api_notify_test():
    """Sends a test notification through every channel that is set up: {results: [{channel, ok, error}]}."""
    return _notify_call(notify_store.send_test)


@app.route("/api/camera/shape", methods=["POST"])
def api_camera_shape():
    """The size of the toolhead and of the gantry around the nozzle (mm): {"toolhead": {left, right, front, back, top, below},
    "gantry": {on, behind, depth, low, high}}; the values not given stay. The masks of the monitor use it at once."""
    return _camera_call(lambda: {"shape": camera_cal.set_shape(_camera_body())})


@app.route("/api/camera/overlay", methods=["GET"])
def api_camera_overlay():
    """Where the nozzle, the toolhead and the bed are in the picture right now (saved calibration, or ?draft=1 the one
    just calculated): to see on the live picture whether the calibration is right."""
    def work():
        overlay = camera_cal.overlay(use_draft=request.args.get("draft") == "1")
        if overlay is None:
            raise ValueError("the camera is not calibrated")
        # phase 4c: the objects of the print running now (where the part is expected), when they are known
        objects, known = detector.zone.get("objects"), camera_cal.limits()
        overlay["zone"] = None
        if objects and known and camera_cal.saved and request.args.get("draft") != "1":
            parts = print_zone.outlines(camera_cal.saved, objects, overlay["position"][2], known[0], known[1])
            overlay["zone"] = {"source": detector.zone.get("source"), "objects": len(objects),
                               "expected": [[[round(u, 4), round(v, 4)] for u, v in p] for p in parts["expected"]]}
        return overlay
    response = _camera_call(work)
    if isinstance(response, Response):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/camera/check", methods=["POST"])
def api_camera_check():
    """Has the camera moved since the calibration? Compares a new picture with the one taken then."""
    if not HAS_CV2:
        return jsonify({"ok": False, "error": bt("OpenCV is missing on the Raspberry", _lang())}), 500
    return _camera_call(lambda: {"watch": camera_cal.check_moved()})
# === end CAMERA CALIBRATION ===========================================================================================


# === END OPENCV DETECTOR V10 ===


# === PRINT AI ANALYSIS V9 - SPAGHETTI / EMPTY BED / LAYER SHIFT ===
import base64
import io

@app.route("/api/print/snapshot", methods=["GET"])
def api_print_snapshot():
    """Proxy snapshot raw"""
    try:
        r = requests.get(f"{CAMERA_NGINX_URL}/snapshot", timeout=5, stream=True)
        return Response(r.iter_content(chunk_size=8192), status=r.status_code, content_type=r.headers.get('Content-Type','image/jpeg'))
    except Exception as e:
        return jsonify({"error": str(e)}), 502

@app.route("/api/print/analyze", methods=["POST","GET"])
def api_print_analyze():
    """
    Analyses the print in progress: camera snapshot + telemetry
    (the same approach as the logs, with vision)
    """
    try:
        cfg = load_ai_config()
        if not cfg.get("api_key"):
            return jsonify({"error": bt("API key not set: go to System logs > ⚙️ and enter a Groq/OpenAI key", _lang()), "howto": bt("Use the same key as the logs", _lang())}), 401

        # 1. camera snapshot - V17: resized to 1080x720 for the detail of an empty bed
        img_b64 = None
        img_resized_bytes = None
        try:
            r = requests.get(f"{CAMERA_NGINX_URL}/snapshot", timeout=6)
            content = None
            if r.ok and len(r.content) > 1000:
                content = r.content
            else:
                r2 = requests.get(f"{CAMERA_NGINX_URL}/?action=snapshot", timeout=6)
                if r2.ok and len(r2.content) > 1000:
                    content = r2.content
            
            if content:
                try:
                    if HAS_CV2:
                        arr = np.frombuffer(content, np.uint8)
                        frm = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                        if frm is not None:
                            resized = cv2.resize(frm, (AI_IMAGE_WIDTH, AI_IMAGE_HEIGHT), interpolation=cv2.INTER_AREA)
                            _, buf = cv2.imencode('.jpg', resized, [int(cv2.IMWRITE_JPEG_QUALITY), AI_IMAGE_QUALITY])
                            img_resized_bytes = buf.tobytes()
                            img_b64 = base64.b64encode(img_resized_bytes).decode('utf-8')
                        else:
                            img_b64 = base64.b64encode(content).decode('utf-8')
                    else:
                        img_b64 = base64.b64encode(content).decode('utf-8')
                except:
                    img_b64 = base64.b64encode(content).decode('utf-8')
        except Exception as e:
            print(f"[PRINT-AI] snapshot error: {e}")

        if not img_b64:
            return jsonify({"error": bt("Cannot take a camera snapshot: check the camera on the Home page", _lang())}), 500

        # 2. print telemetry
        telemetry = {}
        try:
            pr = requests.get(f"{MOONRAKER_URL}/printer/objects/query?print_stats&extruder&heater_bed&display_status&toolhead&virtual_sdcard&gcode_move", timeout=3).json()
            telemetry = pr.get("result",{}).get("status",{})
        except Exception as e:
            telemetry = {"error": str(e)}

        print_stats = telemetry.get("print_stats",{})
        display = telemetry.get("display_status",{})
        extruder = telemetry.get("extruder",{})
        bed = telemetry.get("heater_bed",{})
        v_sd = telemetry.get("virtual_sdcard",{})

        state = print_stats.get("state","unknown")
        filename = print_stats.get("filename","")
        progress = display.get("progress",0)*100
        temp_h = extruder.get("temperature",0)
        target_h = extruder.get("target",0)
        temp_b = bed.get("temperature",0)

        # 3. vision prompt - hybrid solution 5
        # real_print_started is worked out here too, for the prompt
        real_print_started = False
        real_reason = ""
        try:
            file_pos = v_sd.get("file_position",0)
            file_size = v_sd.get("file_size",1)
            file_progress = file_pos / file_size if file_size>0 else 0
            total_dur = print_stats.get("total_duration",0)
            progress_frac = progress/100 if progress>1 else progress
            # the same criteria as the detector
            checks = []
            if progress_frac < detector.min_progress/100 and file_progress < detector.min_progress/200:
                checks.append(f"progress {progress_frac*100:.1f}% low")
            else:
                real_print_started = True
            if abs(temp_h - target_h) > detector.hotend_tol and target_h>0:
                real_print_started = False
                checks.append(f"hotend not at temperature {temp_h:.0f}/{target_h:.0f}")
            if total_dur < detector.warmup:
                real_print_started = False
                checks.append(f"duration {total_dur:.0f}s <{detector.warmup}s")
            if progress_frac >= detector.min_progress/100 and abs(temp_h - target_h) <= detector.hotend_tol:
                real_print_started = True
                checks = ["ok - real print started"]
            real_reason = "; ".join(checks)
        except Exception as e:
            real_reason = f"real_print check failed: {e}"

        language = _lang()
        prompt_text = f"""You are a 3D printing expert, specialised in detecting failed prints.

Analyse this picture of the print in progress.

TELEMETRY:
- State: {state}
- File: {filename}
- Progress: {progress:.1f}%
- Hotend: {temp_h:.1f}°C / target {target_h:.1f}°C
- Bed: {temp_b:.1f}°C
- Print stats: {print_stats}
- REAL_PRINT_STARTED: {real_print_started} ({real_reason})
- File position: {file_pos}/{file_size} ({file_progress*100:.1f}%)

CRITICAL RULE AGAINST A FALSE EMPTY BED:
- If REAL_PRINT_STARTED is False (heating, mesh, homing, calibration, purge not started yet):
  - NEVER report "empty bed" as an error
  - CONTINUE with the note "heating/calibration in progress, an empty bed is normal"
- If REAL_PRINT_STARTED is True BUT progress < 3% or file position < 5%:
  - An empty bed is NORMAL if you see no part: the first layer may still be thin or transparent
  - Ask for confidence >= 85% to report an empty bed in the first layers
  - If you see a shadow, a reflection or a faint outline on the bed, it is still a valid print = CONTINUE
- ONLY when REAL_PRINT_STARTED is True AND progress > 5% AND file position > 10% may you report an empty bed, with confidence >= 70%
- LOOK CAREFULLY: if you see even a dot, a line or an edge on the bed, it is NOT empty
- The picture is high resolution: use the detail to tell a clean bed from a thin first layer

TASK:
1) Detect SPAGHETTI (tangled filament, extrusion in the air)
2) Detect an EMPTY BED (part detached, empty bed while printing)
3) Detect a LAYER SHIFT
4) Detect WARPING / failed adhesion
5) Detect a CLOGGED NOZZLE / under-extrusion
6) Give a confidence % for each one
7) Suggest an action: CONTINUE / PAUSE / CANCEL

Write the texts in {LANGUAGE_NAMES.get(language, "English")}; keep the JSON keys and the action words in English.
Structured JSON + a short explanation:
{{
  "spaghetti": {{"detected": true/false, "confidence": 0-100, "note": "..."}},
  "empty_bed": {{"detected": true/false, "confidence": 0-100}},
  "layer_shift": {{"detected": true/false, "confidence": 0-100}},
  "warping": {{"detected": true/false}},
  "action": "CONTINUE|PAUSE|CANCEL",
  "summary": "short sentence"
}}
Then add a markdown section with a detailed explanation.
"""

        provider = cfg.get("provider","openai").lower()
        model = cfg.get("model","gpt-4o-mini")
        api_key = cfg.get("api_key")

        # Mappa provider -> endpoint vision
        # Groq vision: meta-llama/llama-4-scout-17b-16e-instruct or llama-4-maverick
        # OpenAI: gpt-4o-mini supporta vision
        provider_map_vision = {
            "openai": ("https://api.openai.com/v1/chat/completions", model if "vision" in model.lower() or "gpt-4o" in model.lower() or "gpt-4" in model.lower() else "gpt-4o-mini"),
            "groq": ("https://api.groq.com/openai/v1/chat/completions", "qwen/qwen3.8-27b"),  # FIX 2026-10: Llama-4 Scout removed from Groq, now only Qwen 3.8 vision
            "meta": ("https://api.llama.com/compat/v1/chat/completions", "Llama-4-Scout-17B-16E-Instruct"),
            "llama": ("https://api.llama.com/compat/v1/chat/completions", "Llama-4-Scout-17B-16E-Instruct"),
        }
        endpoint, final_model = provider_map_vision.get(provider, (f"https://api.openai.com/v1/chat/completions", "gpt-4o-mini"))

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type":"application/json"}
        if provider=="openrouter":
            headers["HTTP-Referer"]="https://klippeye.local"
            endpoint = "https://openrouter.ai/api/v1/chat/completions"
            final_model = "meta-llama/llama-4-scout-17b-16e-instruct"
        if detector.ai_model:  # chosen in the dashboard (Monitor thresholds): wins over the service's default
            final_model = detector.ai_model

        payload = {
            "model": final_model,
            "messages":[
                {"role":"system","content":"You are an expert in detecting failed 3D prints. Always answer with JSON + markdown."},
                {"role":"user","content":[
                    {"type":"text","text":prompt_text},
                    {"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]}
            ],
            "temperature":0.2,
            "max_tokens": 1800
        }

        # providers that do not take an array as content (old ones): text only after an error
        try:
            r = requests.post(endpoint, headers=headers, json=payload, timeout=40)
            if not r.ok:
                # try without the picture, with a note
                print(f"[PRINT-AI] vision failed {r.status_code}: {r.text[:500]}")
                # fallback: telemetry only
                payload_fallback = {
                    "model": final_model,
                    "messages":[
                        {"role":"system","content":"3D printing expert"},
                        {"role":"user","content": f"{prompt_text}\n\n[NOTE: the picture is not available with this provider: analyse the telemetry only and suggest using OpenAI gpt-4o-mini for vision]"}
                    ],
                    "temperature":0.3,
                    "max_tokens":1200
                }
                r = requests.post(endpoint, headers=headers, json=payload_fallback, timeout=30)
            j = r.json()
            if not r.ok:
                return jsonify({"error": f"{provider} API error {r.status_code}: {r.text[:1000]}", "model": final_model}), 500
            answer = j["choices"][0]["message"]["content"] if "choices" in j else str(j)[:2000]
            return jsonify({
                "ok": True,
                "provider": provider,
                "model": final_model,
                "state": state,
                "filename": filename,
                "progress": progress,
                "telemetry": telemetry,
                "analysis": answer
            })
        except Exception as e:
            return jsonify({"error": f"print analyze failed: {e}"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === END PRINT AI V9 ===


# start the detector when cv2 is there (unless switched off in the menu: Monitor thresholds > Monitor on)
try:
    if HAS_CV2 and brain_config.snapshot()["enabled"]:
        detector.start()
        print("[OPENCV] Detector started (it checks while printing)")
    elif HAS_CV2:
        detector.enabled = False
        detector.stats["status"] = "stopped"
        print("[OPENCV] Detector switched off in the menu: not started")
    else:
        print("[OPENCV] Detector not started: cv2 missing")
except Exception as e:
    print(f"[OPENCV] Auto-start fail: {e}")

if __name__ == "__main__":
    threading.Thread(target=_repair_at_startup, name="repair", daemon=True).start()
    print(f"KlippEye backend {RELEASE} (api {API_LEVEL}) - data in {DATA_DIR} - settings {'read from ' + BRAIN_CONFIG_PATH if brain_config.saved else 'default (no saved file)'}")
    print(f"KlippEye backend running on 0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
