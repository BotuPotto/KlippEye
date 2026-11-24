import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Proof I-2: two open dashboards change two different settings; the second save wipes the first one.
First: copy /tmp/ke_build.html to /tmp/ke_probe.html adding "window.__ss = settingsStore;" after the createSettingsStore line. Run: cd tests/ui && python3 ../../.superpowers/audit/proofs/I/settings_race.py /tmp/ke_build.html 8792"""
import sys, json, urllib.request
sys.path.insert(0, ROOT + "/tests/ui")
from playwright.sync_api import sync_playwright
from lib import Mock, Page
html, port = sys.argv[1], int(sys.argv[2])
mock = Mock(html, port)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        A = Page(b, mock, 390, 844); B = Page(b, mock, 1300, 800)
        for P in (A, B):
            P.pg.goto(mock.base + "/"); P.pg.wait_for_timeout(2300)
        # phone (A) renames the printer; the computer (B) was open the whole time and never left the front
        A.pg.evaluate("() => __ss.update((d) => { d.printer.name = 'FROM-PHONE'; })"); A.pg.wait_for_timeout(2000)
        mid = json.loads(urllib.request.urlopen(mock.base + "/server/database/item?namespace=klippeye").read())["result"]["value"]["settings"]["printer"]["name"]
        print("after the phone's save, stored printer.name:", repr(mid))
        B.pg.evaluate("() => __ss.update((d) => { d.materials[0].hotend = 215; })"); B.pg.wait_for_timeout(2000)
        raw = json.loads(urllib.request.urlopen(mock.base + "/server/database/item?namespace=klippeye").read())
        s = raw["result"]["value"]["settings"]
        print("stored printer.name:", repr(s["printer"]["name"]), "(expected 'FROM-PHONE')")
        print("stored materials[0].hotend:", s["materials"][0]["hotend"])
finally:
    mock.stop()
