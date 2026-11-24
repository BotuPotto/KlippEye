import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof K7: two tabs. Tab A has printer.cfg open; tab B saves a change; tab A presses Save: B's change is overwritten with no
warning (Save never checks that the file on the Pi is still the text the editor opened), and the 'earlier version' kept is A's
own old text, so B's change is not in the versions either.
Run: cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../docs/audits/2026-11-24-proofs/K/two_tabs.py ../../frontend/klippeye_frontend.html /tmp/k7 8798
"""
import sys, os, re, json, urllib.request
sys.path.insert(0, os.getcwd())
from playwright.sync_api import sync_playwright
from lib import *
html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
B_TEXT = "[stepper_x]\n# saved by tab B\nrotation_distance: 40\n"
with sync_playwright() as p:
    b = p.chromium.launch(); mock.reset()
    A = Page(b, mock, 390, 844); A.goto("config", 1800)
    A.pg.locator(".cfg-row", has=A.pg.locator(".cfg-row__name", has_text=re.compile("^printer.cfg$"))).first.locator(".cfg-row__main").click()
    A.pg.wait_for_selector(".screen--editor .cm-editor"); A.pg.wait_for_timeout(500)
    A.pg.evaluate("() => { const v = CM.EditorView.findFromDOM(document.querySelector('.screen--editor .cm-editor')); v.dispatch({changes: {from: 0, insert: '# tab A edit\\n'}}); }")
    Bp = Page(b, mock, 390, 844); Bp.goto("config", 1500)     # a second browser tab / phone
    Bp.pg.evaluate("""async (text) => { const f = new FormData(); f.append('file', new Blob([text]), 'printer.cfg'); f.append('root', 'config'); await fetch('/server/files/upload', {method:'POST', body:f}); }""", B_TEXT)
    A.pg.locator(".editor-save").first.click(); A.pg.wait_for_timeout(1500)
    on_pi = urllib.request.urlopen(mock.base + "/server/files/config/printer.cfg").read().decode()
    print("tab B's change survived on the Pi:", "saved by tab B" in on_pi)
    vers = json.loads(urllib.request.urlopen(mock.base + "/api/config/versions?path=printer.cfg").read())["versions"]
    kept = [json.loads(urllib.request.urlopen(mock.base + "/api/config/versions/%s?path=printer.cfg" % v["id"]).read())["content"] for v in vers]
    print("tab B's change is in a kept version:", any("saved by tab B" in k for k in kept))
    print("any warning dialog in tab A:", A.dialogs)
    b.close()
