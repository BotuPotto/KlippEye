import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof K6: «Save and restart» on a Klipper file asks for confirmation only when it can read the print state. When that read
fails (Moonraker slow, Wi-Fi hiccup: `.catch(() => ({}))`), the state is unknown, no question is asked and FIRMWARE_RESTART
is sent in the middle of a print.
Run: cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../docs/audits/2026-11-24-proofs/K/restart_fail_open.py ../../frontend/klippeye_frontend.html /tmp/k6 8796
"""
import sys, os, re
sys.path.insert(0, os.getcwd())
from playwright.sync_api import sync_playwright
from lib import *
html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
def run(fail_read):
    with sync_playwright() as p:
        b = p.chromium.launch(); mock.reset(); mock.set(printing=True)
        P = Page(b, mock, 390, 844); P.goto("config", 1800)
        P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^printer.cfg$"))).first.locator(".cfg-row__main").click()
        P.pg.wait_for_selector(".screen--editor .cm-editor"); P.pg.wait_for_timeout(500)
        P.pg.evaluate("() => { const v = CM.EditorView.findFromDOM(document.querySelector('.screen--editor .cm-editor')); v.dispatch({changes: {from: 0, insert: '# x\\n'}}); }")
        if fail_read:   # the read of print_stats is cut (a slow answer, a Wi-Fi drop)
            P.pg.route(re.compile(r".*/printer/objects/query\?print_stats.*"), lambda r: r.abort())
        restarts = []
        P.pg.on("request", lambda r: restarts.append(r.url) if "firmware_restart" in r.url or r.url.endswith("/printer/restart") else None)
        P.pg.locator('.editor-save[data-restarts="klipper"]').click(); P.pg.wait_for_timeout(2500)
        print("state read fails =", fail_read, "| confirm dialogs shown:", P.dialogs, "| restart requests:", restarts)
        b.close()
run(False); run(True)
