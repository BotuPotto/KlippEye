import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof K2: a system log opened from System > logs is an ordinary config-folder editor session: it is not read-only, and
Save uploads the (3000-line tail of the) log as a file named like the log into Moonraker's config folder.
Run: cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../docs/audits/2026-11-24-proofs/K/log_editor_writable.py ../../frontend/klippeye_frontend.html /tmp/k2 8792
"""
import sys, os, json, urllib.request
sys.path.insert(0, os.getcwd())
from playwright.sync_api import sync_playwright
from lib import *
html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
VIEW = "CM.EditorView.findFromDOM(document.querySelector('.screen--editor .cm-editor'))"
with sync_playwright() as p:
    b = p.chromium.launch(); mock.reset()
    P = Page(b, mock, 390, 844); P.goto("sistema", 2000)
    P.pg.locator(".log-row", has_text="klippy.log").first.locator("button", has_text="Apri").click()
    P.pg.wait_for_selector(".screen--editor .cm-editor"); P.pg.wait_for_timeout(500)
    print("read-only badge shown :", P.pg.locator(".editor-title-row .oui-badge", has_text="Sola lettura").count() == 1)
    print("Save button present   :", P.pg.locator(".editor-save").count())
    P.pg.evaluate("() => { const v = %s; v.dispatch({changes: {from: v.state.doc.length, insert: ' '}}); }" % VIEW)
    P.pg.locator(".editor-save").first.click(); P.pg.wait_for_timeout(1500)
    print("mock log of writes    :", [l for l in mock.gcode() if "UPLOAD" in str(l)])
    b.close()
