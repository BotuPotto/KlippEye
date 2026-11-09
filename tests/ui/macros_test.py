"""Release 1.33.0 (roadmap 6b part 4): the macro cards, like Mainsail's. "All the macros" (one card, macros can be hidden) or
"Groups" (cards of one's own: name, colour, order, the printer states they show in), set in Settings → Macros and kept in the
shared settings; the old "Calibrations" choice becomes a group. The endstops have a card of their own. Against the mock.
Usage: macros_test.py <html> <outdir> <port>"""
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


def gcodes():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/gcode").read())


def stored():
    db = json.loads(urllib.request.urlopen(mock.base + "/__mock/db").read())["db"]
    return (db.get("klippeye/settings") or {}).get("macros")


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


def fresh(b, tab="controllo", w=390, h=844, **st):
    mock.reset()
    mock.set(**st)
    P = Page(b, mock, w, h)
    CUR[0] = P
    P.goto(tab, 2400)
    return P


def cards(P):
    return P.pg.locator("[data-macro-card]")


def card_titles(P):
    return [t.strip().lower() for t in cards(P).locator(".oui-card-title").all_inner_texts()]


def card_buttons(P, cid):
    return [t.strip() for t in P.pg.locator('[data-macro-card="%s"] :is(.macro-run, .macro-split-run)' % cid).all_inner_texts()]


def MOCK_HEX(value):
    return isinstance(value, str) and len(value) == 7 and value.startswith("#")


def drawer(P):
    return P.pg.locator(".drawer")


def close_drawer(P):
    P.pg.click('.drawer button[aria-label="Chiudi"]')
    P.pg.wait_for_selector(".drawer", state="detached")
    P.settle(200)


with sync_playwright() as p:
    b = p.chromium.launch()

    # ---- the old "Calibrations" choice becomes a group
    P = fresh(b, calib_selected=["PARK_TEST", "SHAPER_CALIBRATE"])
    pg = P.pg
    ok("the macros chosen before 1.33 become the group 'Calibrazioni'", wait_until(lambda: card_titles(P) == ["calibrazioni"]), card_titles(P))
    ok("... saved in the shared settings: groups mode", wait_until(lambda: (stored() or {}).get("mode") == "groups" and stored()["groups"][0]["macros"] == ["PARK_TEST", "SHAPER_CALIBRATE"]), stored())
    ok("... and the old list emptied (it happens once)", wait_until(lambda: json.loads(urllib.request.urlopen(mock.base + "/api/calibration/selected").read())["selected"] == []))
    ok("... with its buttons, in the same order", card_buttons(P, "calib") == ["Park test", "Shaper calibrate"], card_buttons(P, "calib"))
    ok("the endstops have a card of their own", pg.locator(".endstops-card .endstops-body").count() == 1)
    pg.locator('[data-macro-card="calib"] .macro-split-run').click()
    ok("a tap on a macro runs it", wait_until(lambda: "PARK_TEST" in gcodes()))
    pg.locator('[data-macro-card="calib"] .macro-split-gear').click()
    pg.wait_for_selector(".sheet-overlay--params")
    pg.locator(".sheet-overlay--params .params-run").click()
    ok("the ⚙ of a macro with parameters: the form, then PARK_TEST X=100 Y=50", wait_until(lambda: "PARK_TEST X=100 Y=50" in gcodes()), gcodes()[-3:])
    pg.locator('[data-macro-card="calib"] button[aria-label="Gestisci le macro"]').click()
    ok("the gear of a card opens Settings → Macros", wait_until(lambda: drawer(P).count() == 1 and "Come vengono mostrate le macro".lower() in drawer(P).inner_text().lower()))
    P.settle(400)
    pg.screenshot(path=out + "/settings_groups.png")

    # ---- the group editor
    ed = pg.locator('.macro-group-edit[data-group-id="calib"]')
    ed.locator('[data-macro="SHAPER_CALIBRATE"] button[aria-label="Sposta su"]').click()
    ok("moving a macro up changes the order", wait_until(lambda: stored()["groups"][0]["macros"] == ["SHAPER_CALIBRATE", "PARK_TEST"]), stored())
    pg.get_by_role("button", name="Nuovo gruppo", exact=True).click()
    ok("'Nuovo gruppo' adds a group", wait_until(lambda: len(stored()["groups"]) == 2), stored())
    new = pg.locator(".macro-group-edit").nth(1)
    name = new.locator("input.set-field__input")
    name.fill("Filamento")
    name.press("Enter")
    new.get_by_role("radio", name="Verde").click()
    new.locator('button[data-state="standby"]').click()
    new.get_by_role("button", name="Aggiungi o rimuovi macro").click()
    pg.wait_for_selector(".sheet-overlay--picker")
    P.settle(300)
    pg.locator(".sheet-overlay--picker .picker-row:has-text('CLEAN_NOZZLE')").first.click()
    pg.locator(".sheet-overlay--picker").get_by_role("button", name="Fatto", exact=True).click()
    ok("... named, green, not while idle, with CLEAN_NOZZLE",
       wait_until(lambda: stored()["groups"][1]["name"] == "Filamento" and stored()["groups"][1]["color"] == "ok" and stored()["groups"][1]["show"] == {"standby": False, "printing": True, "paused": True} and stored()["groups"][1]["macros"] == ["CLEAN_NOZZLE"]),
       stored()["groups"][1])
    P.settle(300)
    pg.screenshot(path=out + "/group_editor.png")
    ok("no horizontal overflow in the editor", pg.evaluate("() => { const b = document.querySelector('.drawer__body'); return b.scrollWidth <= b.clientWidth; }"))
    # 1.33.1: any colour, on the wheel
    cal = pg.locator('.macro-group-edit[data-group-id="calib"]')
    cal.get_by_role("radio", name="Personalizzato").click()
    ok("'Personalizzato' opens the colour wheel", wait_until(lambda: cal.locator(".color-wheel__disc").count() == 1 and MOCK_HEX(stored()["groups"][0]["color"])), stored()["groups"][0]["color"])
    box = cal.locator(".color-wheel__disc").bounding_box()
    pg.mouse.click(box["x"] + box["width"] - 3, box["y"] + box["height"] / 2)
    ok("a tap at the right edge of the wheel: red", wait_until(lambda: stored()["groups"][0]["color"][1:3] == "ff" and int(stored()["groups"][0]["color"][3:5], 16) < 0x20 and int(stored()["groups"][0]["color"][5:7], 16) < 0x20), stored()["groups"][0]["color"])
    pg.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    ok("... at the centre: white", wait_until(lambda: stored()["groups"][0]["color"] == "#ffffff"), stored()["groups"][0]["color"])
    hexf = cal.locator(".color-wheel__hex")
    hexf.fill("#12ab34")
    ok("typing a colour code sets it", wait_until(lambda: stored()["groups"][0]["color"] == "#12ab34"), stored()["groups"][0]["color"])
    hexf.blur()
    P.settle(300)
    cal.screenshot(path=out + "/color_wheel.png")
    close_drawer(P)
    ok("the card takes the colour of the wheel", "#12ab34" in (pg.locator('[data-macro-card="calib"]').get_attribute("style") or "") and "macro-card--custom" in pg.locator('[data-macro-card="calib"]').get_attribute("class"))
    ok("idle: only the groups shown while idle (Filamento is not)", card_titles(P) == ["calibrazioni"], card_titles(P))
    ok("... and the new order", card_buttons(P, "calib") == ["Shaper calibrate", "Park test"], card_buttons(P, "calib"))
    P.close()

    P = fresh(b, printing=True, db={"klippeye/settings": {"_t": 5, "language": "it", "macros": {"mode": "groups", "groups": [
        {"id": "calib", "name": "Calibrazioni", "color": "none", "show": {"standby": True, "printing": False, "paused": False}, "macros": ["SHAPER_CALIBRATE"]},
        {"id": "fil", "name": "Filamento", "color": "ok", "show": {"standby": False, "printing": True, "paused": True}, "macros": ["CLEAN_NOZZLE", "NOT_THERE"]}]}}})
    ok("printing: the group shown while printing, the idle-only one hidden", wait_until(lambda: card_titles(P) == ["filamento"]), card_titles(P))
    ok("... in its colour", "macro-card--ok" in P.pg.locator('[data-macro-card="fil"]').get_attribute("class"))
    ok("... a macro Klipper does not have is left out", wait_until(lambda: card_buttons(P, "fil") == ["Clean nozzle"]), card_buttons(P, "fil"))
    P.pg.locator('[data-macro-card="fil"]').screenshot(path=out + "/card_green.png")
    P.pg.locator('[data-macro-card="fil"] button[aria-label="Gestisci le macro"]').click()
    P.pg.wait_for_selector(".drawer")
    P.settle(400)
    ok("the editor says which macro Klipper does not have", "Klipper non ce l'ha" in P.pg.locator('.macro-group-edit[data-group-id="fil"] [data-macro="NOT_THERE"]').inner_text())
    P.pg.locator('.macro-group-edit[data-group-id="calib"] button[aria-label="Elimina il gruppo"]').click()
    P.pg.wait_for_selector(".confirm-card")
    P.pg.locator(".confirm-card").get_by_role("button", name="Elimina", exact=True).click()
    ok("deleting a group (after the question)", wait_until(lambda: [g["id"] for g in stored()["groups"]] == ["fil"]), stored())
    P.pg.locator('.macro-group-edit[data-group-id="fil"] [data-macro="NOT_THERE"] button[aria-label="Rimuovi"]').click()
    ok("removing a macro from a group", wait_until(lambda: stored()["groups"][0]["macros"] == ["CLEAN_NOZZLE"]))

    # ---- "All the macros"
    P.pg.get_by_role("radio", name="Tutte le macro").click()
    P.settle(400)
    sw = P.pg.locator(".macro-visibility .set-switch:has-text('CLEAN_NOZZLE')")
    ok("all the macros: a switch for each, on", sw.count() == 1 and sw.get_attribute("aria-checked") == "true")
    ok("... no macro whose name starts with _", P.pg.locator(".macro-visibility .set-switch:has-text('_HIDDEN')").count() == 0)
    sw.click()
    ok("switching one off hides it", wait_until(lambda: stored()["mode"] == "simple" and stored()["hidden"] == ["CLEAN_NOZZLE"]), stored())
    P.pg.screenshot(path=out + "/settings_simple.png")
    close_drawer(P)
    names = card_buttons(P, "all")
    ok("one card 'Macro' with every macro but the hidden one", card_titles(P) == ["macro"] and "Park test" in names and "Shaper calibrate" in names and "Clean nozzle" not in names and "Luci on" in names, (card_titles(P), names))
    P.close()

    # ---- a new installation (nothing chosen before): every macro
    P = fresh(b)
    ok("nothing chosen before: 'All the macros'", wait_until(lambda: card_titles(P) == ["macro"] and len(card_buttons(P, "all")) >= 5) and wait_until(lambda: (stored() or {}).get("mode") == "simple"), (card_titles(P), stored()))
    P.close()

    # ---- the computer: the Calibrazione page
    P = fresh(b, tab="controllo", w=1440, h=900)
    ok("desktop: the macro cards and the endstops on the Calibrazione page", wait_until(lambda: P.pg.locator(".desk-col [data-macro-card]").count() == 1 and P.pg.locator(".desk-col .endstops-card").count() == 1))
    P.pg.screenshot(path=out + "/desktop.png")
    P.close()

    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
