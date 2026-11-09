"""Release 1.42.0 (roadmap 6d part 1): the print history and its statistics, like Mainsail. The Files page switches between
the print files and the history (kept on this device); the statistics (Moonraker's totals, how the prints ended, the last
14 days), the list (searched, filtered), a job (its figures, a note kept in Moonraker's database, Print again, Remove),
Reset of the totals, and the message when Moonraker keeps no history. Against the mock.
Usage: history_test.py <html> <outdir> <port>"""
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


def db():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/db").read())["db"]


def rows(P):
    return P.pg.locator(".history-row").all_inner_texts()


def stat(P, sid):
    return P.pg.locator('[data-stat="%s"] .history-stat__value' % sid).inner_text()


def errs(P):
    return [e for e in P.errors if "pageerror" in e or "console.error" in e]


def open_history(b, w=390, h=844, reset=True, **st):
    if reset:
        mock.reset()
    if st:
        mock.set(**st)
    P = Page(b, mock, w, h)
    CUR[0] = P
    P.goto("files", 1800)
    P.pg.locator('[data-files-section="history"]').click()
    return P


with sync_playwright() as p:
    b = p.chromium.launch()

    mock.reset()
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("files", 1800)
    pg = P.pg
    ok("the Files page opens on the print files, with the switch", pg.locator(".files-section-switch").count() == 1 and pg.locator('[data-files-section="files"]').get_attribute("aria-pressed") == "true" and pg.locator(".file-card").count() >= 1)
    pg.locator('[data-files-section="history"]').click()
    ok("'Cronologia': six prints, newest first", wait_until(lambda: len(rows(P)) == 6) and "Benchy" in rows(P)[0] and "Nested_part" in rows(P)[-1], rows(P))
    ok("... the print files are gone from the page", pg.locator(".file-card").count() == 0)
    ok("statistics: Moonraker's totals (6 prints, filament 19.0 m, longest 1h 56m)", stat(P, "jobs") == "6" and stat(P, "filament") == "19.0 m" and stat(P, "longest") == "1h 56m", (stat(P, "jobs"), stat(P, "filament"), stat(P, "longest")))
    ok("... 4 of 6 completed: 67%", stat(P, "success") == "67%", stat(P, "success"))
    legend = pg.locator(".history-outcome__legend").inner_text()
    ok("how they ended: 4 completed, 1 cancelled, 1 failed, in words", "Completate\n4" in legend.replace(" ", "\n") or ("Completate" in legend and "4" in legend), legend)
    ok("... one bar in three parts", pg.locator(".history-outcome__part").count() == 3)
    bars = pg.evaluate("() => [...document.querySelectorAll('.history-days__bar')].map(b => b.style.height)")
    ok("the last 14 days: 14 bars, today's the highest (the Benchy)", len(bars) == 14 and bars[-1] == "100%" and bars[0] in ("0%", "0", "0px", ""), bars)
    pg.locator('.history-days__slot[data-day="13"]').click()
    ok("a tap on a bar says its value and day", "1h 56m" in pg.locator(".history-days__readout").inner_text() and "1 stampa" in pg.locator(".history-days__readout").inner_text(), pg.locator(".history-days__readout").inner_text())
    pg.locator('[data-measure="filament"]').click()
    pg.locator('.history-days__slot[data-day="13"]').click()
    ok("... and the filament", wait_until(lambda: "4.20 m" in pg.locator(".history-days__readout").inner_text()), pg.locator(".history-days__readout").inner_text())
    ok("five days with prints; the 20-day-old one is not in the 14 days", sum(1 for x in pg.evaluate("() => [...document.querySelectorAll('.history-days__bar')].map(b => b.style.height)") if x not in ("0%", "0", "0px", "")) == 5)
    pg.screenshot(path=out + "/stats.png", full_page=True)
    ok("a row: thumbnail, status, time, filament", pg.locator(".history-row").first.locator("img").count() == 1 and "Completata" in rows(P)[0] and "1h 56m" in rows(P)[0] and "4.20 m" in rows(P)[0], rows(P)[0])
    ok("a deleted file has no thumbnail", pg.locator('.history-row[data-job="000002"] img').count() == 0)
    pg.locator('[data-filter="failed"]').click()
    ok("filter 'Fallite': the Klipper shutdown", wait_until(lambda: len(rows(P)) == 1) and "Bracket" in rows(P)[0] and "Klipper in shutdown" in rows(P)[0], rows(P))
    pg.locator('[data-filter="cancelled"]').click()
    ok("filter 'Annullate'", wait_until(lambda: len(rows(P)) == 1) and "Calibration" in rows(P)[0])
    pg.locator('[data-filter="all"]').click()
    pg.locator(".history-search").fill("vase")
    ok("search 'vase'", wait_until(lambda: len(rows(P)) == 1) and "Vase" in rows(P)[0] and "1 / 6" in pg.locator(".history-list-card .oui-badge").first.inner_text())
    pg.locator(".history-search").fill("")

    # a job
    pg.locator('.history-row[data-job="000006"]').click()
    sheet = pg.locator(".history-job")
    ok("a tap opens the job: started, ended, times, filament, slicer, file still there", wait_until(lambda: sheet.count() == 1) and all(t in sheet.inner_text() for t in ("Avviata", "Finita", "Tempo di stampa", "Tempo totale", "Filamento usato", "OrcaSlicer 2.1.1", "Ancora sulla stampante")), sheet.inner_text() if sheet.count() else "")
    pg.screenshot(path=out + "/job.png")
    note = sheet.locator(".history-note__input")
    note.fill("Bobina nuova")
    note.blur()
    ok("the note is saved in Moonraker's database", wait_until(lambda: db().get("klippeye/history_notes", {}).get("000006") == "Bobina nuova"), db().get("klippeye/history_notes"))
    sheet.get_by_role("button", name="Stampa di nuovo").click()
    ok("'Stampa di nuovo' asks to confirm the print of that file", wait_until(lambda: pg.locator(".confirm-card", has_text="Conferma").count() == 1 and pg.locator(".history-job").count() == 0))
    pg.locator(".confirm-card").get_by_role("button", name="Annulla").click()
    ok("the note shows in the list", wait_until(lambda: "Bobina nuova" in rows(P)[0]))
    pg.locator(".history-search").fill("bobina")
    ok("... and the search finds it", wait_until(lambda: len(rows(P)) == 1))
    pg.locator(".history-search").fill("")
    pg.locator('.history-row[data-job="000002"]').click()
    ok("a job whose file was deleted: no 'Stampa di nuovo'", wait_until(lambda: pg.locator(".history-job").count() == 1) and pg.locator(".history-reprint").count() == 0 and "Eliminato" in pg.locator(".history-job").inner_text())
    pg.locator(".history-remove").click()
    pg.locator(".confirm-card").get_by_role("button", name="Rimuovi").click()
    ok("'Rimuovi' removes it from Moonraker's history", wait_until(lambda: "DELETE:000002" in state()["history_log"]) and wait_until(lambda: len(rows(P)) == 5))
    pg.locator(".history-reset").click()
    pg.locator(".confirm-card").get_by_role("button", name="Azzera").click()
    ok("'Azzera' resets Moonraker's totals", wait_until(lambda: "RESET" in state()["history_log"]) and wait_until(lambda: stat(P, "filament") != "19.0 m"))
    ok("no horizontal overflow", pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    ok("no page errors", not errs(P), errs(P)[:2])
    pg.reload()
    pg.wait_for_timeout(1800)
    ok("the choice stays on this device", wait_until(lambda: pg.locator(".history-row").count() >= 1) and pg.locator('[data-files-section="history"]').get_attribute("aria-pressed") == "true")
    pg.locator('[data-files-section="files"]').click()
    ok("back to the print files", wait_until(lambda: pg.locator(".file-card").count() >= 1))
    P.close()

    # no [history] in moonraker.conf
    P = open_history(b, history_mode="missing")
    ok("Moonraker without [history]: it says what to add", wait_until(lambda: "[history]" in P.pg.locator(".history-error").inner_text()), P.pg.locator(".history-stats-card").inner_text())
    P.close()

    # 320 px
    P = open_history(b, 320, 640)
    wait_until(lambda: len(rows(P)) == 6)
    ok("[320] nothing sticks out", P.pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    P.close()

    # computer
    P = open_history(b, 1440, 900)
    ok("desktop: statistics and list side by side", wait_until(lambda: len(rows(P)) == 6) and P.pg.locator(".desk-split--history .history-stats-card").count() == 1)
    a = P.pg.locator(".history-stats-card").bounding_box()
    c = P.pg.locator(".history-list-card").bounding_box()
    ok("... the list to the right of the statistics", c["x"] > a["x"] + a["width"] - 1, (a, c))
    P.pg.screenshot(path=out + "/desktop.png")
    ok("desktop: no page errors", not errs(P), errs(P)[:2])
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
