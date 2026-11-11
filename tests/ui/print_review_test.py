"""Release 1.103: «How did the print go?» on the home page when a print has ended (phone and computer): went fine, or a problem
with its kinds and the picture it shows from; Skip; Don't ask again (the setting print_review); nothing during a print; at
320 px nothing out of the card. Against the mock.
Usage: print_review_test.py <html> <outdir> <port>"""
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


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def review(rid="20261111-150000-Benchy", thumbs=12):
    started = 1793000000.0
    return {"id": rid, "file": "Benchy_PLA_45m.gcode", "started": started, "ended": started + 2700, "end_state": "complete",
            "thumbs": [{"n": i + 1, "t": started + i * 225, "progress": i * 8.5, "layer": i * 12} for i in range(thumbs)], "answer": None}


def wait(pg, fn, timeout=8000):
    end = pg.evaluate("Date.now()") + timeout
    while pg.evaluate("Date.now()") < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        pg.wait_for_timeout(150)
    return False


with sync_playwright() as p:
    b = p.chromium.launch()

    # --- nothing waiting: no card
    P = Page(b, mock, 390, 844, locale="it-IT")
    P.goto("home", 2400)
    ok("no print to judge: no card", P.pg.locator(".print-review").count() == 0)
    P.close()

    # --- went fine
    mock.set(review=review())
    P = Page(b, mock, 390, 844, locale="it-IT")
    P.goto("home", 2400)
    card = P.pg.locator(".print-review")
    ok("a print just ended: the card asks how it went, with the file and a picture", card.count() == 1 and "Com'è andata la stampa?" in card.inner_text()
       and "Benchy_PLA_45m.gcode" in card.inner_text() and card.locator("img.print-review__thumb").count() == 1, card.inner_text()[:300] if card.count() else "")
    ok("... it is the first card of the page", P.pg.evaluate("() => { const c = document.querySelector('.print-review'); const cam = document.querySelector('[data-card=camera], .camera-card, .oui-card'); return c && c.getBoundingClientRect().top <= cam.getBoundingClientRect().top + 1; }"))
    P.shot(os.path.join(out, "review_ask_390.png"), tall=False)
    card.locator('[data-review="ok"]').click()
    ok("«Went fine»: saved, with the alarms it judged", wait(P.pg, lambda: state()["review_answers"] and "Grazie" in card.inner_text()), card.inner_text() if card.count() else "")
    a = state()["review_answers"][-1]
    ok("... sent: ok, no problems", a["outcome"] == "ok" and a["problems"] == [] and a["id"] == review()["id"], a)
    ok("... then the card goes away", wait(P.pg, lambda: P.pg.locator(".print-review").count() == 0, 7000))
    P.close()

    # --- a problem, its kinds and from when
    mock.set(review=review(), review_answers=[])
    P = Page(b, mock, 390, 844, locale="it-IT")
    P.goto("home", 2400)
    card = P.pg.locator(".print-review")
    card.locator('[data-review="failed"]').click()
    P.settle(200)
    save = card.locator("[data-review-save]")
    ok("«There was a problem»: the kinds to choose, Save off until one is chosen", card.locator("[data-review-problem]").count() == 15 and card.locator(".print-review__group").count() == 2 and save.is_disabled())
    card.locator('[data-review-problem="spaghetti"]').click()
    card.locator('[data-review-problem="detached"]').click()
    slider = card.locator("[data-review-when]")
    slider.evaluate("(el) => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(el, '5'); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }")
    P.settle(200)
    ok("... the slider shows the moment of that picture (progress, layer)", "43%" in card.inner_text() and "60" in card.inner_text(), card.inner_text())
    P.shot(os.path.join(out, "review_problem_390.png"), tall=False)
    save.click()
    ok("... saved: failed, the two kinds, from that picture's time", wait(P.pg, lambda: state()["review_answers"]), state()["review_answers"])
    a = state()["review_answers"][-1]
    ok("... the answer sent", a["outcome"] == "failed" and sorted(a["problems"]) == ["detached", "spaghetti"] and a["failed_at"] == review()["thumbs"][5]["t"], a)
    P.close()

    # --- skip, don't ask again
    mock.set(review=review(), review_answers=[])
    P = Page(b, mock, 390, 844, locale="it-IT")
    P.goto("home", 2400)
    P.pg.locator('.print-review [data-review="skipped"]').click()
    ok("Skip: sent as skipped, the card goes", wait(P.pg, lambda: state()["review_answers"] and P.pg.locator(".print-review").count() == 0) and state()["review_answers"][-1]["outcome"] == "skipped")
    P.close()
    mock.set(review=review(), review_answers=[])
    P = Page(b, mock, 390, 844, locale="it-IT")
    P.goto("home", 2400)
    P.pg.locator(".print-review [data-review-never]").click()
    ok("Don't ask again: the setting print_review off, the card goes", wait(P.pg, lambda: any(c.get("print_review") is False for c in state()["brain_cfg_log"]) and P.pg.locator(".print-review").count() == 0), state()["brain_cfg_log"][-3:])
    P.close()

    # --- not while printing
    mock.set(review=review(), printing=True)
    P = Page(b, mock, 390, 844, locale="it-IT")
    P.goto("home", 2400)
    ok("during a print: no question", P.pg.locator(".print-review").count() == 0)
    P.close()
    mock.set(printing=False)

    # --- 320 px, a long language; the computer
    for locale, w, h in (("de-DE", 320, 700), ("ru-RU", 320, 700), ("it-IT", 1280, 900)):
        mock.set(review=review(), review_answers=[])
        P = Page(b, mock, w, h, locale=locale)
        P.goto("home", 2400)
        card = P.pg.locator(".print-review")
        if card.count():
            card.locator('[data-review="failed"]').click()
            P.settle(200)
        wide = P.pg.evaluate("() => [...document.querySelectorAll('.print-review *')].filter(e => { const r = e.getBoundingClientRect(), c = document.querySelector('.print-review').getBoundingClientRect(); return r.width && (r.right > c.right + 1 || r.left < c.left - 1); }).map(e => e.className).slice(0, 5)")
        ok("%s %d px: the card is there and nothing goes out of it" % (locale, w), card.count() == 1 and not wide, wide)
        P.shot(os.path.join(out, "review_%s_%d.png" % (locale, w)), tall=False)
        P.close()
    b.close()

print("%d FAIL" % len(FAILS))
sys.exit(1 if FAILS else 0)
