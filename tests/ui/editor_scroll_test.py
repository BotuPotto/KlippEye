"""The editor's colour layer and line numbers stay where the textarea is (also at the end of the file, and after a missed scroll event).
Usage: editor_scroll_test.py <html> <outdir> <port>"""
import sys, os, re
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
FAILS = []


def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra != "" else ""))


POS = """() => { const t = document.querySelector('.editor-input'), l = document.querySelector('.editor-layer'), n = document.querySelector('.editor-lines');
  return { t: [t.scrollTop, t.scrollLeft], l: [l.scrollTop, l.scrollLeft], n: n.scrollTop, max: t.scrollHeight - t.clientHeight }; }"""
BIG = "\n".join(("# " + "long line of text and more text " * 6 + str(i)) if i % 3 == 0 else f"key_{i}: value {i}" for i in range(1, 41)) + "\n"


def open_big(w, h, text=BIG):
    mock.reset()
    P = Page(b, mock, w, h); P.goto("config", 1800)
    P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^printer.cfg$"))).first.locator(".cfg-row__main").click()
    P.pg.wait_for_selector(".editor-input"); P.pg.wait_for_timeout(500)
    P.pg.evaluate("(t) => { const el = document.querySelector('.editor-input'); el.focus(); el.select(); document.execCommand('insertText', false, t); el.setSelectionRange(0, 0); }", text)
    P.pg.wait_for_timeout(300)
    return P


def synced(r): return r["l"] == r["t"] and r["n"] == r["t"][0]


with sync_playwright() as p:
    b = p.chromium.launch()
    for w, h in ((390, 500), (390, 844), (320, 480), (1440, 900)):
        P = open_big(w, h)
        for where, js in (("middle", "t.scrollTop = (t.scrollHeight - t.clientHeight) / 2; t.scrollLeft = 300"), ("end of the file", "t.scrollTop = t.scrollHeight; t.scrollLeft = t.scrollWidth"), ("top", "t.scrollTop = 0; t.scrollLeft = 0")):
            P.pg.evaluate("() => { const t = document.querySelector('.editor-input'); " + js + "; }"); P.pg.wait_for_timeout(250)
            r = P.pg.evaluate(POS)
            ok(f"[{w}x{h}] {where}: colour layer and line numbers are exactly where the textarea is", synced(r), r)
        # the end of the file is really the end: the last line (the empty one after the final newline) is reachable
        P.pg.evaluate("() => { const t = document.querySelector('.editor-input'); t.scrollTop = t.scrollHeight; }"); P.pg.wait_for_timeout(250)
        r = P.pg.evaluate(POS); ok(f"[{w}x{h}] the textarea is really at the end", r["t"][0] >= r["max"] - 1, r)
        # a scroll that was never announced, while the user is in the text: the layers are brought back by themselves
        r = P.pg.evaluate("() => { document.querySelector('.editor-layer').scrollTop = 7; document.querySelector('.editor-lines').scrollTop = 3; return (" + POS + ")(); }")
        ok(f"[{w}x{h}] [setup] layers pushed out of place without any event", not synced(r), r)
        P.pg.wait_for_timeout(150)
        r = P.pg.evaluate(POS); ok(f"[{w}x{h}] with the focus in the text they are back within a few frames, with no event at all", synced(r), r)
        # without the focus nothing keeps running; the next touch / selection change / scroll brings them back
        P.pg.evaluate("() => document.querySelector('.editor-input').blur()"); P.pg.wait_for_timeout(500)
        P.pg.evaluate("() => { document.querySelector('.editor-layer').scrollTop = 7; }"); P.pg.wait_for_timeout(300)
        r = P.pg.evaluate(POS); ok(f"[{w}x{h}] without the focus the check is not running all the time", not synced(r), r)
        P.pg.evaluate("() => document.querySelector('.editor-input').dispatchEvent(new Event('touchend', { bubbles: true }))"); P.pg.wait_for_timeout(120)
        r = P.pg.evaluate(POS); ok(f"[{w}x{h}] after the next touch they are back", synced(r), r)
        P.pg.evaluate("() => { document.querySelector('.editor-layer').scrollTop = 11; }")
        P.pg.evaluate("() => document.querySelector('.editor-input').setSelectionRange(5, 40)"); P.pg.wait_for_timeout(200)
        r = P.pg.evaluate(POS); ok(f"[{w}x{h}] a selection change brings them back too", synced(r), r)
        P.close()

    # typing at the very end (the caret in the empty last line) and undo keep them together
    P = open_big(390, 500)
    P.pg.locator(".editor-input").click(); P.pg.keyboard.press("Control+End"); P.pg.keyboard.type("new line", delay=10); P.pg.keyboard.press("Enter"); P.pg.keyboard.type("x", delay=10); P.pg.wait_for_timeout(300)
    r = P.pg.evaluate(POS); ok("typing at the end of the file: together", synced(r) and r["t"][0] > 0, r)
    P.pg.keyboard.press("Control+z"); P.pg.keyboard.press("Control+z"); P.pg.wait_for_timeout(300)
    r = P.pg.evaluate(POS); ok("after undo: together", synced(r), r)
    # visual check: select the last lines, screenshot at the end
    P.pg.evaluate("() => { const t = document.querySelector('.editor-input'); t.focus(); t.setSelectionRange(t.value.length - 200, t.value.length); t.scrollTop = t.scrollHeight; }"); P.pg.wait_for_timeout(300)
    P.pg.locator(".editor-body").screenshot(path=f"{out}/selection_at_end_390.png", animations="disabled")
    ok("no page errors", not [e for e in P.errors if "pageerror" in e], P.errors[:2]); P.close()
    b.close()

print("\nFAILED: " + str(len(FAILS)) + " " + str(FAILS) if FAILS else "\nALL PASS")
sys.exit(1 if FAILS else 0)
