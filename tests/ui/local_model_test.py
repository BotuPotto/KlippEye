"""Release 1.106: the local model on Settings → AI monitor: none installed (it says the monitor works without, no switches),
KlippEye's model in use (version, last look, what it did, its switches, the way to its thresholds); its thresholds in their
own group on Monitor thresholds; 320 px. Against the mock.
Usage: local_model_test.py <html> <outdir> <port>"""
import json
import os
import sys
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


def open_page(b, page, w=390, h=844, **st):
    mock.reset()
    mock.set(**st)
    P = Page(b, mock, w, h)
    P.goto("home", 1400)
    P.pg.locator(".header-btn--menu").click()
    P.pg.wait_for_selector(".drawer")
    P.settle(450)
    P.pg.click('.set-entry[data-page="%s"]' % page)
    P.settle(1200)
    return P


with sync_playwright() as p:
    b = p.chromium.launch()
    P = open_page(b, "ai")
    box = P.pg.locator("[data-local-model]")
    ok("no model installed: it says so, the monitor works without; no switches", box.count() == 1 and box.get_attribute("data-local-model") == "none"
       and "Nessun modello locale" in box.inner_text() and P.pg.locator('.set-switch:has-text("Usa il modello locale")').count() == 0, box.inner_text() if box.count() else "")
    P.close()

    model = {"available": True, "source": "base", "version": "20261120-1015", "threshold": 0.62, "size": 224,
             "last": {"score": 87.4, "checks": 120, "filtered": 9, "asked": 3}}
    P = open_page(b, "ai", local_model=model)
    box = P.pg.locator("[data-local-model]")
    page = P.pg.locator(".drawer__body").inner_text()
    ok("KlippEye's model in use: its version and last look", box.get_attribute("data-local-model") == "base" and "il modello di KlippEye" in box.inner_text()
       and "20261120-1015" in box.inner_text() and "87%" in box.inner_text(), box.inner_text())
    ok("... what it did, its three switches, the way to its thresholds", "allarmi tenuti lontano dall'IA online: 9" in page and "Usa il modello locale" in page
       and "Ferma col solo modello locale" in page and P.pg.locator('[data-go="detector"]').count() >= 1, page[-900:])
    P.shot(os.path.join(out, "local_model_ai.png"))
    P.pg.locator('[data-go="detector"]').last.click()
    P.settle(1000)
    page = P.pg.locator(".drawer__body").inner_text()
    ok("Monitor thresholds: the group «Local model» with its three thresholds (the switches are not repeated)",
       "MODELLO LOCALE" in page.upper() and "In dubbio da" in page and "Sicuro da" in page and "Ogni quanto guarda da solo" in page and "Usa il modello locale" not in page, page[-1200:])
    P.close()

    P = open_page(b, "ai", 320, 700, local_model=model)
    wide = P.pg.evaluate("() => { const d = document.querySelector('.drawer__body'); return d.scrollWidth - d.clientWidth; }")
    ok("320 px: nothing sideways", wide <= 0, wide)
    P.close()
    b.close()

print("%d FAIL" % len(FAILS))
sys.exit(1 if FAILS else 0)
