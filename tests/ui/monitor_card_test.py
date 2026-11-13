"""Release 1.124: the AI monitoring panel shows the local model next to OpenCV: each with its last score and the highest of
the print; «Try the local model now» rates the camera's picture; a note while the local model's doubt makes OpenCV
readier; without a model it says «none» and offers no test. Phone and 320 px. Against the mock.
Usage: monitor_card_test.py <html> <outdir> <port>"""
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


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


MODEL = {"available": True, "source": "base", "version": "20261112-1614", "threshold": 0.3, "size": 224, "last": {"score": 18.0, "checks": 40}}


def panel(b, w=390, h=844, **st):
    mock.reset()
    mock.set(**st)
    P = Page(b, mock, w, h)
    P.goto("home", 1500)
    P.pg.locator("[data-ai-badge]").first.click()
    P.settle(900)
    return P


def wait_until(fn, seconds=6):
    end = time.time() + seconds
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(0.15)
    return False


def tile(P, name):
    return P.pg.locator('[data-tile="%s"]' % name).inner_text()


with sync_playwright() as p:
    b = p.chromium.launch()

    P = panel(b, local_model=MODEL, printing=True, detector_status="scanning (whole bed, outside the parts)",
              detector_extra={"peak_score": 3.4, "local": {"score": 18.0, "peak": 41.5, "best": "part"}, "boost": False})
    ok("the local model's tile: its last score and the highest of the print", "Modello locale" in tile(P, "local") and "18%" in tile(P, "local") and "41,5%" in tile(P, "local"), tile(P, "local"))
    ok("OpenCV's tile: a change score, and the highest (the last one goes back to 0 once a change stays)", "Cambiamenti (OpenCV)" in tile(P, "opencv")
       and "12%" in tile(P, "opencv") and "3,4%" in tile(P, "opencv"), tile(P, "opencv"))
    ok("no doubt now: no note about OpenCV being readier", P.pg.locator("[data-boost]").count() == 0)
    P.pg.locator("[data-local-test]").click()
    ok("«Try the local model now»: asked, the score and the verdict, with the views it looked at",
       wait_until(lambda: P.pg.locator("[data-local-try]").count() == 1) and state().get("local_tests") == 1
       and "62,5%" in P.pg.locator("[data-local-try]").inner_text() and "in dubbio" in P.pg.locator("[data-local-try]").inner_text()
       and "foto intera 18%" in P.pg.locator("[data-local-try]").inner_text(), P.pg.locator(".monitor-try").inner_text())
    P.shot(os.path.join(out, "monitor_card_390.png"), tall=False)
    P.close()

    P = panel(b, local_model=MODEL, printing=True, detector_status="scanning (whole bed, outside the parts)",
              detector_extra={"local": {"score": 52.0, "peak": 52.0}, "boost": True}, local_test_result={"score": 91.0, "views": {"whole": 91.0}, "best": "whole", "doubt": 35, "sure": 80})
    ok("the local model in doubt: a note that OpenCV raises an alarm sooner", P.pg.locator("[data-boost]").count() == 1 and "OpenCV" in P.pg.locator("[data-boost]").inner_text())
    P.pg.locator("[data-local-test]").click()
    ok("... a sure score is marked as such", wait_until(lambda: P.pg.locator("[data-local-try].is-sure").count() == 1) and "sicuro" in P.pg.locator("[data-local-try]").inner_text())
    P.close()

    P = panel(b, printing=True, detector_status="scanning")
    ok("no local model: «none», no test button", "nessun" in tile(P, "local").lower() and P.pg.locator("[data-local-test]").count() == 0, tile(P, "local"))
    P.close()

    P = panel(b, 320, 700, local_model=MODEL, printing=True, detector_status="scanning (whole bed, outside the parts)",
              detector_extra={"peak_score": 13.25, "local": {"score": 100.0, "peak": 100.0}})
    wide = P.pg.evaluate("() => { const g = document.querySelector('.monitor-grid').getBoundingClientRect(); return [...document.querySelectorAll('.monitor-grid *, .monitor-try *')].filter(e => { const r = e.getBoundingClientRect(); return r.width && (r.right > g.right + 1 || r.left < g.left - 1); }).map(e => e.className).slice(0, 4); }")
    ok("320 px: nothing out of the tiles", not wide, wide)
    P.shot(os.path.join(out, "monitor_card_320.png"), tall=False)
    P.close()
    b.close()

print("%d FAIL" % len(FAILS))
sys.exit(1 if FAILS else 0)
