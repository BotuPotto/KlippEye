"""Release 1.104: the AI monitor's backup services and the guides to a free key (app/59l-ai-services.js). Settings → AI
monitor → The AI service: add a backup (the first service with a key not used yet), change its model, the second opinion
switch, remove it; a backup without a key says so; at most three; «How to get a free key» under a service; 320 px. Against
the mock backend, which applies the same rules as backend/ai_services.py.
Usage: ai_backups_test.py <html> <outdir> <port>"""
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
GROQ = "gsk_" + "x" * 40 + "AB12"
GEMINI = "AIzaSy" + "g" * 33


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:700]) if (extra != "" and not cond) else ""), flush=True)


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def wait(P, fn, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        P.pg.wait_for_timeout(120)
    return False


def open_ai_page(b, w=390, h=844, locale="it-IT", **st):
    mock.reset()
    mock.set(**st)
    P = Page(b, mock, w, h, locale=locale)
    P.goto("home", 1400)
    P.pg.locator(".header-btn--menu").click()
    P.pg.wait_for_selector(".drawer")
    P.settle(450)
    P.pg.click('.set-entry[data-page="ai"]')
    P.settle(900)
    return P


with sync_playwright() as p:
    b = p.chromium.launch()
    two_keys = {"keys": {"groq": GROQ, "gemini": GEMINI}, "monitor": {"provider": "groq", "model": ""}}

    P = open_ai_page(b, ai_cfg=two_keys)
    box = P.pg.locator("[data-ai-backups]")
    ok("the backups section: none yet, «Add a backup service», no second-opinion switch yet",
       box.count() == 1 and box.get_attribute("data-ai-backups") == "0" and P.pg.locator("[data-ai-backup-add]").count() == 1 and "Secondo parere" not in box.inner_text(), box.inner_text() if box.count() else "")
    P.pg.click("[data-ai-backup-add]")
    ok("added: the first service with a key not used yet (Gemini), its default model",
       wait(P, lambda: box.get_attribute("data-ai-backups") == "1") and state()["ai_posts"][-1] == {"monitor_backups": [{"provider": "gemini", "model": ""}]}, state()["ai_posts"][-1:])
    ok("... its models read from the service, the second opinion switch appears (on)",
       wait(P, lambda: P.pg.locator('[data-ai-backup-model="0"] option').count() >= 3) and "Secondo parere" in box.inner_text()
       and box.locator(".set-switch input, [role=switch]").first.is_checked(), box.inner_text())
    P.pg.select_option('[data-ai-backup-model="0"]', "gemini-3.8-flash-lite")
    ok("a model chosen for the backup: saved", wait(P, lambda: state()["ai_posts"][-1] == {"monitor_backups": [{"provider": "gemini", "model": "gemini-3.8-flash-lite"}]}), state()["ai_posts"][-1:])
    box.locator(".set-switch").first.click()
    ok("second opinion switched off: saved", wait(P, lambda: state()["ai_posts"][-1] == {"second_opinion": False}), state()["ai_posts"][-1:])
    P.pg.select_option('[data-ai-backup-service="0"]', "mistral")
    ok("a backup without a key: it says so, no model list",
       wait(P, lambda: "Nessuna chiave salvata per Mistral" in box.inner_text()) and P.pg.locator('[data-ai-backup-model="0"]').count() == 0, box.inner_text())
    P.pg.click("[data-ai-backup-add]")
    wait(P, lambda: box.get_attribute("data-ai-backups") == "2")
    P.pg.click("[data-ai-backup-add]")
    ok("three at most: the add button goes", wait(P, lambda: box.get_attribute("data-ai-backups") == "3") and P.pg.locator("[data-ai-backup-add]").count() == 0)
    P.shot(os.path.join(out, "backups_390.png"))
    P.pg.click('[data-ai-backup-remove="0"]')
    ok("removed: the others stay, in order", wait(P, lambda: box.get_attribute("data-ai-backups") == "2") and [x["provider"] for x in state()["ai_posts"][-1]["monitor_backups"]][:1] != ["mistral"], state()["ai_posts"][-1:])
    P.close()

    # --- the guides
    P = open_ai_page(b, ai_cfg={"keys": {}})
    guide = P.pg.locator('[data-ai-guide="gemini"]')
    ok("«How to get a free key» under Gemini, Groq, OpenRouter, Mistral (not under the paid ones)",
       guide.count() == 1 and P.pg.locator("[data-ai-guide]").count() == 4 and P.pg.locator('[data-ai-guide="openai"]').count() == 0)
    guide.locator("summary").click()
    P.settle(200)
    ok("... opened: the steps and what the free plan means", "aistudio.google.com/apikey" in guide.inner_text() and "Create API key" in guide.inner_text() and "migliorare" in guide.inner_text(), guide.inner_text())
    P.close()

    # --- 320 px, long languages
    for locale in ("de-DE", "ru-RU"):
        P = open_ai_page(b, 320, 700, locale=locale, ai_cfg=dict(two_keys, monitor_backups=[{"provider": "gemini", "model": ""}, {"provider": "mistral", "model": ""}]))
        P.pg.locator(".ai-keys > summary").click()
        P.settle(200)
        P.pg.locator('[data-ai-guide="groq"] summary').click()
        P.settle(300)
        wide = P.pg.evaluate("() => { const d = document.querySelector('.drawer__body'); return d.scrollWidth - d.clientWidth; }")
        out_of = P.pg.evaluate("() => [...document.querySelectorAll('.ai-backup, .ai-backup *, .ai-guide *')].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.right > window.innerWidth + 1; }).map(e => e.className).slice(0, 4)")
        ok("%s 320 px: the backups and the guide inside the page" % locale, wide <= 0 and not out_of and P.pg.locator(".ai-backup").count() == 2, (wide, out_of))
        P.shot(os.path.join(out, "backups_%s_320.png" % locale))
        P.close()
    b.close()

print("%d FAIL" % len(FAILS))
sys.exit(1 if FAILS else 0)
