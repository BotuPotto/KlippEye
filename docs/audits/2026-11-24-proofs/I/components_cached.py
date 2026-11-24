import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof I-4: Moonraker's component list (/server/info) is asked once per page load and never again,
also after Moonraker restarted with a new component (the dashboard's own timelapse set-up does exactly that).
Run: cd tests/ui && python3 ../../.superpowers/audit/proofs/I/components_cached.py /tmp/ke_build.html 8794"""
import sys, json
sys.path.insert(0, ROOT + "/tests/ui")
from playwright.sync_api import sync_playwright
from lib import Mock, Page
html, port = sys.argv[1], int(sys.argv[2])
mock = Mock(html, port)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        P = Page(b, mock, 390, 844); pg = P.pg
        comps = {"v": ["job_queue"]}
        hits = []
        def info(route):
            hits.append(list(comps["v"]))
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"result": {"components": comps["v"], "klippy_state": "ready", "klippy_connected": True}}))
        pg.route("**/server/info", info)
        pg.goto(mock.base + "/"); pg.wait_for_timeout(3000)
        n1 = len(hits)
        comps["v"] = ["job_queue", "timelapse", "spoolman"]   # Moonraker restarted with two more components
        pg.wait_for_timeout(1000)
        pg.evaluate("() => window.dispatchEvent(new Event('online'))")  # a wake-up / reconnect
        pg.wait_for_timeout(6000)
        print("requests to /server/info and what they returned:", hits, "(%d before, %d after the restart)" % (n1, len(hits) - n1))
finally:
    mock.stop()
