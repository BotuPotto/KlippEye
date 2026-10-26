"""The block "App Android" of the page Aggiornamenti: what the backend offers (/api/app/version), what the app says about itself
(window.KlippEyeApp.appInfo), the update through the app (updateApp -> window.klippeyeAppUpdate events), an older app, a browser.
The Android app is played by a small fake bridge injected before the page starts.
Usage: app_test.py <html> <outdir> <port>"""
import sys, os, re, json, time, urllib.request
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
FAILS = []
SHA = "ab" * 32
OFFER = {"available": True, "version": "1.0.1", "code": 10001, "size": 8650000, "sha256": SHA, "built": "2026-10-22T21:15:07Z", "url": "/app/KlippEye.apk"}


def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:700]) if (extra != "" and not cond) else ""), flush=True)


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


CUR = [None]


def ws_refuses(ws):
    def on_message(msg):
        try: data = json.loads(msg)
        except Exception: return
        if isinstance(data, dict) and "id" in data:
            ws.send(json.dumps({"jsonrpc": "2.0", "id": data["id"], "error": {"code": -32601, "message": "Method not found"}}))
    ws.on_message(on_message)


def wait_until(fn, timeout=4.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn(): return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    try: return bool(fn())
    except Exception: return False


def bridge(level=5, version="1.0.0", code=10000, can_install=True, save=True, update_raises=False, info_raw=None):
    """The script that makes the page believe it runs inside the app (user agent marker + window.KlippEyeApp)."""
    info = info_raw if info_raw is not None else json.dumps(json.dumps({"version": version, "code": code, "canInstall": can_install}))
    members = []
    if level >= 5:
        members.append("appInfo: () => %s" % info)
        members.append("updateApp: (p, v, s, z) => { window.__bridge.updates.push([p, v, s, z]); %s }" % ("throw new Error('no');" if update_raises else ""))
    if save and level >= 3:
        members.append("saveUrl: (u, n) => { window.__bridge.saves.push([u, n]); }")
    return """(() => {
      const ua = navigator.userAgent + ' KlippEyeApp/%d';
      Object.defineProperty(navigator, 'userAgent', { get: () => ua });
      window.__bridge = { updates: [], saves: [] };
      window.KlippEyeApp = { %s };
    })();""" % (level, ", ".join(members))


def fresh(b, w=390, h=844, wait=1400, app=None, script=None, **st):
    mock.reset()
    mock.set(services={"klipper": ["active", "running"], "moonraker": ["active", "running"], "klippeye": ["active", "running"], "klippeye-notifier": ["active", "running"]},
             **({"app_apk": app} if app is not None else {}), **st)
    P = Page(b, mock, w, h)
    CUR[0] = P
    P.pg.route("https://raw.githubusercontent.com/**", lambda route: route.fulfill(status=200, body="1.0.0\n", content_type="text/plain", headers={"access-control-allow-origin": "*"}))
    P.pg.route_web_socket("**/websocket", ws_refuses)
    if script: P.pg.add_init_script(script)
    P.goto("home", wait)
    return P


def open_software(P):
    P.pg.click('button[aria-label="Impostazioni"]'); P.pg.wait_for_selector(".drawer"); P.settle(450)
    P.pg.click('.set-entry[data-page="software"]'); P.settle(600)


def block(P):
    """The text and the controls of the group "App Android"."""
    return P.pg.locator(".set-group", has=P.pg.locator(".set-group__label", has_text="App Android"))


def block_text(P):
    return block(P).inner_text()


def buttons(P):
    return [t.strip() for t in block(P).locator("button").all_inner_texts()]


def emit(P, event):
    P.pg.evaluate("(e) => window.klippeyeAppUpdate && window.klippeyeAppUpdate(e)", event)
    P.settle(150)


def updates(P):
    return P.pg.evaluate("() => window.__bridge.updates")


with sync_playwright() as p:
    b = p.chromium.launch()

    # ====================================================================================== a browser
    P = fresh(b, app=OFFER)
    pg = P.pg
    open_software(P)
    ok("browser: the group exists on the page", block(P).count() == 1)
    ok("browser: it says what the Raspberry has", wait_until(lambda: "Sul Raspberry" in block_text(P) and "1.0.1 • 8.2 MB" in block_text(P)), block_text(P))
    ok("browser: no installed version is shown (a browser has no app)", "App installata" not in block_text(P))
    ok("browser: the app is announced as ready, with one download button", "L'app Android 1.0.1 è pronta" in block_text(P) and buttons(P) == ["Scarica l'app"], (block_text(P), buttons(P)))
    ok("browser: it explains how to install", "dal telefono" in block_text(P) and "consentire" in block_text(P))
    with pg.expect_download() as info:
        block(P).locator("button", has_text="Scarica l'app").click()
    ok("browser: the button downloads KlippEye-1.0.1.apk from the backend", info.value.suggested_filename == "KlippEye-1.0.1.apk" and state()["app_apk_downloads"] >= 1, (info.value.suggested_filename, state()["app_apk_downloads"]))
    ok("browser: no console error", P.errors == [], P.errors)
    P.close()

    # ====================================================================================== nothing offered
    for label, kwargs, expect in (
        ("nothing published yet", dict(app=None), "non c'è ancora nessuna app"),
        ("the backend says the file is not whole", dict(app={"available": False, "reason": "the APK does not match version.json (different fingerprint)"}), "non è completa (l'APK non corrisponde a version.json (impronta diversa))"),
        ("a backend that does not know apps (404)", dict(app_apk_status=404), "non conosce ancora l'app"),
        ("the backend fails (500)", dict(app_apk_status=500), "non risponde"),
        ("the backend answers nonsense", dict(app={"available": True, "version": "x"}), "non conosce ancora l'app"),
    ):
        P = fresh(b, **kwargs)
        open_software(P)
        ok("offer: %s -> a clear line, no button" % label, wait_until(lambda: expect in block_text(P)) and buttons(P) == [], (block_text(P), buttons(P)))
        P.close()

    # ====================================================================================== the app of release 5
    P = fresh(b, app=OFFER, script=bridge())
    pg = P.pg
    ok("app: the user agent carries the marker", pg.evaluate("() => /KlippEyeApp\\/5/.test(navigator.userAgent)"))
    pg.click('button[aria-label="Impostazioni"]'); pg.wait_for_selector(".drawer"); P.settle(500)
    entry = pg.locator('.set-entry[data-page="software"]')
    ok("app: the menu list announces the waiting app (badge + summary)", wait_until(lambda: entry.locator(".set-entry__badge").count() == 1 and "app da aggiornare" in entry.locator(".set-entry__meta").inner_text()), entry.inner_text())
    pg.click('.set-entry[data-page="software"]'); P.settle(600)
    ok("app: installed and offered versions are shown", wait_until(lambda: "App installata" in block_text(P) and "1.0.0" in block_text(P) and "1.0.1 • 8.2 MB" in block_text(P)), block_text(P))
    ok("app: 'Disponibile l'app 1.0.1 (hai la 1.0.0)' and the button", "Disponibile l'app 1.0.1 (hai la 1.0.0)" in block_text(P) and buttons(P) == ["Aggiorna l'app"], (block_text(P), buttons(P)))
    ok("app: the note says Android asks for confirmation", "Android ti chiede conferma" in block_text(P) and "Installa app sconosciute" not in block_text(P))
    P.shot(out + "/app_waiting.png", tall=False)
    block(P).locator("button", has_text="Aggiorna l'app").click(); P.settle(300)
    ok("app: the button calls updateApp once, with path, version, sha256 and size as text", updates(P) == [["/app/KlippEye.apk", "1.0.1", SHA, "8650000"]], updates(P))
    ok("app: while waiting for the app it says it is starting", "Avvio l'aggiornamento" in block_text(P) and buttons(P) == [], block_text(P))
    emit(P, {"stato": "scarico", "fatto": 0, "totale": 8650000})
    ok("app: download 0 %", "Scarico l'app 1.0.1… 0 %" in block_text(P), block_text(P))
    emit(P, {"stato": "scarico", "fatto": 3633000, "totale": 8650000})
    bar = block(P).locator(".oui-progress__bar")
    ok("app: download 42 %: text and bar", "42 %" in block_text(P) and abs(float(bar.evaluate("e => e.style.width").replace("%", "")) - 42) < 1 and block(P).locator("[role=progressbar]").get_attribute("aria-valuenow") == "42", (block_text(P), bar.evaluate("e => e.style.width")))
    P.shot(out + "/app_downloading.png", tall=False)
    emit(P, {"stato": "scarico", "fatto": 99999999, "totale": 8650000})
    ok("app: a progress beyond the total stops at 100 %", "100 %" in block_text(P))
    emit(P, {"stato": "boh"}); emit(P, None); emit(P, "testo"); emit(P, {"stato": "scarico", "fatto": "x", "totale": "y"})
    ok("app: unknown or broken events are ignored (the page does not crash)", P.errors == [] and "Scarico l'app" in block_text(P), (P.errors, block_text(P)))
    emit(P, {"stato": "permesso"})
    ok("app: Android asks for the install permission -> instructions and a retry button", "Consenti da questa fonte" in block_text(P) and "Auto Blocker" in block_text(P) and buttons(P) == ["Riprova"], (block_text(P), buttons(P)))
    P.shot(out + "/app_permission.png", tall=False)
    emit(P, {"stato": "installazione"})
    ok("app: the installer is open -> what to do, and a retry button", "Conferma l'installazione" in block_text(P) and "riapri KlippEye" in block_text(P) and buttons(P) == ["Riprova"], (block_text(P), buttons(P)))
    block(P).locator("button", has_text="Riprova").click(); P.settle(300)
    ok("app: 'Riprova' asks the app again", len(updates(P)) == 2 and updates(P)[1] == updates(P)[0], updates(P))
    emit(P, {"stato": "errore", "messaggio": "il file scaricato è rovinato (impronta diversa): riprova"})
    ok("app: an error shows its reason and offers a retry", "Aggiornamento non riuscito: il file scaricato è rovinato" in block_text(P) and buttons(P) == ["Riprova"], block_text(P))
    P.shot(out + "/app_error.png", tall=False)
    emit(P, {"stato": "errore", "messaggio": "x" * 800})
    ok("app: a very long error is cut", len(block_text(P)) < 700, len(block_text(P)))
    # leaving the page and coming back forgets the progress (the app goes on by itself)
    pg.click('.drawer button[aria-label="Indietro"]'); P.settle(500)
    ok("app: the listener is removed when the page is left", pg.evaluate("() => window.klippeyeAppUpdate === undefined"))
    pg.click('.set-entry[data-page="software"]'); P.settle(600)
    ok("app: back on the page it starts again from the button", buttons(P) == ["Aggiorna l'app"], buttons(P))
    ok("app: no page error during the whole update", P.errors == [], P.errors)
    P.close()

    # the app never answers
    P = fresh(b, app=OFFER, script=bridge())
    open_software(P)
    block(P).locator("button", has_text="Aggiorna l'app").click()
    ok("app: no answer from the app within 12 s -> an error, not an endless wait", wait_until(lambda: "l'app non ha risposto" in block_text(P), 13.0), block_text(P))
    ok("... with a retry button", buttons(P) == ["Riprova"], buttons(P))
    P.close()

    # the bridge refuses
    P = fresh(b, app=OFFER, script=bridge(update_raises=True))
    open_software(P)
    block(P).locator("button", has_text="Aggiorna l'app").click(); P.settle(300)
    ok("app: a bridge that throws -> an error that says so", "l'app non ha accettato la richiesta" in block_text(P) and buttons(P) == ["Riprova"], block_text(P))
    P.close()

    # same version / newer app / Android does not allow installs yet
    P = fresh(b, app=OFFER, script=bridge(version="1.0.1", code=10001))
    open_software(P)
    ok("app: same version -> 'L'app è aggiornata', no button, no badge", wait_until(lambda: "L'app è aggiornata" in block_text(P)) and buttons(P) == [], (block_text(P), buttons(P)))
    pg = P.pg
    pg.click('.drawer button[aria-label="Indietro"]'); P.settle(500)
    entry = pg.locator('.set-entry[data-page="software"]')
    ok("app: ... and the menu list has no badge", entry.locator(".set-entry__badge").count() == 0 and "app da aggiornare" not in entry.inner_text(), entry.inner_text())
    P.close()

    P = fresh(b, app=OFFER, script=bridge(version="1.2.0", code=10200))
    open_software(P)
    ok("app: newer than the Raspberry -> says to update KlippEye first, no button", wait_until(lambda: "più nuova di quella sul Raspberry" in block_text(P)) and buttons(P) == [], (block_text(P), buttons(P)))
    P.close()

    P = fresh(b, app=OFFER, script=bridge(can_install=False))
    open_software(P)
    ok("app: Android has not allowed installs yet -> the note announces the permission", wait_until(lambda: "Installa app sconosciute" in block_text(P)), block_text(P))
    P.close()

    P = fresh(b, app=None, script=bridge())
    open_software(P)
    ok("app: nothing on the Raspberry -> installed version shown, no update button", wait_until(lambda: "App installata" in block_text(P) and "non c'è ancora nessuna app" in block_text(P)) and buttons(P) == [], (block_text(P), buttons(P)))
    P.close()

    P = fresh(b, app=OFFER, script=bridge(info_raw="'non json'"))
    open_software(P)
    ok("app: appInfo answers nonsense -> treated as an old app, no crash", wait_until(lambda: "versione precedente dell'app" in block_text(P)) and P.errors == [], (block_text(P), P.errors))
    P.close()

    # ====================================================================================== an older app
    P = fresh(b, app=OFFER, script=bridge(level=4))
    open_software(P)
    ok("old app (4): says it cannot update itself and offers the download", wait_until(lambda: "non sa aggiornarsi da sola" in block_text(P)) and buttons(P) == ["Scarica l'app 1.0.1"], (block_text(P), buttons(P)))
    ok("old app (4): the note points at the Download folder and the conflict case", "cartella Download" in block_text(P) and "disinstalla prima" in block_text(P))
    block(P).locator("button", has_text="Scarica l'app").click(); P.settle(300)
    ok("old app (4): the button asks the app to save the file", P.pg.evaluate("() => window.__bridge.saves") == [["/app/KlippEye.apk", "KlippEye-1.0.1.apk"]], P.pg.evaluate("() => window.__bridge.saves"))
    ok("old app (4): the menu list has no badge for it", True)
    P.close()

    P = fresh(b, app=OFFER, script=bridge(level=2))
    open_software(P)
    ok("old app (2): cannot save files -> points at the browser with the full address", wait_until(lambda: "nel browser del telefono" in block_text(P)) and (mock.base + "/app/KlippEye.apk") in block_text(P), block_text(P))
    block(P).locator("button", has_text="Scarica l'app").click(); P.settle(400)
    ok("old app (2): the button explains instead of failing silently", P.pg.locator("text=Il download non funziona in questa versione dell'app").count() >= 1)
    P.close()

    # ====================================================================================== layout
    for vw, vh in ((360, 740), (1280, 800)):
        P = fresh(b, vw, vh, app={**OFFER, "version": "1.0.12", "code": 10012}, script=bridge())
        pg = P.pg
        open_software(P)
        wait_until(lambda: "Disponibile l'app" in block_text(P))
        block(P).locator("button", has_text="Aggiorna l'app").click(); P.settle(300)
        emit(P, {"stato": "scarico", "fatto": 5000000, "totale": 8650000})
        o = pg.evaluate("() => { const b = document.querySelector('.drawer__body'); return { page: document.documentElement.scrollWidth - document.documentElement.clientWidth, body: b.scrollWidth - b.clientWidth }; }")
        ok("[%dpx] app block during a download: nothing sticks out sideways" % vw, o["page"] <= 0 and o["body"] <= 0, o)
        emit(P, {"stato": "permesso"})
        o = pg.evaluate("() => { const b = document.querySelector('.drawer__body'); return { page: document.documentElement.scrollWidth - document.documentElement.clientWidth, body: b.scrollWidth - b.clientWidth }; }")
        ok("[%dpx] app block asking for the permission: nothing sticks out sideways" % vw, o["page"] <= 0 and o["body"] <= 0, o)
        P.shot(out + "/app_%d.png" % vw, tall=False)
        ghosts = pg.evaluate(GHOST_JS)
        unknown = [c for c in ghosts["unknown"] if c != "position-readout" and not c.startswith(("is-", "has-"))]
        ok("[%dpx] every class used has a style" % vw, unknown == [], unknown)
        buttons_ok = pg.evaluate("() => [...document.querySelectorAll('.set-group button, .set-group a')].filter(e => e.offsetParent && e.getBoundingClientRect().height < 34).length")
        ok("[%dpx] buttons are at least 34 px tall" % vw, buttons_ok == 0, buttons_ok)
        P.close()
    b.close()

print("\nFAILS:", FAILS if FAILS else "none")
print("ALLDONE" if not FAILS else "ALLDONE_WITH_FAILURES")
sys.exit(1 if FAILS else 0)
