"""Release 1.72: the console's input field: ↑ / ↓ go through the commands sent before (kept on this
device, the line being typed comes back), Tab completes a command's name from Klipper's commands (one match: written
out; several: listed with their help, a tap writes one), Escape closes the list. On the phone card, the full screen and
the computer's bar.
Usage: console_input_test.py <html> <outdir> <port>"""
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


def gcode(script):
    urllib.request.urlopen(urllib.request.Request(mock.base + "/printer/gcode/script", data=json.dumps({"script": script}).encode(), headers={"Content-Type": "application/json"}))


def respond(msg):
    gcode('RESPOND TYPE=command MSG="action:prompt_%s"' % msg)


def sent():
    return state()["gcode_log"]



with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("controllo", 2400)
    pg = P.pg
    field = pg.locator(".oui-card .console-input").first
    field.scroll_into_view_if_needed()
    for cmd in ("G28", "M84", "QUERY_PROBE"):
        field.fill(cmd)
        field.press("Enter")
        P.settle(150)
    ok("three commands sent", wait_until(lambda: sent()[-3:] == ["G28", "M84", "QUERY_PROBE"]), sent()[-3:])
    field.fill("SET_")
    field.press("ArrowUp")
    ok("↑: the last command sent", field.input_value() == "QUERY_PROBE")
    field.press("ArrowUp"); field.press("ArrowUp")
    ok("↑ ↑: the ones before, in order", field.input_value() == "G28")
    field.press("ArrowUp")
    ok("↑ at the oldest: stays there", field.input_value() == "G28")
    field.press("ArrowDown")
    ok("↓: the next one", field.input_value() == "M84")
    field.press("ArrowDown"); field.press("ArrowDown")
    ok("↓ past the newest: the line being typed comes back", field.input_value() == "SET_")
    pg.reload(); P.settle(2400)
    field = pg.locator(".oui-card .console-input").first
    field.scroll_into_view_if_needed()
    field.press("ArrowUp")
    ok("the history stays on this device after a reload", field.input_value() == "QUERY_PROBE")
    field.fill("cle")
    field.press("Tab")
    ok("Tab with one match: the name written out (capitals, a space after it)", wait_until(lambda: field.input_value() == "CLEAN_NOZZLE "), field.input_value())
    ok("... the focus stays in the field", field.evaluate("e => document.activeElement === e"))
    field.fill("SET_")
    field.press("Tab")
    box = pg.locator(".console-suggest").first
    ok("Tab with several: the list above the field, with each command's help", wait_until(lambda: box.count() == 1) and box.locator("[data-suggest]").count() >= 4 and "help for SET_LED" in box.inner_text(), box.inner_text() if box.count() else "")
    ok("... the field has what they share", field.input_value() == "SET_")
    pg.screenshot(path=out + "/phone.png")
    box.locator('[data-suggest="SET_PRESSURE_ADVANCE"]').click()
    ok("a tap on one writes it", field.input_value() == "SET_PRESSURE_ADVANCE " and box.count() == 0)
    field.fill("SET_L"); field.press("Tab")
    ok("Tab: «SET_L» → «SET_LED» (shared start of SET_LED, SET_LED_EFFECT)", wait_until(lambda: field.input_value() == "SET_LED"), field.input_value())
    field.press("Escape")
    ok("Escape closes the list", box.count() == 0)
    field.fill("NOPE"); field.press("Tab")
    P.settle(300)
    ok("Tab with no match: nothing changes", field.input_value() == "NOPE" and box.count() == 0)
    ok("Tab after a space (parameters): nothing happens", (field.fill("G28 X"), field.press("Tab"), P.settle(200), field.input_value())[-1] == "G28 X")
    ok("no page errors", not errs(P), errs(P)[:2])
    P.close()

    # a phone's touch screen: no Tab key, the matches come while typing
    ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, locale="it-IT")
    ctx.add_init_script("try { localStorage.setItem('ke_setup_offered', '1'); localStorage.setItem('klippeye.updates.auto', '0'); } catch (e) {}")
    tp = ctx.new_page()
    tp.route_web_socket("**/websocket", lambda ws: None)
    tp.goto(mock.base + "/", wait_until="domcontentloaded")
    tp.evaluate("() => { localStorage.setItem('ke_current_tab', 'controllo'); }")
    tp.reload(); tp.wait_for_timeout(2600)
    tf = tp.locator(".oui-card .console-input").first
    tf.scroll_into_view_if_needed()
    tf.type("CLE", delay=60)
    tp.wait_for_timeout(600)
    ok("touch screen: typing «CLE» lists CLEAN_NOZZLE, no Tab needed", tp.locator('.console-suggest [data-suggest="CLEAN_NOZZLE"]').count() == 1, tp.locator(".console-suggest").inner_text() if tp.locator(".console-suggest").count() else "none")
    tp.locator('.console-suggest [data-suggest="CLEAN_NOZZLE"]').tap()
    ok("touch screen: a tap writes it", tf.input_value() == "CLEAN_NOZZLE ")
    tf.type("X", delay=40)
    tp.wait_for_timeout(300)
    ok("touch screen: after a space (parameters) no list", tp.locator(".console-suggest").count() == 0)
    ctx.close()

    # the computer's bar
    P = Page(b, mock, 1440, 900)
    CUR[0] = P
    P.goto("home", 2400)
    dock = P.pg.locator(".desk-dock__input")
    dock.click()
    dock.fill("G28"); dock.press("Enter"); P.settle(200)
    dock.press("ArrowUp")
    ok("computer: ↑ in the bar brings back the command sent", dock.input_value() == "G28")
    dock.fill("SHAP"); dock.press("Tab")
    ok("computer: Tab completes in the bar", wait_until(lambda: dock.input_value() == "SHAPER_CALIBRATE "), dock.input_value())
    dock.fill("Z_"); dock.press("Tab")
    ok("computer: one match only (Z_OFFSET_APPLY_…) or a list above the bar", wait_until(lambda: dock.input_value().startswith("Z_") and (dock.input_value().endswith(" ") or P.pg.locator(".console-suggest").count() == 1)))
    P.pg.screenshot(path=out + "/desktop.png")
    dock.fill("M84"); dock.press("Enter")
    ok("computer: Enter sends", wait_until(lambda: sent()[-1] == "M84"))
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
