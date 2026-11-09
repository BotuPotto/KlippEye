"""Release 1.34.0 (roadmap 6b part 5): the console's tools, like Mainsail's: clear, autoscroll on / off, newest on top or at
the bottom, temperatures shown or hidden (kept on this device), full screen. On the phone (Control page) and on a computer
(the console bar's panel). Against the mock.
Usage: console_test.py <html> <outdir> <port>"""
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
NOW = 1760000000


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


def gcodes():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/gcode").read())


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


def lines(P, scope=".console-well"):
    return [t.strip() for t in P.pg.locator(scope).first.locator(".log-msg").all_inner_texts()]


def option(P, key):
    P.pg.locator('button[aria-label="Opzioni della console"]').first.click()
    P.pg.wait_for_selector(".oui-menu")
    P.pg.locator('.console-option[data-option="%s"]' % key).click()
    P.pg.keyboard.press("Escape")
    P.settle(250)


def extra(n, start=200, word="line"):
    return [{"message": "%s %d" % (word, i), "time": NOW + start + i, "type": "response"} for i in range(n)]


with sync_playwright() as p:
    b = p.chromium.launch()

    P = fresh(b)
    pg = P.pg
    card = pg.locator(".oui-card:has(.console-well)").first
    ok("the console card has clear, options and full screen", card.locator('button[aria-label="Pulisci la console"]').count() == 1 and card.locator('button[aria-label="Opzioni della console"]').count() == 1 and card.locator('button[aria-label="Schermo intero"]').count() == 1)
    ok("by default: oldest first, temperatures hidden", wait_until(lambda: lines(P)[:1] == ["G28"] and lines(P)[-1] == "plain info line" and not any(l.startswith("B:60.1") for l in lines(P))), lines(P))
    pg.locator('button[aria-label="Opzioni della console"]').first.click()
    pg.wait_for_selector(".oui-menu")
    states = {o.get_attribute("data-option"): o.get_attribute("aria-checked") for o in pg.locator(".console-option").all()}
    ok("the options menu: autoscroll on, newest on top off, temperatures off", states == {"autoscroll": "true", "newestOnTop": "false", "showTemps": "false"}, states)
    pg.screenshot(path=out + "/options_390.png")
    pg.keyboard.press("Escape")
    P.settle(200)

    option(P, "showTemps")
    ok("'Mostra le temperature': the temperature report appears", wait_until(lambda: any(l.startswith("B:60.1") for l in lines(P))), lines(P))
    option(P, "newestOnTop")
    ok("'Più recenti in alto': the newest line first", wait_until(lambda: lines(P)[:1] == ["plain info line"] and lines(P)[-1] == "G28"), lines(P))
    P.pg.reload()
    P.pg.wait_for_timeout(2400)
    ok("the choices stay on this device after a reload", wait_until(lambda: lines(P)[:1] == ["plain info line"] and any(l.startswith("B:60.1") for l in lines(P))), lines(P))
    option(P, "newestOnTop")
    option(P, "showTemps")

    # 1.69: the HTML in Klipper's messages is drawn, as in Mainsail; a command link fills the input field
    mock.set(console_extra=[
        {"message": '// Use <a class="command">SAVE_CONFIG</a> to <b>save</b><script>window.__hit=1</script><img src="x" onerror="window.__hit=2">', "time": NOW + 150, "type": "response"},
        {"message": '!! Probe <span style="color: red" onclick="window.__hit=3">failed</span>', "time": NOW + 151, "type": "response"},
        {"message": "_SET_TIMELAPSE_SETUP  ENABLE=True VERBOSE=False PARK_ENABLE=False", "time": NOW + 152, "type": "command"},
    ])
    link = pg.locator(".console-well .log-cmd").first
    ok("a <a class=\"command\"> is drawn as a link, not printed", wait_until(lambda: link.count() == 1 and link.inner_text() == "SAVE_CONFIG"), lines(P)[-3:])
    msg = pg.locator(".console-well .log-msg", has_text="SAVE_CONFIG").first
    ok("... the '// ' mark dropped, <b> drawn, no tag printed", msg.inner_text().strip() == "Use SAVE_CONFIG to save" and msg.locator("b").count() == 1, msg.inner_text())
    ok("... scripts, images and event attributes are left out", msg.locator("img, script").count() == 0 and pg.evaluate("() => window.__hit") is None)
    red = pg.locator(".console-well .log-msg", has_text="failed").first
    ok("... an error keeps its colour, the '!! ' dropped, a coloured span kept", red.inner_text().strip() == "Probe failed" and "log--error" in (red.get_attribute("class") or "") and red.locator("span").first.evaluate("e => e.style.color") == "red")
    ok("... moonraker-timelapse's own _SET_TIMELAPSE_SETUP line is not shown", not any("_SET_TIMELAPSE_SETUP" in l for l in lines(P)))
    red.locator("span").first.click()
    link.click()
    ok("... a click on the command puts it in the input field", wait_until(lambda: pg.locator(".console-input").first.input_value() == "SAVE_CONFIG") and pg.evaluate("() => window.__hit") is None)
    pg.locator(".console-input").first.fill("")
    mock.set(console_extra=[])

    pg.locator('button[aria-label="Pulisci la console"]').first.click()
    ok("'Pulisci' empties the view", wait_until(lambda: lines(P) == [] and "Niente di nuovo" in pg.locator(".console-well").first.inner_text()), lines(P))
    mock.set(console_extra=extra(1, word="after the clear"))
    ok("... and then shows only what comes after", wait_until(lambda: lines(P) == ["after the clear 0"]), lines(P))
    pg.locator(".console-input").first.fill("M115")
    pg.locator(".console-input").first.press("Enter")
    ok("a command sent after the clear is shown", wait_until(lambda: "M115" in gcodes()))

    # autoscroll
    mock.set(console_extra=extra(60))
    well = pg.locator(".console-well").first
    at_bottom = "e => e.scrollHeight - e.scrollTop - e.clientHeight < 4"
    ok("autoscroll on: the log follows the newest line", wait_until(lambda: len(lines(P)) >= 60 and well.evaluate(at_bottom)))
    option(P, "autoscroll")
    mock.set(console_extra=extra(120))
    ok("autoscroll off: new lines arrive, the log stays where it was", wait_until(lambda: len(lines(P)) >= 120) and not well.evaluate(at_bottom))
    # 1.69: ... and the text in view does not slide when the oldest lines drop off the list (it did, "autoscroll" seemed on)
    well.evaluate("e => { e.scrollTop = e.scrollHeight - e.clientHeight - 300; e.dispatchEvent(new Event('scroll')); }")
    P.settle(300)
    first_visible = "e => { const top = e.getBoundingClientRect().top; const l = [...e.querySelectorAll('.log-line')].find(x => x.getBoundingClientRect().bottom > top + 1); return l ? [l.querySelector('.log-msg').textContent, Math.round(l.getBoundingClientRect().top - top)] : null; }"
    before = well.evaluate(first_visible)
    mock.set(console_extra=extra(220))
    wait_until(lambda: "line 219" in lines(P))
    P.settle(500)
    after = well.evaluate(first_visible)
    ok("autoscroll off: the oldest lines drop off, the text in view stays put", before is not None and before == after and lines(P)[0] != "G28", (before, after, lines(P)[:1]))
    option(P, "autoscroll")

    # full screen
    pg.locator('button[aria-label="Schermo intero"]').first.click()
    full = pg.locator(".console-full")
    ok("'Schermo intero': the console covers the screen", wait_until(lambda: full.count() == 1) and full.bounding_box()["height"] >= 840 and full.bounding_box()["width"] >= 389)
    pg.locator('.console-full button[aria-label="Opzioni della console"]').click()
    ok("... its options menu opens above it", wait_until(lambda: pg.locator(".oui-menu").is_visible()) and pg.evaluate("() => { const r = document.querySelector('.oui-menu').getBoundingClientRect(); const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!(el && el.closest('.oui-menu')); }"))
    pg.keyboard.press("Escape")
    P.settle(300)
    ok("... Escape closes the menu, the full screen stays", pg.locator(".console-full").count() == 1)
    if pg.locator(".console-full").count() == 0:
        pg.locator('button[aria-label="Schermo intero"]').first.click()
        P.settle(400)
    full.locator(".console-input").fill("G28 X")
    full.locator(".console-input").press("Enter")
    ok("... and sends from its own field", wait_until(lambda: "G28 X" in gcodes()))
    pg.screenshot(path=out + "/fullscreen_390.png")
    full.locator('button[aria-label="Esci da schermo intero"]').click()
    ok("leaving full screen", wait_until(lambda: pg.locator(".console-full").count() == 0))
    P.close()

    # ---- computer: the console bar's panel
    P = fresh(b, tab="home", w=1440, h=900)
    pg = P.pg
    ok("desktop: the bar's preview hides the temperatures", wait_until(lambda: "plain info line" in pg.locator(".desk-dock__log").inner_text() and "B:60.1" not in pg.locator(".desk-dock__log").inner_text()))
    pg.locator(".desk-dock__expand").click()
    ok("the panel has the tools", wait_until(lambda: pg.locator('.desk-drawer button[aria-label="Pulisci la console"]').count() == 1 and pg.locator('.desk-drawer button[aria-label="Schermo intero"]').count() == 1))
    pg.screenshot(path=out + "/desktop_panel.png")
    pg.locator('.desk-drawer button[aria-label="Pulisci la console"]').click()
    ok("clearing there empties the bar's preview too", wait_until(lambda: pg.locator(".desk-dock__line").count() == 0))
    pg.locator('.desk-drawer button[aria-label="Schermo intero"]').click()
    ok("full screen from the panel", wait_until(lambda: pg.locator(".console-full").count() == 1))
    pg.keyboard.press("Escape")
    ok("Escape leaves the full screen", wait_until(lambda: pg.locator(".console-full").count() == 0))
    P.close()

    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
