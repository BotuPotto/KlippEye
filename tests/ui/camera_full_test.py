"""Release 1.35.0 (roadmap 6b part 6): the camera in full screen, turned to fit the screen. A phone held upright that does
not turn (a browser that cannot lock landscape, an iPhone) gets the picture turned 90°; the turn button switches that off;
the KlippEye app (1.5.0, KlippEyeApp/8) is asked to hide Android's bars and turn the screen itself. Against the mock.
Usage: camera_full_test.py <html> <outdir> <port>"""
import json
import os
import sys
import time
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit
atexit.register(mock.stop)
FAILS = []
CUR = [None]

APP8 = """(() => { const ua = navigator.userAgent + ' KlippEyeApp/8'; Object.defineProperty(navigator, 'userAgent', { get: () => ua });
  window.__fs = [];
  window.KlippEyeApp = { setFullscreen: (on, landscape) => window.__fs.push([on, landscape]), appInfo: () => JSON.stringify({ version: '1.5.0', code: 10500, canInstall: true }),
    notifyState: () => JSON.stringify({ permission: true, battery: true, receive: false, chosen: true, mode: '', connected: false, lastMessageAt: 0 }), notifySetup: () => '{}' }; })();"""


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
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    return bool(fn())


def fresh(b, w=390, h=844, script=None, **st):
    mock.reset()
    mock.set(**st)
    P = Page(b, mock, w, h)
    if script:
        P.ctx.add_init_script(script)
    CUR[0] = P
    P.goto("home", 2200)
    return P


def full(P):
    return P.pg.locator(".camera-full")


with sync_playwright() as p:
    b = p.chromium.launch()

    # ---- a phone's browser, held upright
    P = fresh(b)
    pg = P.pg
    btn = pg.locator(".camera-full-open").first
    ok("the camera card has a full-screen button", btn.count() == 1 and btn.get_attribute("aria-label") == "Schermo intero")
    btn.click()
    ok("it opens the camera over the whole screen", wait_until(lambda: full(P).count() == 1) and full(P).bounding_box()["width"] >= 389 and full(P).bounding_box()["height"] >= 843)
    ok("the screen stays upright: the picture is turned 90°", wait_until(lambda: full(P).get_attribute("data-rotated") == "true"))
    box = pg.locator(".camera-full__stage").bounding_box()
    ok("... and fills the screen turned (its long side along the screen's height)", box["height"] > box["width"] and box["height"] >= 840, box)
    pg.screenshot(path=out + "/phone_turned.png")
    pg.get_by_role("button", name="Non girare l'immagine").click()
    ok("the turn button puts it back upright", wait_until(lambda: full(P).get_attribute("data-rotated") == "false"))
    pg.screenshot(path=out + "/phone_upright.png")
    pg.wait_for_timeout(4200)
    ok("the buttons fade after a while", "is-shown" not in pg.locator(".camera-full__controls").get_attribute("class"))
    pg.mouse.click(195, 400)
    ok("... and come back with a tap", wait_until(lambda: "is-shown" in pg.locator(".camera-full__controls").get_attribute("class")))
    pg.locator('.camera-full button[aria-label="Esci da schermo intero"]').click()
    ok("'Esci da schermo intero' closes it", wait_until(lambda: full(P).count() == 0))
    ok("... and the card shows the camera again", wait_until(lambda: pg.locator(".camera-frame .camera-frame__video").count() == 1))
    btn.click()
    wait_until(lambda: full(P).count() == 1)
    ok("the phone's back closes it (app back button)", pg.evaluate("() => window.klippeyeBack && window.klippeyeBack()") and wait_until(lambda: full(P).count() == 0))
    P.close()

    # ---- held sideways: nothing to turn
    P = fresh(b, w=844, h=390)
    P.pg.locator(".camera-full-open").first.click()
    ok("a landscape screen: the picture is not turned, no turn button", wait_until(lambda: full(P).count() == 1) and full(P).get_attribute("data-rotated") == "false" and P.pg.locator('.camera-full button[aria-label*="immagine"]').count() == 0)
    P.pg.screenshot(path=out + "/landscape.png")
    P.close()

    # ---- the KlippEye app
    P = fresh(b, script=APP8)
    P.pg.locator(".camera-full-open").first.click()
    ok("in the app 1.5.0: Android is asked for full screen and landscape", wait_until(lambda: P.pg.evaluate("window.__fs") == [[True, True]]), P.pg.evaluate("window.__fs"))
    P.pg.locator('.camera-full button[aria-label="Esci da schermo intero"]').click()
    ok("... and given its screen back on leaving", wait_until(lambda: P.pg.evaluate("window.__fs") == [[True, True], [False, False]]), P.pg.evaluate("window.__fs"))
    P.close()

    # ---- a computer
    P = fresh(b, w=1440, h=900)
    P.pg.locator(".desk-camera .camera-full-open").click()
    ok("desktop: the camera panel's button opens the full screen", wait_until(lambda: full(P).count() == 1 and full(P).bounding_box()["width"] >= 1439))
    P.pg.keyboard.press("Escape")
    ok("... Escape leaves it", wait_until(lambda: full(P).count() == 0))
    P.close()

    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
