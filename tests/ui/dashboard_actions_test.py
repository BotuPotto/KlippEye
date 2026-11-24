"""1.138.0: nothing in the dashboard moves or restarts the printer unseen. The emergency stop says when it did not go through,
Start / Pause / Cancel / Exclude tell Klipper's refusal, a quick run of jog taps all arrive and a refused jog puts the printer
back in absolute mode, «Save and restart» asks when it cannot tell whether a print runs and does not claim a restart Klipper
refused, a renamed bed mesh profile leaves the mesh in use alone, a dialog opened while idle checks the print lock again when
it is confirmed, and a macro tapped during a print asks first. Against the mock.
Usage: dashboard_actions_test.py <html> <outdir> <port>"""
import json
import os
import re
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
REFUSE = json.dumps({"error": {"code": 400, "message": "Klipper says no (mock)"}})
refuse = lambda r: r.fulfill(status=400, body=REFUSE, content_type="application/json")


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


def wait_until(fn, timeout=5.0, step=0.15):
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


def fresh(b, tab="home", wait=2200, **st):
    mock.reset()
    if st:
        mock.set(**st)
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto(tab, wait)
    return P


def toasts(P):
    return " | ".join(P.pg.locator(".toast").all_inner_texts())


def square(name, x, y, size=30):
    return {"name": name, "center": [x, y], "polygon": [[x - size / 2, y - size / 2], [x + size / 2, y - size / 2], [x + size / 2, y + size / 2], [x - size / 2, y + size / 2]]}


def open_printer_cfg(P):
    P.goto("config", 1800)
    P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^printer.cfg$"))).first.locator(".cfg-row__main").click()
    P.pg.wait_for_selector(".screen--editor .cm-editor")
    P.pg.wait_for_timeout(500)
    P.pg.evaluate("() => { const v = CM.EditorView.findFromDOM(document.querySelector('.screen--editor .cm-editor')); v.dispatch({changes: {from: 0, insert: '# x\\n'}}); }")


with sync_playwright() as p:
    b = p.chromium.launch()

    # ------------------------------------------------------------------ the emergency stop
    P = fresh(b)
    pg = P.pg
    pg.route("**/printer/emergency_stop", lambda r: r.abort("connectionfailed"))
    pg.route("**/printer/gcode/script", lambda r: r.abort("connectionfailed"))
    pg.click('button[aria-label="Arresto di emergenza"]')
    ok("1.138.0: an emergency stop that reaches nobody says so", wait_until(lambda: "arresto" in toasts(P).lower() or "emergency" in toasts(P).lower(), 7), toasts(P))
    P.close()
    P = fresh(b)
    pg = P.pg
    pg.route("**/printer/emergency_stop", refuse)
    pg.route("**/printer/gcode/script", refuse)
    pg.click('button[aria-label="Arresto di emergenza"]')
    ok("1.138.0: ... also when Klipper refuses both requests", wait_until(lambda: "arresto" in toasts(P).lower(), 7), toasts(P))
    P.close()
    P = fresh(b)
    pg = P.pg
    pg.click('button[aria-label="Arresto di emergenza"]')
    pg.wait_for_timeout(1500)
    ok("1.138.0: ... and says nothing when it went through", "arresto" not in toasts(P).lower(), toasts(P))
    P.close()

    # ------------------------------------------------------------------ Start, Pause, Cancel, Exclude read Klipper's answer
    P = fresh(b, "files")
    pg = P.pg
    pg.route("**/printer/print/start", refuse)
    pg.locator(".file-card", has_text="Benchy").first.get_by_role("button", name="Avvia stampa").click()
    pg.wait_for_selector(".confirm-card")
    pg.locator(".confirm-card .oui-btn--primary").click()
    ok("1.138.0: a start Klipper refuses shows Klipper's words", wait_until(lambda: "Klipper says no (mock)" in toasts(P)), toasts(P))
    P.close()

    P = fresh(b, printing=True)
    pg = P.pg
    pg.route("**/printer/gcode/script", refuse)
    pg.get_by_role("button", name="Annulla stampa").first.click()
    pg.wait_for_selector(".confirm-card")
    pg.locator(".confirm-card").get_by_role("button", name="Annulla stampa").click()
    ok("1.138.0: a cancel Klipper refuses shows Klipper's words", wait_until(lambda: "Klipper says no (mock)" in toasts(P)), toasts(P))
    ok("1.138.0: ... and does not say CANCEL_PRINT was sent", "CANCEL_PRINT" not in toasts(P), toasts(P))
    P.close()

    P = fresh(b, printing=True)
    pg = P.pg
    pg.route("**/printer/gcode/script", refuse)
    pg.get_by_role("button", name="Pausa", exact=True).first.click()
    ok("1.138.0: a pause Klipper refuses shows Klipper's words", wait_until(lambda: "Klipper says no (mock)" in toasts(P)), toasts(P))
    P.close()

    P = fresh(b, printing=True, print_objects=[square("BENCHY_A", 100, 100), square("BENCHY_B", 220, 120)])
    pg = P.pg
    pg.route("**/printer/gcode/script", refuse)
    pg.locator("[data-exclude-open]").click()
    pg.wait_for_selector("[data-exclude-dialog]")
    pg.locator('[data-exclude-dialog] [data-object-row="BENCHY_B"]').click()
    pg.click("[data-exclude-confirm]")
    ok("1.138.0: an exclude Klipper refuses stays open with Klipper's words", wait_until(lambda: "Klipper says no (mock)" in pg.locator("[data-exclude-dialog]").inner_text()), pg.locator("[data-exclude-dialog]").inner_text() if pg.locator("[data-exclude-dialog]").count() else "closed")
    P.close()

    # ------------------------------------------------------------------ jog taps
    P = fresh(b)
    pg = P.pg
    before = len(mock.gcode())
    btn = pg.locator("button[data-z='-1']").first
    btn.scroll_into_view_if_needed()
    for _ in range(5):
        btn.click()
        pg.wait_for_timeout(90)
    pg.wait_for_timeout(800)
    sent = [g for g in mock.gcode()[before:] if "G1 Z" in g]
    ok("1.138.0: five quick taps on Z -1 send five moves", len(sent) == 5, sent)
    P.close()

    P = fresh(b)
    pg = P.pg
    before = len(mock.gcode())
    pg.route("**/printer/gcode/script", lambda r: refuse(r) if "G1 Z" in (r.request.post_data or "") else r.continue_())
    pg.locator("button[data-z='-1']").first.click()
    pg.wait_for_timeout(1000)
    after = mock.gcode()[before:]
    ok("1.138.0: a refused jog is followed by G90, so the printer is not left in relative mode", "G90" in after, after)
    P.close()

    # ------------------------------------------------------------------ «Save and restart»
    P = fresh(b, printing=True)
    open_printer_cfg(P)
    P.pg.route(re.compile(r".*/printer/objects/query\?print_stats.*"), lambda r: r.abort())
    P.pg.locator('.editor-save[data-restarts="klipper"]').click()
    P.pg.wait_for_timeout(2500)
    ok("1.138.0: when the print state cannot be read, «Save and restart» asks first", len([d for d in P.dialogs if d[0] == "confirm"]) == 1, P.dialogs)
    P.close()

    P = fresh(b, pending={"probe": {"z_offset": 1.2}})
    open_printer_cfg(P)
    P.pg.route(re.compile(r".*/printer/gcode/script"), refuse)
    P.pg.locator('.editor-save[data-restarts="klipper"]').click()
    seen = []
    for _ in range(14):
        P.pg.wait_for_timeout(250)
        if P.pg.locator(".editor-status").count():
            seen.append(P.pg.locator(".editor-status").inner_text())
    ok("1.138.0: SAVE_CONFIG refused by Klipper: the editor does not say Klipper restarts", not any("riavvia ✓" in s or "riavvia ✓" in s for s in seen), sorted(set(seen)))
    P.close()

    # ------------------------------------------------------------------ the bed mesh rename keeps the mesh in use
    P = fresh(b, "controllo", 2200, mesh=True)
    pg = P.pg
    c = pg.locator(".mesh-card")
    c.scroll_into_view_if_needed()
    pg.wait_for_timeout(500)
    c.locator('[data-profile="adaptive"] button[aria-label="Rinomina adaptive"]').click()
    pg.wait_for_selector(".confirm-card .mesh-name__input")
    pg.locator(".confirm-card .mesh-name__input").fill("fine_bed")
    pg.locator(".confirm-card").get_by_role("button", name="Rinomina", exact=True).click()
    ok("1.138.0: renaming a profile that is not in use leaves the one in use in use", wait_until(lambda: c.locator("[data-active-profile]").get_attribute("data-active-profile") == "default" and "fine_bed" in c.inner_text(), 8), c.locator("[data-active-profile]").get_attribute("data-active-profile"))
    P.close()

    # ------------------------------------------------------------------ a dialog opened while idle, a print starts
    P = fresh(b, "controllo", 2600)
    pg = P.pg
    card = pg.locator(".shaper-card")
    card.scroll_into_view_if_needed()
    pg.wait_for_timeout(1500)
    card.locator('[data-shaper-measure="x"]').click()
    pg.wait_for_selector(".confirm-card")
    pg.wait_for_timeout(300)
    mock.set(printing=True)
    wait_until(lambda: card.locator('[data-shaper-measure="x"]').is_disabled(), 9)
    pg.locator(".confirm-card").get_by_role("button", name="Misura", exact=True).click()
    pg.wait_for_timeout(1200)
    sent = [g for g in mock.gcode() if "SHAPER" in g or "G28" in g]
    ok("1.138.0: «Measure» confirmed after a print started sends nothing", not sent, sent)
    P.close()

    P = fresh(b, "controllo", 2200, mesh=True)
    pg = P.pg
    c = pg.locator(".mesh-card")
    c.scroll_into_view_if_needed()
    pg.wait_for_timeout(500)
    c.locator('[data-profile="adaptive"] button[aria-label="Rinomina adaptive"]').click()
    pg.wait_for_selector(".confirm-card .mesh-name__input")
    pg.locator(".confirm-card .mesh-name__input").fill("fine_bed")
    mock.set(printing=True)
    wait_until(lambda: c.get_by_role("button", name="Calibra mesh", exact=True).is_disabled(), 9)
    pg.locator(".confirm-card").get_by_role("button", name="Rinomina", exact=True).click()
    pg.wait_for_timeout(1200)
    sent = [g for g in mock.gcode() if "BED_MESH" in g]
    ok("1.138.0: a mesh rename confirmed after a print started sends nothing", not sent, sent)
    P.close()

    # ------------------------------------------------------------------ a macro during a print
    P = fresh(b, "controllo", 2600, printing=True)
    pg = P.pg
    card = pg.locator('[data-macro-card="all"]')
    card.scroll_into_view_if_needed()
    pg.wait_for_timeout(800)
    before = len(mock.gcode())
    card.locator(".macro-run, .macro-split-run").first.click()
    pg.wait_for_timeout(800)
    ok("1.138.0: a macro tapped during a print asks first and sends nothing yet", pg.locator(".confirm-card").count() == 1 and len(mock.gcode()) == before, (pg.locator(".confirm-card").count(), mock.gcode()[before:]))
    pg.locator(".confirm-card .oui-btn--danger").click()
    ok("1.138.0: ... and runs it when confirmed", wait_until(lambda: len(mock.gcode()) > before), mock.gcode()[before:])
    P.close()

    P = fresh(b, "controllo", 2600)
    pg = P.pg
    card = pg.locator('[data-macro-card="all"]')
    card.scroll_into_view_if_needed()
    pg.wait_for_timeout(800)
    before = len(mock.gcode())
    card.locator(".macro-run, .macro-split-run").first.click()
    ok("1.138.0: ... and when the printer is idle one tap still runs it", wait_until(lambda: len(mock.gcode()) > before) and pg.locator(".confirm-card").count() == 0, mock.gcode()[before:])
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
