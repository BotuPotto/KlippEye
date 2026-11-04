"""Release 1.49.0 (roadmap 6d part 8): the G-code viewer. "Vedi i layer" in a file's menu, on the computer's file panel
and on the print card; the file read with a progress bar, drawn layer by layer from above (the slider, ‹ ›, the arrows),
coloured by the slicer's ;TYPE: (a legend that hides a kind), travels and the layer below on request; while that file
prints, "Segui la stampa" shows the layer at the nozzle. Against the mock.
Usage: gcodeviewer_test.py <html> <outdir> <port>"""
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


def wait_until(fn, timeout=8.0, step=0.15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    return bool(fn())


def layer(P):
    c = P.pg.locator(".gcode-canvas")
    return (int(c.get_attribute("data-layer")), int(c.get_attribute("data-layers"))) if c.count() else None


def painted(P):
    """How many pixels of the canvas are coloured (not the background)."""
    return P.pg.evaluate("""() => { const c = document.querySelector('.gcode-canvas'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0;
        for (let i = 0; i < d.length; i += 16) if (d[i + 3] > 60) n++; return n; }""")


def errs(P):
    return [e for e in P.errors if "pageerror" in e or "console.error" in e]


with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("files", 2200)
    pg = P.pg
    card = pg.locator(".file-card", has_text="Bracket").first
    box = card.bounding_box()
    pg.mouse.move(box["x"] + 40, box["y"] + 40)
    pg.mouse.down()
    pg.wait_for_timeout(700)
    pg.mouse.up()
    pg.wait_for_selector(".sheet-overlay--actions")
    pg.wait_for_timeout(500)
    pg.locator(".file-action", has_text="Vedi i layer").click()
    ok("'Vedi i layer' opens the viewer, which reads the file", wait_until(lambda: pg.locator(".gcode-viewer").count() == 1))
    ok("... and draws it: the last layer first", wait_until(lambda: layer(P) is not None, 30) and layer(P)[0] == layer(P)[1] - 1 and layer(P)[1] > 100, layer(P))
    total = layer(P)[1]
    ok("the layer and its height", "Layer %d / %d" % (total, total) in pg.locator(".gcode-layer__label").inner_text() and "Z " in pg.locator(".gcode-layer__label").inner_text(), pg.locator(".gcode-layer__label").inner_text())
    ok("something is drawn", painted(P) > 200, painted(P))
    ok("the legend: the kinds of the slicer's ;TYPE:", [e.get_attribute("data-kind") for e in pg.locator(".gcode-legend__item[data-kind]").all()] == ["outer", "inner", "infill", "support"], [e.get_attribute("data-kind") for e in pg.locator(".gcode-legend__item[data-kind]").all()])
    pg.screenshot(path=out + "/phone.png")
    pg.get_by_role("button", name="Layer sotto").first.click()
    ok("‹: one layer down", wait_until(lambda: layer(P)[0] == total - 2))
    pg.locator(".gcode-layer__range").fill("0")
    ok("the slider: the first layer", wait_until(lambda: layer(P)[0] == 0) and "Layer 1 / " in pg.locator(".gcode-layer__label").inner_text())
    pg.keyboard.press("ArrowUp")
    ok("the arrow keys move too", wait_until(lambda: layer(P)[0] == 1))
    before = painted(P)
    for kind in ("outer", "inner", "infill", "support"):
        pg.locator('.gcode-legend__item[data-kind="%s"]' % kind).click()
    ok("hiding every kind leaves only the layer below", wait_until(lambda: painted(P) < before), (before, painted(P)))
    pg.locator(".gcode-below").click()
    ok("... and without the layer below nothing is left but the grid", wait_until(lambda: painted(P) < 50), painted(P))
    pg.locator(".gcode-travels").click()
    ok("the travels on request", wait_until(lambda: pg.locator(".gcode-travels").get_attribute("aria-pressed") == "true"))
    ok("no horizontal overflow", pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    pg.keyboard.press("Escape")
    ok("Esc closes it", wait_until(lambda: pg.locator(".gcode-viewer").count() == 0))
    ok("no page errors", not errs(P), errs(P)[:2])
    P.close()

    # 1.63: a spiral vase (the height rises at every move): the slicer's ;LAYER_CHANGE marks, 20 layers, not 1200
    mock.reset()
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("files", 2200)
    pg = P.pg
    pg.locator(".file-card", has_text="Vase_mode").first.locator(".file-card__more").click()
    pg.wait_for_selector(".sheet-overlay--actions"); pg.wait_for_timeout(600)
    pg.locator(".file-action", has_text="Vedi i layer").click()
    ok("vase mode: the layers the slicer marks (20), each a whole turn", wait_until(lambda: layer(P) is not None, 30) and layer(P)[1] == 20 and painted(P) > 200, (layer(P), painted(P) if layer(P) else None))
    pg.screenshot(path=out + "/vase.png")
    P.close()

    # following a print
    mock.reset()
    mock.set(printing=True, file_position=60000)
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("home", 2400)
    pg = P.pg
    pg.locator(".gcode-view-btn").first.click()
    ok("the print card's 'Vedi i layer': the file printing, followed", wait_until(lambda: layer(P) is not None, 30) and wait_until(lambda: pg.locator(".gcode-follow").get_attribute("aria-pressed") == "true"))
    ok("... at the nozzle's layer (not the last one)", wait_until(lambda: 0 < layer(P)[0] < layer(P)[1] - 1), layer(P))
    at = layer(P)[0]
    mock.set(file_position=100000)
    ok("... and it moves on with the print", wait_until(lambda: layer(P)[0] > at, 8), (at, layer(P)))
    pg.screenshot(path=out + "/follow.png")
    pg.locator(".gcode-layer__range").fill("3")
    ok("moving the slider stops following", wait_until(lambda: pg.locator(".gcode-follow").get_attribute("aria-pressed") == "false") and layer(P)[0] == 3)
    P.close()

    # computer
    mock.reset()
    P = Page(b, mock, 1440, 900)
    CUR[0] = P
    P.goto("files", 2400)
    P.pg.locator(".desk-detail__layers").click()
    ok("desktop: 'Layer' on the file panel", wait_until(lambda: layer(P) is not None, 30))
    P.pg.mouse.move(700, 400)
    P.pg.mouse.wheel(0, -400)
    P.pg.wait_for_timeout(300)
    P.pg.screenshot(path=out + "/desktop.png")
    ok("desktop: no page errors", not errs(P), errs(P)[:2])
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
