"""Checks the motion layer (One UI animations): layers come in and go out, the tab marker slides, pages rise, sections
fold, nothing keeps animating at rest, 'reduce motion' is honoured. Usage: motion_test.py <html> <outdir> <port>"""
import sys, os, re, json
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
FAILS = []


def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra != "" else ""))


def fresh(w=390, h=844, tab="home", wait=1800, reduced=False, **state):
    mock.reset()
    if state: mock.set(**state)
    P = Page(b, mock, w, h)
    if reduced: P.pg.emulate_media(reduced_motion="reduce")
    P.goto(tab, wait)
    return P


def errs(P): return [e for e in P.errors if "pageerror" in e or "console.error" in e]
def anims(P): return P.pg.evaluate("() => document.getAnimations().map(a => ({n: a.animationName || a.transitionProperty || '', t: a.constructor.name}))")
def cs(P, sel, prop): return P.pg.evaluate("([s, p]) => { const e = document.querySelector(s); return e ? getComputedStyle(e)[p] : null }", [sel, prop])
def num(x):
    try: return float(x)
    except Exception: return None


with sync_playwright() as p:
    b = p.chromium.launch()

    # ------------------------------------------------------------------ tokens
    P = fresh()
    tok = P.pg.evaluate("() => { const s = getComputedStyle(document.documentElement); return ['--oui-ease','--oui-dur-press','--oui-dur-fast','--oui-dur-base','--oui-dur-slow','--oui-dur-exit','--oui-dur-bar'].map(k => s.getPropertyValue(k).trim()) }")
    ok("tokens: One UI basic curve and 100–500 ms", tok[0] == "cubic-bezier(0.22, 0.25, 0, 1)" and tok[1:] == ["100ms", "150ms", "250ms", "350ms", "150ms", "450ms"], tok)
    P.close()

    # ------------------------------------------------------------------ a layer comes in and goes out (phone)
    P = fresh()
    P.pg.locator("[aria-label='Save config']").click()
    P.pg.wait_for_timeout(30)
    ok("dialog enter: scrim fades, card pops (animations running)", cs(P, ".confirm-overlay", "animationName") == "oui-fade" and cs(P, ".confirm-card", "animationName") == "oui-pop", (cs(P, ".confirm-overlay", "animationName"), cs(P, ".confirm-card", "animationName")))
    op = num(cs(P, ".confirm-overlay", "opacity"))
    ok("dialog enter: starts transparent, not yet opaque at 30 ms", op is not None and op < 0.9, op)
    tr = cs(P, ".confirm-card", "transform")
    ok("dialog enter: card is still scaling/rising at 30 ms", tr not in (None, "none", "matrix(1, 0, 0, 1, 0, 0)"), tr)
    P.pg.screenshot(path=f"{out}/dialog_in_30ms.png", animations="allow")
    P.pg.wait_for_timeout(600)
    ok("dialog enter: settled (no transform left, opaque)", num(cs(P, ".confirm-overlay", "opacity")) == 1 and cs(P, ".confirm-card", "transform") in ("none", "matrix(1, 0, 0, 1, 0, 0)"))
    ok("wrapper has no box and no effect on layout", cs(P, ".oui-presence", "display") == "contents")
    P.pg.locator(".confirm-card .oui-btn").first.click()
    P.pg.wait_for_timeout(40)
    ok("dialog exit: still there, marked leaving, taps ignored", P.pg.locator("[data-presence=leaving] .confirm-overlay").count() == 1 and cs(P, ".confirm-overlay", "pointerEvents") == "none")
    ok("dialog exit: plays the exit animation", cs(P, ".confirm-overlay", "animationName") == "oui-fade-out" and cs(P, ".confirm-card", "animationName") == "oui-pop-out", (cs(P, ".confirm-overlay", "animationName"), cs(P, ".confirm-card", "animationName")))
    P.pg.screenshot(path=f"{out}/dialog_out_40ms.png", animations="allow")
    P.pg.wait_for_timeout(400)
    ok("dialog exit: gone from the DOM afterwards (page back to its normal DOM)", P.pg.locator(".confirm-overlay").count() == 0 and P.pg.locator(".oui-presence").count() == 0)
    # open again right after closing (while the exit may still run) -> works, single overlay
    P.pg.locator("[aria-label='Save config']").click(); P.pg.wait_for_timeout(60)
    P.pg.locator(".confirm-card .oui-btn").first.click(); P.pg.wait_for_timeout(30)
    P.pg.locator("[aria-label='Save config']").click(); P.pg.wait_for_timeout(500)
    ok("reopening during the exit: exactly one dialog, interactive", P.pg.locator(".confirm-overlay").count() == 1 and P.pg.locator("[data-presence=leaving]").count() == 0 and cs(P, ".confirm-overlay", "pointerEvents") != "none")
    P.pg.locator(".confirm-card .oui-btn").first.click(); P.pg.wait_for_timeout(400)
    ok("no page errors (dialogs)", not errs(P), errs(P)[:3]); P.close()

    # ------------------------------------------------------------------ input dialog (temperature) and the bed under it
    P = fresh()
    P.pg.locator("button.heater-tile").first.click(); P.pg.wait_for_timeout(500)
    ok("temperature dialog opens in a .modal with a card", P.pg.locator(".modal .modal-card").count() == 1)
    ok("the highest temperature is Klipper's ([extruder] max_temp 285), not a fixed 300", P.pg.locator(".modal input").get_attribute("max") == "285", P.pg.locator(".modal input").get_attribute("max"))
    P.pg.locator(".modal .dialog-close").click(); P.pg.wait_for_timeout(40)
    ok("temperature dialog leaves with an animation first", P.pg.locator("[data-presence=leaving] .modal").count() == 1)
    P.pg.wait_for_timeout(350)
    ok("…and is then removed", P.pg.locator(".modal").count() == 0)
    ok("no page errors (temperature)", not errs(P), errs(P)[:3]); P.close()

    # ------------------------------------------------------------------ tab change: marker slides, cards rise
    P = fresh()
    pos0 = P.pg.evaluate("() => document.querySelector('.bottom-nav__pill').getBoundingClientRect().x")
    ok("nav: marker sits under the active tab", abs(pos0 - P.pg.locator(".bottom-nav__tab.is-active").bounding_box()["x"]) < 1.0, (pos0, P.pg.locator(".bottom-nav__tab.is-active").bounding_box()))
    P.pg.locator(".bottom-nav__tab[data-tab=sistema]").click(); P.pg.wait_for_timeout(120)
    mid = P.pg.evaluate("() => document.querySelector('.bottom-nav__pill').getBoundingClientRect().x")
    tgt = P.pg.locator(".bottom-nav__tab[data-tab=sistema]").bounding_box()["x"]
    ok("nav: marker is travelling at 120 ms (between old and new tab)", pos0 < mid < tgt, (pos0, mid, tgt))
    P.pg.wait_for_timeout(450)
    end = P.pg.evaluate("() => document.querySelector('.bottom-nav__pill').getBoundingClientRect().x")
    ok("nav: marker arrives exactly under the new tab", abs(end - tgt) < 1.0, (end, tgt))
    pill = P.pg.evaluate("() => { const e = document.querySelector('.bottom-nav__pill').getBoundingClientRect(), t = document.querySelector('.bottom-nav__tab.is-active').getBoundingClientRect(); return [e.width - t.width, e.height - t.height, e.y - t.y] }")
    ok("nav: marker has the size of the tab", all(abs(v) < 1.0 for v in pill), pill)
    P.pg.locator(".bottom-nav__tab[data-tab=config]").click(); P.pg.wait_for_timeout(60)
    run = anims(P)
    ok("page change: cards of the new page are animating in", any(a["n"] in ("oui-rise", "oui-fade") for a in run), run[:6])
    P.pg.screenshot(path=f"{out}/page_in_60ms.png", animations="allow")
    P.pg.wait_for_timeout(900)
    left = [a for a in anims(P) if a["t"] == "CSSAnimation" and a["n"] not in ("oui-pulse", "vz-spin", "oui-spin")]
    ok("page change: all entrance animations are over after 0.9 s", not left, left)
    ok("no page errors (tabs)", not errs(P), errs(P)[:3]); P.close()

    # ------------------------------------------------------------------ nothing keeps moving at rest (no card re-mounts on every poll)
    for tab, state in (("home", {}), ("home", {"printing": True}), ("controllo", {}), ("files", {}), ("sistema", {})):
        P = fresh(tab=tab, wait=2500, **state)
        P.pg.evaluate("() => { window.__anim = 0; document.addEventListener('animationstart', e => { if (!/pulse|spin/.test(e.animationName)) window.__anim++ }, true) }")
        P.pg.wait_for_timeout(7000)
        n = P.pg.evaluate("() => window.__anim")
        ok(f"at rest [{tab}{' printing' if state else ''}]: no animation starts during 7 s of polling", n == 0, n)
        P.close()

    # ------------------------------------------------------------------ a section unfolds
    P = fresh(tab="controllo")
    head = P.pg.locator(".endstops-head")
    ok("endstops: wrapper present while folded, nothing inside", P.pg.locator(".oui-collapse:not(.is-open) .oui-collapse__inner").count() >= 1 and P.pg.locator(".endstops-body").count() == 0)
    head.click(); P.pg.wait_for_timeout(110)
    h_mid = P.pg.evaluate("() => document.querySelector('.endstops .oui-collapse').getBoundingClientRect().height")
    P.pg.wait_for_timeout(600)
    h_full = P.pg.evaluate("() => document.querySelector('.endstops .oui-collapse').getBoundingClientRect().height")
    ok("endstops: height grows smoothly (mid < full)", 0 < h_mid < h_full, (h_mid, h_full))
    ok("endstops: content shown after unfolding", P.pg.locator(".endstops-body").count() == 1)
    head.click(); P.pg.wait_for_timeout(110)
    h_mid2 = P.pg.evaluate("() => document.querySelector('.endstops .oui-collapse').getBoundingClientRect().height")
    ok("endstops: folding shrinks smoothly (content still there)", 0 < h_mid2 < h_full and P.pg.locator(".endstops-body").count() == 1, (h_mid2, h_full))
    P.pg.wait_for_timeout(600)
    ok("endstops: folded again, content removed, height 0", P.pg.locator(".endstops-body").count() == 0 and P.pg.evaluate("() => document.querySelector('.endstops .oui-collapse').getBoundingClientRect().height") == 0)
    ok("no page errors (collapse)", not errs(P), errs(P)[:3]); P.close()

    # ------------------------------------------------------------------ menu grows out of its button, editor slides up
    P = fresh(tab="config")
    P.pg.locator("button:has-text('Nuovo')").click(); P.pg.wait_for_timeout(30)
    ok("menu: grows (scale animation) and fades", "oui-menu-in" in cs(P, ".oui-menu", "animationName") and num(cs(P, ".oui-menu", "opacity")) is not None and num(cs(P, ".oui-menu", "opacity")) < 1)
    P.pg.wait_for_timeout(500)
    P.pg.keyboard.press("Escape"); P.pg.wait_for_timeout(40)
    ok("menu: leaves with a fade first", P.pg.locator("[data-presence=leaving] .oui-menu").count() == 1)
    P.pg.wait_for_timeout(300)
    ok("menu: removed", P.pg.locator(".oui-menu").count() == 0)
    P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^notes.txt$"))).locator(".cfg-row__main").click(); P.pg.wait_for_timeout(40)
    ok("editor: slides up while fading in", "oui-layer-in" in cs(P, ".screen--editor", "animationName"), cs(P, ".screen--editor", "animationName"))
    P.pg.wait_for_timeout(900)
    P.pg.locator(".editor-close").click(); P.pg.wait_for_timeout(40)
    ok("editor: leaves with its exit animation", P.pg.locator("[data-presence=leaving] .screen--editor").count() == 1 and "oui-layer-out" in cs(P, ".screen--editor", "animationName"))
    P.pg.wait_for_timeout(300)
    ok("editor: removed", P.pg.locator(".screen--editor").count() == 0)
    ok("no page errors (menu/editor)", not errs(P), errs(P)[:3]); P.close()

    # ------------------------------------------------------------------ reduce motion
    P = fresh(reduced=True)
    tok = P.pg.evaluate("() => ['--oui-dur-press','--oui-dur-base','--oui-dur-slow','--oui-dur-exit','--oui-stagger'].map(k => getComputedStyle(document.documentElement).getPropertyValue(k).trim())")
    ok("reduce motion: every time collapses to 1 ms", tok == ["1ms", "1ms", "1ms", "1ms", "0ms"], tok)
    P.pg.locator("[aria-label='Save config']").click(); P.pg.wait_for_timeout(120)
    ok("reduce motion: dialog is complete after 120 ms", num(cs(P, ".confirm-overlay", "opacity")) == 1 and cs(P, ".confirm-card", "transform") in ("none", "matrix(1, 0, 0, 1, 0, 0)"))
    P.pg.locator(".confirm-card .oui-btn").first.click(); P.pg.wait_for_timeout(300)
    ok("reduce motion: still works (closes)", P.pg.locator(".confirm-overlay").count() == 0)
    ok("no page errors (reduced)", not errs(P), errs(P)[:3]); P.close()

    # ------------------------------------------------------------------ wide layout
    P = fresh(1440, 900)
    x0 = P.pg.evaluate("() => document.querySelector('.header-tabs__pill').getBoundingClientRect().x")
    tab0 = P.pg.locator(".header-tabs__tab.is-active").bounding_box()
    ok("header tabs: marker under the active tab", abs(x0 - tab0["x"]) < 1.0, (x0, tab0))
    P.pg.locator(".header-tabs__tab", has_text="Sistema").click(); P.pg.wait_for_timeout(120)
    xm = P.pg.evaluate("() => document.querySelector('.header-tabs__pill').getBoundingClientRect().x")
    t1 = P.pg.locator(".header-tabs__tab", has_text="Sistema").bounding_box()
    ok("header tabs: marker is travelling at 120 ms", x0 < xm < t1["x"], (x0, xm, t1["x"]))
    P.pg.wait_for_timeout(500)
    xe = P.pg.evaluate("() => { const r = document.querySelector('.header-tabs__pill').getBoundingClientRect(); return [r.x, r.width] }")
    t1 = P.pg.locator(".header-tabs__tab.is-active").bounding_box()
    ok("header tabs: marker lands on the new tab, same width", abs(xe[0] - t1["x"]) < 1.0 and abs(xe[1] - t1["width"]) < 1.0, (xe, t1))
    P.pg.set_viewport_size({"width": 1200, "height": 900}); P.pg.wait_for_timeout(500)
    xr = P.pg.evaluate("() => { const r = document.querySelector('.header-tabs__pill').getBoundingClientRect(); return [r.x, r.width] }")
    t2 = P.pg.locator(".header-tabs__tab.is-active").bounding_box()
    ok("header tabs: marker follows after a resize", abs(xr[0] - t2["x"]) < 1.0 and abs(xr[1] - t2["width"]) < 1.0, (xr, t2))
    P.pg.locator(".header-tabs__tab", has_text="Dispositivo").click(); P.pg.wait_for_timeout(900)
    P.pg.locator(".desk-dock__expand").click(); P.pg.wait_for_timeout(30)
    ok("console drawer: rises while fading in", "oui-rise" in cs(P, ".desk-drawer", "animationName"), cs(P, ".desk-drawer", "animationName"))
    P.pg.wait_for_timeout(500)
    P.pg.locator(".desk-dock__expand").click(); P.pg.wait_for_timeout(40)
    ok("console drawer: leaves with a fade", P.pg.locator("[data-presence=leaving] .desk-drawer").count() == 1)
    P.pg.wait_for_timeout(300)
    ok("console drawer: removed", P.pg.locator(".desk-drawer").count() == 0)
    P.pg.locator(".header-tabs__tab", has_text="File").click(); P.pg.wait_for_timeout(1500)
    P.pg.locator(".desk-col--files .file-card").nth(1).click(); P.pg.wait_for_timeout(40)
    ok("file detail: cross-fades when another file is picked", cs(P, ".desk-detail", "animationName") == "oui-fade", cs(P, ".desk-detail", "animationName"))
    ok("no page errors (wide)", not errs(P), errs(P)[:3]); P.close()

    b.close()
print("\nFAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
