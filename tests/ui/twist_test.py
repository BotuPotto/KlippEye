"""Release 1.33.1: (1) after a finished print (file still loaded, 100 %) the print status loads again (it threw, and the
tools waited for it for ever: "Waiting for the printer status"); (2) the axis twist calibration of printers with no
Cartographer: Klipper's own AXIS_TWIST_COMPENSATION_CALIBRATE, with the paper test at each point. Against the mock.
Usage: twist_test.py <html> <outdir> <port>"""
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


def fresh(b, tab="home", w=390, h=844, **st):
    mock.reset()
    mock.set(**st)
    P = Page(b, mock, w, h)
    CUR[0] = P
    P.goto(tab, 2400)
    return P


def open_calibrate(P):
    P.pg.locator("button:has-text('Calibra')").first.click()
    P.pg.wait_for_timeout(400)


with sync_playwright() as p:
    b = p.chromium.launch()

    # ---- a print that has just finished
    P = fresh(b, done_print=True)
    errors = []
    P.pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
    P.pg.wait_for_timeout(2500)
    open_calibrate(P)
    menu = P.pg.locator(".oui-menu")
    ok("after a finished print the tools do not wait for the printer status", "attesa dello stato" not in menu.inner_text().lower() and not P.pg.locator(".oui-menu__item").first.is_disabled(), menu.inner_text())
    ok("... and the print status has no error", not any("print status" in e for e in errors), errors)
    P.pg.keyboard.press("Escape")
    P.close()

    # ---- Klipper's own twist calibration
    P = fresh(b, twist_kind="klipper")
    pg = P.pg
    open_calibrate(P)
    text = pg.locator(".oui-menu").inner_text().lower()
    ok("no Cartographer: 'Axis twist compensation' (Klipper's), only axis X without the Y options", "axis twist compensation" in text and "cartographer" not in text and pg.locator(".oui-menu__item:has-text('Asse X')").count() == 1 and pg.locator(".oui-menu__item:has-text('Asse Y')").count() == 0, text)
    ok("... it says it is the paper test", "prova del foglio" in text)
    pg.screenshot(path=out + "/menu_klipper.png")
    pg.locator(".oui-menu__item:has-text('Asse X')").click()
    sheet = pg.locator(".manual-probe")
    ok("AXIS_TWIST_COMPENSATION_CALIBRATE AXIS=X sent", wait_until(lambda: "AXIS_TWIST_COMPENSATION_CALIBRATE AXIS=X" in gcodes()), gcodes()[-3:])
    ok("the paper-test sheet: point 1 of 3, Z 1.000", wait_until(lambda: "punto 1 di 3" in sheet.inner_text().lower() and "Z 1.000" in sheet.inner_text()), sheet.inner_text() if sheet.count() else "")
    pg.screenshot(path=out + "/paper_test.png")
    sheet.get_by_role("button", name="−0.1", exact=True).click()
    ok("−0.1: TESTZ Z=-0.1, Z 0.900", wait_until(lambda: "TESTZ Z=-0.1" in gcodes() and "Z 0.900" in sheet.inner_text()), sheet.inner_text())
    sheet.get_by_role("button", name="+0.01", exact=True).click()
    ok("+0.01: TESTZ Z=0.01", wait_until(lambda: "TESTZ Z=0.01" in gcodes() and "Z 0.910" in sheet.inner_text()))
    sheet.get_by_role("button", name="Accetta", exact=True).click()
    ok("'Accetta': ACCEPT, Klipper measures, then point 2", wait_until(lambda: "ACCEPT" in gcodes() and "punto 2 di 3" in sheet.inner_text().lower() and "Z 1.000" in sheet.inner_text()), sheet.inner_text())
    wait_until(lambda: not sheet.get_by_role("button", name="Accetta", exact=True).is_disabled())
    sheet.get_by_role("button", name="Accetta", exact=True).click()
    ok("point 3", wait_until(lambda: "punto 3 di 3" in sheet.inner_text().lower() and "Z 1.000" in sheet.inner_text()))
    wait_until(lambda: not sheet.get_by_role("button", name="Accetta", exact=True).is_disabled())
    sheet.get_by_role("button", name="Accetta", exact=True).click()
    ok("after the last point: the sheet closes and SAVE_CONFIG is offered", wait_until(lambda: pg.locator(".manual-probe").count() == 0 and pg.locator(".confirm-card:has-text('Compensazione calcolata')").count() == 1, 8), (gcodes()[-4:], pg.locator(".manual-probe").count(), json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read()).get("mp_points")))
    pg.screenshot(path=out + "/after_last.png")
    pg.locator(".confirm-card").get_by_role("button", name="Più tardi").click()
    P.close()

    P = fresh(b, twist_kind="klipper", twist_y=True)
    open_calibrate(P)
    ok("with the Y options in the config: axis X and axis Y", P.pg.locator(".oui-menu__item:has-text('Asse X')").count() == 1 and P.pg.locator(".oui-menu__item:has-text('Asse Y')").count() == 1)
    P.pg.locator(".oui-menu__item:has-text('Asse Y')").click()
    sheet = P.pg.locator(".manual-probe")
    wait_until(lambda: "Z 1.000" in sheet.inner_text())
    sheet.get_by_role("button", name="Interrompi", exact=True).click()
    ok("'Interrompi': ABORT and the sheet closes", wait_until(lambda: "ABORT" in gcodes() and P.pg.locator(".manual-probe").count() == 0))
    ok("... no SAVE_CONFIG question", P.pg.locator(".confirm-card:has-text('Compensazione calcolata')").count() == 0)
    P.close()

    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
