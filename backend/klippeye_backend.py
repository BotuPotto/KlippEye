"""
KlippEye backend - server del frontend (Flask) + monitor IA (OpenCV) + ponte verso Moonraker.

Parte del progetto KlippEye (cartella ~/klippeye, vedi README.md): questo file sta in backend/, il frontend (la dashboard) in
frontend/, la versione in VERSION. Il codice qui sotto e' quello del backend V18 (UI 1:1 identica ma NON MOCK, dati reali, comandi
reali, camera, ZeroTier fix, FIX 404 Groq, FIX 413 TPM) con queste aggiunte della release 1.0:

  * le soglie del monitor IA (sensibilita', quante anomalie, ogni quanti secondi, avvio dopo N secondi, ROI...) sono
    impostazioni: si leggono e si cambiano da /api/backend/config (la dashboard ha il menu) e restano salvate in
    <cartella dati>/brain.json. Un file mancante o rovinato vuol dire "valori di sempre": non impedisce mai l'avvio;
  * /api/version dice release, livello dell'interfaccia (API_LEVEL) e commit; la release viene dal file VERSION;
  * la cartella dati (default ~/printer_data/klippeye, cambia con la variabile KLIPPEYE_DATA; il vecchio nome VZBOT_DATA vale
    ancora) tiene tutto quello che e' del
    Raspberry e non del codice: impostazioni, chiave dell'IA (file con permessi 600), notifiche. Gli aggiornamenti
    del codice (Moonraker -> update manager) non la toccano mai;
  * il ponte verso Moonraker aspetta fino a 10 minuti le operazioni lunghe (/machine/update/...) invece di 10 secondi;
  * l'app Android: l'APK costruito da GitHub arriva nella cartella apk/ del repository con l'aggiornamento di KlippEye e il backend
    lo offre al telefono (/api/app/version dice quale versione e', /app/KlippEye.apk e' il file; /app/VzBot.apk e' lo stesso file,
    per l'app con il vecchio nome che cerca li' l'aggiornamento);
  * la cartella dati e le vecchie posizioni (/home/pi/vzbot_ai_config.json...) si leggono entrambe: nessun dato perso;
  * dal vecchio nome: un'installazione che sta ancora in ~/vzbot (servizio "vzbot") si sposta da sola in ~/klippeye
    (/api/migrate/..., scripts/passa-a-klippeye.sh), vedi la sezione PASSAGGIO A KLIPPEYE.
"""
from flask import Flask, request, Response, jsonify, send_file
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

app = Flask(__name__)
# CORS: no longer open to every site (1.2.0). The dashboard and the app talk to the backend from its own origin; see ACCESS.

MOONRAKER_URL = "http://127.0.0.1:7125"
CAMERA_NGINX_URL = "http://127.0.0.1/webcam"
PORT = int(os.environ.get("KLIPPEYE_PORT") or 8085)  # 8085 di sempre (la variabile serve solo alle prove)

# === BASE: release, cartella dati, impostazioni salvate ===========================================
BRAIN_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BRAIN_DIR)  # ~/klippeye: la cartella del repository (backend/, frontend/, VERSION...)
API_LEVEL = 2  # sale quando cambia il "linguaggio" tra backend e dashboard (la dashboard dice quale le serve)
START_TS = time.time()


def _read_release():
    """La release e' scritta in VERSION (accanto a backend/, frontend/...). Senza il file (backend copiato da solo): 'sviluppo'."""
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
    chosen = (os.environ.get("KLIPPEYE_DATA") or os.environ.get("VZBOT_DATA") or "").strip()  # VZBOT_DATA: il servizio col vecchio nome
    if chosen:
        return os.path.abspath(os.path.expanduser(chosen))
    home = os.path.expanduser("~")
    if os.path.isdir(os.path.join(home, "printer_data")):
        new, old = os.path.join(home, "printer_data", "klippeye"), os.path.join(home, "printer_data", "vzbot")
        return old if os.path.isdir(old) and not os.path.isdir(new) else new  # prima del passaggio al nuovo nome i dati stanno ancora nella vecchia
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
MONITOR_CONFIG_PATH = os.path.join(DATA_DIR, "monitor.json")   # the AI monitor thresholds (brain.json before 1.3.0)
BRAIN_CONFIG_PATH = MONITOR_CONFIG_PATH   # old name of the variable, kept for code that still uses it


def write_json_atomic(path, data, private=False):
    """Scrive su un file temporaneo e lo sostituisce: una caduta di corrente non lascia mai mezzo file."""
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
ACCESS_PUBLIC = {"/login", "/api/auth/status", "/api/auth/login", "/api/app/version", "/app/KlippEye.apk", "/app/VzBot.apk"}
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
     "note": "Every few seconds the backend compares two camera pictures: if many points of the outer band of the watched area change, and it happens several times, it asks the AI to look at the picture."},
    {"id": "filtro", "title": "False alarms",
     "note": "The filter compares the current picture with a «background» made of several pictures of the last minutes (the passing toolhead is not part of it) and counts only the changes that stay for several checks in a row. It also ignores light changes."},
    {"id": "area", "title": "Watched area", "note": "The rectangle where the backend looks for suspicious movement. By default it is the central 60% of the picture."},
    {"id": "tempi", "title": "Pauses and usage", "note": "The AI analysis uses an online service: these pauses avoid calling it too often."},
    {"id": "avvio", "title": "When it starts checking",
     "note": "During heating, mesh or purge the real print has not started yet: the monitor waits."},
    {"id": "ia", "title": "AI model", "note": ""},
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
    {"key": "persist_checks", "type": "int", "default": 3, "min": 2, "max": 6, "step": 1, "unit": "", "group": "filtro",
     "label": "Checks in a row the change must stay for",
     "help": "Higher = fewer false alarms but a problem is noticed a few seconds later (checks × interval)."},
    {"key": "reference_seconds", "type": "int", "default": 60, "min": 20, "max": 300, "step": 10, "unit": "s", "group": "filtro",
     "label": "Time covered by the background",
     "help": "The background is made from the pictures of the last N seconds. Longer = the toolhead and slow movements weigh less, but a long-lasting problem is «absorbed» later."},
    {"key": "global_change", "type": "float", "default": 30, "min": 5, "max": 100, "step": 5, "decimals": 0, "unit": "%", "group": "filtro",
     "label": "Light change: ignore if more than this changes",
     "help": "If more than this part of the whole picture changes at once (light on or off, camera moved, toolhead right in front of the lens) the check is ignored. If it lasts more than about thirty seconds it counts as a real change."},
    {"key": "ai_min_confidence", "type": "int", "default": 70, "min": 0, "max": 100, "step": 5, "unit": "%", "group": "ia",
     "label": "Minimum AI confidence to report a problem",
     "help": "If the AI suggests PAUSE or CANCEL but no defect has at least this confidence, the verdict becomes CONTINUE (it stays written in the history). 0 = always trust it."},
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
    """Le soglie in uso e il file dove restano. Tutto passa da qui, sempre con il lucchetto."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.values = config_defaults()
        self.saved = False  # esiste un file letto o scritto da noi
        self.save_error = ""
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                document = json.load(f)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as error:
            self._set_aside("illeggibile (%s)" % error)
            return
        stored = document.get("values") if isinstance(document, dict) and isinstance(document.get("values"), dict) else document
        if not isinstance(stored, dict):
            self._set_aside("non è un elenco di impostazioni")
            return
        for spec in CONFIG_SPEC:
            if spec["key"] not in stored:
                continue
            try:
                self.values[spec["key"]] = coerce_config_value(spec, stored[spec["key"]])
            except ValueError as error:
                print("[CONFIG] %s: '%s' ignorata (%s), uso %r" % (self.path, spec["key"], error, self.values[spec["key"]]))
        self.saved = True

    def _set_aside(self, why):
        """Un file rovinato non deve fermare il backend: lo metto da parte (si può guardare) e riparto dai valori di sempre."""
        target = "%s.damaged-%d" % (self.path, int(time.time()))
        try:
            os.replace(self.path, target)
        except OSError:
            target = "(non spostato)"
        print("[CONFIG] %s %s: uso i valori di sempre. Copia: %s" % (self.path, why, target))

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.values)

    def update(self, changes):
        """Applica `changes` {chiave: valore}. Restituisce (errori, chiavi cambiate); con un errore non cambia niente."""
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
            print("[CONFIG] non riesco a salvare %s: %s" % (self.path, error))


brain_config = backendConfig(BRAIN_CONFIG_PATH)


def _git_info(_cache={"at": 0.0, "value": None}):
    """Commit e ramo del repository (best effort, ricordati per un minuto). None se non e' un repository git."""
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
OPENCV_WIDTH = 1080
OPENCV_HEIGHT = 720
# V18: TUTTO a 1080x720 - CPU più alta ma dettaglio massimo


FRONTEND_CANDIDATES = [
    os.path.join(REPO_DIR, "frontend", "klippeye_frontend.html"),  # il posto di sempre (~/klippeye/frontend/)
    # prima del nome KlippEye (release 1.0.x) e prima del repository: si cercano ancora, nel caso
    os.path.join(REPO_DIR, "dashboard", "vzbot_dashboard.html"),
    os.path.join(os.path.dirname(__file__), "vzbot_frontend_original.html"),
    "/home/pi/vzbot_frontend_original.html",
    "./vzbot_frontend_original.html",
    "/home/pi/vzbot_frontend_REAL_FINAL.html"
]

def find_frontend():
    for p in FRONTEND_CANDIDATES:
        if os.path.exists(p):
            return p
    # also check any html in /home/pi/
    try:
        for f in os.listdir("/home/pi"):
            if f.endswith(".html") and ("klippeye" in f.lower() or "vzbot" in f.lower()):
                return os.path.join("/home/pi", f)
    except:
        pass
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


EMERGENCY_PAGE = """<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="8"><title>KlippEye</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#120d22;color:#e8e1ff;font:16px/1.5 system-ui,sans-serif;text-align:center;padding:24px;box-sizing:border-box}
h1{font-size:20px;margin:0 0 8px}p{margin:6px 0;color:#b9afd6;max-width:420px}</style></head><body><div>
<h1>KlippEye sta rimettendo a posto i suoi file</h1>
<p>Dopo uno spegnimento improvviso la pagina della dashboard risulta rovinata. La sto ripristinando da sola: questa pagina si ricarica ogni pochi secondi.</p>
<p>Se non cambia nulla, apri Mainsail &rarr; Machine &rarr; Update Manager &rarr; klippeye &rarr; <b>Recover</b> (hard).</p></div></body></html>"""

# Le operazioni che Moonraker finisce solo a lavoro fatto (aggiornamenti, riavvii di servizi): 10 secondi non bastano.
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

@app.route("/")
def index():
    f = find_frontend()
    if f and not frontend_ok(f):
        ran = run_repair()    # pagina vuota o troncata (blackout): la rimetto a posto adesso, prima di servirla
        f = find_frontend()
        print(f"[REPAIR] {time.strftime('%H:%M:%S')} the page {os.path.basename(str(f))} is damaged: check {'done' if ran else 'skipped (another one just ran)'}")
        if not f or not frontend_ok(f):
            return Response(EMERGENCY_PAGE, status=503, mimetype="text/html", headers={"Retry-After": "8", "Cache-Control": "no-store"})
    if f:
        return send_file(f)
    run_repair()              # file mancante: stessa cosa
    f = find_frontend()
    if f and frontend_ok(f):
        return send_file(f)
    return "frontend/klippeye_frontend.html non trovato in " + REPO_DIR, 404

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
    """Riceve {script: 'G28'} dal frontend e lo manda a Moonraker POST /printer/gcode/script"""
    if request.method == "OPTIONS":
        return "", 200
    try:
        body = request.get_json(force=True, silent=True) or {}
        script = body.get("script") or body.get("gcode") or request.data.decode() if request.data else ""
        if not script:
            # prova anche query param
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
    # se è gcode/script, usa handler dedicato
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











# === MACROS SYSTEM V34 - Metodo V30 che trovava TUTTE le macro + params defaults ===
import glob as globmod
import re as re_global
import os

MACRO_BASE_DIRS = [
    "/home/pi/printer_data/config",
    "/home/pi/klipper_config",
    "/home/pi/klippain_shaketune",
    "/home/pi/klippain_shaketune/shaketune",
]

SHAKETUNE_PATHS = [
    "/home/pi/printer_data/config/shaketune",
    "/home/pi/klipper_config/shaketune",
    "/home/pi/klippain_shaketune",
    "/home/pi/klippain_shaketune/shaketune",
    "/home/pi/klippain_shaketune/config",
]

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
                            "description": "da objects/list (iniettata live)",
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
    for base in SHAKETUNE_PATHS:
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
                                                "description": "Shaketune (da scan cartella)",
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
        
        base_dir = "/home/pi/printer_data/config"
        for bd in MACRO_BASE_DIRS:
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
        
        for base in SHAKETUNE_PATHS:
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

# Prima stava in printer_data/config/vzbot_calibration_selected.json (nessuna macro lo usa): ora e' nella cartella dati.
# I due posti di prima si leggono ancora (niente si perde); si scrive solo qui.
CALIBRATION_SELECTED_FILE = os.path.join(DATA_DIR, "calibration_selected.json")
CALIBRATION_SELECTED_LEGACY = ["/home/pi/printer_data/config/vzbot_calibration_selected.json", "/home/pi/vzbot_calibration_selected.json"]

def load_calibration_selected():
    for fp in [CALIBRATION_SELECTED_FILE] + CALIBRATION_SELECTED_LEGACY:
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
            # Scrivi solo nel primo path riuscito
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
LOGS_DIR = "/home/pi/printer_data/logs"


@app.route("/api/logs/list", methods=["GET"])
def api_logs_list():
    try:
        if not os.path.exists(LOGS_DIR):
            return jsonify({"error": f"logs dir not found: {LOGS_DIR}", "files": []}), 404
        files = []
        for name in os.listdir(LOGS_DIR):
            # ignora *.log.* (vecchi log rotati)
            if ".log." in name:
                continue
            full = os.path.join(LOGS_DIR, name)
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
        # ordina per modified desc (più recenti prima)
        files.sort(key=lambda x: x.get("modified",0), reverse=True)
        return jsonify({"dir": LOGS_DIR, "files": files, "count": len(files)})
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
        full = os.path.join(LOGS_DIR, fname)
        if not os.path.exists(full):
            return jsonify({"error": "file not found"}), 404
        # leggi ultime N righe
        try:
            max_lines = int(request.args.get("lines", "2000"))
        except:
            max_lines = 2000
        max_lines = max(50, min(max_lines, 10000))
        # leggi file efficientemente dal fondo
        try:
            with open(full, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                # prendi ultime max_lines
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
        full = os.path.join(LOGS_DIR, fname)
        if not os.path.exists(full):
            return jsonify({"error": "not found"}), 404
        return send_file(full, as_attachment=True, download_name=fname)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === END LOGS ===


# === AUTO AI ANALYSIS V4 - Soluzione B ===
import json

AI_CONFIG_PATH = os.path.join(DATA_DIR, "ai.json")  # release 1.0: nella cartella dati, permessi 600 (e' una password)
AI_CONFIG_PATH_LEGACY = "/home/pi/vzbot_ai_config.json"  # dove stava prima: si legge ancora, non si scrive piu'
AI_CONFIG_PATH_ALT = os.path.join(os.path.dirname(__file__), "vzbot_ai_config.json")

def load_ai_config():
    for p in [AI_CONFIG_PATH, AI_CONFIG_PATH_LEGACY, AI_CONFIG_PATH_ALT, "/home/pi/vzbot_ai_key.txt"]:
        try:
            if os.path.exists(p):
                if p.endswith('.txt'):
                    # file txt con solo la key
                    with open(p,'r') as f:
                        key=f.read().strip()
                        if key:
                            return {"provider":"openai","api_key":key,"model":"gpt-4o-mini"}
                else:
                    with open(p,'r') as f:
                        j=json.load(f)
                        if "api_key" in j or "key" in j:
                            # normalizza
                            j["api_key"] = j.get("api_key") or j.get("key")
                            j["provider"] = j.get("provider","openai")
                            j["model"] = j.get("model","gpt-4o-mini")
                            return j
        except Exception as e:
            continue
    return None

def get_logs_combined(max_files=25, lines_per_file=400, max_chars=12000):
    """Prende TUTTI i file .log (esclusi *.log.*) con priorità klippy/moonraker"""
    if not os.path.exists(LOGS_DIR):
        return "", []
    files=[]
    try:
        for name in os.listdir(LOGS_DIR):
            if ".log." in name:  # esclude rotati tipo klippy.log.2024-10-01
                continue
            if not name.endswith('.log'):
                # include anche file senza estensione .log? no, solo .log
                # ma includiamo anche .log con prefissi strani
                if '.log' not in name:
                    continue
            full=os.path.join(LOGS_DIR,name)
            if not os.path.isfile(full):
                continue
            try:
                stat=os.stat(full)
                # priorità: klippy e moonraker prima
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
        # ordina per priority desc, poi per mtime desc
        files.sort(key=lambda x: (x[4], x[2]), reverse=True)
        # prendi TUTTI (max_files è alto)
        files=files[:max_files]
    except Exception as e:
        print(f"[LOGS] errore lista: {e}")
        files=[]
    combined=""
    used=[]
    total_chars=0
    for name,full,mtime,size,priority in files:
        try:
            with open(full,'r',encoding='utf-8',errors='ignore') as f:
                lines=f.readlines()
                # linee in base alla priorità - FIX 413 ridotto drasticamente per TPM Groq
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
                # se file vuoto, segnala
                if not chunk.strip():
                    chunk="(file vuoto - 0 byte di contenuto utile)"

                header=f"\n\n===== FILE: {name} ({len(lines)} righe prese, {size} byte totali, priority {priority}) =====\n"
                entry=header+chunk
                # controlla se superiamo max_chars totale
                if total_chars+len(entry) > max_chars and 'klippy' not in name.lower() and 'moonraker' not in name.lower():
                    # per file non critici, se superiamo, saltiamo
                    # ma per klippy/moonraker forziamo sempre
                    if total_chars > max_chars*0.8:
                        continue
                combined+=entry
                total_chars+=len(entry)
                used.append(name)
        except Exception as e:
            combined+=f"\n\n===== FILE: {name} ERRORE LETTURA: {e} =====\n"
            used.append(name)

    # Se ancora troppo lungo, taglia mantenendo inizio (con lista file) e fine (con klippy che è all'inizio per priorità)
    if len(combined)>max_chars:
        # mantieni primi 500 char (lista) + ultimi max_chars-500
        combined = combined[:800] + "\n...[TAGLIO PER LUNGHEZZA, MANTENGO ULTIMI LOG]...\n" + combined[-(max_chars-800):]

    print(f"[LOGS] Combinati {len(used)} file: {used} - tot chars {len(combined)}")
    return combined, used

@app.route("/api/ai/config", methods=["GET","POST"])
def api_ai_config():
    try:
        if request.method=="GET":
            cfg=load_ai_config()
            if not cfg:
                return jsonify({"configured": False, "message": "Nessuna config trovata. Inserisci la chiave dalla dashboard (Config > Log di sistema > ingranaggio) oppure crea %s con {\"api_key\": \"...\", \"provider\": \"openai\"}" % AI_CONFIG_PATH})
            # non esporre key intera
            safe={"provider":cfg.get("provider"),"model":cfg.get("model"),"key_preview": ("…"+cfg.get("api_key","")[-4:]) if cfg.get("api_key") else "", "configured": True}
            return jsonify(safe)
        else:
            body=request.get_json(force=True,silent=True) or {}
            key=body.get("api_key") or body.get("key") or ""
            provider=body.get("provider","openai")
            model=body.get("model","gpt-4o-mini")
            if not key or len(key)<20:
                return jsonify({"error":"api_key troppo corta"}),400
            cfg={"provider":provider,"api_key":key,"model":model}
            # release 1.0: un solo posto (cartella dati), file leggibile solo dall'utente del servizio
            try:
                write_json_atomic(AI_CONFIG_PATH, cfg, private=True)
            except OSError as e:
                return jsonify({"error": "non riesco a salvare la chiave in %s: %s" % (AI_CONFIG_PATH, e)}), 500
            return jsonify({"ok":True,"saved_to":[AI_CONFIG_PATH]})
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.route("/api/logs/analyze", methods=["POST","GET"])
def api_logs_analyze():
    try:
        cfg=load_ai_config()
        if not cfg or not cfg.get("api_key"):
            return jsonify({
                "error":"API key non configurata",
                "howto":"Inserisci la chiave dalla dashboard (Config > Log di sistema > ingranaggio) oppure crea il file %s con contenuto: {\"api_key\": \"sk-...\", \"provider\": \"openai\", \"model\": \"gpt-4o-mini\"} oppure fai POST a /api/ai/config con {\"api_key\": \"...\"}" % AI_CONFIG_PATH,
                "configured": False
            }), 400

        # Supporto singolo file ?file=klippy.log
        single_file = request.args.get('file') or (request.json.get('file') if request.is_json else None)
        is_single = False
        if single_file:
            safe_name = os.path.basename(single_file)
            full = os.path.join(LOGS_DIR, safe_name)
            if ".log." in safe_name or not os.path.isfile(full):
                return jsonify({"error": f"File {safe_name} non trovato"}), 404
            try:
                with open(full,'r',encoding='utf-8',errors='ignore') as f:
                    lines = f.readlines()
                    want = 3500 if 'klippy' in safe_name.lower() else 2500
                    if len(lines) > want:
                        lines = lines[-want:]
                    content = "".join(lines)[-18000:]
                    if not content.strip():
                        content = "(file vuoto)"
                combined = f"===== FILE: {safe_name} ({len(lines)} righe, analisi singola) =====\n" + content
                used_files = [safe_name]
                is_single = True
            except Exception as e:
                return jsonify({"error": f"Errore lettura {safe_name}: {e}"}), 500
        else:
            # FIX 413 - ridotto da 30000 a 12000 char per non superare TPM 8000 di Groq gpt-oss-120b (8000 token limit)
            # 12000 char ~ 3000 token, lascia spazio per prompt
            combined, used_files = get_logs_combined(max_files=20, lines_per_file=400, max_chars=12000)
            if not combined:
                return jsonify({"error":"nessun log trovato"}),404

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
Analyse these system logs taken from printer_data/logs (all the files, not only klippy.log).

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

        # Chiamata AI - supporta openai, meta, groq, together, openrouter, ecc (tutti OpenAI-compat)
        provider = provider.lower()
        # Fix: se hai salvato un modello GPT ma usi Groq/Meta, correggi automaticamente
        if provider in ["groq","meta","llama","llama.com","together","openrouter","fireworks"]:
            if model and "gpt-" in model.lower():
                print(f"[AI-FIX] Modello {model} non valido per {provider}, uso default Llama")
                model = None

        # Mappa provider -> endpoint base e modello default
        provider_map = {
            "openai": ("https://api.openai.com/v1/chat/completions", model or "gpt-4o-mini"),
            "meta": ("https://api.llama.com/compat/v1/chat/completions", model or "Llama-4-Maverick-17B-128E-Instruct-FP8"),
            "llama": ("https://api.llama.com/compat/v1/chat/completions", model or "Llama-4-Maverick-17B-128E-Instruct-FP8"),
            "llama.com": ("https://api.llama.com/compat/v1/chat/completions", model or "Llama-4-Maverick-17B-128E-Instruct-FP8"),
            "groq": ("https://api.groq.com/openai/v1/chat/completions", model or "openai/gpt-oss-20b"),  # FIX 413: gpt-oss-120b ha TPM 8000 troppo basso, uso llama-3.3 con TPM più alto
            "together": ("https://api.together.xyz/v1/chat/completions", model or "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"),
            "openrouter": ("https://openrouter.ai/api/v1/chat/completions", model or "meta-llama/llama-3.3-70b-instruct"),
            "fireworks": ("https://api.fireworks.ai/inference/v1/chat/completions", model or "accounts/fireworks/models/llama-v3p3-70b-instruct"),
        }
        endpoint, final_model = provider_map.get(provider, (f"https://api.openai.com/v1/chat/completions", model or "gpt-4o-mini"))
        # Sicurezza extra: se final_model contiene gpt e provider è groq, forza llama
        if provider=="groq" and final_model.lower() in ["llama-3.1-8b-instant","llama3-70b-8192","llama3-8b-8192"]:
            final_model="openai/gpt-oss-20b"
        # Se final_model è ancora vecchio llama su groq, forza nuovo
        if provider=="groq" and "gpt-oss" in final_model:
            final_model="openai/gpt-oss-20b"  # FIX 413
        if provider in ["meta","llama"] and "gpt" in final_model.lower():
            final_model="Llama-4-Maverick-17B-128E-Instruct-FP8"


        # Per Meta API serve anche base_url diverso se usato api.meta.ai (nuovo)
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
            # Supporta sia choices[0].message.content che altri formati
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
try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError as e:
    cv2 = None
    np = None
    HAS_CV2 = False
    print(f"[OPENCV] cv2/numpy non installati, detector disabilitato: {e} - installa con: pip install opencv-python-headless numpy")

# --- storico degli allarmi: cosa ha visto il monitor e cosa ha detto l'IA, con le foto (cosi' si capisce quanti erano veri) ---
ALERT_HISTORY_DIR = os.path.join(DATA_DIR, "alerts")
ALERT_HISTORY_KEEP = 40  # eventi con foto
REFERENCE_SAMPLES = 7  # foto dello sfondo (mediana)
REFERENCE_MIN = 5  # sotto questo numero il confronto non e' pronto
GLOBAL_STREAK_MAX = 10  # controlli di fila con il cambio "globale" prima di considerarlo vero
_history_lock = threading.Lock()


def record_alert(event, image_path=None, reference_path=None):
    """Adds an event to <data>/alerts/history.jsonl and copies the pictures next to it. Must never make the monitor fail."""
    try:
        with _history_lock:
            os.makedirs(ALERT_HISTORY_DIR, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            event = dict(event, time=time.strftime("%Y-%m-%d %H:%M:%S"), id=stamp)
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
    """Tiene le ultime `keep` foto di allarme in /tmp e toglie le altre (ognuna e' ~100 KB e prima non si cancellavano mai)."""
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


class LightDetector:
    def __init__(self):
        self.enabled = True  # AUTO-ENABLED
        self.running = False
        self.thread = None
        self.generation = 0  # ogni start() ne apre una nuova: un vecchio ciclo ancora addormentato capisce da solo di dover finire
        self.last_frames = deque(maxlen=5)
        self.roi = None
        # Le soglie qui sotto sono i valori di sempre; subito dopo la creazione apply_config() mette quelli salvati
        # (brain.json) e da allora li cambia la dashboard: /api/backend/config.
        self.sensitivity = 35  # V18: alzata da 25 a 35 per meno falsi positivi
        self.trigger_count = 0
        self.trigger_threshold = 3
        self.cooldown_until = 0
        self.cooldown_sec = 90  # cooldown più lungo per non spammare Groq
        self.last_ai_call = 0
        self.ai_cooldown = 120  # 120s tra chiamate AI
        self.score_threshold = 2.5  # % della fascia esterna che deve muoversi (V18: da 1.5 a 2.5)
        self.check_interval = 3  # secondi tra due controlli
        self.border = 0.25  # larghezza della fascia esterna, frazione dell'area controllata
        self.warmup = 90  # secondi di stampa prima di cominciare a controllare
        self.min_progress = 2  # % di avanzamento prima di cominciare a controllare
        self.hotend_tol = 8  # scarto massimo dell'ugello dalla temperatura impostata
        self.ai_model = ""  # vuoto: il modello predefinito del servizio
        self.persistent_filter = True  # filtro anti falsi allarmi (vedi _persistent_score)
        self.persist_checks = 3
        self.reference_seconds = 60
        self.global_change = 30.0
        self.ai_min_confidence = 70
        self.ai_send_reference = True
        self.recent_masks = deque(maxlen=3)
        self.ref_small = deque(maxlen=REFERENCE_SAMPLES)  # (istante, foto piccola in grigio) per lo sfondo
        self.ref_jpegs = deque(maxlen=REFERENCE_SAMPLES)  # (istante, foto com'e' arrivata dalla camera) per mostrare all'IA "com'era prima"
        self.bg = None
        self.global_streak = 0
        self.stats = {
            "frames_checked": 0,
            "anomalies": 0,
            "last_trigger": None,
            "last_score": 0,
            "status": "idle - in attesa stampa"
        }
        self.last_alert_img_path = None
        self.last_analysis = None  # ultimo risultato AI formattato

    def set_roi(self, x, y, w, h):
        self.roi = (x,y,w,h)

    def apply_config(self, values):
        """Mette in uso le soglie (dict di backendConfig). Vale dal controllo successivo, senza riavviare niente."""
        self.sensitivity = values["sensitivity"]
        self.score_threshold = values["score_threshold"]
        self.trigger_threshold = values["trigger_count"]
        self.check_interval = values["check_interval"]
        self.border = values["border"] / 100.0
        self.cooldown_sec = values["cooldown"]
        self.ai_cooldown = values["ai_cooldown"]
        self.warmup = values["warmup_seconds"]
        self.min_progress = values["min_progress"]
        self.hotend_tol = values["hotend_tolerance"]
        self.ai_model = values["ai_model"]
        self.persistent_filter = values["persistent_filter"]
        if values["persist_checks"] != self.persist_checks or self.recent_masks.maxlen != values["persist_checks"]:
            self.recent_masks = deque(maxlen=values["persist_checks"])
        self.persist_checks = values["persist_checks"]
        self.reference_seconds = values["reference_seconds"]
        self.global_change = values["global_change"]
        self.ai_min_confidence = values["ai_min_confidence"]
        self.ai_send_reference = values["ai_send_reference"]
        x, y, w, h = values["roi"]  # in % dell'immagine -> pixel dell'immagine ridimensionata (1080x720)
        self.roi = (int(OPENCV_WIDTH * x / 100), int(OPENCV_HEIGHT * y / 100), int(OPENCV_WIDTH * w / 100), int(OPENCV_HEIGHT * h / 100))

    def start(self):
        if not HAS_CV2:
            print("[OPENCV] Impossibile avviare, cv2 mancante")
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
        """Dorme `seconds` ma si sveglia subito se il rilevatore e' stato fermato o riavviato: un vecchio ciclo non resta in giro."""
        end = time.time() + seconds
        while time.time() < end and self.running and generation == self.generation:
            time.sleep(min(0.1, max(0.0, end - time.time())))

    def loop(self, generation=None):
        if generation is None:
            generation = self.generation
        while self.running and generation == self.generation:
            try:
                if not HAS_CV2:
                    self.stats["status"] = "cv2 non installato"
                    self._nap(generation, 5)
                    continue
                if not self.enabled:
                    self._nap(generation, 1)
                    continue
                # Cooldown check
                if time.time() < self.cooldown_until:
                    self.stats["status"] = f"cooldown {int(self.cooldown_until - time.time())}s"
                    self._nap(generation, 1)
                    continue
                # Check if printing
                # === SOLUZIONE 5 - IBRIDA - CHECK STAMPA REALE ===
                try:
                    pr = requests.get(f"{MOONRAKER_URL}/printer/objects/query?print_stats&extruder&display_status&virtual_sdcard&toolhead&heater_bed", timeout=3).json()
                    status = pr.get("result",{}).get("status",{})
                    ps = status.get("print_stats",{})
                    extr = status.get("extruder",{})
                    disp = status.get("display_status",{})
                    v_sd = status.get("virtual_sdcard",{})
                    tool = status.get("toolhead",{})
                    bed = status.get("heater_bed",{})
                    state = ps.get("state","")

                    if state != "printing":
                        self._reset_reference()  # una stampa nuova riparte con uno sfondo nuovo
                        self.stats["status"] = f"idle (state={state})"
                        self.stats["real_print_started"] = False
                        self.stats["real_print_reason"] = f"state={state}"
                        self._nap(generation, 5)
                        continue

                    # Calcola se stampa reale iniziata
                    progress = disp.get("progress",0)  # 0-1
                    temp_h = extr.get("temperature",0)
                    target_h = extr.get("target",0)
                    temp_b = bed.get("temperature",0)
                    target_b = bed.get("target",0)
                    file_pos = v_sd.get("file_position",0)
                    file_size = v_sd.get("file_size",1)
                    file_progress = file_pos / file_size if file_size>0 else 0
                    total_dur = ps.get("total_duration",0)

                    # Criteri per stampa reale
                    reasons = []
                    real_started = True

                    # 1. Progress deve superare la soglia (di serie 2%; il file la meta' di quella)
                    if progress < self.min_progress/100 and file_progress < self.min_progress/200:
                        real_started = False
                        reasons.append(f"progress {progress*100:.1f}% <{self.min_progress:g}%")
                    # 2. Hotend deve essere vicino al target
                    if target_h > 0 and abs(temp_h - target_h) > self.hotend_tol:
                        real_started = False
                        reasons.append(f"hotend {temp_h:.0f}/{target_h:.0f}C non a temp")
                    # 3. Bed vicino a target se ha target
                    if target_b > 0 and abs(temp_b - target_b) > 10:
                        # Non blocchiamo per bed, ma logghiamo
                        reasons.append(f"bed {temp_b:.0f}/{target_b:.0f}C non a temp")
                    # 4. Deve aver passato almeno N secondi di stampa (di serie 90: riscaldamento+mesh spesso <60s)
                    if total_dur < self.warmup:
                        real_started = False
                        reasons.append(f"durata {total_dur:.0f}s <{self.warmup}s")
                    # 5. Toolhead Z: se è ancora alto >10mm probabilmente è in mesh/homing
                    try:
                        z_pos = tool.get("position",[0,0,0])[2] if tool.get("position") else 0
                        if z_pos > 15:
                            reasons.append(f"Z={z_pos:.1f}mm alto (mesh?)")
                    except:
                        pass

                    self.stats["real_print_started"] = real_started
                    self.stats["real_print_reason"] = "; ".join(reasons) if reasons else "ok - stampa reale"
                    self.stats["progress"] = progress
                    self.stats["file_progress"] = file_progress
                    self.stats["total_duration"] = total_dur

                    if not real_started:
                        self.stats["status"] = f"riscaldamento/mesh - attesa stampa reale ({'; '.join(reasons)[:80]})"
                        self._nap(generation, 3)
                        continue

                except Exception as e:
                    print(f"[DETECTOR] real_print check err: {e}")
                    self._nap(generation, 3)
                    continue

                # Get snapshot low-res
                try:
                    r = requests.get(f"{CAMERA_NGINX_URL}/snapshot", timeout=4)
                    if not r.ok or len(r.content) < 1000:
                        self._nap(generation, 2)
                        continue
                    img_arr = np.frombuffer(r.content, np.uint8)
                    frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
                    if frame is None:
                        self._nap(generation, 2)
                        continue
                except Exception as e:
                    print(f"[OPENCV] snapshot fail: {e}")
                    self._nap(generation, 3)
                    continue

                score = self._persistent_score(frame, r.content) if self.persistent_filter else self._motion_score(frame)
                if score is None:  # il confronto non e' ancora pronto, oppure il controllo e' da ignorare (cambio di luce)
                    self._nap(generation, self.check_interval)
                    continue
                self.stats["last_score"] = round(score, 2)

                # Soglia: se piu' del 2.5% (di serie) di pixel in periferia si muove = sospetto
                if score > self.score_threshold:  # V18: da 1.5% a 2.5% per ridurre falsi positivi
                    self.trigger_count += 1
                    self.stats["anomalies"] += 1
                    print(f"[OPENCV] Anomalia {self.trigger_count}/{self.trigger_threshold} score={score:.2f}%")
                else:
                    self.trigger_count = max(0, self.trigger_count-1)

                if self.trigger_count >= self.trigger_threshold:
                    # TRIGGER!
                    print(f"[OPENCV] TRIGGER spaghetti! score={score:.2f}%")
                    self.stats["last_trigger"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    self.stats["status"] = f"TRIGGERED score={score:.2f}%"
                    self.cooldown_until = time.time() + self.cooldown_sec
                    self.trigger_count = 0
                    # Salva immagine full-res per AI
                    try:
                        prune_alert_images(keep=20)  # le foto degli allarmi vecchie non si accumulano per sempre (adesso + prima)
                        full_path = f"/tmp/klippeye_alert_{int(time.time())}.jpg"
                        # Riscarica e ridimensiona a 1080x720 per AI - V17 anti-falso positivo
                        r_full = requests.get(f"{CAMERA_NGINX_URL}/snapshot", timeout=5)
                        if r_full.ok:
                            try:
                                # Resize a 1080x720 con qualità 85% per dettaglio piatto
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
                            # Auto-chiama AI analysis in background (non blocca loop)
                            ref_path, ref_age = self._save_reference(full_path)
                            threading.Thread(target=self.call_ai_analysis, args=(full_path, ref_path, ref_age), daemon=True).start()
                    except Exception as e:
                        print(f"[OPENCV] save alert fail: {e}")

                self._nap(generation, self.check_interval)  # check ogni 3s di serie (la dashboard: Monitor IA > Ogni quanto guarda la camera)

            except Exception as e:
                print(f"[OPENCV] loop error: {e}")
                self._nap(generation, 3)

    def _motion_score(self, frame):
        """Il rilevamento di prima (filtro spento): quanto si muove la fascia esterna fra due foto di fila, in % dell'area."""
        # Resize a 1080x720 per dettaglio - V18 FULL HD (6-11% CPU)
        small = cv2.resize(frame, (OPENCV_WIDTH, OPENCV_HEIGHT))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        self.last_frames.append(gray)
        self.stats["frames_checked"] += 1
        self.stats["status"] = "scanning"

        if len(self.last_frames) < 3:
            return None

        # Confronto con frame precedente (background subtraction semplice)
        prev = self.last_frames[-2]
        diff = cv2.absdiff(prev, gray)
        thresh = cv2.threshold(diff, self.sensitivity, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        return self._periphery_score(thresh, 1.0)

    def _roi_rect(self, shape, scale):
        """L'area controllata (pixel dell'immagine 1080x720) portata alla scala dell'immagine che si sta guardando."""
        h, w = shape[:2]
        if self.roi is None:
            return int(w * 0.2), int(h * 0.2), int(w * 0.6), int(h * 0.6)
        x, y, rw, rh = self.roi
        return int(x * scale), int(y * scale), int(rw * scale), int(rh * scale)

    def _periphery_mask(self, h, w):
        border = self.border  # fascia esterna: di serie il 25% (0.25 / 0.75)
        mask = np.zeros((h, w), np.uint8)
        mask[:int(h * border), :] = 255  # alto
        mask[int(h * (1 - border)):, :] = 255  # basso
        mask[:, :int(w * border)] = 255  # sinistra
        mask[:, int(w * (1 - border)):] = 255  # destra
        return mask

    def _periphery_score(self, thresh, scale):
        """% dell'area controllata coperta da punti "cambiati" nella fascia esterna."""
        x, y, rw, rh = self._roi_rect(thresh.shape, scale)
        roi_thresh = thresh[y:y + rh, x:x + rw]
        h_roi, w_roi = roi_thresh.shape
        if h_roi == 0 or w_roi == 0:
            return 0.0
        moved = cv2.bitwise_and(roi_thresh, roi_thresh, mask=self._periphery_mask(h_roi, w_roi))
        return (cv2.countNonZero(moved) / (w_roi * h_roi)) * 100

    def _save_reference(self, adesso_path):
        """La foto "di prima" per l'IA: la piu' vecchia fra quelle dello sfondo (~reference_seconds fa). -> (percorso, eta' in secondi) o (None, None)."""
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
            print(f"[OPENCV] foto di prima non salvata: {error}")
            return None, None

    def _reset_reference(self):
        self.ref_small.clear()
        self.ref_jpegs.clear()
        self.recent_masks.clear()
        self.bg = None
        self.global_streak = 0

    def _persistent_score(self, frame, raw):
        """
        Il filtro anti falsi allarmi. Invece di confrontare due foto di fila (basta la testina che passa per far scattare tutto):
          1. lo SFONDO e' la mediana di 7 foto sparse negli ultimi `reference_seconds`: cio' che sta in un punto solo per poco
             (testina, mano, riflesso) non ne fa parte;
          2. la luminosita' media viene allineata a quella dello sfondo (la camera che regola l'esposizione non e' un movimento);
          3. se cambia piu' di `global_change`% dell'intera immagine di colpo (luce, camera mossa) il controllo si ignora, ma se dura
             piu' di GLOBAL_STREAK_MAX controlli di fila e' un cambiamento vero;
          4. conta solo cio' che, nella fascia esterna dell'area, e' cambiato rispetto allo sfondo in TUTTI gli ultimi `persist_checks` controlli.
        Lavora a meta' risoluzione: 4 volte meno punti da guardare di prima. -> % dell'area, oppure None (niente da contare adesso).
        """
        now = time.time()
        small = cv2.resize(frame, (OPENCV_WIDTH // 2, OPENCV_HEIGHT // 2), interpolation=cv2.INTER_AREA)
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (11, 11), 0)
        self.stats["frames_checked"] += 1
        if self.ref_small and now - self.ref_small[-1][0] > 2 * self.reference_seconds:
            self._reset_reference()  # una lunga pausa: lo sfondo vecchio non vale piu'
        result = None
        if self.bg is not None and self.bg.shape == gray.shape:
            result = self._compare_with_background(gray)
        else:
            self.stats["status"] = "preparo il confronto (%d/%d foto)" % (len(self.ref_small), REFERENCE_MIN)
        step = max(self.check_interval, self.reference_seconds / REFERENCE_SAMPLES)
        if not self.ref_small or now - self.ref_small[-1][0] >= step:
            self.ref_small.append((now, gray))
            self.ref_jpegs.append((now, raw))
            if len(self.ref_small) >= REFERENCE_MIN:
                self.bg = np.median(np.stack([g for _, g in self.ref_small]), axis=0).astype(np.uint8)
        return result

    def _compare_with_background(self, gray):
        shift = float(gray.mean()) - float(self.bg.mean())
        if abs(shift) > 1:
            gray = cv2.convertScaleAbs(gray, alpha=1.0, beta=-shift)
        thresh = cv2.threshold(cv2.absdiff(self.bg, gray), self.sensitivity, 255, cv2.THRESH_BINARY)[1]
        changed = cv2.countNonZero(thresh) * 100.0 / thresh.size
        self.stats["global_change"] = round(changed, 1)
        if changed > self.global_change:
            self.global_streak += 1
            self.recent_masks.clear()
            if self.global_streak < GLOBAL_STREAK_MAX:
                self.stats["ignored_global"] = self.stats.get("ignored_global", 0) + 1
                self.stats["status"] = f"cambio di luce o camera mossa ({changed:.0f}% dell'immagine): ignoro"
                return None
            self.stats["status"] = "scanning (cambiamento grande e persistente)"
            return changed  # dura da molti controlli: non e' un lampo di luce
        self.global_streak = 0
        thresh = cv2.dilate(thresh, None, iterations=1)
        x, y, rw, rh = self._roi_rect(thresh.shape, 0.5)
        roi = thresh[y:y + rh, x:x + rw]
        if roi.size == 0:
            return 0.0
        if self.recent_masks and self.recent_masks[-1].shape != roi.shape:
            self.recent_masks.clear()  # l'area e' stata cambiata dal menu
        self.recent_masks.append(roi)
        self.stats["status"] = "scanning"
        if len(self.recent_masks) < self.recent_masks.maxlen:
            return 0.0
        persistent = self.recent_masks[0]
        for other in list(self.recent_masks)[1:]:
            persistent = cv2.bitwise_and(persistent, other)
        h_roi, w_roi = persistent.shape
        stays = cv2.bitwise_and(persistent, persistent, mask=self._periphery_mask(h_roi, w_roi))
        return (cv2.countNonZero(stays) / (w_roi * h_roi)) * 100

    def call_ai_analysis(self, img_path, ref_path=None, ref_age=None):
        """Chiede all'IA di guardare la foto (e, se c'e', com'era prima) quando il monitor scatta, senza intervento umano."""
        score = self.stats.get("last_score", 0)
        try:
            now = time.time()
            if now - self.last_ai_call < self.ai_cooldown:
                print(f"[OPENCV] AI cooldown attivo, salto (mancano {int(self.ai_cooldown - (now-self.last_ai_call))}s)")
                record_alert({"outcome": "skipped: AI cooldown not over", "score": score}, img_path, ref_path)
                return
            self.last_ai_call = now
            print(f"[OPENCV] AUTO-CHIAMATA IA per {img_path}")

            # Leggi immagine e converti base64
            if not os.path.exists(img_path):
                print(f"[OPENCV] img non trovata {img_path}")
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
                print("[OPENCV] No API key per AI auto-call")
                record_alert({"outcome": "skipped: no AI key", "score": score}, img_path, ref_path)
                return

            provider = cfg.get("provider","groq").lower()
            api_key = cfg.get("api_key")
            endpoint = "https://api.groq.com/openai/v1/chat/completions"
            final_model = "qwen/qwen3.8-27b"
            if provider == "openai":
                endpoint = "https://api.openai.com/v1/chat/completions"
                final_model = "gpt-4o-mini"
            if self.ai_model:  # scelto dalla dashboard (Monitor IA): vince su quello predefinito del servizio
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
                # alcuni servizi/modelli accettano una sola foto (o hanno un limite di dati): riprovo con la sola foto di adesso
                print(f"[OPENCV] IA ha rifiutato due foto ({r.status_code}): riprovo con una sola")
                used_reference = False
                r = ask(False)
            if not r.ok:
                print(f"[OPENCV] IA error {r.status_code}: {r.text[:500]}")
                record_alert({"outcome": f"AI error {r.status_code}", "score": score, "model": final_model}, img_path, ref_path)
                return
            j = r.json()
            answer = j["choices"][0]["message"]["content"] if "choices" in j else str(j)
            print(f"[OPENCV] AI Risposta: {answer[:500]}")

            # Parsa JSON
            parsed = None
            try:
                parsed = json.loads(answer)
                if isinstance(parsed, dict) and "spaghetti" not in parsed:
                    for v in parsed.values():  # a volte la risposta e' dentro un altro oggetto
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
                print(f"[OPENCV] AI analysis salvata: {parsed}")
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

detector = LightDetector()
detector.apply_config(brain_config.snapshot())  # le soglie salvate (o quelle di sempre) valgono dal primo controllo


def set_brain_config(changes):
    """Cambia delle soglie: le controlla, le salva in brain.json e le mette in uso. -> (errori, chiavi cambiate)."""
    errors, changed = brain_config.update(changes)
    if errors:
        return errors, changed
    values = brain_config.snapshot()
    detector.apply_config(values)
    if "enabled" in changed:
        if values["enabled"]:
            detector.start()
        else:
            detector.stop()
    return errors, changed


@app.route("/api/version", methods=["GET"])
def api_version():
    """Chi sono: release (file VERSION), livello dell'interfaccia, commit del repository, da quanto sono acceso."""
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
        "legacy": LEGACY_INSTALL,  # True: sta ancora in ~/vzbot (servizio "vzbot"): la dashboard propone il passaggio a KlippEye
    })


# === PASSAGGIO A KLIPPEYE: dal vecchio nome (~/vzbot, servizio "vzbot") al nuovo ===================================
# Chi ha installato la 1.0.x ha cartella, dati e servizi che si chiamano "vzbot". L'aggiornamento normale porta qui il codice
# nuovo senza spostare niente (il servizio vecchio continua a partire, grazie al file brain/vzbot_brain.py, che lancia questo
# file). Lo spostamento vero lo fa scripts/passa-a-klippeye.sh: la dashboard lo lancia con il pulsante "Passa a KlippEye"
# (/api/migrate/start) e ne segue i passi (/api/migrate/status); da terminale: bash ~/vzbot/scripts/passa-a-klippeye.sh.
LEGACY_INSTALL = os.path.basename(REPO_DIR).lower() == "vzbot"
MIGRATION_SCRIPT = os.path.join(REPO_DIR, "scripts", "passa-a-klippeye.sh")
MIGRATION_STATUS_PATH = os.environ.get("KLIPPEYE_MIGRATION_STATUS") or os.path.join(tempfile.gettempdir(), "klippeye-migrazione.json")
MIGRATION_SUDO = os.environ.get("KLIPPEYE_SUDO", "sudo")  # "" = niente sudo (prove, o se il servizio gira gia' come amministratore)
MIGRATION_LAUNCHER = os.environ.get("KLIPPEYE_MIGRATION_LAUNCHER", "")  # solo per le prove: al posto di "sudo systemd-run ..."
MIGRATION_COMMAND = "bash ~/%s/scripts/passa-a-klippeye.sh" % os.path.basename(REPO_DIR)


def read_migration_status():
    """Lo stato scritto dallo script: {"state": "none" | "running" | "done" | "error", "step", "steps", "message"}."""
    try:
        with open(MIGRATION_STATUS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("state") in ("running", "done", "error"):
            if data["state"] == "running" and time.time() - float(data.get("time") or 0) > 900:
                return {"state": "error", "step": data.get("step", 0), "steps": data.get("steps", 6), "message": "Lo script non da' piu' notizie da 15 minuti."}
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {"state": "none"}


def _is_printing_now():
    try:
        r = requests.get(f"{MOONRAKER_URL}/printer/objects/query?print_stats=state", timeout=4).json()
        return r["result"]["status"]["print_stats"]["state"] in ("printing", "paused")
    except Exception:
        return False


@app.route("/api/migrate/status", methods=["GET"])
def api_migrate_status():
    response = jsonify(dict(read_migration_status(), ok=True, legacy=LEGACY_INSTALL, command=MIGRATION_COMMAND))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/migrate/start", methods=["POST"])
def api_migrate_start():
    """Lancia lo script del passaggio, staccato dal servizio (che lo script stesso fermera' e ricreera' col nuovo nome)."""
    if not LEGACY_INSTALL:
        return jsonify({"ok": False, "error": "Sei gia' in ~/klippeye: non c'e' niente da spostare."}), 400
    if not os.path.isfile(MIGRATION_SCRIPT):
        return jsonify({"ok": False, "error": "Manca scripts/passa-a-klippeye.sh: aggiorna prima KlippEye.", "command": MIGRATION_COMMAND}), 500
    if read_migration_status()["state"] == "running":
        return jsonify({"ok": False, "error": "Il passaggio e' gia' in corso."}), 409
    if _is_printing_now():
        return jsonify({"ok": False, "error": "Sta stampando: il passaggio riavvia il backend e Moonraker. Aspetta la fine della stampa."}), 409
    sudo = [MIGRATION_SUDO] if MIGRATION_SUDO else []
    if MIGRATION_LAUNCHER:
        command = MIGRATION_LAUNCHER.split() + ["bash", MIGRATION_SCRIPT, "--dal-backend"]
    else:
        if sudo and subprocess.run(sudo + ["-n", "true"], capture_output=True).returncode != 0:
            return jsonify({"ok": False, "error": "no_sudo", "command": MIGRATION_COMMAND,
                            "message": "Qui non posso farlo da solo (serve la password di amministratore). Da terminale: " + MIGRATION_COMMAND}), 501
        user = __import__("pwd").getpwuid(os.getuid()).pw_name
        env = ["--setenv=HOME=" + os.path.expanduser("~"), "--setenv=PATH=" + os.environ.get("PATH", "/usr/bin:/bin")]
        env += ["--setenv=%s=%s" % (k, v) for k, v in os.environ.items() if k.startswith("KLIPPEYE_") or k.startswith("VZBOT_")]
        command = sudo + ["systemd-run", "--unit=klippeye-passaggio", "--collect", "--uid=" + user, "--working-directory=/tmp"] + env + \
                  ["bash", MIGRATION_SCRIPT, "--dal-backend"]
    try:
        with open(MIGRATION_STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump({"state": "running", "step": 0, "steps": 6, "message": "Parto...", "time": time.time()}, f)
        subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, cwd="/tmp")
    except Exception as e:
        return jsonify({"ok": False, "error": "Non riesco a lanciare lo script: %s" % e, "command": MIGRATION_COMMAND}), 500
    return jsonify({"ok": True, "started": True})
# === fine PASSAGGIO A KLIPPEYE ============================================================================


# === APP ANDROID: l'APK che GitHub costruisce (apk/KlippEye.apk + apk/version.json) ===============================
APK_DIR = os.path.join(REPO_DIR, "apk")
APK_PATH = os.path.join(APK_DIR, "KlippEye.apk")
APK_INFO_PATH = os.path.join(APK_DIR, "version.json")
APK_MIMETYPE = "application/vnd.android.package-archive"
_APK_VERSION_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{1,2})$")
_APK_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_apk_cache = {"key": None, "value": None}
_apk_lock = threading.Lock()


def _apk_code(version):
    """1.2.3 -> 10203: la stessa formula di android/app/build.gradle (None se il formato non va)."""
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
    Cosa offre il backend al telefono: {"available": True, "version", "code", "size", "sha256", "built", "url"} oppure
    {"available": False, "reason": ...}. Il file apk/version.json e' scritto da GitHub insieme all'APK; qui si controlla che
    i due vadano d'accordo (grandezza e impronta SHA-256 del file vero), cosi' un aggiornamento a meta' o un file rovinato
    non arriva mai al telefono. Il calcolo (qualche decimo di secondo sul Raspberry) si rifa' solo se i file cambiano.
    """
    try:
        info_stat, apk_stat = os.stat(APK_INFO_PATH), os.stat(APK_PATH)
    except OSError:
        return {"available": False, "reason": "nessuna app pubblicata"}
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
        return {"available": False, "reason": "apk/version.json non si legge"}
    if not isinstance(data, dict):
        return {"available": False, "reason": "apk/version.json non e' valido"}
    version, sha = data.get("version"), str(data.get("sha256") or "").lower()
    if not isinstance(version, str) or _apk_code(version) is None or not _APK_SHA_RE.match(sha):
        return {"available": False, "reason": "apk/version.json non e' valido"}
    if data.get("size") != apk_size:
        return {"available": False, "reason": "l'APK non corrisponde a version.json (aggiornamento a meta'?)"}
    try:
        actual = _apk_sha256(APK_PATH)
    except OSError:
        return {"available": False, "reason": "l'APK non si legge"}
    if actual != sha:
        return {"available": False, "reason": "l'APK non corrisponde a version.json (impronta diversa)"}
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
    """L'app Android che il backend puo' dare al telefono (vedi read_apk_info). Mai in cache: dopo un aggiornamento cambia."""
    response = jsonify(dict(read_apk_info(), ok=True))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/app/KlippEye.apk", methods=["GET"])
@app.route("/app/VzBot.apk", methods=["GET"])  # lo stesso file: l'app con il vecchio nome (VzBot 1.0.x) cerca l'aggiornamento li'
def app_apk():
    """Il file dell'app. Si da' solo se e' coerente con version.json (grandezza e impronta), altrimenti 404 con il motivo."""
    info = read_apk_info()
    if not info["available"]:
        return jsonify({"ok": False, "error": info["reason"]}), 404
    response = send_file(APK_PATH, mimetype=APK_MIMETYPE, as_attachment=True, download_name="KlippEye-%s.apk" % info["version"], conditional=True, max_age=0)
    response.headers["Cache-Control"] = "no-store"
    return response
# === fine APP ANDROID ==================================================================================


# === LOGHI DELLA STAMPANTE: la cartella logos/ del repository ==================================================
# La dashboard puo' mostrare nella barra in alto il logo di VzBot, Voron o RatRig (Impostazioni -> Stampante). I file ufficiali
# si mettono in logos/ (voron.svg, ratrig.png...) e arrivano col normale aggiornamento: nessuna ricostruzione della dashboard.
LOGOS_DIR = os.path.join(REPO_DIR, "logos")
LOGO_BRANDS = ("vzbot", "voron", "ratrig")
LOGO_FILE_RE = re.compile(r"^(vzbot|voron|ratrig)\.(svg|png|webp)$")
LOGO_MIMETYPES = {"svg": "image/svg+xml", "png": "image/png", "webp": "image/webp"}
LOGO_MAX_BYTES = 2 * 1024 * 1024
LOGO_EXT_ORDER = ("svg", "png", "webp")  # se ce ne sono due della stessa marca vince il primo


def list_logo_files():
    """I loghi presenti, un file per marca: ["voron.svg", ...] (ignora nomi diversi, cartelle e file troppo grandi)."""
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
    """Un logo della cartella logos/ (solo i nomi previsti: vzbot|voron|ratrig . svg|png|webp)."""
    if name not in list_logo_files():
        return jsonify({"ok": False, "error": "logo non trovato"}), 404
    response = send_file(os.path.join(LOGOS_DIR, name), mimetype=LOGO_MIMETYPES[name.rsplit(".", 1)[1]], conditional=True, max_age=0)
    # un SVG aperto da solo non deve poter eseguire script; dentro un <img> non lo fa comunque
    response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-cache"
    return response
# === fine LOGHI DELLA STAMPANTE ===========================================================================


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
    """Le soglie del monitor IA con tutto quello che serve per disegnare il menu (etichette, limiti, valori di sempre)."""
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
    """{"values": {chiave: valore, ...}}: solo le chiavi indicate. Se un valore non va non cambia niente (400 + errors)."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return brain_config_reply(False, 400, errors={"_": "serve un oggetto JSON"})
    changes = body.get("values") if isinstance(body.get("values"), dict) else body
    errors, changed = set_brain_config(changes)
    if errors:
        return brain_config_reply(False, 400, errors=errors)
    return brain_config_reply(changed=changed)


@app.route("/api/backend/config/reset", methods=["POST"])
def api_brain_config_reset():
    """Torna ai valori di sempre: tutti, oppure solo {"keys": [...]}."""
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
    # Vecchio endpoint, tenuto uguale per chi lo usa: ora passa dalle impostazioni, quindi la modifica resta salvata.
    # (Il menu della dashboard usa /api/backend/config.) roi = [x,y,w,h] in pixel dell'immagine 1080x720.
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
        if errors:  # un valore non accettabile (es. area fuori dall'immagine): si lascia com'era, come faceva il try/except di prima
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
    """Gli ultimi allarmi del monitor (con il verdetto dell'IA e i nomi delle foto), dal piu' recente."""
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
    """Ritorna ultima analisi AI pretty JSON - per dashboard auto"""
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
    Analizza stampa in corso: snapshot camera + telemetria
    Stesso approccio dei log ma con visione
    """
    try:
        cfg = load_ai_config()
        if not cfg.get("api_key"):
            return jsonify({"error":"API Key non configurata, vai in LOGS SISTEMA > ⚙️ e inserisci Groq/OpenAI key", "howto":"Usa stessa key dei log"}), 401

        # 1. Snapshot camera - V17 resize a 1080x720 per dettaglio piatto vuoto
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
            return jsonify({"error":"Impossibile catturare snapshot camera, verifica camera in Home"}), 500

        # 2. Telemetria stampa
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

        # 3. Prompt per vision - SOLUZIONE 5 ibrida
        # Calcola real_print_started anche qui per prompt
        real_print_started = False
        real_reason = ""
        try:
            file_pos = v_sd.get("file_position",0)
            file_size = v_sd.get("file_size",1)
            file_progress = file_pos / file_size if file_size>0 else 0
            total_dur = print_stats.get("total_duration",0)
            progress_frac = progress/100 if progress>1 else progress
            # Stessi criteri del detector
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
            "groq": ("https://api.groq.com/openai/v1/chat/completions", "qwen/qwen3.8-27b"),  # FIX 2026-10: Llama-4 Scout rimosso da Groq, ora solo Qwen 3.8 vision
            "meta": ("https://api.llama.com/compat/v1/chat/completions", "Llama-4-Scout-17B-16E-Instruct"),
            "llama": ("https://api.llama.com/compat/v1/chat/completions", "Llama-4-Scout-17B-16E-Instruct"),
        }
        endpoint, final_model = provider_map_vision.get(provider, (f"https://api.openai.com/v1/chat/completions", "gpt-4o-mini"))

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type":"application/json"}
        if provider=="openrouter":
            headers["HTTP-Referer"]="https://klippeye.local"
            endpoint = "https://openrouter.ai/api/v1/chat/completions"
            final_model = "meta-llama/llama-4-scout-17b-16e-instruct"
        if detector.ai_model:  # scelto dalla dashboard (Monitor IA): vince su quello predefinito del servizio
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

        # Per provider che non supportano array content (vecchi), fallback a solo testo se errore
        try:
            r = requests.post(endpoint, headers=headers, json=payload, timeout=40)
            if not r.ok:
                # Prova senza immagine ma con nota
                print(f"[PRINT-AI] vision failed {r.status_code}: {r.text[:500]}")
                # Fallback: analisi solo telemetria
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


# Auto-start detector se cv2 disponibile (e se non l'hai spento dal menu: Monitor IA > Monitor attivo)
try:
    if HAS_CV2 and brain_config.snapshot()["enabled"]:
        detector.start()
        print("[OPENCV] Auto-start detector attivo (parte quando stampa)")
    elif HAS_CV2:
        detector.enabled = False
        detector.stats["status"] = "stopped"
        print("[OPENCV] Detector spento dal menu: non parte")
    else:
        print("[OPENCV] Detector non avviato, manca cv2")
except Exception as e:
    print(f"[OPENCV] Auto-start fail: {e}")

if __name__ == "__main__":
    threading.Thread(target=_repair_at_startup, name="repair", daemon=True).start()
    print(f"KlippEye backend {RELEASE} (api {API_LEVEL}) - dati in {DATA_DIR} - impostazioni {'lette da ' + BRAIN_CONFIG_PATH if brain_config.saved else 'di serie (nessun file salvato)'}")
    print(f"KlippEye backend running on 0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
