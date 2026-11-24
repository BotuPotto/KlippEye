"""1.153.0: small dashboard fixes. The back button and Escape close a confirmation, the list of Moonraker's components is read
again when Klipper is back, pins that are not lights (a relay, "psu_enabled") are not offered as lights and a pca9632 light is,
«Clear console» does not depend on the phone's clock, a re-sliced file under the same name is read again at the next print,
a stuck camera photo does not freeze the picture, an update that Moonraker answers late is not shown as failed, and the
G-code viewer does not scan every segment on each pan. Against the mock.
Usage: small_fixes_test.py <html> <outdir> <port>"""
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
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63f8cfc0f01f0005000201a5f645400000000049454e44ae426082")


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


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
    try:
        return bool(fn())
    except Exception:
        return False


def fresh(b, tab="home", wait=2200, script=None, ws=None, **st):
    mock.reset()
    if st:
        mock.set(**st)
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    if script:
        P.ctx.add_init_script(script)
    if ws:
        P.pg.route_web_socket("**/websocket", ws)
    P.goto(tab, wait)
    return P


def ws_refuses(ws):
    def on_message(msg):
        try:
            data = json.loads(msg)
        except Exception:
            return
        if isinstance(data, dict) and "id" in data:
            ws.send(json.dumps({"jsonrpc": "2.0", "id": data["id"], "error": {"code": -32601, "message": "Method not found"}}))
    ws.on_message(on_message)


with sync_playwright() as p:
    b = p.chromium.launch()

    # ---- 54: back and Escape close a confirmation
    P = fresh(b)
    pg = P.pg
    pg.click('button[aria-label="Salva configurazione"]')
    ok("1.153.0: the save-config confirmation opens", wait_until(lambda: pg.locator(".confirm-card").count() == 1))
    back = pg.evaluate("() => window.klippeyeBack()")
    ok("1.153.0: the phone's back button closes it", back is True and wait_until(lambda: pg.locator(".confirm-card").count() == 0), back)
    if pg.locator(".confirm-card").count():
        pg.locator(".confirm-card .oui-btn").first.click()
        wait_until(lambda: pg.locator(".confirm-card").count() == 0)
    pg.click('button[aria-label="Salva configurazione"]')
    wait_until(lambda: pg.locator(".confirm-card").count() == 1)
    pg.keyboard.press("Escape")
    ok("1.153.0: Escape closes it", wait_until(lambda: pg.locator(".confirm-card").count() == 0))
    if pg.locator(".confirm-card").count():
        pg.locator(".confirm-card .oui-btn").first.click()
    ok("1.153.0: ... and nothing was sent to the printer", "SAVE_CONFIG" not in state()["gcode_log"], state()["gcode_log"])
    P.close()

    # ---- 55: the components are asked again when Klipper is back
    P = fresh(b, tab="files", timelapse_on=False)
    pg = P.pg
    pg.locator('[data-files-section="timelapse"]').click()
    ok("1.153.0: without the add-on the Timelapse section says how to install it", wait_until(lambda: pg.locator(".timelapse-missing").count() == 1))
    mock.set(webhooks="shutdown")
    wait_until(lambda: pg.locator(".klipper-state").count() == 1, 10)
    mock.set(webhooks="ready", timelapse_on=True)
    ok("1.153.0: Klipper is back: the Timelapse section has the add-on without a reload", wait_until(lambda: pg.locator(".klipper-state").count() == 0 and pg.locator(".timelapse-missing").count() == 0, 15), pg.locator(".files-section-bar").count())
    P.close()

    # ---- 56 and 71: the lights
    P = fresh(b, extra_lights=True, odd_pins=True)
    pg = P.pg
    pg.locator(".light-more").first.click()
    panel = pg.locator(".lights-panel")
    wait_until(lambda: panel.count() == 1)
    rows = [e.get_attribute("data-light") for e in panel.locator(".light-row").all()]
    ok("1.153.0: a relay and «psu_enabled» are not lights; a pca9632 output is", rows == ["m-luci-on", "o-neopixel-strip", "o-output-pin-caselight", "o-pca9632-status"], rows)
    P.close()

    # ---- 60: «Clear console» does not depend on the phone's clock (an hour ahead here)
    sockets = []

    def live_line(ws):
        sockets.append(ws)

        def on_message(msg):
            try:
                data = json.loads(msg)
            except Exception:
                return
            if data.get("method") == "server.gcode_store.subscribe":
                ws.send(json.dumps({"jsonrpc": "2.0", "id": data["id"], "result": {}}))
        ws.on_message(on_message)

    P = fresh(b, script="(() => { const now = Date.now.bind(Date); Date.now = () => now() + 3600e3; })();", tab="controllo", ws=live_line)
    pg = P.pg
    P.settle(1500)
    sockets[-1].send(json.dumps({"jsonrpc": "2.0", "method": "notify_gcode_response", "params": ["// live line"]}))

    def lines():
        return [e.inner_text().strip() for e in pg.locator(".console-well").first.locator(".log-msg").all()]
    ok("1.153.0: the console shows the live line", wait_until(lambda: any("live line" in l for l in lines())), lines())
    pg.locator('button[aria-label="Pulisci la console"]').first.click()
    ok("1.153.0: «Pulisci» empties the view", wait_until(lambda: lines() == []), lines())
    mock.set(console_extra=[{"message": "after the clear", "time": time.time() + 5, "type": "response"}])
    pg.locator(".console-input").first.fill("M115")
    pg.locator(".console-input").first.press("Enter")
    ok("1.153.0: a line of the Raspberry after the clear is shown, the phone's clock an hour ahead", wait_until(lambda: any("after the clear" in l for l in lines()), 8), lines())
    P.close()

    # ---- 61: a re-sliced file with the same name is read again at the next print
    P = fresh(b, printing=True)
    pg = P.pg
    pg.locator("[data-print-more]").click()
    ok("1.153.0: the print card says the slicer's estimate, 1h 40m", wait_until(lambda: "1h 40m" in pg.locator("[data-print-details]").inner_text()), pg.locator("[data-print-details]").inner_text() if pg.locator("[data-print-details]").count() else "")
    mock.set(printing=False)
    P.settle(4500)
    mock.set(printing=True, meta_extra={"estimated_time": 3600})
    wait_until(lambda: pg.locator("[data-print-more]").count() == 1, 8)
    pg.locator("[data-print-more]").click()
    ok("1.153.0: the same file sliced again (1 h): the new estimate at the next print", wait_until(lambda: pg.locator("[data-print-details]").count() == 1 and "Stima dello slicer (stampa intera)\n1h 0m" in pg.locator("[data-print-details]").inner_text(), 12),
       pg.locator("[data-print-details]").inner_text() if pg.locator("[data-print-details]").count() else "no details")
    P.close()

    # ---- 62: a photo that never arrives does not freeze the camera
    settings = {"klippeye/settings": {"camera": {"method": "adaptive", "fps": 5}}}
    P = fresh(b, wait=300, db=settings)
    pg = P.pg
    hits = []

    def snapshot(route):
        hits.append(time.time())
        if len(hits) == 1:
            route.fulfill(status=200, body=PNG, content_type="image/png")
        # the others never get an answer: a half-open connection
    pg.route("**/webcam/?action=snapshot*", snapshot)
    pg.reload()
    wait_until(lambda: len(hits) >= 1, 8)
    ok("1.153.0: a camera photo that never arrives: the next one is asked for anyway", wait_until(lambda: len(hits) >= 3, 25), len(hits))
    P.close()

    # ---- 68: an update that Moonraker answers late is not asked again by HTTP, nor shown as failed
    def silent(ws):
        def on_message(msg):
            try:
                data = json.loads(msg)
            except Exception:
                return
            if isinstance(data, dict) and "id" in data and data.get("method") != "machine.update.upgrade":
                ws.send(json.dumps({"jsonrpc": "2.0", "id": data["id"], "error": {"code": -32601, "message": "Method not found"}}))
        ws.on_message(on_message)

    P = fresh(b, tab="sistema", wait=2500, ws=silent)
    pg = P.pg
    posts = []

    def busy(route):
        posts.append(route.request.url)
        route.fulfill(status=400, content_type="application/json", body=json.dumps({"error": {"code": 400, "message": "Update in progress"}}))
    pg.route("**/machine/update/upgrade", busy)
    pg.route("**/machine/update/full", busy)
    row = pg.locator(".update-row", has_text="klipper").first
    wait_until(lambda: row.locator("button", has_text="Aggiorna").count() >= 1, 8)
    row.locator("button", has_text="Aggiorna").first.click()
    P.settle(400)
    pg.locator(".sheet-footer button", has_text="Aggiorna").click()
    wait_until(lambda: pg.locator(".sheet-card").count() == 0 or "Non riuscito" in pg.locator(".sheet-card").inner_text() or "completato" in pg.locator(".sheet-card").inner_text().lower(), 25)
    text = pg.locator(".sheet-card").inner_text() if pg.locator(".sheet-card").count() else ""
    ok("1.153.0: no answer in 12 s is not shown as «Non riuscito»", "Non riuscito" not in text, text)
    ok("1.153.0: ... and no second upgrade is asked by HTTP", posts == [], posts)
    P.close()

    # ---- 59: the viewer does not scan every segment on each pan
    mock.reset()
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.ctx.add_init_script("""(() => { window.__scans = 0; const typed = Object.getPrototypeOf(Uint8Array.prototype);
      for (const proto of [Array.prototype, typed]) { const some = proto.some; proto.some = function (...args) { if (this.length > 2000) window.__scans += 1; return some.apply(this, args); }; } })();""")
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
    wait_until(lambda: pg.locator(".gcode-canvas").count() == 1, 30)
    P.settle(500)
    canvas = pg.locator(".gcode-canvas").bounding_box()
    pg.evaluate("() => { window.__scans = 0; }")
    pg.mouse.move(canvas["x"] + 100, canvas["y"] + 100)
    pg.mouse.down()
    for step in range(12):
        pg.mouse.move(canvas["x"] + 100 + step * 6, canvas["y"] + 100 + step * 3)
        pg.wait_for_timeout(40)
    pg.mouse.up()
    scans = pg.evaluate("() => window.__scans")
    ok("1.153.0: 12 pointer moves in the viewer do not scan the segments again each time", scans < 12, scans)
    P.close()

    b.close()

print("\n%d failed" % len(FAILS))
sys.exit(1 if FAILS else 0)
