"""Release 1.61: more printers. Settings → Your printers (add with «Try», the name the printer gives itself, remove);
the switcher on the logo and name in the top bar (this printer, the others with their state, the overview, manage);
the overview's tiles; opening another printer (its address :8085, saying where it comes from; in the app, through the
app); arriving from another printer offers to add it. Their state comes through this KlippEye (/api/printers/peek).
Against the mock. Usage: printers_test.py <html> <outdir> <port>"""
import json
import os
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit
atexit.register(mock.stop)
FAILS = []


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


def wait_until(fn, timeout=6.0, step=0.15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(step)
    return False


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def stored():
    for _ in range(3):
        doc = json.loads(urllib.request.urlopen(mock.base + "/server/database/item?namespace=klippeye&key=settings").read())
        return (doc.get("result") or {}).get("value") or {}


VORON = {"ok": True, "name": "Voron 2.4", "brand": "voron", "release": "1.61.0", "state": "printing", "filename": "Cube.gcode", "progress": 0.3, "duration": 600, "extruder": [240.0, 240.0], "bed": [100.0, 100.0]}

with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    mock.set(printing=True, peers={"192.168.1.60": VORON})
    P = Page(b, mock, 390, 844)
    pg = P.pg
    P.goto("home", 2000)
    switch = pg.locator(".app-header__switch")
    ok("the logo and name in the top bar are a button (the printers)", switch.count() == 1 and switch.get_attribute("data-printers") == "0")
    switch.click(); P.settle(1200)
    menu = pg.locator(".oui-menu")
    ok("with no other printer: this one (and its state), and «Aggiungi una stampante»", "Questa stampante" in menu.inner_text() and "Stampa in corso · 42%" in menu.inner_text() and "Aggiungi una stampante" in menu.inner_text(), menu.inner_text())
    menu.locator(".oui-menu__item", has_text="Aggiungi una stampante").click(); P.settle(900)
    ok("... which opens Settings → Your printers", pg.locator(".drawer__title").inner_text() == "Le tue stampanti")

    # ------------------------------------------------------------------ adding
    addr = pg.locator("[data-printer-address]")
    addr.fill("not an address!"); P.settle(200)
    ok("not an address: says so, nothing can be added", "Non è un indirizzo" in pg.locator(".drawer__body").inner_text() and pg.locator("[data-printer-add]").is_disabled())
    addr.fill(pg.evaluate("() => location.host")); P.settle(200)
    ok("this printer's own address: already there", "c'è già" in pg.locator(".drawer__body").inner_text() and pg.locator("[data-printer-add]").is_disabled())
    addr.fill("http://192.168.1.60/"); P.settle(200)
    pg.locator("[data-printer-try]").click()
    ok("Prova: asked through this KlippEye, it answers with its name and state", wait_until(lambda: pg.locator('[data-printer-trial="ok"]').count() == 1) and "Voron 2.4" in pg.locator('[data-printer-trial="ok"]').inner_text() and "192.168.1.60" in state()["peek_log"], state()["peek_log"])
    pg.locator("[data-printer-add]").click(); P.settle(900)
    ok("added with the name it gives itself, http:// and / dropped, saved in the shared settings", wait_until(lambda: [(x["name"], x["host"]) for x in stored().get("printers", [])] == [("Voron 2.4", "192.168.1.60")]), stored().get("printers"))
    addr.fill("192.168.1.61:9000"); pg.locator("[data-printer-name]").fill("Ender"); P.settle(200)
    pg.locator("[data-printer-add]").click(); P.settle(900)
    ok("a second one with a port and a name of mine (nobody answers there: added anyway)", wait_until(lambda: [x["host"] for x in stored().get("printers", [])] == ["192.168.1.60", "192.168.1.61:9000"]))
    ok("... the list shows each one with its state", wait_until(lambda: "Non raggiungibile" in pg.locator('[data-printer="192.168.1.61:9000"]').inner_text() and "Stampa in corso · 30%" in pg.locator('[data-printer="192.168.1.60"]').inner_text()), pg.locator("[data-printers-list]").inner_text())
    pg.locator('[data-printer="192.168.1.61:9000"]').get_by_role("button", name="Sposta in su").click(); P.settle(600)
    ok("moving one up changes the order", wait_until(lambda: [e.get_attribute("data-printer") for e in pg.locator("[data-printer]").all()] == ["192.168.1.61:9000", "192.168.1.60"]))
    P.shot_vp(out + "/settings.png")  # (a tall screenshot opens more camera streams than the browser's connections: after the saves)
    pg.click('.drawer button[aria-label="Chiudi"]'); P.settle(500)

    # ------------------------------------------------------------------ the switcher and the overview
    switch.click(); P.settle(1500)
    ok("the switcher: this one, then the others in order with their state and address", [e.get_attribute("data-printer-row") for e in pg.locator("[data-printer-row]").all()] == ["self", "192.168.1.61:9000", "192.168.1.60"]
       and "Voron 2.4" in menu.inner_text() and "Panoramica" in menu.inner_text() and "Gestisci le stampanti" in menu.inner_text(), menu.inner_text())
    P.shot_vp(out + "/switcher.png")
    menu.locator(".oui-menu__item", has_text="Panoramica").click(); P.settle(1500)
    tiles = pg.locator("[data-printer-tile]")
    ok("the overview: a tile for each, this one first", wait_until(lambda: tiles.count() == 3) and tiles.first.get_attribute("data-printer-tile") == "self")
    voron = pg.locator('[data-printer-tile="192.168.1.60"]')
    ok("... a tile says state, progress, file, temperatures", wait_until(lambda: "30%" in voron.inner_text()) and "Cube.gcode" in voron.inner_text() and "Ugello 240°/240°" in voron.inner_text() and voron.locator(".printer-tile__fill").count() == 1, voron.inner_text())
    P.shot_vp(out + "/overview.png")
    target = []
    pg.route("http://192.168.1.60:8085/**", lambda route: (target.append(route.request.url), route.fulfill(status=200, body="<html><body>other</body></html>", content_type="text/html")))
    voron.click()
    ok("a tap opens it: its address on port 8085, saying where it comes from", wait_until(lambda: target and target[0].startswith("http://192.168.1.60:8085/?from=") and "fromName=KlippEye" in target[0]), target)
    P.close()

    # ------------------------------------------------------------------ arriving from another printer
    P = Page(b, mock, 390, 844)
    pg = P.pg
    pg.goto(mock.base + "/?from=192.168.1.70&fromName=Prusa%20MK4"); pg.wait_for_timeout(2200)
    invite = pg.locator("[data-printer-arrival]")
    ok("arriving from a printer not in the list: «Arrivi da «Prusa MK4»…», and the address is cleaned", invite.count() == 1 and "Prusa MK4" in invite.inner_text() and "from=" not in pg.url, (invite.count(), pg.url))
    invite.get_by_role("button", name="Aggiungi").click(); P.settle(900)
    ok("... «Aggiungi» puts it in the list", wait_until(lambda: [x["host"] for x in stored()["printers"]][-1] == "192.168.1.70" and stored()["printers"][-1]["name"] == "Prusa MK4") and invite.count() == 0, stored().get("printers"))
    pg.goto(mock.base + "/?from=192.168.1.60&fromName=Voron"); pg.wait_for_timeout(2000)
    ok("arriving from one already in the list: nothing asked", pg.locator("[data-printer-arrival]").count() == 0)
    ok("no page errors", not [e for e in P.errors if "pageerror" in e], P.errors[:3])
    P.close()

    # ------------------------------------------------------------------ in the app: the app opens it
    P = Page(b, mock, 390, 844)
    pg = P.pg
    pg.add_init_script("window.__switched = []; window.KlippEyeApp = { switchPrinter: (json) => window.__switched.push(JSON.parse(json)) };")
    P.goto("home", 2000)
    pg.locator(".app-header__switch").click(); P.settle(1200)
    pg.locator('[data-printer-row="192.168.1.60"]').click(); P.settle(400)
    ok("in the app: the app is asked to open it (host and name)", pg.evaluate("() => window.__switched") == [{"host": "192.168.1.60", "name": "Voron 2.4"}], pg.evaluate("() => window.__switched"))
    P.close()

    # ------------------------------------------------------------------ narrow phones: the bar still fits
    for w in (360, 320):
        P = Page(b, mock, w, 740)
        P.goto("home", 1800)
        r = P.pg.evaluate("() => ({ sw: document.querySelector('.app-header__bar').scrollWidth, cw: document.querySelector('.app-header__bar').clientWidth, page: document.documentElement.scrollWidth - document.documentElement.clientWidth })")
        ok("[%d] the top bar fits with the switcher" % w, r["sw"] <= r["cw"] and r["page"] <= 0, r)
        P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
