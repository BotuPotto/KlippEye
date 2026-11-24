import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
import sys; sys.path.insert(0,ROOT + "/tests/ui")
from playwright.sync_api import sync_playwright
from lib import Mock, Page
m=Mock(ROOT + "/frontend/klippeye_frontend.html",9933)
with sync_playwright() as pw:
    b=pw.chromium.launch()
    for w,h in ((360,780),(1280,800)):
        m.reset(); P=Page(b,m,w,h); P.goto("home",2200); m.set(moonraker_down=True); P.pg.wait_for_timeout(12000)
        P.pg.screenshot(path="shots/%d-state-piDown-12s.png"%w, full_page=False); P.close()
    b.close()
m.stop()
