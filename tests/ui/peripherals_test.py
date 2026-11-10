"""Release 1.76: the devices connected to the Raspberry on the System page (Moonraker's /machine/peripherals/*): serial
ports with the address for printer.cfg (a tap copies it), USB devices, cameras, CAN (none here: says so).
Usage: peripherals_test.py <html> <outdir> <port>"""
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


with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    for w, hh in ((390, 844), (1440, 900)):
        P = Page(b, mock, w, hh)
        CUR[0] = P
        P.goto("sistema", 2600)
        pg = P.pg
        card = pg.locator(".peripherals-list").first
        ok("%d: the serial board with its by-id address" % w, wait_until(lambda: card.count() == 1 and "Klipper stm32h723xx" in card.inner_text() and "/dev/serial/by-id/usb-Klipper_stm32h723xx" in card.inner_text(), 8), card.inner_text() if card.count() else "")
        if w == 390:
            pg.context.grant_permissions(["clipboard-read", "clipboard-write"])
            card.locator(".peripheral-row__copy").first.click()
            ok("a tap copies the address and says so", wait_until(lambda: "Indirizzo copiato" in pg.evaluate("() => document.body.innerText")))
            pg.screenshot(path=out + "/phone.png", full_page=True)
        pg.locator('[data-peripherals="usb"]').first.click()
        ok("%d: USB: the board and the webcam, with vendor:product" % w, wait_until(lambda: "Logitech Webcam C270" in card.inner_text() and "046d:0825" in card.inner_text()))
        pg.locator('[data-peripherals="video"]').first.click()
        ok("%d: cameras: C270 HD WEBCAM, /dev/video0" % w, wait_until(lambda: "C270 HD WEBCAM" in card.inner_text() and "/dev/video0" in card.inner_text()))
        pg.locator('[data-peripherals="can"]').first.click()
        ok("%d: CAN: no network here, said in words" % w, wait_until(lambda: "Nessuna rete CAN" in pg.locator(".peripherals-note").first.inner_text()))
        ok("%d: no horizontal overflow, no page errors" % w, pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth") and not [e for e in errs(P) if "404" not in e], errs(P)[:2])
        P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
