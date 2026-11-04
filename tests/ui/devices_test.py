"""Release 1.45.0 (roadmap 6d part 4): the Devices card, like Mainsail's "Power control" and "Miscellaneous": Moonraker's
power devices (the off asked first; a name with _ hidden), Klipper's output pins (a switch; a slider for a PWM pin), the
filament sensors (filament there or not, the sensor on / off). No card when there is nothing. Against the mock.
Usage: devices_test.py <html> <outdir> <port>"""
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


def fresh(b, w=390, h=844, tab="controllo", **st):
    mock.reset()
    if st:
        mock.set(**st)
    P = Page(b, mock, w, h)
    CUR[0] = P
    P.goto(tab, 2400)
    return P


with sync_playwright() as p:
    b = p.chromium.launch()

    P = fresh(b)
    ok("nothing to show (no [power], no pins, no sensors): no card", P.pg.locator(".devices-card").count() == 0)
    P.close()

    P = fresh(b, power_on=True, extra_devices=True, extra_lights=True)
    pg = P.pg
    card = pg.locator(".devices-card")
    ok("the Devices card on the Control page", wait_until(lambda: card.count() == 1))
    card.scroll_into_view_if_needed()
    ok("power: the printer and the LED strip, not _hidden_relay", [e.get_attribute("data-power") for e in card.locator("[data-power]").all()] == ["printer", "led_strip"])
    ok("... the printer says it is locked while printing", "Bloccato durante la stampa" in card.locator('[data-power="printer"]').inner_text())
    ok("outputs: caselight (PWM, a slider), beeper and relay (switches), not _secret",
       card.locator('[data-pin="caselight"] input[type=range]').count() == 1 and card.locator('[data-pin="beeper"] [role=switch]').count() == 1 and card.locator('[data-pin="relay"] [role=switch]').count() == 1 and card.locator('[data-pin="_secret"]').count() == 0)
    ok("filament sensors: runout has filament, the encoder is empty", "Filamento presente" in card.locator('[data-sensor="runout"]').inner_text() and "Niente filamento" in card.locator('[data-sensor="encoder"]').inner_text())
    pg.screenshot(path=out + "/card.png", full_page=True)
    card.locator('[data-power="led_strip"] [role=switch]').click()
    ok("switching a power device on: POST action=on", wait_until(lambda: "led_strip:on" in state()["power_log"]))
    card.locator('[data-power="printer"] [role=switch]').click()
    ok("switching one off asks first", wait_until(lambda: pg.locator(".confirm-card", has_text="Spegnere Printer").count() == 1) and "printer:off" not in state()["power_log"])
    pg.locator(".confirm-card").get_by_role("button", name="Spegni").click()
    ok("... then it goes off", wait_until(lambda: "printer:off" in state()["power_log"]) and wait_until(lambda: card.locator('[data-power="printer"] [role=switch]').get_attribute("aria-checked") == "false"))
    card.locator('[data-pin="relay"] [role=switch]').click()
    ok("the relay: SET_PIN PIN=relay VALUE=1", wait_until(lambda: state()["pins"]["relay"] == 1.0), state()["pins"])
    card.locator('[data-pin="caselight"] input[type=range]').fill("40")
    ok("the PWM pin at 40 %: SET_PIN PIN=caselight VALUE=0.4", wait_until(lambda: "SET_PIN PIN=caselight VALUE=0.4" in state()["gcode_log"]), state()["gcode_log"][-3:])
    card.locator('[data-sensor="runout"] [role=switch]').click()
    ok("the runout sensor off: SET_FILAMENT_SENSOR SENSOR=runout ENABLE=0", wait_until(lambda: state()["sensors"]["runout"]["enabled"] is False) and wait_until(lambda: "Spento" in card.locator('[data-sensor="runout"]').inner_text()))
    ok("no horizontal overflow", pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    ok("no page errors", not errs(P), errs(P)[:2])
    P.close()

    # a print going on: Moonraker refuses the locked device
    P = fresh(b, power_on=True, printing=True)
    card = P.pg.locator(".devices-card")
    wait_until(lambda: card.count() == 1)
    card.scroll_into_view_if_needed()
    card.locator('[data-power="printer"] [role=switch]').click()
    P.pg.locator(".confirm-card").get_by_role("button", name="Spegni").click()
    ok("while printing Moonraker refuses the printer's plug: it says so and the switch stays on",
       wait_until(lambda: P.pg.locator("text=while printing").count() >= 1) and wait_until(lambda: card.locator('[data-power="printer"] [role=switch]').get_attribute("aria-checked") == "true", 8))
    P.close()

    # computer
    P = fresh(b, 1440, 900, tab="home", power_on=True, extra_devices=True)
    ok("desktop: the card on the device page, with the fans", wait_until(lambda: P.pg.locator(".desk-slot--fans .devices-card").count() == 1))
    P.pg.locator(".devices-card").scroll_into_view_if_needed()
    P.pg.screenshot(path=out + "/desktop.png")
    ok("desktop: no page errors", not errs(P), errs(P)[:2])
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
