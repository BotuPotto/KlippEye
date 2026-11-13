"""One "back" for the dashboard (1.24.0, roadmap phase 5f): the menu's history, the phone's back button (window.klippeyeBack,
KlippEye app 7), the swipe that closes the menu, sliders that do not move by themselves, links in the app, CPU every 5 s.
Usage: back_test.py <html> <outdir> <port>"""
import sys, os, time
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


def wait_until(fn, timeout=5.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn(): return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    try: return bool(fn())
    except Exception: return False


APP7 = """(() => { const ua = navigator.userAgent + ' KlippEyeApp/7'; Object.defineProperty(navigator, 'userAgent', { get: () => ua });
  window.KlippEyeApp = { appInfo: () => JSON.stringify({ version: '1.4.0', code: 10400, canInstall: true }), notifyState: () => JSON.stringify({ permission: true, battery: true, receive: false, chosen: true, mode: '', connected: false, lastMessageAt: 0 }), notifySetup: () => '{}' }; })();"""


def start(b, script=None, **st):
    mock.reset()
    if st: mock.set(**st)
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    if script: P.pg.add_init_script(script)
    P.pg.goto(mock.base + "/"); P.pg.wait_for_timeout(2300)
    return P


def title(P):
    return P.pg.locator(".drawer__title").inner_text() if P.pg.locator(".drawer").count() else None


def back(P):
    r = P.pg.evaluate("() => window.klippeyeBack()"); P.settle(450)
    return r


with sync_playwright() as p:
    b = p.chromium.launch()
    P = start(b)
    pg = P.pg
    ok("nothing open: «back» says there was nothing to do (the app then does its own back)", pg.evaluate("() => window.klippeyeBack()") is False)
    pg.click('button[aria-label="Impostazioni"]'); pg.wait_for_selector(".drawer"); P.settle(450)
    pg.locator('.set-entry[data-page="camera"]').click(); P.settle(500)
    pg.locator('.set-entry[data-page="camcal"]').click(); P.settle(500)
    ok("Telecamera -> Telecamera calibration (a link from another group)", title(P) == "Calibrazione della telecamera", title(P))
    pg.locator('.drawer__head [aria-label="Indietro"]').click(); P.settle(450)
    ok("the arrow goes back to the page it came from (Telecamera), not to the AI monitor", title(P) == "Telecamera", title(P))
    pg.locator('.drawer__head [aria-label="Indietro"]').click(); P.settle(450)
    ok("... then to the list", title(P) == "Impostazioni", title(P))
    pg.locator('.set-entry[data-page="ai"]').click(); P.settle(400)
    pg.locator('.set-entry[data-page="detector"]').click(); P.settle(400)
    ok("the phone's back: from Monitor thresholds to AI monitor", back(P) is True and title(P) == "Monitor IA", title(P))
    pg.locator('.drawer__help').click(); P.settle(400)
    ok("... with the guide open, back closes only the guide", back(P) is True and pg.locator(".help-sheet").count() == 0 and title(P) == "Monitor IA")
    ok("... then the list, then the menu closes", back(P) and title(P) == "Impostazioni" and back(P) and pg.locator(".drawer").count() == 0)
    ok("... and with nothing open again, false", pg.evaluate("() => window.klippeyeBack()") is False)
    pg.click('button[aria-label="Impostazioni"]'); pg.wait_for_selector(".drawer"); P.settle(450)
    pg.locator('.set-entry[data-page="setup"]').click(); P.settle(600)
    pg.locator("[data-setup-next]").click(); P.settle(300); pg.locator("[data-setup-next]").click(); P.settle(300)
    step = lambda: pg.locator("[data-setup-step]").get_attribute("data-setup-step")
    ok("guided set-up: back goes to the previous step", step() == "camera" and back(P) and step() == "printer", step())
    ok("... on the first step it closes it", back(P) and back(P) and pg.locator(".setup").count() == 0)
    pg.click('button[aria-label="Impostazioni"]'); pg.wait_for_selector(".drawer"); P.settle(450)
    pg.locator("button", has_text="Ripristina i valori iniziali").click(); P.settle(500)
    ok("a confirmation over the menu: back closes the confirmation first", pg.locator(".confirm-overlay").count() == 1 and back(P) and pg.locator(".confirm-overlay").count() == 0 and pg.locator(".drawer").count() == 1)
    pg.keyboard.press("Escape"); P.settle(400)
    P.close()

    # --- the swipe that closes the menu, on a phone
    ctx = b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, locale="it-IT")
    ctx.add_init_script("try { localStorage.setItem('ke_setup_offered', '1'); } catch (e) {}")
    pg = ctx.new_page(); CUR[0] = type("X", (), {"pg": pg})()
    mock.reset()
    pg.goto(mock.base + "/"); pg.wait_for_timeout(2300)
    pg.click('button[aria-label="Impostazioni"]'); pg.wait_for_selector(".drawer"); pg.wait_for_timeout(450)
    pg.locator('.set-entry[data-page="ai"]').click(); pg.wait_for_timeout(500)
    pg.locator('.set-entry[data-page="detector"]').click(); pg.wait_for_timeout(1500)
    SWIPE = """([sx, ex, ms, sel]) => new Promise((done) => { const el = sel ? document.querySelector(sel) : document.querySelector('.drawer__body');
      const r = el.getBoundingClientRect(); const y = r.top + Math.min(r.height / 2, 20);
      const mk = (type, x) => { const t = new Touch({ identifier: 1, target: el, clientX: x, clientY: y }); return new TouchEvent(type, { bubbles: true, cancelable: true, touches: type === 'touchend' ? [] : [t], changedTouches: [t] }); };
      el.dispatchEvent(mk('touchstart', sx)); setTimeout(() => { el.dispatchEvent(mk('touchend', ex)); done(); }, ms); })"""
    pg.evaluate(SWIPE, [300, 220, 80, None]); pg.wait_for_timeout(300)
    ok("swipe: 80 px is not enough any more (it was 70)", pg.locator(".drawer").count() == 1)
    pg.evaluate(SWIPE, [330, 120, 900, None]); pg.wait_for_timeout(300)
    ok("swipe: a slow drag does not close it", pg.locator(".drawer").count() == 1)
    pg.evaluate(SWIPE, [330, 100, 120, ".set-num__range"]); pg.wait_for_timeout(300)
    ok("swipe: started on a slider it never closes the menu", pg.locator(".drawer").count() == 1)

    # --- sliders: a touch away from the knob does not change the value
    rng = pg.locator(".set-num__range").first
    rng.scroll_into_view_if_needed(); pg.wait_for_timeout(300)
    before = rng.input_value()
    box = rng.bounding_box()
    knob = pg.evaluate("(el) => { const r = el.getBoundingClientRect(); const min = +el.min, max = +el.max; return r.left + 11 + (el.value - min) / (max - min) * (r.width - 22); }", rng.element_handle())
    far = box["x"] + 30 if knob > box["x"] + box["width"] / 2 else box["x"] + box["width"] - 30
    pg.touchscreen.tap(far, box["y"] + box["height"] / 2); pg.wait_for_timeout(400)
    ok("a slider touched away from its knob (scrolling the menu) keeps its value", rng.input_value() == before, (before, rng.input_value()))
    pg.evaluate(SWIPE, [330, 100, 120, None]); pg.wait_for_timeout(500)
    ok("swipe: long, quick and sideways on the page closes it", pg.locator(".drawer").count() == 0)
    ctx.close()

    # --- in the app 1.4.0: store links and «Open in the ntfy app»
    P = start(b, APP7, ntfy={"enabled": True, "server": "https://ntfy.sh", "topic": "klippeye-abcdefghijklmnop", "has_token": False, "click": ""})
    pg = P.pg
    pg.click('button[aria-label="Impostazioni"]'); pg.wait_for_selector(".drawer"); P.settle(450)
    pg.locator('.set-entry[data-page="notifications"]').click(); P.settle(900)
    ok("app 1.4.0 (it opens links outside): the store buttons are back in «Altri telefoni»", pg.locator(".nt-links a").count() == 3)
    P.close()

    # --- System: CPU and memory every 5 seconds
    P = start(b)
    P.goto("sistema", 1500)
    P.reqs.clear(); P.pg.wait_for_timeout(11000)
    n = len([r for r in P.reqs if r["u"].startswith("/machine/proc_stats")])
    ok("System page: CPU and memory read again every 5 s (2 in 11 s)", n >= 2, n)
    P.pg.evaluate("() => localStorage.setItem('ke_current_tab', 'home')"); P.pg.reload(); P.pg.wait_for_timeout(1500); P.reqs.clear(); P.pg.wait_for_timeout(6000)
    ok("... and not on the other pages", not [r for r in P.reqs if r["u"].startswith("/machine/proc_stats")])
    P.close()
    b.close()

print("\nFAILED: %d %s" % (len(FAILS), FAILS) if FAILS else "\nALL PASS")
sys.exit(1 if FAILS else 0)
