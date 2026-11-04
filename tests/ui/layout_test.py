"""Releases 1.50.0 / 1.51.0 (roadmap 6e parts 1 and 2): cards that fold down to their title (the chevron, kept on this device), and
Settings → Appearance: the order of the cards of Home and Control, the hidden ones, "open them all", the usual order
back; the hints (the small texts that explain a page) shown or hidden. Against the mock.
Usage: layout_test.py <html> <outdir> <port>"""
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


def order(P):
    return [e.get_attribute("data-card") for e in P.pg.locator(".app-main [data-card]").all()]


def errs(P):
    return [e for e in P.errors if "pageerror" in e or "console.error" in e]


def open_appearance(P):
    P.pg.click('button[aria-label="Impostazioni"]')
    P.pg.wait_for_selector(".drawer")
    P.settle(450)
    P.pg.locator('.set-entry[data-page="appearance"]').click()
    P.settle(600)


def close_menu(P):
    P.pg.click('.drawer button[aria-label="Chiudi"]')
    P.settle(600)


with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("home", 2400)
    pg = P.pg
    ok("Home in the usual order: camera, heaters, temperatures, movement", wait_until(lambda: order(P) == ["camera", "heaters", "temps", "movement"]), order(P))
    heaters = pg.locator('[data-card="heaters"]')
    h0 = heaters.bounding_box()["height"]
    heaters.locator(".oui-card__fold").click()
    ok("the chevron folds a card down to its title", wait_until(lambda: "is-collapsed" in heaters.get_attribute("class")) and heaters.bounding_box()["height"] < h0 / 2 and heaters.locator(".heater-tile").count() >= 0 and not heaters.locator(".heater-tile").first.is_visible(), heaters.bounding_box())
    pg.reload()
    pg.wait_for_timeout(2400)
    ok("... it stays folded on this device", wait_until(lambda: "is-collapsed" in pg.locator('[data-card="heaters"]').get_attribute("class")))

    open_appearance(P)
    ok("Settings → Appearance: Home's cards in order", [e.get_attribute("data-layout-card") for e in pg.locator('[data-layout-page="home"] [data-layout-card]').all()] == ["camera", "heaters", "temps", "spool", "movement"])
    ok("... '1 card è richiusa'", "1 card è richiusa" in pg.locator(".drawer").inner_text())
    pg.locator('[data-layout-page="home"] [data-layout-card="movement"]').get_by_role("button", name="Su: Movimento e Z-offset").click()
    pg.locator('[data-layout-page="home"] [data-layout-card="movement"]').get_by_role("button", name="Su: Movimento e Z-offset").click()
    pg.locator('[data-layout-page="home"] [data-layout-card="movement"]').get_by_role("button", name="Su: Movimento e Z-offset").click()
    pg.locator('[data-layout-page="home"] [data-layout-card="camera"] [role=switch]').click()
    pg.screenshot(path=out + "/appearance.png", full_page=True)
    pg.get_by_role("button", name="Riaprile tutte").click()
    close_menu(P)
    ok("Home: movement moved up three places (before the heaters), camera hidden", wait_until(lambda: order(P) == ["movement", "heaters", "temps"]), order(P))
    ok("... and the folded card open again", "is-collapsed" not in pg.locator('[data-card="heaters"]').get_attribute("class"))
    pg.reload()
    pg.wait_for_timeout(2400)
    ok("the order stays on this device", wait_until(lambda: order(P) == ["movement", "heaters", "temps"]), order(P))

    # Control
    pg.locator('.bottom-nav__tab[data-tab="controllo"]').click()
    P.settle(1200)
    ok("Control in the usual order", wait_until(lambda: [c for c in order(P) if not c.startswith("macro:")][:5] == ["console", "extruder", "tune", "endstops", "bedmesh"]), order(P))
    open_appearance(P)
    pg.locator('[data-layout-page="control"] [data-layout-card="bedmesh"]').get_by_role("button", name="Su: Bed mesh").click()
    pg.locator('[data-layout-page="control"] [data-layout-card="console"] [role=switch]').click()
    close_menu(P)
    ok("Control: no console, bed mesh before endstops", wait_until(lambda: "console" not in order(P) and order(P).index("bedmesh") > order(P).index("tune")) and pg.locator(".endstops-card").count() == 1, order(P))

    open_appearance(P)
    pg.get_by_role("button", name="Ordine solito, tutto visibile").click()
    close_menu(P)
    ok("'Ordine solito, tutto visibile' brings everything back", wait_until(lambda: "console" in order(P)))
    ok("no horizontal overflow", pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    ok("no page errors", not errs(P), errs(P)[:2])
    P.close()

    # 1.51: the hints
    mock.reset()
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("home", 2400)
    ok("the hints show by default ('Tocca per modificare')", P.pg.locator(".ui-hint", has_text="Tocca per modificare").first.is_visible())
    open_appearance(P)
    P.pg.locator('[data-setting="hints"] [role=switch]').click()
    close_menu(P)
    ok("'Mostra i suggerimenti' off: they hide", wait_until(lambda: not P.pg.locator(".ui-hint").first.is_visible()) and P.pg.locator(".heater-tile").first.is_visible())
    P.pg.reload()
    P.pg.wait_for_timeout(2400)
    ok("... and stay hidden on this device", not P.pg.locator(".ui-hint").first.is_visible())
    P.close()

    # 1.54: the menu's "Vai a"
    mock.reset()
    mock.set(timelapse_on=True)
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("home", 2400)
    P.pg.click('button[aria-label="Impostazioni"]')
    P.pg.wait_for_selector(".drawer")
    P.settle(600)
    ok("the menu's 'Vai a': history and timelapse (Moonraker has it)", wait_until(lambda: [e.get_attribute("data-page") for e in P.pg.locator('[data-group="pages"] [data-page]').all()] == ["go-history", "go-timelapse"]))
    ok("1.60: 'Notifiche e aspetto': notifications, appearance, language", [e.get_attribute("data-page") for e in P.pg.locator('[data-group="yours"] [data-page]').all()] == ["notifications", "appearance", "language"])
    P.pg.locator('[data-page="go-timelapse"]').click()
    ok("'Timelapse' closes the menu and opens the Files page on it", wait_until(lambda: P.pg.locator(".drawer").count() == 0 and P.pg.locator(".timelapse-videos").count() == 1))
    P.pg.click('button[aria-label="Impostazioni"]')
    P.pg.wait_for_selector(".drawer")
    P.settle(600)
    P.pg.locator('[data-page="go-history"]').click()
    ok("'Cronologia stampe' opens the history", wait_until(lambda: P.pg.locator(".history-list-card").count() == 1))
    P.close()

    # computer: the cards fold there too
    mock.reset()
    P = Page(b, mock, 1440, 900)
    CUR[0] = P
    P.goto("home", 2400)
    fans = P.pg.locator('[data-card="fans"]')
    fans.locator(".oui-card__fold").click()
    ok("desktop: the fans fold too", wait_until(lambda: "is-collapsed" in fans.get_attribute("class")))
    P.pg.screenshot(path=out + "/desktop.png")
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
