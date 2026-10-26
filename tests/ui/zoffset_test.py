import sys, os
from playwright.sync_api import sync_playwright
from lib import *
html, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
mock = Mock(html, 9540)
import atexit; atexit.register(mock.stop)
FONT = "document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');s.textContent=':root{--oui-font:Inter,sans-serif}';document.head.appendChild(s)})"
OVER = "() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})"
def fresh(w=390, h=844, wait=2600, **state):
    mock.reset()
    if state: mock.set(**state)
    P = Page(b, mock, w, h)
    P.ctx.add_init_script(FONT)
    P.goto("home", wait)
    return P
_FAILED = []
def ok(name, cond, extra=""):
    if not cond: _FAILED.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra != "" else ""))
def zcard(P): return P.pg.locator(".oui-card:has(.oui-card-title:text-is('Z-offset'))").first
def mcard(P): return P.pg.locator(".oui-card:has(.oui-card-title:text-is('Movimento'))")
def readout(P): return zcard(P).locator(".zoffset-readout__value").inner_text().replace("\n", "").replace("mm", "").strip()
PRINT = dict(printing=True)
with sync_playwright() as p:
    b = p.chromium.launch()
    for w in (390, 320, 1280):
        P = fresh(w, 844 if w < 1000 else 800, **PRINT)
        ok(f"[{w}] printing: z-offset card replaces movement", zcard(P).count() == 1 and mcard(P).count() == 0)
        ov = P.pg.evaluate(OVER); ok(f"[{w}] no horizontal overflow", ov["sw"] <= ov["cw"], ov)
        zcard(P).screenshot(path=f"{out}/printing_{w}.png", animations="disabled")
        P.close()

    P = fresh(**PRINT)
    z = zcard(P)
    ok("initial", readout(P) == "0.000" and "Live" in z.inner_text() and "Nessuna correzione" in z.inner_text(), readout(P))
    ok("apply + reset disabled with zero offset while printing", z.locator("button:has-text('Salva offset')").is_disabled() and z.locator("button:has-text('Azzera')").is_disabled())
    ok("hint", "a fine stampa" in z.inner_text().lower())
    # two quick taps -> one command
    z.locator("button:has-text('Alza')").click(); z.locator("button:has-text('Alza')").click()
    ok("optimistic read-out", readout(P) == "+0.020", readout(P))
    P.pg.wait_for_timeout(1800)
    sent = [g for g in mock.gcode() if g.startswith("SET_GCODE_OFFSET")]
    ok("one combined command", sent == ["SET_GCODE_OFFSET Z_ADJUST=+0.02 MOVE=1"], sent)
    ok("read-out after refresh", readout(P) == "+0.020" and "più lontano" in z.inner_text(), readout(P))
    # step selection
    z.locator(".zoffset-steps .oui-chip:text-is('0.05')").click()
    z.locator("button:has-text('Abbassa')").click(); P.pg.wait_for_timeout(1800)
    sent = [g for g in mock.gcode() if g.startswith("SET_GCODE_OFFSET")]
    ok("lower by 0.05", sent[-1] == "SET_GCODE_OFFSET Z_ADJUST=-0.05 MOVE=1" and readout(P) == "−0.030" and "più vicino" in z.inner_text(), (sent, readout(P)))
    zcard(P).screenshot(path=f"{out}/adjusted.png", animations="disabled")
    ok("apply still disabled while printing", z.locator("button:has-text('Salva offset')").is_disabled())
    # reset: cancel then confirm
    z.locator("button:has-text('Azzera')").click(); P.pg.wait_for_selector(".confirm-overlay")
    P.pg.screenshot(path=f"{out}/reset_dialog.png", animations="disabled")
    P.pg.locator(".confirm-card button:has-text('Annulla')").click(); P.pg.wait_for_timeout(400)
    ok("cancel keeps offset", not any(g.startswith("SET_GCODE_OFFSET Z=0") for g in mock.gcode()) and readout(P) == "−0.030")
    z.locator("button:has-text('Azzera')").click(); P.pg.wait_for_selector(".confirm-overlay")
    P.pg.locator(".confirm-card button:has-text('Azzera')").click(); P.pg.wait_for_timeout(1800)
    ok("reset sent", "SET_GCODE_OFFSET Z=0 MOVE=1" in mock.gcode() and readout(P) == "0.000", (mock.gcode()[-2:], readout(P)))
    # step remembered
    P.pg.reload(); P.pg.wait_for_timeout(2600)
    ok("step remembered", "is-selected" in (zcard(P).locator(".zoffset-steps .oui-chip:text-is('0.05')").get_attribute("class") or ""))
    P.close()

    # end of print: card above movement, apply works
    P = fresh(print_state="complete", z_offset=-0.05)
    z = zcard(P)
    ok("complete + offset: z card above movement", z.count() == 1 and mcard(P).count() == 1 and z.bounding_box()["y"] < mcard(P).bounding_box()["y"])
    ok("badge 'A fine stampa', apply enabled", "A fine stampa" in z.inner_text() and z.locator("button:has-text('Salva offset')").is_enabled() and readout(P) == "−0.050")
    P.pg.evaluate("window.scrollTo(0, 0)"); P.pg.wait_for_timeout(200)
    z.screenshot(path=f"{out}/end_of_print.png", animations="disabled")
    z.locator("button:has-text('Salva offset')").click(); P.pg.wait_for_selector(".confirm-overlay")
    P.pg.screenshot(path=f"{out}/apply_dialog.png", animations="disabled")
    ok("dialog names the command", "Z_OFFSET_APPLY_PROBE" in P.pg.locator(".confirm-card").inner_text())
    P.pg.locator(".confirm-card button:has-text('Applica e salva')").click(); P.pg.wait_for_timeout(1500)
    log = mock.gcode()
    ok("apply then save", log[-2:] == ["Z_OFFSET_APPLY_PROBE", "SAVE_CONFIG"], log)
    P.pg.wait_for_timeout(1500)
    ok("card gone after save (offset reset by restart)", zcard(P).count() == 0 and mcard(P).count() == 1)
    P.close()
    P = fresh(print_state="complete", z_offset=-0.05, apply_error="Unknown command")
    z = zcard(P); z.locator("button:has-text('Salva offset')").click(); P.pg.wait_for_selector(".confirm-overlay")
    P.pg.locator(".confirm-card button:has-text('Applica e salva')").click(); P.pg.wait_for_timeout(1200)
    ok("apply failure: toast, no SAVE_CONFIG", "SAVE_CONFIG" not in mock.gcode() and "non applicato" in P.pg.locator(".toast").last.inner_text(), mock.gcode())
    P.close()
    # endstop flavour
    P = fresh(print_state="complete", z_offset=0.03, z_pin="PA1", z_apply="endstop")
    z = zcard(P); z.locator("button:has-text('Salva offset')").click(); P.pg.wait_for_selector(".confirm-overlay")
    ok("endstop printers use Z_OFFSET_APPLY_ENDSTOP", "Z_OFFSET_APPLY_ENDSTOP" in P.pg.locator(".confirm-card").inner_text())
    P.close()
    P = fresh(print_state="complete", z_offset=0.03, z_pin="probe:z_virtual_endstop", z_apply="endstop")
    z = zcard(P)
    ok("mismatch: no apply button, explanation", z.locator("button:has-text('Salva offset')").count() == 0 and "Klipper non offre" in z.inner_text())
    P.close()
    # states that must NOT show the card
    for name, st in [("idle + offset", dict(z_offset=0.04)), ("complete, no offset", dict(print_state="complete")), ("paused", dict(printing=True, paused=True, z_offset=0.04))]:
        P = fresh(**st)
        ok(f"no z card: {name}", zcard(P).count() == 0 and mcard(P).count() == 1)
        P.close()
    P = fresh(print_state="cancelled", z_offset=0.02)
    ok("cancelled with offset: card shown", zcard(P).count() == 1)
    P.close()
    P = fresh(**PRINT)
    ok("no page errors", not [e for e in P.errors if "pageerror" in e], P.errors[:3])
    P.close()
    b.close()
print("FAILS: %s" % (_FAILED or "none"))
sys.exit(1 if _FAILED else 0)
