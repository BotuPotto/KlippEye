"""Release 1.70: scheduled prints. «Programma la stampa» in a file's menu and on the computer's file panel (a day, a time,
quick choices), the «Stampe programmate» card on the Files page (waiting, started, not started and why; cancel, remove),
the next one on the computer's idle print card. The KlippEye service starts them (the mock's clock ticks at each read).
Usage: schedule_test.py <html> <outdir> <port>"""
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

def entries():
    return state()["schedule"]


def card_rows(P):
    return [r.get_attribute("data-status") + "|" + r.locator(".schedule-row__name").inner_text() for r in P.pg.locator(".schedule-row").all()]


with sync_playwright() as p:
    b = p.chromium.launch()

    mock.reset()
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("files", 2200)
    pg = P.pg
    ok("nothing scheduled: no card", pg.locator(".schedule-card").count() == 0)
    long_press(P, "Benchy")
    ok("the file's menu has «Programma la stampa»", pg.locator(".file-action", has_text="Programma la stampa").count() == 1)
    pg.locator(".file-action", has_text="Programma la stampa").click()
    dialog = pg.locator(".schedule-add")
    ok("the dialog: the file, the quick choices, a day and a time (in an hour to start with)", wait_until(lambda: dialog.count() == 1) and "Benchy" in dialog.inner_text() and dialog.locator("[data-schedule-quick]").count() >= 2 and "tra 60" in dialog.locator(".schedule-add__when").inner_text().lower(), dialog.inner_text() if dialog.count() else "")
    ok("... and it says to leave the bed clear", "piatto libero" in dialog.inner_text())
    dialog.locator('[data-schedule-quick="morning"]').click()
    ok("«Domani alle 7:00»: tomorrow at 07:00", "Domani alle 07:00" in dialog.locator(".schedule-add__when").inner_text() and dialog.locator("[data-schedule-time]").input_value() == "07:00", dialog.locator(".schedule-add__when").inner_text())
    dialog.locator("[data-schedule-day]").fill("2020-01-01")
    ok("a day gone by: refused, «Programma» off", "orario futuro" in dialog.locator(".schedule-add__when").inner_text() and dialog.locator(".schedule-add__confirm").is_disabled())
    dialog.locator('[data-schedule-quick="morning"]').click()
    pg.screenshot(path=out + "/dialog.png")
    dialog.locator(".schedule-add__confirm").click()
    ok("«Programma»: kept by the service for tomorrow 07:00", wait_until(lambda: len(entries()) == 1 and entries()[0]["filename"] == B and entries()[0]["status"] == "waiting"), entries())
    at = entries()[0]["at"]
    lt = time.localtime(at)
    ok("... at 07:00 local time, tomorrow", lt.tm_hour == 7 and lt.tm_min == 0 and at - time.time() > 0 and at - time.time() < 32 * 3600, time.ctime(at))
    ok("the «Stampe programmate» card appears with it", wait_until(lambda: card_rows(P) == ["waiting|" + B]) and "Domani alle 07:00" in pg.locator(".schedule-card").inner_text(), pg.locator(".schedule-card").inner_text() if pg.locator(".schedule-card").count() else "")
    pg.locator('.schedule-row[data-status="waiting"]').get_by_role("button", name="Annulla la stampa programmata").click()
    ok("cancelling it: gone from the service and from the page", wait_until(lambda: entries() == []) and wait_until(lambda: pg.locator(".schedule-card").count() == 0))
    ok("no horizontal overflow", pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    ok("no page errors", not errs(P), errs(P)[:2])
    P.close()

    # its time comes: started; another one while printing: not started, and why
    mock.reset()
    now = int(time.time())
    mock.set(schedule=[{"id": "a1", "filename": C, "at": now + 4, "created": now, "status": "waiting"}])
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("files", 2200)
    pg = P.pg
    ok("a print scheduled in a few seconds: «tra meno di un minuto»", wait_until(lambda: "meno di un minuto" in pg.locator(".schedule-card").inner_text()))
    P.settle(4500)
    pg.reload(); P.settle(2200)
    ok("at its time the service starts it: «Avviata»", wait_until(lambda: "START:" + C in state()["schedule_log"]) and wait_until(lambda: card_rows(P) == ["started|" + C]), card_rows(P))
    mock.set(printing=True, schedule=entries() + [{"id": "a2", "filename": V, "at": int(time.time()) + 3, "created": now, "status": "waiting"}])
    pg.reload(); P.settle(2200)
    P.settle(3500)
    pg.reload(); P.settle(2200)
    row = pg.locator('.schedule-row[data-schedule="a2"]')
    ok("another one while printing: «Non avviata», the printer was busy", wait_until(lambda: row.count() == 1 and row.get_attribute("data-status") == "missed") and "occupata" in row.inner_text(), row.inner_text() if row.count() else card_rows(P))
    pg.screenshot(path=out + "/card.png", full_page=True)
    row.get_by_role("button", name="Rimuovi dall'elenco").click()
    ok("a finished one removed from the list", wait_until(lambda: [e["id"] for e in entries()] == ["a1"]))
    P.close()

    # computer: the button on the file panel, the next one on the idle print card
    mock.reset()
    P = Page(b, mock, 1440, 900)
    CUR[0] = P
    P.goto("files", 2400)
    P.pg.locator(".desk-detail__schedule").click()
    P.pg.locator('.schedule-add [data-schedule-quick="hour"]').click()
    P.pg.locator(".schedule-add__confirm").click()
    shown = P.pg.locator(".desk-detail").inner_text()
    ok("desktop: «Programma» on the file panel schedules the shown file", wait_until(lambda: len(entries()) == 1) and entries()[0]["filename"] in shown, entries())
    P.pg.screenshot(path=out + "/desktop.png")
    P.pg.evaluate("() => localStorage.setItem('ke_current_tab', 'home')")
    P.pg.reload(); P.settle(2400)
    nxt = P.pg.locator("[data-next-scheduled]")
    ok("desktop: the idle print card says what starts next, and when", wait_until(lambda: nxt.count() == 1) and "Programmata" in nxt.inner_text() and entries()[0]["filename"] in nxt.inner_text() and "Oggi alle" in nxt.inner_text() or "Domani alle" in nxt.inner_text(), nxt.inner_text() if nxt.count() else "")
    ok("desktop: no page errors", not errs(P), errs(P)[:2])
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
