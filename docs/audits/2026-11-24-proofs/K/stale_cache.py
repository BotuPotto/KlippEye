import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof K1: the config editor shows a cached copy of the file, so a change made on the Pi after the first read
(SAVE_CONFIG, a second browser) is overwritten by the next Save, and the kept 'earlier version' is the stale text too.
Run: cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../docs/audits/2026-11-24-proofs/K/stale_cache.py ../../frontend/klippeye_frontend.html /tmp/k1 8791
"""
import sys, os, re, json, urllib.request
sys.path.insert(0, os.getcwd())
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
NEWER = "[stepper_x]\n# written by Klipper's SAVE_CONFIG after the editor first read the file\n#*# [probe]\n#*# z_offset = 1.234\n"

def open_printer_cfg(P):
    P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^printer.cfg$"))).first.locator(".cfg-row__main").click()
    P.pg.wait_for_selector(".screen--editor .cm-editor"); P.pg.wait_for_timeout(500)
VIEW = "CM.EditorView.findFromDOM(document.querySelector('.screen--editor .cm-editor'))"

with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    P = Page(b, mock, 390, 844); P.goto("config", 1800)
    open_printer_cfg(P)                                   # first read: the text is cached by the page
    first = P.pg.evaluate("() => %s.state.doc.toString()" % VIEW)
    P.pg.locator(".editor-close").click(); P.pg.wait_for_timeout(300)
    # "Klipper wrote printer.cfg" (SAVE_CONFIG) or "another browser saved": the file on the Pi changes under the page
    P.pg.evaluate("""async (text) => { const f = new FormData(); f.append('file', new Blob([text]), 'printer.cfg'); f.append('root', 'config'); await fetch('/server/files/upload', {method:'POST', body:f}); }""", NEWER)
    open_printer_cfg(P)                                   # the editor opens again
    shown = P.pg.evaluate("() => %s.state.doc.toString()" % VIEW)
    print("editor shows the file as it is on the Pi now:", shown == NEWER)
    print("editor shows the first (stale) copy        :", shown == first)
    P.pg.evaluate("() => { const v = %s; v.dispatch({changes: {from: v.state.doc.length, insert: '\\n# my edit'}}); }" % VIEW)
    P.pg.locator(".editor-save").first.click(); P.pg.wait_for_timeout(1500)
    disk = json.loads(urllib.request.urlopen(mock.base + "/server/files/directory?path=config").read())
    on_pi = urllib.request.urlopen(mock.base + "/server/files/config/printer.cfg").read().decode()
    print("printer.cfg on the Pi still has the SAVE_CONFIG block:", "z_offset = 1.234" in on_pi)
    vers = json.loads(urllib.request.urlopen(mock.base + "/api/config/versions?path=printer.cfg").read())["versions"]
    kept = [json.loads(urllib.request.urlopen(mock.base + "/api/config/versions/%s?path=printer.cfg" % v["id"]).read())["content"] for v in vers]
    print("a kept earlier version holds the lost SAVE_CONFIG block:", any("z_offset = 1.234" in k for k in kept))
    b.close()
