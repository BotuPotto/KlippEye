"""Release 1.112: the temperature window has the usual materials (PLA, PETG, ABS, ASA, TPU: the nozzle and the bed with
one tap) and «Off» for the heater it was opened for; 360 px. Against the mock.
Usage: temp_presets_test.py <html> <outdir> <port>"""
import json
import os
import sys
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


def gcodes():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/gcode").read())


with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    P = Page(b, mock, 360, 780)
    P.goto("home", 1600)
    P.pg.locator(".heater-tile--hotend, .heater-tile").first.click()
    P.settle(500)
    chips = P.pg.locator("[data-temp-preset]")
    ok("the window has the materials and «Spegni»", [chips.nth(i).get_attribute("data-temp-preset") for i in range(chips.count())] == ["PLA", "PETG", "ABS", "ASA", "TPU", "off"]
       and "210° / 60°" in P.pg.locator('[data-temp-preset="PLA"]').inner_text() and "Spegni" in P.pg.locator('[data-temp-preset="off"]').inner_text())
    wide = P.pg.evaluate("() => { const c = document.querySelector('.modal-card'); return c.scrollWidth - c.clientWidth; }")
    ok("... they fit at 360 px", wide <= 0, wide)
    P.shot_vp(os.path.join(out, "temp_presets.png"), 780)
    P.pg.locator('[data-temp-preset="PETG"]').click()
    P.settle(600)
    sent = gcodes()
    ok("PETG: the nozzle at 240 and the bed at 80 together, the window closed",
       any("M104 S240" in g and "M140 S80" in g for g in sent) and P.pg.locator(".modal-card").count() == 0, sent[-3:])
    tiles = P.pg.locator(".heater-tile")
    tiles.nth(tiles.count() - 1).click()
    P.settle(500)
    P.pg.locator('[data-temp-preset="off"]').click()
    P.settle(600)
    ok("«Spegni» from the bed's window: the bed only, to 0", "M140 S0" in gcodes()[-1] and "M104" not in gcodes()[-1], gcodes()[-2:])
    P.close()
    b.close()

print("%d FAIL" % len(FAILS))
sys.exit(1 if FAILS else 0)
