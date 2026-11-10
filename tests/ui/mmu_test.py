"""Release 1.85: the multi-material unit (Happy Hare's `mmu` object) on the Home page: no unit, no card; the tool,
gate and filament; the gates with colour, material and state; a gate's tool and selection; load, unload, home, recover;
the commands waiting while the unit is busy.
Usage: mmu_test.py <html> <outdir> <port>"""
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


MMU = {"enabled": True, "num_gates": 4, "tool": 1, "gate": 1, "filament": "Loaded", "action": "Idle",
       "gate_status": [1, 2, 0, -1], "gate_color": ["ff0000", "00ff00", "", "blue"], "gate_material": ["PLA", "PETG", "", "ABS"],
       "ttg_map": [0, 1, 2, 3]}


def open_home(b, w=390, hh=844, **st):
    mock.reset()
    if st:
        mock.set(**st)
    P = Page(b, mock, w, hh)
    CUR[0] = P
    P.goto("home", 2600)
    return P


with sync_playwright() as p:
    b = p.chromium.launch()
    P = open_home(b)
    P.pg.wait_for_timeout(1500)
    ok("no unit: no card", P.pg.locator(".mmu-card").count() == 0)
    P.close()

    for w, hh in ((390, 844), (1440, 900)):
        P = open_home(b, w, hh, mmu=MMU)
        pg = P.pg
        card = pg.locator(".mmu-card")
        wait_until(lambda: card.count() == 1, 8)
        card.scroll_into_view_if_needed()
        ok("%d: the card: T1, gate #1, loaded, ready" % w, wait_until(lambda: card.locator("[data-mmu-tool]").inner_text() == "T1" and card.locator("[data-mmu-gate]").inner_text() == "#1" and "Caricato" in card.inner_text() and "Pronta" in card.inner_text(), 8), card.inner_text() if card.count() else "")
        tiles = card.locator("[data-mmu-gate-tile]")
        ok("%d: four gates with colour, material and state; the current one marked" % w, tiles.count() == 4 and "PETG" in tiles.nth(1).inner_text() and "Nel buffer" in tiles.nth(1).inner_text() and "Vuoto" in tiles.nth(2).inner_text()
           and "is-current" in tiles.nth(1).get_attribute("class") and "is-empty" in tiles.nth(2).get_attribute("class")
           and tiles.nth(0).locator(".mmu-gate__swatch").evaluate("e => getComputedStyle(e).backgroundColor") == "rgb(255, 0, 0)"
           and tiles.nth(3).locator(".mmu-gate__swatch").evaluate("e => getComputedStyle(e).backgroundColor") == "rgb(0, 0, 255)")
        if w == 390:
            tiles.nth(3).click()
            ok("a gate tapped: change to its tool, select it", wait_until(lambda: card.locator("[data-mmu-chosen='3']").count() == 1 and "Passa a T3" in card.locator(".mmu-chosen").inner_text()))
            card.locator(".mmu-chosen button", has_text="Passa a T3").click()
            ok("«Change to T3» sends MMU_CHANGE_TOOL TOOL=3", wait_until(lambda: "MMU_CHANGE_TOOL TOOL=3" in state()["gcode_log"]), state()["gcode_log"][-3:])
            card.locator(".mmu-chosen button", has_text="Seleziona il gate #3").click()
            ok("«Select gate» sends MMU_SELECT GATE=3", wait_until(lambda: "MMU_SELECT GATE=3" in state()["gcode_log"]))
            for cmd, script in (("load", "MMU_LOAD"), ("unload", "MMU_UNLOAD"), ("home", "MMU_HOME"), ("recover", "MMU_RECOVER")):
                card.locator('[data-mmu-cmd="%s"]' % cmd).click()
            ok("load, unload, home, recover", wait_until(lambda: all(s in state()["gcode_log"] for s in ("MMU_LOAD", "MMU_UNLOAD", "MMU_HOME", "MMU_RECOVER"))), state()["gcode_log"][-5:])
            pg.wait_for_timeout(500)
            card.screenshot(path=out + "/mmu_phone.png")
        ok("%d: no horizontal overflow, no page errors" % w, pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth") and not errs(P), errs(P)[:2])
        P.close()

    busy = dict(MMU, action="Loading")
    P = open_home(b, mmu=busy)
    card = P.pg.locator(".mmu-card")
    wait_until(lambda: card.count() == 1, 8)
    ok("busy: what it does, the commands wait (but Recover)", wait_until(lambda: "Loading" in card.locator("[data-mmu-action]").inner_text()) and card.locator('[data-mmu-cmd="load"]').is_disabled() and card.locator('[data-mmu-cmd="recover"]').is_enabled())
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
