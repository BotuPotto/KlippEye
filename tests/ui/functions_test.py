"""Settings -> Printer functions (1.18.0, roadmap phase 5b): what the buttons that use the printer's own macros do.
The mock printer is the VzBot: a neopixel strip LUCI driven by a klipper-led_effect effect and switched by LUCI_ON / LUCI_OFF,
a CLEAN_NOZZLE macro, no park / load / unload macros.
Usage: functions_test.py <html> <outdir> <port>"""
import sys, os, json, time, urllib.request
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
FAILS = []
CUR = [None]


def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""))


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def stored():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/db").read())["db"].get("klippeye/settings") or {}


def wait_until(fn, timeout=4.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn(): return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    try: return bool(fn())
    except Exception: return False


def fresh(b, tab="controllo", reset=True, **st):
    if reset: mock.reset()
    if st: mock.set(**st)
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    to_tab(P, tab)
    return P


def to_tab(P, tab):
    P.pg.goto(mock.base + "/")
    P.pg.evaluate("(t) => localStorage.setItem('ke_current_tab', t)", tab)
    P.pg.reload(); P.pg.wait_for_timeout(2200)


def body(P):
    return P.pg.locator(".drawer__body").inner_text()


def open_page(P):
    P.pg.click('button[aria-label="Impostazioni"]'); P.pg.wait_for_selector(".drawer"); P.settle(450)
    P.pg.locator('.set-entry[data-page="functions"]').click(); P.settle(700)


def group(P, fid):
    return P.pg.locator("section.set-group", has=P.pg.locator('[data-function-group="%s"]' % fid))


with sync_playwright() as p:
    b = p.chromium.launch()

    # ------------------------------------------------------------------ what is found by itself
    P = fresh(b)
    buttons = P.pg.locator("[data-function]").evaluate_all("els => els.map(e => e.dataset.function)")
    ok("Automatic: only what the printer has gets a button (CLEAN_NOZZLE -> Wipe; no park / load / unload macros)", buttons == ["wipe"], buttons)
    P.pg.locator('[data-function="wipe"]').click(); P.settle(500)
    ok("... and the button runs the macro that was found", wait_until(lambda: "CLEAN_NOZZLE" in state()["gcode_log"]), state()["gcode_log"][-3:])
    to_tab(P, "home")
    ok("the light button is there (LUCI_ON / LUCI_OFF found)", P.pg.locator(".light-btn").count() == 1)
    mock.set(light=0); P.settle(2500)
    ok("the light button reads the strip and its effect: off when the effect stops (whoever stopped it)", "is-on" not in (P.pg.locator(".light-btn").get_attribute("class") or ""))
    mock.set(light=1); P.settle(2500)
    ok("... on as soon as the effect runs again (switched from Mainsail, KlipperScreen, the console...)", "is-on" in (P.pg.locator(".light-btn").get_attribute("class") or ""))

    # ------------------------------------------------------------------ the page
    P.pg.click('button[aria-label="Impostazioni"]'); P.pg.wait_for_selector(".drawer"); P.settle(450)
    entry = P.pg.locator('.set-entry[data-page="functions"]')
    ok("the menu has 'Funzioni della stampante', marked 'Da controllare'", entry.count() == 1 and "Da controllare" in entry.inner_text(), entry.inner_text() if entry.count() else "")
    entry.click(); P.settle(700)
    text = body(P)
    ok("the page asks to check, and says what it found for the light", "controlla ogni funzione" in text and "LUCI_ON / LUCI_OFF" in text and "neopixel LUCI" in text and "effetti (1)" in text, text[:900])
    ok("... park: nothing found, the button is not shown; wipe: CLEAN_NOZZLE", "Niente trovato" in P.pg.locator('[data-now="park"]').inner_text() and "CLEAN_NOZZLE" in P.pg.locator('[data-now="wipe"]').inner_text())
    P.shot(out + "/functions_page.png")

    # park -> macro PARK_TEST
    group(P, "park").locator(".oui-chip", has_text="Macro").click(); P.settle(300)
    field = P.pg.locator('[data-macro="park"]')
    field.fill("park_test"); field.blur(); P.settle(600)
    ok("park -> macro: typed in lower case, kept as PARK_TEST, saved in the shared settings", wait_until(lambda: stored().get("functions", {}).get("park") == {"mode": "macro", "macro": "PARK_TEST", "gcode": ""}), stored().get("functions"))
    ok("... the page says it runs PARK_TEST", "PARK_TEST" in P.pg.locator('[data-now="park"]').inner_text())

    # load -> G-code written in the editor
    group(P, "load").locator(".oui-chip", has_text="G-code").click(); P.settle(300)
    P.pg.locator('[data-edit-gcode="load"]').click(); P.settle(600)
    ok("G-code: the dashboard's editor opens over the page", P.pg.locator(".editor-textarea, textarea").count() >= 1 and P.pg.locator(".editor-save").count() >= 1)
    ok("... with only 'Salva' (no 'Salva e riavvia': this text is not a file)", P.pg.locator(".editor-save", has_text="riavvia").count() == 0)
    ta = P.pg.locator("textarea").last
    ta.fill("M109 S220\nG1 E50 F300")
    P.pg.locator(".editor-save").first.click(); P.settle(900)
    ok("... saving keeps the G-code in the settings and closes the editor", wait_until(lambda: stored().get("functions", {}).get("load", {}).get("gcode") == "M109 S220\nG1 E50 F300") and P.pg.locator(".editor-save").count() == 0, stored().get("functions", {}).get("load"))

    # unload -> create a macro
    P.pg.locator('[data-create="unload"]').scroll_into_view_if_needed()
    P.pg.locator('[data-create="unload"]').click(); P.settle(800)
    ok("create a macro: the proposed KLIPPEYE_UNLOAD_FILAMENT opens in the editor", "KLIPPEYE_UNLOAD_FILAMENT" in P.pg.locator("textarea").last.input_value())
    P.pg.locator(".editor-save").first.click(); P.settle(1200)
    ok("... saved by the backend into klippeye_macros.cfg, and the function now uses it", wait_until(lambda: "KLIPPEYE_UNLOAD_FILAMENT" in state()["pm_macros"]) and wait_until(lambda: stored().get("functions", {}).get("unload", {}).get("macro") == "KLIPPEYE_UNLOAD_FILAMENT"), (state()["pm_macros"].keys(), stored().get("functions", {}).get("unload")))
    ok("... the page says Klipper must restart, with the button", wait_until(lambda: P.pg.locator('[data-restart="1"]').count() == 1), body(P)[:400])
    P.pg.locator('[data-restart="1"]').click(); P.settle(500)
    ok("... 'Riavvia Klipper adesso' restarts Klipper", wait_until(lambda: any("firmware_restart" in str(a) for a in state()["actions"])), state()["actions"][-3:])

    # wipe -> off
    group(P, "wipe").locator(".oui-chip", has_text="Non usata").click(); P.settle(400)
    ok("wipe -> Off", wait_until(lambda: stored().get("functions", {}).get("wipe", {}).get("mode") == "off"))

    # the filament change
    fil = P.pg.locator("section.set-group", has_text="Notifica di cambio filamento")
    fil.scroll_into_view_if_needed()
    ok("filament: no sensor in this printer (the switch says so and is off)", "Nessun sensore del filamento" in fil.inner_text())
    fil.locator('[data-wrap="LUCI_OFF"]').click(); P.settle(200)
    fil.locator('[data-apply-wraps="1"]').click(); P.settle(900)
    ok("filament: a macro chosen is sent to the backend as an announcer", wait_until(lambda: state()["pm_wraps"] == ["LUCI_OFF"]) and wait_until(lambda: stored().get("functions", {}).get("filament", {}).get("macros") == ["LUCI_OFF"]), (state()["pm_wraps"], stored().get("functions", {}).get("filament")))
    ph = P.pg.locator('[data-phrases="1"]')
    ph.fill("Cambio filamento!\n  M600 in corso  "); ph.blur(); P.settle(700)
    ok("filament: console lines kept one per line, trimmed (the notification service reads them)", wait_until(lambda: stored().get("functions", {}).get("filament", {}).get("phrases") == ["Cambio filamento!", "M600 in corso"]), stored().get("functions", {}).get("filament"))

    # confirm
    P.pg.locator('[data-reviewed="1"]').scroll_into_view_if_needed()
    P.pg.locator('[data-reviewed="1"]').click(); P.settle(600)
    ok("'Va tutto bene': reviewed, the reminder goes away", wait_until(lambda: stored().get("functions", {}).get("reviewed") is True) and P.pg.locator(".fn-review").count() == 0)
    P.shot(out + "/functions_done.png")
    P.pg.click('button[aria-label="Indietro"]'); P.settle(500)
    ok("... and the menu line no longer says 'Da controllare'", "Da controllare" not in P.pg.locator('.set-entry[data-page="functions"]').inner_text(), P.pg.locator('.set-entry[data-page="functions"]').inner_text())
    P.close()

    # ------------------------------------------------------------------ the buttons follow the settings
    P = fresh(b, reset=False)
    buttons = P.pg.locator("[data-function]").evaluate_all("els => els.map(e => e.dataset.function)")
    ok("Control page: park (PARK_TEST), load (G-code), unload (the created macro); wipe off", buttons == ["park", "load", "unload"], buttons)
    P.pg.locator('[data-function="load"]').click(); P.settle(600)
    ok("... load sends the G-code written in the editor", wait_until(lambda: "M109 S220\nG1 E50 F300" in state()["gcode_log"]), state()["gcode_log"][-3:])
    P.pg.locator('[data-function="park"]').click(); P.settle(600)
    ok("... park sends PARK_TEST", wait_until(lambda: "PARK_TEST" in state()["gcode_log"]), state()["gcode_log"][-3:])
    P.close()

    # ------------------------------------------------------------------ the light switched directly on the strip
    P = fresh(b, "home", reset=False)
    P.pg.click('button[aria-label="Impostazioni"]'); P.pg.wait_for_selector(".drawer"); P.settle(450)
    P.pg.locator('.set-entry[data-page="functions"]').click(); P.settle(700)
    group(P, "light").locator(".oui-chip", has_text="Uscita").click(); P.settle(300)
    P.pg.locator('[data-light-select="object"]').select_option("neopixel LUCI"); P.settle(600)
    ok("light -> Output: neopixel LUCI, switched with Klipper's commands", "comandata direttamente su neopixel LUCI" in P.pg.locator('[data-now="light"]').inner_text(), P.pg.locator('[data-now="light"]').inner_text())
    P.pg.click('.drawer button[aria-label="Chiudi"]'); P.settle(600)
    mock.set(light=1); P.settle(2200)
    P.pg.locator(".light-btn").click(); P.settle(1200)
    log = state()["gcode_log"]
    ok("... the button stops the effects on the strip and sets it to 0 (no macro needed)", any('STOP_LED_EFFECTS LEDS="neopixel:LUCI"' in g and "SET_LED LED=LUCI RED=0" in g for g in log), log[-3:])
    P.close()

    # ------------------------------------------------------------------ everything off
    P = fresh(b, "home")
    P.pg.click('button[aria-label="Impostazioni"]'); P.pg.wait_for_selector(".drawer"); P.settle(450)
    P.pg.locator('.set-entry[data-page="functions"]').click(); P.settle(700)
    group(P, "light").locator(".oui-chip", has_text="Non usata").click(); P.settle(600)
    P.pg.click('.drawer button[aria-label="Chiudi"]'); P.settle(600)
    ok("light Off: no light button", P.pg.locator(".light-btn").count() == 0)
    overflow = P.pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    ok("no horizontal scrolling", overflow <= 0, overflow)
    P.close()
    b.close()

print("\nFAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
