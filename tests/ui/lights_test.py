"""Release 1.37.0 (roadmap 6b part 8): as many lights as the printer has. KlippEye finds them (the LUCI_ON / LUCI_OFF pair
read on neopixel LUCI, a white+RGB neopixel STRIP, a PWM pin "caselight"; not the pin "beeper"); the round button switches
the ones marked together, its arrow opens every light with brightness, colour and scenes; Settings → Printer functions edits
the list (in three parts: lights, buttons, filament). Against the mock.
Usage: lights_test.py <html> <outdir> <port>"""
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


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def gcodes():
    return state()["gcode_log"]


def stored():
    db = json.loads(urllib.request.urlopen(mock.base + "/__mock/db").read())["db"]
    return (db.get("klippeye/settings") or {}).get("functions", {}).get("lights") or {}


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


def fresh(b, w=390, h=844, reset=True, **st):
    if reset:
        mock.reset()
    mock.set(extra_lights=True, **st)
    P = Page(b, mock, w, h)
    CUR[0] = P
    P.goto("home", 2600)
    return P


def is_on(P):
    return "is-on" in (P.pg.locator(".light-btn").first.get_attribute("class") or "")


def row(P, lid):
    return P.pg.locator('.light-row[data-light="%s"]' % lid)


with sync_playwright() as p:
    b = p.chromium.launch()

    P = fresh(b)
    pg = P.pg
    ok("one round button and its arrow on the camera", wait_until(lambda: pg.locator(".light-btn").count() == 1 and pg.locator(".light-more").count() == 1))
    pg.locator(".light-btn").first.click()
    ok("the round button switches every light found: LUCI by its macro, the strip and the pin on their outputs",
       wait_until(lambda: state()["light"] == 1 and state()["strip"][0] == 1 and state()["caselight"] == 1, 8), (state()["light"], state()["strip"], state()["caselight"]))
    ok("... and shows on", wait_until(lambda: is_on(P)))
    pg.locator(".light-btn").first.click()
    ok("a second tap switches them all off", wait_until(lambda: state()["light"] == 0 and state()["strip"] == [0, 0, 0, 0] and state()["caselight"] == 0, 8) and wait_until(lambda: not is_on(P)), (state()["light"], state()["strip"], state()["caselight"]))

    # the panel
    pg.locator(".light-more").first.click()
    panel = pg.locator(".lights-panel")
    ok("the arrow opens every light", wait_until(lambda: panel.count() == 1) and [e.get_attribute("data-light") for e in panel.locator(".light-row").all()] == ["m-luci-on", "o-neopixel-strip", "o-output-pin-caselight"],
       [e.get_attribute("data-light") for e in panel.locator(".light-row").all()])
    ok("... not the pin 'beeper' (its name does not say light)", "beeper" not in panel.inner_text().lower())
    ok("... brightness for the strip and the PWM pin, colour for the strip only, nothing for the macros",
       row(P, "o-neopixel-strip").locator(".light-row__level").count() == 1 and row(P, "o-neopixel-strip").locator(".light-row__swatch").count() == 1
       and row(P, "o-output-pin-caselight").locator(".light-row__level").count() == 1 and row(P, "o-output-pin-caselight").locator(".light-row__swatch").count() == 0
       and row(P, "m-luci-on").locator(".light-row__level").count() == 0)
    row(P, "o-output-pin-caselight").locator(".light-row__level").fill("40")
    ok("the pin's brightness at 40 %: SET_PIN PIN=caselight VALUE=0.4", wait_until(lambda: "SET_PIN PIN=caselight VALUE=0.4" in gcodes() and abs(state()["caselight"] - 0.4) < 1e-6), gcodes()[-3:])
    row(P, "o-neopixel-strip").get_by_role("switch").click()
    ok("the strip's own switch: on (white on its white channel)", wait_until(lambda: state()["strip"] == [1, 1, 1, 1]), state()["strip"])
    row(P, "o-neopixel-strip").locator(".light-row__swatch").click()
    hexf = row(P, "o-neopixel-strip").locator(".color-wheel__hex")
    hexf.fill("#ff0000")
    ok("the strip's colour: red (no white)", wait_until(lambda: state()["strip"] == [1, 0, 0, 0]), state()["strip"])
    row(P, "o-neopixel-strip").locator(".light-row__level").fill("50")
    ok("... at half brightness", wait_until(lambda: state()["strip"] == [0.5, 0, 0, 0]), state()["strip"])
    pg.screenshot(path=out + "/panel.png")

    # scenes
    panel.get_by_role("button", name="Salva come scena").click()
    panel.locator(".lights-scene-new__input").fill("Sera")
    panel.get_by_role("button", name="Salva", exact=True).click()
    ok("'Salva come scena': saved in the shared settings with each light", wait_until(lambda: any(s["name"] == "Sera" for s in stored().get("scenes", []))), stored().get("scenes"))
    scene = next(s for s in stored()["scenes"] if s["name"] == "Sera")
    ok("... the strip red at 50 %, the pin at 40 %, LUCI off", scene["set"]["o-neopixel-strip"] == {"on": True, "level": 50, "color": "#ff0000"} and scene["set"]["o-output-pin-caselight"]["level"] == 40 and scene["set"]["m-luci-on"]["on"] is False, scene["set"])
    row(P, "o-neopixel-strip").get_by_role("switch").click()
    row(P, "o-output-pin-caselight").get_by_role("switch").click()
    wait_until(lambda: state()["strip"] == [0, 0, 0, 0] and state()["caselight"] == 0)
    panel.locator(".lights-scene", has_text="Sera").click()
    ok("a tap on the scene brings it back", wait_until(lambda: state()["strip"] == [0.5, 0, 0, 0] and abs(state()["caselight"] - 0.4) < 1e-6), (state()["strip"], state()["caselight"]))
    panel.get_by_role("button", name="Fatto").click()
    P.close()

    # settings: the list, the round button's lights
    P = fresh(b, reset=False)
    pg = P.pg
    pg.click('button[aria-label="Impostazioni"]')
    pg.wait_for_selector(".drawer")
    P.settle(450)
    pg.locator('.set-entry[data-page="functions"]').click()
    P.settle(700)
    ok("the page in three parts: lights, buttons, filament", [e.get_attribute("data-section") for e in pg.locator(".fn-section").all()] == ["lights", "buttons", "filament"])
    ok("it says the lights were found by KlippEye (3)", "3 luci" in pg.locator('[data-lights-state="found"]').inner_text(), pg.locator("[data-lights-state]").inner_text())
    ok("... each with its editor", pg.locator("[data-light-item]").count() == 3)
    pg.screenshot(path=out + "/settings.png")
    ok("1.57: each light is a closed row with how it is switched", pg.locator('[data-light-item] > .fn-fold__head[aria-expanded="false"]').count() == 3 and "pulsante tondo" in pg.locator('[data-light-item="o-output-pin-caselight"] .fn-fold__summary').inner_text())
    for one in ("o-output-pin-caselight", "o-neopixel-strip"):
        pg.locator('[data-light-item="%s"] > .fn-fold__head' % one).click(); P.settle(450)
    item = pg.locator('[data-light-item="o-output-pin-caselight"]')
    item.locator(".set-switch", has_text="Comandata dal pulsante tondo").click()
    ok("taking the pin out of the round button keeps the list as the person's", wait_until(lambda: stored().get("configured") is True and [i["main"] for i in stored()["items"]] == [True, True, False]), stored())
    name = pg.locator('[data-light-item="o-neopixel-strip"] input.set-field__input').first
    name.fill("Striscia")
    name.press("Enter")
    ok("renaming the strip", wait_until(lambda: stored()["items"][1]["name"] == "Striscia"))
    pg.locator('[data-add-light="1"]').click()
    ok("'Aggiungi una luce' adds one to fill in", wait_until(lambda: len(stored()["items"]) == 4) and pg.locator("[data-light-item]").count() == 4)
    ok("... the scenes are listed with their lights", pg.locator('[data-scene-row]').count() == 1 and "Sera" in pg.locator('[data-scene-row]').inner_text())
    pg.click('.drawer button[aria-label="Chiudi"]')
    P.settle(600)
    mock.set(light=0, strip=[0, 0, 0, 0], caselight=0)
    P.settle(1600)
    pg.locator(".light-btn").first.click()
    ok("the round button now leaves the pin alone", wait_until(lambda: state()["light"] == 1 and state()["strip"][0] == 1, 8) and state()["caselight"] == 0, (state()["light"], state()["strip"], state()["caselight"]))
    pg.locator(".light-more").first.click()
    ok("the panel shows the new name", wait_until(lambda: "Striscia" in pg.locator(".lights-panel").inner_text()))
    P.close()

    # the old single light of an earlier release becomes the list's only light
    P = fresh(b, db={"klippeye/settings": {"_t": 5, "language": "it", "functions": {"light": {"mode": "object", "object": "neopixel STRIP"}}}})
    ok("a light chosen before 1.37 (output neopixel STRIP) is kept as the only light", wait_until(lambda: P.pg.locator(".light-btn").count() == 1))
    P.pg.locator(".light-more").first.click()
    ok("... the panel has just it", wait_until(lambda: P.pg.locator(".lights-panel .light-row").count() == 1))
    P.close()

    # computer
    P = fresh(b, w=1440, h=900)
    P.pg.locator(".desk-camera .light-more").click()
    ok("desktop: the arrow on the camera panel opens the lights", wait_until(lambda: P.pg.locator(".lights-panel .light-row").count() == 3))
    P.pg.screenshot(path=out + "/desktop.png")
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
