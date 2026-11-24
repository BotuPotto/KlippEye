import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof K4: a confirmation dialog opened while idle sends its command even if a print started in the meantime
(a scheduled print, a print started from another browser). The Measure button is disabled during a print, but the dialog that
was already open is not checked again when «Measure» is pressed: G28 + SHAPER_CALIBRATE go to the printer mid-print.
Run: cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../docs/audits/2026-11-24-proofs/K/stale_lock.py ../../frontend/klippeye_frontend.html /tmp/k4 8794
"""
import sys, os
sys.path.insert(0, os.getcwd())
from playwright.sync_api import sync_playwright
from lib import *
html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
with sync_playwright() as p:
    b = p.chromium.launch(); mock.reset()
    P = Page(b, mock, 390, 844); P.goto("controllo", 2600)
    card = P.pg.locator(".shaper-card"); card.scroll_into_view_if_needed(); P.pg.wait_for_timeout(1500)
    card.locator('[data-shaper-measure="x"]').click()          # idle: the dialog opens
    P.pg.wait_for_selector(".confirm-card"); P.pg.wait_for_timeout(300)
    mock.set(printing=True)                                     # a print starts now (scheduled, or from another browser)
    P.pg.wait_for_timeout(6000)                                 # the page learns it: the Measure button is disabled
    print("Measure button disabled:", card.locator('[data-shaper-measure="x"]').is_disabled())
    P.pg.locator(".confirm-card").get_by_role("button", name="Misura", exact=True).click()
    P.pg.wait_for_timeout(1500)
    print("sent during the print  :", [g for g in mock.gcode() if "SHAPER" in str(g) or "G28" in str(g)])
    b.close()
