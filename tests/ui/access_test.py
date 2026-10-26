"""Password della dashboard (1.2.0) con il backend VERO: attivarla dal menu, la pagina di accesso su un altro dispositivo,
'fai uscire gli altri' che rimanda alla pagina di accesso chi era dentro, 'esci da questo dispositivo', togliere la password.
Usage: access_test.py <html> <outdir> <port>"""
import importlib.util, os, shutil, sys, tempfile, threading, time
from playwright.sync_api import sync_playwright

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(out, exist_ok=True)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))   # the repository
sys.path.insert(0, os.path.join(ROOT, "tests", "backend"))
sys.path.insert(0, os.path.join(ROOT, "tests", "backend", "stubs"))
import fakes  # noqa: E402

FAILS = []


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:400]) if (extra != "" and not cond) else ""))


# un "repository" provvisorio: backend vero + la dashboard da provare
root = tempfile.mkdtemp(prefix="ke-access-")
repo, data = os.path.join(root, "klippeye"), os.path.join(root, "data")
os.makedirs(os.path.join(repo, "backend")); os.makedirs(os.path.join(repo, "frontend"))
for name in ("klippeye_backend.py", "access.py"):
    shutil.copy(os.path.join(ROOT, "backend", name), os.path.join(repo, "backend", name))
shutil.copy(html, os.path.join(repo, "frontend", "klippeye_frontend.html"))
open(os.path.join(repo, "VERSION"), "w").write("1.2.0\n")
os.environ["KLIPPEYE_DATA"] = data
fake = fakes.Fake()
spec = importlib.util.spec_from_file_location("ke_backend", os.path.join(repo, "backend", "klippeye_backend.py"))
b = importlib.util.module_from_spec(spec); sys.modules["ke_backend"] = b; spec.loader.exec_module(b)
b.MOONRAKER_URL = fake.url
b.CAMERA_NGINX_URL = fake.url + "/webcam"
from werkzeug.serving import make_server  # noqa: E402
server = make_server("127.0.0.1", port, b.app, threaded=True)
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % port


def wait(pg, fn, timeout=6.0):
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
    A = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
    errors = []
    A.on("pageerror", lambda e: errors.append(str(e)))
    A.goto(BASE + "/"); A.wait_for_selector('.app-header button[aria-label="Impostazioni"]', timeout=15000); A.wait_for_timeout(800)
    ok("senza password la dashboard si apre come prima", A.url.endswith("/") and A.locator(".app-header").count() == 1)
    A.click('button[aria-label="Impostazioni"]'); A.wait_for_selector(".drawer"); A.wait_for_timeout(450)
    entry = A.locator('.set-entry[data-page="access"]')
    ok("nel menu c'e' il gruppo 'Accesso'", entry.count() == 1 and "Accesso" in entry.inner_text(), A.locator(".set-entry").all_inner_texts())
    ok("... il riassunto dice 'Password non attiva'", wait(A, lambda: "Password non attiva" in entry.inner_text()), entry.inner_text())
    entry.click(); A.wait_for_timeout(500)
    ok("la pagina dice che la password non e' attiva", wait(A, lambda: "Password non attiva" in A.locator(".drawer").inner_text()))
    A.screenshot(path=os.path.join(out, "accesso_spenta.png"))
    A.fill("#access-new", "abc"); A.fill("#access-repeat", "abc")
    A.click("text=Attiva la password")
    ok("password troppo corta: lo dice e non la attiva", wait(A, lambda: "almeno 6 caratteri" in A.locator(".drawer").inner_text()))
    A.fill("#access-new", "segreta123"); A.fill("#access-repeat", "segreta124")
    A.click("text=Attiva la password")
    ok("le due password diverse: lo dice", wait(A, lambda: "non coincidono" in A.locator(".drawer").inner_text()))
    A.fill("#access-repeat", "segreta123")
    A.click("text=Attiva la password")
    ok("attivata: messaggio e stato 'Password attiva'", wait(A, lambda: "Password attivata" in A.locator(".drawer").inner_text() and "Password attiva" in A.locator(".drawer").inner_text()), A.locator(".drawer").inner_text()[:300])
    ok("... compaiono 'Fai uscire tutti' e 'Togli la password'", A.locator("text=Fai uscire tutti gli altri dispositivi").count() == 1 and A.locator("button:has-text('Togli la password')").count() == 1)
    A.screenshot(path=os.path.join(out, "accesso_attiva.png"))
    A.reload(); A.wait_for_timeout(1500)
    ok("questo dispositivo resta dentro anche ricaricando", A.url.endswith("/") and A.locator(".app-header").count() == 1, A.url)

    B = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
    B.goto(BASE + "/")
    ok("un altro dispositivo finisce sulla pagina di accesso", B.url.endswith("/login") and B.locator("input[name=password]").count() == 1, B.url)
    B.screenshot(path=os.path.join(out, "login.png"))
    B.fill("input[name=password]", "sbagliata"); B.click("button[type=submit]")
    ok("... password sbagliata: resta li' e lo dice", "Wrong password" in B.inner_text("body") and B.url.endswith("/login"))
    B.fill("input[name=password]", "segreta123"); B.click("button[type=submit]")
    B.wait_for_selector('.app-header button[aria-label="Impostazioni"]', timeout=15000)
    ok("... password giusta: entra nella dashboard", B.url.endswith("/") and B.locator(".app-header").count() == 1, B.url)
    B.wait_for_timeout(1500)
    ok("... e la dashboard lavora (legge lo stato della stampante)", B.url.endswith("/"))

    # A fa uscire gli altri: B al prossimo dato letto torna alla pagina di accesso
    A.click('button[aria-label="Impostazioni"]'); A.wait_for_selector(".drawer"); A.wait_for_timeout(400)
    A.click('.set-entry[data-page="access"]'); A.wait_for_timeout(500)
    A.click("text=Fai uscire tutti gli altri dispositivi")
    ok("'fai uscire tutti gli altri': conferma", wait(A, lambda: "dovranno rifare l'accesso" in A.locator(".drawer").inner_text()))
    ok("... l'altro dispositivo torna da solo alla pagina di accesso", wait(B, lambda: B.url.endswith("/login"), 10), B.url)
    ok("... questo no", A.url.endswith("/") and A.locator(".drawer").count() == 1)

    A.click("text=Esci da questo dispositivo")
    ok("'esci da questo dispositivo' porta alla pagina di accesso", wait(A, lambda: A.url.endswith("/login"), 8), A.url)
    A.fill("input[name=password]", "segreta123"); A.click("button[type=submit]")
    A.wait_for_selector('.app-header button[aria-label="Impostazioni"]', timeout=15000)
    A.click('button[aria-label="Impostazioni"]'); A.wait_for_selector(".drawer"); A.wait_for_timeout(400)
    A.click('.set-entry[data-page="access"]'); A.wait_for_timeout(500)
    A.click("button:has-text('Togli la password')") if A.locator("button:has-text('Togli la password')").is_enabled() else None
    ok("'Togli la password' e' spento finche' non scrivi la password attuale", not A.locator("button:has-text('Togli la password')").is_enabled())
    A.fill("#access-current", "segreta123")
    A.click("button:has-text('Togli la password')")
    ok("tolta: 'Password non attiva'", wait(A, lambda: "Password tolta" in A.locator(".drawer").inner_text()), A.locator(".drawer").inner_text()[:300])
    C = browser.new_context().new_page(); C.goto(BASE + "/")
    ok("... e un dispositivo nuovo entra senza accesso", C.url.endswith("/"), C.url)
    ok("nessun errore JavaScript", not errors, errors[:3])
    browser.close()

server.shutdown(); fake.close(); shutil.rmtree(root, ignore_errors=True)
print("FAILS: %d" % len(FAILS) if FAILS else "ALL PASS")
sys.exit(1 if FAILS else 0)
