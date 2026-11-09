"""Release 1.44.0 (roadmap 6d part 3): Moonraker's print queue. "Add to the queue" in a file's menu (with copies) and on
the computer's file panel; the Queue card on the Files page: order, move up / down / to the front, remove, empty, start and
pause; nothing of it without [job_queue]. Against the mock.
Usage: queue_test.py <html> <outdir> <port>"""
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


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def queued():
    return [j["filename"] for j in state()["queue"]]


def rows(P):
    return [t.split("\n") for t in P.pg.locator(".queue-row").all_inner_texts()]


def names(P):
    return [r.locator(".queue-row__name").inner_text() for r in P.pg.locator(".queue-row").all()]


def long_press(P, text):
    card = P.pg.locator(".file-card", has_text=text).first
    card.scroll_into_view_if_needed()
    P.pg.wait_for_timeout(300)
    box = card.bounding_box()
    P.pg.mouse.move(box["x"] + 40, box["y"] + 40)
    P.pg.mouse.down()
    P.pg.wait_for_timeout(700)
    P.pg.mouse.up()
    P.pg.wait_for_selector(".sheet-overlay--actions")
    P.pg.wait_for_timeout(500)


def errs(P):
    return [e for e in P.errors if "pageerror" in e or "console.error" in e]


B, C, V = "Benchy_0.2mm_PLA.gcode", "Calibration_cube_long_filename_for_wrapping_test.gcode", "Vase_mode.gcode"

with sync_playwright() as p:
    b = p.chromium.launch()

    # without [job_queue]
    mock.reset()
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("files", 2200)
    long_press(P, "Benchy")
    ok("without [job_queue]: no 'Aggiungi alla coda' and no Queue card", P.pg.locator(".file-action", has_text="Aggiungi alla coda").count() == 0 and P.pg.locator(".queue-card").count() == 0)
    P.close()

    mock.reset()
    mock.set(queue_on=True, queue_state="paused")
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("files", 2200)
    pg = P.pg
    ok("an empty queue: no card", pg.locator(".queue-card").count() == 0)
    long_press(P, "Benchy")
    pg.locator(".file-action", has_text="Aggiungi alla coda").click()
    dialog = pg.locator(".queue-add")
    ok("'Aggiungi alla coda' asks how many copies, and says the queue is paused", wait_until(lambda: dialog.count() == 1) and "in pausa" in dialog.inner_text(), dialog.inner_text() if dialog.count() else "")
    dialog.get_by_role("button", name="Una in più").click()
    dialog.get_by_role("button", name="Una in più").click()
    ok("... 3 copies", dialog.locator("input").input_value() == "3")
    dialog.locator(".queue-add__confirm").click()
    ok("three Benchy in Moonraker's queue", wait_until(lambda: queued() == [B, B, B]), queued())
    ok("the Queue card appears with them", wait_until(lambda: len(names(P)) == 3))
    long_press(P, "Vase")
    pg.locator(".file-action", has_text="Aggiungi alla coda").click()
    ok("the next one says it goes after the 3 waiting", wait_until(lambda: "dopo le 3" in pg.locator(".queue-add").inner_text()))
    pg.locator(".queue-add__confirm").click()
    ok("the vase at the end", wait_until(lambda: queued() == [B, B, B, V]) and wait_until(lambda: names(P)[-1] == V), queued())
    ok("its estimated time and the total", wait_until(lambda: "circa" in pg.locator(".queue-state").inner_text()) and "2.0h" in pg.locator(".queue-row").first.inner_text(), pg.locator(".queue-card").inner_text())
    pg.screenshot(path=out + "/queue.png", full_page=True)
    pg.locator(".queue-row").nth(3).get_by_role("button", name="Su").click()
    ok("Su: the vase one up (the queue set again in the new order)", wait_until(lambda: queued() == [B, B, V, B]), queued())
    pg.locator(".queue-row").nth(2).get_by_role("button", name="Prima").click()
    ok("'Stampala per prima': to the front", wait_until(lambda: queued() == [V, B, B, B]) and "JUMP" in state()["queue_log"], queued())
    ok("the first has no Su", wait_until(lambda: names(P)[0] == V) and pg.locator(".queue-row").first.get_by_role("button", name="Su").is_disabled())
    pg.locator(".queue-row").nth(1).get_by_role("button", name="Rimuovi dalla coda").click()
    ok("a job removed", wait_until(lambda: queued() == [V, B, B]), queued())
    pg.locator(".queue-start").click()
    ok("'Avvia la coda'", wait_until(lambda: "START" in state()["queue_log"]) and wait_until(lambda: pg.locator(".queue-pause").count() == 1))
    pg.locator(".queue-pause").click()
    ok("'Metti in pausa la coda'", wait_until(lambda: "PAUSE" in state()["queue_log"]) and wait_until(lambda: pg.locator(".queue-start").count() == 1))
    pg.locator(".queue-clear").click()
    pg.locator(".confirm-card").get_by_role("button", name="Svuota").click()
    ok("'Svuota' empties it, and the card goes", wait_until(lambda: queued() == []) and wait_until(lambda: pg.locator(".queue-card").count() == 0))
    ok("no horizontal overflow", pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    ok("no page errors", not errs(P), errs(P)[:2])
    P.close()

    # a free printer and a running queue: it says the first one starts at once
    mock.reset()
    mock.set(queue_on=True, queue_state="ready")
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("files", 2200)
    long_press(P, "Benchy")
    P.pg.locator(".file-action", has_text="Aggiungi alla coda").click()
    ok("free printer, running queue: it warns the print starts at once ('Aggiungi e stampa')", wait_until(lambda: "parte subito" in P.pg.locator(".queue-add").inner_text()) and P.pg.locator(".queue-add__confirm").inner_text() == "Aggiungi e stampa")
    P.pg.locator(".queue-add").get_by_role("button", name="Annulla").click()
    P.close()

    # computer
    mock.reset()
    mock.set(queue_on=True, queue_state="paused", queue=[{"filename": C, "job_id": "0000000001", "time_added": time.time() - 600}])
    P = Page(b, mock, 1440, 900)
    CUR[0] = P
    P.goto("files", 2400)
    ok("desktop: the Queue card over the files", wait_until(lambda: names(P) == [C]), P.pg.locator(".queue-card").inner_text() if P.pg.locator(".queue-card").count() else "")
    P.pg.locator(".desk-detail__queue").click()
    P.pg.locator(".queue-add__confirm").click()
    ok("desktop: 'Coda' on the file panel adds the shown file", wait_until(lambda: queued() == [C, B]), queued())
    P.pg.screenshot(path=out + "/desktop.png")
    ok("desktop: no page errors", not errs(P), errs(P)[:2])
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
