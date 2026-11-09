"""Release 1.70.2: the visual review of 9 November, on a phone (360 px), a tablet and computers. What was found and fixed
stays fixed: clock times under the temperature chart that ran into each other, the Files switch on two lines, the file
panel's buttons squeezed into each other, «6,3 mm…» on the print card, «Camera» said twice over the picture, «See the
layers» touching Pause / Cancel. And on every page at every size: no sideways scrolling, no text off the screen.
Usage: visual_test.py <html> <outdir> <port>"""
import os
import sys
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


OVERLAP = """(sel) => { const r = [...document.querySelectorAll(sel)].filter(e => e.offsetParent).map(e => e.getBoundingClientRect());
  for (let i = 0; i < r.length; i++) for (let j = i + 1; j < r.length; j++) {
    const a = r[i], b = r[j];
    if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) return [i, j];
  } return null; }"""
CLIPPED = """(sel) => [...document.querySelectorAll(sel)].filter(e => e.offsetParent && e.scrollWidth > e.clientWidth + 1).map(e => e.textContent)"""
OFFSCREEN = """() => { const vw = document.documentElement.clientWidth; const out = [];
  if (document.documentElement.scrollWidth > vw + 1) out.push("page " + document.documentElement.scrollWidth);
  for (const el of document.querySelectorAll('button, .oui-card__title, .dialog-title, .oui-label')) {
    if (!el.offsetParent || el.closest('.set-chips, .temp-ranges, .files-section-bar, .oui-segmented, [class*=scroll], .desk-dock')) continue;
    const r = el.getBoundingClientRect(); if (r.width && (r.right > vw + 1 || r.left < -1)) out.push(el.textContent.trim().slice(0, 30)); }
  return out; }"""

with sync_playwright() as p:
    b = p.chromium.launch()
    # a 360 px phone
    mock.reset()
    P = Page(b, mock, 360, 780)
    P.goto("home", 2600)
    ok("360 px: the clock times under the temperature chart do not run into each other", P.pg.evaluate(OVERLAP, ".temp-chart__tick") is None and P.pg.locator(".temp-chart__tick").count() >= 3)
    P.goto("files", 2200)
    btn = P.pg.locator(".files-section-switch > button").first
    ok("360 px: «File di stampa» on one line", btn.bounding_box()["height"] < 48 and btn.evaluate("e => e.scrollWidth <= e.clientWidth + 1"), btn.bounding_box())
    P.close()
    mock.reset()
    mock.set(printing=True)
    P = Page(b, mock, 1024, 768)
    P.goto("home", 2400)
    gap = P.pg.evaluate("() => { const a = document.querySelector('.gcode-view-btn').getBoundingClientRect(); const b = [...document.querySelectorAll('.oui-btn-row .oui-btn')].find(e => e.offsetParent).getBoundingClientRect(); return b.top - a.bottom; }")
    ok("tablet: a gap between «Vedi i layer» and Pausa / Annulla", gap >= 8, gap)
    P.close()
    # computers
    mock.reset()
    mock.set(printing=True)
    P = Page(b, mock, 1280, 720)
    P.goto("home", 2600)
    ok("1280: the six figures of the print fit (no «6,3 mm…»)", P.pg.evaluate(CLIPPED, ".desk-print__stats .print-stat__value") == [], P.pg.evaluate(CLIPPED, ".desk-print__stats .print-stat__value"))
    ok("1280: with a camera picker, «Camera» is not said twice over the picture", P.pg.locator(".desk-camera__picker").count() == 0 or P.pg.locator(".desk-camera__tag").count() == 0)
    P.close()
    mock.reset()
    P = Page(b, mock, 1440, 900)
    P.goto("files", 2400)
    ok("1440: the file panel's buttons never overlap", P.pg.evaluate(OVERLAP, ".desk-detail__actions > .oui-btn") is None and P.pg.evaluate(CLIPPED, ".desk-detail__actions > .oui-btn") == [], P.pg.evaluate(CLIPPED, ".desk-detail__actions > .oui-btn"))
    P.close()
    # every page, every size: nothing sideways
    for w, hh in ((360, 780), (390, 844), (768, 1024), (1024, 768), (1280, 720), (1920, 1080)):
        for state in ({}, {"printing": True}):
            for tab in ("home", "controllo", "files", "config", "sistema"):
                mock.reset()
                mock.set(**state)
                P = Page(b, mock, w, hh)
                P.goto(tab, 1800)
                bad = P.pg.evaluate(OFFSCREEN)
                ok("%dx%d %s%s: nothing off the screen" % (w, hh, tab, " (printing)" if state else ""), bad == [], bad)
                P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
