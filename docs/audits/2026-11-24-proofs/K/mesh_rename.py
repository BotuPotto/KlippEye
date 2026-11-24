import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof K3: renaming a bed-mesh profile that is NOT the one in use changes the mesh in use.
The rename is LOAD old / SAVE new / REMOVE old. Klipper's LOAD makes `old` the active mesh and SAVE makes `new` the active
profile, so afterwards the printer uses the renamed profile's heights, not the one it used before.
Run: cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../docs/audits/2026-11-24-proofs/K/mesh_rename.py ../../frontend/klippeye_frontend.html /tmp/k3 8793
"""
import sys, os
sys.path.insert(0, os.getcwd())
from playwright.sync_api import sync_playwright
from lib import *
html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
with sync_playwright() as p:
    b = p.chromium.launch(); mock.reset(); mock.set(mesh=True)
    P = Page(b, mock, 390, 844); P.goto("controllo", 2200)
    c = P.pg.locator(".mesh-card")
    c.scroll_into_view_if_needed(); P.pg.wait_for_timeout(500)
    print("in use before the rename:", c.locator("[data-active-profile]").get_attribute("data-active-profile"))
    c.locator('[data-profile="adaptive"] button[aria-label="Rinomina adaptive"]').click()
    P.pg.wait_for_selector(".confirm-card .mesh-name__input")
    P.pg.locator(".confirm-card .mesh-name__input").fill("fine_bed")
    P.pg.locator(".confirm-card").get_by_role("button", name="Rinomina", exact=True).click()
    P.pg.wait_for_timeout(5000)
    print("gcode sent               :", [g for g in mock.gcode() if "BED_MESH" in str(g)])
    print("in use after the rename  :", c.locator("[data-active-profile]").get_attribute("data-active-profile"))
    b.close()
