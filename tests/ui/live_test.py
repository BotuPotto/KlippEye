"""Release 1.126: the dashboard stays connected by itself. Against the mock, with the watchdog's times shortened
(localStorage klippeye.live.scale = 0.1: «quiet» 1.5 s, reload after 4.5 s, away for long 60 s).
  - an answer that stops in the middle (headers and a piece, then nothing): the reads go on, no reload needed;
  - no answers at all while the printer's server still answers: «Reconnecting…», then the page reloads by itself;
  - the same with unsaved changes in the editor: never reloaded;
  - the printer does not answer at all: «The printer does not answer», no reload; back: the page comes back;
  - away for long (hidden): reloaded on coming back.
Usage: live_test.py <html> <outdir> <port>"""
import json
import os
import re
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
SCALE = 0.1


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


CURRENT = [None]   # the page whose events are pumped while waiting (the harness routes every request through Python)


def pause(seconds):
    if CURRENT[0] is not None:
        CURRENT[0].pg.wait_for_timeout(int(seconds * 1000))
    else:
        time.sleep(seconds)


def wait_until(fn, seconds=8.0):
    end = time.time() + seconds
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        pause(0.15)
    return False


def page(b, w=390, h=844):
    mock.reset()
    P = Page(b, mock, w, h, locale="it-IT")
    CURRENT[0] = P
    P.ctx.add_init_script("try { localStorage.setItem('klippeye.live.scale', '%s'); } catch (e) {}" % SCALE)
    P.goto("home", 1800)
    P.pg.evaluate("() => { window.__notReloaded = true; }")
    return P


def reloaded(P):
    return P.pg.evaluate("() => window.__notReloaded !== true")


def banner(P):
    strip = P.pg.locator("#live-banner")
    return strip.inner_text(timeout=1000) if strip.count() else ""


HANG = []   # requests held for ever by a route (a connection that never answers)
DEAD = re.compile(r".*/(api|printer|machine|access|server)/.*")


def hang(route):
    if "probe=" in route.request.url:   # the watchdog's own probe reaches the printer's server
        route.continue_()
        return
    HANG.append(route)   # never answered


with sync_playwright() as p:
    b = p.chromium.launch()

    # --- an answer stopped in the middle: the reads go on by themselves
    P = page(b)
    mock.set(stall_body=True)
    before = state()["printer_reads"]
    pause(14.0)
    during = state()["printer_reads"]
    ok("an answer stopped in the middle: the status keeps being asked (the stuck read is given up, not waited on for ever)",
       during - before >= 3, (before, during))
    mock.set(stall_body=False)
    ok("... answers again: the page goes on, never reloaded", wait_until(lambda: state()["printer_reads"] > during + 2, 8) and not reloaded(P))
    P.close()

    # --- nothing answers, but the printer's server does: reconnecting, then a reload
    P = page(b)
    P.pg.route(DEAD, hang)
    ok("no answers for a while: «Reconnecting…»", wait_until(lambda: "Riconnessione" in banner(P), 6), banner(P))
    P.shot(os.path.join(out, "live_reconnecting.png"), tall=False)
    ok("... still nothing, the printer's server answers: the page reloads by itself", wait_until(lambda: reloaded(P), 12))
    P.pg.unroute_all(behavior="ignoreErrors")
    HANG.clear()
    P.pg.wait_for_load_state()
    ok("... and it works again after the reload", wait_until(lambda: P.pg.locator(".app-header").count() == 1, 8))
    P.close()

    # --- unsaved changes: never reloaded
    P = page(b, 1280, 860)
    P.goto("config", 1800)
    P.pg.evaluate("() => { window.__notReloaded = true; }")
    P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^printer.cfg$"))).first.locator(".cfg-row__main").click()
    wait_until(lambda: P.pg.locator(".cm-content").count() == 1, 6)
    P.pg.locator(".cm-content").click()
    P.pg.keyboard.type("# a change not saved\n")
    P.pg.route(DEAD, hang)
    ok("unsaved changes in the editor: «Reconnecting…» but no reload", wait_until(lambda: "Riconnessione" in banner(P), 6) and (pause(7) or True) and not reloaded(P), banner(P))
    P.pg.unroute_all(behavior="ignoreErrors")
    HANG.clear()
    ok("... answers again: the strip goes, the change is still there", wait_until(lambda: banner(P) == "", 8) and "a change not saved" in P.pg.locator(".cm-content").inner_text())
    P.close()

    # --- the printer does not answer at all: said, no reload; back: the page comes back
    P = page(b)
    P.pg.route(re.compile(r".*/(api|printer|machine|access|server)/.*"), lambda route: route.abort())
    ok("the printer does not answer at all: «The printer does not answer», no reload",
       wait_until(lambda: "non risponde" in banner(P), 12) and not reloaded(P), banner(P))
    P.shot(os.path.join(out, "live_unreachable.png"), tall=False)
    P.pg.unroute_all(behavior="ignoreErrors")
    ok("... back: the page comes back (reloaded, or the reads resume) and the strip goes",
       wait_until(lambda: (reloaded(P) or banner(P) == "") and P.pg.locator(".app-header").count() == 1, 15), banner(P))
    P.close()

    # --- away for long: reloaded on coming back
    P = page(b)
    hide = "() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => %s }); document.dispatchEvent(new Event('visibilitychange')); }"
    P.pg.evaluate(hide % "true")
    pause(600 * SCALE + 3)
    P.pg.evaluate(hide % "false")
    ok("away for long: reloaded on coming back", wait_until(lambda: reloaded(P), 8))
    P.close()
    P = page(b)
    P.pg.evaluate(hide % "true")
    pause(2)
    P.pg.evaluate(hide % "false")
    pause(2)
    ok("away for a moment: not reloaded", not reloaded(P))
    P.close()
    b.close()

print("%d FAIL" % len(FAILS))
sys.exit(1 if FAILS else 0)
