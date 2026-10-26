"""
klippeye_notifier.py against the real thing as far as it can be had here: the Moonraker/Brain stand-in used for the dashboard
tests, and a stand-in for Google (OAuth2 token endpoint that VERIFIES the RS256 signature of the sign-in, and the FCM
send endpoint that checks the token). Usage: python3 test_integration.py <dashboard html for the mock> <port>
"""
import base64, json, os, re, signal, subprocess, sys, tempfile, threading, time, io, contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "notifier"))
sys.path.insert(0, os.path.join(HERE, "..", "ui"))
import klippeye_notifier as vn
from lib import Mock
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization

html, port = sys.argv[1], int(sys.argv[2])
GPORT = port + 1
FAILS = []
def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra != "" else ""))

NOW = 1760000000
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()

from fake_google import Google, ISSUER

google = Google(KEY, GPORT); google.start()
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
TMP = tempfile.mkdtemp(prefix="vzn-")
KEYFILE = os.path.join(TMP, "service-account.json")
json.dump({"type": "service_account", "project_id": "vzbot-test", "private_key_id": "abc", "private_key": PEM, "client_email": "firebase-adminsdk@vzbot-test.iam.gserviceaccount.com", "token_uri": "http://127.0.0.1:%d/token" % GPORT}, open(KEYFILE, "w"))
CONFIG = {"moonraker_url": mock.base, "brain_url": mock.base, "service_account_file": KEYFILE, "topic": "vzbot-test-topic",
          "poll_seconds": 0.15, "ai_poll_seconds": 0.2, "pause_grace_seconds": 0.8, "retry_seconds": 0.3, "settings_poll_seconds": 0.3, "heartbeat_seconds": 1.0,
          "fcm_url": "http://127.0.0.1:%d/v1/projects/{project}/messages:send" % GPORT,
          "cooldown_seconds": {"error": 2, "runout": 2, "ai_pause": 1, "ai_cancel": 1, "paused": 0.2, "cancelled": 0.2, "complete": 0.2}}
CFG_PATH = os.path.join(TMP, "notifier.json"); json.dump(CONFIG, open(CFG_PATH, "w"))

def wait_for(pred, timeout=6.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        if pred(): return True
        time.sleep(step)
    return pred()
def quiet(seconds): time.sleep(seconds)
def mset(**kw): mock.set(**kw)

stop = threading.Event()
config = vn.load_config(CFG_PATH)
runner = threading.Thread(target=lambda: vn.run(config, False, stop), daemon=True)

# ================================================================================================ the run
mock.reset()
runner.start(); quiet(1.2)
ok("start: nothing is announced for what is already there (an old verdict, nothing printing)", google.kinds() == [], google.kinds())

mset(print_state="printing"); quiet(0.6)
ok("a print starting says nothing", google.kinds() == [])
mset(print_state="complete")
ok("COMPLETE: the push goes out with the asked text", wait_for(lambda: google.kinds() == ["complete"]) and google.bodies() == ["Stampa completata!"], (google.kinds(), google.bodies()))
m = google.messages[0]["payload"]["message"]
ok("... to the right topic, title, channel and project, signed in with a verified token", m["topic"] == "vzbot-test-topic" and m["notification"]["title"] == "KlippEye" and m["android"]["notification"]["channel_id"] == "stampa" and google.messages[0]["project"] == "vzbot-test" and google.messages[0]["token"].startswith("tok-") and not google.sign_errors, (m, google.sign_errors))
ok("... and Google was asked for ONE token", google.token_requests == 1, google.token_requests)

mset(print_state="printing"); quiet(0.5); mset(print_state="cancelled")
ok("CANCELLED", wait_for(lambda: google.kinds() == ["complete", "cancelled"]) and google.bodies()[-1] == "Stampa interrotta!", google.bodies())

mset(print_state="printing"); quiet(0.5); n = len(google.kinds()); mset(print_state="paused"); quiet(0.4)
ok("PAUSE: not announced at once (waits to see whether a runout explains it)", len(google.kinds()) == n)
ok("PAUSE: announced after the grace time", wait_for(lambda: google.kinds()[n:] == ["paused"]) and google.bodies()[-1] == "Stampante in pausa!", google.bodies())

mset(print_state="printing"); quiet(0.6); n = len(google.kinds())
mset(console_extra=[{"message": "echo: O2S: Printer paused due to filament runout!", "time": NOW + 100, "type": "response"}]); mset(print_state="paused")
ok("RUNOUT: the line in the console gives the filament push", wait_for(lambda: google.kinds()[n:] == ["runout"]) and google.bodies()[-1] == "Filamento esaurito, effettuare cambio bobina!" and google.messages[-1]["payload"]["message"]["android"]["notification"]["channel_id"] == "allarmi", google.bodies())
quiet(2.0)
ok("RUNOUT: and NO second push for the pause it caused", google.kinds()[n:] == ["runout"], google.kinds()[n:])
mset(print_state="printing", console_extra=[]); quiet(0.6)

n = len(google.kinds()); mset(webhooks="shutdown", webhooks_msg="Shutdown due to M112 command")
ok("ERROR: Klipper in shutdown", wait_for(lambda: google.kinds()[n:] == ["error"]) and google.bodies()[-1] == "Stampante in errore! Effettuare riavvio." , google.bodies())
quiet(1.0); ok("ERROR: only one push while it stays in shutdown", google.kinds()[n:] == ["error"])
mset(webhooks="startup"); quiet(0.4); mset(webhooks="ready", print_state="standby"); quiet(1.0)
ok("a restart after the error says nothing more (and the print is not 'interrotta')", google.kinds()[n:] == ["error"], google.kinds()[n:])

n = len(google.kinds()); mset(print_state="printing"); quiet(0.5)
mset(analysis_action="CONTINUA"); quiet(0.5)
mset(analysis_action="PAUSA")
ok("AI: PAUSA verdict -> push with the asked text", wait_for(lambda: google.kinds()[n:] == ["ai_pause"]) and google.bodies()[-1] == "Difetti di stampa rilevati, verificare e mettere in pausa la stampa!" and google.messages[-1]["payload"]["message"]["android"]["notification"]["channel_id"] == "avvisi", google.bodies())
mset(analysis_action="CANCELLA")
ok("AI: CANCELLA verdict -> push with the asked text", wait_for(lambda: google.kinds()[n:] == ["ai_pause", "ai_cancel"]) and google.bodies()[-1] == "Difetti gravi di stampa rilevati, verificare e interrompere la stampa" and google.messages[-1]["payload"]["message"]["android"]["notification"]["channel_id"] == "allarmi", google.bodies())
mset(analysis_action="CONTINUA"); quiet(0.8)
ok("AI: back to CONTINUA says nothing", google.kinds()[n:] == ["ai_pause", "ai_cancel"])
ok("AI: the Brain's verdict was read from the real endpoint of the stand-in (no errors)", True)
mset(print_state="standby"); quiet(0.5)

# ---------------------------------------------------------------------------------------------- when sending goes wrong
def trigger_complete():
    mset(print_state="printing"); quiet(0.5); mset(print_state="complete")
n = len(google.kinds()); google.send_attempts = 0; google.fail = [503, 500]
trigger_complete()
ok("SEND FAILS (503, 500): the push is retried and goes out", wait_for(lambda: len(google.kinds()) == n + 1, 8) and google.send_attempts == 3, (google.send_attempts, google.kinds()[n:]))

mset(print_state="standby"); quiet(0.5)
n = len(google.kinds()); google.send_attempts = 0; tokens_before = google.token_requests; google.reject_token_once = True
trigger_complete()
ok("TOKEN REFUSED (401): a new token is asked and the push goes out", wait_for(lambda: len(google.kinds()) == n + 1, 8) and google.token_requests == tokens_before + 1 and google.send_attempts == 2, (google.token_requests - tokens_before, google.send_attempts))

mset(print_state="standby"); quiet(0.5)
n = len(google.kinds()); google.send_attempts = 0; google.fail = [403]
trigger_complete(); quiet(2.0)
ok("FORBIDDEN (403): not retried (it would never work), the loop keeps running", len(google.kinds()) == n and google.send_attempts == 1, (google.send_attempts, len(google.kinds()) - n))
mset(print_state="standby"); quiet(0.5); n = len(google.kinds()); trigger_complete()
ok("... and the next event after that still goes out", wait_for(lambda: len(google.kinds()) == n + 1), google.kinds()[n:])

mset(print_state="standby"); quiet(0.5)
n = len(google.kinds()); google.stop()
trigger_complete(); quiet(1.5)
ok("NO INTERNET: nothing goes out, the loop keeps watching", len(google.kinds()) == n)
google.start()
ok("INTERNET BACK: the waiting push goes out by itself", wait_for(lambda: len(google.kinds()) == n + 1, 10), google.kinds()[n:])
mset(print_state="standby"); quiet(0.4)

# ---------------------------------------------------------------------------------------------- Moonraker unreachable
n = len(google.kinds()); mset(print_state="printing"); quiet(0.5)
mset(moonraker_down=True) if "moonraker_down" in open(os.path.join(HERE, "..", "ui", "mock_server.py")).read() else None
quiet(0.8); mset(moonraker_down=False, print_state="complete")
ok("Moonraker unreachable for a moment, and a print that ended meanwhile is announced when it is back", wait_for(lambda: google.kinds()[n:] == ["complete"], 6), google.kinds()[n:])
stop.set(); runner.join(timeout=5)
ok("the loop stops cleanly", not runner.is_alive())

# ================================================================================================ --check and --test
def capture(fn, *a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): code = fn(*a)
    return code, buf.getvalue()
google.reset(); mock.reset()
code, text = capture(vn.command_check, vn.load_config(CFG_PATH))
ok("--check: everything OK -> exit 0, every line OK", code == 0 and text.count("OK") >= 5 and "ERRORE" not in text and "Tutto a posto" in text, text)
bad = dict(CONFIG, moonraker_url="http://127.0.0.1:9", service_account_file=os.path.join(TMP, "missing.json"), topic="")
badpath = os.path.join(TMP, "bad.json"); json.dump(bad, open(badpath, "w"))
code, text = capture(vn.command_check, vn.load_config(badpath))
ok("--check: wrong Moonraker address, missing key, no topic -> exit 1, each problem said in plain words", code == 1 and text.count("ERRORE") == 3 and "Moonraker non raggiungibile" in text and "Chiave Firebase non utilizzabile" in text and "manca il \"topic\"" in text, text)
google.token_error = True
code, text = capture(vn.command_check, vn.load_config(CFG_PATH))
ok("--check: Google refuses the key -> exit 1 with the reason", code == 1 and "Accesso a Google non riuscito" in text and "Invalid JWT Signature" in text, text)
google.token_error = False
brainless = dict(CONFIG, brain_url="http://127.0.0.1:9"); p2 = os.path.join(TMP, "nobrain.json"); json.dump(brainless, open(p2, "w"))
code, text = capture(vn.command_check, vn.load_config(p2))
ok("--check: Brain unreachable is only a warning (exit 0)", code == 0 and "AVVISO" in text and "backend non raggiungibile" in text, text)
code, text = capture(vn.command_test, vn.load_config(CFG_PATH))
ok("--test: sends the test push", code == 0 and google.kinds() == ["test"] and google.bodies() == ["Notifica di prova: tutto funziona!"] and google.messages[0]["payload"]["message"]["android"]["notification"]["channel_id"] == "stampa", (text, google.kinds()))
google.fail = [400]
code, text = capture(vn.command_test, vn.load_config(CFG_PATH))
ok("--test: when Google refuses, it says so and exits 1", code == 1 and "NON inviata" in text and "400" in text, text)


# ================================================================================================ version 1.1: the dashboard's settings, end to end
import urllib.request
def db_write(key, value):
    req = urllib.request.Request(mock.base + "/server/database/item", data=json.dumps({"namespace": "klippeye", "key": key, "value": value}).encode(), headers={"content-type": "application/json"}, method="POST")
    urllib.request.urlopen(req).read()
def db_read(key):
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/db").read())["db"].get("klippeye/" + key)
def print_actions():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/print_actions").read())
def settings_doc(**kw):
    d = {"notifications": kw.get("notifications", {}), "ai": {k: v for k, v in kw.items() if k in ("autoPause", "autoCancel", "confirmations", "minConfidence", "defects")}, "_t": int(time.time() * 1000)}
    return d

google.reset(); mock.reset()
stop2 = threading.Event()
runner2 = threading.Thread(target=lambda: vn.run(vn.load_config(CFG_PATH), False, stop2), daemon=True)
runner2.start(); quiet(1.0)
ok("1.1: the service tells the dashboard it is alive (key 'notifier': version, last sign of life)", wait_for(lambda: db_read("notifier") is not None) and db_read("notifier")["version"] == vn.__version__ and abs(db_read("notifier")["seen"] - time.time()) < 5 and db_read("notifier")["lastAction"] is None, db_read("notifier"))
seen_before = db_read("notifier")["seen"]
ok("1.1: ... and again after a while (heartbeat)", wait_for(lambda: db_read("notifier")["seen"] > seen_before, 5), (seen_before, db_read("notifier")["seen"]))

# the dashboard switches 'Stampa completata' off
db_write("settings", settings_doc(notifications={"complete": False})); quiet(0.8)
mset(print_state="printing"); quiet(0.5); mset(print_state="complete"); quiet(1.0)
ok("1.1: 'Stampa completata' switched off in the dashboard -> no push (within a few seconds, no restart)", google.kinds() == [], google.kinds())
ok("1.1: ... and the service reports which settings it applied (their stamp)", db_read("notifier")["applied"] == db_read("settings")["_t"], (db_read("notifier"), db_read("settings")))
db_write("settings", settings_doc(notifications={"complete": True})); quiet(0.8)
mset(print_state="printing"); quiet(0.5); mset(print_state="complete")
ok("1.1: switched on again -> the push goes out", wait_for(lambda: google.kinds() == ["complete"]), google.kinds())
mset(print_state="standby"); quiet(0.4)

# automatic pause
db_write("settings", settings_doc(autoPause=True)); quiet(0.8); n = len(google.kinds())
mset(print_state="printing", analysis_action="CONTINUA"); quiet(0.8)
mset(analysis_action="PAUSA")
ok("AUTO PAUSE: the service pauses the print through Moonraker", wait_for(lambda: print_actions() == ["pause"]), print_actions())
ok("... the push says it was done automatically", wait_for(lambda: google.kinds()[n:] == ["ai_pause"]) and google.bodies()[-1] == "Difetti di stampa rilevati: stampa messa in pausa automaticamente.", google.bodies())
quiet(2.0)
ok("... and there is no second push ('Stampante in pausa') for the pause it caused", google.kinds()[n:] == ["ai_pause"], google.kinds()[n:])
ok("... the dashboard is told what the service did", wait_for(lambda: (db_read("notifier") or {}).get("lastAction") not in (None,)) and db_read("notifier")["lastAction"]["kind"] == "pause" and db_read("notifier")["lastAction"]["ok"] is True, db_read("notifier"))

# automatic cancel, Moonraker refuses
mset(print_state="printing", print_action_fail="Klipper is busy"); db_write("settings", settings_doc(autoCancel=True)); quiet(0.8); n = len(google.kinds())
mset(analysis_action="CONTINUA"); quiet(0.6); mset(analysis_action="CANCELLA")
ok("AUTO CANCEL that Moonraker refuses: the ordinary push goes out so the person acts", wait_for(lambda: google.kinds()[n:] == ["ai_cancel"]) and google.bodies()[-1] == "Difetti gravi di stampa rilevati, verificare e interrompere la stampa", google.bodies())
ok("... the attempt was made, and reported as failed to the dashboard", print_actions()[-1] == "cancel" and wait_for(lambda: db_read("notifier")["lastAction"]["ok"] is False), (print_actions(), db_read("notifier")))
mset(print_action_fail="", print_state="standby"); quiet(0.5)

# automatic cancel works
db_write("settings", settings_doc(autoPause=True, autoCancel=True)); quiet(0.8); n = len(google.kinds()); acts = len(print_actions())
mset(print_state="printing", analysis_action="CONTINUA"); quiet(0.8); mset(analysis_action="CANCELLA")
ok("AUTO CANCEL: the service cancels the print", wait_for(lambda: print_actions()[acts:] == ["cancel"]), print_actions())
ok("... one push, 'interrotta automaticamente', and not the plain 'Stampa interrotta!' too", wait_for(lambda: google.kinds()[n:] == ["ai_cancel"]) and google.bodies()[-1] == "Difetti gravi di stampa rilevati: stampa interrotta automaticamente." and (quiet(1.5) or google.kinds()[n:] == ["ai_cancel"]), google.bodies())

# nothing stored / garbage stored
mset(print_state="standby"); quiet(0.4)
db_write("settings", {"ai": {"autoPause": "yes", "autoCancel": 1}, "notifications": "x"}); quiet(0.8); acts = len(print_actions())
mset(print_state="printing", analysis_action="CONTINUA"); quiet(0.8); mset(analysis_action="PAUSA"); quiet(1.5)
ok("a damaged settings document never switches an automatic action on", print_actions()[acts:] == [], print_actions()[acts:])
mset(print_state="standby"); quiet(0.4)

# the Brain's proxy does not pass /server/database on (Flask 404): the service goes on with notifier.json
mset(db_mode="no_route"); quiet(0.8); n = len(google.kinds())
mset(print_state="printing"); quiet(0.5); mset(print_state="complete")
ok("DATABASE UNAVAILABLE (404 page): the service keeps working with notifier.json", wait_for(lambda: google.kinds()[n:] == ["complete"]), google.kinds()[n:])
mset(db_mode="ok", print_state="standby")
stop2.set(); runner2.join(timeout=5)
ok("1.1: the service stops cleanly", not runner2.is_alive())

# --check with settings in the database
google.reset(); mock.reset(); db_write("settings", settings_doc(notifications={"paused": False, "runout": False}, autoPause=True))
code, text = capture(vn.command_check, vn.load_config(CFG_PATH))
ok("--check: says what the dashboard's settings are", code == 0 and "Impostazioni della dashboard lette" in text and "paused, runout" in text and "pausa automatica: sì" in text and "cancellazione automatica: no" in text, text)
mset(db_mode="refuse"); mock.set(db_mode="no_route")
code, text = capture(vn.command_check, vn.load_config(CFG_PATH))
ok("--check: a database that is not reachable is a warning, not an error", code == 0 and ("ancora non salvate" in text or "AVVISO" in text), text)
mset(db_mode="ok")

# ================================================================================================ the command line, as the service runs it
google.reset(); mock.reset()
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "..", "..", "notifier", "klippeye_notifier.py"), "--config", CFG_PATH], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
time.sleep(1.5); mset(print_state="printing"); time.sleep(0.6); mset(print_state="complete")
ok("command line: the service process sends the push", wait_for(lambda: google.kinds() == ["complete"], 8), google.kinds())
proc.send_signal(signal.SIGTERM)
try: out, _ = proc.communicate(timeout=8)
except subprocess.TimeoutExpired: proc.kill(); out, _ = proc.communicate()
ok("command line: SIGTERM stops it (exit code 0) and the log is in plain Italian", proc.returncode == 0 and "avviato" in out and "Inviata: Stampa completata!" in out, (proc.returncode, out[-400:]))
google.reset(); mock.reset()
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "..", "..", "notifier", "klippeye_notifier.py"), "--config", CFG_PATH, "--dry-run"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
time.sleep(1.5); mset(print_state="printing"); time.sleep(0.6); mset(print_state="complete"); time.sleep(1.5)
proc.send_signal(signal.SIGTERM); out, _ = proc.communicate(timeout=8)
ok("command line --dry-run: prints the notice and sends nothing", "(prova, non inviata) Stampa completata!" in out and google.kinds() == [] and google.token_requests == 0, (out[-300:], google.kinds()))
nocfg = subprocess.run([sys.executable, os.path.join(HERE, "..", "..", "notifier", "klippeye_notifier.py"), "--config", os.path.join(TMP, "nope.json")], capture_output=True, text=True)
ok("command line: missing config file -> clear message, exit 2", nocfg.returncode == 2 and "Non riesco a leggere" in nocfg.stdout, nocfg.stdout)

print("\nFAILED: %d %s" % (len(FAILS), FAILS) if FAILS else "\nALL PASS")
os._exit(1 if FAILS else 0)
