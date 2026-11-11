"""Settings › Home Assistant / MQTT (1.100) with the REAL backend and a small MQTT broker: the page off at first, a wrong
password told by «Test the connection», saving connects and publishes the printer (Home Assistant's discovery included),
the password never shown again, the page at 320 px.
Usage: mqtt_test.py <html> <outdir> <port>"""
import importlib.util, json, os, shutil, sys, tempfile, threading, time
from playwright.sync_api import sync_playwright

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(out, exist_ok=True)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tests", "backend"))
sys.path.insert(0, os.path.join(ROOT, "tests", "backend", "stubs"))
import fakes  # noqa: E402
from fake_mqtt_broker import FakeBroker  # noqa: E402

FAILS = []


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:400]) if (extra != "" and not cond) else ""))


root = tempfile.mkdtemp(prefix="ke-mqtt-")
repo, data = os.path.join(root, "klippeye"), os.path.join(root, "data")
os.makedirs(os.path.join(repo, "backend")); os.makedirs(os.path.join(repo, "frontend"))
for name in os.listdir(os.path.join(ROOT, "backend")):
    if name.endswith(".py"):
        shutil.copy(os.path.join(ROOT, "backend", name), os.path.join(repo, "backend", name))
shutil.copy(html, os.path.join(repo, "frontend", "klippeye_frontend.html"))
open(os.path.join(repo, "VERSION"), "w").write("1.100.0\n")
os.environ["KLIPPEYE_DATA"] = data
fake = fakes.Fake()
spec = importlib.util.spec_from_file_location("ke_backend", os.path.join(repo, "backend", "klippeye_backend.py"))
b = importlib.util.module_from_spec(spec); sys.modules["ke_backend"] = b; spec.loader.exec_module(b)
b.MOONRAKER_URL = fake.url
b.PORT = port
b.CAMERA_NGINX_URL = fake.url + "/webcam"
b._mqtt_read_lights = lambda: [{"id": "m-luci-on", "name": "Luci", "on": "LUCI_ON", "off": "LUCI_OFF", "object": None}]
from werkzeug.serving import make_server  # noqa: E402
server = make_server("127.0.0.1", port, b.app, threaded=True)
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % port
broker = FakeBroker("ha", "secret")


def wait(pg, fn, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        pg.wait_for_timeout(150)
    return False


with sync_playwright() as p:
    browser = p.chromium.launch()
    A = browser.new_context(viewport={"width": 390, "height": 844}, locale="it-IT").new_page()
    errors = []
    A.on("pageerror", lambda e: errors.append(str(e)))
    A.goto(BASE + "/"); A.wait_for_selector('.app-header button[aria-label="Impostazioni"]', timeout=15000); A.wait_for_timeout(800)
    A.click('button[aria-label="Impostazioni"]'); A.wait_for_selector(".drawer"); A.wait_for_timeout(450)
    entry = A.locator('.set-entry[data-page="homeauto"]')
    ok("in the menu: Home Assistant / MQTT, with the system pages", entry.count() == 1 and "Home Assistant" in entry.inner_text(), A.locator(".set-entry").all_inner_texts())
    entry.click()
    ok("off at first", wait(A, lambda: A.locator('[data-mqtt-status="off"]').count() == 1))
    drawer = A.locator(".drawer")
    ok("the plain topics shown with the printer's own main topic", "klippeye/" in A.locator("[data-mqtt-topics]").inner_text() and "/command" in A.locator("[data-mqtt-topics]").inner_text())
    A.locator('.set-switch:has-text("Pubblica la stampante su MQTT")').click()
    A.fill('[data-mqtt-field="host"]', "127.0.0.1")
    A.fill('[data-mqtt-field="port"]', str(broker.port))
    A.fill('[data-mqtt-field="username"]', "ha")
    A.fill("#mqtt-password", "wrong")
    A.click("[data-mqtt-test]")
    ok("«Test the connection» with a wrong password says so", wait(A, lambda: "wrong user name or password" in drawer.inner_text()), drawer.inner_text()[:400])
    A.fill("#mqtt-password", "secret")
    A.click("[data-mqtt-test]")
    ok("... with the right one: the broker answered", wait(A, lambda: "utente e password sono giusti" in drawer.inner_text()))
    A.click("[data-mqtt-save]")
    ok("saved: connected to the broker", wait(A, lambda: A.locator('[data-mqtt-status="connected"]').count() == 1, 15), drawer.inner_text()[:400])
    ok("... the password field empty again, «saved» in its label", A.locator("#mqtt-password").input_value() == "" and "salvata" in drawer.inner_text())
    ok("the printer on the broker: online, its state, Home Assistant's discovery with the light",
       wait(A, lambda: any(t.endswith("/availability") and v == b"online" for t, v in broker.retained.items())
            and any(t.endswith("/status/state") for t in broker.retained) and any(t.startswith("homeassistant/light/") for t in broker.retained)), sorted(broker.retained))
    ok("... the lights published listed on the page", wait(A, lambda: "Luci" in A.locator("[data-mqtt-lights]").inner_text()))
    A.screenshot(path=os.path.join(out, "mqtt_connected.png"), full_page=True)
    ok("the password never sent back to the page", "secret" not in json.dumps(json.loads(A.evaluate("() => fetch('/api/mqtt').then(r => r.text())"))))
    A.locator('.set-switch:has-text("Permetti di annullare la stampa")').click()
    A.click("[data-mqtt-save]")
    ok("cancel allowed: Home Assistant gets a cancel button", wait(A, lambda: any("/button/" in t and t.endswith("/cancel/config") and v for t, v in broker.retained.items())), sorted(broker.retained))
    A.set_viewport_size({"width": 320, "height": 700}); A.wait_for_timeout(400)
    wide = A.evaluate("() => [...document.querySelectorAll('.drawer *')].filter(e => e.getBoundingClientRect().right > window.innerWidth + 1).map(e => e.className).slice(0, 5)")
    ok("at 320 px nothing goes out of the page", not wide, wide)
    A.set_viewport_size({"width": 390, "height": 844}); A.wait_for_timeout(300)
    A.locator('.set-switch:has-text("Pubblica la stampante su MQTT")').click()
    A.click("[data-mqtt-save]")
    ok("switched off: off, and the entities removed from Home Assistant",
       wait(A, lambda: A.locator('[data-mqtt-status="off"]').count() == 1 and not [t for t in broker.retained if t.endswith("/config")]), sorted(broker.retained))
    ok("no errors in the page", not errors, errors)
    browser.close()

broker.close()
server.shutdown()
fake.close()
print("%d FAIL" % len(FAILS))
sys.exit(1 if FAILS else 0)
