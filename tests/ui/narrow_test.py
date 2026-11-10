"""Release 1.55.3 (roadmap 8): nothing sticks out of its card on a narrow phone. Every page (Home, Control, Files with
history and timelapse, Config, System) with every optional card on (more sensors, power devices, Spoolman, the queue, the
timelapse, a print going on), at 320 and 390 px: no element reaches past the edge of its card, and no page scrolls
sideways. Against the mock.
Usage: narrow_test.py <html> <outdir> <port>"""
import json
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


JS = """() => { const out = []; const vw = document.documentElement.clientWidth;
  for (const card of document.querySelectorAll('.oui-card, .set-group, .sheet-card')) {
    const cr = card.getBoundingClientRect(); if (cr.width === 0) continue;
    for (const el of card.querySelectorAll('button, a, input, span, div, img, svg, canvas')) {
      const r = el.getBoundingClientRect(); if (r.width === 0 || r.height === 0) continue;
      const cs = getComputedStyle(el); if (cs.position === 'fixed' || cs.visibility === 'hidden') continue;
      let p = el.parentElement, clipped = false; while (p && p !== card) { const s = getComputedStyle(p); if (s.overflowX !== 'visible' || s.overflow !== 'visible') { clipped = true; break; } p = p.parentElement; }
      if (clipped) continue;
      if (r.right > cr.right + 1.5 || r.left < cr.left - 1.5) out.push([(card.getAttribute('data-card') || card.className).slice(0, 40), (el.className && el.className.baseVal === undefined ? el.className : el.tagName).toString().slice(0, 50), Math.round(r.left), Math.round(r.right), Math.round(cr.left), Math.round(cr.right), (el.innerText || '').slice(0, 30)]);
    }
  }
  return { page: document.documentElement.scrollWidth > vw, out: out.slice(0, 12) }; }"""

with sync_playwright() as p:
    b = p.chromium.launch()
    # 1.86: in Spanish too (longer words than Italian)
    for lang, w in (("it-IT", 320), ("it-IT", 390), ("es-ES", 320), ("es-ES", 390), ("de-DE", 320), ("de-DE", 390)):
        mock.reset()
        mock.set(extra_temps=True, power_on=True, extra_devices=True, spoolman_on=True, queue_on=True, timelapse_on=True, printing=True,
                 queue=[{"filename": "Benchy_0.2mm_PLA.gcode", "job_id": "1", "time_added": 1}])
        P = Page(b, mock, w, 800, locale=lang)
        if lang == "es-ES":
            P.goto("home", 2600)
            ok("[%d] es: the page is in Spanish" % w, P.pg.evaluate("document.documentElement.lang") == "es" and P.pg.locator('.app-header button[aria-label="Ajustes"]').count() == 1 and "Calentadores" in P.pg.locator("body").inner_text())
        if lang == "de-DE":
            P.goto("home", 2600)
            ok("[%d] de: the page is in German" % w, P.pg.evaluate("document.documentElement.lang") == "de" and P.pg.locator('.app-header button[aria-label="Einstellungen"]').count() == 1 and "Heizungen" in P.pg.locator("body").inner_text())
        tag = "" if lang == "it-IT" else " " + lang[:2]
        for tab in ("home", "controllo", "files", "config", "sistema"):
            P.goto(tab, 2600)
            r = P.pg.evaluate(JS)
            ok("[%d%s] %s: nothing out of its card, no sideways scroll" % (w, tag, tab), not r["page"] and not r["out"], json.dumps(r, ensure_ascii=False))
        for section in ("history", "timelapse"):
            P.goto("files", 1500)
            P.pg.locator('[data-files-section="%s"]' % section).click()
            P.pg.wait_for_timeout(1500)
            r = P.pg.evaluate(JS)
            ok("[%d%s] files / %s: nothing out of its card" % (w, tag, section), not r["page"] and not r["out"], json.dumps(r, ensure_ascii=False))
        P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
