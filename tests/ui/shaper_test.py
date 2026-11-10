"""Release 1.80: the input shaper graphs (Control on the phone, Calibration on the computer): the files SHAPER_CALIBRATE
leaves in /tmp (made up by the mock, read by the real backend/shaper_data.py), the shaper printer.cfg sets, a row chosen,
«Try …» (SET_INPUT_SHAPER), «Measure X/Y» (SHAPER_CALIBRATE, after G28 when not homed), no files.
Usage: shaper_test.py <html> <outdir> <port>"""
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




def gcodes():
    return state()["gcode_log"]


def peak(card):
    return float(card.locator(".shaper-chart__peak-label").text_content().split()[0].replace(",", "."))


def open_page(b, w, hh, **st):
    mock.reset()
    if st:
        mock.set(**st)
    P = Page(b, mock, w, hh)
    CUR[0] = P
    P.goto("controllo", 2600)
    card = P.pg.locator(".shaper-card")
    wait_until(lambda: card.count() == 1, 8)
    card.scroll_into_view_if_needed()  # the cards below the screen fill in when they come into view
    return P


with sync_playwright() as p:
    b = p.chromium.launch()
    for w, hh in ((390, 844), (1440, 900)):
        P = open_page(b, w, hh)
        pg = P.pg
        card = pg.locator(".shaper-card")
        ok("%d: the card, with the shaper printer.cfg sets" % w, wait_until(lambda: card.count() == 1 and "X MZV 52,4 Hz" in card.locator("[data-shaper-current]").inner_text() and "Y EI 55 Hz" in card.locator("[data-shaper-current]").inner_text(), 8), card.evaluate("e => e.outerHTML.slice(0, 900)") if card.count() else "no card")
        ok("%d: X first: the vibrations and four shapers, the peak at 52 Hz" % w, wait_until(lambda: card.locator(".shaper-chart[data-axis=x] .shaper-chart__psd").count() == 1 and card.locator(".shaper-chart__shaper").count() == 4 and abs(peak(card) - 52) < 1.5, 8), [card.locator(".shaper-chart[data-axis=x] .shaper-chart__psd").count(), card.locator(".shaper-chart__shaper").count(), card.locator(".shaper-chart__peak-label").count()])
        rows = card.locator("[data-shaper-row]")
        ok("%d: the rows: MZV in use, the vibrations left" % w, rows.count() == 4 and "in uso" in card.locator('[data-shaper-row="mzv"]').inner_text() and "rimaste" in rows.first.inner_text(), card.locator(".shaper-list").inner_text())
        ok("%d: one row says it leaves the fewest vibrations" % w, card.locator(".shaper-row__tag.is-best").count() <= 1 and (card.locator(".shaper-row__tag.is-best").count() == 1 or "in uso" in card.locator(".shaper-list").inner_text()))
        if w == 390:
            pg.screenshot(path=out + "/phone_x.png", full_page=False)
            # the pointer on the chart: the frequency and the chosen shaper
            card.locator('[data-shaper-row="zv"]').click()
            ok("a row chosen: its line stands out, the others dim", wait_until(lambda: card.locator('.shaper-chart__shaper.is-selected[data-shaper="zv"]').count() == 1 and card.locator(".shaper-chart__shaper.is-dim").count() == 3))
            box = card.locator(".shaper-chart__svg").bounding_box()
            pg.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + box["height"] / 2)
            ok("the pointer: the frequency and what ZV lets through", wait_until(lambda: "Hz" in card.locator(".shaper-chart__tip").inner_text() and "ZV lascia passare" in card.locator(".shaper-chart__tip").inner_text()), card.locator(".shaper-chart__tip").inner_text() if card.locator(".shaper-chart__tip").count() else "")
            pg.mouse.move(5, 5)
            card.locator('[data-shaper-apply="zv"]').click()
            ok("«Try ZV»: SET_INPUT_SHAPER for X with ZV's frequency", wait_until(lambda: any(g.startswith("SET_INPUT_SHAPER SHAPER_TYPE_X=zv SHAPER_FREQ_X=58.2") for g in state()["gcode_log"])), state()["gcode_log"][-3:])
            card.locator('[data-shaper-axis="y"]').click()
            ok("the Y axis: its own measurement (peak at 44 Hz), EI in use, nothing chosen", wait_until(lambda: card.locator(".shaper-chart[data-axis=y]").count() == 1 and abs(peak(card) - 44) < 1.5 and "in uso" in card.locator('[data-shaper-row="ei"]').inner_text() and card.locator(".shaper-row.is-selected").count() == 0, 8))
            card.locator('[data-shaper-measure="y"]').click()
            dialog = pg.locator(".confirm-card")
            ok("«Measure Y» asks first", wait_until(lambda: dialog.count() == 1 and "Misurare l'asse Y?" in dialog.inner_text()))
            pg.screenshot(path=out + "/phone_measure.png")
            dialog.locator(".oui-btn--primary").click()
            ok("then SHAPER_CALIBRATE AXIS=Y (homed already: no G28)", wait_until(lambda: "SHAPER_CALIBRATE AXIS=Y" in state()["gcode_log"]), state()["gcode_log"][-3:])
        ok("%d: no horizontal overflow, no page errors" % w, pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth") and not errs(P), errs(P)[:2])
        if w == 1440:
            pg.screenshot(path=out + "/desktop.png", full_page=False)
        P.close()

    # not homed: the measurement homes first
    P = open_page(b, 390, 844, homed="")
    card = P.pg.locator(".shaper-card")
    wait_until(lambda: card.locator('[data-shaper-measure="x"]').count() == 1, 8)
    card.locator('[data-shaper-measure="x"]').click()
    ok("not homed: the dialog says the axes are homed first", wait_until(lambda: "homing" in P.pg.locator(".confirm-card").inner_text()))
    P.pg.locator(".confirm-card .oui-btn--primary").click()
    ok("not homed: G28, then SHAPER_CALIBRATE AXIS=X", wait_until(lambda: "G28\nSHAPER_CALIBRATE AXIS=X" in state()["gcode_log"] or state()["gcode_log"][-2:] == ["G28", "SHAPER_CALIBRATE AXIS=X"]), state()["gcode_log"][-3:])
    P.close()

    # no files: said in words, the buttons still there
    P = open_page(b, 390, 844, shaper_files=False)
    card = P.pg.locator(".shaper-card")
    ok("no measurement: said in words, «Measure X» / «Measure Y» there", wait_until(lambda: card.locator("[data-shaper-empty]").count() == 1 and card.locator("[data-shaper-measure]").count() == 2, 8), card.inner_text() if card.count() else "")
    ok("no measurement: no chart, no page errors", card.locator(".shaper-chart").count() == 0 and not errs(P), errs(P)[:2])
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
