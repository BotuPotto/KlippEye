"""Release 1.94: Settings › Access › Address: KlippEye at the Raspberry's own address (no port), the previous page at
another port, given back; without the administrator's rights the command to run; HTTPS then at the address without a
port. (scripts/web_front.py itself, on an nginx configuration, is tested by the backend tests.)
Usage: web_address_test.py <html> <outdir> <port>"""
import json
import os
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit
atexit.register(mock.stop)
FAILS = []


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


CUR = [None]


def wait_until(fn, timeout=6.0, step=0.15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    return False


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def open_access(b, w=390, hh=844, **st):
    mock.reset()
    if st:
        mock.set(**st)
    P = Page(b, mock, w, hh)
    CUR[0] = P
    P.goto("home", 1800)
    P.pg.click('.app-header button[aria-label="Impostazioni"]')
    P.pg.wait_for_timeout(400)
    P.pg.click('.set-entry[data-page="access"]')
    P.pg.wait_for_timeout(600)
    return P


with sync_playwright() as p:
    b = p.chromium.launch()
    for w, hh in ((390, 844), (1440, 900)):
        P = open_access(b, w, hh)
        pg = P.pg
        ok("%d: the Address group: KlippEye at port 8085 for now" % w, wait_until(lambda: pg.locator('[data-web-status="port"]').count() == 1 and "127.0.0.1:8085" in pg.locator('[data-web-status]').inner_text()), pg.locator(".set-group").all_inner_texts()[:6])
        pg.locator("[data-web-main]").click()
        ok("%d: «Open KlippEye at http://…»: done, the previous page at its new port" % w, wait_until(lambda: pg.locator('[data-web-status="main"]').count() == 1 and "http://127.0.0.1:82" in pg.locator('[data-web-moved="webui"]').inner_text() and state()["web_log"] == [True]))
        ok("%d: HTTPS then at the address without a port (no port field)" % w, wait_until(lambda: "All'indirizzo del Raspberry" in pg.locator(".set-switch", has_text="Ingresso cifrato").inner_text()) or pg.locator("[data-https-port]").count() == 0)
        if w == 390:
            pg.locator('[data-web-status]').scroll_into_view_if_needed()
            pg.screenshot(path=out + "/web_main.png")
            pg.locator("[data-web-restore]").click()
            ok("«Give the address back»: KlippEye at port 8085 again", wait_until(lambda: pg.locator('[data-web-status="port"]').count() == 1 and state()["web_log"] == [True, False]))
        ok("%d: no horizontal overflow, no page errors" % w, pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth") and not [e for e in P.errors if "pageerror" in e or "console.error" in e])
        P.close()

    # without the administrator's rights (sudo asks a password): the command to run
    P = open_access(b, web_sudo=False)
    pg = P.pg
    wait_until(lambda: pg.locator("[data-web-main]").count() == 1)
    pg.locator("[data-web-main]").click()
    ok("no rights: said, with the command to run on the Raspberry", wait_until(lambda: pg.locator("[data-web-command]").inner_text() == "klippeye web main" and "permessi di amministratore" in pg.locator(".set-status--warn[role=alert]").last.inner_text()))
    P.close()

    # a Raspberry without nginx: no Address group
    P = open_access(b, web={"nginx": False, "main": False, "https": False, "moved": [], "sites": {}})
    ok("without nginx: no Address group", P.pg.locator("[data-web-status]").count() == 0 and P.pg.locator(".set-group").count() > 0)
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
