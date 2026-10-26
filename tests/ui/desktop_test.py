"""Functional test of the wide (desktop) layout: tabs, device page, files + detail panel, inline config editor
with its unsaved-changes guards, console bar, the 1100 px breakpoint. Usage: desktop_test.py <html> <outdir> <port>"""
import sys, os, re, json
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
FAILS = []


def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra != "" else ""))


def fresh(w=1440, h=900, tab="home", wait=1800, **state):
    mock.reset()
    if state: mock.set(**state)
    P = Page(b, mock, w, h)
    P.goto(tab, wait)
    return P


def go(P, label):
    P.pg.locator(".header-tabs button", has_text=re.compile("^" + label + "$")).click(); P.pg.wait_for_timeout(700)


def tab_stored(P): return P.pg.evaluate("() => localStorage.getItem('ke_current_tab')")
# the browser logs every 502/503 answer as a console error; "Salva e riavvia" restarts Klipper (the mock answers 503 while it is down), which is expected
def errs(P): return [e for e in P.errors if ("pageerror" in e or "console.error" in e) and not re.search(r"Failed to load resource: the server responded with a status of 50[23]", e)]
def gl(prefix=""): return [g for g in mock.gcode() if g.startswith(prefix)]
def overflow(P): return P.pg.evaluate("() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, sh: document.documentElement.scrollHeight, ch: document.documentElement.clientHeight})")


with sync_playwright() as p:
    b = p.chromium.launch()

    # ------------------------------------------------------------------ shell + tabs
    P = fresh()
    ok("wide layout active (is-wide + desk-app)", P.pg.evaluate("() => document.documentElement.classList.contains('is-wide')") and P.pg.locator(".desk-app").count() == 1)
    ok("no bottom bar, no pull-to-refresh on the wide layout", P.pg.locator("#vz-custom-bottom-nav, .bottom-nav").count() == 0)
    ok("five tabs in the header", P.pg.locator(".header-tabs button").all_inner_texts() == ["Dispositivo", "Calibrazione", "File", "Config", "Sistema"], P.pg.locator(".header-tabs button").all_inner_texts())
    ok("state pill says Pronta", "Pronta" in P.pg.locator(".header-state").inner_text(), P.pg.locator(".header-state").inner_text())
    ov = overflow(P); ok("page does not scroll as a whole", ov["sw"] <= ov["cw"] and ov["sh"] <= ov["ch"], ov)
    ok("console bar present on the device page", P.pg.locator(".desk-dock").count() == 1)
    for label, marker, stored in [("Calibrazione", ".desk-split", "controllo"), ("File", ".desk-split--files", "files"), ("Config", ".desk-split--config", "config"), ("Sistema", ".desk-system", "sistema"), ("Dispositivo", ".desk-device", "home")]:
        go(P, label)
        ok(f"tab {label}: page shown, tab remembered, dock still there", P.pg.locator(marker).count() >= 1 and tab_stored(P) == stored and P.pg.locator(".desk-dock").count() == 1, (stored, tab_stored(P)))
        ov = overflow(P); ok(f"tab {label}: no page scroll", ov["sw"] <= ov["cw"] and ov["sh"] <= ov["ch"], ov)
    ok("no errors across the tabs", not errs(P), errs(P)[:3])
    P.close()

    # a stored phone tab opens the matching wide page
    P = fresh(tab="controllo")
    ok("stored tab 'controllo' opens Calibrazione", P.pg.locator(".header-tabs button.is-active", has_text="Calibrazione").count() == 1 or "Calibrazione" in P.pg.locator(".header-tabs [aria-current], .header-tabs .is-active, .header-tabs [aria-selected=true]").all_inner_texts().__str__())
    P.close()

    # ------------------------------------------------------------------ device page: idle vs printing
    P = fresh()
    ok("idle: Movimento + Estrusore present, Z-offset absent", P.pg.locator(".desk-slot--motion .oui-card-title:text-is('Movimento')").count() == 1 and P.pg.locator(".desk-slot--extruder").count() == 1 and P.pg.locator(".desk-slot--motion .oui-card-title:text-is('Z-offset')").count() == 0)
    ok("idle: 'Scegli un file da stampare' leads to File", (P.pg.locator(".desk-print__cta").click(), P.pg.wait_for_timeout(600), P.pg.locator(".desk-split--files").count())[2] == 1)
    P.close()
    P = fresh(printing=True)
    ok("printing: progress card with file name", "Benchy_0.2mm_PLA.gcode" in P.pg.locator(".desk-print").inner_text() and "42%" in P.pg.locator(".desk-print").inner_text(), P.pg.locator(".desk-print").inner_text()[:80])
    ok("printing: Z-offset in place of Movimento, no extruder", P.pg.locator(".desk-slot--motion .oui-card-title:text-is('Z-offset')").count() == 1 and P.pg.locator(".desk-slot--extruder").count() == 0)
    P.pg.locator(".desk-print button:has-text('Pausa')").click(); P.pg.wait_for_timeout(700)
    ok("Pausa sends PAUSE", any(g.startswith("PAUSE") for g in mock.gcode()), mock.gcode()[-3:])
    P.pg.locator(".desk-print button:has-text('Cancella stampa')").click(); P.pg.wait_for_timeout(500)
    ok("Cancella stampa asks first", P.pg.locator(".confirm-overlay").count() == 1)
    P.pg.locator(".confirm-card .oui-btn").first.click(); P.pg.wait_for_timeout(300)
    ok("printing: tap on a temperature opens the editor sheet", (P.pg.locator(".desk-slot--heaters .heater-tile, .desk-slot--heaters button").first.click(), P.pg.wait_for_timeout(500), P.pg.locator(".sheet-overlay, .modal-card, .confirm-overlay").count())[2] >= 1)
    ok("no errors on the device page", not errs(P), errs(P)[:3]); P.close()

    # ------------------------------------------------------------------ console bar
    P = fresh()
    inp = P.pg.locator(".desk-dock__input")
    inp.fill("M105"); inp.press("Enter"); P.pg.wait_for_timeout(500)
    ok("console bar sends the command with Enter and clears the field", "M105" in gl() and inp.input_value() == "", (gl()[-3:], inp.input_value()))
    inp.fill("G28 X"); P.pg.locator(".desk-dock__send").click(); P.pg.wait_for_timeout(500)
    ok("send button sends too", "G28 X" in gl(), gl()[-3:])
    inp.fill("   "); P.pg.locator(".desk-dock__send").click(); P.pg.wait_for_timeout(200)
    ok("empty command is not sent", gl().count("") == 0 and not any(g.strip() == "" for g in gl()))
    P.pg.locator(".desk-dock__expand").click(); P.pg.wait_for_timeout(500)
    ok("arrow opens the full console above the bar", P.pg.locator(".desk-drawer").count() == 1 and P.pg.locator(".desk-drawer .log-time").count() >= 3)
    bb = P.pg.locator(".desk-drawer").bounding_box(); dk = P.pg.locator(".desk-dock").bounding_box()
    ok("drawer sits right above the bar and inside the window", bb["y"] >= 0 and bb["y"] + bb["height"] <= dk["y"] + 1, (bb, dk))
    P.pg.screenshot(path=f"{out}/drawer.png", animations="disabled")
    P.pg.locator(".desk-drawer .log-line, .desk-drawer [class*=log-row], .desk-drawer .oui-mono").first.click(); P.pg.wait_for_timeout(200)
    P.pg.keyboard.press("Escape"); P.pg.wait_for_timeout(300)
    ok("Esc closes the drawer", P.pg.locator(".desk-drawer").count() == 0)
    P.pg.locator(".desk-dock__title").click(); P.pg.wait_for_timeout(300)
    ok("'Console' title toggles it open", P.pg.locator(".desk-drawer").count() == 1)
    P.pg.locator(".desk-dock__title").click(); P.pg.wait_for_timeout(300)
    ok("…and closed again", P.pg.locator(".desk-drawer").count() == 0)
    ok("no errors on the console bar", not errs(P), errs(P)[:3]); P.close()

    # ------------------------------------------------------------------ files page
    P = fresh(tab="files")
    tiles = P.pg.locator(".desk-col--files .file-card")
    ok("files: tiles listed", tiles.count() >= 4, tiles.count())
    ok("files: first file selected by default and detail shown", P.pg.locator(".file-card.is-selected").count() == 1 and P.pg.locator(".desk-detail").count() == 1)
    first_name = P.pg.locator(".desk-detail__name").inner_text()
    tiles.nth(1).click(); P.pg.wait_for_timeout(500)
    ok("files: a click selects another file and the detail follows", P.pg.locator(".desk-detail__name").inner_text() != first_name and P.pg.locator(".file-card.is-selected").count() == 1, (first_name, P.pg.locator(".desk-detail__name").inner_text()))
    ok("files: detail has the facts and the three actions", P.pg.locator(".desk-fact").count() >= 3 and P.pg.locator(".desk-detail__actions button").all_inner_texts() == ["Scarica", "Editor", "Elimina"], P.pg.locator(".desk-detail__actions button").all_inner_texts())
    P.pg.screenshot(path=f"{out}/files_detail.png", animations="disabled")
    # download
    with P.pg.expect_download(timeout=8000) as dl:
        P.pg.locator(".desk-detail__actions button", has_text="Scarica").click()
    ok("files: Scarica downloads the gcode", dl.value.suggested_filename.endswith(".gcode"), dl.value.suggested_filename)
    # print
    P.pg.locator(".desk-detail__print").click(); P.pg.wait_for_timeout(500)
    ok("files: Avvia stampa opens the confirmation", P.pg.locator(".confirm-overlay").count() == 1 and ".gcode" in P.pg.locator(".confirm-overlay").inner_text())
    P.pg.locator(".confirm-card .oui-btn").first.click(); P.pg.wait_for_timeout(400)
    ok("files: cancelling does not start anything", not any("SDCARD_PRINT_FILE" in g or "print/start" in g for g in mock.gcode()), mock.gcode()[-3:])
    # delete: cancel then confirm
    name_before = P.pg.locator(".desk-detail__name").inner_text()
    P.pg.locator(".desk-detail__actions button", has_text="Elimina").click(); P.pg.wait_for_timeout(500)
    ok("files: Elimina asks first", P.pg.locator(".confirm-overlay").count() == 1)
    P.pg.locator(".confirm-card .oui-btn").first.click(); P.pg.wait_for_timeout(400)
    ok("files: cancel keeps the file", not gl("DELETE:") and P.pg.locator(".desk-detail__name").inner_text() == name_before)
    P.pg.locator(".desk-detail__actions button", has_text="Elimina").click(); P.pg.wait_for_timeout(500)
    P.pg.locator(".confirm-card .oui-btn").last.click(); P.pg.wait_for_timeout(1500)
    ok("files: confirmed delete calls the backend and the detail moves on", len(gl("DELETE:")) == 1 and P.pg.locator(".desk-detail__name").inner_text() != name_before and P.pg.locator(".file-card.is-selected").count() == 1, (gl("DELETE:"), P.pg.locator(".desk-detail__name").inner_text()))
    # editor on a gcode (full-screen overlay, not the inline one)
    P.pg.locator(".desk-detail__actions button", has_text="Editor").click(); P.pg.wait_for_timeout(1200)
    ok("files: Editor opens the gcode in the editor", P.pg.locator(".screen--editor").count() == 1 and P.pg.locator(".screen--editor.screen--inline").count() == 0)
    P.pg.screenshot(path=f"{out}/files_editor.png", animations="disabled")
    P.pg.locator(".editor-close").click(); P.pg.wait_for_timeout(500)
    ok("files: editor closes back to the page", P.pg.locator(".screen--editor").count() == 0 and P.pg.locator(".desk-split--files").count() == 1)
    ok("no errors on the files page", not errs(P), errs(P)[:3]); P.close()

    # empty list
    P = fresh(tab="files")
    for _ in range(0): pass
    P.close()

    # ------------------------------------------------------------------ config page + inline editor
    P = fresh(tab="config")
    ok("config: placeholder while nothing is open", P.pg.locator(".desk-empty").count() == 1 and P.pg.locator(".screen--editor").count() == 0)
    P.pg.screenshot(path=f"{out}/config_empty.png", animations="disabled")
    def cfg_row(name): return P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^" + re.escape(name) + "$"))).first
    cfg_row("printer.cfg").locator(".cfg-row__main").click(); P.pg.wait_for_timeout(1200)
    ok("config: file opens inline next to the list", P.pg.locator(".desk-editor .screen--inline").count() == 1 and "printer.cfg" in P.pg.locator(".desk-editor .editor-title").inner_text() and P.pg.locator(".desk-empty").count() == 0)
    ok("config: list stays visible beside the editor", cfg_row("moonraker.conf").is_visible())
    ed = P.pg.locator(".editor-input")
    ok("config: editor holds the file text", "stepper_x" in ed.input_value(), ed.input_value()[:40])
    ok("config: Salva disabled while nothing changed", P.pg.locator(".editor-save", has_text=re.compile("^Salva$")).is_disabled())
    bb = P.pg.locator(".desk-editor").bounding_box(); vp = P.pg.viewport_size
    dk = P.pg.locator(".desk-dock").bounding_box()
    ok("config: editor fits above the console bar", bb["y"] + bb["height"] <= dk["y"] + 1, (bb, dk))
    P.pg.screenshot(path=f"{out}/config_editor.png", animations="disabled")
    # edit -> dirty
    ed.click(); P.pg.keyboard.press("Control+End"); P.pg.keyboard.type("\n; prova\n"); P.pg.wait_for_timeout(300)
    ok("config: typing enables Salva", P.pg.locator(".editor-save", has_text=re.compile("^Salva$")).is_enabled())
    # another file in the list -> guard
    cfg_row("moonraker.conf").locator(".cfg-row__main").click(); P.pg.wait_for_timeout(500)
    ok("guard: opening another file asks first", P.pg.locator(".confirm-overlay").count() == 1 and "Modifiche non salvate" in P.pg.locator(".confirm-overlay").inner_text(), P.pg.locator(".confirm-overlay").inner_text()[:60])
    P.pg.screenshot(path=f"{out}/config_guard.png", animations="disabled")
    P.pg.locator(".confirm-card .oui-btn").first.click(); P.pg.wait_for_timeout(400)
    ok("guard: Annulla keeps printer.cfg and the typed text", "printer.cfg" in P.pg.locator(".desk-editor .editor-title").inner_text() and "; prova" in P.pg.locator(".editor-input").input_value())
    # tab switch -> guard
    go(P, "File")
    ok("guard: switching tab asks first and stays", P.pg.locator(".confirm-overlay").count() == 1 and tab_stored(P) == "config", tab_stored(P))
    P.pg.locator(".confirm-card .oui-btn").first.click(); P.pg.wait_for_timeout(400)
    ok("guard: Annulla stays on Config with the edit", P.pg.locator(".desk-split--config").count() == 1 and "; prova" in P.pg.locator(".editor-input").input_value())
    # save
    P.pg.locator(".editor-save", has_text=re.compile("^Salva$")).click(); P.pg.wait_for_timeout(1200)
    ok("save: upload to config/printer.cfg", gl("UPLOAD:") and gl("UPLOAD:")[-1] == "UPLOAD:/printer.cfg", gl("UPLOAD:"))
    ok("save: no longer dirty (Salva disabled) and the file stays open", P.pg.locator(".editor-save", has_text=re.compile("^Salva$")).is_disabled() and "printer.cfg" in P.pg.locator(".desk-editor .editor-title").inner_text())
    ok("save: status says Salvato", "Salvato" in P.pg.locator(".editor-status").inner_text(), P.pg.locator(".editor-status").inner_text())
    P.pg.locator(".editor-input").click(); P.pg.keyboard.press("Control+End"); P.pg.keyboard.type("y"); P.pg.wait_for_timeout(250)
    ok("typing again clears 'Salvato' and re-enables Salva", P.pg.locator(".editor-status").inner_text() == "" and P.pg.locator(".editor-save", has_text=re.compile("^Salva$")).is_enabled(), P.pg.locator(".editor-status").inner_text())
    P.pg.locator(".editor-save", has_text="Salva e riavvia").click(); P.pg.wait_for_timeout(1500)
    ok("Salva e riavvia: uploads, sends SAVE_CONFIG and stays open", len(gl("UPLOAD:")) == 2 and any("SAVE_CONFIG" in g for g in mock.gcode()) and P.pg.locator(".desk-editor .screen--inline").count() == 1, (gl("UPLOAD:"), mock.gcode()[-3:], P.pg.locator(".editor-status").inner_text()))
    ok("…status shows SAVE_CONFIG inviato", "SAVE_CONFIG" in P.pg.locator(".editor-status").inner_text(), P.pg.locator(".editor-status").inner_text())
    cfg_row("moonraker.conf").locator(".cfg-row__main").click(); P.pg.wait_for_timeout(900)
    ok("after saving, another file opens without any question", P.pg.locator(".confirm-overlay").count() == 0 and "moonraker.conf" in P.pg.locator(".desk-editor .editor-title").inner_text(), P.pg.locator(".desk-editor .editor-title").inner_text())
    # dirty again -> Continua really discards
    ed = P.pg.locator(".editor-input"); ed.click(); P.pg.keyboard.press("Control+End"); P.pg.keyboard.type("x"); P.pg.wait_for_timeout(250)
    go(P, "Sistema")
    ok("guard 2: tab switch asks", P.pg.locator(".confirm-overlay").count() == 1)
    P.pg.locator(".confirm-card .oui-btn").last.click(); P.pg.wait_for_timeout(900)
    ok("guard 2: Continua goes to Sistema", P.pg.locator(".desk-system").count() == 1 and tab_stored(P) == "sistema", tab_stored(P))
    go(P, "Config")
    ok("coming back to Config shows the placeholder (no stale editor, discarded edit not saved)", P.pg.locator(".desk-empty").count() == 1 and len(gl("UPLOAD:")) == 2, (P.pg.locator(".desk-empty").count(), gl("UPLOAD:")))
    # close button (the editor's own guard)
    cfg_row("crowsnest.conf").locator(".cfg-row__main").click(); P.pg.wait_for_timeout(900)
    P.pg.locator(".editor-input").click(); P.pg.keyboard.type("z"); P.pg.wait_for_timeout(200)
    P.pg.locator(".editor-close").click(); P.pg.wait_for_timeout(400)
    ok("close with unsaved edit asks (editor's own dialog)", P.pg.locator(".confirm-overlay").count() == 1, P.pg.locator(".confirm-overlay").count())
    P.pg.locator(".confirm-card .oui-btn").last.click(); P.pg.wait_for_timeout(500)
    ok("…and Continua closes the editor back to the placeholder", P.pg.locator(".desk-empty").count() == 1 and P.pg.locator(".screen--editor").count() == 0)
    # image opens full screen (viewer), not inline
    cfg_row("img").locator(".cfg-row__main").click(); P.pg.wait_for_timeout(600)
    P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text="bed.png")).first.locator(".cfg-row__main").click(); P.pg.wait_for_timeout(900)
    ok("image opens in the viewer, the editor area stays on the placeholder", P.pg.locator(".desk-empty").count() == 1 and P.pg.locator(".viewer-overlay, .image-viewer, [class*=viewer]").count() >= 1)
    ok("no errors on the config page", not errs(P), errs(P)[:3]); P.close()

    # ------------------------------------------------------------------ sistema + calibrazione smoke
    P = fresh(tab="sistema")
    ok("sistema: three columns with host, logs, AI monitor", P.pg.locator(".desk-system > .desk-col").count() == 3, P.pg.locator(".desk-system > .desk-col").count())
    P.pg.screenshot(path=f"{out}/sistema.png", animations="disabled")
    ok("no errors on Sistema", not errs(P), errs(P)[:3]); P.close()
    P = fresh(tab="controllo")
    ok("calibrazione: mesh card and calibration card side by side", P.pg.locator(".desk-split > .desk-col").count() == 2)
    P.pg.screenshot(path=f"{out}/calibrazione.png", animations="disabled")
    ok("no errors on Calibrazione", not errs(P), errs(P)[:3]); P.close()

    # ------------------------------------------------------------------ breakpoint
    P = fresh(1440, 900)
    for w, wide in [(1099, False), (1100, True), (800, False), (390, False), (1600, True), (1280, True)]:
        P.pg.set_viewport_size({"width": w, "height": 900}); P.pg.wait_for_timeout(500)
        has_wide = P.pg.locator(".desk-app").count() == 1
        has_phone = P.pg.locator(".app-main").count() == 1
        isw = P.pg.evaluate("() => document.documentElement.classList.contains('is-wide')")
        ov = overflow(P)
        ok(f"breakpoint {w}px -> {'wide' if wide else 'phone'} layout", has_wide == wide and has_phone != wide and isw == wide and ov["sw"] <= ov["cw"], (has_wide, has_phone, isw, ov))
    ok("no errors across resizes", not errs(P), errs(P)[:3])
    # switching layout keeps the tab
    P.pg.set_viewport_size({"width": 1440, "height": 900}); P.pg.wait_for_timeout(400); go(P, "File")
    P.pg.set_viewport_size({"width": 390, "height": 844}); P.pg.wait_for_timeout(600)
    ok("rotating to phone width keeps the File tab", P.pg.locator(".file-card").count() >= 1 and tab_stored(P) == "files")
    P.close()

    # a very small desktop (1100x600) still usable
    P = fresh(1100, 600)
    ov = overflow(P); ok("1100x600: no page scroll", ov["sw"] <= ov["cw"] and ov["sh"] <= ov["ch"], ov)
    P.pg.screenshot(path=f"{out}/small_1100x600.png", animations="disabled"); P.close()

    b.close()
print("\nFAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
