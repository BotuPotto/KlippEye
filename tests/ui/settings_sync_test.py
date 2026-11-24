"""1.145.0: two dashboards open at once do not undo each other's settings. A page saves only what it changed on top of the
Raspberry's copy, so a page that stayed open cannot put «Cancel by itself» back on or bring back an old printer name.
Against the mock.
Usage: settings_sync_test.py <html> <outdir> <port>"""
import json
import os
import sys
import urllib.request
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(out, exist_ok=True)
# a copy of the page that lets the test change settings like a tap would
probe = os.path.join(out, "probe.html")
src = open(html, encoding="utf-8").read()
marker = "const settingsStore = createSettingsStore();"
assert marker in src
open(probe, "w", encoding="utf-8").write(src.replace(marker, marker + " window.__ss = settingsStore;", 1))
mock = Mock(probe, port)
import atexit
atexit.register(mock.stop)
FAILS = []


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


def stored():
    raw = json.loads(urllib.request.urlopen(mock.base + "/server/database/item?namespace=klippeye&key=settings").read())
    return raw["result"]["value"]


def change(P, js):
    P.pg.evaluate("() => __ss.update((d) => { %s })" % js)
    P.pg.wait_for_timeout(2200)


with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    A = Page(b, mock, 390, 844)
    A.pg.goto(mock.base + "/")
    A.pg.wait_for_timeout(2300)
    change(A, "d.ai.autoCancel = true;")
    B = Page(b, mock, 1300, 800)  # opens after: it reads «Cancel by itself» on
    B.pg.goto(mock.base + "/")
    B.pg.wait_for_timeout(2300)
    ok("1.145.0: setup, the second page starts from the stored settings", stored().get("ai", {}).get("autoCancel") is True, stored().get("ai"))
    # the phone renames the printer and switches the automatic cancel off; the computer, never left, changes a material
    change(A, "d.printer.name = 'FROM-PHONE'; d.ai.autoCancel = false;")
    change(B, "d.materials[0].hotend = 215;")
    s = stored()
    ok("1.145.0: a page that stayed open keeps the other one's printer name", s["printer"]["name"] == "FROM-PHONE", s["printer"])
    ok("1.145.0: ... does not switch «Cancel by itself» back on", s["ai"]["autoCancel"] is False, s["ai"])
    ok("1.145.0: ... and its own change is saved", s["materials"][0]["hotend"] == 215, s["materials"][0])
    # the same page keeps the merged copy, so its next change does not undo anything either
    change(B, "d.ai.autoPause = true;")
    s = stored()
    ok("1.145.0: the next save of that page still keeps the phone's changes", s["printer"]["name"] == "FROM-PHONE" and s["ai"]["autoCancel"] is False and s["ai"]["autoPause"] is True, s["ai"])
    ok("1.145.0: no page errors", not A.errors and not B.errors, (A.errors, B.errors))
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
