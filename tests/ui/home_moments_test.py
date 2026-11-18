"""1.134: Home follows the moment of the print, cards move instead of jumping, dialogs grow from the tap, the camera
goes into a small window. Usage: home_moments_test.py <html> <outdir> <port>"""
import sys, os
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
FAILS = []


def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:400]) if (extra != "" and not cond) else ""))


def start(b, **st):
    mock.reset()
    if st: mock.set(**st)
    P = Page(b, mock, 390, 844)
    P.goto("home", 2600)
    return P


SLOTS = "() => [...document.querySelectorAll('[data-slot]')].map(e => e.dataset.slot)"

with sync_playwright() as p:
    b = p.chromium.launch()

    P = start(b)
    idle = P.pg.evaluate(SLOTS)
    ok("1.134: idle Home keeps the spool and the movement", "spool" in idle and "movement" in idle and "camera" in idle, idle)
    # 1.134.1: a card folds and opens with a height motion, its content shown while it folds
    card = P.pg.locator("[data-slot=temps] .oui-card").first
    full = card.bounding_box()["height"]
    card.locator(".oui-card__fold").click()
    P.pg.wait_for_timeout(60)
    mid = P.pg.evaluate("() => { const c = document.querySelector('[data-slot=temps] .oui-card'); return { folding: c.classList.contains('is-folding'), anims: c.getAnimations().length, h: c.offsetHeight }; }")
    P.settle(700)
    folded = card.bounding_box()["height"]
    ok("1.134.1: folding a card moves its height, content still shown meanwhile", mid["folding"] and mid["anims"] == 1 and folded < full / 2, (mid, full, folded))
    card.locator(".oui-card__fold").click(); P.settle(900)
    ok("... it opens back to its height", abs(card.bounding_box()["height"] - full) < 2 and "is-folding" not in (card.get_attribute("class") or ""), (full, card.bounding_box()["height"]))
    # the side menu arrives with the spring
    P.pg.locator(".header-btn--menu").click()
    P.pg.wait_for_selector(".drawer")
    ok("... the side menu comes in with the spring", "linear(" in P.pg.evaluate("() => getComputedStyle(document.querySelector('.drawer')).animationTimingFunction"))
    P.close()

    P = start(b, printing=True)
    printing = P.pg.evaluate(SLOTS)
    ok("... printing: the spool steps aside, print card first", "spool" not in printing and printing[:2] == ["print", "camera"], printing)
    # a dialog grows out of the tile that was tapped
    tile = P.pg.locator("[data-slot=heaters] .heater-tiles > *").first
    tile.click()
    P.pg.wait_for_selector(".modal-card, .sheet-card, .confirm-card")
    origin = P.pg.evaluate("() => document.querySelector('.modal-card, .sheet-card, .confirm-card').style.transformOrigin")
    ok("... a dialog grows from the tap", origin.endswith("px") and origin != "", origin)
    P.pg.locator(".modal").click(position={"x": 8, "y": 8}); P.settle(600)
    # the camera into a small window, which stays on another page and brings it back
    P.pg.locator(".camera-mini-open").click(); P.settle(800)
    ok("... small window: the camera card leaves Home", P.pg.locator(".camera-mini").count() == 1 and "camera" not in P.pg.evaluate(SLOTS))
    P.pg.locator("[data-tab=files]").click(); P.settle(800)
    ok("... small window: still there on another page", P.pg.locator(".camera-mini").is_visible())
    P.pg.locator(".camera-mini").click(); P.settle(900)
    ok("... small window: a tap goes back to Home with the camera card", P.pg.locator(".camera-mini").count() == 0 and "camera" in P.pg.evaluate(SLOTS))
    P.shot(f"{out}/printing.png", tall=False)
    P.close()

    P = start(b, printing=True, detector_status="scanning", has_analysis=True, analysis_action="PAUSA")
    P.settle(4500)  # the AI monitor is read every 4 s
    alarm = P.pg.evaluate(SLOTS)
    ok("... alarm: the camera goes on top, the rest steps back", alarm[0] == "camera" and P.pg.locator("[data-slot=temps].home-dim").count() == 1, alarm)
    ok("... alarm: the print card stays bright", P.pg.locator("[data-slot=print].home-dim").count() == 0)
    ok("... alarm: the AI badge hops", P.pg.locator(".ai-header-badge--alarm").count() == 1)
    P.shot(f"{out}/alarm.png", tall=False)
    P.close()
    b.close()

print("FAILED: " + ", ".join(FAILS) if FAILS else "all passed")
sys.exit(1 if FAILS else 0)
