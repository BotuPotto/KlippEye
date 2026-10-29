"""Does the dashboard come back to life after the phone slept / the page was in the background?
A proxy stands between browser and mock and, on freeze(), kills the connections that exist at that moment without
closing them (what a sleeping phone's connections do): requests on them hang for ever, new connections work.
Usage: live_test.py <html> <outdir> <port> [--repro]   (--repro: only print, never fail)"""
import sys, os, re, json, time
from playwright.sync_api import sync_playwright
from lib import *
from blackhole_proxy import Proxy

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
REPRO = "--repro" in sys.argv
mock = Mock(html, port)
proxy = Proxy(port + 1, port)
import atexit; atexit.register(mock.stop); atexit.register(proxy.stop)


class Via:                        # the page talks to the proxy; the test talks to the mock directly
    base = f"http://127.0.0.1:{port + 1}"


FAILS = []
VIS = """(hidden) => { Object.defineProperty(document, 'hidden', {configurable: true, get: () => hidden});
  Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => hidden ? 'hidden' : 'visible'});
  document.dispatchEvent(new Event('visibilitychange')); }"""


def ok(name, cond, extra=""):
    if not cond and not REPRO: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra != "" else ""))


def fresh(tab="home", **state):
    mock.reset()
    if state: mock.set(**state)
    P = Page(b, Via, 390, 844)
    P.answers = []                                   # (time, path) of every answer that came back
    P.pg.add_init_script("(() => { const W = window.WebSocket; let n = 0; window.__wsCount = () => n; window.WebSocket = new Proxy(W, { construct(t, a) { n++; return new t(...a); } }); })();")
    P.pg.on("response", lambda r: P.answers.append((time.time(), r.url.replace(Via.base, "").split("?")[0])))
    P.goto(tab, 3000)
    return P


def answered_after(P, t0, path, limit):
    """Seconds after t0 until `path` is answered (None: never within `limit`)."""
    while time.time() - t0 < limit:
        for t, u in P.answers:
            if t >= t0 and u == path: return round(t - t0, 1)
        P.pg.wait_for_timeout(100)
    return None


def hot(P): return P.pg.locator("button.heater-tile").first.inner_text().replace("\n", " ")
def errs(P): return [e for e in P.errors if "pageerror" in e or "console.error" in e]
def vis(P, hidden): P.pg.evaluate(VIS, hidden)


def wait_for(P, pred, limit):
    t0 = time.time()
    while time.time() - t0 < limit:
        try:
            if pred(): return round(time.time() - t0, 1)
        except Exception:
            pass
        P.pg.wait_for_timeout(100)
    return None


with sync_playwright() as p:
    b = p.chromium.launch()

    # ------------------------------------------------ 1. sleep with the usual signals (hidden ... visible)
    for tab in ("home", "files"):
        P = fresh(tab)
        vis(P, True); proxy.freeze(); mock.set(ext_t=222.0)
        P.pg.wait_for_timeout(4000)                     # the phone sleeps
        vis(P, False); t0 = time.time()
        t = answered_after(P, t0, "/api/printer", 30)
        ok(f"[{tab}: sleep + visible] data flowing again within 3 s of coming back", t is not None and t <= 3, t)
        if tab == "home":
            t = wait_for(P, lambda: "222.0" in hot(P), 5)
            ok("[home: sleep + visible] the new temperature is shown", t is not None and t <= 3, t)
            mock.set(ext_t=223.0)
            t2 = wait_for(P, lambda: "223.0" in hot(P), 5)
            ok("[home: sleep + visible] and it keeps following", t2 is not None and t2 <= 3, t2)
        ok(f"[{tab}: sleep + visible] no page errors", not errs(P), errs(P)[:2]); P.close()

    # ------------------------------------------------ 2. connections die, the page never learns it was away
    for tab in ("home", "files"):
        P = fresh(tab)
        proxy.freeze(); t0 = time.time()
        t = answered_after(P, t0, "/api/printer", 40)
        ok(f"[{tab}: dead connections, no signal] recovers by itself within 10 s", t is not None and t <= 10, t)
        ok(f"[{tab}: dead connections, no signal] no page errors", not errs(P), errs(P)[:2]); P.close()

    # ------------------------------------------------ 3. in the background: no traffic; coming back: at once
    P = fresh()
    vis(P, True); P.pg.wait_for_timeout(300); P.take_reqs()
    P.pg.wait_for_timeout(3000)
    polls = [r for r in P.take_reqs() if is_poll(r)]
    ok("[hidden] no polling while the page is hidden (3 s)", len(polls) <= 2, len(polls))
    mock.set(ext_t=230.0)
    vis(P, False)
    t = wait_for(P, lambda: "230.0" in hot(P), 3)
    ok("[hidden -> visible] refreshes at once (<= 0.8 s)", t is not None and t <= 0.8, t)
    ok("[hidden -> visible] no page errors", not errs(P), errs(P)[:2]); P.close()

    # ------------------------------------------------ 4. the clock jumps (timers were frozen): detected without any event
    P = fresh()
    P.pg.evaluate("() => { const real = Date.now.bind(Date); window.__off = 0; Date.now = () => real() + window.__off; }")
    P.pg.evaluate("() => { document.querySelector('iframe').dataset.mark = 'old'; }")
    P.take_reqs(); ws0 = P.pg.evaluate("() => __wsCount()")
    P.pg.evaluate("() => { window.__off = 30000; }")      # 30 s vanish
    P.pg.wait_for_timeout(2500)
    probes = [r for r in P.take_reqs() if r["m"] == "GET" and r["u"].startswith("/printer/info")]
    ok("[clock jump] noticed: connection check sent", len(probes) >= 4, len(probes))
    ok("[clock jump] camera view restarted (away 30 s)", P.pg.evaluate("() => document.querySelector('iframe').dataset.mark") is None)
    ok("[clock jump] console socket reopened", P.pg.evaluate("() => __wsCount()") == ws0 + 1, (ws0, P.pg.evaluate("() => __wsCount()")))
    ok("[clock jump] no page errors", not errs(P), errs(P)[:2]); P.close()

    # ------------------------------------------------ 5. short absence: nothing is torn down
    P = fresh()
    P.pg.evaluate("() => { document.querySelector('iframe').dataset.mark = 'old'; }")
    ws0 = P.pg.evaluate("() => __wsCount()")
    vis(P, True); P.pg.wait_for_timeout(1200); vis(P, False); P.pg.wait_for_timeout(1500)
    ok("[1 s away] console socket left alone", P.pg.evaluate("() => __wsCount()") == ws0)
    ok("[1 s away] camera left alone", P.pg.evaluate("() => document.querySelector('iframe').dataset.mark") == "old")
    ok("[1 s away] no new connection check storm", len([r for r in P.take_reqs() if r["u"].startswith("/printer/info")]) <= 8)
    P.close()

    # ------------------------------------------------ 6. the case light after a sleep
    P = fresh()
    vis(P, True); proxy.freeze(); mock.set(light=1)
    P.pg.wait_for_timeout(3500)
    vis(P, False)
    t = wait_for(P, lambda: P.pg.evaluate("() => document.querySelector('.light-btn').classList.contains('is-on')"), 15)
    ok("[light after sleep] shown on within 4 s", t is not None and t <= 4, t)
    P.pg.locator(".light-btn").click()
    t = wait_for(P, lambda: mock.gcode() and mock.gcode()[-1].lower() == "luci_off", 3)
    ok("[light after sleep] the button works", t is not None, t)
    P.close()

    b.close()
print("\nFAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
