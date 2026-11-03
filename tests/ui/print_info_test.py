"""Release 1.30.0 (roadmap 6b part 1): the print card shows more, like Mainsail (when it ends, speed, volumetric flow, the
estimates one by one, filament, height, the factors) and offers «Exclude an object» (Klipper's exclude_object) with a map.
Against the mock (print 42%, 1260 s, filament 3.2 of 4.2 m, slicer 7260 s, speed factor 110%, flow factor 95%).
Usage: print_info_test.py <html> <outdir> <port>"""
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
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:700]) if (extra != "" and not cond) else ""), flush=True)


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def wait_until(fn, timeout=6.0, step=0.15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    try:
        return bool(fn())
    except Exception:
        return False


def square(name, x, y, size=30):
    return {"name": name, "center": [x, y], "polygon": [[x - size / 2, y - size / 2], [x + size / 2, y - size / 2], [x + size / 2, y + size / 2], [x - size / 2, y + size / 2]]}


OBJECTS = [square("BENCHY_A", 100, 100), square("BENCHY_B", 220, 120), square("CUBE_C", 170, 250, 40)]


def fresh(b, w=390, h=844, **st):
    mock.reset()
    mock.set(printing=True, **st)
    P = Page(b, mock, w, h)
    CUR[0] = P
    P.goto("home", 2600)
    return P


with sync_playwright() as p:
    b = p.chromium.launch()
    P = fresh(b, print_objects=OBJECTS)
    pg = P.pg
    live = pg.locator("[data-print-live]")
    ok("the print card has a second row: ends at, speed, flow", wait_until(lambda: live.count() == 1 and "Fine alle" in live.inner_text() and "87 mm/s" in live.inner_text()), live.inner_text() if live.count() else "")
    ok("... the volumetric flow from the extruder's speed and the filament (2.6 mm/s of 1.75 mm: 6.3 mm³/s)", "6,3 mm³/s" in live.inner_text(), live.inner_text())
    eta = live.locator(".print-stat__value").first.inner_text()
    ok("... 'ends at' is a clock time", len(eta) >= 5 and eta[-3] == ":", eta)
    details = pg.locator("[data-print-details]")
    ok("'Più dettagli' is folded", details.count() == 1 and details.get_attribute("open") is None)
    details.locator("summary").click()
    P.settle(300)
    text = details.inner_text()
    ok("... the estimates one by one: file 29:00, filament 06:33, slicer 1h 40m", "Rimanente secondo il file\n29:00" in text and "Rimanente secondo il filamento\n06:33" in text and "Rimanente secondo lo slicer\n1h 40m" in text, text)
    ok("... the slicer's whole estimate and the total time with pauses", "Stima dello slicer (stampa intera)\n2h 1m" in text and "Tempo totale (con le pause)\n21:40" in text, text)
    ok("... filament used of total, in m and g", "3,2 / 4,2 m • 9 / 12 g" in text, text)
    ok("... height now of the object's", "15,3 / 48 mm" in text, text)
    ok("... speed now / requested (100 mm/s × 110%) and the two factors", "87 / 110 mm/s" in text and "Fattore di velocità\n110%" in text and "Fattore di flusso\n95%" in text, text)
    pg.screenshot(path=os.path.join(out, "01_card.png"), full_page=True)

    # --- exclude an object
    btn = pg.locator("[data-exclude-open]")
    ok("«Escludi un oggetto (3 di 3 in stampa)»", btn.count() == 1 and "3 di 3 in stampa" in btn.inner_text(), btn.inner_text() if btn.count() else "")
    btn.click()
    P.settle(500)
    dlg = pg.locator("[data-exclude-dialog]")
    ok("... a map of the bed with the 3 objects, and their list (the one printing now marked)", dlg.count() == 1 and dlg.locator("polygon[data-object]").count() == 3 and dlg.locator(".exclude-map__object.is-current").count() == 1
       and "in stampa ora" in dlg.locator('[data-object-row="BENCHY_A"]').inner_text(), dlg.inner_text() if dlg.count() else "")
    ok("... nothing chosen: the button says to choose", pg.locator("[data-exclude-confirm]").is_disabled() and "Scegli un oggetto" in pg.locator("[data-exclude-confirm]").inner_text())
    dlg.locator('polygon[data-object="BENCHY_B"]').click()
    ok("tapping an object on the map chooses it, and asks to confirm", "Escludere «BENCHY_B»?" in dlg.inner_text() and dlg.locator(".exclude-map__object.is-chosen").count() == 1 and not pg.locator("[data-exclude-confirm]").is_disabled(), dlg.inner_text())
    pg.screenshot(path=os.path.join(out, "02_exclude.png"))
    pg.evaluate("() => window.klippeyeBack()")
    P.settle(300)
    ok("the phone's back first forgets the choice, the dialog stays", dlg.count() == 1 and "Escludere" not in dlg.inner_text())
    dlg.locator('[data-object-row="BENCHY_B"]').click()
    pg.click("[data-exclude-confirm]")
    ok("«Escludilo»: EXCLUDE_OBJECT NAME=BENCHY_B sent, the dialog closes", wait_until(lambda: "EXCLUDE_OBJECT NAME=BENCHY_B" in state()["gcode_log"]) and wait_until(lambda: dlg.count() == 0), state()["gcode_log"][-3:])
    ok("... and the button says 2 of 3", wait_until(lambda: "2 di 3 in stampa" in btn.inner_text(), 6), btn.inner_text())
    btn.click()
    P.settle(400)
    ok("... reopened: BENCHY_B is excluded, grey and not choosable", dlg.locator('[data-object-row="BENCHY_B"]').is_disabled() and "escluso" in dlg.locator('[data-object-row="BENCHY_B"]').inner_text()
       and dlg.locator('polygon[data-object="BENCHY_B"].is-excluded').count() == 1)
    pg.evaluate("() => window.klippeyeBack()")
    P.settle(300)
    ok("... the back closes it", dlg.count() == 0)
    ok("no horizontal scrolling (390 px)", pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0)
    ok("no JavaScript error", P.errors == [], P.errors)
    P.ctx.close()

    P = fresh(b, w=360, h=740, print_objects=OBJECTS[:1])
    ok("one object only: no «Escludi un oggetto»", wait_until(lambda: P.pg.locator("[data-print-live]").count() == 1) and P.pg.locator("[data-exclude-open]").count() == 0)
    ok("360 px: no horizontal scrolling", P.pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0)
    P.ctx.close()

    P = fresh(b, w=1440, h=900, print_objects=OBJECTS)
    ok("desktop: the same row and details in the print card", wait_until(lambda: P.pg.locator(".desk-print [data-print-live]").count() == 1) and P.pg.locator(".desk-print [data-print-details]").count() == 1
       and P.pg.locator(".desk-print [data-exclude-open]").count() == 1)
    P.pg.screenshot(path=os.path.join(out, "03_desktop.png"))
    ok("no JavaScript error (desktop)", P.errors == [], P.errors)
    P.ctx.close()

    # --- 1.30.1: on a computer the console bar must not cover the AI alarm's answers
    P = fresh(b, w=1366, h=720, print_objects=OBJECTS, detector_status="scanning", has_analysis=True, analysis_action="PAUSA")
    pg = P.pg
    ok("desktop, low screen: the AI alarm question is in the print card", wait_until(lambda: pg.locator("[data-ai-question] [data-ai-answer]").count() == 3, 8))
    pg.locator(".desk-print [data-print-details] summary").click()
    P.settle(300)
    cover = []
    for k in range(3):
        btn = pg.locator("[data-ai-question] [data-ai-answer]").nth(k)
        btn.scroll_into_view_if_needed()
        P.settle(200)
        cover.append(pg.evaluate("""(b) => { const r = b.getBoundingClientRect(); const dock = document.querySelector('.desk-dock').getBoundingClientRect();
            const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return { hit: b.contains(top), below: r.bottom <= dock.top + 1 }; }""", btn.element_handle()))
    ok("... each answer can be pressed: not under the console bar (the column scrolls)", all(c["hit"] and c["below"] for c in cover), cover)
    pg.screenshot(path=os.path.join(out, "04_desktop_alarm.png"))
    ok("no JavaScript error (desktop, alarm)", P.errors == [], P.errors)
    P.ctx.close()
    b.close()

print("FAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
