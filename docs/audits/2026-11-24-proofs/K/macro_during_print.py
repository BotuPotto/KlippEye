import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof K5: with the default macro card («simple» mode) every macro is a one-tap button that runs at once, also during a
print (no lock, no confirmation).
Run: cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../docs/audits/2026-11-24-proofs/K/macro_during_print.py ../../frontend/klippeye_frontend.html /tmp/k5 8795
"""
import sys, os
sys.path.insert(0, os.getcwd())
from playwright.sync_api import sync_playwright
from lib import *
html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
with sync_playwright() as p:
    b = p.chromium.launch(); mock.reset(); mock.set(printing=True)
    P = Page(b, mock, 390, 844); P.goto("controllo", 2600)
    card = P.pg.locator('[data-macro-card="all"]'); card.scroll_into_view_if_needed(); P.pg.wait_for_timeout(800)
    names = card.locator(".macro-run, .macro-split-run").all_inner_texts()
    print("macro buttons while printing:", names[:8])
    before = len(mock.gcode())
    card.locator(".macro-run, .macro-split-run").first.click(); P.pg.wait_for_timeout(800)
    print("gcode sent by one tap       :", mock.gcode()[before:])
    b.close()
