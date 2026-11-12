"""Release 1.32.0 (roadmap 6b part 3): the Tune card (speed and flow factors, pressure advance, machine limits, firmware
retraction) and the leveling tools of the "Calibrate" menu (Z tilt adjust, quad gantry level, bed screws adjust step by step).
Against the mock.
Usage: tune_test.py <html> <outdir> <port>"""
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


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


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
    P.goto(tab, 2200)
    return P


def row(P, rid):
    return P.pg.locator('.tune-row[data-tune="%s"]' % rid)


def value(P, rid):
    return row(P, rid).locator("input").input_value()


def open_calibrate(P):
    P.pg.locator("button:has-text('Calibra')").first.click()
    P.pg.wait_for_timeout(400)


with sync_playwright() as p:
    b = p.chromium.launch()

    # ---- the card on the Control page
    P = fresh(b)
    pg = P.pg
    card = pg.locator(".tune-card")
    ok("the Control page has the Tune card ('Regolazioni')", card.count() == 1 and "Regolazioni" in card.inner_text())
    groups = card.locator("[data-tune-group]")
    ok("... four groups: print, pressure advance, machine limits, firmware retraction",
       [groups.nth(i).get_attribute("data-tune-group") for i in range(groups.count())] == ["print", "pa", "limits", "retraction"])
    ok("speed and flow as Klipper reports them (110 %, 95 %)", wait_until(lambda: value(P, "speed") == "110" and value(P, "flow") == "95"), (value(P, "speed"), value(P, "flow")))
    ok("pressure advance 0.040, printer.cfg 0.050 written under it", value(P, "pa") == "0.040" and "printer.cfg: 0.050" in row(P, "pa").inner_text(), row(P, "pa").inner_text())
    ok("a value away from printer.cfg has the button back to it, one equal to it does not",
       "is-hidden" not in row(P, "pa").locator(".tune-reset").get_attribute("class") and "is-hidden" in row(P, "smooth").locator(".tune-reset").get_attribute("class"))
    ok("1.113: machine limits and retraction start folded (only their titles), the others open",
       row(P, "accel").count() == 0 and row(P, "retractLength").count() == 0 and row(P, "pa").count() == 1
       and card.locator('[data-tune-fold="limits"]').get_attribute("aria-expanded") == "false")
    card.locator('[data-tune-fold="limits"]').click()
    card.locator('[data-tune-fold="retraction"]').click()
    P.settle(300)
    ok("... one tap opens each", row(P, "accel").count() == 1 and row(P, "retractLength").count() == 1)
    ok("limits of a recent Klipper: minimum cruise ratio, no accel_to_decel", row(P, "mcr").count() == 1 and row(P, "a2d").count() == 0)
    ok("no horizontal overflow at 390", pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    card.screenshot(path=out + "/tune_card_390.png")

    row(P, "speed").locator("button[aria-label$='+']").click()
    ok("+ on the speed: M220 S115, after a moment", wait_until(lambda: "M220 S115" in gcodes()), gcodes()[-5:])
    ok("... and the field shows what Klipper now reports", wait_until(lambda: value(P, "speed") == "115" and abs(state()["speed_factor"] - 1.15) < 1e-6))
    before = len([g for g in gcodes() if g.startswith("M221")])
    plus = row(P, "flow").locator("button[aria-label$='+']")
    for _ in range(3):
        plus.click()
        pg.wait_for_timeout(80)
    ok("three quick taps on the flow: sent once, M221 S98", wait_until(lambda: "M221 S98" in gcodes()) and len([g for g in gcodes() if g.startswith("M221")]) == before + 1, [g for g in gcodes() if g.startswith("M221")])
    field = row(P, "accel").locator("input")
    field.click()
    field.fill("5000")
    field.press("Enter")
    ok("typing 5000 in the acceleration: SET_VELOCITY_LIMIT ACCEL=5000", wait_until(lambda: "SET_VELOCITY_LIMIT ACCEL=5000" in gcodes()), gcodes()[-4:])
    ok("... the button back to printer.cfg (3000) appears", wait_until(lambda: "is-hidden" not in row(P, "accel").locator(".tune-reset").get_attribute("class")))
    field.click()
    field.fill("abc")
    field.press("Enter")
    pg.wait_for_timeout(900)
    ok("text that is not a number is not sent and the value comes back", value(P, "accel") == "5000" and not any("ACCEL=abc" in g for g in gcodes()))
    P.goto("controllo", 2200)
    ok("1.113: opened groups stay open on this device", row(P, "accel").count() == 1)
    card = P.pg.locator(".tune-card")
    card.locator('[data-tune-fold="limits"]').click(); P.settle(300)
    ok("... folded with a value away from printer.cfg: a dot on its title", row(P, "accel").count() == 0 and card.locator('[data-tune-group="limits"] .tune-group__changed').count() == 1)
    card.locator('[data-tune-fold="limits"]').click(); P.settle(300)
    row(P, "pa").locator(".tune-reset").click()
    ok("back to printer.cfg on the pressure advance: SET_PRESSURE_ADVANCE ADVANCE=0.05", wait_until(lambda: "SET_PRESSURE_ADVANCE ADVANCE=0.05" in gcodes()), gcodes()[-4:])
    ok("... the field shows 0.050 and the button goes", wait_until(lambda: value(P, "pa") == "0.050" and "is-hidden" in row(P, "pa").locator(".tune-reset").get_attribute("class")))
    row(P, "retractLength").locator("button[aria-label$='−']").click()
    ok("− on the retract length: SET_RETRACTION RETRACT_LENGTH=0.7", wait_until(lambda: "SET_RETRACTION RETRACT_LENGTH=0.7" in gcodes()), gcodes()[-4:])
    row(P, "smooth").locator("button[aria-label$='+']").click()
    ok("+ on the smooth time: SMOOTH_TIME=0.045", wait_until(lambda: "SET_PRESSURE_ADVANCE SMOOTH_TIME=0.045" in gcodes()), gcodes()[-4:])
    P.close()

    # ---- an older Klipper, no firmware retraction
    P = fresh(b, old_limits=True, has_retraction=False)
    wait_until(lambda: P.pg.locator('[data-tune-fold="limits"]').count() == 1)
    P.pg.locator('[data-tune-fold="limits"]').click()
    ok("an older Klipper: accel_to_decel instead of the minimum cruise ratio", wait_until(lambda: row(P, "a2d").count() == 1) and row(P, "mcr").count() == 0)
    ok("no [firmware_retraction]: no retraction group", P.pg.locator('[data-tune-group="retraction"]').count() == 0)
    P.close()

    # ---- during a print the card stays usable (mobile Control page and the desktop device page)
    P = fresh(b, printing=True)
    row(P, "speed").locator("button[aria-label$='−']").click()
    ok("printing: − on the speed sends M220 S105", wait_until(lambda: "M220 S105" in gcodes()), gcodes()[-4:])
    P.close()
    P = fresh(b, tab="home", w=1440, h=900, printing=True)
    ok("desktop, printing: the Tune card is on the printer page", wait_until(lambda: P.pg.locator(".desk-slot--tune .tune-card").count() == 1))
    P.pg.locator(".desk-slot--tune").scroll_into_view_if_needed()
    P.pg.screenshot(path=out + "/tune_desktop.png")
    P.close()

    # ---- leveling: Z tilt adjust, quad gantry level
    P = fresh(b, tab="home", has_level=True)
    open_calibrate(P)
    menu = P.pg.locator(".oui-menu")
    ok("[z_tilt]: the Calibrate menu has Z tilt adjust under 'Livellamento'", "z tilt adjust" in menu.inner_text().lower() and "livellamento" in menu.inner_text().lower(), menu.inner_text())
    P.pg.screenshot(path=out + "/calibrate_menu_ztilt.png")
    P.pg.locator(".oui-menu__item:has-text('Z tilt adjust')").click()
    ok("Z_TILT_ADJUST sent", wait_until(lambda: "Z_TILT_ADJUST" in gcodes()))
    ok("... at the end: 'Z tilt adjust completato'", wait_until(lambda: any("Z tilt adjust completato" in t for t in P.pg.locator(".toast").all_inner_texts()), 8), P.pg.locator(".toast").all_inner_texts())
    P.close()
    P = fresh(b, tab="home", has_level=True, z_kind="toolhead", tool_timeout_502=True, level_delay=3.0)
    open_calibrate(P)
    ok("[quad_gantry_level]: Quad gantry level, no Z tilt", "quad gantry level" in P.pg.locator(".oui-menu").inner_text().lower() and "z tilt" not in P.pg.locator(".oui-menu").inner_text().lower())
    P.pg.locator(".oui-menu__item:has-text('Quad gantry level')").click()
    ok("QGL running longer than the proxy waits: the button says QGL…", wait_until(lambda: "QGL" in P.pg.locator(".movement-actions").inner_text()), P.pg.locator(".movement-actions").inner_text())
    ok("... and ends when Klipper is idle again", wait_until(lambda: "Calibra" in P.pg.locator(".movement-actions").inner_text(), 10) and any("Quad gantry level completato" in t for t in P.pg.locator(".toast").all_inner_texts()))
    P.close()
    P = fresh(b, tab="home", has_level=True, tool_error="Probe triggered prior to movement")
    open_calibrate(P)
    P.pg.locator(".oui-menu__item:has-text('Z tilt adjust')").click()
    ok("a failing Z tilt: the error in a toast, the button idle again", wait_until(lambda: any("Probe triggered" in t for t in P.pg.locator(".toast").all_inner_texts()), 8) and wait_until(lambda: "Calibra" in P.pg.locator(".movement-actions").inner_text()))
    P.close()

    # ---- bed screws adjust, step by step
    P = fresh(b, tab="home", has_bed_screws=True)
    pg = P.pg
    open_calibrate(P)
    ok("[bed_screws]: Bed screws adjust in the menu", "bed screws adjust" in pg.locator(".oui-menu").inner_text().lower())
    pg.locator(".oui-menu__item:has-text('Bed screws adjust')").click()
    sheet = pg.locator(".bed-screws")
    ok("the sheet opens at the first screw: 'Vite 1 di 3', front left", wait_until(lambda: "vite 1 di 3" in sheet.inner_text().lower() and "front left" in sheet.inner_text()), sheet.inner_text() if sheet.count() else "")
    ok("... with the paper test explained", "foglio" in sheet.inner_text())
    pg.screenshot(path=out + "/bed_screws_sheet.png")

    def press(label, expect):
        sheet.get_by_role("button", name=label, exact=True).click()
        return wait_until(lambda: expect.lower() in sheet.inner_text().lower(), 5)

    ok("'Regolata' (ADJUSTED): the second screw", press("Regolata", "Vite 2 di 3") and "ADJUSTED" in gcodes() and "front right" in sheet.inner_text())
    ok("'Accetta' (ACCEPT): the third", press("Accetta", "Vite 3 di 3") and "ACCEPT" in gcodes())
    ok("a round with an adjusted screw starts again from the first", press("Accetta", "Vite 1 di 3"))
    press("Accetta", "Vite 2 di 3")
    press("Accetta", "Vite 3 di 3")
    ok("a round all accepted: the bed is level", press("Accetta", "livellato"), sheet.inner_text())
    pg.screenshot(path=out + "/bed_screws_done.png")
    sheet.get_by_role("button", name="Fatto", exact=True).click()
    ok("'Fatto' closes it", wait_until(lambda: pg.locator(".bed-screws").count() == 0))
    open_calibrate(P)
    pg.locator(".oui-menu__item:has-text('Bed screws adjust')").click()
    wait_until(lambda: "vite 1 di 3" in sheet.inner_text().lower())
    sheet.get_by_role("button", name="Interrompi", exact=True).click()
    ok("'Interrompi' sends ABORT and closes the sheet", wait_until(lambda: "ABORT" in gcodes() and pg.locator(".bed-screws").count() == 0) and not state()["bs"]["is_active"])
    open_calibrate(P)
    pg.locator(".oui-menu__item:has-text('Bed screws adjust')").click()
    wait_until(lambda: "vite 1 di 3" in sheet.inner_text().lower())
    pg.locator(".bed-screws .dialog-close").click()
    ok("closing it while it runs aborts it too", wait_until(lambda: gcodes().count("ABORT") == 2 and pg.locator(".bed-screws").count() == 0))

    # 1.69: while Klipper waits, the sheet stays: after a reload, on another device, after a tap beside it
    open_calibrate(P)
    pg.locator(".oui-menu__item:has-text('Bed screws adjust')").click()
    wait_until(lambda: "vite 1 di 3" in sheet.inner_text().lower())
    sheet.get_by_role("button", name="Regolata", exact=True).click()
    wait_until(lambda: "vite 2 di 3" in sheet.inner_text().lower())
    pg.mouse.click(5, 300)
    P.settle(500)
    ok("1.69: a tap beside the sheet does not close it while Klipper waits", pg.locator(".bed-screws").count() == 1 and gcodes().count("ABORT") == 2)
    pg.reload()
    ok("1.69: after a reload the sheet opens again by itself, at the same screw", wait_until(lambda: pg.locator(".bed-screws").count() == 1 and "vite 2 di 3" in pg.locator(".bed-screws").inner_text().lower(), 10), pg.locator(".bed-screws").inner_text() if pg.locator(".bed-screws").count() else "")
    Q = Page(b, mock, 1440, 900)
    Q.goto("files", 1500)
    ok("1.69: ... and on another device too (a computer, on another page)", wait_until(lambda: Q.pg.locator(".bed-screws").count() == 1 and "vite 2 di 3" in Q.pg.locator(".bed-screws").inner_text().lower(), 10))
    Q.pg.locator(".bed-screws").get_by_role("button", name="Accetta", exact=True).click()
    ok("... an answer on one device moves the other on", wait_until(lambda: "vite 3 di 3" in pg.locator(".bed-screws").inner_text().lower(), 8))
    pg.locator(".bed-screws").get_by_role("button", name="Interrompi", exact=True).click()
    ok("... «Interrompi» on one: both close", wait_until(lambda: pg.locator(".bed-screws").count() == 0 and gcodes().count("ABORT") == 3) and wait_until(lambda: Q.pg.locator(".bed-screws").count() == 0, 8), (pg.locator(".bed-screws").count(), gcodes().count("ABORT"), Q.pg.locator(".bed-screws").count(), Q.pg.locator(".bed-screws").inner_text() if Q.pg.locator(".bed-screws").count() else ""))
    Q.close()
    P.close()

    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
