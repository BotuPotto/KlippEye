"""Release 1.48.0 (roadmap 6d part 7): more cameras. Besides the settings' camera, the webcams set up in Mainsail /
Fluidd (Moonraker's /server/webcams/list) that the dashboard can show: a menu on the camera card, on the computer's camera
panel and in the full screen follows it; the same camera twice and the kinds it cannot show are left out; the choice is
kept on this device; one camera only: no menu. Against the mock.
Usage: cameras_test.py <html> <outdir> <port>"""
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


def media(P, scope=""):
    return P.pg.evaluate("(s) => { const e = document.querySelector(s + ' .camera-frame__video, ' + s + ' .desk-camera__video'); return e ? [e.tagName, e.getAttribute('src') || ''] : null; }", scope)


def errs(P):
    return [e for e in P.errors if "pageerror" in e or "console.error" in e]


with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("home", 2400)
    pg = P.pg
    ok("two cameras (the settings' and Mainsail's 'Piatto'; its own copy and the go2rtc one left out): a menu on the card", wait_until(lambda: pg.locator(".camera-picker").count() == 1) and "Camera" in pg.locator(".camera-picker").inner_text())
    ok("the settings' camera shows first (WebRTC page)", media(P)[0] == "IFRAME" and media(P)[1].endswith("/webcam/webrtc"), media(P))
    pg.locator(".camera-picker").click()
    pg.wait_for_selector(".oui-menu")
    ok("the menu: Camera and Piatto", [e.get_attribute("data-camera") for e in pg.locator(".oui-menu [data-camera]").all()] == ["main", "w:Piatto"])
    pg.screenshot(path=out + "/menu.png")
    pg.locator('.oui-menu [data-camera="w:Piatto"]').click()
    ok("Piatto: its MJPEG stream, flipped as Mainsail says", wait_until(lambda: media(P) and media(P)[0] == "IMG" and "/webcam2/?action=stream" in media(P)[1]) and "scaleX(-1)" in (pg.locator(".camera-frame__video").get_attribute("style") or ""), media(P))
    ok("... the menu says Piatto", "Piatto" in pg.locator(".camera-picker").inner_text())
    pg.locator(".camera-full-open").first.click()
    ok("the full screen shows the chosen camera", wait_until(lambda: pg.locator(".camera-full img, .camera-full iframe").count() >= 1) and "/webcam2/" in (pg.locator(".camera-full img, .camera-full iframe").first.get_attribute("src") or ""))
    pg.keyboard.press("Escape")
    pg.reload()
    pg.wait_for_timeout(2400)
    ok("the choice stays on this device", wait_until(lambda: media(P) and "/webcam2/" in media(P)[1]))
    ok("no page errors", not errs(P), errs(P)[:2])
    P.close()

    # one camera only
    mock.reset()
    mock.set(webcams=[])
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("home", 2400)
    P.pg.wait_for_timeout(800)
    ok("Mainsail has no other camera: no menu", P.pg.locator(".camera-picker").count() == 0)
    P.close()

    # computer
    mock.reset()
    P = Page(b, mock, 1440, 900)
    CUR[0] = P
    P.goto("home", 2400)
    ok("desktop: the menu on the camera panel", wait_until(lambda: P.pg.locator(".desk-camera .camera-picker").count() == 1))
    P.pg.locator(".desk-camera .camera-picker").click()
    P.pg.locator('.oui-menu [data-camera="w:Piatto"]').click()
    ok("desktop: Piatto in the panel", wait_until(lambda: "/webcam2/" in (P.pg.locator(".desk-camera__video").get_attribute("src") or "")))
    P.pg.screenshot(path=out + "/desktop.png")
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
