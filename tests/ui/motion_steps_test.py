"""Release 1.31.0 (roadmap 6b part 2): the Motion card's Z arrows follow the part that moves (the bed or the toolhead,
automatic from Klipper's configuration or chosen in Settings → Motion) and the pad and the Z buttons can have 50 and 100 mm
steps besides 1 and 10. Against the mock.
Usage: motion_steps_test.py <html> <outdir> <port>"""
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
CUR = [None]


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


def gcodes():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/gcode").read())


def wait_until(fn, timeout=6.0, step=0.15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    return bool(fn())


def fresh(b, w=390, h=844, **st):
    mock.reset()
    mock.set(**st)
    P = Page(b, mock, w, h)
    CUR[0] = P
    P.goto("home", 2000)
    return P


def open_motion(P):
    P.pg.click('button[aria-label="Impostazioni"]')
    P.pg.wait_for_selector(".drawer")
    P.settle(500)
    P.pg.click('.set-entry[data-page="motion"]')
    P.settle(700)


def close_menu(P):
    P.pg.click('.drawer button[aria-label="Chiudi"]')
    P.settle(600)


def last_move():
    moves = [g for g in gcodes() if g.startswith("G91")]
    return moves[-1].split("\n")[1] if moves else ""


with sync_playwright() as p:
    b = p.chromium.launch()
    P = fresh(b)
    pg = P.pg
    zc = pg.locator(".z-controls")
    ok("a CoreXY with z_tilt: Z moves the bed (automatic), the column says so", wait_until(lambda: zc.get_attribute("data-z-moves") == "bed") and "piatto" in zc.inner_text(), zc.inner_text())
    ok("... the pad has the usual two rings (1 and 10 mm), the Z column four buttons", pg.locator("[data-jog]").count() == 8 and pg.locator("[data-z]").count() == 4)
    pg.get_by_role("button", name="↑ 10", exact=True).click()
    ok("bed: ↑ 10 brings the bed up, towards the nozzle (Z−10)", wait_until(lambda: last_move().startswith("G1 Z-10")), last_move())
    pg.get_by_role("button", name="↓ 1", exact=True).click()
    ok("bed: ↓ 1 lowers it (Z+1)", wait_until(lambda: last_move().startswith("G1 Z+1 ")), last_move())
    P.ctx.close()

    P = fresh(b, z_kind="toolhead")
    pg = P.pg
    zc = pg.locator(".z-controls")
    ok("a Voron 2.4 (quad_gantry_level): Z moves the toolhead (automatic)", wait_until(lambda: zc.get_attribute("data-z-moves") == "toolhead") and "testina" in zc.inner_text(), zc.inner_text())
    pg.get_by_role("button", name="↑ 10", exact=True).click()
    ok("toolhead: ↑ 10 lifts the toolhead (Z+10)", wait_until(lambda: last_move().startswith("G1 Z+10")), last_move())

    # --- Settings → Motion
    open_motion(P)
    body = pg.locator(".drawer__body").inner_text()
    ok("Settings → Motion: what Z moves (automatic: the toolhead, from Klipper) and the steps", "Dalla configurazione di Klipper: la testina." in body and "passi del cerchio x / y" in body.lower() and "passi dei tasti z" in body.lower(), body[:700])
    pg.locator(".set-choice", has_text="Il piatto").click()
    P.settle(400)
    pg.locator(".set-group", has_text="Passi del cerchio X / Y").locator(".set-switch", has_text="± 50 mm").click()
    pg.locator(".set-group", has_text="Passi del cerchio X / Y").locator(".set-switch", has_text="± 100 mm").click()
    pg.locator(".set-group", has_text="Passi dei tasti Z").locator(".set-switch", has_text="± 50 mm").click()
    P.settle(400)
    ok("... 1 and 10 mm are always on (not switchable)", pg.locator(".set-group", has_text="Passi del cerchio X / Y").locator(".set-switch", has_text="± 1 mm").first.is_disabled())
    entry_line = None
    pg.click('.drawer button[aria-label="Indietro"]')
    P.settle(500)
    entry_line = pg.locator('.set-entry[data-page="motion"]').inner_text()
    ok("the menu line says it: bed, XY 1·10·50·100, Z 1·10·50", "Z muove il piatto" in entry_line and "XY 1·10·50·100" in entry_line and "Z 1·10·50 mm" in entry_line, entry_line)
    close_menu(P)
    ok("chosen by hand: the bed (even if Klipper says toolhead)", wait_until(lambda: zc.get_attribute("data-z-moves") == "bed"))
    ok("the pad has four rings now (16 parts), the Z column six buttons, smaller", pg.locator("[data-jog]").count() == 16 and pg.locator("[data-z]").count() == 6 and pg.locator(".z-btn--compact").count() == 6)
    labels = pg.evaluate("() => [...document.querySelectorAll('.jog-pad .bambu-num')].map(t => t.textContent)")
    ok("... each ring has its step written on it", sorted(labels) == sorted(["+1", "-1", "+10", "-10", "+50", "-50", "+100", "-100"]), labels)
    pg.locator('[data-jog="X+100"]').dispatch_event("click")
    ok("the outer ring moves 100 mm", wait_until(lambda: last_move().startswith("G1 X+100")), last_move())
    pg.locator('[data-jog="Y-50"]').dispatch_event("click")
    ok("the third ring 50 mm", wait_until(lambda: last_move().startswith("G1 Y-50")), last_move())
    pg.get_by_role("button", name="↑ 50", exact=True).click()
    ok("Z ↑ 50 with the bed: Z−50", wait_until(lambda: last_move().startswith("G1 Z-50")), last_move())
    pg.locator(".movement-actions").scroll_into_view_if_needed()
    pg.locator(".jog-pad").screenshot(path=os.path.join(out, "01_pad4.png"))
    pg.screenshot(path=os.path.join(out, "02_card.png"), full_page=True)
    ok("no JavaScript error", P.errors == [], P.errors)
    P.ctx.close()

    P = fresh(b, w=360, h=740)
    P.pg.evaluate("""async () => { const r = await fetch('/server/database/item?namespace=klippeye&key=settings'); }""")
    ok("360 px: no horizontal scrolling with the usual pad", P.pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0)
    P.ctx.close()
    b.close()

print("FAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
