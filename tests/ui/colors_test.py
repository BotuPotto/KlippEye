"""Releases 1.52.0 / 1.53.0 (roadmap 6e parts 3 and 4): the accent colour (Settings → Appearance → Colour): the logo's violet, five other
colours, or any colour from the wheel (made light enough for the dark page); kept on this device; the looks (One UI, Liquid Glass, Material 3 Expressive, HyperOS 4). Against the mock.
Usage: colors_test.py <html> <outdir> <port>"""
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


def accent(P):
    return P.pg.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--oui-accent').trim().toLowerCase()")


def lightness(hexv):
    r, g, b = (int(hexv[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return (max(r, g, b) + min(r, g, b)) / 2


def errs(P):
    return [e for e in P.errors if "pageerror" in e or "console.error" in e]


with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("home", 2400)
    pg = P.pg
    ok("the logo's violet by default", accent(P) == "#b79cff", accent(P))
    pg.click('button[aria-label="Impostazioni"]')
    pg.wait_for_selector(".drawer")
    P.settle(450)
    pg.locator('.set-entry[data-page="appearance"]').click()
    P.settle(600)
    pg.locator('[data-accent="blue"]').click()
    ok("Blu: the accent changes at once", wait_until(lambda: accent(P) == "#8ab4ff"), accent(P))
    ok("... the switches follow it", "138, 180, 255" in pg.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--oui-accent-rgb')"))
    pg.screenshot(path=out + "/blue.png", full_page=True)
    pg.locator('[data-accent="custom"]').click()
    hexf = pg.locator(".accent-wheel .color-wheel__hex")
    hexf.fill("#003300")
    ok("a very dark colour of your own is made light enough (green, lightness >= 62 %)", wait_until(lambda: accent(P) != "#8ab4ff") and lightness(accent(P)) >= 0.6 and int(accent(P)[3:5], 16) > int(accent(P)[1:3], 16), accent(P))
    custom = accent(P)
    pg.reload()
    pg.wait_for_timeout(2400)
    ok("the colour stays on this device", accent(P) == custom, (accent(P), custom))
    pg.click('button[aria-label="Impostazioni"]')
    pg.wait_for_selector(".drawer")
    P.settle(450)
    ok("the menu says 'Colore tuo'", "Colore tuo" in pg.locator('.set-entry[data-page="appearance"]').inner_text())
    pg.locator('.set-entry[data-page="appearance"]').click()
    P.settle(600)
    pg.locator('[data-accent="violet"]').click()
    ok("Viola: the logo's colour again", wait_until(lambda: accent(P) == "#b79cff"), accent(P))
    # 1.53: the looks
    for look in ("glass", "material", "studio", "soft", "fluent", "aurora", "hyperos"):
        pg.locator('[data-look-choice="%s"]' % look).click()
        ok("look %s: set on the page" % look, wait_until(lambda: pg.evaluate("document.documentElement.getAttribute('data-look')") == look))
    ok("HyperOS: the cards are flat grey", pg.evaluate("() => getComputedStyle(document.querySelector('.oui-card')).backgroundColor") == "rgb(22, 23, 26)", pg.evaluate("() => getComputedStyle(document.querySelector('.oui-card')).backgroundColor"))
    pg.reload()
    pg.wait_for_timeout(2400)
    ok("the look stays on this device", pg.evaluate("document.documentElement.getAttribute('data-look')") == "hyperos")
    pg.click('button[aria-label="Impostazioni"]')
    pg.wait_for_selector(".drawer")
    P.settle(450)
    pg.locator('.set-entry[data-page="appearance"]').click()
    P.settle(600)
    pg.locator('[data-look-choice="oneui"]').click()
    ok("One UI: the usual look again", wait_until(lambda: pg.evaluate("document.documentElement.getAttribute('data-look')") is None))
    for w in (390, 320):
        pg.set_viewport_size({"width": w, "height": 800})
        pg.wait_for_timeout(300)
        ok("[%d] the camera card's buttons stay inside it" % w, pg.evaluate("() => { const c = document.querySelector('[data-card=camera]'); return !c || c.querySelector('.oui-card__fold').getBoundingClientRect().right <= c.getBoundingClientRect().right; }"))
    ok("no page errors", not errs(P), errs(P)[:2])
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
