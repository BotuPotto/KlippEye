"""1.154.0: small fixes of the look. The tab bar is translated («Files», «Config»), the small buttons have a 44 px touch area
(fold chevron, fan − / +, round header buttons, the AI badge, the «?» buttons, a file's menu), the brand name is not cut on a 360 to
412 px phone, a fan's name wraps to two lines instead of being cut (German, Polish, Russian), and a Raspberry that does not answer
shows the strip at once and keeps the last temperatures instead of zeros. Against the mock.
Usage: look_small_test.py <html> <outdir> <port>"""
import os
import sys
import time
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


def wait_until(fn, timeout=6.0, step=0.15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    try:
        return bool(fn())
    except Exception:
        return False


def fresh(b, w=360, h=780, tab="home", wait=2200, locale="en-US", **st):
    mock.reset()
    if st:
        mock.set(**st)
    P = Page(b, mock, w, h, locale=locale)
    CUR[0] = P
    P.goto(tab, wait)
    return P


# a 44 px square around each element answers its taps: four points 21 px from the centre hit the element (or its touch area)
HIT_JS = """(sel) => {
  const bad = []; let n = 0;
  for (const el of document.querySelectorAll(sel)) {
    const cs = getComputedStyle(el); if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    el.scrollIntoView({ block: 'center' });
    const r = el.getBoundingClientRect(); if (r.width < 2) continue;
    n += 1;
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    for (const [x, y] of [[cx - 21, cy], [cx + 21, cy], [cx, cy - 21], [cx, cy + 21]]) {
      const t = document.elementFromPoint(x, y);
      if (!(t && (t === el || el.contains(t)))) { bad.push((el.getAttribute('aria-label') || el.className) + ' @' + Math.round(x - cx) + ',' + Math.round(y - cy) + ' -> ' + (t && (t.className || t.tagName))); break; }
    }
  }
  return { n, bad };
}"""


def hits(P, sel):
    return P.pg.evaluate(HIT_JS, sel)


def open_drawer(P, page=None):
    P.pg.locator(".header-btn--menu").click()
    P.pg.wait_for_selector(".drawer")
    P.pg.wait_for_timeout(600)
    if page:
        P.pg.click('.drawer .set-entry[data-page="%s"]' % page)
        P.pg.wait_for_timeout(600)


with sync_playwright() as p:
    b = p.chromium.launch()

    # ---- 74: the tab bar and the page title in the person's language
    for loc, files, config in (("pl-PL", "Pliki", "Konfig"), ("de-DE", "Dateien", "Konfig"), ("ru-RU", "Файлы", "Конфиг")):
        P = fresh(b, locale=loc)
        labels = [e.inner_text().strip() for e in P.pg.locator(".bottom-nav__label").all()]
        ok("1.154.0: the tab bar is translated (%s)" % loc, files in labels and config in labels and "Files" not in labels and "Config" not in labels, labels)
        P.pg.locator('.bottom-nav [data-tab="files"]').click()
        P.pg.wait_for_timeout(600)
        ok("1.154.0: ... and so is the page title (%s)" % loc, P.pg.locator(".oui-page-title").first.inner_text().strip() == files, P.pg.locator(".oui-page-title").first.inner_text())
        P.close()
    P = fresh(b, 1280, 800, locale="de-DE")
    head = P.pg.locator(".app-header").inner_text()
    ok("1.154.0: the computer's top tabs say «Konfig»", "Konfig" in head and "Config" not in head, head)
    P.close()

    # ---- 75: touch areas
    P = fresh(b, printing=True)
    P.pg.locator(".fan-lock").first.click()   # the fans are locked at first: a locked button answers no tap
    for sel, minimum in ((".header-btn", 4), (".ai-header-badge", 1), (".oui-card__fold", 3), (".fan-step", 4)):
        res = hits(P, sel)
        ok("1.154.0: %s answers a tap 22 px from its centre (%d found)" % (sel, res["n"]), res["n"] >= minimum and not res["bad"], res)
    P.close()
    P = fresh(b, tab="files")
    res = hits(P, ".file-card__more")
    ok("1.154.0: a file's menu button answers a tap 22 px from its centre (%d found)" % res["n"], res["n"] >= 2 and not res["bad"], res)
    P.close()
    P = fresh(b)
    open_drawer(P, "motion")
    res = hits(P, ".help-btn--small, .drawer__help, .drawer__btn")
    ok("1.154.0: the «?» buttons and the drawer's buttons answer a tap 22 px from their centre (%d found)" % res["n"], res["n"] >= 4 and not res["bad"], res)
    P.close()
    P = fresh(b, 1280, 800, printing=True)
    P.pg.locator(".fan-lock").first.click()
    res = hits(P, ".oui-card__fold, .fan-step")
    ok("1.154.0: the same on a computer (%d found)" % res["n"], res["n"] >= 4 and not res["bad"], res)
    P.close()

    # ---- 76: the brand name is whole
    for w in (360, 375, 390, 412):
        P = fresh(b, w, 780, printing=True)
        sizes = P.pg.evaluate("() => { const n = document.querySelector('.app-header__name'); return [n.scrollWidth, n.clientWidth, n.innerText]; }")
        ok("1.154.0: the brand name is not cut at %d px" % w, sizes[0] <= sizes[1], sizes)
        P.close()

    # ---- 77: a fan's name wraps instead of being cut
    for loc in ("pl-PL", "de-DE", "ru-RU"):
        P = fresh(b, locale=loc)
        cut = P.pg.evaluate("() => [...document.querySelectorAll('.fan-name')].filter(e => e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1).map(e => e.innerText)")
        names = P.pg.locator(".fan-name").count()
        ok("1.154.0: the fan names are whole (%s, %d fans)" % (loc, names), names >= 4 and not cut, cut)
        P.close()

    # ---- 78: the Raspberry does not answer
    P = fresh(b)
    pg = P.pg
    heat = lambda: pg.locator('[data-card="heaters"]').inner_text() if pg.locator('[data-card="heaters"]').count() else pg.locator("body").inner_text()
    ok("1.154.0: before, the nozzle reads its temperature", "215.3" in heat(), heat())
    mock.set(moonraker_down=True)
    ok("1.154.0: a few seconds after, the strip says the printer does not answer", wait_until(lambda: pg.locator("#live-banner[data-state='unreachable']").count() == 1, 8))
    ok("1.154.0: ... and the nozzle still shows its last temperature, not 0.0", "215.3" in heat() and "0.0°" not in heat().replace("215.3°", ""), heat())
    mock.set(moonraker_down=False)
    ok("1.154.0: when it answers again the strip goes", wait_until(lambda: pg.locator("#live-banner").count() == 0, 8))
    P.close()

    b.close()

print("\n%d failed" % len(FAILS))
sys.exit(1 if FAILS else 0)
