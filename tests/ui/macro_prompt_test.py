"""Release 1.71: windows opened by Klipper macros (RESPOND TYPE=command MSG="action:prompt_…"): title, text, buttons, groups, footer buttons; a button sends its command; ✕ sends action:prompt_end; the
window opens on every device and after a reload, closes on prompt_end; the prompt lines are not shown in the console.
Usage: macro_prompt_test.py <html> <outdir> <port>"""
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


def gcode(script):
    urllib.request.urlopen(urllib.request.Request(mock.base + "/printer/gcode/script", data=json.dumps({"script": script}).encode(), headers={"Content-Type": "application/json"}))


def respond(msg):
    gcode('RESPOND TYPE=command MSG="action:prompt_%s"' % msg)


def sent():
    return state()["gcode_log"]


PROMPT = ["begin Filament change", "text Load the <b>new</b> filament, then choose:", "button_group_start", "button Purge 10 mm|PURGE LENGTH=10|primary",
          "button Purge 50 mm|PURGE LENGTH=50", "button_group_end", "button Unload|UNLOAD_FILAMENT|warning", "footer_button Cancel|CANCEL_PRINT|error",
          "footer_button Done|RESUME|primary", "show"]

with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("home", 2200)
    pg = P.pg
    dialog = pg.locator(".macro-prompt")
    for line in PROMPT[:-1]:
        respond(line)
    P.settle(3000)
    ok("before «show»: no window", dialog.count() == 0)
    respond(PROMPT[-1])
    ok("«show»: the window opens with its title", wait_until(lambda: dialog.count() == 1, 10) and "Filament change" in dialog.locator(".dialog-title").inner_text())
    ok("... its text, with the macro's HTML drawn (bold), no tags printed", dialog.locator(".macro-prompt__text").inner_text() == "Load the new filament, then choose:" and dialog.locator(".macro-prompt__text b").count() == 1)
    rows = dialog.locator(".macro-prompt__body .macro-prompt__row")
    ok("... a group of two buttons on one row, then a button on its own", rows.count() == 2 and rows.nth(0).locator("button").all_inner_texts() == ["Purge 10 mm", "Purge 50 mm"] and rows.nth(1).locator("button").all_inner_texts() == ["Unload"], [r.inner_text() for r in rows.all()])
    ok("... the colours: primary, warning, error", "oui-btn--primary" in rows.nth(0).locator("button").first.get_attribute("class") and "is-warning" in rows.nth(1).locator("button").first.get_attribute("class") and "oui-btn--danger" in dialog.locator(".macro-prompt__footer button").first.get_attribute("class"))
    ok("... the footer buttons at the bottom", dialog.locator(".macro-prompt__footer button").all_inner_texts() == ["Cancel", "Done"])
    pg.screenshot(path=out + "/phone.png")
    rows.nth(0).locator("button").nth(1).click()
    ok("a button sends its command", wait_until(lambda: "PURGE LENGTH=50" in sent()))
    ok("... and the window stays (the macro decides when it ends)", dialog.count() == 1)
    pg.reload(); P.settle(2200)
    ok("after a reload it is there again", wait_until(lambda: dialog.count() == 1, 10))
    Q = Page(b, mock, 1440, 900)
    Q.goto("files", 2200)
    ok("on another device (a computer, another page) too", wait_until(lambda: Q.pg.locator(".macro-prompt").count() == 1, 10))
    Q.pg.screenshot(path=out + "/desktop.png")
    ok("the prompt lines are not shown in the console", "action:prompt" not in Q.pg.locator(".desk-dock").inner_text())
    Q.pg.locator(".macro-prompt .macro-prompt__footer button", has_text="Done").click()
    ok("a footer button sends its command", wait_until(lambda: "RESUME" in sent()))
    respond("end")
    ok("«end» from the macro: closed everywhere", wait_until(lambda: dialog.count() == 0 and Q.pg.locator(".macro-prompt").count() == 0, 10))
    Q.close()
    # ✕ closes it here at once and sends prompt_end
    respond("begin Question")
    respond("text Continue?")
    respond("show")
    ok("a new window", wait_until(lambda: dialog.count() == 1 and "Question" in dialog.inner_text(), 10))
    dialog.locator(".dialog-close").click()
    ok("✕: closed at once, RESPOND …action:prompt_end sent", wait_until(lambda: dialog.count() == 0) and any("action:prompt_end" in g for g in sent()))
    P.settle(2500)
    ok("... and it stays closed", dialog.count() == 0)
    ok("no page errors", not errs(P), errs(P)[:2])
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
