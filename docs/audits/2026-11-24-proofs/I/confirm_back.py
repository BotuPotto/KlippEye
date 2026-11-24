import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof I-1: the phone's back button / Escape does not close a ConfirmDialog.
Run: cd tests/ui && python3 ../../.superpowers/audit/proofs/I/confirm_back.py /tmp/ke_build.html 8791
(run from tests/ui so that `lib` imports)."""
import sys, os
sys.path.insert(0, ROOT + "/tests/ui")
from playwright.sync_api import sync_playwright
from lib import Mock, Page
html, port = sys.argv[1], int(sys.argv[2])
mock = Mock(html, port)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        P = Page(b, mock, 390, 844); pg = P.pg
        pg.goto(mock.base + "/"); pg.wait_for_timeout(2300)
        pg.click('button[aria-label="Salva configurazione"]'); pg.wait_for_timeout(500)
        print("dialog open:", pg.locator(".confirm-card").count())
        r = pg.evaluate("() => window.klippeyeBack()"); pg.wait_for_timeout(500)
        print("klippeyeBack() returned:", r, "| dialog still open:", pg.locator(".confirm-card").count())
        pg.keyboard.press("Escape"); pg.wait_for_timeout(500)
        print("after real Escape key, dialog still open:", pg.locator(".confirm-card").count())
        print("page errors:", P.errors[:5])
finally:
    mock.stop()
