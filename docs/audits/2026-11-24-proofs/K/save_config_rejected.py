import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof K9: «Save and restart» with changes waiting for SAVE_CONFIG sends SAVE_CONFIG with sendGcode(), which resolves also
when Klipper answers 400 (fetch only throws on a network failure). The editor then says «Klipper restarts ✓» and closes:
nothing restarted and the new printer.cfg is not running. (The other branch, firmwareRestart, does check response.ok.)
Run: cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../docs/audits/2026-11-24-proofs/K/save_config_rejected.py ../../frontend/klippeye_frontend.html /tmp/k9 8801
"""
import sys, os, re, json
sys.path.insert(0, os.getcwd())
from playwright.sync_api import sync_playwright
from lib import *
html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
with sync_playwright() as p:
    b = p.chromium.launch(); mock.reset(); mock.set(pending={"probe": {"z_offset": 1.2}})
    P = Page(b, mock, 390, 844); P.goto("config", 1800)
    P.pg.route(re.compile(r".*/printer/gcode/script"), lambda r: r.fulfill(status=400, content_type="application/json", body=json.dumps({"error": {"code": 400, "message": "Unable to parse config: option 'x' is not valid in section 'stepper_x'"}})))
    P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^printer.cfg$"))).first.locator(".cfg-row__main").click()
    P.pg.wait_for_selector(".screen--editor .cm-editor"); P.pg.wait_for_timeout(500)
    P.pg.evaluate("() => { const v = CM.EditorView.findFromDOM(document.querySelector('.screen--editor .cm-editor')); v.dispatch({changes: {from: 0, insert: '# x\\n'}}); }")
    P.pg.locator('.editor-save[data-restarts="klipper"]').click()
    seen = []
    for _ in range(14):
        P.pg.wait_for_timeout(250)
        if P.pg.locator(".editor-status").count(): seen.append(P.pg.locator(".editor-status").inner_text())
    print("statuses shown:", sorted(set(seen) - {""}))
    print("editor still open:", P.pg.locator(".screen--editor").count())
    b.close()
