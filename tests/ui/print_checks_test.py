"""Release 1.83: the checks before a print, in the «Confirm print» dialog: a file that suits the printer says so; one
taller than the printer, sliced for another nozzle, with thick layers, hotter than the printer allows, with SAVE_CONFIG
waiting, says each of them (and can still be started).
Usage: print_checks_test.py <html> <outdir> <port>"""
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


CUR = [None]


def wait_until(fn, timeout=6.0, step=0.15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    return False


def errs(P):
    return [e for e in P.errors if "pageerror" in e or "console.error" in e]


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())




def gcodes():
    return state()["gcode_log"]


def open_confirm(b, w=390, hh=844, **st):
    mock.reset()
    if st:
        mock.set(**st)
    P = Page(b, mock, w, hh)
    CUR[0] = P
    P.goto("files", 2400)
    P.pg.locator(".file-card", has_text="Benchy").locator('button[aria-label="Avvia stampa"]').first.click()
    return P


with sync_playwright() as p:
    b = p.chromium.launch()
    P = open_confirm(b)
    checks = P.pg.locator(".confirm-card .print-checks")
    ok("a file that suits the printer: one line says it was checked", wait_until(lambda: checks.count() == 1 and checks.get_attribute("data-print-checks") == "ok" and "Controllato" in checks.inner_text(), 8), checks.inner_text() if checks.count() else "")
    ok("no page errors", not errs(P), errs(P)[:2])
    P.close()

    bad = {"object_height": 320.0, "nozzle_diameter": 0.6, "layer_height": 0.4, "first_layer_extr_temp": 300.0, "first_layer_bed_temp": 120.0}
    for w, hh in ((390, 844), (320, 640)):
        P = open_confirm(b, w, hh, meta_extra=bad, pending={"bed_mesh default": {"version": "1"}})
        checks = P.pg.locator(".confirm-card .print-checks")
        want = ["height", "nozzle", "layer", "hotend", "bed", "pending"]
        ok("%d: every problem said: taller than Z, another nozzle, thick layers, too hot, SAVE_CONFIG waiting" % w, wait_until(lambda: checks.count() == 1 and checks.get_attribute("data-print-checks").split(",") == want, 8), checks.get_attribute("data-print-checks") if checks.count() else "")
        text = checks.inner_text() if checks.count() else ""
        ok("%d: in words, with the figures" % w, all(s in text for s in ("320 mm", "300 mm", "0,6 mm", "0,4 mm", "300°", "285°", "120°", "110°", "SAVE_CONFIG")), text)
        ok("%d: the print can still be started" % w, P.pg.locator(".confirm-card .oui-btn--primary").is_enabled())
        if w == 390:
            P.pg.wait_for_timeout(800)
            P.pg.screenshot(path=out + "/checks_phone.png")
        ok("%d: no horizontal overflow, no page errors" % w, P.pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth") and not errs(P), errs(P)[:2])
        P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
