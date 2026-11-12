"""Release 1.113: the logs on the System page (no longer on Config); the materials of the temperature window are the
printer's own (Settings → Materials: change, add, remove, back to the usual ones; «Modifica» in the window opens it)
and the spool in use comes first with its filament's temperatures (Spoolman); the ZeroTier guide in Settings →
Addresses, with its commands and the credit to its source. Against the mock.
Usage: tidy_test.py <html> <outdir> <port>"""
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


def open_page(P, page):
    P.pg.locator(".header-btn--menu").click()
    P.pg.wait_for_selector(".drawer")
    P.settle(450)
    P.pg.click('.set-entry[data-page="%s"]' % page)
    P.settle(900)


def chips(P):
    loc = P.pg.locator("[data-temp-preset]")
    return [loc.nth(i).get_attribute("data-temp-preset") for i in range(loc.count())]


with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    P = Page(b, mock, 390, 844)
    P.goto("config", 1800)
    ok("Config: the configuration files only, no logs", P.pg.locator(".log-row").count() == 0 and "Analizza automaticamente" not in P.pg.locator("main").inner_text())
    P.goto("sistema", 1800)
    ok("System: the logs, after the system cards", P.pg.locator(".log-row").count() > 0 and "Analizza automaticamente" in P.pg.locator("main").inner_text())

    # ---- materials
    P.pg.evaluate("() => localStorage.setItem('ke_current_tab', 'home')")
    P.goto("home", 1400)
    P.pg.wait_for_selector(".heater-tile", timeout=15000); P.pg.locator(".heater-tile").first.click(); P.settle(500)
    ok("the window: the usual materials (no Spoolman: no spool)", chips(P) == ["PLA", "PETG", "ABS", "ASA", "TPU", "off"], chips(P))
    P.pg.locator("[data-edit-materials]").click(); P.settle(1200)
    ok("«Modifica» closes the window and opens Settings → Materials", P.pg.locator(".modal-card").count() == 0 and P.pg.locator("[data-material]").count() == 5
       and P.pg.locator(".drawer__title").inner_text() == "Materiali", P.pg.locator(".drawer__title").inner_text() if P.pg.locator(".drawer__title").count() else "")
    pla = P.pg.locator('[data-material="0"]')
    pla.locator('[data-material-field="hotend"]').fill("205"); pla.locator('[data-material-field="hotend"]').press("Enter"); P.settle(600)
    P.pg.locator('[data-material-remove="4"]').click(); P.settle(500)
    P.pg.locator("[data-material-add]").click(); P.settle(500)
    new = P.pg.locator('[data-material="4"]')
    new.locator('[data-material-field="name"]').fill("PA-CF"); new.locator('[data-material-field="name"]').press("Tab")
    new.locator('[data-material-field="hotend"]').fill("280"); new.locator('[data-material-field="hotend"]').press("Tab")
    new.locator('[data-material-field="bed"]').fill("90"); new.locator('[data-material-field="bed"]').press("Tab"); P.settle(900)
    saved = json.loads(urllib.request.urlopen(mock.base + "/server/database/item?namespace=klippeye&key=settings").read())["result"]["value"].get("materials")
    ok("changed, removed, added: saved for every device", saved == [{"name": "PLA", "hotend": 205, "bed": 60}, {"name": "PETG", "hotend": 240, "bed": 80}, {"name": "ABS", "hotend": 250, "bed": 100},
                                                                     {"name": "ASA", "hotend": 255, "bed": 100}, {"name": "PA-CF", "hotend": 280, "bed": 90}], saved)
    ok("... «Torna a quelli di base» offered", P.pg.locator("[data-material-reset]").count() == 1)
    P.shot_vp(os.path.join(out, "materials.png"), 844)
    P.pg.keyboard.press("Escape"); P.settle(300)
    P.goto("home", 1400)
    P.pg.wait_for_selector(".heater-tile", timeout=15000); P.pg.locator(".heater-tile").first.click(); P.settle(500)
    ok("the window shows the printer's own list", chips(P) == ["PLA", "PETG", "ABS", "ASA", "PA-CF", "off"] and "205° / 60°" in P.pg.locator('[data-temp-preset="PLA"]').inner_text(), chips(P))
    P.pg.locator('[data-temp-preset="PA-CF"]').click(); P.settle(600)
    ok("... PA-CF: 280 and 90 together", any("M104 S280" in g and "M140 S90" in g for g in gcodes()), gcodes()[-2:])
    P.close()

    mock.reset()
    mock.set(spoolman_on=True, spool_id=2)
    P = Page(b, mock, 360, 780)
    P.goto("home", 1600)
    P.pg.wait_for_selector(".heater-tile", timeout=15000); P.pg.locator(".heater-tile").first.click(); P.settle(1200)
    spool = P.pg.locator('[data-temp-preset="spool"]')
    ok("with Spoolman: the spool in use first, with its filament's temperatures", chips(P)[:1] == ["spool"] and "PETG" in spool.inner_text() and "235° / 75°" in spool.inner_text(), spool.inner_text() if spool.count() else chips(P))
    P.shot_vp(os.path.join(out, "spool_chip.png"), 780)
    spool.click(); P.settle(600)
    ok("... a tap: 235 and 75", any("M104 S235" in g and "M140 S75" in g for g in gcodes()), gcodes()[-2:])
    P.close()

    mock.reset()
    mock.set(spoolman_on=True, spool_id=1)
    P = Page(b, mock, 360, 780)
    P.goto("home", 1600)
    P.pg.wait_for_selector(".heater-tile", timeout=15000); P.pg.locator(".heater-tile").first.click(); P.settle(1200)
    ok("a spool whose filament has no temperatures: no spool chip", "spool" not in chips(P), chips(P))
    P.close()

    # ---- ZeroTier
    mock.reset()
    P = Page(b, mock, 390, 844)
    P.goto("home", 1400)
    open_page(P, "network")
    guide = P.pg.locator("[data-zerotier-guide]")
    ok("Addresses: the ZeroTier guide, folded", guide.count() == 1 and guide.get_attribute("open") is None)
    guide.locator("summary").click(); P.settle(500)
    text = guide.inner_text()
    ok("... open: six steps, the commands, the credit with the link",
       guide.locator("[data-zt-step]").count() == 6 and "sudo apt install -y zerotier-one" in text and "sudo zerotier-cli join NETWORK_ID" in text
       and "Pi My Life Up" in text and guide.locator('a[href="https://pimylifeup.com/raspberry-pi-zerotier/"]').count() == 1, text[:400])
    wide = P.pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    ok("... no sideways scrolling at 390 px (long commands wrap)", wide <= 0, wide)
    P.shot(os.path.join(out, "zerotier.png"))
    P.close()
    b.close()

print("%d FAIL" % len(FAILS))
sys.exit(1 if FAILS else 0)
