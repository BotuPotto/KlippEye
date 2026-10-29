#!/usr/bin/env python3
"""Tests of the backend (backend/klippeye_backend.py): settings, endpoints, persistence, access and the detector itself.

    python3 test_brain.py [--quick]

--quick skips the two slow runs (original-vs-new comparison at the real 3 s rhythm).
The detector tests use the real OpenCV with synthetic pictures: a white square that appears / disappears at the edge of
the watched area makes a "movement" of a known size, so each threshold can be checked against what it should do.
"""
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
import fakes  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))   # the repository
NEW_BRAIN = os.path.join(ROOT, "backend", "klippeye_backend.py")
OLD_BRAIN = os.path.join(HERE, "fixtures", "vzbot_brain_original.py")   # the original VzBot Brain: same detector results with the default values
QUICK = "--quick" in sys.argv

passed, failed = 0, 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print("  PASS  " + name)
    else:
        failed += 1
        print("  FAIL  " + name + ("   -> " + str(detail) if detail != "" else ""))


_modules = []


def load_brain(path, data_dir, fake=None, brain_json=None, name=None):
    """Imports a fresh copy of the Brain with its own data folder (and optionally a prepared brain.json)."""
    os.makedirs(data_dir, exist_ok=True)
    if brain_json is not None:
        with open(os.path.join(data_dir, "brain.json"), "w", encoding="utf-8") as f:
            json.dump(brain_json, f)
    os.environ["KLIPPEYE_DATA"] = data_dir
    modname = name or "brain_%d" % len(_modules)
    spec = importlib.util.spec_from_file_location(modname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    _modules.append(module)
    if fake is not None:
        module.MOONRAKER_URL = fake.url
        module.CAMERA_NGINX_URL = fake.url + "/webcam"
    return module


def stop_all():
    for module in _modules:
        try:
            module.detector.stop()
        except Exception:
            pass


def wait_for(predicate, seconds, step=0.2):
    end = time.time() + seconds
    while time.time() < end:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


def tmp():
    return tempfile.mkdtemp(prefix="brain_test_")


# ---------------------------------------------------------------------------------------------------------------------
print("== Impostazioni: valori di sempre, API, controlli")
d = tmp()
b = load_brain(NEW_BRAIN, d, brain_json={"formato": 1, "values": {"enabled": False}})  # spento: nessun ciclo parte da solo
client = b.app.test_client()

r = client.get("/api/backend/config")
j = r.get_json()
check("GET /api/backend/config risponde 200", r.status_code == 200)
defaults = j["defaults"]
check("valori di sempre = quelli del Brain V18", defaults["sensitivity"] == 35 and defaults["score_threshold"] == 2.5 and defaults["trigger_count"] == 3
      and defaults["check_interval"] == 3 and defaults["cooldown"] == 90 and defaults["ai_cooldown"] == 120 and defaults["warmup_seconds"] == 90
      and defaults["min_progress"] == 2 and defaults["hotend_tolerance"] == 8 and defaults["border"] == 25 and defaults["roi"] == [20, 20, 60, 60], defaults)
check("la risposta porta spec, gruppi e api", j["api"] == 2 and len(j["spec"]) == len(j["defaults"]) and len(j["groups"]) >= 5)
check("ogni voce della spec ha etichetta e gruppo esistente", all(s["label"] and s["group"] in [g["id"] for g in j["groups"]] for s in j["spec"]))
check("le voci numeriche dicono minimo, massimo e unita'", all(("min" in s and "max" in s) for s in j["spec"] if s["type"] in ("int", "float")))
check("il pattern interno non esce nella spec", all("pattern" not in s for s in j["spec"]))
check("enabled=false letto da brain.json: il rilevatore non parte", b.detector.running is False and j["values"]["enabled"] is False)

r = client.post("/api/backend/config", json={"values": {"sensitivity": 50, "trigger_count": 5}})
j = r.get_json()
check("POST valido: 200, ok, changed", r.status_code == 200 and j["ok"] and sorted(j["changed"]) == ["sensitivity", "trigger_count"], j)
check("... mette in uso le soglie nel rilevatore", b.detector.sensitivity == 50 and b.detector.trigger_threshold == 5)
saved = json.load(open(os.path.join(d, "monitor.json")))
check("... e le salva in monitor.json (brain.json prima della 1.3.0, rinominato da solo)", saved["values"]["sensitivity"] == 50 and saved["values"]["trigger_count"] == 5 and saved["formato"] == 1, saved)
check("... senza lasciare file temporanei", [f for f in os.listdir(d) if f.startswith(".tmp")] == [], os.listdir(d))

r = client.post("/api/backend/config", json={"values": {"sensitivity": 500, "cooldown": 5, "pippo": 1}})
j = r.get_json()
check("POST non valido: 400 con un errore per chiave", r.status_code == 400 and not j["ok"] and set(j["errors"]) == {"sensitivity", "cooldown", "pippo"}, j)
check("... non cambia niente (nemmeno i valori buoni)", b.detector.sensitivity == 50 and j["values"]["sensitivity"] == 50)
check("... e il messaggio dice il motivo (in inglese)", "must be between" in j["errors"]["sensitivity"] and "unknown" in j["errors"]["pippo"], j["errors"])

for bad, label in (({"sensitivity": True}, "bool al posto di un numero"), ({"sensitivity": 3.5}, "decimale in un intero"), ({"sensitivity": "abc"}, "testo"),
                   ({"sensitivity": None}, "null"), ({"enabled": 1}, "1 al posto di sì/no"), ({"enabled": "true"}, "'true' al posto di sì/no"),
                   ({"roi": [0, 0, 5, 50]}, "area troppo stretta"), ({"roi": [50, 0, 60, 50]}, "area fuori dall'immagine"), ({"roi": [1, 2, 3]}, "area con 3 numeri"),
                   ({"ai_model": "a b"}, "modello con spazi"), ({"ai_model": "x" * 200}, "modello troppo lungo"), ({"score_threshold": float("nan")}, "NaN")):
    try:
        r = client.post("/api/backend/config", json={"values": bad})
        code = r.status_code
    except Exception as e:  # NaN is not valid JSON: the client refuses before sending
        code = 400
    check("rifiuta " + label, code == 400)

r = client.post("/api/backend/config", json={"values": {"sensitivity": "40", "score_threshold": "3,5", "check_interval": 4.0}})
check("accetta numeri scritti come testo ('3,5') e interi 4.0", r.status_code == 200 and b.detector.sensitivity == 40 and b.detector.score_threshold == 3.5 and b.detector.check_interval == 4, r.get_json())
r = client.post("/api/backend/config", json={"sensitivity": 41})
check("accetta anche l'oggetto senza 'values'", r.status_code == 200 and b.detector.sensitivity == 41)
r = client.post("/api/backend/config", data="non json", content_type="text/plain")
check("un corpo che non e' JSON da' 400", r.status_code == 400)

r = client.post("/api/backend/config", json={"values": {"roi": [10, 15.55, 70, 60.04]}})
check("area: arrotondata a un decimale e convertita in pixel 1080x720", r.status_code == 200 and b.brain_config.snapshot()["roi"] == [10.0, 15.6, 70.0, 60.0]
      and b.detector.roi == (108, 112, 756, 432), (b.brain_config.snapshot()["roi"], b.detector.roi))
r = client.post("/api/backend/config", json={"values": {"border": 30, "warmup_seconds": 20, "min_progress": 0.5, "hotend_tolerance": 12, "ai_model": "qwen/qwen3.8-27b", "ai_cooldown": 300, "cooldown": 30}})
check("tutte le altre soglie arrivano al rilevatore", r.status_code == 200 and b.detector.border == 0.30 and b.detector.warmup == 20 and b.detector.min_progress == 0.5
      and b.detector.hotend_tol == 12 and b.detector.ai_model == "qwen/qwen3.8-27b" and b.detector.ai_cooldown == 300 and b.detector.cooldown_sec == 30)

# persistenza: un Brain nuovo che parte con la stessa cartella ritrova tutto
b2 = load_brain(NEW_BRAIN, d, brain_json=None)
v2 = b2.brain_config.snapshot()
check("persistenza: dopo un riavvio le soglie sono quelle salvate", v2["sensitivity"] == 41 and v2["border"] == 30 and v2["ai_model"] == "qwen/qwen3.8-27b" and v2["roi"] == [10.0, 15.6, 70.0, 60.0], v2)
check("... e il rilevatore le usa subito", b2.detector.sensitivity == 41 and b2.detector.warmup == 20 and b2.detector.roi == (108, 112, 756, 432))
b2.detector.stop()

r = client.post("/api/backend/config/reset", json={"keys": ["sensitivity"]})
check("reset di una sola voce", r.status_code == 200 and b.detector.sensitivity == 35 and b.detector.warmup == 20)
r = client.post("/api/backend/config/reset")
j = r.get_json()
check("reset di tutto: tornano i valori di sempre", r.status_code == 200 and j["values"] == defaults and b.detector.warmup == 90 and b.detector.roi == (216, 144, 648, 432), j["values"])

# file mancante / rovinato / con valori strani
d2 = tmp()
b3 = load_brain(NEW_BRAIN, d2, brain_json={"formato": 1, "values": {"sensitivity": 9999, "trigger_count": "tre", "cooldown": 45, "roi": "tutto", "x": 1, "enabled": False}})
v3 = b3.brain_config.snapshot()
check("valori strani nel file: ignorati uno per uno, gli altri restano", v3["sensitivity"] == 35 and v3["trigger_count"] == 3 and v3["cooldown"] == 45 and v3["roi"] == [20, 20, 60, 60], v3)
d3 = tmp()
os.makedirs(d3, exist_ok=True)
open(os.path.join(d3, "brain.json"), "w").write("{ questo non e' json")
os.environ["KLIPPEYE_DATA"] = d3
b4 = load_brain(NEW_BRAIN, d3)
check("file rovinato: il Brain parte lo stesso con i valori di sempre", b4.brain_config.snapshot() == b4.config_defaults())
check("... e il file rovinato viene messo da parte, non perso", any(f.startswith("monitor.json.damaged-") for f in os.listdir(d3)), os.listdir(d3))
b4.detector.stop()
d4 = tmp()
open(os.path.join(d4, "brain.json"), "w").write("[1,2,3]")
b5 = load_brain(NEW_BRAIN, d4)
check("file con la forma sbagliata (una lista): valori di sempre", b5.brain_config.snapshot() == b5.config_defaults())
b5.detector.stop()

# cartella non scrivibile: l'impostazione vale ma il Brain lo dice
d5 = tmp()
b6 = load_brain(NEW_BRAIN, d5, brain_json={"values": {"enabled": False}})
os.chmod(d5, 0o500)
if os.geteuid() == 0:
    check("(salto la prova della cartella non scrivibile: sono root)", True)
else:
    r = b6.app.test_client().post("/api/backend/config", json={"values": {"sensitivity": 60}})
    j = r.get_json()
    check("cartella non scrivibile: 200, valore in uso, ma save_error", r.status_code == 200 and b6.detector.sensitivity == 60 and j["save_error"], j)
os.chmod(d5, 0o700)

# vecchi endpoint
r = client.post("/api/print/detector/config", json={"sensitivity": 5000, "cooldown": 60, "roi": [100, 100, 500, 400]})
check("vecchio /detector/config: limita la sensibilita' a 100, accetta cooldown e area in pixel", r.status_code == 200 and b.detector.sensitivity == 100 and b.detector.cooldown_sec == 60
      and b.brain_config.snapshot()["roi"][0] == round(100 * 100 / 1080, 1), (b.detector.sensitivity, b.detector.cooldown_sec, b.brain_config.snapshot()["roi"]))
r = client.post("/api/print/detector/config", json={"roi": [0, 0, 5, 5], "sensitivity": 50})
check("... un'area non valida viene lasciata com'era, il resto si applica", r.status_code == 200 and b.detector.sensitivity == 50 and b.brain_config.snapshot()["roi"][2] == round(500 * 100 / 1080, 1))
st = client.get("/api/print/detector/status").get_json()
check("/detector/status ha ancora tutti i campi di prima", all(k in st for k in ("ok", "enabled", "running", "has_cv2", "stats", "real_print_started", "real_print_reason", "progress", "roi", "sensitivity", "last_alert_img")), list(st))
client.post("/api/backend/config/reset")

# versione
r = client.get("/api/version")
j = r.get_json()
check("/api/version: release, api, uptime, cartella dati, python", r.status_code == 200 and j["api"] == 2 and j["release"] and j["uptime"] >= 0 and j["data_dir"] == d and j["has_cv2"] is True, j)
check("la release e' quella scritta nel file VERSION del repository", j["release"] == open(os.path.join(ROOT, "VERSION")).read().strip(), j["release"])
nover = tmp()
os.makedirs(os.path.join(nover, "backend"))
shutil.copy(NEW_BRAIN, os.path.join(nover, "backend", "klippeye_backend.py"))
b6 = load_brain(os.path.join(nover, "backend", "klippeye_backend.py"), tmp(), brain_json={"values": {"enabled": False}})
check("senza il file VERSION la release e' 'sviluppo'", b6.RELEASE == "sviluppo", b6.RELEASE)
vroot = tmp()
os.makedirs(os.path.join(vroot, "backend"))
shutil.copy(NEW_BRAIN, os.path.join(vroot, "backend", "klippeye_backend.py"))
open(os.path.join(vroot, "VERSION"), "w").write("1.2.3\n")
b7 = load_brain(os.path.join(vroot, "backend", "klippeye_backend.py"), tmp(), brain_json={"values": {"enabled": False}})
check("con il file VERSION accanto a backend/ la release e' quella", b7.RELEASE == "1.2.3" and b7.app.test_client().get("/api/version").get_json()["release"] == "1.2.3")
open(os.path.join(vroot, "VERSION"), "w").write("<script>alert(1)</script>\n")
b7b = load_brain(os.path.join(vroot, "backend", "klippeye_backend.py"), tmp(), brain_json={"values": {"enabled": False}})
check("un VERSION con roba strana non passa", b7b.RELEASE == "sviluppo")

# dashboard servita dal posto nuovo
os.makedirs(os.path.join(vroot, "frontend"))
open(os.path.join(vroot, "frontend", "klippeye_frontend.html"), "w").write("<!doctype html><html><head><title>KlippEye</title></head><body>nuova dashboard</body></html>\n")
b8 = load_brain(os.path.join(vroot, "backend", "klippeye_backend.py"), tmp(), brain_json={"values": {"enabled": False}})
r = b8.app.test_client().get("/")
check("la dashboard si serve da frontend/klippeye_frontend.html", r.status_code == 200 and b"nuova dashboard" in r.data)
r.close()
check("/api/version dice quale file serve", b8.app.test_client().get("/api/version").get_json()["frontend"].endswith("frontend/klippeye_frontend.html"))

# pagina rovinata da un blackout: vuota o troncata -> pagina d'emergenza 503 (mai una pagina bianca), senza lo script di riparazione non si inventa niente
fe = os.path.join(vroot, "frontend", "klippeye_frontend.html")
good_page = open(fe, "rb").read()
check("frontend_ok: pagina intera si', vuota no, troncata no, tutta zeri no, file che non c'e' no",
      b8.frontend_ok(fe) and not (open(fe, "wb").close() or b8.frontend_ok(fe)) and not (open(fe, "wb").write(good_page[:-20]) and b8.frontend_ok(fe))
      and not (open(fe, "wb").write(b"\x00" * 400) and b8.frontend_ok(fe)) and not b8.frontend_ok(fe + ".manca"))
for label, damage in (("vuota", b""), ("troncata", good_page[:-20])):
    open(fe, "wb").write(damage)
    r = b8.app.test_client().get("/")
    check("pagina %s e nessuno script di riparazione: 503 con la pagina d'emergenza che si ricarica" % label,
          r.status_code == 503 and b"putting its files back in order" in r.data and b'http-equiv="refresh"' in r.data and r.headers.get("Retry-After") == "8", (r.status_code, r.data[:80]))
    r.close()
open(fe, "wb").write(good_page)
r = b8.app.test_client().get("/")
check("rimessa a posto la pagina, la dashboard torna normale", r.status_code == 200 and b"nuova dashboard" in r.data)
r.close()
check("/api/version: campo repair (null se non c'e' mai stato un ripristino)", "repair" in b8.app.test_client().get("/api/version").get_json())
rk = tmp()
json.dump({"time": 1, "restored": ["a"], "failed": []}, open(os.path.join(rk, "ripristino.json"), "w"))
b8b = load_brain(os.path.join(vroot, "backend", "klippeye_backend.py"), rk, brain_json={"values": {"enabled": False}})
check("... e con un ripristino registrato lo riporta", b8b.app.test_client().get("/api/version").get_json()["repair"] == {"time": 1, "restored": ["a"], "failed": []})
open(os.path.join(rk, "ripristino.json"), "w").write("{rovinato")
check("... un ripristino.json rovinato non rompe /api/version", b8b.app.test_client().get("/api/version").get_json()["repair"] is None)
rk2 = tmp(); os.makedirs(rk2, exist_ok=True)
json.dump({"time": 2, "restored": ["b"], "failed": []}, open(os.path.join(rk2, "repair.json"), "w"))
b8c = load_brain(NEW_BRAIN, rk2, brain_json={"values": {"enabled": False}})
check("1.3.0: l'ultimo ripristino si legge da repair.json", b8c.app.test_client().get("/api/version").get_json()["repair"] == {"time": 2, "restored": ["b"], "failed": []})
mg = tmp(); os.makedirs(os.path.join(mg, "allarmi"), exist_ok=True)
open(os.path.join(mg, "allarmi", "storico.jsonl"), "w").write(json.dumps({"id": "20260101-000000", "esito": "analizzato", "con_foto_di_prima": True, "osservazione": "x", "image": "20260101-000000-adesso.jpg"}) + "\n")
open(os.path.join(mg, "allarmi", "20260101-000000-adesso.jpg"), "wb").write(b"\xff\xd8\xff\xd9")
bmg = load_brain(NEW_BRAIN, mg, brain_json={"values": {"enabled": False, "sensitivity": 44}})
check("1.3.0: brain.json diventa monitor.json (stesse soglie)", os.path.isfile(os.path.join(mg, "monitor.json")) and not os.path.exists(os.path.join(mg, "brain.json")) and bmg.brain_config.snapshot()["sensitivity"] == 44, os.listdir(mg))
check("... allarmi/ diventa alerts/ e storico.jsonl history.jsonl", os.path.isfile(os.path.join(mg, "alerts", "history.jsonl")) and not os.path.exists(os.path.join(mg, "allarmi")), os.listdir(mg))
h_old = bmg.read_alert_history()
check("... gli eventi vecchi si leggono con le chiavi inglesi", h_old and h_old[0]["outcome"] == "analizzato" and h_old[0]["with_reference"] is True and h_old[0]["observation"] == "x" and "esito" not in h_old[0], h_old)
check("... e le loro foto si scaricano ancora", bmg.app.test_client().get("/api/print/alerts/image/20260101-000000-adesso.jpg").status_code == 200)

# chiave dell'IA: nuovo posto con permessi 600, vecchio posto ancora letto
dk = tmp()
bk = load_brain(NEW_BRAIN, dk, brain_json={"values": {"enabled": False}})
ck = bk.app.test_client()
r = ck.post("/api/ai/config", json={"api_key": "k" * 30, "provider": "groq"})
j = r.get_json()
mode = stat.S_IMODE(os.stat(os.path.join(dk, "ai.json")).st_mode)
check("salvare la chiave dell'IA: va in ai.json con permessi 600", r.status_code == 200 and j["saved_to"] == [os.path.join(dk, "ai.json")] and mode == 0o600, (j, oct(mode)))
g = ck.get("/api/ai/config").get_json()
check("... e la chiave non esce intera", g["configured"] and "k" * 30 not in json.dumps(g) and g["provider"] == "groq", g)
check("... load_ai_config la legge", bk.load_ai_config()["api_key"] == "k" * 30)
# files of before release 1.0 in the home folder: copied once into the data folder
old_home = tmp()
os.makedirs(os.path.join(old_home, "printer_data", "config"))
json.dump({"api_key": "L" * 30, "provider": "openai"}, open(os.path.join(old_home, "vzbot_ai_config.json"), "w"))
json.dump({"selected": ["a", "b"]}, open(os.path.join(old_home, "printer_data", "config", "vzbot_calibration_selected.json"), "w"))
saved_home = os.environ["HOME"]
os.environ["HOME"] = old_home
dk2 = tmp()
bk2 = load_brain(NEW_BRAIN, dk2, brain_json={"values": {"enabled": False}})
check("old files: the AI key of before 1.0 is copied into the data folder (mode 600) and read", bk2.load_ai_config()["api_key"] == "L" * 30 and stat.S_IMODE(os.stat(os.path.join(dk2, "ai.json")).st_mode) == 0o600)
check("... and the chosen calibrations too", bk2.load_calibration_selected() == ["a", "b"])
bk2.app.test_client().post("/api/ai/config", json={"api_key": "N" * 30})
bk3 = load_brain(NEW_BRAIN, dk2, brain_json={"values": {"enabled": False}})
check("... only once: a new key is not overwritten by the old file at the next start", bk3.load_ai_config()["api_key"] == "N" * 30)
check("... the old file is not touched", json.load(open(os.path.join(old_home, "vzbot_ai_config.json")))["api_key"] == "L" * 30)
os.environ["HOME"] = saved_home

# ponte verso Moonraker: attesa lunga solo per update/servizi
seen = {}


class FakeResp:
    status_code = 200
    headers = {"Content-Type": "application/json"}

    def iter_content(self, chunk_size=8192):
        yield b"{}"


def fake_request(method, url, **kw):
    seen["timeout"] = kw.get("timeout")
    return FakeResp()


bp = load_brain(NEW_BRAIN, tmp(), brain_json={"values": {"enabled": False}})
real_request = bp.requests.request
bp.requests.request = fake_request
cp = bp.app.test_client()
cp.post("/machine/update/upgrade", json={"name": "klippeye"}).close()
check("ponte: /machine/update/* aspetta fino a 10 minuti", seen["timeout"] == (5, 600), seen)
cp.post("/machine/services/restart?service=klippeye").close()
check("ponte: /machine/services/* idem", seen["timeout"] == (5, 600), seen)
cp.get("/printer/info").close()
check("ponte: il resto resta a 10 secondi", seen["timeout"] == 10, seen)
bp.requests.request = real_request

# ---------------------------------------------------------------------------------------------------------------------
print("== Rilevatore: lo stesso comportamento di prima con i valori di sempre")
SQUARE = (60, 60, 120, 100)  # (x, y, w, h) nella fascia esterna dell'area di sempre? vedi sotto: l'area va da (216,144) a (864,576)
# fascia esterna dell'area di sempre: 25% dell'area -> da x=216 a 378 (sinistra), y=144..252 (alto)...
EDGE = (230, 160, 100, 100)  # dentro la fascia esterna in alto a sinistra dell'area
CENTER = (500, 330, 100, 100)  # al centro dell'area: non conta come sospetto
OUTSIDE = (20, 20, 100, 100)  # fuori dall'area controllata


def blink(rect, n, base=100):
    """n foto che alternano 'quadrato bianco' / 'niente': ogni confronto vede il quadrato apparire o sparire."""
    on, off = fakes.jpeg(fakes.frame(rect)), fakes.jpeg(fakes.frame())
    return [on if i % 2 == 0 else off for i in range(n)]


def run_scenario(path, fake, frames, seconds, brain_json=None, state=None, interval=None, extra=None):
    """Starts a Brain on the fake machine, lets it watch for `seconds`, returns (module, trace of stats)."""
    fake.snapshots = 0
    fake.state["frames"] = frames
    fake.state.update({"print_state": "printing", "progress": 0.5, "file_position": 5000, "file_size": 10000, "total_duration": 500.0,
                       "hotend": 210.0, "hotend_target": 210.0})
    if state:
        fake.state.update(state)
    values = {"enabled": False, "persistent_filter": False}  # i test di una volta provano il rilevamento di prima; il filtro nuovo ha la sua sezione
    values.update(brain_json or {})
    m = load_brain(path, tmp(), fake, brain_json={"values": values} if path == NEW_BRAIN else None)
    m.detector.last_ai_call = time.time() + 99999  # niente chiamata all'IA: qui conta solo quando scatta
    if path == NEW_BRAIN and interval:
        m.set_brain_config({"check_interval": interval})
    if extra:
        extra(m)
    m.detector.enabled = True
    m.detector.start()
    trace = []
    end = time.time() + seconds
    while time.time() < end:
        s = dict(m.detector.stats)
        trace.append((round(time.time() - (end - seconds), 1), s.get("frames_checked"), s.get("anomalies"), s.get("last_score"), s.get("last_trigger"), s.get("status")))
        time.sleep(0.5)
    m.detector.stop()
    time.sleep(0.3)
    return m, trace


fake = fakes.Fake()
frames_edge = blink(EDGE, 40)

if QUICK:
    print("  (salto il confronto al ritmo vero di 3 s: --quick)")
else:
    t0 = time.time()
    mo, to = run_scenario(OLD_BRAIN, fake, frames_edge, 22)
    old_stats = (mo.detector.stats["frames_checked"], mo.detector.stats["anomalies"], mo.detector.stats["last_trigger"] is not None, mo.detector.stats["last_score"])
    mn, tn = run_scenario(NEW_BRAIN, fake, frames_edge, 22)
    new_stats = (mn.detector.stats["frames_checked"], mn.detector.stats["anomalies"], mn.detector.stats["last_trigger"] is not None, mn.detector.stats["last_score"])
    print("      vecchio:", old_stats, " nuovo:", new_stats)
    check("stesso numero di foto controllate, anomalie, punteggio e scatto (vecchio Brain = nuovo con i valori di sempre)",
          abs(old_stats[0] - new_stats[0]) <= 1 and abs(old_stats[1] - new_stats[1]) <= 1 and old_stats[2] == new_stats[2] and abs(old_stats[3] - new_stats[3]) < 0.01, (old_stats, new_stats))
    check("... e il rilevamento scatta davvero (3 anomalie)", new_stats[2] is True and new_stats[1] >= 3, new_stats)

print("== Rilevatore: ogni soglia fa quello che dice (ritmo 1 s)")


def outcome(m):
    s = m.detector.stats
    return {"frames": s["frames_checked"], "anomalies": s["anomalies"], "triggered": s["last_trigger"] is not None, "score": s["last_score"], "status": s["status"]}


m, _ = run_scenario(NEW_BRAIN, fake, frames_edge, 9, interval=1)
base = outcome(m)
check("base: il quadrato ai bordi scatta con 3 anomalie", base["triggered"] and base["anomalies"] >= 3 and base["score"] > 2.5, base)
check("... il punteggio e' il peso del quadrato sull'area (circa 3-4%)", 2.5 < base["score"] < 6, base)

m, _ = run_scenario(NEW_BRAIN, fake, blink(CENTER, 40), 9, interval=1)
o = outcome(m)
check("movimento al centro dell'area: non conta (fascia esterna soltanto)", not o["triggered"] and o["anomalies"] == 0 and o["score"] < 1, o)

m, _ = run_scenario(NEW_BRAIN, fake, blink(OUTSIDE, 40), 9, interval=1)
o = outcome(m)
check("movimento fuori dall'area controllata: non conta", not o["triggered"] and o["anomalies"] == 0, o)

m, _ = run_scenario(NEW_BRAIN, fake, frames_edge, 9, interval=1, brain_json={"trigger_count": 1})
o = outcome(m)
check("trigger_count=1: scatta alla prima anomalia", o["triggered"], o)

m, _ = run_scenario(NEW_BRAIN, fake, frames_edge, 9, interval=1, brain_json={"trigger_count": 10})
o = outcome(m)
check("trigger_count=10: 9 secondi non bastano per scattare", not o["triggered"] and o["anomalies"] >= 3, o)

m, _ = run_scenario(NEW_BRAIN, fake, frames_edge, 9, interval=1, brain_json={"score_threshold": 8})
o = outcome(m)
check("score_threshold=8: il quadrato (3-4%) non basta", not o["triggered"] and o["anomalies"] == 0 and o["score"] > 0, o)

m, _ = run_scenario(NEW_BRAIN, fake, frames_edge, 9, interval=1, brain_json={"score_threshold": 0.5})
o = outcome(m)
check("score_threshold=0.5: scatta", o["triggered"], o)

m, _ = run_scenario(NEW_BRAIN, fake, frames_edge, 9, interval=1, brain_json={"sensitivity": 100})
o = outcome(m)
check("sensitivity=100 (soglia piu' alta): il quadrato 255 su 100 (salto 155) conta ancora", o["triggered"], o)

dim = [fakes.jpeg(fakes.frame((230, 160, 100, 100)) // 5 + 80) if i % 2 == 0 else fakes.jpeg(fakes.frame() // 5 + 80) for i in range(40)]  # salto di circa 31 livelli
m, _ = run_scenario(NEW_BRAIN, fake, dim, 9, interval=1, brain_json={"sensitivity": 35})
o35 = outcome(m)
m, _ = run_scenario(NEW_BRAIN, fake, dim, 9, interval=1, brain_json={"sensitivity": 10})
o10 = outcome(m)
check("sensitivity: un salto di ~31 livelli non passa con 35 ma passa con 10", not o35["triggered"] and o10["triggered"], (o35, o10))

m, _ = run_scenario(NEW_BRAIN, fake, frames_edge, 9, interval=1, brain_json={"roi": [0, 0, 100, 100]})
o = outcome(m)
check("area = tutta l'immagine: la stessa macchia pesa molto meno sull'area (e non scatta)", not o["triggered"] and 0 < o["score"] < base["score"] / 2, (o, base))

m, _ = run_scenario(NEW_BRAIN, fake, frames_edge, 9, interval=1, brain_json={"roi": [50, 50, 50, 50]})
o = outcome(m)
check("area spostata in basso a destra: il quadrato non e' piu' dentro", not o["triggered"] and o["score"] == 0, o)

m, _ = run_scenario(NEW_BRAIN, fake, frames_edge, 9, interval=1, brain_json={"border": 10})
o = outcome(m)
check("border=10: la fascia e' piu' stretta (il quadrato la copre solo in parte) e il punteggio scende", o["score"] < base["score"], (o, base))

# intervallo: quante foto in 7 secondi
m, _ = run_scenario(NEW_BRAIN, fake, blink(CENTER, 80), 7, interval=1)
fast = outcome(m)["frames"]
m, _ = run_scenario(NEW_BRAIN, fake, blink(CENTER, 80), 7, interval=3)
slow = outcome(m)["frames"]
check("check_interval: 1 s controlla piu' foto di 3 s", fast >= slow + 2, (fast, slow))

# avvio: non controlla durante riscaldamento
m, _ = run_scenario(NEW_BRAIN, fake, frames_edge, 5, interval=1, state={"total_duration": 60.0})
o = outcome(m)
check("durata 60 s < 90 s: attende, nessuna foto controllata", o["frames"] == 0 and "duration 60s <90s" in m.detector.stats.get("real_print_reason", ""), (o, m.detector.stats.get("real_print_reason")))
m, _ = run_scenario(NEW_BRAIN, fake, frames_edge, 9, interval=1, state={"total_duration": 60.0}, brain_json={"warmup_seconds": 30})
o = outcome(m)
check("warmup_seconds=30: con 60 s di stampa il controllo parte", o["frames"] > 0 and o["triggered"], o)
m, _ = run_scenario(NEW_BRAIN, fake, frames_edge, 5, interval=1, state={"progress": 0.01, "file_position": 50, "file_size": 10000})
o = outcome(m)
check("avanzamento 1% < 2%: attende", o["frames"] == 0 and "<2%" in m.detector.stats.get("real_print_reason", ""), (o, m.detector.stats.get("real_print_reason")))
m, _ = run_scenario(NEW_BRAIN, fake, frames_edge, 9, interval=1, state={"progress": 0.01, "file_position": 50, "file_size": 10000}, brain_json={"min_progress": 0.5})
o = outcome(m)
check("min_progress=0.5: con 1% il controllo parte", o["frames"] > 0, o)
m, _ = run_scenario(NEW_BRAIN, fake, frames_edge, 5, interval=1, state={"hotend": 190.0})
o = outcome(m)
check("ugello 20 gradi sotto il target (tolleranza 8): attende", o["frames"] == 0 and "not at temperature" in m.detector.stats.get("real_print_reason", ""), (o, m.detector.stats.get("real_print_reason")))
m, _ = run_scenario(NEW_BRAIN, fake, frames_edge, 9, interval=1, state={"hotend": 190.0}, brain_json={"hotend_tolerance": 25})
o = outcome(m)
check("hotend_tolerance=25: il controllo parte", o["frames"] > 0, o)
m, tr = run_scenario(NEW_BRAIN, fake, frames_edge, 4, interval=1, state={"print_state": "standby"})
o = outcome(m)
check("senza stampa in corso: non controlla", o["frames"] == 0 and "idle" in str(tr[-1][5]), (o, tr[-1]))

# cooldown dopo lo scatto
m, tr = run_scenario(NEW_BRAIN, fake, frames_edge, 12, interval=1, brain_json={"cooldown": 10})
trig = [t for t in tr if t[4]]
check("dopo lo scatto parte la pausa ('cooldown Ns')", any("cooldown" in str(t[5]) for t in tr), tr[-3:])

# ---------------------------------------------------------------------------------------------------------------------
print("== Filtro anti falsi allarmi: testina che passa, luce, macchia che resta")
HEAD_POS = [(230, 160, 100, 100), (390, 160, 100, 100), (550, 160, 100, 100), (710, 160, 100, 100)]  # una "testina" che salta da un punto all'altro della fascia alta
head_frames = [fakes.jpeg(fakes.frame(HEAD_POS[i % 4])) for i in range(80)]
FILTER = {"persistent_filter": True, "reference_seconds": 20, "persist_checks": 3}
BLOB = (230, 160, 100, 100)
empty_j, blob_j = fakes.jpeg(fakes.frame()), fakes.jpeg(fakes.frame(BLOB))

m, _ = run_scenario(NEW_BRAIN, fake, head_frames, 22, interval=1, brain_json={})
o_old = outcome(m)
m, _ = run_scenario(NEW_BRAIN, fake, head_frames, 30, interval=1, brain_json=FILTER)
o_new = outcome(m)
check("testina che salta nella fascia esterna: il rilevamento di prima scatta (falso allarme)", o_old["triggered"], o_old)
check("... con il filtro NO: nessuna anomalia, nessuno scatto", not o_new["triggered"] and o_new["anomalies"] == 0 and o_new["frames"] > 12, o_new)

flicker = [fakes.jpeg(fakes.frame(base=100 if i % 2 == 0 else 150)) for i in range(80)]  # luce che cambia ovunque di 50 livelli
m, _ = run_scenario(NEW_BRAIN, fake, flicker, 22, interval=1, brain_json={})
o_old = outcome(m)
m, _ = run_scenario(NEW_BRAIN, fake, flicker, 30, interval=1, brain_json=FILTER)
o_new = outcome(m)
check("luce che cambia in tutta l'immagine: il rilevamento di prima scatta", o_old["triggered"], o_old)
check("... con il filtro la luminosita' media viene allineata: niente anomalie", not o_new["triggered"] and o_new["anomalies"] == 0, o_new)

half = [fakes.jpeg(fakes.frame((0, 0, 540, 720))) if i % 2 == 0 else empty_j for i in range(80)]  # meta' immagine cambia di colpo: luce, camera mossa
m, _ = run_scenario(NEW_BRAIN, fake, half, 30, interval=1, brain_json=FILTER)
o = outcome(m)
check("meta' immagine cambia di colpo: il controllo viene ignorato (cambio di luce)", not o["triggered"] and o["anomalies"] == 0 and m.detector.stats.get("ignored_global", 0) > 3, (o, m.detector.stats))
half_stay = [empty_j] * 14 + [fakes.jpeg(fakes.frame((0, 0, 540, 720)))] * 60
m, _ = run_scenario(NEW_BRAIN, fake, half_stay, 38, interval=1, brain_json=FILTER, extra=lambda mm: setattr(mm.detector, "global_streak_max", 4))
o = outcome(m)
check("... ma se il grande cambiamento resta (non e' un lampo) dopo qualche controllo conta come cambiamento vero", o["triggered"], (o, m.detector.stats))

still = [empty_j] * 14 + [blob_j] * 70
m, _ = run_scenario(NEW_BRAIN, fake, still, 30, interval=1, brain_json={})
o_old = outcome(m)
m, _ = run_scenario(NEW_BRAIN, fake, still, 36, interval=1, brain_json=FILTER)
o_new = outcome(m)
check("macchia che compare ai bordi e RESTA (spaghetti fermi): il rilevamento di prima non se ne accorge", not o_old["triggered"], o_old)
check("... con il filtro scatta", o_new["triggered"], o_new)

mixed = [fakes.jpeg(fakes.frame(HEAD_POS[i % 4])) for i in range(14)] + [fakes.jpeg(fakes.frame(HEAD_POS[i % 4], (230, 440, 100, 100))) for i in range(80)]  # testina + macchia ferma in basso
m, _ = run_scenario(NEW_BRAIN, fake, mixed, 38, interval=1, brain_json=FILTER)
o = outcome(m)
check("testina che passa E macchia che resta: scatta per la macchia, non per la testina", o["triggered"], o)

m, tr6 = run_scenario(NEW_BRAIN, fake, still, 6, interval=1, brain_json=FILTER)
o = outcome(m)
check("all'inizio prepara lo sfondo: nessun allarme prima di avere 5 foto ('preparo il confronto')", not o["triggered"] and o["anomalies"] == 0, (o, m.detector.stats["status"]))
check("... e lo dice nello stato", any("preparing the comparison" in str(t[5]) for t in tr6), [t[5] for t in tr6])  # lo stato si legge MENTRE gira: a rilevatore fermo dice solo "stopped"

m, _ = run_scenario(NEW_BRAIN, fake, still, 24, interval=1, brain_json=dict(FILTER, persistent_filter=False))
check("filtro spento: torna il rilevamento di prima (nessuna foto di sfondo conservata)", len(m.detector.ref_small) == 0 and m.detector.bg is None)
m, _ = run_scenario(NEW_BRAIN, fake, still, 30, interval=1, brain_json=FILTER)
check("memoria limitata: al massimo 7 foto di sfondo (e 7 foto dalla camera)", 0 < len(m.detector.ref_small) <= 7 and len(m.detector.ref_jpegs) <= 7, (len(m.detector.ref_small), len(m.detector.ref_jpegs)))
m, _ = run_scenario(NEW_BRAIN, fake, still, 4, interval=1, brain_json=FILTER, state={"print_state": "standby"})
check("senza stampa in corso lo sfondo si azzera (una stampa nuova riparte da capo)", len(m.detector.ref_small) == 0 and m.detector.bg is None)


# acceso/spento a caldo
mt = load_brain(NEW_BRAIN, tmp(), fake, brain_json={"values": {"enabled": True}})
fake.state["frames"] = blink(CENTER, 80)
fake.snapshots = 0
time.sleep(0.5)
ct = mt.app.test_client()
check("enabled=true salvato: all'avvio il rilevatore parte da solo", mt.detector.running is True)
ct.post("/api/backend/config", json={"values": {"enabled": False}})
check("Monitor spento dal menu: il rilevatore si ferma subito", mt.detector.running is False and mt.detector.enabled is False)
ct.post("/api/backend/config", json={"values": {"enabled": True}})
check("... e riacceso dal menu riparte", mt.detector.running is True and mt.detector.enabled is True)
gen_before = mt.detector.generation
ct.post("/api/backend/config", json={"values": {"check_interval": 1}})
ct.post("/api/backend/config", json={"values": {"enabled": False}})
ct.post("/api/backend/config", json={"values": {"enabled": True}})
time.sleep(2.5)
import threading  # noqa: E402
loops = [t for t in threading.enumerate() if t.is_alive() and getattr(t, "_target", None) and getattr(t._target, "__name__", "") == "loop" and getattr(t._target, "__self__", None) is mt.detector]
check("spegni e riaccendi in fretta: resta UN solo ciclo (nessun doppione)", len(loops) == 1, len(loops))
mt.detector.stop()

# foto di allarme: non si accumulano
alerts = tmp()
for i in range(15):
    p = os.path.join(alerts, "klippeye_alert_%d.jpg" % (1000 + i))
    open(p, "wb").write(b"x")
    os.utime(p, (1000 + i, 1000 + i))
mt.prune_alert_images(pattern=os.path.join(alerts, "klippeye_alert_*.jpg"))
left = sorted(os.listdir(alerts))
check("prune_alert_images tiene le ultime 10", len(left) == 10 and "klippeye_alert_1014.jpg" in left and "klippeye_alert_1004.jpg" not in left and "klippeye_alert_1005.jpg" in left, left)

# modello IA: il Brain lo usa al posto di quello predefinito
cap = {}


class AIResp:
    ok = True
    status_code = 200

    def json(self):
        return {"choices": [{"message": {"content": json.dumps({"spaghetti": {"detected": False, "confidence": 10}, "action": "CONTINUA", "summary": "tutto bene"})}}]}


def fake_post(url, headers=None, json=None, timeout=None):
    cap["url"], cap["model"] = url, json["model"]
    return AIResp()


real_post = __import__("requests").post
for provider, expected_default in (("groq", "qwen/qwen3.8-27b"), ("openai", "gpt-4o-mini")):
    dm = tmp()
    mm = load_brain(NEW_BRAIN, dm, fake, brain_json={"values": {"enabled": False}})
    mm.requests.post = fake_post
    mm.AI_CONFIG_PATH = os.path.join(dm, "ai.json")
    json.dump({"api_key": "k" * 30, "provider": provider}, open(mm.AI_CONFIG_PATH, "w"))
    img = os.path.join(dm, "a.jpg")
    open(img, "wb").write(fakes.jpeg(fakes.frame()))
    mm.detector.last_ai_call = 0
    mm.detector.call_ai_analysis(img)
    check("IA %s: senza modello scelto usa quello predefinito" % provider, cap.get("model") == expected_default, cap)
    mm.set_brain_config({"ai_model": "mio/modello-nuovo"})
    mm.detector.last_ai_call = 0
    mm.detector.call_ai_analysis(img)
    check("IA %s: con ai_model scelto usa quello" % provider, cap.get("model") == "mio/modello-nuovo", cap)
    check("IA %s: l'analisi viene salvata (CONTINUA della risposta diventa CONTINUE)" % provider, mm.detector.last_analysis and mm.detector.last_analysis["analysis"]["action"] == "CONTINUE")

# ---------------------------------------------------------------------------------------------------------------------
print("== IA: richiesta con foto di prima, testo neutro, fiducia minima, storico degli allarmi")
prompt1 = mm.build_ai_prompt(3.1, "printing", "x.gcode", 12.0, 210.0, None)
prompt2 = mm.build_ai_prompt(3.1, "printing", "x.gcode", 12.0, 210.0, 55, "it")
check("il testo (in inglese) non dice 'spaghetti suspected' ne' 'VzBot' e dice cosa NON e' un problema", "suspect" not in prompt1 and "VzBot" not in prompt1 and "NOT PROBLEMS" in prompt1 and "print head" in prompt1 and "when in doubt" in prompt1, prompt1[:300])
check("con la foto di prima il testo spiega 'before'/'now' (circa 55 s), senza dice 'ONE picture'", "TWO pictures" in prompt2 and "55 seconds" in prompt2 and "ONE picture" in prompt1)
check("il formato della risposta: chiavi e parole del verdetto in inglese (+ 'observation')", all(k in prompt1 for k in ('"spaghetti"', '"empty_bed"', '"layer_shift"', '"warping"', '"action"', '"summary"', '"observation"', "CONTINUE|PAUSE|CANCEL")))
check("i testi liberi nella lingua scelta: inglese di serie, italiano se richiesto", 'in English;' in prompt1 and 'in Italian;' in prompt2)
check("normalize_action: parole inglesi e italiane, maiuscole o no", [mm.normalize_action(v) for v in ("PAUSA", "pause", "Cancella la stampa", "CANCEL", "CONTINUA", "continue", "", None)] == ["PAUSE", "PAUSE", "CANCEL", "CANCEL", "CONTINUE", "CONTINUE", "", ""])

seen_calls = []


def ai_reply(defect_confidence=40, action="PAUSA", fail_two=False, english=False):
    def _post(url, headers=None, json=None, timeout=None):
        images = [c for c in json["messages"][1]["content"] if c.get("type") == "image_url"]
        seen_calls.append(len(images))

        class R:
            ok = True
            status_code = 200
            text = "rifiutato"

            def json(self_inner):
                return {"choices": [{"message": {"content": __import__("json").dumps({("observation" if english else "osservazione"): ("the head" if english else "la testina"), "spaghetti": {"detected": True, "confidence": defect_confidence},
                                                                                        "empty_bed": {"detected": False, "confidence": 0}, "action": action, "summary": "forse un problema"})}}]}
        r = R()
        if fail_two and len(images) == 2:
            r.ok, r.status_code = False, 400
        return r
    return _post


def fresh_ai(post):
    dd = tmp()
    b_ai = load_brain(NEW_BRAIN, dd, fake, brain_json={"values": {"enabled": False}})
    b_ai.requests.post = post
    b_ai.AI_CONFIG_PATH = os.path.join(dd, "ai.json")
    json.dump({"api_key": "k" * 30, "provider": "groq"}, open(b_ai.AI_CONFIG_PATH, "w"))
    cur, prev = os.path.join(dd, "a.jpg"), os.path.join(dd, "a_prima.jpg")
    open(cur, "wb").write(fakes.jpeg(fakes.frame(BLOB)))
    open(prev, "wb").write(fakes.jpeg(fakes.frame()))
    b_ai.detector.last_ai_call = 0
    return b_ai, cur, prev


del seen_calls[:]
b_ai, cur, prev = fresh_ai(ai_reply(defect_confidence=40))
b_ai.detector.call_ai_analysis(cur, prev, 60)
check("con la foto di prima: l'IA riceve DUE foto", seen_calls == [2], seen_calls)
check("... difetto con fiducia 40% sotto la soglia 70%: PAUSA diventa CONTINUE e resta scritto l'originale (PAUSE)",
      b_ai.detector.last_analysis["analysis"]["action"] == "CONTINUE" and b_ai.detector.last_analysis["analysis"]["original_action"] == "PAUSE" and "threshold 70%" in b_ai.detector.last_analysis["analysis"]["summary"], b_ai.detector.last_analysis)
check("... e /api/print/last_analysis lo mostra cosi' (e dice 'forse un problema' nel riassunto)", "forse un problema" in b_ai.app.test_client().get("/api/print/last_analysis").get_json()["analysis"]["summary"])
hist = b_ai.read_alert_history()
check("storico: un evento con esito 'declassato', verdetto, osservazione e le due foto copiate",
      len(hist) == 1 and "downgraded" in hist[0]["outcome"] and hist[0]["action"] == "CONTINUE" and hist[0]["original_action"] == "PAUSE" and hist[0]["observation"] == "la testina"
      and os.path.isfile(os.path.join(b_ai.ALERT_HISTORY_DIR, hist[0]["image"])) and os.path.isfile(os.path.join(b_ai.ALERT_HISTORY_DIR, hist[0]["reference"])), hist)
cl_ai = b_ai.app.test_client()
j = cl_ai.get("/api/print/alerts/history").get_json()
check("/api/print/alerts/history elenca gli allarmi (piu' recente per primo)", j["ok"] and len(j["alerts"]) == 1 and j["alerts"][0]["id"] == hist[0]["id"])
r = cl_ai.get("/api/print/alerts/image/" + hist[0]["image"])
check("/api/print/alerts/image/<nome> manda la foto (jpeg)", r.status_code == 200 and r.mimetype == "image/jpeg" and r.data[:2] == b"\xff\xd8")
r.close()
check("... e rifiuta nomi strani (niente percorsi): 404", all(cl_ai.get("/api/print/alerts/image/" + n).status_code == 404 for n in ("..%2F..%2Fai.json", "ai.json", "20260101-000000-now.png", "x-now.jpg")))

b_ai, cur, prev = fresh_ai(ai_reply(defect_confidence=85))
b_ai.detector.call_ai_analysis(cur, prev, 60)
check("difetto con fiducia 85% sopra la soglia: resta PAUSE", b_ai.detector.last_analysis["analysis"]["action"] == "PAUSE" and "original_action" not in b_ai.detector.last_analysis["analysis"])
b_ai, cur, prev = fresh_ai(ai_reply(defect_confidence=40))
b_ai.set_brain_config({"ai_min_confidence": 0})
b_ai.detector.call_ai_analysis(cur, prev, 60)
check("ai_min_confidence=0: si fida sempre (resta PAUSE)", b_ai.detector.last_analysis["analysis"]["action"] == "PAUSE")
b_ai, cur, prev = fresh_ai(ai_reply(defect_confidence=40, action="PAUSE", english=True))
b_ai._SHARED_LANGUAGE.update(value="it", at=time.time())
b_ai.detector.call_ai_analysis(cur, prev, 60)
check("1.6: risposta all'inglese (PAUSE, observation) e lingua delle notifiche italiana: il motivo del declassamento e' in italiano",
      b_ai.detector.last_analysis["analysis"]["action"] == "CONTINUE" and b_ai.detector.last_analysis["analysis"]["original_action"] == "PAUSE"
      and "soglia 70%" in b_ai.detector.last_analysis["analysis"]["summary"] and b_ai.read_alert_history()[0]["observation"] == "the head", b_ai.detector.last_analysis)
b_ai, cur, prev = fresh_ai(ai_reply(defect_confidence=40))
b_ai.set_brain_config({"ai_send_reference": False})
del seen_calls[:]
b_ai.detector.call_ai_analysis(cur, None, None)
check("senza foto di prima (o con l'opzione spenta): una foto sola", seen_calls == [1], seen_calls)
b_ai, cur, prev = fresh_ai(ai_reply(defect_confidence=85, fail_two=True))
del seen_calls[:]
b_ai.detector.call_ai_analysis(cur, prev, 60)
check("il servizio rifiuta due foto (400): riprova da solo con una e l'analisi arriva comunque", seen_calls == [2, 1] and b_ai.detector.last_analysis["analysis"]["action"] == "PAUSE" and b_ai.detector.last_analysis["with_reference"] is False, (seen_calls, b_ai.detector.last_analysis))
check("... e lo storico lo segna ('senza foto di prima', senza copiare quella)", b_ai.read_alert_history()[0]["with_reference"] is False and "reference" not in b_ai.read_alert_history()[0])

b_ai, cur, prev = fresh_ai(ai_reply())
b_ai.detector.last_ai_call = time.time()
b_ai.detector.call_ai_analysis(cur, prev, 60)
check("pausa tra due analisi non finita: salta ma lo scrive nello storico", "skipped" in b_ai.read_alert_history()[0]["outcome"])

b_ai, cur, prev = fresh_ai(ai_reply())
for i in range(45):
    b_ai.record_alert({"outcome": "test %d" % i}, cur, prev)
    time.sleep(0.002) if i % 7 == 0 else None
lines = open(os.path.join(b_ai.ALERT_HISTORY_DIR, "history.jsonl")).read().splitlines()
jpgs = [n for n in os.listdir(b_ai.ALERT_HISTORY_DIR) if n.endswith(".jpg")]
check("lo storico tiene gli ultimi 40 eventi e cancella le foto degli altri", len(lines) == 40 and len(jpgs) <= 80, (len(lines), len(jpgs)))
bad_dir = tmp()
b_ai.ALERT_HISTORY_DIR = os.path.join(bad_dir, "file")
open(b_ai.ALERT_HISTORY_DIR, "w").write("x")
b_ai.record_alert({"outcome": "x"}, cur, prev)
check("cartella dello storico non scrivibile: nessuna eccezione (il monitor non si ferma)", True)

check("impostazioni nuove: valori di serie (filtro acceso, 3 controlli, 60 s, 30%, fiducia 70%, foto di prima accesa)",
      (lambda v: v["persistent_filter"] is True and v["persist_checks"] == 3 and v["reference_seconds"] == 60 and v["global_change"] == 30 and v["ai_min_confidence"] == 70 and v["ai_send_reference"] is True)(mm.brain_config.snapshot()))
r = mm.app.test_client().post("/api/backend/config", json={"values": {"persist_checks": 5, "reference_seconds": 90, "ai_min_confidence": 55, "persistent_filter": False}})
check("... si cambiano dal menu e arrivano al rilevatore", r.status_code == 200 and mm.detector.persist_checks == 5 and mm.detector.recent_masks.maxlen == 5 and mm.detector.reference_seconds == 90
      and mm.detector.ai_min_confidence == 55 and mm.detector.persistent_filter is False, r.get_json())
r = mm.app.test_client().post("/api/backend/config", json={"values": {"persist_checks": 1, "reference_seconds": 5, "global_change": 500, "ai_min_confidence": 101}})
check("... valori fuori limite: 400 con un errore per voce", r.status_code == 400 and set(r.get_json()["errors"]) == {"persist_checks", "reference_seconds", "global_change", "ai_min_confidence"}, r.get_json())


# ---------------------------------------------------------------------------------------------------------------------
print("== App Android: /api/app/version e /app/KlippEye.apk")
import hashlib  # noqa: E402

da = tmp()
ba = load_brain(NEW_BRAIN, da, brain_json={"values": {"enabled": False}})
cl = ba.app.test_client()
apkdir = os.path.join(tmp(), "apk")
ba.APK_DIR, ba.APK_PATH, ba.APK_INFO_PATH = apkdir, os.path.join(apkdir, "KlippEye.apk"), os.path.join(apkdir, "version.json")
check("la cartella apk/ del repository e' accanto a backend/ (come scrive il workflow)", os.path.basename(NEW_BRAIN) == "klippeye_backend.py"
      and load_brain(NEW_BRAIN, tmp(), brain_json={"values": {"enabled": False}}).APK_PATH == os.path.join(os.path.dirname(os.path.dirname(NEW_BRAIN)), "apk", "KlippEye.apk"))
r = cl.get("/api/app/version")
j = r.get_json()
check("senza apk/: 200, available=false e il motivo (in inglese di serie)", r.status_code == 200 and j["ok"] and j["available"] is False and "no app published" in j["reason"], j)
cl.set_cookie("klippeye_lang", "it")
check("... e in italiano per una dashboard in italiano (cookie klippeye_lang)", "nessuna app" in cl.get("/api/app/version").get_json()["reason"])
cl.delete_cookie("klippeye_lang")
check("... e il file non si scarica (404 con il motivo)", cl.get("/app/KlippEye.apk").status_code == 404 and cl.get("/app/KlippEye.apk").get_json()["ok"] is False)

apk = bytes((i * 7 + 3) % 251 for i in range(300000))
os.makedirs(apkdir)
open(ba.APK_PATH, "wb").write(apk)
info = {"version": "1.0.0", "code": 10000, "size": len(apk), "sha256": hashlib.sha256(apk).hexdigest(), "firma": "ab" * 32, "built": "2026-10-22T21:15:07Z", "source": "abc"}
json.dump(info, open(ba.APK_INFO_PATH, "w"))
r = cl.get("/api/app/version")
j = r.get_json()
check("con apk/ coerente: available, versione, codice, grandezza, impronta, indirizzo",
      r.status_code == 200 and j["available"] is True and j["version"] == "1.0.0" and j["code"] == 10000 and j["size"] == len(apk) and j["sha256"] == info["sha256"] and j["url"] == "/app/KlippEye.apk" and j["built"] == info["built"], j)
check("... la risposta non si tiene in cache", r.headers.get("Cache-Control") == "no-store")
check("... e non svela cose in piu' (niente percorsi del Raspberry, niente firma)", set(j) == {"ok", "available", "version", "code", "size", "sha256", "built", "url"}, set(j))
r = cl.get("/app/KlippEye.apk")
check("il file arriva uguale, come APK", r.status_code == 200 and r.data == apk and r.mimetype == "application/vnd.android.package-archive", (r.status_code, r.mimetype))
check("... con la grandezza giusta e il nome con la versione", int(r.headers["Content-Length"]) == len(apk) and "KlippEye-1.0.0.apk" in r.headers.get("Content-Disposition", ""), dict(r.headers))
check("... non si tiene in cache", r.headers.get("Cache-Control") == "no-store")
r = cl.get("/app/KlippEye.apk", headers={"Range": "bytes=100-199"})
check("... e si puo' riprendere (Range)", r.status_code == 206 and r.data == apk[100:200])
check("... solo con GET", cl.post("/app/KlippEye.apk").status_code == 405 and cl.post("/api/app/version").status_code == 405)

# il calcolo dell'impronta si rifa' solo se i file cambiano
calls = []
real_sha = ba._apk_sha256
ba._apk_sha256 = lambda path: (calls.append(path), real_sha(path))[1]
cl.get("/api/app/version")
cl.get("/api/app/version")
cl.get("/app/KlippEye.apk")
check("l'impronta non si ricalcola a ogni richiesta (file invariati)", calls == [], calls)
# ... ma si rifa' appena cambia qualcosa
apk2 = apk[:-1] + b"X"
open(ba.APK_PATH, "wb").write(apk2)
j = cl.get("/api/app/version").get_json()
check("APK cambiato ma version.json no: non si offre (impronta diversa)", j["available"] is False and "fingerprint" in j["reason"] and len(calls) == 1, (j, calls))
check("... e il file non si scarica", cl.get("/app/KlippEye.apk").status_code == 404)
info.update(sha256=hashlib.sha256(apk2).hexdigest(), version="1.0.1", code=10001)
json.dump(info, open(ba.APK_INFO_PATH, "w"))
j = cl.get("/api/app/version").get_json()
check("version.json aggiornato insieme all'APK: si offre la nuova", j["available"] is True and j["version"] == "1.0.1" and j["code"] == 10001 and cl.get("/app/KlippEye.apk").data == apk2)
ba._apk_sha256 = real_sha

# file rovinati / aggiornamento a meta'
def offre():
    return cl.get("/api/app/version").get_json()

open(ba.APK_PATH, "wb").write(apk2[:1000])
j = offre()
check("APK piu' corto di quanto dice version.json (git a meta'): non si offre", j["available"] is False and "does not match" in j["reason"], j)
open(ba.APK_PATH, "wb").write(apk2)
check("... a lavoro finito torna disponibile da solo", offre()["available"] is True)
for contenuto, nome in ((b"{rotto", "JSON rotto"), (b"[1,2]", "non e' un oggetto"), (b'{"version":"boh","sha256":"%s","size":%d}' % (info["sha256"].encode(), len(apk2)), "versione non valida"),
                        (b'{"version":"1.0.1","sha256":"abc","size":%d}' % len(apk2), "impronta non valida"), (b'{"version":"1.0.1","sha256":"%s"}' % info["sha256"].encode(), "manca la grandezza"),
                        (b'{"version":"1.0.100","sha256":"%s","size":%d}' % (info["sha256"].encode(), len(apk2)), "versione fuori dai limiti")):
    open(ba.APK_INFO_PATH, "wb").write(contenuto)
    j = offre()
    check("version.json " + nome + ": non si offre, nessun errore 500", j["available"] is False and j["ok"] is True and cl.get("/app/KlippEye.apk").status_code == 404, j)
info["sha256"] = info["sha256"].upper()
json.dump(info, open(ba.APK_INFO_PATH, "w"))
check("l'impronta scritta in maiuscolo si riconosce lo stesso (e si restituisce minuscola)", offre()["available"] is True and offre()["sha256"] == info["sha256"].lower())
os.remove(ba.APK_INFO_PATH)
check("manca version.json: non si offre", offre()["available"] is False)
json.dump(info, open(ba.APK_INFO_PATH, "w"))
os.remove(ba.APK_PATH)
check("manca l'APK: non si offre", offre()["available"] is False)
check("il codice della versione e' quello di Gradle e di Kotlin", [ba._apk_code(v) for v in ("1.0.0", "1.2.3", "0.0.1", "99.99.99", "1.0", "1.0.100", "mk218", None)] == [10000, 10203, 1, 999999, None, None, None, None])

# ---------------------------------------------------------------------------------------------------------------------
print("== KlippEye: printer logos, no names of the VzBot days")
r = cl.get("/app/VzBot.apk")
check("/app/VzBot.apk (the app of the VzBot days) is gone", r.status_code == 404, r.status_code)
saved_env = {k: os.environ.pop(k, None) for k in ("KLIPPEYE_DATA", "VZBOT_DATA")}
os.environ["VZBOT_DATA"] = tmp()
spec = importlib.util.spec_from_file_location("brain_oldenv", NEW_BRAIN)
mod = importlib.util.module_from_spec(spec); sys.modules["brain_oldenv"] = mod; spec.loader.exec_module(mod); _modules.append(mod)
check("VZBOT_DATA is no longer read", mod.DATA_DIR != os.environ["VZBOT_DATA"], mod.DATA_DIR)
check("/api/version has no 'legacy' and /api/migrate/... is gone", "legacy" not in mod.app.test_client().get("/api/version").get_json() and mod.app.test_client().get("/api/migrate/status").status_code == 404)
for k, v in saved_env.items():
    if v is None: os.environ.pop(k, None)
    else: os.environ[k] = v

# ---- loghi della stampante
dl = tmp()
bl = load_brain(NEW_BRAIN, dl, brain_json={"values": {"enabled": False}})
logos = os.path.join(tmp(), "logos")
os.makedirs(logos)
for name, content in (("vzbot.png", b"\x89PNG-vz"), ("voron.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>"), ("voron.png", b"\x89PNG-voron"), ("ratrig.webp", b"RIFFxxxxWEBP"),
                      ("evil.svg", b"<svg/>"), ("voron.gif", b"GIF89a"), ("README.md", b"x"), ("Voron.SVG", b"<svg/>")):
    open(os.path.join(logos, name), "wb").write(content)
open(os.path.join(logos, "ratrig.png"), "wb").write(b"0" * (bl.LOGO_MAX_BYTES + 1))
open(os.path.join(logos, "vuoto.png"), "wb").close()
os.symlink("/etc/passwd", os.path.join(logos, "vzbot.svg"))
bl.LOGOS_DIR = logos
cl2 = bl.app.test_client()
j = cl2.get("/api/logos").get_json()
check("/api/logos elenca un file per marca, solo i nomi previsti (svg prima di png), nell'ordine vzbot, voron, ratrig", j == {"ok": True, "files": ["vzbot.png", "voron.svg", "ratrig.webp"]}, j)
check("... e non si tiene in cache", cl2.get("/api/logos").headers.get("Cache-Control") == "no-store")
r = cl2.get("/logos/voron.svg")
check("/logos/voron.svg: 200, tipo SVG, e un SVG aperto da solo non esegue script", r.status_code == 200 and r.mimetype == "image/svg+xml" and r.data.startswith(b"<svg") and "default-src 'none'" in r.headers.get("Content-Security-Policy", "") and r.headers.get("X-Content-Type-Options") == "nosniff", dict(r.headers))
check("/logos/vzbot.png e /logos/ratrig.webp: il tipo giusto", cl2.get("/logos/vzbot.png").mimetype == "image/png" and cl2.get("/logos/ratrig.webp").mimetype == "image/webp")
for nome in ("evil.svg", "voron.gif", "README.md", "Voron.SVG", "voron.png", "ratrig.png", "vuoto.png", "vzbot.svg", "../README.md", "..%2Fbackend%2Fklippeye_backend.py", "%2e%2e/VERSION", "nonesiste.svg"):
    st = cl2.get("/logos/" + nome).status_code
    check("/logos/%s non si serve (404)" % nome, st in (404, 308), st)
bl.LOGOS_DIR = os.path.join(tmp(), "nessuna")
check("senza cartella logos/: elenco vuoto, nessun errore", cl2.get("/api/logos").get_json() == {"ok": True, "files": []})
check("... e nessun file", cl2.get("/logos/voron.svg").status_code == 404)

print("== Accesso (1.2.0): password facoltativa, gettoni, controlli di rete, permessi")
import subprocess as _sp
da = tmp()
os.makedirs(da, exist_ok=True)
for _n in ("ai.json", "service-account.json"):
    with open(os.path.join(da, _n), "w") as _f:
        _f.write('{"api_key": "' + "Z" * 30 + '"}' if _n == "ai.json" else "{}")
    os.chmod(os.path.join(da, _n), 0o644)
os.chmod(da, 0o755)
ba = load_brain(NEW_BRAIN, da, fake, brain_json={"values": {"enabled": False}})
_mode = lambda p: stat.S_IMODE(os.stat(p).st_mode)
check("all'avvio i segreti copiati a mano con permessi larghi tornano 600", _mode(os.path.join(da, "ai.json")) == 0o600 and _mode(os.path.join(da, "service-account.json")) == 0o600,
      (oct(_mode(os.path.join(da, "ai.json"))), oct(_mode(os.path.join(da, "service-account.json")))))
check("... e la cartella dati 700", _mode(da) == 0o700, oct(_mode(da)))
_tok_path = os.path.join(da, "internal.token")
internal = open(_tok_path).read().strip() if os.path.exists(_tok_path) else ""
check("gettone interno creato: lungo, permessi 600", len(internal) >= 64 and _mode(_tok_path) == 0o600, (len(internal), oct(_mode(_tok_path)) if os.path.exists(_tok_path) else None))
check("access.json creato con permessi 600", _mode(os.path.join(da, "access.json")) == 0o600)

ca = ba.app.test_client()
j = ca.get("/api/auth/status").get_json()
check("di serie la password NON e' attiva", j["ok"] and j["enabled"] is False and j["logged_in"] is True and j["network_checks"] is True, j)
check("senza password tutto si apre come prima (/api/version, la pagina)", ca.get("/api/version").status_code == 200 and ca.get("/").status_code in (200, 404))
g = ca.get("/api/ai/config").get_json()
check("anteprima della chiave IA: solo le ultime 4 lettere", g.get("key_preview") == "…ZZZZ", g)

# nome di rete (DNS rebinding) e origine
r = ca.get("/api/version", headers={"Host": "stampante-cattiva.example.com"})
check("chiamato con un nome di internet: 403 'host' con il comando per ammetterlo", r.status_code == 403 and r.get_json()["error"] == "host" and "host-add" in r.get_json()["message"], (r.status_code, r.get_json()))
for _h in ("192.168.1.17:8085", "172.25.170.177:8085", "klippeye.local:8085", "voron:8085", "[fe80::1]:8085", "localhost:8085", "stampante.lan"):
    if ca.get("/api/version", headers={"Host": _h}).status_code != 200:
        check("nome di rete ammesso: " + _h, False)
        break
else:
    check("ammessi: indirizzi IP (anche IPv6), nomi .local/.lan, nome senza punti, localhost", True)
r = ca.post("/api/gcode", json={"script": "M115"}, headers={"Origin": "http://sito-cattivo.example"})
check("un comando che arriva da un'altra pagina web: 403 'origin'", r.status_code == 403 and r.get_json()["error"] == "origin", (r.status_code, r.get_json()))
r = ca.post("/api/backend/config", json={"values": {"sensitivity": 40}}, headers={"Origin": "http://localhost"})
check("... dalla dashboard stessa (Origin = stesso indirizzo) passa", r.status_code == 200, (r.status_code, r.get_json()))
r = ca.get("/api/version", headers={"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "cors"})
check("lettura da un altro sito (Sec-Fetch-Site cross-site): 403", r.status_code == 403)
r = ca.get("/", headers={"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"})
check("... ma aprire la dashboard da un collegamento si puo'", r.status_code in (200, 404))
r = ca.get("/api/version", headers={"Origin": "http://sito-cattivo.example"})
check("niente piu' CORS aperto: nessun Access-Control-Allow-Origin", "Access-Control-Allow-Origin" not in r.headers, dict(r.headers))
r = ca.get("/api/version", headers={"Host": "nome.di.internet.com", "X-KlippEye-Token": internal})
check("i servizi del Raspberry (gettone interno) passano sempre", r.status_code == 200)

# attivo la password
r = ca.post("/api/auth/password", json={"new": "abc"})
check("password troppo corta: rifiutata", r.status_code == 400 and r.get_json()["error"] == "weak", r.get_json())
r = ca.post("/api/auth/password", json={"new": "segreta123"})
check("attivare la password: ok e questo dispositivo resta dentro (cookie)", r.status_code == 200 and "klippeye_session=" in r.headers.get("Set-Cookie", "") and "HttpOnly" in r.headers.get("Set-Cookie", ""), (r.status_code, r.headers.get("Set-Cookie")))
check("... il cookie e' SameSite=Strict", "SameSite=Strict" in r.headers.get("Set-Cookie", ""))
saved = json.load(open(os.path.join(da, "access.json")))
check("in access.json non c'e' la password, solo il suo hash con sale", saved["enabled"] and "segreta123" not in json.dumps(saved) and len(saved["hash"]) == 64 and len(saved["salt"]) == 32, saved)
check("chi l'ha attivata continua a usare la dashboard", ca.get("/api/version").status_code == 200)

cb = ba.app.test_client()   # un altro dispositivo, senza cookie
r = cb.get("/api/version")
check("un altro dispositivo senza accesso: 401 con il segnale X-KlippEye-Login", r.status_code == 401 and r.headers.get("X-KlippEye-Login") == "1" and r.get_json()["error"] == "login", (r.status_code, dict(r.headers)))
r = cb.get("/")
check("... aprendo la dashboard va alla pagina di accesso", r.status_code == 303 and r.headers["Location"].endswith("/login"), (r.status_code, r.headers.get("Location")))
r = cb.get("/login")
check("... che e' una pagina con il modulo della password", r.status_code == 200 and b'name="password"' in r.data and b"klippeye password remove" in r.data and r.headers.get("X-Frame-Options") == "DENY")
blocked = {p: cb.get(p).status_code for p in ("/webcam/?action=snapshot", "/printer/info", "/server/files/list", "/api/print/snapshot", "/api/logs/list")}
check("... camera, Moonraker, file e log chiusi (401)", set(blocked.values()) == {401}, blocked)
check("... anche i comandi: /api/gcode e /api/update/channel", cb.post("/api/gcode", json={"script": "M112"}).status_code == 401 and cb.post("/api/update/channel", json={"channel": "dev"}).status_code == 401)
check("... restano aperti: stato dell'accesso e aggiornamento dell'app", cb.get("/api/auth/status").status_code == 200 and cb.get("/api/app/version").status_code == 200)
check("... lo stato dice: attiva, non sei dentro", cb.get("/api/auth/status").get_json()["enabled"] is True and cb.get("/api/auth/status").get_json()["logged_in"] is False)

r = cb.post("/api/auth/login", json={"password": "sbagliata"})
check("password sbagliata: 401 'password'", r.status_code == 401 and r.get_json()["error"] == "password")
r = cb.post("/api/auth/login", json={"password": "segreta123"})
check("password giusta: entra", r.status_code == 200 and cb.get("/api/version").status_code == 200)
cc = ba.app.test_client()
r = cc.post("/login", data={"password": "segreta123"})
check("anche dal modulo della pagina di accesso: 303 alla dashboard con il cookie", r.status_code == 303 and r.headers["Location"].endswith("/") and "klippeye_session=" in r.headers.get("Set-Cookie", ""))
r = cc.post("/login", data={"password": "no"})
check("... sbagliata: la pagina lo dice (in inglese di serie)", r.status_code == 401 and "Wrong password" in r.get_data(as_text=True))
r = cc.post("/login", data={"password": "no"}, headers={"Accept-Language": "it-IT,it;q=0.9,en;q=0.8"})
check("... e in italiano per un browser italiano", "Password sbagliata" in r.get_data(as_text=True) and 'lang="it"' in r.get_data(as_text=True))
check("pagina di accesso in italiano per un browser italiano", "Accedi" in ba.app.test_client().get("/login", headers={"Accept-Language": "it"}).get_data(as_text=True) and "Log in" in ba.app.test_client().get("/login").get_data(as_text=True))

cd = ba.app.test_client()
codes = [cd.post("/api/auth/login", json={"password": "x%d" % i}, environ_base={"REMOTE_ADDR": "10.9.9.9"}).status_code for i in range(7)]
check("tentativi a raffica: dopo 5 errori bisogna aspettare (429)", codes[:5] == [401] * 5 and 429 in codes[5:], codes)
r = cd.post("/api/auth/login", json={"password": "segreta123"}, environ_base={"REMOTE_ADDR": "10.9.9.9"})
check("... anche con la password giusta, finche' non e' passata l'attesa", r.status_code == 429, r.status_code)
r = cd.post("/api/auth/login", json={"password": "segreta123"}, environ_base={"REMOTE_ADDR": "10.9.9.8"})
check("... gli altri indirizzi non sono bloccati", r.status_code == 200)

check("i servizi del Raspberry (notifiche) passano col gettone interno", ba.app.test_client().get("/api/print/last_analysis", headers={"X-KlippEye-Token": internal}).status_code == 200)
check("... un gettone interno sbagliato no", ba.app.test_client().get("/api/version", headers={"X-KlippEye-Token": "a" * 64}).status_code == 401)
check("un cookie falsificato non vale", ba.app.test_client().get("/api/version", headers={"Cookie": "klippeye_session=eyJ2IjoxLCJleHAiOjk5OTk5OTk5OTksImdlbiI6OTl9.firmafalsa"}).status_code == 401)
_s = ba.ACCESS.load()
check("un gettone scaduto non vale", not ba.access.token_valid(_s, ba.access.make_token(_s, now=time.time() - 200 * 86400)) and ba.access.token_valid(_s, ba.access.make_token(_s)))

r = ca.post("/api/auth/password", json={"current": "sbagliata", "new": "nuova4567"})
check("cambiare la password vuole quella attuale", r.status_code == 401)
r = ca.post("/api/auth/password", json={"current": "segreta123", "new": "nuova4567"})
check("... con quella giusta cambia; chi la cambia resta dentro", r.status_code == 200 and ca.get("/api/version").status_code == 200)
check("... gli altri dispositivi devono rifare l'accesso", cb.get("/api/version").status_code == 401 and cc.get("/api/version").status_code == 401)
cb.post("/api/auth/login", json={"password": "nuova4567"})
r = ca.post("/api/auth/logout_all")
check("'fai uscire tutti gli altri': gli altri fuori, questo dentro", r.status_code == 200 and cb.get("/api/version").status_code == 401 and ca.get("/api/version").status_code == 200)
r = ca.post("/api/auth/logout")
check("'esci da questo dispositivo'", r.status_code == 200 and ca.get("/api/version").status_code == 401)
ca.post("/api/auth/login", json={"password": "nuova4567"})
r = ca.post("/api/auth/disable", json={"current": "no"})
check("togliere la password vuole quella attuale", r.status_code == 401)
r = ca.post("/api/auth/disable", json={"current": "nuova4567"})
check("... con quella giusta si toglie e tutti rientrano senza accesso", r.status_code == 200 and ba.app.test_client().get("/api/version").status_code == 200)

# comando da terminale (klippeye password ...): stesso file, il backend se ne accorge senza riavvio
_acc = os.path.join(ROOT, "backend", "access.py")
_env = dict(os.environ, KLIPPEYE_DATA=da)
out = _sp.run([sys.executable, _acc, "set", "dalterminale9"], env=_env, capture_output=True, text=True)
time.sleep(0.05)
check("da terminale 'set': il backend chiede subito l'accesso", out.returncode == 0 and ba.app.test_client().get("/api/version").status_code == 401, out.stdout + out.stderr)
check("... e la password vale", ba.app.test_client().post("/api/auth/login", json={"password": "dalterminale9"}).status_code == 200)
out = _sp.run([sys.executable, _acc, "remove"], env=_env, capture_output=True, text=True)
check("da terminale 'remove' (password dimenticata): si rientra senza", out.returncode == 0 and ba.app.test_client().get("/api/version").status_code == 200, out.stdout)
out = _sp.run([sys.executable, _acc, "host-add", "stampante.casa.it"], env=_env, capture_output=True, text=True)
check("da terminale 'host-add': quel nome viene accettato", ba.app.test_client().get("/api/version", headers={"Host": "stampante.casa.it:8085"}).status_code == 200, out.stdout)
_sp.run([sys.executable, _acc, "network-checks", "off"], env=_env, capture_output=True, text=True)
check("'network-checks off' torna al comportamento di prima (qualunque nome e origine)",
      ba.app.test_client().get("/api/version", headers={"Host": "x.example.com"}).status_code == 200 and ba.app.test_client().post("/api/backend/config", json={"values": {}}, headers={"Origin": "http://altro.example"}).status_code == 200)
_sp.run([sys.executable, _acc, "network-checks", "on"], env=_env, capture_output=True, text=True)
out = _sp.run([sys.executable, _acc, "status"], env=_env, capture_output=True, text=True)
check("'status' racconta password, controlli e nomi aggiunti", "off (anyone" in out.stdout and "Network checks (host name and origin of requests): on" in out.stdout and "stampante.casa.it" in out.stdout, out.stdout)
open(os.path.join(da, "access.json"), "w").write("{rotto")
time.sleep(0.05)
check("access.json rovinato (blackout): si riparte senza password invece di chiudere fuori", ba.app.test_client().get("/api/version").status_code == 200 and json.load(open(os.path.join(da, "access.json")))["enabled"] is False)

# ---------------------------------------------------------------------------------------------------------------------
print("== 1.9.0: pagina compressa, rapporto di diagnostica")
import gzip as _gz
dg = tmp()
bg = load_brain(NEW_BRAIN, dg, fake, brain_json={"values": {"enabled": False}})
cg = bg.app.test_client()
page = open(bg.find_frontend(), "rb").read()
r = cg.get("/", headers={"Accept-Encoding": "gzip, deflate"})
check("la dashboard arriva compressa (gzip) a chi la accetta, e decompressa e' identica",
      r.status_code == 200 and r.headers.get("Content-Encoding") == "gzip" and _gz.decompress(r.data) == page and len(r.data) < len(page) / 2, (r.status_code, r.headers.get("Content-Encoding"), len(r.data), len(page)))
check("... con Vary e un ETag", r.headers.get("Vary") == "Accept-Encoding" and r.headers.get("ETag"))
etag = r.headers.get("ETag")
r2 = cg.get("/")
check("senza Accept-Encoding: la pagina normale, stesso ETag", r2.status_code == 200 and r2.headers.get("Content-Encoding") is None and r2.data == page and r2.headers.get("ETag") == etag)
r3 = cg.get("/", headers={"If-None-Match": etag, "Accept-Encoding": "gzip"})
check("pagina non cambiata: 304 senza contenuto", r3.status_code == 304 and r3.data == b"")
open(os.path.join(dg, "ai.json"), "w").write(json.dumps({"api_key": "gsk_SEGRETISSIMA1234567890", "provider": "groq"}))
open(os.path.join(dg, "internal.token"), "w").write("tokeninterno-segreto-xyz")
r = cg.get("/api/diagnose")
report = r.get_data(as_text=True)
check("/api/diagnose: un file di testo da scaricare con release, sistema, Moonraker e cartella dati",
      r.status_code == 200 and r.mimetype == "text/plain" and "attachment" in r.headers.get("Content-Disposition", "") and "== KlippEye" in report and "== System" in report and "== Moonraker" in report and "ai.json" in report, report[:600])
check("... senza segreti: ne' la chiave dell'IA ne' il token interno", "SEGRETISSIMA" not in report and "tokeninterno" not in report)
import importlib.util as _iu
_spec = _iu.spec_from_file_location("diagnose", os.path.join(ROOT, "scripts", "diagnose.py")); _dm = _iu.module_from_spec(_spec); _spec.loader.exec_module(_dm)
check("diagnose.redact nasconde chiavi, password, token, cookie e credenziali negli indirizzi",
      all("SECRET" not in _dm.redact(t) for t in ("gsk_SECRETSECRETSECRET", '"api_key": "sk-SECRETSECRET1"', "password=SECRETpw", "Bearer SECRETSECRETxx", "klippeye_session=SECRET", "https://u:SECRET@github.com", "-----BEGIN PRIVATE KEY-----\nSECRET\n-----END PRIVATE KEY-----")))

# ---------------------------------------------------------------------------------------------------------------------
print("== 1.10.0: canale degli aggiornamenti")
CONF = "[server]\nhost: 0.0.0.0\n\n# KlippEye: updates\n[update_manager klippeye]\ntype: git_repo\npath: ~/klippeye\nchannel: dev\nmanaged_services: klippeye\n\n[update_manager mainsail]\ntype: web\nchannel: stable\n"
check("update_channel_of: legge il canale della sola voce klippeye", bg.update_channel_of(CONF) == "dev" and bg.update_channel_of(CONF.replace("channel: dev\n", "")) == "dev" and bg.update_channel_of("[server]\n") is None)
c2 = bg.with_update_channel(CONF, "stable")
check("with_update_channel: cambia solo la riga della voce klippeye", bg.update_channel_of(c2) == "stable" and c2.count("channel: stable") == 2 and "[update_manager mainsail]\ntype: web\nchannel: stable" in c2, c2)
c3 = bg.with_update_channel(CONF.replace("channel: dev\n", ""), "stable")
check("... e la aggiunge dopo 'type:' se manca", "type: git_repo\nchannel: stable\npath:" in c3, c3)
__import__("requests").post = real_post
bg.requests.post = real_post
fake.state["moonraker_conf"] = CONF
fake.state["print_state"] = "standby"
j = cg.get("/api/update/channel").get_json()
check("GET /api/update/channel: dev, elencato", j["ok"] and j["channel"] == "dev" and j["listed"] is True, j)
del fake.posts[:]
r = cg.post("/api/update/channel", json={"channel": "stable"})
check("POST stable: moonraker.conf riscritto tramite Moonraker e Moonraker riavviato", r.status_code == 200 and r.get_json()["changed"] is True and bg.update_channel_of(fake.state["moonraker_conf"]) == "stable"
      and "/server/files/upload" in fake.posts and "/server/restart" in fake.posts and "[server]\nhost: 0.0.0.0" in fake.state["moonraker_conf"], (r.get_json(), fake.posts, fake.state["moonraker_conf"]))
check("... con una copia del file di prima nella cartella dati", any(n.startswith("moonraker.conf-") for n in os.listdir(os.path.join(dg, "backup"))))
del fake.posts[:]
r = cg.post("/api/update/channel", json={"channel": "stable"})
check("stesso canale: niente da cambiare, Moonraker non si riavvia", r.status_code == 200 and r.get_json()["changed"] is False and "/server/restart" not in fake.posts)
check("canale sconosciuto: 400", cg.post("/api/update/channel", json={"channel": "beta"}).status_code == 400)
fake.state["print_state"] = "printing"
r = cg.post("/api/update/channel", json={"channel": "dev"})
check("durante una stampa: 409 e niente cambia", r.status_code == 409 and bg.update_channel_of(fake.state["moonraker_conf"]) == "stable", r.get_json())
fake.state["print_state"] = "standby"
fake.state["moonraker_conf"] = "[server]\n"
check("senza voce klippeye in moonraker.conf: GET dice non elencato, POST 409", cg.get("/api/update/channel").get_json()["listed"] is False and cg.post("/api/update/channel", json={"channel": "dev"}).status_code == 409)
fake.state["moonraker_conf"] = None

print("== 1.12.0: recorder, labels, replay (phase 3: measuring the monitor)")
import subprocess as _sub2  # noqa: E402
import re  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "backend"))
import recorder as _rec  # noqa: E402
import monitor_core as _core  # noqa: E402

# --- the recorder alone
rroot = os.path.join(tmp(), "recordings")
rr = _rec.Recorder(rroot, _core.cv2, "9.9.9")
rr.observe("printing", "a.gcode", 1000.0)
check("recorder off: nothing is opened", rr.session is None and not os.path.exists(rroot))
rr.configure(True, 500)
rr.observe("printing", "../../etc/a b.gcode", 1000.0, {"sensitivity": 35})
sid1 = rr.session["id"]
check("printing: a recording opens, its id is safe (time + cleaned file name)", re.fullmatch(r"\d{8}-\d{6}-a_b", sid1) is not None and os.path.isfile(os.path.join(rroot, sid1, "session.json")), sid1)
img = fakes.frame(EDGE)
for i in range(5):
    rr.add_frame(img, 1000.0 + i * 3, {"layer": i, "score": 0.5, "trig": False})
p1 = rr.frame_path(sid1, 1)
check("pictures: 540x360 JPEG, one line each in frames.jsonl", p1 and _core.cv2.imread(p1).shape[:2] == (360, 540) and len(rr.frames(sid1)) == 5 and rr.frames(sid1)[4]["layer"] == 4, rr.frames(sid1)[:1])
rr.note_trigger(1010.0)
ev = {"id": "20990101-000000", "outcome": "analysed", "action": "PAUSE", "summary": "x"}
rr.attach_alert(ev)
check("an AI verdict right after a live alarm is linked to the recording", ev.get("session") == sid1 and ev.get("frame") == 5 and len(rr.session["alerts"]) == 1, ev)
rr.observe("paused", "../../etc/a b.gcode", 1020.0)
check("paused: the same recording goes on", rr.session and rr.session["id"] == sid1)
rr.observe("complete", "", 1030.0)
s1 = rr.load(sid1)
check("print ended: closed with its end state and time", rr.session is None and s1["end_state"] == "complete" and s1["ended"] == 1030.0 and s1["frames"] == 5 and len(s1["live_triggers"]) == 1, s1)
try:
    rr.set_label(sid1, "failed", 5.0)
    bad = False
except ValueError:
    bad = True
check("label: a failure time outside the recording is refused", bad)
check("label: failed from a moment of the recording", rr.set_label(sid1, "failed", 1006.0)["failed_at"] == 1006.0 and rr.load(sid1)["label"]["outcome"] == "failed")
try:
    rr.set_label(sid1, "maybe")
    bad = False
except ValueError:
    bad = True
check("label: an unknown outcome is refused", bad)
for evil in ("../x", "20990101-000000/../../", "x", ""):
    check("a bad id is refused (%r)" % evil, rr.load(evil) is None and rr.frame_path(evil, 1) is None and rr.delete(evil) is False)
rr.observe("printing", "b.gcode", 2000.0)
sid2 = rr.session["id"]
for i in range(40):
    rr.add_frame(fakes.frame((i * 20, 100, 60, 60)), 2000.0 + i * 3, {"score": None, "trig": False})
used = rr.summary()["used_bytes"]
rr.max_bytes = used - 1000   # less than what is there: the oldest goes
rr.observe("complete", "", 2200.0)
check("over the space limit: the oldest recording is deleted, the newest stays", not os.path.exists(os.path.join(rroot, sid1)) and os.path.exists(os.path.join(rroot, sid2)), os.listdir(rroot))
rr.max_bytes = 10
rr.observe("printing", "c.gcode", 3000.0)
for i in range(_rec.SAVE_EVERY):
    rr.add_frame(img, 3000.0 + i, {})
check("a print that alone fills the space: it stops growing (truncated), the others are deleted", rr.session["truncated"] is True and rr.add_frame(img, 3100.0, {}) is None and "stopped" in rr.status, rr.status)
rr.observe("complete", "", 3200.0)
real_usage = _rec.shutil.disk_usage
_rec.shutil.disk_usage = lambda path: type("U", (), {"free": 10 * 1024 ** 2, "total": 1, "used": 1})()
rr.max_bytes = 10 ** 9
rr.observe("printing", "d.gcode", 4000.0)
check("less than 1 GB free: nothing is written, the status says so", rr.add_frame(img, 4000.0, {}) is None and "1 GB" in rr.status, rr.status)
_rec.shutil.disk_usage = real_usage
rr.observe("complete", "", 4010.0)
last_id = rr.ids()[-1]
check("delete: the folder goes", rr.delete(last_id) and not os.path.exists(os.path.join(rroot, last_id)))
rr.configure(False, 500)
check("switched off: status off", rr.status == "off")

# --- the backend: live recording during a (fake) print
fake.snapshots = 0
fake.state.update({"print_state": "printing", "progress": 0.5, "file_position": 5000, "file_size": 10000, "total_duration": 500.0,
                   "hotend": 210.0, "hotend_target": 210.0, "layer": 7, "filename": "benchy.gcode", "frames": blink(EDGE, 60)})
drec = tmp()
mr = load_brain(NEW_BRAIN, drec, fake, brain_json={"values": {"enabled": False, "persistent_filter": False, "record": True, "check_interval": 1, "cooldown": 10}})
mr.detector.last_ai_call = time.time() + 99999
mr.detector.enabled = True
mr.detector.start()
ok_trigger = wait_for(lambda: mr.recorder.session is not None and len(mr.recorder.session["live_triggers"]) >= 1, 25)
check("live: recording on + print running -> a recording with the pictures and the live alarm", ok_trigger, mr.recorder.status)
time.sleep(4)   # a few pictures during the monitor's pause after the alarm
sid = mr.recorder.session["id"] if mr.recorder.session else None
fake.state["print_state"] = "complete"
wait_for(lambda: mr.recorder.session is None, 12)
mr.detector.stop()
cr = mr.app.test_client()
j = cr.get("/api/recordings").get_json()
check("/api/recordings: the print, ended 'complete', with pictures and its alarm", j["ok"] and j["enabled"] is True and len(j["sessions"]) == 1 and j["sessions"][0]["id"] == sid
      and j["sessions"][0]["end_state"] == "complete" and j["sessions"][0]["frames"] >= 5 and j["sessions"][0]["live_triggers"] >= 1 and j["used_bytes"] > 0, j)
check("... and it is not cached", cr.get("/api/recordings").headers.get("Cache-Control") == "no-store")
d = cr.get("/api/recordings/" + sid).get_json()
fr = d["frames"]
check("/api/recordings/<id>: session (file, settings in use) and pictures with layer and progress", d["session"]["file"] == "benchy.gcode" and d["session"]["config"].get("check_interval") == 1
      and fr[0]["layer"] == 7 and fr[0]["layers"] == 40 and fr[0]["progress"] == 50.0 and any(f["trig"] for f in fr), (d["session"].get("file"), fr[:2]))
check("... pictures taken during the pause after the alarm are marked", any(f.get("cool") for f in fr), [f.get("cool") for f in fr])
full = mr.recorder.frames(sid)
check("... the toolhead position is kept with each picture (commanded and live)", full[0].get("pos") in ([120.5, 80.2, 5.0], [120.5, 80.3, 5.0]) and full[0].get("live") == [121.0, 80.5, 5.0], full[0])
r = cr.get("/api/recordings/%s/frames/1.jpg" % sid)
check("a picture: 200 JPEG", r.status_code == 200 and r.mimetype == "image/jpeg" and r.data[:2] == b"\xff\xd8")
check("a picture that is not there, or a bad id: 404", cr.get("/api/recordings/%s/frames/99999.jpg" % sid).status_code == 404 and cr.get("/api/recordings/..%2Fx/frames/1.jpg").status_code == 404)
check("label: 400 for an unknown outcome, 404 for an unknown recording", cr.post("/api/recordings/%s/label" % sid, json={"outcome": "maybe"}).status_code == 400
      and cr.post("/api/recordings/20990101-000000/label", json={"outcome": "ok"}).status_code == 404)
r = cr.post("/api/recordings/%s/label" % sid, json={"outcome": "ok"})
check("label 'ok' saved in session.json", r.status_code == 200 and mr.recorder.load(sid)["label"]["outcome"] == "ok", r.get_json())
# an AI verdict linked to the recording, then marked by the person
mr.recorder.last_trigger = (sid, time.time(), 3, time.time())
mr.record_alert({"outcome": "analysed", "action": "PAUSE", "summary": "strings"})
hist = mr.read_alert_history(5)
aid = hist[0]["id"]
check("the alert history entry knows its recording and picture", hist[0].get("session") == sid and hist[0].get("frame") == 3, hist[0])
r = cr.post("/api/print/alerts/%s/label" % aid, json={"label": "false"})
check("alert label 'false': in the history and in the recording", r.status_code == 200 and mr.read_alert_history(5)[0]["label"] == "false"
      and mr.recorder.load(sid)["alerts"][-1]["label"] == "false", (r.get_json(), mr.recorder.load(sid)["alerts"]))
check("alert label: 400 for a bad label, 404 for an unknown alarm", cr.post("/api/print/alerts/%s/label" % aid, json={"label": "maybe"}).status_code == 400
      and cr.post("/api/print/alerts/20990101-000000/label", json={"label": "false"}).status_code == 404)
r = cr.post("/api/print/alerts/%s/label" % aid, json={"label": None})
check("alert label null: the label goes away", r.status_code == 200 and "label" not in mr.read_alert_history(5)[0])

# --- the replay (scripts/replay.py) on that recording
REPLAY = os.path.join(ROOT, "scripts", "replay.py")
out_json = os.path.join(tmp(), "m.json")
rp = _sub2.run([sys.executable, REPLAY, "--data", drec, "--json", out_json], capture_output=True, text=True, timeout=120)
res = json.load(open(out_json))
check("replay: a table with the print, its alarms and the label", rp.returncode == 0 and "TOTAL" in rp.stdout and "benchy" in rp.stdout and "went fine" in rp.stdout, rp.stdout + rp.stderr)
row = res["sessions"][0]
check("replay: with the thresholds of the recording it raises alarms like the live monitor did; all false (the print went fine)", row["alarms"] >= 1 and row["false"] == row["alarms"]
      and res["total"]["false_per_hour"] is not None and row["ms_per_check"] is not None, row)
rp2 = _sub2.run([sys.executable, REPLAY, "--data", drec, "--json", out_json, "--set", "score_threshold=30", "--set", "persist_checks=4"], capture_output=True, text=True, timeout=120)
res2 = json.load(open(out_json))
check("replay --set: other thresholds, other count (30% of the band must move: no alarm)", rp2.returncode == 0 and res2["sessions"][0]["alarms"] == 0 < row["alarms"] and res2["overrides"] == {"score_threshold": 30, "persist_checks": 4}, (res2["sessions"][0]["alarms"], row["alarms"]))
mr.recorder.set_label(sid, "failed", fr[0]["t"])
rp3 = _sub2.run([sys.executable, REPLAY, "--data", drec, "--json", out_json], capture_output=True, text=True, timeout=120)
res3 = json.load(open(out_json))
check("replay: a print failed from the start, its first alarm caught it (with the delay)", res3["sessions"][0]["seen"] is True and res3["sessions"][0]["false"] == 0
      and res3["total"]["failures"] == 1 and res3["total"]["seen"] == 1 and res3["sessions"][0]["delay_s"] >= 0, res3["sessions"][0])
mr.recorder.set_label(sid, None)
_sub2.run([sys.executable, REPLAY, "--data", drec, "--json", out_json], capture_output=True, timeout=120)
row4 = json.load(open(out_json))["sessions"][0]
check("replay: not marked: false alarms unknown", row4["false"] is None and row4["outcome"] is None, row4)
empty = tmp()
rp4 = _sub2.run([sys.executable, REPLAY, "--data", empty], capture_output=True, text=True, timeout=60)
check("replay without recordings: says how to start, exit 0", rp4.returncode == 0 and "No recordings" in rp4.stdout, rp4.stdout + rp4.stderr)

# --- measuring from the dashboard
r = cr.post("/api/recordings/measure")
check("POST /api/recordings/measure starts the replay", r.status_code == 200 and r.get_json()["state"] == "running", r.get_json())
wait_for(lambda: cr.get("/api/recordings/measure").get_json()["state"] != "running", 90)
j = cr.get("/api/recordings/measure").get_json()
check("GET: done, with the result (one print, the thresholds in use now)", j["state"] == "done" and j["result"]["settings"] == "current" and j["result"]["total"]["recordings"] == 1, j)
r = cr.delete("/api/recordings/" + sid)
check("DELETE: the recording goes, then 404", r.status_code == 200 and cr.get("/api/recordings/" + sid).status_code == 404 and cr.delete("/api/recordings/" + sid).status_code == 404)
check("CPU of the monitor: time of a check in the status", isinstance(mr.detector.stats.get("check_ms"), float), mr.detector.stats)
check("the recording settings are in the menu's list (group 'recording')", [s["key"] for s in cr.get("/api/backend/config").get_json()["spec"] if s["group"] == "recording"] == ["record", "record_max_mb"])
check("turning recording off from the menu reaches the recorder", cr.post("/api/backend/config", json={"values": {"record": False}}).status_code == 200 and mr.recorder.enabled is False and mr.recorder.status == "off")
fake.state["filename"] = "test.gcode"

print("== 1.13.0: camera calibration (phase 4a)")
import camera_model as _cm  # noqa: E402
_rng = _core.np.random.default_rng(7)
CAM_W, CAM_H = 1280, 720
_texture = _core.cv2.GaussianBlur((_rng.random((CAM_H + 80, CAM_W + 80)) * 255).astype(_core.np.uint8), (5, 5), 0)


def _look_at(cam, target):
    np_ = _core.np
    fwd = np_.asarray(target, float) - cam
    fwd /= np_.linalg.norm(fwd)
    right = np_.cross(fwd, [0, 0, 1.0])
    right /= np_.linalg.norm(right)
    rot = np_.stack([right, np_.cross(fwd, right), fwd])
    return rot, -rot @ cam


_rot, _t = _look_at(_core.np.array([175.0, -60.0, 120.0]), [175.0, 200.0, -40.0])   # front-centre camera, looking down at the bed
TRUE_CAM = {"model": "fisheye", "width": CAM_W, "height": CAM_H, "params": [CAM_W / 3.2, CAM_W / 2 + 15, CAM_H / 2 - 10, 0.03, -0.01] + list(_cm.rotation_to_vector(_rot)) + list(_t)}


def render_camera(state):
    """A picture of the fake camera: a fixed texture (what the movement check looks at), moved by state["cam_shift"] pixels."""
    dx, dy = state.get("cam_shift", (0, 0))
    img = _texture[40 + dy:40 + dy + CAM_H, 40 + dx:40 + dx + CAM_W]
    return fakes.jpeg(_core.cv2.cvtColor(img, _core.cv2.COLOR_GRAY2BGR))


def true_tap(frame, noise=1.5):
    uv, _ = _cm.project(TRUE_CAM, [frame])
    return [float(uv[0][0] + _rng.normal(0, noise) / CAM_W), float(uv[0][1] + _rng.normal(0, noise) / CAM_H)]


fake.state.update({"render": render_camera, "print_state": "standby", "homed": "", "position": [175.0, 175.0, 10.0]})
dcal = tmp()
mc = load_brain(NEW_BRAIN, dcal, fake, brain_json={"values": {"enabled": False}})
cc = mc.app.test_client()
j = cc.get("/api/camera/calibration").get_json()
check("GET: not calibrated, the printer read, the kind guessed from Klipper's settings (corexy + z_tilt: Z moves the bed)", j["ok"] and j["saved"] is None and j["printer"]["homed"] == ""
      and j["guess"] == "bed" and j["targets"] == [], j)
r = cc.post("/api/camera/calibration/options", json={"z_moves": "sideways"})
check("options: an unknown kind is refused (400)", r.status_code == 400)
r = cc.post("/api/camera/calibration/options", json={"z_moves": "bed", "toolhead": {"width": 60, "depth": 70, "height": 70}})
j = cc.get("/api/camera/calibration").get_json()
check("Z moves the bed: no points before the markers are on the bed", r.status_code == 200 and j["targets"] == [], j["targets"])
import camera_markers as _mk  # noqa: E402
r = cc.get("/api/camera/markers.stl")
_stl = r.data
check("the markers STL: 6 pyramids (36 triangles) sized for this bed, as a download", r.status_code == 200 and "klippeye-camera-markers.stl" in r.headers.get("Content-Disposition", "")
      and len(_stl) == 84 + 36 * 50 and _core.np.frombuffer(_stl[80:84], "<u4")[0] == 36, (r.status_code, len(_stl)))



def sliced_markers(dx, dy, count=6):
    return fakes.sliced_markers(fake.state["axis_min"], fake.state["axis_max"], dx, dy, count=count)


fake.state["gcodes"] = {"benchy.gcode": "G90\nM83\nG1 Z0.2\nG1 X10 Y10 E5\nG1 X100 Y10 E5\n", "klippeye-camera-markers_PLA_12m.gcode": sliced_markers(4.0, -3.0), "notes.txt": "x"}
r = cc.get("/api/camera/gcode-files")
check("the G-code files on the printer (newest first, only G-code)", r.status_code == 200 and [f["path"] for f in r.get_json()["files"]] == ["klippeye-camera-markers_PLA_12m.gcode", "benchy.gcode"], r.get_json())
r = cc.post("/api/camera/calibration/markers", json={"file": "missing.gcode"})
check("markers from a file that is not there: 400", r.status_code == 400, r.get_json())
r = cc.post("/api/camera/calibration/markers", json={"file": "benchy.gcode"})
check("markers from a file without them: 400 'print the KlippEye markers file'", r.status_code == 400 and "markers file" in r.get_json()["error"], r.get_json())
fake.state["gcodes"]["five.gcode"] = sliced_markers(0, 0, count=5)
r = cc.post("/api/camera/calibration/markers", json={"file": "five.gcode"})
check("a file with 5 markers: 400 '5 markers found instead of 6'", r.status_code == 400 and "5 markers" in r.get_json()["error"], r.get_json())
r = cc.post("/api/camera/calibration/markers", json={"file": "klippeye-camera-markers_PLA_12m.gcode"})
mk = r.get_json().get("markers") or {}
_expect = [(x + 4.0, y - 3.0) for x, y in _mk.marker_positions(fake.state["axis_min"], fake.state["axis_max"])]
check("markers read from the printed G-code: 6, where the slicer put them (moved 4, -3), tips at 10 mm", r.status_code == 200 and mk.get("source") == "file" and len(mk["points"]) == 6
      and all(abs(p[0] - e[0]) < 0.3 and abs(p[1] - e[1]) < 0.3 and abs(p[2] - 10.0) < 0.01 for p, e in zip(mk["points"], _expect)), mk)
j = cc.get("/api/camera/calibration").get_json()
tg = j["targets"]
check("now 6 nozzle points just above the tips, then the 6 markers with the bed lowered", [t["kind"] for t in tg] == ["nozzle"] * 6 + ["mark"] * 6
      and all(t["z"] == 13.0 for t in tg[:6]) and all(t["z"] >= 20 and t["height"] == 10.0 for t in tg[6:]) and (tg[0]["x"], tg[0]["y"]) == (round(_expect[0][0], 2), round(_expect[0][1], 2)), tg)
r = cc.post("/api/camera/calibration/marks", json={"nozzle": 400, "bed": 60})
check("blobs: a wrong temperature is refused (400)", r.status_code == 400 and "170" in r.get_json()["error"], r.get_json())
del fake.scripts[:]
fake.state["homed"] = "xyz"   # the blobs need a homed printer (homing itself is checked below)
r = cc.post("/api/camera/calibration/marks", json={"nozzle": 215, "bed": 65})
wait_for(lambda: mc.camera_cal.marks["state"] != "running", 10)
blob_script = [x for x in fake.scripts if "M109" in x]
_bs = blob_script[0] if blob_script else ""
check("the blobs: the chosen temperatures, a disc at each of the 6 points, retraction and Z hop between them, then cools down",
      r.status_code == 200 and mc.camera_cal.marks["state"] == "done" and "M109 S215" in _bs and "M190 S65" in _bs and _bs.count("G1 E-1 F2400") == 7
      and _bs.count("G0 Z5 F1200") == 6 and _bs.rstrip().endswith("M400") and "M104 S0" in _bs, (mc.camera_cal.marks, _bs[:300]))
check("... the blobs are the markers now (0.6 mm tall)", mc.camera_cal.draft["markers"]["source"] == "blobs" and [p[2] for p in mc.camera_cal.draft["markers"]["points"]] == [0.6] * 6)
r = cc.post("/api/camera/calibration/markers", json={"file": "klippeye-camera-markers_PLA_12m.gcode"})
tg = cc.get("/api/camera/calibration").get_json()["targets"]
check("... and the printed ones again (back to the file)", r.status_code == 200 and mc.camera_cal.draft["markers"]["source"] == "file" and tg[6]["height"] == 10.0)
fake.state["homed"] = ""
r = cc.post("/api/camera/calibration/goto", json={"target": "tip1"})
check("not homed: no move (409, 'home the printer first')", r.status_code == 409 and "home" in r.get_json()["error"], r.get_json())
fake.state["print_state"] = "printing"
r = cc.post("/api/camera/calibration/home")
check("while printing: not even homing (409)", r.status_code == 409)
fake.state["print_state"] = "standby"
del fake.scripts[:]
r = cc.post("/api/camera/calibration/home")
check("home: G28 sent", r.status_code == 200 and fake.scripts == ["G28"] and fake.state["homed"] == "xyz", fake.scripts)
r = cc.post("/api/camera/calibration/goto", json={"target": "nope"})
check("an unknown point: 400", r.status_code == 400)
del fake.scripts[:]
r = cc.post("/api/camera/calibration/goto", json={"target": "tip1"})
check("goto: up first (above the tallest marker), then across, then down to the point (never dragged over the markers)", r.status_code == 200
      and fake.state["position"] == [tg[0]["x"], tg[0]["y"], 13.0] and fake.scripts[0].splitlines()[1] == "G0 Z15.00 F900"
      and fake.scripts[0].splitlines()[2].startswith("G0 X%.2f Y%.2f" % (tg[0]["x"], tg[0]["y"])), (fake.scripts, fake.state["position"]))
check("tap: u, v must be fractions", cc.post("/api/camera/calibration/point", json={"target": "tip1", "u": 1.5, "v": 0.2}).status_code == 400)
for t in tg:
    cc.post("/api/camera/calibration/goto", json={"target": t["id"]})
    pos = fake.state["position"]
    frame = [pos[0], pos[1], 0.0] if t["kind"] == "nozzle" else [t["x"], t["y"], 10.0 - pos[2]]
    u, v = true_tap(frame)
    r = cc.post("/api/camera/calibration/point", json={"target": t["id"], "u": u, "v": v})
check("markers: the nozzle is parked at the back and the bed lowered when the markers are tapped", tg[-1]["kind"] == "mark" and fake.state["position"][1] == 345.0 and fake.state["position"][2] == tg[-1]["z"], fake.state["position"])
pts = mc.camera_cal.draft["points"]
check("12 points kept (in the draft, also after a reload): nozzle at height 0, marker tips at 10 - Z", len(pts) == 12 and pts["tip1"]["frame"][2] == 0.0 and pts["mark1"]["frame"][2] == round(10.0 - tg[6]["z"], 6) and os.path.isfile(os.path.join(dcal, "camera_draft.json")), list(pts.items())[:2])
check("save before calculating: refused", cc.post("/api/camera/calibration/save").status_code == 400)
r = cc.post("/api/camera/calibration/fit")
fit = r.get_json().get("fit") or {}
check("fit: a good calibration (a few pixels), nothing to redo, the camera found where it is", r.status_code == 200 and fit["quality"] == "good" and fit["rms_px"] < 4 and fit["redo"] == []
      and abs(fit["camera_position"][1] + 60) < 15 and abs(fit["camera_position"][2] - 120) < 15, {k: fit.get(k) for k in ("quality", "rms_px", "redo", "camera_position", "model")})
r = cc.post("/api/camera/calibration/save")
j = cc.get("/api/camera/calibration").get_json()
check("save: camera.json and the reference picture; usable; the draft is gone", r.status_code == 200 and j["saved"]["quality"] == "good" and j["saved"]["points"] == 12 and j["usable"] is True
      and os.path.isfile(os.path.join(dcal, "camera.json")) and os.path.isfile(os.path.join(dcal, "camera_reference.jpg")) and not j["draft"], j["saved"])
fake.state["position"] = [100.0, 200.0, 25.0]
ov = cc.get("/api/camera/overlay").get_json()
truth, _ = _cm.project(TRUE_CAM, [[100.0, 200.0, 0.0]])
check("overlay: the nozzle drawn where it really is (within 1% of the picture)", ov["ok"] and abs(ov["nozzle"][0] - truth[0][0]) < 0.01 and abs(ov["nozzle"][1] - truth[0][1]) < 0.01, (ov.get("nozzle"), truth[0]))
check("... with the toolhead outline around it and the bed outline (bed lowered by Z = 25)", len(ov["toolhead"]) >= 4 and len(ov["bed"]) >= 30 and ov["z_moves"] == "bed")
w = cc.post("/api/camera/check").get_json()
check("camera check: unchanged picture -> ok", w["watch"]["state"] == "ok", w)
fake.state["cam_shift"] = (24, 10)
w = cc.post("/api/camera/check").get_json()
j = cc.get("/api/camera/calibration").get_json()
check("camera moved: 'moved', the calibration is no longer used (usable false)", w["watch"]["state"] == "moved" and j["usable"] is False, (w, j["usable"]))
fake.state["render"] = lambda st: fakes.jpeg(fakes.frame(base=0))
w = cc.post("/api/camera/check").get_json()
check("a black picture says nothing: it stays 'moved' (an unclear look does not clear it)", w["watch"]["state"] == "moved", w)
fake.state["render"] = render_camera
fake.state["cam_shift"] = (0, 0)
w = cc.post("/api/camera/check").get_json()
check("camera put back: ok again", w["watch"]["state"] == "ok", w)
mb = load_brain(NEW_BRAIN, dcal, fake, brain_json={"values": {"enabled": False}})
check("after a restart the calibration is read again", mb.camera_cal.usable() is True and mb.camera_cal.saved["z_moves"] == "bed")
fake.state["gcode_fail"] = "Must home axis first"
r = cc.post("/api/camera/calibration/jog", json={"dx": 10})
check("Klipper refuses a command: 409 with Klipper's words", r.status_code == 409 and "Must home axis first" in r.get_json()["error"], r.get_json())
fake.state["gcode_fail"] = None
check("jog: at most 50 mm", cc.post("/api/camera/calibration/jog", json={"dz": 80}).status_code == 400)
cc.set_cookie("klippeye_lang", "it")
_it = cc.post("/api/camera/calibration/goto", json={"target": "x"}).get_json()["error"]
cc.delete_cookie("klippeye_lang")
check("the messages are translated (Italian page)", "punto sconosciuto" in _it.lower(), _it)

# --- a printer where Z moves the toolhead: nozzle at two heights
cc.post("/api/camera/calibration/options", json={"z_moves": "toolhead"})
tg2 = cc.get("/api/camera/calibration").get_json()["targets"]
check("Z moves the toolhead: 12 nozzle points, 6 low (Z 5) and 6 high", [t["kind"] for t in tg2] == ["nozzle"] * 12 and {t["z"] for t in tg2[:6]} == {5.0} and len({t["z"] for t in tg2[6:]}) == 1 and tg2[6]["z"] > 20, tg2)
TRUE_CAM2 = dict(TRUE_CAM, params=list(TRUE_CAM["params"][:5]) + list(_cm.rotation_to_vector(_look_at(_core.np.array([0.0, -50.0, 200.0]), [175.0, 175.0, 0.0])[0])) + list(_look_at(_core.np.array([0.0, -50.0, 200.0]), [175.0, 175.0, 0.0])[1]))
for t in tg2:
    cc.post("/api/camera/calibration/goto", json={"target": t["id"]})
    uv, _ = _cm.project(TRUE_CAM2, [fake.state["position"]])
    cc.post("/api/camera/calibration/point", json={"target": t["id"], "u": float(uv[0][0]), "v": float(uv[0][1])})
fit2 = cc.post("/api/camera/calibration/fit").get_json()["fit"]
check("... the fit is good with exact taps", fit2["quality"] == "good" and fit2["rms_px"] < 1, {k: fit2[k] for k in ("quality", "rms_px", "model")})
cc.post("/api/camera/calibration/forget", json={"target": "high1"})
cc.post("/api/camera/calibration/forget", json={"target": "high2"})
cc.post("/api/camera/calibration/forget", json={"target": "high3"})
cc.post("/api/camera/calibration/forget", json={"target": "high4"})
cc.post("/api/camera/calibration/forget", json={"target": "high5"})
r = cc.post("/api/camera/calibration/fit")
check("7 points: not enough (400 'at least 8 points')", r.status_code == 400 and "8 points" in r.get_json()["error"], r.get_json())
for t in tg2[6:11]:
    cc.post("/api/camera/calibration/goto", json={"target": t["id"]})
    cc.post("/api/camera/calibration/point", json={"target": t["id"], "u": 0.5, "v": 0.5})   # all tapped on the same spot: wrong
_rb = cc.post("/api/camera/calibration/fit")
bad = _rb.get_json().get("fit") or {}
check("wrong taps: no camera fits (400), or the fit says 'poor' / names the points to redo",
      (_rb.status_code == 400 and "no camera fits" in _rb.get_json()["error"]) or bad.get("quality") == "poor" or bad.get("redo"), (_rb.get_json().get("error"), {k: bad.get(k) for k in ("quality", "rms_px", "redo")}))
if bad.get("quality") == "poor":
    check("... save refused", cc.post("/api/camera/calibration/save").status_code == 400)
cc.post("/api/camera/calibration/reset")
check("reset: the draft is gone, the saved calibration stays", not mc.camera_cal.draft and mc.camera_cal.saved is not None)
r = cc.delete("/api/camera/calibration")
check("DELETE: the saved calibration is forgotten", r.status_code == 200 and cc.get("/api/camera/calibration").get_json()["saved"] is None and not os.path.exists(os.path.join(dcal, "camera.json")))
fake.state.update({"render": None, "print_state": "printing", "homed": "xyz"})

stop_all()
fake.close()
print("\n%d PASS, %d FAIL" % (passed, failed))
sys.exit(1 if failed else 0)
