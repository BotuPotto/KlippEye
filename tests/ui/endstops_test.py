import sys, os
from playwright.sync_api import sync_playwright
from lib import *
html, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
mock = Mock(html, 9530)
import atexit; atexit.register(mock.stop)
FONT = "document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');s.textContent=':root{--oui-font:Inter,sans-serif}';document.head.appendChild(s)})"
OVER = "() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})"
def fresh(w=390, h=844, wait=2300, preopen=False, **state):
    mock.reset()
    if state: mock.set(**state)
    P = Page(b, mock, w, h)
    P.ctx.add_init_script(FONT)
    if preopen: P.ctx.add_init_script("try{localStorage.setItem('ke_endstops_open','1')}catch(e){}")
    P.goto("controllo", wait)
    return P
_FAILED = []
def ok(name, cond, extra=""):
    if not cond: _FAILED.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra != "" else ""))
def card(P): return P.pg.locator(".oui-card:has(.oui-card-title:text-is('Calibrazioni'))").first
def n_queries(): return sum(1 for g in mock.gcode() if g in ("QUERY_ENDSTOPS", "QUERY_PROBE"))
def asked(P): return any("query_endstops" in r["u"] for r in P.reqs) or n_queries() > 0
def press_update(P, c, wait=1000):
    c.locator("button:has-text('Aggiorna')").click(); P.pg.wait_for_timeout(wait)
with sync_playwright() as p:
    b = p.chromium.launch()
    for w in (390, 320, 1280):
        P = fresh(w, 844 if w < 1000 else 800)
        c = card(P)
        ok(f"[{w}] collapsed: header only, nothing queried", c.locator(".endstops-head").count() == 1 and c.locator(".endstops-body").count() == 0 and "QUERY_ENDSTOPS" not in mock.gcode())
        c.locator(".endstops-head").click(); P.pg.wait_for_timeout(1500)
        body = c.locator(".endstops-body").inner_text()
        ok(f"[{w}] opening the section reads nothing: it says to press Aggiorna", c.locator(".endstops-body .oui-row").count() == 0 and not asked(P) and "Premi Aggiorna" in body and "Non ancora letti" in body and c.locator("button:has-text('Aggiorna')").is_enabled(), (body, P.reqs[-3:], mock.gcode()))
        press_update(P, c)
        ok(f"[{w}] Aggiorna reads endstops and probe", c.locator(".endstops-body .oui-row").count() == 4 and "QUERY_ENDSTOPS" in mock.gcode() and "QUERY_PROBE" in mock.gcode() and "Aggiornato alle" in c.locator(".endstops-body").inner_text(), mock.gcode())
        ov = P.pg.evaluate(OVER); ok(f"[{w}] no horizontal overflow", ov["sw"] <= ov["cw"], ov)
        c.screenshot(path=f"{out}/open_{w}.png", animations="disabled")
        P.close()
    # states
    P = fresh(endstops={"x": "TRIGGERED", "y": "open", "z": "open"}, probe_triggered=True)
    c = card(P); c.locator(".endstops-head").click(); P.pg.wait_for_timeout(600); press_update(P, c)
    rows = c.locator(".endstops-body .oui-row")
    txt = [rows.nth(i).inner_text().replace("\n", " ") for i in range(rows.count())]
    ok("row contents", txt[0].startswith("X") and "Attivato" in txt[0] and "Aperto" in txt[1] and "Probe" in txt[3] and "cartographer" in txt[3] and "Attivato" in txt[3], txt)
    ok("badge classes", c.locator(".oui-badge--danger").count() == 2 and c.locator(".oui-badge--ok").count() == 2)
    c.screenshot(path=f"{out}/states.png", animations="disabled")
    # refresh picks up new state
    mock.set(endstops={"x": "open", "y": "TRIGGERED", "z": "open"}, probe_triggered=False)
    press_update(P, c)
    rows = c.locator(".endstops-body .oui-row")
    txt = [rows.nth(i).inner_text().replace("\n", " ") for i in range(rows.count())]
    ok("refresh updates", "Aperto" in txt[0] and "Attivato" in txt[1] and "Aperto" in txt[3], txt)
    # persistence of open/closed
    n_before = n_queries()
    P.take_reqs(); P.pg.reload(); P.pg.wait_for_timeout(2800)
    ok("open state remembered", card(P).locator(".endstops-body").count() == 1)
    ok("coming back to the page with the section open reads nothing", not any("query_endstops" in r["u"] for r in P.reqs) and n_queries() == n_before and card(P).locator(".endstops-body .oui-row").count() == 0 and "Premi Aggiorna" in card(P).locator(".endstops-body").inner_text(), (P.reqs[-3:], n_queries(), n_before))
    card(P).locator(".endstops-head").click(); P.pg.wait_for_timeout(300)
    ok("collapse: the content stays while the section folds (350 ms)", card(P).locator(".endstops-body").count() == 1)
    P.pg.wait_for_timeout(500)
    ok("collapse", card(P).locator(".endstops-body").count() == 0)
    P.close()
    # no probe
    P = fresh(has_probe=False, preopen=True)
    c = card(P); P.pg.wait_for_timeout(500)
    ok("page opened with the section open: nothing read by itself", not asked(P), (P.reqs[-3:], mock.gcode()))
    press_update(P, c)
    ok("probe object missing: still 3 endstops, no probe row", c.locator(".endstops-body .oui-row").count() == 3 and "Probe" not in c.locator(".endstops-body").inner_text())
    P.close()
    # error
    P = fresh(endstops_error="Klippy Host not ready", preopen=True)
    c = card(P); P.pg.wait_for_timeout(500)
    ok("error: nothing read until Aggiorna", not asked(P) and "Klippy Host not ready" not in c.locator(".endstops-body").inner_text())
    press_update(P, c)
    ok("error shown", "Klippy Host not ready" in c.locator(".endstops-body").inner_text(), c.locator(".endstops-body").inner_text())
    ok("error: caption says the reading failed and Aggiorna can try again", "Lettura non riuscita" in c.locator(".endstops-foot").inner_text() and c.locator("button:has-text('Aggiorna')").is_enabled(), c.locator(".endstops-foot").inner_text())
    c.screenshot(path=f"{out}/error.png", animations="disabled")
    mock.set(endstops_error="")
    press_update(P, c)
    ok("error: after the fault clears, Aggiorna reads normally", c.locator(".endstops-body .oui-row").count() == 4, c.locator(".endstops-body").inner_text())
    P.close()
    # printing
    P = fresh(printing=True, preopen=True)
    c = card(P); P.pg.wait_for_timeout(500)
    ok("printing: notice, nothing queried", "durante una stampa" in c.locator(".endstops-body").inner_text() and "QUERY_ENDSTOPS" not in mock.gcode() and "QUERY_PROBE" not in mock.gcode(), mock.gcode())
    P.close()
    P = fresh()
    ok("no page errors", not [e for e in P.errors if "pageerror" in e], P.errors[:3])
    P.close()
    b.close()
print("FAILS: %s" % (_FAILED or "none"))
sys.exit(1 if _FAILED else 0)
