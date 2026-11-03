"""Release 1.38.0 (roadmap 6b part 9): Settings → Notifications sets the texts of the notifications (placeholders), the
pause's delay and notifications of your own (started, progress, time left, layer, console line, temperature), saved in the
shared settings the notification service reads. Against the mock.
Usage: notify_test.py <html> <outdir> <port>"""
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
CUR = [None]


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


def stored():
    db = json.loads(urllib.request.urlopen(mock.base + "/__mock/db").read())["db"]
    return (db.get("klippeye/settings") or {}).get("notify") or {}


def wait_until(fn, timeout=6.0, step=0.15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    return bool(fn())


with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("home", 2200)
    pg = P.pg
    pg.click('button[aria-label="Impostazioni"]')
    pg.wait_for_selector(".drawer")
    P.settle(450)
    pg.locator('.set-entry[data-page="notifications"]').click()
    P.settle(800)

    row = pg.locator('[data-notify-kind="complete"]')
    ok("each notification has 'Cambia il testo'", pg.locator(".notify-kind__edit").count() == 7)
    row.locator(".notify-kind__edit").click()
    field = row.locator("textarea")
    ok("... the usual text shown in grey (in the language of the notifications)", field.get_attribute("placeholder") == "Stampa completata!", field.get_attribute("placeholder"))
    field.fill("{file} pronto in {elapsed}!")
    field.blur()
    ok("a text of yours is saved for the service", wait_until(lambda: stored().get("texts", {}).get("complete") == "{file} pronto in {elapsed}!"), stored())
    ok("... and shown under the switch", "{file} pronto in {elapsed}!" in row.locator(".set-switch").inner_text())
    field.fill("")
    field.blur()
    ok("emptied: the usual text again", wait_until(lambda: "complete" not in stored().get("texts", {})), stored())

    paused = pg.locator('[data-notify-kind="paused"]')
    paused.locator(".notify-kind__edit").click()
    paused.get_by_role("button", name="Subito").click()
    ok("the pause: announced at once", wait_until(lambda: stored().get("pauseDelay") == 0), stored())
    err = pg.locator('[data-notify-kind="error"]')
    err.locator(".notify-kind__edit").click()
    ok("the error explains {message}", "{message}" in err.inner_text())

    # your own
    pg.locator('[data-add-rule="progress"]').scroll_into_view_if_needed()
    pg.locator('[data-add-rule="progress"]').click()
    ok("'Avanzamento raggiunto' added at 50 %", wait_until(lambda: len(stored().get("rules", [])) == 1 and stored()["rules"][0]["kind"] == "progress" and stored()["rules"][0]["value"] == 50), stored())
    rule = pg.locator('[data-rule-kind="progress"]')
    num = rule.locator("input.set-field__input").first
    num.fill("75")
    num.press("Enter")
    ok("... changed to 75 %", wait_until(lambda: stored()["rules"][0]["value"] == 75), stored()["rules"])
    num.fill("150")
    num.press("Enter")
    P.settle(500)
    ok("150 % is refused", stored()["rules"][0]["value"] == 75)
    ok("its text: the service's default shown in grey", rule.locator("textarea").get_attribute("placeholder") == "{file}: {progress}% completato")
    rule.locator(".set-switch", has_text="Importante").click()
    ok("'Importante': an alarm", wait_until(lambda: stored()["rules"][0]["high"] is True))
    pg.locator('[data-add-rule="line"]').click()
    line = pg.locator('[data-rule-kind="line"]')
    ok("a console line with no words yet says it never goes out", wait_until(lambda: line.count() == 1) and "non parte mai" in line.inner_text())
    lf = line.locator("input.set-field__input").first
    lf.fill("CAMBIO COLORE")
    lf.press("Enter")
    ok("... the words saved", wait_until(lambda: stored()["rules"][1] == {"id": stored()["rules"][1]["id"], "kind": "line", "value": "CAMBIO COLORE", "text": "", "on": True, "high": False}), stored()["rules"])
    pg.locator('[data-add-rule="temp"]').click()
    temp = pg.locator('[data-rule-kind="temp"]')
    temp.get_by_role("button", name="Ugello").click()
    ok("a temperature: the nozzle", wait_until(lambda: stored()["rules"][2]["value"] == "extruder"), stored()["rules"])
    pg.screenshot(path=out + "/rules.png", full_page=True)
    temp.locator('button[aria-label^="Togli"]').click()
    ok("removing one", wait_until(lambda: [r["kind"] for r in stored()["rules"]] == ["progress", "line"]))
    ok("the placeholders are listed", "{remaining}" in pg.locator(".notify-placeholders").inner_text())
    ok("no horizontal overflow in the menu", pg.evaluate("() => { const b = document.querySelector('.drawer__body'); return b.scrollWidth <= b.clientWidth; }"))
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
