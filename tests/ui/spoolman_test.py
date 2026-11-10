"""Release 1.47.0 (roadmap 6d part 6): Spoolman through Moonraker. The Spool card (Home; on the computer with the fans):
the spool in use with its colour, name, material and what is left; "Cambia bobina" lists Spoolman's spools (last used
first), searched; a tap makes one the active spool, "Nessuna bobina" leaves none; Spoolman unreachable: it says so; no
card without the component. Against the mock.
Usage: spoolman_test.py <html> <outdir> <port>"""
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


def errs(P):
    return [e for e in P.errors if "pageerror" in e or "console.error" in e]


def fresh(b, w=390, h=844, **st):
    mock.reset()
    if st:
        mock.set(**st)
    P = Page(b, mock, w, h)
    CUR[0] = P
    P.goto("home", 2400)
    return P


with sync_playwright() as p:
    b = p.chromium.launch()
    P = fresh(b)
    ok("without Spoolman in Moonraker: no card", P.pg.locator(".spool-card").count() == 0)
    P.close()

    P = fresh(b, spoolman_on=True)
    pg = P.pg
    card = pg.locator(".spool-card")
    ok("the Spool card with the spool in use: Sunlu PETG Orange, 640 g left, 64%", wait_until(lambda: "Sunlu PETG Orange" in card.inner_text()) and "640 g" in card.inner_text() and "64%" in card.inner_text() and "PETG" in card.inner_text(), card.inner_text() if card.count() else "")
    ok("... drawn in its colour", "240, 112, 32" in card.locator(".spool-swatch").get_attribute("style") or "#f07020" in card.locator(".spool-swatch").get_attribute("style").lower(), card.locator(".spool-swatch").get_attribute("style"))
    card.scroll_into_view_if_needed()
    pg.screenshot(path=out + "/card.png")
    card.locator(".spool-change").click()
    picker = pg.locator(".spool-picker")
    ok("'Cambia bobina': Spoolman's spools, the last used first", wait_until(lambda: picker.locator(".spool-choice").count() == 3) and [e.get_attribute("data-spool") for e in picker.locator(".spool-choice").all()] == ["2", "1", "3"])
    ok("... the one in use marked", "In uso" in picker.locator('[data-spool="2"]').inner_text())
    picker.locator(".spool-search").fill("asa")
    ok("search 'asa': the white ASA", wait_until(lambda: picker.locator(".spool-choice").count() == 1) and "ASA White" in picker.inner_text())
    pg.wait_for_timeout(600)
    pg.screenshot(path=out + "/picker.png")
    picker.locator('[data-spool="3"]').click()
    ok("a tap makes it the active spool", wait_until(lambda: state()["spool_id"] == 3) and wait_until(lambda: "ASA White" in card.inner_text()), state()["spool_id"])
    ok("... no weight of its own: the filament's (750 g) makes it full, 100%", "750 g" in card.inner_text() and "100%" in card.inner_text())
    card.locator(".spool-change").click()
    pg.locator(".spool-clear").click()
    ok("'Nessuna bobina': none in use", wait_until(lambda: state()["spool_id"] is None) and wait_until(lambda: "Nessuna bobina in uso" in card.inner_text()))
    ok("no horizontal overflow", pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    ok("no page errors", not errs(P), errs(P)[:2])
    P.close()

    P = fresh(b, spoolman_on=True, spoolman_connected=False)
    ok("Spoolman unreachable: the card says so, no 'Cambia bobina'", wait_until(lambda: "non raggiunge Spoolman" in P.pg.locator(".spool-card").inner_text()) and P.pg.locator(".spool-change").count() == 0)
    P.close()

    # 1.77: the spool in the print's confirmation
    P = fresh(b, spoolman_on=True)
    P.goto("files", 2200)
    P.pg.locator(".file-card", has_text="Benchy").locator('button[aria-label="Avvia stampa"]').first.click()
    row = P.pg.locator(".confirm-card .print-spool")
    ok("1.77: the print's confirmation shows the spool in use (PETG Orange, 640 g left)", wait_until(lambda: row.count() == 1 and "Sunlu PETG Orange" in row.inner_text() and "640 g" in row.inner_text()), row.inner_text() if row.count() else "")
    ok("... and warns: the file is sliced for PLA", wait_until(lambda: "preparato per PLA" in row.inner_text() and "la bobina è PETG" in row.inner_text()), row.inner_text())
    P.pg.screenshot(path=out + "/print-spool.png")
    row.locator(".print-spool__change").click()
    P.pg.locator('.spool-picker [data-spool="1"]').click()
    ok("«Cambia» → the PLA spool: made active, no warning left (12.4 g needed, 120 g left)", wait_until(lambda: state()["spool_id"] == 1) and wait_until(lambda: "PLA Basic Black" in row.inner_text() and "preparato" not in row.inner_text() and "richiede" not in row.inner_text()), row.inner_text())
    ok("... the confirmation is still open", P.pg.locator(".confirm-card .print-spool").count() == 1)
    P.close()

    P = fresh(b, 1440, 900, spoolman_on=True)
    ok("desktop: the card with the fans", wait_until(lambda: P.pg.locator(".desk-slot--spool .spool-card").count() == 1 and "PETG" in P.pg.locator(".spool-card").inner_text()))
    ok("desktop: no page errors", not errs(P), errs(P)[:2])
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
