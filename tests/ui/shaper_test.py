"""Releases 1.80 and 1.89: the input shaper graphs (Control on the phone, Calibration on the computer): the files
SHAPER_CALIBRATE leaves in /tmp (made up by the mock, read by the real backend/shaper_data.py), drawn as an axis
frequency profile (the vibrations of all axes and of each, what the two recommended shapers leave, the two bands, the
numbered peaks, each shaper's response dotted, a legend that hides and shows them), the recommendations, the table
(frequency, vibrations, smoothing, max accel), «Save …» writing the chosen shaper where Klipper reads it (a new
[input_shaper] in printer.cfg, Klipper's own block at its end, or the included file that has the section) and applying
it, «Measure X/Y» with their settings (empty: not sent; kept on the device), no files.
Usage: shaper_test.py <html> <outdir> <port>"""
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


def gcodes():
    return state()["gcode_log"]


def cfg_text(path):
    f = state()["cfg"]["files"].get(path)
    return None if f is None else f["content"]


def with_files(**contents):
    """The config tree with these files (path: text) written in it."""
    tree = state()["cfg"]
    for path, text in contents.items():
        tree["files"][path] = {"size": len(text), "modified": 1700000000, "content": text}
        if "/" in path:
            tree["dirs"][path.rsplit("/", 1)[0]] = 1700000000
    return tree


def open_page(b, w, hh, files=None, **st):
    mock.reset()
    if files:
        st["cfg"] = with_files(**files)
    if st:
        mock.set(**st)
    P = Page(b, mock, w, hh)
    CUR[0] = P
    P.goto("controllo", 2600)
    card = P.pg.locator(".shaper-card")
    wait_until(lambda: card.count() == 1, 8)
    card.scroll_into_view_if_needed()  # the cards below the screen fill in when they come into view
    wait_until(lambda: card.locator(".shaper-chart").count() == 1, 8)
    return P


def save(card, pg, shaper):
    card.locator('[data-shaper-row="%s"] .shaper-row__pick' % shaper).click()
    card.locator('[data-shaper-save="%s"]' % shaper).click()
    dialog = pg.locator(".confirm-card")
    wait_until(lambda: dialog.count() == 1)
    dialog.locator(".oui-btn--primary").click()


AUTOSAVE = """[printer]
kinematics: corexy

#*# <---------------------- SAVE_CONFIG ---------------------->
#*# DO NOT EDIT THIS BLOCK OR BELOW. The contents are auto-generated.
#*#
#*# [input_shaper]
#*# shaper_type_x = mzv
#*# shaper_freq_x = 52.4
#*# shaper_type_y = ei
#*# shaper_freq_y = 55.0
#*#
#*# [probe]
#*# z_offset = 1.200
"""

with sync_playwright() as p:
    b = p.chromium.launch()
    for w, hh in ((390, 844), (1440, 900)):
        P = open_page(b, w, hh, files={"macros/park.cfg": "[gcode_macro PARK]\ngcode:\n    G28\n", "macros/led.cfg": "[led status]\nred_pin: PA2\n"})
        pg = P.pg
        card = pg.locator(".shaper-card")
        ok("%d: the card, with the shaper printer.cfg sets" % w, wait_until(lambda: "X MZV 52,4 Hz" in card.locator("[data-shaper-current]").inner_text() and "Y EI 55,0 Hz" in card.locator("[data-shaper-current]").inner_text(), 8), card.evaluate("e => e.outerHTML.slice(0, 900)") if card.count() else "no card")
        chart = card.locator(".shaper-chart[data-axis=x]")
        ok("%d: X first: the title with ω0 and ζ" % w, wait_until(lambda: "Profilo di frequenza dell'asse (ω0=5" in chart.locator("[data-shaper-title]").inner_text() and "ζ=0," in chart.locator("[data-shaper-title]").inner_text(), 8), chart.locator("[data-shaper-title]").inner_text() if chart.count() else "")
        ok("%d: the vibrations of all axes, X and Y (Z hidden at first), what MZV leaves" % w, all(chart.locator('[data-series="%s"]' % s).count() == 1 for s in ("sum", "x", "y", "after-mzv")) and chart.locator('[data-series="z"]').count() == 0, [chart.locator("[data-series]").evaluate_all("l => l.map(e => e.dataset.series)")])
        ok("%d: the four shapers' responses, the two bands, the numbered peaks" % w, chart.locator(".shaper-chart__shaper").count() == 4 and chart.locator("[data-shaper-band]").count() == 2 and chart.locator("[data-shaper-peak]").count() >= 1 and chart.locator('[data-shaper-peak="1"] text').text_content() == "1", [chart.locator(".shaper-chart__shaper").count(), chart.locator("[data-shaper-band]").count(), chart.locator("[data-shaper-peak]").count()])
        ok("%d: the vibrations' scale with its power of ten" % w, chart.locator("[data-shaper-exponent]").count() == 1 and "×10" in chart.locator("[data-shaper-exponent]").text_content())
        advice = card.locator("[data-shaper-advice]")
        ok("%d: the recommendations: performance, low vibrations, damping" % w, "Per le prestazioni: MZV a 52,0 Hz" in advice.inner_text() and "Per meno vibrazioni:" in advice.inner_text() and "Smorzamento stimato ζ = 0," in advice.inner_text(), advice.inner_text() if advice.count() else "")
        heads = card.locator(".shaper-table thead th").all_inner_texts()
        ok("%d: the table's columns" % w, [t.strip().lower() for t in heads] == ["tipo", "frequenza\nhz", "vibrazioni\n%", "smussatura", "accel. max\nmm/s²"], heads)
        rows = card.locator("[data-shaper-row]")
        mzv = card.locator('[data-shaper-row="mzv"]')
        ok("%d: four rows, MZV in use and chosen (the recommended one), with smoothing and max accel" % w, rows.count() == 4 and "in uso" in mzv.inner_text() and "is-selected" in mzv.get_attribute("class") and float(mzv.locator("[data-smoothing]").get_attribute("data-smoothing")) > 0 and int(mzv.locator("[data-max-accel]").get_attribute("data-max-accel")) > 1000, mzv.inner_text())
        ok("%d: «Save MZV at 52.0 Hz in printer.cfg»" % w, "Salva MZV a 52,0 Hz in printer.cfg" in card.locator('[data-shaper-save="mzv"]').inner_text())
        ok("%d: no «Try»" % w, card.locator("[data-shaper-apply]").count() == 0)
        if w == 390:
            pg.screenshot(path=out + "/phone_x.png", full_page=False)
            card.locator(".shaper-chart").screenshot(path=out + "/phone_chart.png")
            # the legend hides and shows a line
            card.locator('[data-shaper-legend="sum"]').click()
            ok("the legend: X+Y+Z hidden (and its peaks)", wait_until(lambda: chart.locator('[data-series="sum"]').count() == 0 and chart.locator("[data-shaper-peak]").count() == 0 and card.locator('[data-shaper-legend="sum"]').get_attribute("aria-pressed") == "false"))
            card.locator('[data-shaper-legend="sum"]').click()
            card.locator('[data-shaper-legend="z"]').click()
            ok("the legend: X+Y+Z back, Z shown", wait_until(lambda: chart.locator('[data-series="sum"]').count() == 1 and chart.locator('[data-series="z"]').count() == 1))
            # a row chosen: its line stands out
            card.locator('[data-shaper-row="zv"] .shaper-row__pick').click()
            ok("ZV chosen: its line solid, the button says ZV", wait_until(lambda: chart.locator('.shaper-chart__shaper.is-selected[data-shaper="zv"]').count() == 1 and card.locator('[data-shaper-save="zv"]').count() == 1))
            box = card.locator(".shaper-chart__svg").bounding_box()
            pg.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + box["height"] / 2)
            ok("the pointer: the frequency, the vibrations, what ZV lets through", wait_until(lambda: "Hz" in card.locator(".shaper-chart__tip").inner_text() and "Vibrazioni:" in card.locator(".shaper-chart__tip").inner_text() and "ZV lascia passare" in card.locator(".shaper-chart__tip").inner_text()), card.locator(".shaper-chart__tip").inner_text() if card.locator(".shaper-chart__tip").count() else "")
            pg.mouse.move(5, 5)
            # Save: asks, writes a new [input_shaper] in printer.cfg (none anywhere), keeps a version, applies it
            card.locator('[data-shaper-save="zv"]').click()
            dialog = pg.locator(".confirm-card")
            ok("«Save» asks first", wait_until(lambda: dialog.count() == 1 and "Salvare ZV a 58,2 Hz per X?" in dialog.inner_text()), dialog.inner_text() if dialog.count() else "")
            pg.screenshot(path=out + "/phone_save.png")
            dialog.locator(".oui-btn--primary").click()
            ok("saved: a new [input_shaper] in printer.cfg, the rest kept", wait_until(lambda: "[input_shaper]\nshaper_type_x: zv\nshaper_freq_x: 58.2" in (cfg_text("printer.cfg") or "") and "[gcode_macro PARK]" in cfg_text("printer.cfg"), 8), (cfg_text("printer.cfg") or "")[-200:])
            ok("saved: the version before kept, then SET_INPUT_SHAPER", "printer.cfg" in state().get("versions_log", []) and wait_until(lambda: any(g == "SET_INPUT_SHAPER SHAPER_TYPE_X=zv SHAPER_FREQ_X=58.2" for g in gcodes())), [state().get("versions_log"), gcodes()[-3:]])
            ok("saved: the card says ZV is in use for X", wait_until(lambda: "X ZV 58,2 Hz" in card.locator("[data-shaper-current]").inner_text() and "in uso" in card.locator('[data-shaper-row="zv"]').inner_text()))
            # the Y axis
            card.locator('[data-shaper-axis="y"]').click()
            ok("the Y axis: its own measurement, EI in use", wait_until(lambda: card.locator(".shaper-chart[data-axis=y]").count() == 1 and "in uso" in card.locator('[data-shaper-row="ei"]').inner_text(), 8))
            # the measurement's settings
            card.locator('[data-shaper-params="y"]').click()
            panel = card.locator('[data-shaper-params-panel="y"]')
            ok("«Measure Y ▾»: the settings, Klipper's values in grey ([resonance_tester] max_freq 120)", wait_until(lambda: panel.count() == 1 and panel.locator('[data-shaper-param]').count() == 5 and panel.locator('[data-shaper-param="FREQ_END"]').get_attribute("placeholder") == "120" and panel.locator('[data-shaper-param="FREQ_START"]').get_attribute("placeholder") == "5") and card.locator('[data-shaper-params="y"]').get_attribute("aria-expanded") == "true")
            panel.locator('[data-shaper-param="FREQ_START"]').fill("10")
            panel.locator('[data-shaper-param="HZ_PER_SEC"]').fill("2")
            panel.locator('[data-shaper-param="ACCEL_PER_HZ"]').fill("abc")
            ok("a value not valid: marked", panel.locator('[data-shaper-param="ACCEL_PER_HZ"]').get_attribute("aria-invalid") == "true")
            pg.screenshot(path=out + "/phone_params.png")
            card.locator('[data-shaper-measure="y"]').click()
            dialog = pg.locator(".confirm-card")
            ok("«Measure Y» asks first, with the settings", wait_until(lambda: dialog.count() == 1 and "Misurare l'asse Y?" in dialog.inner_text() and "FREQ_START=10 HZ_PER_SEC=2" in dialog.inner_text()), dialog.inner_text() if dialog.count() else "")
            dialog.locator(".oui-btn--primary").click()
            ok("then SHAPER_CALIBRATE AXIS=Y with the valid settings only", wait_until(lambda: "SHAPER_CALIBRATE AXIS=Y FREQ_START=10 HZ_PER_SEC=2" in gcodes()), gcodes()[-3:])
            # kept on the device
            pg.reload()
            pg.wait_for_timeout(2600)
            card = pg.locator(".shaper-card")
            wait_until(lambda: card.count() == 1, 8)
            card.scroll_into_view_if_needed()
            wait_until(lambda: card.locator('[data-shaper-params="y"]').count() == 1, 8)
            card.locator('[data-shaper-params="y"]').click()
            panel = card.locator('[data-shaper-params-panel="y"]')
            ok("the settings kept after a reload; X has none", wait_until(lambda: panel.locator('[data-shaper-param="FREQ_START"]').input_value() == "10") and "modificate" in card.locator('[data-shaper-params="y"]').get_attribute("aria-label") and "modificate" not in card.locator('[data-shaper-params="x"]').get_attribute("aria-label"))
            panel.locator("[data-shaper-params-reset]").click()
            card.locator('[data-shaper-measure="y"]').click()
            pg.locator(".confirm-card .oui-btn--primary").click()
            ok("«Defaults»: SHAPER_CALIBRATE AXIS=Y alone", wait_until(lambda: gcodes()[-1] == "SHAPER_CALIBRATE AXIS=Y"), gcodes()[-3:])
        ok("%d: the table fits" % w, card.locator(".shaper-table-box").evaluate("e => e.scrollWidth <= e.clientWidth"), card.locator(".shaper-table-box").evaluate("e => [e.scrollWidth, e.clientWidth]"))
        ok("%d: no horizontal overflow, no page errors" % w, pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth") and not errs(P), errs(P)[:2])
        if w == 1440:
            pg.screenshot(path=out + "/desktop.png", full_page=False)
            card.locator(".shaper-chart").screenshot(path=out + "/desktop_chart.png")
        P.close()

    # Klipper's own block has [input_shaper]: the value is changed there, nothing added above
    P = open_page(b, 390, 844, files={"printer.cfg": AUTOSAVE})
    card = P.pg.locator(".shaper-card")
    save(card, P.pg, "ei")
    text = lambda: cfg_text("printer.cfg") or ""
    ok("autosave: X changed in Klipper's block (its way of writing)", wait_until(lambda: "#*# shaper_type_x = ei\n#*# shaper_freq_x = 65.0\n#*# shaper_type_y = ei" in text(), 8), text())
    ok("autosave: no [input_shaper] above, the rest as it was", "\n[input_shaper]" not in text() and text().startswith("[printer]\nkinematics: corexy\n\n#*# <----") and "#*# [probe]\n#*# z_offset = 1.200" in text(), text())
    P.close()

    # printer.cfg has the section without Y: Y is added to it
    P = open_page(b, 390, 844, files={"printer.cfg": "[printer]\nkinematics: corexy\n\n[input_shaper]\nshaper_freq_x: 52.4 # measured\nshaper_type_x: mzv\n\n[probe]\npin: PA1\n"})
    card = P.pg.locator(".shaper-card")
    card.locator('[data-shaper-axis="y"]').click()
    wait_until(lambda: card.locator(".shaper-chart[data-axis=y]").count() == 1, 8)
    save(card, P.pg, "mzv")
    ok("the body's section: Y added after X, before [probe]", wait_until(lambda: "[input_shaper]\nshaper_freq_x: 52.4 # measured\nshaper_type_x: mzv\nshaper_type_y: mzv\nshaper_freq_y: " in text() and text().index("shaper_freq_y") < text().index("[probe]"), 8), text())
    P.close()

    # the section is in an included file: that file is written, printer.cfg is not
    P = open_page(b, 390, 844, files={"printer.cfg": "[include hardware/*.cfg]\n[printer]\nkinematics: corexy\n", "hardware/shaper.cfg": "[input_shaper]\nshaper_type_x: mzv\nshaper_freq_x: 52.4\n", "hardware/probe.cfg": "[probe]\npin: PA1\n"}, )
    card = P.pg.locator(".shaper-card")
    save(card, P.pg, "zv")
    ok("include: the included file with [input_shaper] written", wait_until(lambda: cfg_text("hardware/shaper.cfg") == "[input_shaper]\nshaper_type_x: zv\nshaper_freq_x: 58.2\n", 8), [cfg_text("hardware/shaper.cfg"), state().get("versions_log")])
    ok("include: printer.cfg and the other file left alone", cfg_text("printer.cfg") == "[include hardware/*.cfg]\n[printer]\nkinematics: corexy\n" and cfg_text("hardware/probe.cfg") == "[probe]\npin: PA1\n" and not errs(P), [cfg_text("printer.cfg"), errs(P)[:2]])
    P.close()

    # not homed: the measurement homes first
    P = open_page(b, 390, 844, homed="")
    card = P.pg.locator(".shaper-card")
    wait_until(lambda: card.locator('[data-shaper-measure="x"]').count() == 1, 8)
    card.locator('[data-shaper-measure="x"]').click()
    ok("not homed: the dialog says the axes are homed first", wait_until(lambda: "homing" in P.pg.locator(".confirm-card").inner_text()))
    P.pg.locator(".confirm-card .oui-btn--primary").click()
    ok("not homed: G28, then SHAPER_CALIBRATE AXIS=X", wait_until(lambda: "G28\nSHAPER_CALIBRATE AXIS=X" in gcodes() or gcodes()[-2:] == ["G28", "SHAPER_CALIBRATE AXIS=X"]), gcodes()[-3:])
    P.close()

    # no files: said in words, the buttons still there
    mock.reset()
    mock.set(shaper_files=False)
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("controllo", 2600)
    card = P.pg.locator(".shaper-card")
    wait_until(lambda: card.count() == 1, 8)
    card.scroll_into_view_if_needed()
    ok("no measurement: said in words, «Measure X» / «Measure Y» there", wait_until(lambda: card.locator("[data-shaper-empty]").count() == 1 and card.locator("[data-shaper-measure]").count() == 2, 8), card.inner_text() if card.count() else "")
    ok("no measurement: no chart, no «Save», no page errors", card.locator(".shaper-chart").count() == 0 and card.locator("[data-shaper-save]").count() == 0 and not errs(P), errs(P)[:2])
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
