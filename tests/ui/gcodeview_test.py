"""Release 1.40.0 (roadmap 6c part 2): the print files searched by name and in the chosen order (newest / oldest, name,
print time, filament, size, last printed — kept on this device), and «Dettagli» in the long-press menu with what Mainsail
shows of a file (slicer, times, layer heights, filament, temperatures, last print). Against the mock.
Usage: gcodeview_test.py <html> <outdir> <port>"""
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
B, C, V, BR, N = "Benchy_0.2mm_PLA.gcode", "Calibration_cube_long_filename_for_wrapping_test.gcode", "Vase_mode.gcode", "Bracket.gcode", "Nested_part.gcode"


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


def wait_until(fn, timeout=8.0, step=0.2):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    return bool(fn())


def names(P):
    return [t.strip() for t in P.pg.locator(".file-card__name").all_inner_texts()]


def sort(P, key):
    P.pg.locator(".files-sort__btn").click()
    P.pg.wait_for_selector(".oui-menu")
    P.pg.locator('.oui-menu [data-sort="%s"]' % key).click()
    P.settle(300)


with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("files", 2400)
    pg = P.pg
    ok("by default: newest first", wait_until(lambda: names(P) == [B, C, V, BR, N]), names(P))
    sort(P, "name")
    ok("Nome A→Z (the file's name, not its folder)", wait_until(lambda: names(P) == [B, BR, C, N, V]), names(P))
    sort(P, "time")
    ok("Stampa più breve prima (every file's metadata is read for it)", wait_until(lambda: names(P) == [N, V, C, BR, B], 12), names(P))
    sort(P, "time-desc")
    ok("Stampa più lunga prima", wait_until(lambda: names(P) == [B, BR, C, V, N]), names(P))
    sort(P, "filament")
    ok("Più filamento prima (weight, else from the length)", wait_until(lambda: names(P) == [BR, C, B, V, N]), names(P))
    sort(P, "size")
    ok("Più grandi prima", wait_until(lambda: names(P) == [BR, C, B, V, N]), names(P))
    sort(P, "printed")
    ok("Stampati di recente prima (never printed: by name, after)", wait_until(lambda: names(P) == [B, BR, C, N, V]), names(P))
    pg.reload()
    pg.wait_for_timeout(2400)
    ok("the order stays on this device", wait_until(lambda: names(P) == [B, BR, C, N, V], 12) and "Stampati di recente" in pg.locator(".files-sort__btn").inner_text(), names(P))
    sort(P, "oldest")
    ok("Più vecchi prima", wait_until(lambda: names(P) == [N, BR, V, C, B]), names(P))
    search = pg.locator(".files-search__input")
    search.fill("cal")
    ok("search 'cal': only the calibration cube, the count says 1 / 5", wait_until(lambda: names(P) == [C]) and "1 / 5" in pg.locator(".files-sort .oui-badge").inner_text())
    search.fill("test/")
    ok("search by folder: Test/Nested_part", wait_until(lambda: names(P) == [N]))
    search.fill("zzz")
    ok("nothing found says so", wait_until(lambda: "Nessun file contiene «zzz»" in pg.locator(".files-notice").inner_text()))
    search.fill("")
    pg.screenshot(path=out + "/list.png")

    # 1.56: the ⋯ button of a tile opens the same menu (the long press stays)
    pg.locator(".file-card", has_text="Benchy").first.locator(".file-card__more").click()
    ok("the ⋯ button opens the file's menu", wait_until(lambda: pg.locator(".sheet-overlay--actions .file-action", has_text="Dettagli").count() == 1))
    pg.wait_for_timeout(600)  # the menu ignores taps for its first 450 ms (lifting the finger must not pick a row)
    pg.locator(".sheet-overlay--actions .sheet-footer button").click()
    ok("... which closes with Annulla", wait_until(lambda: pg.locator(".sheet-overlay--actions").count() == 0))

    # details
    card = pg.locator(".file-card", has_text="Benchy").first
    box = card.bounding_box()
    pg.mouse.move(box["x"] + 40, box["y"] + 40)
    pg.mouse.down()
    pg.wait_for_timeout(700)
    pg.mouse.up()
    pg.wait_for_selector(".sheet-overlay--actions")
    pg.wait_for_timeout(500)
    ok("the long-press menu has 'Dettagli'", pg.locator(".file-action", has_text="Dettagli").count() == 1)
    pg.locator(".file-action", has_text="Dettagli").click()
    sheet = pg.locator(".file-details")
    ok("the details: slicer, estimated time, layer heights, filament, temperatures, last print",
       wait_until(lambda: "OrcaSlicer 2.1.1" in sheet.inner_text() and "Altezza primo layer" in sheet.inner_text() and "0.25 mm" in sheet.inner_text()
                  and "PLA · Generic PLA" in sheet.inner_text() and "215 °C" in sheet.inner_text() and "60 °C" in sheet.inner_text() and "4.20 m" in sheet.inner_text()
                  and "12.4 g" in sheet.inner_text() and "Ultima stampa" in sheet.inner_text()), sheet.inner_text() if sheet.count() else "")
    pg.screenshot(path=out + "/details.png")
    sheet.get_by_role("button", name="Avvia stampa").click()
    ok("'Avvia stampa' from the details asks to confirm the print", wait_until(lambda: pg.locator(".confirm-card", has_text="Benchy").count() == 1))
    pg.locator(".confirm-card").get_by_role("button", name="Annulla").click()
    P.close()

    # computer
    P = Page(b, mock, 1440, 900)
    CUR[0] = P
    P.goto("files", 2400)
    ok("desktop: the detail panel shows the first file (newest)", wait_until(lambda: "Benchy" in P.pg.locator(".desk-detail__name").inner_text()))
    sort(P, "oldest")
    ok("... and follows the order (oldest first: the nested part)", wait_until(lambda: "Nested_part" in P.pg.locator(".desk-detail__name").inner_text()), P.pg.locator(".desk-detail__name").inner_text())
    P.pg.locator(".desk-detail").get_by_role("button", name="Dettagli").click()
    ok("... and has 'Dettagli'", wait_until(lambda: P.pg.locator(".file-details").count() == 1))
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
