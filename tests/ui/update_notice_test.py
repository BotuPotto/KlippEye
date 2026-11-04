"""1.67: the dashboard looks for new versions by itself (app/56a-update-notice.js): once a day Moonraker is asked to
look (never while printing); a number on «Sistema» and a message say when there are some (the OS packages left out);
Settings → Software switches it off.
Usage: update_notice_test.py <html> <outdir> <port>"""
import sys, os, json, time, urllib.request
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
FAILS = []
CUR = [None]


def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""))


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def wait_until(fn, timeout=8.0, step=0.15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn(): return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    try: return bool(fn())
    except Exception: return False


def start(b, w=390, h=844, auto=True, **st):
    mock.reset()
    if st: mock.set(**st)
    P = Page(b, mock, w, h, auto_updates=auto)
    CUR[0] = P
    P.goto("home", 2500)
    return P


badge = lambda P: P.pg.locator("[data-update-badge]")

with sync_playwright() as p:
    b = p.chromium.launch()

    P = start(b)
    ok("a phone: a number on the «Sistema» tab (Klipper has a new version; the OS packages do not count)", wait_until(lambda: badge(P).count() == 1) and badge(P).get_attribute("data-update-badge") == "1" and P.pg.locator('.bottom-nav__tab[data-tab="sistema"] [data-update-badge]').count() == 1)
    ok("... and a message names it, once", wait_until(lambda: "Nuove versioni: Klipper" in P.pg.locator(".toast--notice").inner_text()), P.pg.locator(".toast--notice").inner_text() if P.pg.locator(".toast--notice").count() else "")
    ok("... Moonraker was asked to look for new versions (the first time on this device)", wait_until(lambda: state().get("update_refreshes", 0) == 1, 25), state().get("update_refreshes"))
    P.shot_vp(out + "/phone.png")
    P.goto("home", 2500)
    ok("a new visit the same day: not asked again, no message again, the number stays", wait_until(lambda: badge(P).count() == 1) and state().get("update_refreshes", 0) == 1 and P.pg.locator(".toast--notice.is-visible").count() == 0)
    # off in Settings → Aggiornamenti
    P.pg.click('button[aria-label="Impostazioni"]'); P.pg.wait_for_selector(".drawer"); P.settle(450)
    P.pg.click('.set-entry[data-page="software"]'); P.settle(800)
    row = P.pg.locator('[data-setting="auto-update-check"] [role="switch"]')
    ok("Settings → Aggiornamenti: «Cerca da solo le nuove versioni», on", wait_until(lambda: row.count() == 1) and row.get_attribute("aria-checked") == "true")
    row.click(); P.settle(400)
    ok("... switched off: the number goes away", row.get_attribute("aria-checked") == "false" and badge(P).count() == 0)
    P.goto("home", 2500)
    ok("... and stays off at the next visit", badge(P).count() == 0 and P.pg.evaluate("() => localStorage.getItem('klippeye.updates.auto')") == "0")
    P.close()

    # while printing: read, but Moonraker is not asked to look
    P = start(b, printing=True)
    ok("while printing: the number is there, but Moonraker is not asked to look (it refuses during a print)", wait_until(lambda: badge(P).count() == 1) and (P.settle(1500) or True) and state().get("update_refreshes", 0) == 0)
    P.close()

    # the computer: the number on the tab at the top; the switch in Settings → Software
    P = start(b, w=1440, h=900)
    ok("a computer: the number on the «Sistema» tab at the top", wait_until(lambda: P.pg.locator('.header-tabs__tab[data-tab="sistema"] [data-update-badge="1"]').count() == 1))
    P.shot_vp(out + "/desk.png", 900)
    sw = P.pg.evaluate("""async () => { const r = await fetch('/machine/update/status'); return (await r.json()).result.version_info.klipper.remote_version }""")
    ok("(the mock's Klipper)", sw == "v0.12.0-120", sw)
    ok("no errors in the page", not P.errors, P.errors[:3])
    P.close()
    b.close()

print("ALL PASS" if not FAILS else "FAILED: " + ", ".join(FAILS))
sys.exit(1 if FAILS else 0)
