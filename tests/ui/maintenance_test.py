"""Release 1.73: maintenance reminders. On Files → History: «Add» (what to do, every N printing hours / metres of filament /
days, a note), the progress counted from Moonraker's totals since the last time it was done, «Soon» and «To do», «Done»
starts it again, change and remove; kept in Moonraker's database (every device); a message once a day when one is due.
Usage: maintenance_test.py <html> <outdir> <port>"""
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


def db():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/db").read())["db"]


def items():
    return db().get("klippeye/maintenance") or []


def open_history(P):
    P.goto("files", 2200)
    P.pg.locator('.files-section-switch button', has_text="Cronologia").click()
    P.settle(1200)


with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    totals = state_totals = json.loads(urllib.request.urlopen(mock.base + "/server/history/totals").read())["result"]["job_totals"]
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    open_history(P)
    pg = P.pg
    card = pg.locator(".maintenance-card")
    ok("the Maintenance card is on the History page, empty, with a hint", wait_until(lambda: card.count() == 1) and "Ancora nessun promemoria" in card.inner_text(), card.inner_text() if card.count() else "")
    card.locator("[data-maintenance-add]").click()
    dialog = pg.locator(".maintenance-dialog")
    ok("«Aggiungi» opens the dialog", wait_until(lambda: dialog.count() == 1))
    ok("... «Salva» off without a name and an interval", dialog.locator(".maintenance-dialog__save").is_disabled())
    dialog.locator("[data-maintenance-name]").fill("Ingrassa le guide")
    ok("... still off with a name only", dialog.locator(".maintenance-dialog__save").is_disabled())
    dialog.locator('[data-every="hours"]').fill("200")
    dialog.locator('[data-every="days"]').fill("90")
    dialog.locator("textarea").fill("Grasso al litio")
    pg.screenshot(path=out + "/dialog.png")
    dialog.locator(".maintenance-dialog__save").click()
    ok("saved in Moonraker's database, counting from now (today's totals)", wait_until(lambda: len(items()) == 1) and items()[0]["name"] == "Ingrassa le guide" and items()[0]["every"] == {"hours": 200, "metres": 0, "days": 90} and items()[0]["last"]["printTime"] == totals["total_print_time"], items())
    row = card.locator(".maintenance-row").first
    ok("the row: name, OK, 0 of 200 printing hours · 0 of 90 days, the note", wait_until(lambda: row.count() == 1 and row.get_attribute("data-state") == "ok") and "0 di 200 ore di stampa" in row.inner_text() and "0 di 90 giorni" in row.inner_text() and "Grasso al litio" in row.inner_text(), row.inner_text() if row.count() else "")
    # 185 more printing hours: «Tra poco»; 210: «Da fare»
    t = dict(totals); t["total_print_time"] = totals["total_print_time"] + 185 * 3600
    mock.set(history_totals=t)
    pg.reload(); P.settle(2200)
    pg.locator('.files-section-switch button', has_text="Cronologia").click() if pg.locator(".maintenance-card").count() == 0 else None
    row = pg.locator(".maintenance-row").first
    ok("185 h later: «Tra poco», 185 of 200", wait_until(lambda: row.get_attribute("data-state") == "soon", 8) and "185 di 200 ore di stampa" in row.inner_text(), row.inner_text())
    t["total_print_time"] = totals["total_print_time"] + 210 * 3600
    mock.set(history_totals=t)
    pg.evaluate("() => localStorage.removeItem('klippeye.maintenance.announced')")
    pg.reload(); P.settle(800)
    row = pg.locator(".maintenance-row").first
    ok("... and a message says so (once a day on this device)", wait_until(lambda: "Manutenzione da fare: Ingrassa le guide" in pg.evaluate("() => document.body.innerText"), 8), "")
    ok("210 h later: «Da fare»", wait_until(lambda: row.get_attribute("data-state") == "due", 8), row.inner_text())
    pg.screenshot(path=out + "/card.png", full_page=True)
    row.locator(".maintenance-row__done").click()
    ok("«Fatto»: counts again from the totals of now", wait_until(lambda: items()[0]["last"]["printTime"] == t["total_print_time"]) and wait_until(lambda: row.get_attribute("data-state") == "ok"), items())
    pg.reload(); P.settle(2600)
    ok("... the message is not repeated the same day", "Manutenzione da fare" not in pg.evaluate("() => document.body.innerText"))
    # Moonraker's totals reset: what was counted since is used, never a negative number
    t2 = dict(t); t2["total_print_time"] = 3 * 3600
    mock.set(history_totals=t2)
    pg.reload(); P.settle(2400)
    row = pg.locator(".maintenance-row").first
    ok("totals reset: the counter shows what was printed since (3 h), not a negative", wait_until(lambda: "3 di 200 ore di stampa" in row.inner_text(), 8), row.inner_text())
    # change and remove
    row.locator(".maintenance-row__main").click()
    dialog = pg.locator(".maintenance-dialog")
    ok("a tap on the row opens it to change it", wait_until(lambda: dialog.count() == 1) and dialog.locator("[data-maintenance-name]").input_value() == "Ingrassa le guide" and dialog.locator('[data-every="hours"]').input_value() == "200")
    dialog.locator('[data-every="metres"]').fill("500")
    dialog.locator(".maintenance-dialog__save").click()
    ok("changed: 500 m of filament too, the count kept", wait_until(lambda: items()[0]["every"]["metres"] == 500) and items()[0]["last"]["printTime"] == t["total_print_time"], items())
    ok("... the row says the metres too", wait_until(lambda: "di 500 m di filamento" in row.inner_text()), row.inner_text())
    # another device sees it
    Q = Page(b, mock, 1440, 900)
    Q.goto("files", 2200)
    Q.pg.locator('.files-section-switch button', has_text="Cronologia").click()
    ok("a computer sees the same reminder (Moonraker's database)", wait_until(lambda: Q.pg.locator(".maintenance-row").count() == 1, 8))
    Q.pg.screenshot(path=out + "/desktop.png")
    Q.close()
    row.locator(".maintenance-row__main").click()
    pg.locator(".maintenance-dialog .oui-btn--danger").click()
    ok("«Rimuovi»: gone", wait_until(lambda: items() == []) and wait_until(lambda: pg.locator(".maintenance-row").count() == 0))
    ok("no horizontal overflow", pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    ok("no page errors", not errs(P), errs(P)[:2])
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
