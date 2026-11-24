import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof J1: Start print, Pause and Cancel never look at Klipper's answer.
Klipper (through Moonraker) refuses each request with HTTP 400; the page still closes the dialog and, for Cancel, says
'CANCEL_PRINT sent'. Run: python3 p1_print_actions_ignore_answer.py   (needs /opt/pw-browsers and the mock server)"""
import os, sys, json, re
sys.path.insert(0, ROOT + "/tests/ui")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
from playwright.sync_api import sync_playwright
from lib import Mock, Page

html = ROOT + "/frontend/klippeye_frontend.html"
mock = Mock(html, 8931)
REFUSE = json.dumps({"error": {"code": 400, "message": "Klipper is not ready / already printing"}})
with sync_playwright() as p:
    b = p.chromium.launch()
    # 1. Start print, refused
    P = Page(b, mock, 390, 844, locale="en-US")
    pg = P.pg
    pg.route("**/printer/print/start", lambda r: r.fulfill(status=400, body=REFUSE, content_type="application/json"))
    P.goto("files", 2200)
    pg.locator(".file-card", has_text="Benchy").first.get_by_role("button", name="Start print").click()
    pg.wait_for_selector(".confirm-card")
    pg.locator(".confirm-card .oui-btn--primary").click()
    pg.wait_for_timeout(1200)
    body = pg.locator("body").inner_text()
    print("START refused with 400 -> dialog still open:", pg.locator(".confirm-card").count() > 0, "| any message with 'Klipper' or 'refus' or 'not ready' on the page:", bool(re.search(r"Klipper is not ready|refus|already printing", body)))
    P.close()
    # 2. Cancel print, refused
    mock.reset(); mock.set(printing=True)
    P = Page(b, mock, 390, 844, locale="en-US")
    pg = P.pg
    pg.route("**/printer/gcode/script", lambda r: r.fulfill(status=400, body=REFUSE, content_type="application/json"))
    P.goto("home", 2200)
    pg.get_by_role("button", name="Cancel print").first.click()
    pg.wait_for_timeout(600)
    pg.locator(".confirm-card").get_by_role("button", name="Cancel print").click()
    pg.wait_for_timeout(900)
    print("CANCEL refused with 400 -> page text contains:", [t for t in pg.locator("body").inner_text().split("\n") if "CANCEL_PRINT" in t])
    P.close()
mock.stop()
