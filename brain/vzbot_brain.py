"""
VzBot Brain - server della dashboard (Flask) + monitor IA (OpenCV) + ponte verso Moonraker.

Parte del componente "vzbot" (cartella ~/vzbot, vedi README.md): questo file sta in brain/, la dashboard in dashboard/,
la versione in VERSION. Il codice qui sotto e' quello del Brain V18 (UI 1:1 identica ma NON MOCK, dati reali, comandi
reali, camera, ZeroTier fix, FIX 404 Groq, FIX 413 TPM) con queste aggiunte della release 1.0:

  * le soglie del monitor IA (sensibilita', quante anomalie, ogni quanti secondi, avvio dopo N secondi, ROI...) sono
    impostazioni: si leggono e si cambiano da /api/brain/config (la dashboard ha il menu) e restano salvate in
    <cartella dati>/brain.json. Un file mancante o rovinato vuol dire "valori di sempre": non impedisce mai l'avvio;
  * /api/version dice release, livello dell'interfaccia (API_LEVEL) e commit; la release viene dal file VERSION;
  * la cartella dati (default ~/printer_data/vzbot, cambia con la variabile VZBOT_DATA) tiene tutto quello che e' del
    Raspberry e non del codice: impostazioni, chiave dell'IA (file con permessi 600), notifiche. Gli aggiornamenti
    del codice (Moonraker -> update manager) non la toccano mai;
  * il ponte verso Moonraker aspetta fino a 10 minuti le operazioni lunghe (/machine/update/...) invece di 10 secondi;
  * l'app Android: l'APK costruito da GitHub arriva nella cartella apk/ del repository con l'aggiornamento di VzBot e il Brain
    lo offre al telefono (/api/app/version dice quale versione e', /app/VzBot.apk e' il file);
  * la cartella dati e le vecchie posizioni (/home/pi/vzbot_ai_config.json...) si leggono entrambe: nessun dato perso.
"""
from flask import Flask, request, Response, jsonify, send_file
from flask_cors import CORS
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
import threading
import subprocess

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

MOONRAKER_URL = "http://127.0.0.1:7125"
CAMERA_NGINX_URL = "http://127.0.0.1/webcam"
PORT = int(os.environ.get("VZBOT_PORT") or 8085)  # 8085 di sempre (la variabile serve solo alle prove)

# === VZBOT 1.0 - BASE: release, cartella dati, impostazioni salvate ===========================================
BRAIN_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BRAIN_DIR)  # ~/vzbot: la cartella del repository (brain/, dashboard/, VERSION...)
API_LEVEL = 2  # sale quando cambia il "linguaggio" tra Brain e dashboard (la dashboard dice quale le serve)
START_TS = time.time()


def _read_release():
    """La release e' scritta in VERSION (accanto a brain/, dashboard/...). Senza il file (Brain copiato da solo): 'sviluppo'."""
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
    chosen = os.environ.get("VZBOT_DATA", "").strip()
    if chosen:
        return os.path.abspath(os.path.expanduser(chosen))
    home = os.path.expanduser("~")
    if os.path.isdir(os.path.join(home, "printer_data")):
        return os.path.join(home, "printer_data", "vzbot")
    return os.path.join(home, "vzbot_data")


DATA_DIR = _default_data_dir()
BRAIN_CONFIG_PATH = os.path.join(DATA_DIR, "brain.json")


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


# Le soglie del monitor IA. Il Brain e' l'unica fonte dei limiti: la dashboard disegna il menu da questo elenco
# (etichette, unita', minimi e massimi), quindi una soglia nuova compare nel menu senza toccare la dashboard.
CONFIG_GROUPS = [
    {"id": "monitor", "title": "Monitor", "note": ""},
    {"id": "rilevamento", "title": "Rilevamento del movimento",
     "note": "Ogni pochi secondi il Brain confronta due foto della camera: se molti punti della fascia esterna dell'area controllata cambiano, e succede più volte, chiede all'IA di guardare la foto."},
    {"id": "area", "title": "Area controllata", "note": "Il rettangolo dove il Brain cerca il movimento sospetto. Di serie è il 60% centrale dell'immagine."},
    {"id": "tempi", "title": "Pause e consumi", "note": "L'analisi dell'IA usa un servizio online: queste pause evitano di chiamarla troppo spesso."},
    {"id": "avvio", "title": "Quando comincia a controllare",
     "note": "Durante il riscaldamento, la mesh o il purge la stampa non è ancora iniziata: il monitor aspetta."},
    {"id": "ia", "title": "Modello dell'IA", "note": ""},
]

CONFIG_SPEC = [
    {"key": "enabled", "type": "bool", "default": True, "group": "monitor", "label": "Monitor attivo",
     "help": "Spento, il Brain non guarda la camera e non chiama l'IA."},
    {"key": "sensitivity", "type": "int", "default": 35, "min": 5, "max": 100, "step": 1, "unit": "", "group": "rilevamento",
     "label": "Soglia di cambiamento",
     "help": "Di quanto deve cambiare la luminosità di un punto tra due foto perché conti come movimento. Più ALTA = meno sensibile (meno falsi allarmi); più bassa = più sensibile."},
    {"key": "score_threshold", "type": "float", "default": 2.5, "min": 0.5, "max": 30, "step": 0.5, "decimals": 1, "unit": "%", "group": "rilevamento",
     "label": "Movimento ai bordi",
     "help": "Quanta parte della fascia esterna dell'area deve muoversi perché il controllo sia sospetto. Più bassa = più sensibile."},
    {"key": "trigger_count", "type": "int", "default": 3, "min": 1, "max": 10, "step": 1, "unit": "", "group": "rilevamento",
     "label": "Controlli sospetti prima dell'allarme",
     "help": "Quanti controlli sospetti servono per chiedere l'analisi all'IA. Ogni controllo normale ne toglie uno."},
    {"key": "check_interval", "type": "int", "default": 3, "min": 1, "max": 30, "step": 1, "unit": "s", "group": "rilevamento",
     "label": "Ogni quanto guarda la camera",
     "help": "Più lungo = meno lavoro per il Raspberry, ma un problema si nota più tardi."},
    {"key": "border", "type": "int", "default": 25, "min": 10, "max": 45, "step": 1, "unit": "%", "group": "rilevamento",
     "label": "Larghezza della fascia esterna",
     "help": "Il movimento che conta è quello ai bordi dell'area controllata (spaghetti in aria), non quello al centro dove stampa. Misurata in % dell'area."},
    {"key": "roi", "type": "area", "default": [20, 20, 60, 60], "group": "area", "label": "Area controllata",
     "help": "Sinistra, alto, larghezza e altezza in % dell'immagine."},
    {"key": "cooldown", "type": "int", "default": 90, "min": 10, "max": 3600, "step": 10, "unit": "s", "group": "tempi",
     "label": "Pausa dopo un allarme",
     "help": "Dopo un allarme il monitor aspetta questo tempo prima di tornare a guardare."},
    {"key": "ai_cooldown", "type": "int", "default": 120, "min": 30, "max": 3600, "step": 10, "unit": "s", "group": "tempi",
     "label": "Pausa tra due analisi dell'IA",
     "help": "Tempo minimo tra due chiamate al servizio online. Più lungo = meno consumi e meno rischio di limiti."},
    {"key": "warmup_seconds", "type": "int", "default": 90, "min": 0, "max": 1800, "step": 10, "unit": "s", "group": "avvio",
     "label": "Attesa dopo l'inizio della stampa",
     "help": "Il controllo parte solo dopo questi secondi di stampa (riscaldamento, mesh e purge non contano)."},
    {"key": "min_progress", "type": "float", "default": 2, "min": 0, "max": 20, "step": 0.5, "decimals": 1, "unit": "%", "group": "avvio",
     "label": "Avanzamento minimo",
     "help": "Il controllo parte solo quando la stampa è avanzata almeno di così."},
    {"key": "hotend_tolerance", "type": "int", "default": 8, "min": 2, "max": 50, "step": 1, "unit": "°C", "group": "avvio",
     "label": "Scarto massimo dell'ugello",
     "help": "Se l'ugello è più lontano di così dalla temperatura impostata, la stampa vera non è ancora iniziata."},
    {"key": "ai_model", "type": "text", "default": "", "maxlen": 80, "pattern": r"[A-Za-z0-9._:/@+-]*", "group": "ia",
     "label": "Modello dell'IA (facoltativo)",
     "help": "Vuoto = quello predefinito del servizio scelto. Scrivilo solo se il servizio ritira il modello (errore 404 o 'model not found')."},
]
SPEC_BY_KEY = {spec["key"]: spec for spec in CONFIG_SPEC}


def config_defaults():
    return {spec["key"]: copy.deepcopy(spec["default"]) for spec in CONFIG_SPEC}


def coerce_config_value(spec, raw):
    """Controlla un valore e lo porta alla forma giusta. Alza ValueError con il motivo (in italiano: lo legge l'utente)."""
    kind = spec["type"]
    if kind == "bool":
        if isinstance(raw, bool):
            return raw
        raise ValueError("deve essere sì o no")
    if kind in ("int", "float"):
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            raise ValueError("deve essere un numero")
        try:
            number = float(raw.strip().replace(",", ".")) if isinstance(raw, str) else float(raw)
        except ValueError:
            raise ValueError("deve essere un numero")
        if not math.isfinite(number):
            raise ValueError("deve essere un numero")
        if kind == "int":
            if abs(number - round(number)) > 1e-9:
                raise ValueError("deve essere un numero intero")
            number = int(round(number))
        else:
            number = round(number, spec.get("decimals", 2))
        if number < spec["min"] or number > spec["max"]:
            raise ValueError("deve stare tra %s e %s" % (spec["min"], spec["max"]))
        return number
    if kind == "text":
        if not isinstance(raw, str):
            raise ValueError("deve essere un testo")
        text = raw.strip()
        if len(text) > spec.get("maxlen", 80) or not re.fullmatch(spec.get("pattern", r"[^\x00-\x1f]*"), text):
            raise ValueError("contiene caratteri non validi o è troppo lungo")
        return text
    if kind == "area":
        if not isinstance(raw, (list, tuple)) or len(raw) != 4:
            raise ValueError("servono quattro numeri: sinistra, alto, larghezza, altezza")
        parts = []
        for item in raw:
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
                raise ValueError("servono quattro numeri: sinistra, alto, larghezza, altezza")
            parts.append(round(float(item), 1))
        x, y, w, h = parts
        if x < 0 or y < 0 or w < 10 or h < 10 or x + w > 100.05 or y + h > 100.05:
            raise ValueError("l'area deve stare dentro l'immagine ed essere larga e alta almeno il 10%")
        return [x, y, w, h]
    raise ValueError("tipo sconosciuto")


class BrainConfig:
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
        """Un file rovinato non deve fermare il Brain: lo metto da parte (si può guardare) e riparto dai valori di sempre."""
        target = "%s.rovinato-%d" % (self.path, int(time.time()))
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
                errors[key] = "impostazione sconosciuta"
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


brain_config = BrainConfig(BRAIN_CONFIG_PATH)


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
    os.path.join(REPO_DIR, "dashboard", "vzbot_dashboard.html"),  # il posto della release 1.0 (~/vzbot/dashboard/)
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
            if f.endswith(".html") and "vzbot" in f.lower():
                return os.path.join("/home/pi", f)
    except:
        pass
    return None

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
    if f:
        return send_file(f)
    return "vzbot_frontend_original.html non trovato in /home/pi/", 404

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

CALIBRATION_SELECTED_FILE = "/home/pi/printer_data/config/vzbot_calibration_selected.json"
CALIBRATION_SELECTED_FILE_FALLBACK = "/home/pi/vzbot_calibration_selected.json"

def load_calibration_selected():
    for fp in [CALIBRATION_SELECTED_FILE, CALIBRATION_SELECTED_FILE_FALLBACK]:
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
    for fp in [CALIBRATION_SELECTED_FILE, CALIBRATION_SELECTED_FILE_FALLBACK]:
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
            safe={"provider":cfg.get("provider"),"model":cfg.get("model"),"key_preview": (cfg.get("api_key","")[:8]+"..."+cfg.get("api_key","")[-4:]) if cfg.get("api_key") else "", "configured": True}
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

        if is_single:
            prompt = f"""Sei un esperto di Klipper/Moonraker/VzBot 235.
Analizza SOLO questo singolo file log: {used_files[0]}

Contenuto (ultime righe):
{combined}

Task per singolo file:
1) Tipo di log e cosa registra
2) Stato generale di questo servizio
3) Errori critici SOLO in questo file
4) Per ogni errore: causa + fix immediato
5) Se nessun errore, dillo chiaramente

Rispondi in italiano, markdown breve, focalizzato solo su questo file.
"""
        else:
            prompt = f"""Sei un esperto di Klipper, Moonraker, Crowsnest per VzBot 235.
Analizza questi log di sistema presi da /home/pi/printer_data/logs (tutti i file, non solo klippy.log).

File inclusi: {', '.join(used_files)}

Contenuti (ultime righe):
{combined}

Task:
1) Trova errori, warning, stacktrace rilevanti (TMC, heater, probe, MCU, move out of range, crowsnest, moonraker, ecc)
2) Spiega causa probabile per ogni errore
3) Suggerisci fix concreti: comandi gcode, file da controllare (printer.cfg, ecc), cablaggi, PID, corrente TMC, ecc per VzBot 235
4) Indica se serve FIRMWARE_RESTART, KLIPPER RESTART o controllo hardware
5) Dai priorità: cosa risolvere prima

Rispondi in italiano, tecnico ma chiaro, con bullet point e comandi pronti da copiare. Se non vedi errori critici, dillo esplicitamente.
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
                headers["HTTP-Referer"]="https://vzbot.local"
                headers["X-Title"]="VzBot Logs Analyzer"

            r=requests.post(endpoint,
                headers=headers,
                json={
                    "model": final_model,
                    "messages":[
                        {"role":"system","content":"Sei un esperto di Klipper, Moonraker, Crowsnest per VzBot 235."},
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

def prune_alert_images(keep=10, pattern="/tmp/vzbot_alert_*.jpg"):
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


class LightDetector:
    def __init__(self):
        self.enabled = True  # AUTO-ENABLED
        self.running = False
        self.thread = None
        self.generation = 0  # ogni start() ne apre una nuova: un vecchio ciclo ancora addormentato capisce da solo di dover finire
        self.last_frames = deque(maxlen=5)
        self.roi = None
        # Le soglie qui sotto sono i valori di sempre; subito dopo la creazione apply_config() mette quelli salvati
        # (brain.json) e da allora li cambia la dashboard: /api/brain/config.
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
        """Mette in uso le soglie (dict di BrainConfig). Vale dal controllo successivo, senza riavviare niente."""
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

    def loop(self, generation=None):
        if generation is None:
            generation = self.generation
        while self.running and generation == self.generation:
            try:
                if not HAS_CV2:
                    self.stats["status"] = "cv2 non installato"
                    time.sleep(5)
                    continue
                if not self.enabled:
                    time.sleep(1)
                    continue
                # Cooldown check
                if time.time() < self.cooldown_until:
                    self.stats["status"] = f"cooldown {int(self.cooldown_until - time.time())}s"
                    time.sleep(1)
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
                        self.stats["status"] = f"idle (state={state})"
                        self.stats["real_print_started"] = False
                        self.stats["real_print_reason"] = f"state={state}"
                        time.sleep(5)
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
                        time.sleep(3)
                        continue

                except Exception as e:
                    print(f"[DETECTOR] real_print check err: {e}")
                    time.sleep(3)
                    continue

                # Get snapshot low-res
                try:
                    r = requests.get(f"{CAMERA_NGINX_URL}/snapshot", timeout=4)
                    if not r.ok or len(r.content) < 1000:
                        time.sleep(2)
                        continue
                    img_arr = np.frombuffer(r.content, np.uint8)
                    frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
                    if frame is None:
                        time.sleep(2)
                        continue
                except Exception as e:
                    print(f"[OPENCV] snapshot fail: {e}")
                    time.sleep(3)
                    continue

                # Resize a 1080x720 per dettaglio - V18 FULL HD (6-11% CPU)
                small = cv2.resize(frame, (OPENCV_WIDTH, OPENCV_HEIGHT))
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (21,21), 0)

                self.last_frames.append(gray)
                self.stats["frames_checked"] += 1
                self.stats["status"] = "scanning"

                if len(self.last_frames) < 3:
                    time.sleep(self.check_interval)  # intervallo check
                    continue

                # Confronto con frame precedente (background subtraction semplice)
                prev = self.last_frames[-2]
                diff = cv2.absdiff(prev, gray)
                thresh = cv2.threshold(diff, self.sensitivity, 255, cv2.THRESH_BINARY)[1]
                thresh = cv2.dilate(thresh, None, iterations=2)

                # ROI: se non impostato, usa 60% centrale (area piatto)
                if self.roi is None:
                    h,w = thresh.shape
                    x = int(w*0.2); y = int(h*0.2); rw = int(w*0.6); rh = int(h*0.6)
                else:
                    # scala ROI da 1080x720 a thresh shape (V18 full HD)
                    x,y,rw,rh = self.roi

                roi_thresh = thresh[y:y+rh, x:x+rw]

                # Conta pixel bianchi (movimento) FUORI dal centro atteso del pezzo
                # Per spaghetti, il movimento è in alto / ai lati, non al centro dove c'è estrusione normale
                # Dividiamo ROI in 3 zone: centro (pezzo) e periferia (possibile spaghetti)
                h_roi, w_roi = roi_thresh.shape
                center_x, center_y = w_roi//2, h_roi//2
                # Maschera periferia (bordo 25%)
                border = self.border  # fascia esterna: di serie il 25% (0.25 / 0.75)
                mask_periphery = np.zeros_like(roi_thresh)
                mask_periphery[:int(h_roi*border), :] = 255  # top
                mask_periphery[int(h_roi*(1-border)):, :] = 255  # bottom
                mask_periphery[:, :int(w_roi*border)] = 255  # left
                mask_periphery[:, int(w_roi*(1-border)):] = 255  # right

                periphery_motion = cv2.bitwise_and(roi_thresh, roi_thresh, mask=mask_periphery)
                score = (cv2.countNonZero(periphery_motion) / (w_roi*h_roi)) * 100

                self.stats["last_score"] = round(score,2)

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
                        prune_alert_images()  # le foto degli allarmi vecchie non si accumulano per sempre
                        full_path = f"/tmp/vzbot_alert_{int(time.time())}.jpg"
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
                            threading.Thread(target=self.call_ai_analysis, args=(full_path,), daemon=True).start()
                    except Exception as e:
                        print(f"[OPENCV] save alert fail: {e}")

                time.sleep(self.check_interval)  # check ogni 3s di serie (la dashboard: Monitor IA > Ogni quanto guarda la camera)

            except Exception as e:
                print(f"[OPENCV] loop error: {e}")
                time.sleep(3)

    def call_ai_analysis(self, img_path):
        """AUTO-CHIAMA GROQ quando triggera, senza intervento umano"""
        try:
            now = time.time()
            if now - self.last_ai_call < self.ai_cooldown:
                print(f"[OPENCV] AI cooldown attivo, salto (mancano {int(self.ai_cooldown - (now-self.last_ai_call))}s)")
                return
            self.last_ai_call = now
            print(f"[OPENCV] AUTO-CHIAMATA GROQ per {img_path}")

            # Leggi immagine e converti base64
            if not os.path.exists(img_path):
                print(f"[OPENCV] img non trovata {img_path}")
                return
            with open(img_path, 'rb') as f:
                img_b64 = base64.b64encode(f.read()).decode('utf-8')

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
            bed = telemetry.get("heater_bed",{})
            state = print_stats.get("state","unknown")
            filename = print_stats.get("filename","")
            progress = display.get("progress",0)*100
            temp_h = extruder.get("temperature",0)

            prompt_text = f"""Sei un esperto di stampa 3D VzBot 235.

Analizza questa immagine - sospetto spaghetti rilevato da OpenCV locale (score {self.stats.get('last_score',0)}%).

TELEMETRIA:
- Stato: {state}
- File: {filename}
- Progresso: {progress:.1f}%
- Hotend: {temp_h:.1f}°C

TASK V17 ANTI-FALSO: Rileva SPAGHETTI, PIATTO VUOTO (solo se progress >5% e confidence >=70%), LAYER SHIFT, WARPING. Immagine 1080x720 dettagliata - guarda bene se c'è anche solo un bordo sottile sul piatto = NON vuoto. Dai confidenza % e azione CONTINUA/PAUSA/CANCELLA.

Rispondi SOLO con JSON valido + breve summary:
{{
  "spaghetti": {{"detected": true/false, "confidence": 0-100, "note": "dettaglio"}},
  "empty_bed": {{"detected": true/false, "confidence": 0-100}},
  "layer_shift": {{"detected": true/false, "confidence": 0-100}},
  "warping": {{"detected": true/false, "confidence": 0-100}},
  "action": "CONTINUA|PAUSA|CANCELLA",
  "summary": "frase breve in italiano, max 20 parole"
}}
"""

            cfg = load_ai_config()
            if not cfg.get("api_key"):
                print("[OPENCV] No API key per AI auto-call")
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
            payload = {
                "model": final_model,
                "messages":[
                    {"role":"system","content":"Sei un esperto stampa 3D. Rispondi SOLO con JSON valido come richiesto."},
                    {"role":"user","content":[
                        {"type":"text","text":prompt_text},
                        {"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{img_b64}"}}
                    ]}
                ],
                "temperature":0.2,
                "max_tokens": 800,
                "response_format": {"type": "json_object"}
            }

            r = requests.post(endpoint, headers=headers, json=payload, timeout=30)
            if not r.ok:
                print(f"[OPENCV] Groq error {r.status_code}: {r.text[:500]}")
                return
            j = r.json()
            answer = j["choices"][0]["message"]["content"] if "choices" in j else str(j)
            print(f"[OPENCV] AI Risposta: {answer[:500]}")

            # Parsa JSON
            try:
                parsed = None
                # Prova a estrarre JSON
                import json as js
                # Se risposta contiene solo JSON
                parsed = js.loads(answer)
                if isinstance(parsed, dict) and "spaghetti" not in parsed:
                    # Prova a cercare nested
                    for v in parsed.values():
                        if isinstance(v, dict) and "spaghetti" in v:
                            parsed = v
                            break
            except:
                # Fallback: cerca JSON con regex
                try:
                    import json as js, re
                    m = re.search(r'\{[\s\S]*"spaghetti"[\s\S]*\}', answer)
                    if m:
                        parsed = js.loads(m.group(0))
                except:
                    parsed = None

            if parsed:
                self.last_analysis = {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "model": final_model,
                    "progress": progress,
                    "filename": filename,
                    "image_path": img_path,
                    "analysis": parsed,
                    "raw": answer
                }
                self.stats["status"] = f"AI: {parsed.get('action','?')} - {parsed.get('summary','')[:40]}"
                print(f"[OPENCV] AI analysis salvata: {parsed}")
            else:
                self.last_analysis = {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "model": final_model,
                    "progress": progress,
                    "analysis": {"action":"PAUSA","summary":answer[:200],"raw":True},
                    "raw": answer
                }

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
    })


# === APP ANDROID: l'APK che GitHub costruisce (apk/VzBot.apk + apk/versione.json) ===============================
APK_DIR = os.path.join(REPO_DIR, "apk")
APK_PATH = os.path.join(APK_DIR, "VzBot.apk")
APK_INFO_PATH = os.path.join(APK_DIR, "versione.json")
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
    Cosa offre il Brain al telefono: {"available": True, "version", "code", "size", "sha256", "built", "url"} oppure
    {"available": False, "reason": ...}. Il file apk/versione.json e' scritto da GitHub insieme all'APK; qui si controlla che
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
        return {"available": False, "reason": "apk/versione.json non si legge"}
    if not isinstance(data, dict):
        return {"available": False, "reason": "apk/versione.json non e' valido"}
    version, sha = data.get("version"), str(data.get("sha256") or "").lower()
    if not isinstance(version, str) or _apk_code(version) is None or not _APK_SHA_RE.match(sha):
        return {"available": False, "reason": "apk/versione.json non e' valido"}
    if data.get("size") != apk_size:
        return {"available": False, "reason": "l'APK non corrisponde a versione.json (aggiornamento a meta'?)"}
    try:
        actual = _apk_sha256(APK_PATH)
    except OSError:
        return {"available": False, "reason": "l'APK non si legge"}
    if actual != sha:
        return {"available": False, "reason": "l'APK non corrisponde a versione.json (impronta diversa)"}
    built = data.get("built")
    return {
        "available": True,
        "version": version,
        "code": _apk_code(version),
        "size": apk_size,
        "sha256": sha,
        "built": built if isinstance(built, str) and len(built) <= 40 else "",
        "url": "/app/VzBot.apk",
    }


@app.route("/api/app/version", methods=["GET"])
def api_app_version():
    """L'app Android che il Brain puo' dare al telefono (vedi read_apk_info). Mai in cache: dopo un aggiornamento cambia."""
    response = jsonify(dict(read_apk_info(), ok=True))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/app/VzBot.apk", methods=["GET"])
def app_apk():
    """Il file dell'app. Si da' solo se e' coerente con versione.json (grandezza e impronta), altrimenti 404 con il motivo."""
    info = read_apk_info()
    if not info["available"]:
        return jsonify({"ok": False, "error": info["reason"]}), 404
    response = send_file(APK_PATH, mimetype=APK_MIMETYPE, as_attachment=True, download_name="VzBot-%s.apk" % info["version"], conditional=True, max_age=0)
    response.headers["Cache-Control"] = "no-store"
    return response
# === fine APP ANDROID ==================================================================================


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


@app.route("/api/brain/config", methods=["GET"])
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


@app.route("/api/brain/config", methods=["POST"])
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


@app.route("/api/brain/config/reset", methods=["POST"])
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
    # (Il menu della dashboard usa /api/brain/config.) roi = [x,y,w,h] in pixel dell'immagine 1080x720.
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
                checks.append(f"progress {progress_frac*100:.1f}% basso")
            else:
                real_print_started = True
            if abs(temp_h - target_h) > detector.hotend_tol and target_h>0:
                real_print_started = False
                checks.append(f"hotend non a temp {temp_h:.0f}/{target_h:.0f}")
            if total_dur < detector.warmup:
                real_print_started = False
                checks.append(f"durata {total_dur:.0f}s <{detector.warmup}s")
            if progress_frac >= detector.min_progress/100 and abs(temp_h - target_h) <= detector.hotend_tol:
                real_print_started = True
                checks = ["ok - stampa reale iniziata"]
            real_reason = "; ".join(checks)
        except Exception as e:
            real_reason = f"errore calcolo real_print: {e}"

        prompt_text = f"""Sei un esperto di stampa 3D VzBot 235, specializzato in failure detection.

Analizza questa immagine della stampa in corso.

TELEMETRIA:
- Stato: {state}
- File: {filename}
- Progresso: {progress:.1f}%
- Hotend: {temp_h:.1f}°C / target {target_h:.1f}°C
- Bed: {temp_b:.1f}°C
- Print stats: {print_stats}
- REAL_PRINT_STARTED: {real_print_started} ({real_reason})
- File position: {file_pos}/{file_size} ({file_progress*100:.1f}%)

REGOLA CRITICA ANTI-FALSO PIATTO VUOTO - V17 MIGLIORATA:
- Se REAL_PRINT_STARTED è False (riscaldamento, mesh, homing, calibrazione, purge non ancora iniziata):
  - NON segnalare MAI "piatto vuoto" come errore
  - CONTINUA con nota "riscaldamento/calibrazione in corso, piatto vuoto normale"
- Se REAL_PRINT_STARTED è True MA progress < 3% o file_position < 5%:
  - Piatto vuoto è NORMALE se non vedi pezzo - potrebbe essere primo layer ancora sottile o trasparente
  - Richiedi confidence >= 85% per segnalare piatto vuoto nei primi layer
  - Se vedi ombra, riflesso, o contorno leggero sul piatto, è ancora stampa valida = CONTINUA
- SOLO quando REAL_PRINT_STARTED True E progress > 5% E file_position > 10% puoi segnalare piatto vuoto con confidence >= 70%
- GUARDA ATTENTAMENTE: se vedi anche solo un puntino, linea, o bordo sul piatto, NON è vuoto
- Immagine ora è 1080x720 alta risoluzione - usa dettaglio per distinguere piatto pulito vs primo layer sottile

TASK:

TASK:
1) Rileva SPAGHETTI (filamenti aggrovigliati, estrusione in aria)
2) Rileva PIATTO VUOTO (oggetto staccato, letto vuoto ma stampa in corso)
3) Rileva LAYER SHIFT (spostamento strati)
4) Rileva WARPING / ADESIONE fallita
5) Rileva UGELLO OSTRUITO / UNDER-EXTRUSION
6) Dai confidenza % per ogni rilevamento
7) Suggerisci azione: CONTINUA / PAUSA / CANCELLA

Rispondi in italiano, JSON strutturato + breve spiegazione:
{{
  "spaghetti": {{"detected": true/false, "confidence": 0-100, "note": "..."}},
  "empty_bed": {{"detected": true/false, "confidence": 0-100}},
  "layer_shift": {{"detected": true/false, "confidence": 0-100}},
  "warping": {{"detected": true/false}},
  "action": "CONTINUA|PAUSA|CANCELLA",
  "summary": "frase breve"
}}
Poi aggiungi sezione markdown con spiegazione dettagliata.
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
            headers["HTTP-Referer"]="https://vzbot.local"
            endpoint = "https://openrouter.ai/api/v1/chat/completions"
            final_model = "meta-llama/llama-4-scout-17b-16e-instruct"
        if detector.ai_model:  # scelto dalla dashboard (Monitor IA): vince su quello predefinito del servizio
            final_model = detector.ai_model

        payload = {
            "model": final_model,
            "messages":[
                {"role":"system","content":"Sei un esperto di rilevamento fallimenti stampa 3D. Rispondi sempre in JSON + markdown."},
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
                        {"role":"system","content":"Esperto stampa 3D"},
                        {"role":"user","content": f"{prompt_text}\n\n[NOTA: immagine non disponibile per questo provider, analizza solo telemetria e suggerisci di usare OpenAI gpt-4o-mini per vision]"}
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
    print(f"VzBot Brain {RELEASE} (api {API_LEVEL}) - dati in {DATA_DIR} - impostazioni {'lette da ' + BRAIN_CONFIG_PATH if brain_config.saved else 'di serie (nessun file salvato)'}")
    print(f"VzBot Brain REAL running on 0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
