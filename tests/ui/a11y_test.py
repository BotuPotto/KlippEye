"""Accessibility checks (roadmap): on every page, in every page of the menu (and one level below) and in the print's
confirmation, at phone and computer width: every button, link, switch and tab has a name a screen reader can say,
every field a label, every picture an alt text, switches say whether they are on, no id is used twice.
Usage: a11y_test.py <html> <outdir> <port>"""
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


def errs(P):
    return [e for e in P.errors if "pageerror" in e or "console.error" in e]


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())




def gcodes():
    return state()["gcode_log"]


CHECK = r"""() => {
  const visible = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && !e.closest("[aria-hidden=true],[inert]"); };
  const name = (e) => {
    const label = e.getAttribute("aria-label") || e.getAttribute("title") || "";
    const by = (e.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean).map((id) => (document.getElementById(id) || {}).textContent || "").join(" ");
    const text = (e.innerText || "").trim() || e.textContent || e.value || "";
    const alt = [...e.querySelectorAll("img[alt]")].map((i) => i.alt).join(" ");
    let lab = "";
    if (e.id) { const l = document.querySelector('label[for="' + CSS.escape(e.id) + '"]'); if (l) lab = l.textContent; }
    const wrap = e.closest("label"); if (wrap) lab += wrap.textContent;
    return (label + by + text + alt + lab + (e.getAttribute("placeholder") || "")).trim();
  };
  const where = (e) => (e.className && typeof e.className === "string" ? "." + e.className.trim().split(/\s+/).slice(0, 2).join(".") : e.tagName.toLowerCase()) + (e.closest("[data-card]") ? " in " + e.closest("[data-card]").getAttribute("data-card") : "");
  const out = [];
  document.querySelectorAll("button, a[href], [role=button], [role=switch], [role=tab], [role=menuitem], [role=checkbox]").forEach((e) => { if (visible(e) && !name(e)) out.push(["no-name", where(e)]); });
  document.querySelectorAll("input:not([type=hidden]), select, textarea").forEach((e) => { if (visible(e) && !name(e)) out.push(["field-no-label", where(e)]); });
  document.querySelectorAll("img").forEach((e) => { if (visible(e) && !e.hasAttribute("alt")) out.push(["img-no-alt", where(e)]); });
  document.querySelectorAll("[role=switch], [role=checkbox]").forEach((e) => { if (visible(e) && !e.hasAttribute("aria-checked") && e.tagName !== "INPUT") out.push(["switch-no-state", where(e)]); });
  const ids = {}; document.querySelectorAll("[id]").forEach((e) => { ids[e.id] = (ids[e.id] || 0) + 1; });
  Object.entries(ids).forEach(([id, n]) => n > 1 && out.push(["duplicate-id", id]));
  if (!document.documentElement.lang) out.push(["no-lang", "html"]);
  return out;
}
"""


def check_here(P, where):
    problems = P.pg.evaluate(CHECK)
    ok("%s: every control has a name, every picture an alt, no duplicate ids" % where, not problems, problems[:8])
    return problems


def open_menu(P):
    P.pg.click('button[aria-label="Impostazioni"]')
    P.pg.wait_for_selector(".drawer")
    P.settle(500)


with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    for w, hh in ((390, 844), (1440, 900)):
        P = Page(b, mock, w, hh)
        CUR[0] = P
        for tab in ("home", "controllo", "files", "config", "sistema"):
            P.goto(tab, 2600)
            check_here(P, "%d %s" % (w, tab))
        if w == 390:
            # the menu: every page of its first level, and the ones inside AI monitor and Camera
            P.goto("home", 2000)
            open_menu(P)
            check_here(P, "menu")
            pages = [e.get_attribute("data-page") for e in P.pg.locator(".drawer .set-entry[data-page]").all()]
            for name in pages:
                P.goto("home", 1500)
                open_menu(P)
                P.pg.click('.drawer .set-entry[data-page="%s"]' % name)
                P.settle(900)
                check_here(P, "menu → " + name)
                subs = [e.get_attribute("data-page") for e in P.pg.locator(".drawer .set-entry[data-page]").all()]
                for sub in subs[:6]:
                    P.goto("home", 1500)
                    open_menu(P)
                    P.pg.click('.drawer .set-entry[data-page="%s"]' % name)
                    P.settle(700)
                    P.pg.click('.drawer .set-entry[data-page="%s"]' % sub)
                    P.settle(900)
                    check_here(P, "menu → %s → %s" % (name, sub))
            # a dialog: the print's confirmation
            P.goto("files", 2400)
            P.pg.locator(".file-card", has_text="Benchy").locator('button[aria-label="Avvia stampa"]').first.click()
            P.settle(1200)
            check_here(P, "print confirmation")
        ok("%d: no page errors" % w, not errs(P), errs(P)[:2])
        P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
