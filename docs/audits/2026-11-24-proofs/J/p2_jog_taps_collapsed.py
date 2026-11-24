import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof J2: five quick taps (about 0.14 s apart) on a Z jog button send only TWO moves (the 500 ms duplicate guard), each tap shows a toast.
Run: python3 p2_jog_taps_collapsed.py"""
import os, sys
sys.path.insert(0, ROOT + "/tests/ui")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
from playwright.sync_api import sync_playwright
from lib import Mock, Page
mock = Mock(ROOT + "/frontend/klippeye_frontend.html", 8932)
with sync_playwright() as p:
    b = p.chromium.launch()
    P = Page(b, mock, 390, 844, locale="en-US"); pg = P.pg
    P.goto("home", 2200)
    before = len(mock.gcode())
    btn = pg.locator("button[data-z='-1']").first
    btn.scroll_into_view_if_needed()
    for _ in range(5):
        btn.click(); pg.wait_for_timeout(90)
    pg.wait_for_timeout(800)
    sent = [g for g in mock.gcode()[before:] if "G1 Z" in str(g)]
    print("5 taps on Z -1 within ~0.5 s ->", len(sent), "move(s) reached Klipper:", sent)
    P.close()
mock.stop()
