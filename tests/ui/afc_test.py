"""Release 1.91: the multi-material card with AFC (the `AFC` object and its lanes, `AFC_stepper <lane>` or
`AFC_lane <lane>`): no AFC, no card; the lane in the toolhead, its tool and material; the unit with its lanes (colour,
tool, material, weight, state); a lane tapped: load it into the toolhead, eject it; unload the toolhead; an error:
AFC's message, «Clear the error»; busy: the commands wait.
Usage: afc_test.py <html> <outdir> <port>"""
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


def gcodes():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())["gcode_log"]


AFC = {"current_load": "lane2", "current_lane": None, "next_lane": None, "current_state": "Idle", "error_state": False, "bypass_state": False,
       "units": ["Box_Turtle Turtle_1"], "lanes": ["lane1", "lane2", "lane3", "lane4"], "extruders": ["extruder"], "hubs": ["Turtle_1"],
       "buffers": [], "message": {"message": "", "type": ""}}


def lane(name, index, color, material, weight, load, prep, status, tool=False):
    return {"name": name, "unit": "Turtle_1", "hub": "Turtle_1", "extruder": "extruder", "lane": index, "map": "T%d" % (index - 1), "load": load, "prep": prep,
            "tool_loaded": tool, "material": material, "color": color, "weight": weight, "spool_id": None, "filament_status": status, "status": "None"}


LANES = {"lane1": lane("lane1", 1, "#ff0000", "PLA", 812.4, True, True, "Ready"),
         "lane2": lane("lane2", 2, "#00ff00", "PETG", 640, True, True, "Tooled", tool=True),
         "lane3": lane("lane3", 3, "", "", 0, False, False, "Not Ready"),
         "lane4": lane("lane4", 4, "#0000ff", "ABS", 0, False, True, "Prep")}


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
    ok("no AFC: no card", P.pg.locator(".mmu-card").count() == 0)
    P.close()

    for w, hh in ((390, 844), (1440, 900)):
        P = open_home(b, w, hh, afc=AFC, afc_lanes=LANES)
        pg = P.pg
        card = pg.locator(".afc-card")
        wait_until(lambda: card.count() == 1, 8)
        card.scroll_into_view_if_needed()
        ok("%d: the card: T1, lane2 in the toolhead, PETG, ready" % w, wait_until(lambda: card.locator("[data-afc-tool]").inner_text() == "T1" and card.locator("[data-afc-current]").inner_text() == "lane2" and "PETG" in card.locator(".mmu-now").inner_text() and card.locator("[data-afc-state]").inner_text() == "Pronta", 8), card.inner_text() if card.count() else "")
        tiles = card.locator("[data-afc-lane]")
        ok("%d: the unit and its four lanes (also an AFC_lane one), with colour, tool, material, weight and state" % w, wait_until(lambda: tiles.count() == 4) and "Turtle_1" in card.locator("[data-afc-unit]").inner_text() and "Box Turtle" in card.locator("[data-afc-unit]").inner_text()
           and "lane1 · T0" in tiles.nth(0).inner_text() and "PLA · 812 g" in tiles.nth(0).inner_text() and tiles.nth(0).get_attribute("data-afc-lane-state") == "ready"
           and tiles.nth(1).get_attribute("data-afc-lane-state") == "tool" and "is-current" in tiles.nth(1).get_attribute("class")
           and tiles.nth(2).get_attribute("data-afc-lane-state") == "empty" and "is-empty" in tiles.nth(2).get_attribute("class")
           and tiles.nth(3).get_attribute("data-afc-lane-state") == "partial" and "ABS" in tiles.nth(3).inner_text()
           and tiles.nth(0).locator(".mmu-gate__swatch").evaluate("e => getComputedStyle(e).backgroundColor") == "rgb(255, 0, 0)",
           [tiles.nth(i).inner_text() for i in range(tiles.count())])
        if w == 390:
            tiles.nth(0).click()
            ok("a lane tapped: load it into the toolhead, eject it", wait_until(lambda: card.locator("[data-afc-chosen='lane1']").count() == 1 and "Carica lane1 nella testina" in card.locator(".mmu-chosen").inner_text()))
            card.locator('[data-afc-cmd="load"]').click()
            card.locator('[data-afc-cmd="eject"]').click()
            ok("«Load» sends CHANGE_TOOL LANE=lane1, «Eject» LANE_UNLOAD LANE=lane1", wait_until(lambda: "CHANGE_TOOL LANE=lane1" in gcodes() and "LANE_UNLOAD LANE=lane1" in gcodes()), gcodes()[-3:])
            tiles.nth(1).click()
            ok("the lane in the toolhead: no load or eject, said so", wait_until(lambda: card.locator("[data-afc-chosen='lane2']").count() == 1 and card.locator('[data-afc-cmd="load"]').count() == 0 and "Scarica la testina" in card.locator(".mmu-chosen").inner_text()))
            card.locator('[data-afc-cmd="unload"]').click()
            ok("«Unload the toolhead» sends TOOL_UNLOAD", wait_until(lambda: "TOOL_UNLOAD" in gcodes()))
            ok("no error: no «Clear the error»", card.locator('[data-afc-cmd="reset"]').count() == 0)
            pg.wait_for_timeout(400)
            card.screenshot(path=out + "/afc_phone.png")
        ok("%d: no horizontal overflow, no page errors" % w, pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth") and not errs(P), errs(P)[:2])
        P.close()

    # an error: AFC's message and «Clear the error»; busy: the commands wait
    P = open_home(b, afc=dict(AFC, error_state=True, current_state="Error", message={"message": "lane1 failed to load: hub not triggered", "type": "error"}), afc_lanes=LANES)
    card = P.pg.locator(".afc-card")
    wait_until(lambda: card.count() == 1, 8)
    card.scroll_into_view_if_needed()
    ok("error: the badge, AFC's message", wait_until(lambda: card.locator('[data-afc-state="error"]').count() == 1 and "hub not triggered" in card.locator('[data-afc-message="error"]').inner_text(), 8), card.inner_text() if card.count() else "")
    card.locator('[data-afc-cmd="reset"]').click()
    ok("«Clear the error» sends RESET_FAILURE; the toolhead commands wait", wait_until(lambda: "RESET_FAILURE" in gcodes()) and card.locator('[data-afc-cmd="unload"]').is_disabled(), gcodes()[-3:])
    P.close()
    P = open_home(b, afc=dict(AFC, current_state="Loading"), afc_lanes=LANES)
    card = P.pg.locator(".afc-card")
    wait_until(lambda: card.count() == 1, 8)
    card.scroll_into_view_if_needed()
    card.locator('[data-afc-lane="lane1"]').click()
    ok("busy: what it does, load and unload wait", wait_until(lambda: "Loading" in card.locator("[data-afc-state]").inner_text()) and card.locator('[data-afc-cmd="load"]').is_disabled() and card.locator('[data-afc-cmd="unload"]').is_disabled())
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
