import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof I-3: when both requests of the emergency stop fail (dead connection), nothing tells the person.
Run: cd tests/ui && python3 ../../.superpowers/audit/proofs/I/estop_silent.py /tmp/ke_build.html 8793"""
import sys
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
        seen = []
        def kill(route):
            seen.append(route.request.url); route.abort("connectionfailed")
        pg.route("**/printer/emergency_stop", kill)
        pg.route("**/printer/gcode/script", kill)
        pg.click('button[aria-label="Arresto di emergenza"]'); pg.wait_for_timeout(300)
        print("confirm dialog:", pg.locator(".confirm-card").count())
        if pg.locator(".confirm-card").count():
            pg.locator(".confirm-card .oui-btn--danger").click()
        pg.wait_for_timeout(2500)
        print("requests that failed:", seen)
        print("toasts shown:", pg.locator(".toast").all_inner_texts())
        print("banners:", pg.locator(".live-banner").count())
finally:
    mock.stop()
