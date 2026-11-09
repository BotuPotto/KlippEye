"""Release 1.36.0 (roadmap 6b part 7): the height map redone like Mainsail's. 2D (back of the bed at the top, the values, a
tap tells where a point is) and 3D; probed or interpolated; minimum / maximum / range / points; the profiles (load, rename,
remove, save as), clear, calibrate with a profile name and adaptive. Against the mock.
Usage: bedmesh_test.py <html> <outdir> <port>"""
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
CUR = [None]


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


def gcodes():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/gcode").read())


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


def fresh(b, tab="controllo", w=390, h=844, **st):
    mock.reset()
    mock.set(**st)
    P = Page(b, mock, w, h)
    CUR[0] = P
    P.goto(tab, 2400)
    return P


def card(P):
    return P.pg.locator(".mesh-card")


def stat(P, label):
    return card(P).locator(".mesh-stat:has(.oui-caption:text-is('%s')) .mesh-stat__value" % label).inner_text()


def profiles(P):
    return [e.get_attribute("data-profile") for e in card(P).locator("[data-profile]").all()]


def name_dialog(P, name):
    field = P.pg.locator(".confirm-card .mesh-name__input")
    field.fill(name)
    P.pg.locator(".confirm-card .oui-btn--primary, .confirm-card button.confirm-ok").last.click()


with sync_playwright() as p:
    b = p.chromium.launch()

    P = fresh(b)
    pg = P.pg
    c = card(P)
    c.scroll_into_view_if_needed()
    ok("the card says the profile in use (default)", wait_until(lambda: c.locator("[data-active-profile]").get_attribute("data-active-profile") == "default"))
    ok("1.67: ... the whole name fits its pill (it was cut to «def»)", c.locator("[data-active-profile]").evaluate("e => e.scrollWidth <= e.clientWidth + 1") and c.locator("[data-active-profile]").inner_text() == "default", c.locator("[data-active-profile]").evaluate("e => [e.scrollWidth, e.clientWidth]"))
    ok("minimum, maximum, range and points (7 × 7)", wait_until(lambda: stat(P, "Punti") == "7 × 7") and stat(P, "Minimo").endswith("mm") and stat(P, "Escursione").endswith("mm"), (stat(P, "Minimo"), stat(P, "Massimo"), stat(P, "Escursione")))
    c.screenshot(path=out + "/card_3d.png")
    c.get_by_role("button", name="2D", exact=True).click()
    first = c.locator(".mesh-cell").first
    ok("2D: the back of the bed at the top (the first cell is the last row, back left)", wait_until(lambda: first.get_attribute("data-row") == "6" and first.get_attribute("data-col") == "0"))
    ok("... with the values in the cells", c.locator(".mesh-cell__value").count() == 49)
    first.click()
    ok("a tap on a point says where it is: X 30 · Y 320", wait_until(lambda: "X 30.0 · Y 320.0" in c.locator(".mesh-pick").inner_text()), c.locator(".mesh-grid__foot").inner_text())
    c.screenshot(path=out + "/card_2d.png")
    c.get_by_role("button", name="Interpolati", exact=True).click()
    ok("'Interpolati': the interpolated mesh (13 × 13), too many to write the values", wait_until(lambda: stat(P, "Punti") == "13 × 13") and c.locator(".mesh-cell__value").count() == 0)
    c.get_by_role("button", name="Misurati", exact=True).click()

    # profiles
    ok("the profiles Klipper keeps, the one in use marked", wait_until(lambda: profiles(P) == ["default", "adaptive"]) and "In uso" in c.locator('[data-profile="default"]').inner_text(), profiles(P))
    c.locator('[data-profile="adaptive"]').get_by_role("button", name="Carica", exact=True).click()
    ok("'Carica': BED_MESH_PROFILE LOAD=adaptive, then it is in use (5 × 5)", wait_until(lambda: "BED_MESH_PROFILE LOAD=adaptive" in gcodes() and c.locator("[data-active-profile]").get_attribute("data-active-profile") == "adaptive" and stat(P, "Punti") == "5 × 5"))
    c.locator('[data-profile="adaptive"] button[aria-label="Rinomina adaptive"]').click()
    pg.wait_for_selector(".confirm-card .mesh-name__input")
    pg.locator(".confirm-card .mesh-name__input").fill("my mesh")
    ok("a name with a space is refused", "Solo lettere" in pg.locator(".confirm-card").inner_text())
    pg.locator(".confirm-card").get_by_role("button", name="Rinomina", exact=True).click()
    P.settle(300)
    ok("... and not sent", not any("my mesh" in g for g in gcodes()) and pg.locator(".confirm-card .mesh-name__input").count() == 1)
    pg.locator(".confirm-card .mesh-name__input").fill("fine_bed")
    pg.locator(".confirm-card").get_by_role("button", name="Rinomina", exact=True).click()
    ok("renaming: load, save with the new name, remove the old", wait_until(lambda: "BED_MESH_PROFILE LOAD=adaptive\nBED_MESH_PROFILE SAVE=fine_bed\nBED_MESH_PROFILE REMOVE=adaptive" in gcodes()), gcodes()[-3:])
    ok("... the list has fine_bed, not adaptive", wait_until(lambda: sorted(profiles(P)) == ["default", "fine_bed"]), profiles(P))
    c.locator('[data-profile="default"] button[aria-label="Togli default"]').click()
    pg.wait_for_selector(".confirm-card")
    ok("removing asks first, and says SAVE_CONFIG confirms it", "SAVE_CONFIG" in pg.locator(".confirm-card").inner_text())
    pg.locator(".confirm-card").get_by_role("button", name="Togli", exact=True).click()
    ok("... BED_MESH_PROFILE REMOVE=default", wait_until(lambda: "BED_MESH_PROFILE REMOVE=default" in gcodes() and profiles(P) == ["fine_bed"]))
    c.get_by_role("button", name="Salva come…", exact=True).click()
    pg.wait_for_selector(".confirm-card .mesh-name__input")
    pg.locator(".confirm-card .mesh-name__input").fill("test1")
    pg.locator(".confirm-card").get_by_role("button", name="Salva", exact=True).click()
    ok("'Salva come…': BED_MESH_PROFILE SAVE=test1", wait_until(lambda: "BED_MESH_PROFILE SAVE=test1" in gcodes() and "test1" in profiles(P)))

    # calibrate, clear
    c.get_by_role("button", name="Calibra mesh", exact=True).click()
    pg.wait_for_selector(".confirm-card .mesh-name__input")
    ok("calibrate: the profile name, 'default' proposed", pg.locator(".confirm-card .mesh-name__input").input_value() == "default")
    pg.locator(".confirm-card .mesh-adaptive input").check()
    pg.screenshot(path=out + "/calibrate_dialog.png")
    pg.locator(".confirm-card").get_by_role("button", name="Calibra", exact=True).click()
    ok("... BED_MESH_CALIBRATE PROFILE=default ADAPTIVE=1", wait_until(lambda: "BED_MESH_CALIBRATE PROFILE=default ADAPTIVE=1" in gcodes()), gcodes()[-3:])
    c.get_by_role("button", name="Togli", exact=True).click()
    ok("'Togli': BED_MESH_CLEAR, no mesh in use", wait_until(lambda: "BED_MESH_CLEAR" in gcodes() and "Nessuna mesh caricata" in c.inner_text()))
    ok("no horizontal overflow at 390", pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    P.close()

    # printing
    P = fresh(b, printing=True)
    c = card(P)
    ok("printing: calibrate and load are disabled", wait_until(lambda: c.get_by_role("button", name="Calibra mesh", exact=True).is_disabled()) and c.locator('[data-profile="adaptive"]').get_by_role("button", name="Carica", exact=True).is_disabled())
    P.close()

    # computer
    P = fresh(b, w=1440, h=900)
    ok("desktop: the card on the Calibrazione page", wait_until(lambda: P.pg.locator(".desk-col .mesh-card").count() == 1))
    P.pg.locator(".desk-col .mesh-card").screenshot(path=out + "/desktop.png")
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
