"""Release 1.43.0 (roadmap 6d part 2): every heater and sensor and the temperature chart. The chart starts
from Moonraker's temperature_store and goes on with fresh readings; names hide / show their lines (kept on this device);
5 / 10 / 20 minutes; a pointer (or a finger) on the chart says the values at that moment; the target of a heater that is
not the nozzle or the bed changes with SET_HEATER_TEMPERATURE (SET_TEMPERATURE_FAN_TARGET for a fan). Against the mock.
Usage: temps_test.py <html> <outdir> <port>"""
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


def gcodes():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/gcode").read())


def names(P):
    return [e.get_attribute("data-temp") for e in P.pg.locator(".temp-card .temp-row[data-temp]").all()]


def errs(P):
    return [e for e in P.errors if "pageerror" in e or "console.error" in e]


def fresh(b, w=390, h=844, **st):
    mock.reset()
    mock.set(extra_temps=True, **st)
    P = Page(b, mock, w, h)
    CUR[0] = P
    P.goto("home", 2400)
    P.pg.locator(".temp-card").scroll_into_view_if_needed()
    return P


with sync_playwright() as p:
    b = p.chromium.launch()
    P = fresh(b)
    pg = P.pg
    ok("every heater and sensor: nozzle, bed, the chamber heater, the fan, the sensors (not the _ one)",
       wait_until(lambda: names(P) == ["extruder", "heater_bed", "heater_generic chamber_heater", "temperature_fan mcu_fan", "temperature_sensor chamber", "temperature_sensor raspberry_pi"]), names(P))
    row = lambda n: pg.locator('.temp-row[data-temp="%s"]' % n)
    ok("the nozzle: 215.3°, target 220°, power 45%", "215.3°" in row("extruder").inner_text() and "220°" in row("extruder").inner_text() and "45%" in row("extruder").inner_text(), row("extruder").inner_text())
    ok("names in words: Ugello, Piatto, Chamber heater, Raspberry pi", [row(n).locator(".temp-row__label").inner_text() for n in ("extruder", "heater_bed", "heater_generic chamber_heater", "temperature_sensor raspberry_pi")] == ["Ugello", "Piatto", "Chamber heater", "Raspberry pi"])
    ok("a sensor has no target button", row("temperature_sensor chamber").locator("button.temp-row__target").count() == 0)
    ok("a line for each, a dashed target for the heaters and the fan", pg.locator(".temp-chart__line").count() == 6 and pg.locator(".temp-chart__target").count() == 4)
    d = pg.locator('[data-series="extruder"]').get_attribute("d") or ""
    ok("the nozzle's line starts from Moonraker's history (many points, not just the live ones)", d.count("L") > 200, d.count("L"))
    end0 = float(pg.locator(".temp-chart").get_attribute("data-end"))
    ok("... and goes on with fresh readings (the newest sample moves on)", wait_until(lambda: float(pg.locator(".temp-chart").get_attribute("data-end")) >= end0 + 3500, 8))
    xs = pg.evaluate("() => [...document.querySelectorAll('.temp-chart__tick')].filter(t => t.textContent.includes(':')).map(t => [t.textContent, Number(t.getAttribute('x'))])")
    import re as _re
    ok("1.69: the time axis shows clock times (hh:mm), oldest on the left, newest on the right", len(xs) >= 3 and all(_re.fullmatch(r"\d\d:\d\d", t) for t, _ in xs) and xs[0][1] < xs[-1][1], xs)
    # 1.75: the marks sit on round minutes and slide to the left with the lines
    tk = lambda: pg.evaluate("() => Object.fromEntries([...document.querySelectorAll('.temp-chart__tick[data-time]')].map(t => [t.dataset.time, Number(t.getAttribute('x'))]))")
    first = tk()
    ok("1.75: the marks are on round clock minutes (multiples of 2 min with 10 min shown)", first and all(int(t) % 120000 == 0 for t in first), first)
    wait_until(lambda: any(k in tk() and tk()[k] < first[k] - 1 for k in first), 10)
    later = tk()
    common = [k for k in first if k in later]
    ok("1.75: ... and slide to the left as time goes on (the same clock time, further left)", common and all(later[k] < first[k] for k in common), (first, later))
    # 1.75: the snowflake turns every heater off
    pg.locator("[data-cool-down]").click()
    ok("1.75: the snowflake sends TURN_OFF_HEATERS (no print running: no question)", wait_until(lambda: "TURN_OFF_HEATERS" in json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())["gcode_log"]) and pg.locator(".confirm-card").count() == 0)
    pg.screenshot(path=out + "/phone.png", full_page=True)

    # ranges
    pg.locator('.temp-ranges [data-range="20"]').click()
    d20 = pg.locator('[data-series="extruder"]').get_attribute("d")
    ok("20 min: the heat-up of the nozzle (10 minutes ago) is in the chart", d20.count("L") > 1000, d20.count("L"))
    pg.locator('.temp-ranges [data-range="5"]').click()
    ok("5 min: fewer points", pg.locator('[data-series="extruder"]').get_attribute("d").count("L") < 400)

    # hide / show
    row("temperature_sensor raspberry_pi").locator(".temp-row__name").click()
    ok("a tap on a name hides its line", wait_until(lambda: pg.locator('[data-series="temperature_sensor raspberry_pi"]').count() == 0) and row("temperature_sensor raspberry_pi").locator(".temp-row__name").get_attribute("aria-pressed") == "false")

    # the pointer
    box = pg.locator(".temp-chart__svg").bounding_box()
    pg.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + 80)
    tip = pg.locator(".temp-chart__tip")
    ok("the pointer on the chart: the time and each value at that moment", wait_until(lambda: tip.count() == 1) and "Ugello" in tip.inner_text() and "/ 220°" in tip.inner_text() and "Raspberry" not in tip.inner_text(), tip.inner_text() if tip.count() else "")
    pg.screenshot(path=out + "/tip.png")
    pg.mouse.move(5, 5)

    # targets
    row("heater_generic chamber_heater").locator(".temp-row__target").click()
    dialog = pg.locator(".temp-target")
    ok("the chamber heater's target: a dialog that says the maximum (70 °C)", wait_until(lambda: dialog.count() == 1) and "70" in dialog.inner_text(), dialog.inner_text() if dialog.count() else "")
    dialog.locator("input").fill("90")
    ok("... 90 is too much", dialog.get_by_role("button", name="Imposta").is_disabled())
    dialog.locator("input").fill("50")
    dialog.get_by_role("button", name="Imposta").click()
    ok("... 50: SET_HEATER_TEMPERATURE HEATER=chamber_heater TARGET=50", wait_until(lambda: "SET_HEATER_TEMPERATURE HEATER=chamber_heater TARGET=50" in gcodes()) and wait_until(lambda: "50°" in row("heater_generic chamber_heater").locator(".temp-row__target").inner_text()), gcodes()[-2:])
    row("temperature_fan mcu_fan").locator(".temp-row__target").click()
    pg.locator(".temp-target").get_by_role("button", name="Spegni").click()
    ok("the fan's target off: SET_TEMPERATURE_FAN_TARGET TEMPERATURE_FAN=mcu_fan TARGET=0", wait_until(lambda: "SET_TEMPERATURE_FAN_TARGET TEMPERATURE_FAN=mcu_fan TARGET=0" in gcodes()), gcodes()[-2:])
    row("extruder").locator(".temp-row__target").click()
    ok("the nozzle's target opens the usual temperature dialog", wait_until(lambda: pg.locator(".temp-target").count() == 0 and pg.locator(".modal, .confirm-overlay, .sheet-overlay").count() >= 1))
    pg.keyboard.press("Escape")
    ok("no horizontal overflow", pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    ok("no page errors", not errs(P), errs(P)[:2])
    pg.reload()
    pg.wait_for_timeout(2400)
    ok("the hidden line and the minutes stay on this device", wait_until(lambda: len(names(P)) == 6) and pg.locator('[data-series="temperature_sensor raspberry_pi"]').count() == 0 and pg.locator('.temp-ranges [data-range="5"]').get_attribute("aria-pressed") == "true")
    P.close()

    # 320 px, and a printer with only the nozzle and the bed
    mock.reset()
    P = Page(b, mock, 320, 640)
    CUR[0] = P
    P.goto("home", 2400)
    ok("[320] a printer with just a nozzle and a bed", wait_until(lambda: names(P) == ["extruder", "heater_bed"]), names(P))
    ok("[320] nothing sticks out", P.pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    P.close()

    # computer
    P = fresh(b, 1440, 900)
    ok("desktop: the card under the camera and the print", wait_until(lambda: P.pg.locator(".desk-device__main .temp-card").count() == 1 and len(names(P)) == 6))
    P.pg.screenshot(path=out + "/desktop.png")
    ok("desktop: no page errors", not errs(P), errs(P)[:2])
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
