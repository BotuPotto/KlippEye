"""The case-light toggle against a slow Klipper: it must go to the wanted state at once and STAY there (no
on -> off -> on flicker from readings that started before the tap), give up cleanly when Klipper does not follow, and
follow changes made elsewhere. Usage: light_test.py <html> <outdir> <port> [--repro]  (--repro: print only)"""
import sys, os, re, json, time
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
REPRO = "--repro" in sys.argv
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
FAILS = []

OBSERVE = """() => { window.__lt = []; const b = document.querySelector('.light-btn'); const t0 = performance.now();
  const rec = () => { const on = b.classList.contains('is-on'); const l = window.__lt; if (!l.length || l[l.length-1][1] !== on) l.push([Math.round(performance.now() - t0), on]); };
  rec(); new MutationObserver(rec).observe(b, {attributes: true, attributeFilter: ['class']}); }"""


def ok(name, cond, extra=""):
    if not cond and not REPRO: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra != "" else ""))


def fresh(w=390, h=844, wait=2000, **state):
    mock.reset()
    if state: mock.set(**state)
    P = Page(b, mock, w, h)
    P.goto("home", wait)
    P.pg.evaluate(OBSERVE)
    return P


def seq(P): return P.pg.evaluate("() => window.__lt")
def states(P): return [s for _, s in seq(P)]
def cmds(): return [c for c, _ in mock.get_state().get("light_cmds", [])] if hasattr(mock, "get_state") else None
def real_light(): return json.loads(__import__("urllib.request").request.urlopen(mock.base + "/__mock/state").read())["light"]
def light_cmds(): return [c[0] for c in json.loads(__import__("urllib.request").request.urlopen(mock.base + "/__mock/state").read())["light_cmds"]]
def errs(P): return [e for e in P.errors if "pageerror" in e or "console.error" in e]
def btn(P): return P.pg.locator(".light-btn")
def flag(P, cls): return P.pg.evaluate("(c) => document.querySelector('.light-btn').classList.contains(c)", cls)


with sync_playwright() as p:
    b = p.chromium.launch()

    # ---------------------------------------------------------------- everything instant
    P = fresh()
    btn(P).click(); P.pg.wait_for_timeout(2500)
    ok("[fast] on: goes on once, stays on", states(P) == [False, True], seq(P))
    ok("[fast] one luci_on sent, real light on", light_cmds() == ["luci_on"] and real_light() == 1, (light_cmds(), real_light()))
    btn(P).click(); P.pg.wait_for_timeout(2500)
    ok("[fast] off: goes off once", states(P) == [False, True, False] and light_cmds() == ["luci_on", "luci_off"], (seq(P), light_cmds()))
    ok("[fast] no page errors", not errs(P), errs(P)[:2]); P.close()

    # ---------------------------------------------------------------- slow reads, macro takes 1.2 s, command answers at once
    for label, state in (("slow reads", dict(light_read_delay=0.8, light_exec_delay=1.2, light_block=False)),
                         ("slow macro, command waits (Moonraker style)", dict(light_read_delay=0.6, light_exec_delay=2.0, light_block=True)),
                         ("very slow reads", dict(light_read_delay=1.6, light_exec_delay=0.5, light_block=False))):
        P = fresh(**state)
        P.pg.wait_for_timeout(700)
        btn(P).click(); P.pg.wait_for_timeout(7000)
        ok(f"[{label}] turning ON: on once, no flicker", states(P) == [False, True], seq(P))
        ok(f"[{label}] real light on and still shown on", real_light() == 1 and flag(P, "is-on"))
        P.pg.screenshot(path=f"{out}/slow_on_{re.sub('[^a-z]+', '_', label)[:12]}.png", animations="disabled")
        P.pg.evaluate(OBSERVE)
        btn(P).click(); P.pg.wait_for_timeout(7000)
        ok(f"[{label}] turning OFF: off once, no flicker", states(P) == [True, False], seq(P))
        ok(f"[{label}] real light off and still shown off", real_light() == 0 and not flag(P, "is-on"))
        ok(f"[{label}] no page errors", not errs(P), errs(P)[:2]); P.close()

    # ---------------------------------------------------------------- tap while a reading is in flight, repeated: never flickers
    bad = 0
    for k in range(6):
        P = fresh(wait=1500, light_read_delay=0.7, light_exec_delay=0.9, light_block=False)
        P.pg.wait_for_timeout(120 * k)          # land the tap at different moments of the 500 ms polling cycle
        btn(P).click(); P.pg.wait_for_timeout(4500)
        if states(P) != [False, True]: bad += 1; print("   flicker at offset", 120 * k, seq(P))
        P.close()
    ok("[tap at 6 different moments of the polling cycle] never flickers", bad == 0, bad)

    # ---------------------------------------------------------------- three quick taps on / off / on
    P = fresh(light_read_delay=0.5, light_exec_delay=0.8, light_block=True)
    for _ in range(3):
        btn(P).click(); P.pg.wait_for_timeout(110)
    P.pg.wait_for_timeout(7000)
    ok("[3 quick taps] shows what the taps asked, then holds on", states(P) == [False, True, False, True], seq(P))
    ok("[3 quick taps] Klipper ends on, last command luci_on", real_light() == 1 and light_cmds()[-1] == "luci_on", (real_light(), light_cmds()))
    ok("[3 quick taps] commands never more than the taps", len(light_cmds()) <= 3, light_cmds())
    ok("[3 quick taps] no page errors", not errs(P), errs(P)[:2]); P.close()

    # ---------------------------------------------------------------- Klipper does not follow: the toggle gives up and says so
    P = fresh(light_fail=True, light_exec_delay=0.3, light_block=True)
    t0 = time.time(); btn(P).click(); P.pg.wait_for_timeout(700)
    ok("[no response] shows the wish while waiting", flag(P, "is-on") and flag(P, "is-waiting"), (flag(P, "is-on"), flag(P, "is-waiting")))
    P.pg.screenshot(path=f"{out}/waiting.png", animations="allow")
    P.pg.wait_for_timeout(5500)
    ok("[no response] goes back to off after a few seconds", states(P) == [False, True, False] and not flag(P, "is-waiting"), seq(P))
    ok("[no response] says so", "non ha risposto" in " ".join(P.pg.locator(".toast").all_inner_texts()).lower() or P.pg.locator(".toast--notice.is-visible").count() == 1, P.pg.locator(".toast").all_inner_texts())
    P.pg.wait_for_timeout(3000)
    ok("[no response] the failure is flagged for the shake", P.pg.get_attribute(".light-btn", "data-fail") == "odd", P.pg.get_attribute(".light-btn", "data-fail"))
    ok("[no response] stays off (no bouncing afterwards)", states(P) == [False, True, False], seq(P))
    ok("[no response] button usable again", (btn(P).click(), P.pg.wait_for_timeout(200), flag(P, "is-on"))[2])
    P.pg.wait_for_timeout(800)   # let that last command end before the next scenario resets the mock
    ok("[no response] no page errors", not errs(P), errs(P)[:2]); P.close()

    # ---------------------------------------------------------------- changes made elsewhere are followed
    P = fresh()
    ok("[elsewhere] starts off", states(P) == [False], seq(P))
    mock.set(light=1); P.pg.wait_for_timeout(3000)
    ok("[elsewhere] light turned on elsewhere -> shown on", flag(P, "is-on"), seq(P))
    mock.set(light=0); P.pg.wait_for_timeout(3000)
    ok("[elsewhere] turned off elsewhere -> shown off", not flag(P, "is-on") and states(P) == [False, True, False], seq(P))
    ok("[elsewhere] no command was sent by the dashboard", light_cmds() == [], light_cmds()); P.close()

    # ---------------------------------------------------------------- the polling does not pile up requests
    P = fresh(wait=1500, light_read_delay=0.9)
    r0 = json.loads(__import__("urllib.request").request.urlopen(mock.base + "/__mock/state").read())["light_reads"]
    P.pg.wait_for_timeout(6000)
    r1 = json.loads(__import__("urllib.request").request.urlopen(mock.base + "/__mock/state").read())["light_reads"]
    ok("[polling] with 0.9 s answers, at most one reading at a time (<= 7 in 6 s)", (r1 - r0) <= 7, r1 - r0)
    P.close()

    # ---------------------------------------------------------------- wide layout (button over the camera)
    P = fresh(1440, 900, light_read_delay=0.7, light_exec_delay=1.0, light_block=False)
    P.pg.wait_for_timeout(500)
    btn(P).click(); P.pg.wait_for_timeout(6000)
    ok("[wide] on once, no flicker", states(P) == [False, True] and real_light() == 1, seq(P))
    P.pg.screenshot(path=f"{out}/wide_on.png", animations="disabled")
    ok("no page errors (wide)", not errs(P), errs(P)[:2]); P.close()

    b.close()
print("\nFAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
