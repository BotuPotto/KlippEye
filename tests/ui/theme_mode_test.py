"""Release 1.108: dark, light or as the device (Settings → Appearance → Theme). Dark at first; Light: the page, the cards,
the top bar and the side menu are light and the text dark (enough contrast), the accent deeper, the browser bar's
colour too; «As the device» follows the device's setting, also when it changes; kept on this device; the code
editor's well stays dark. Against the mock.
Usage: theme_mode_test.py <html> <outdir> <port>"""
import os
import sys
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


LUM = """(sel) => { const el = document.querySelector(sel); if (!el) return null;
  const rgb = (c) => (c.match(/[\\d.]+/g) || []).slice(0, 3).map(Number);
  const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  return lum(rgb(getComputedStyle(el).color)); }"""
BG = """() => getComputedStyle(document.documentElement).getPropertyValue('--oui-bg').trim()"""


def open_appearance(P):
    P.pg.locator(".header-btn--menu").click()
    P.pg.wait_for_selector(".drawer")
    P.settle(450)
    P.pg.click('.set-entry[data-page="appearance"]')
    P.settle(900)


with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    P = Page(b, mock)
    P.goto("home", 1400)
    ok("dark at first", P.pg.evaluate("() => document.documentElement.getAttribute('data-mode')") is None and P.pg.evaluate(BG) == "#040507")
    open_appearance(P)
    choices = P.pg.locator("[data-mode-choice]")
    ok("Appearance: the three choices, «Dark» chosen", choices.count() == 3 and P.pg.locator('[data-mode-choice="dark"]').get_attribute("aria-checked") == "true"
       and "Come il dispositivo" in P.pg.locator(".mode-choice").inner_text(), P.pg.locator(".mode-choice").inner_text() if choices.count() else "")
    P.pg.click('[data-mode-choice="light"]')
    P.settle(600)
    ok("Light: the page is light", P.pg.evaluate("() => document.documentElement.getAttribute('data-mode')") == "light" and P.pg.evaluate(BG) == "#eef0f5")
    ok("... the browser bar's colour too", P.pg.evaluate("() => document.querySelector('meta[name=theme-color]').getAttribute('content')") == "#eef0f5")
    ok("... the side menu is light, its texts dark", (P.pg.evaluate(LUM, ".drawer__title") or 1) < 0.05, P.pg.evaluate(LUM, ".drawer__title"))
    accent = P.pg.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--oui-accent').trim()")
    ok("... the accent is deeper (white text on it)", accent.lower() != "#b79cff" and P.pg.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--oui-on-accent').trim()") == "#ffffff", accent)
    P.shot_vp(os.path.join(out, "theme_light_appearance.png"))
    P.goto("home", 1400)
    ok("kept on this device (after a reload)", P.pg.evaluate("() => document.documentElement.getAttribute('data-mode')") == "light")
    ok("... cards' titles dark on the light page", (P.pg.evaluate(LUM, ".oui-card-title") or 1) < 0.05, P.pg.evaluate(LUM, ".oui-card-title"))
    P.shot(os.path.join(out, "theme_light_home.png"))

    open_appearance(P)
    P.pg.emulate_media(color_scheme="dark")
    P.pg.click('[data-mode-choice="auto"]')
    P.settle(500)
    ok("«As the device», the device dark: dark", P.pg.evaluate("() => document.documentElement.getAttribute('data-mode')") is None)
    P.pg.emulate_media(color_scheme="light")
    P.settle(500)
    ok("... the device switches to light: the page follows by itself", P.pg.evaluate("() => document.documentElement.getAttribute('data-mode')") == "light")
    P.pg.emulate_media(color_scheme="dark")
    P.settle(500)
    ok("... and back to dark", P.pg.evaluate("() => document.documentElement.getAttribute('data-mode')") is None)
    P.pg.emulate_media(color_scheme="light")
    P.pg.click('[data-mode-choice="dark"]')
    P.settle(500)
    ok("«Dark» again: dark even with the device light", P.pg.evaluate("() => document.documentElement.getAttribute('data-mode')") is None)
    P.close()

    for look in ("glass", "material", "hyperos"):
        mock.reset()
        P = Page(b, mock)
        P.goto("home", 800)
        P.pg.evaluate("(look) => localStorage.setItem('ke_layout', JSON.stringify({ mode: 'light', look }))", look)
        P.goto("home", 1400)
        ok("light with the look %s: a light page, dark titles" % look, P.pg.evaluate("() => document.documentElement.getAttribute('data-look')") == look
           and (P.pg.evaluate(LUM, ".oui-card-title") or 1) < 0.05 and P.pg.evaluate("() => { const c = getComputedStyle(document.documentElement).getPropertyValue('--oui-bg').trim(); return c.startsWith('#f') || c.startsWith('#e') || c.startsWith('color-mix'); }"),
           P.pg.evaluate(BG))
        P.close()
    b.close()

print("%d FAIL" % len(FAILS))
sys.exit(1 if FAILS else 0)
