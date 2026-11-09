"""The AI monitor's alarm in the print card and the AI panel of the badge (1.25.0, roadmap phase 6a).
Usage: ai_alarm_test.py <html> <outdir> <port>"""
import sys, os, json, time, urllib.request
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


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def wait_until(fn, timeout=8.0, step=0.15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn(): return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    try: return bool(fn())
    except Exception: return False


def start(b, tab="home", w=390, **st):
    mock.reset()
    if st: mock.set(**st)
    P = Page(b, mock, w, 844)
    CUR[0] = P
    P.goto(tab, 2500)
    return P


badge = lambda P: P.pg.locator("[data-ai-badge]")
question = lambda P: P.pg.locator("[data-ai-question]")

with sync_playwright() as p:
    b = p.chromium.launch()

    # ---------------------------------------------------------------- no print
    P = start(b, detector_status="idle - waiting for a print", has_analysis=False)
    ok("no print: the AI badge is there anyway, grey, and says it waits for a print", badge(P).count() == 1 and badge(P).get_attribute("data-ai-badge") == "idle" and "in attesa" in (badge(P).get_attribute("title") or ""))
    badge(P).click(); P.settle(600)
    ok("a tap on the badge opens the AI monitoring panel", P.pg.locator("[data-ai-panel]").count() == 1 and "Nessun allarme in questa stampa" in P.pg.locator("[data-ai-panel]").inner_text())
    P.shot_vp(out + "/panel_idle.png")
    P.pg.locator("[data-ai-settings]").click(); P.settle(700)
    ok("... its settings button leads to Settings → AI monitor", P.pg.locator("[data-ai-panel]").count() == 0 and P.pg.locator(".drawer__title").inner_text() == "Monitor IA")
    P.pg.keyboard.press("Escape"); P.settle(400)
    P.goto("config", 1500)
    ok("the Config page has no AI monitoring card any more", "Monitoraggio IA automatico" not in P.pg.locator(".app-main").inner_text() and P.pg.locator(".monitor-grid").count() == 0)
    P.close()

    # ---------------------------------------------------------------- a print with an alarm
    P = start(b, printing=True, detector_status="scanning", has_analysis=True, analysis_action="PAUSA")
    ok("an alarm during the print: the badge turns amber", wait_until(lambda: badge(P).get_attribute("data-ai-badge") == "on" and "PAUSA" in (badge(P).get_attribute("title") or "")), badge(P).get_attribute("title"))
    ok("... and the print card asks: is it a real problem? (with what the AI saw and its picture)", wait_until(lambda: question(P).count() == 1) and "Il monitor IA ha visto un problema" in question(P).inner_text() and "Spaghetti" in question(P).inner_text() and question(P).locator("[data-zoom]").count() == 1 and question(P).locator("[data-ai-answer]").count() == 3)
    P.shot_vp(out + "/question.png")
    question(P).locator("[data-zoom]").click(); P.settle(500)
    ok("the picture opens over the whole screen", P.pg.locator("[data-photo-open]").count() == 1 and "Cosa ha visto il monitor IA" in P.pg.locator("[data-photo-open]").inner_text())
    box = P.pg.locator(".photo-viewer").bounding_box(); img = P.pg.locator(".photo-viewer__stage img").bounding_box()
    vw, vh = P.pg.viewport_size["width"], P.pg.viewport_size["height"]
    ok("1.67: ... edge to edge, black, the picture as large as the screen allows (turned on an upright phone)", box["width"] == vw and box["height"] == vh and abs(max(img["width"], img["height"]) - vh) < 2 and P.pg.locator('.photo-viewer[data-rotated="true"]').count() == 1, (box, img))
    P.pg.mouse.click(vw / 2, vh / 2); P.settle(400)
    hidden = P.pg.locator(".photo-viewer.is-controls").count() == 0
    P.pg.mouse.click(vw / 2, vh / 2); P.settle(400)
    ok("1.67: ... a tap hides the buttons, another shows them", hidden and P.pg.locator(".photo-viewer.is-controls").count() == 1)
    P.pg.locator("[data-photo-size]").click(); P.settle(300)
    ok("... «Dimensione reale» shows it at its real size", P.pg.locator(".photo-viewer__stage.is-real").count() == 1)
    ok("... the phone's back closes it", P.pg.evaluate("() => window.klippeyeBack()") is True and (P.settle(400) or True) and P.pg.locator("[data-photo-open]").count() == 0)
    question(P).locator('[data-ai-answer="false"]').click(); P.settle(600)
    ok("«Falso allarme»: the question goes, the answer reaches the Raspberry", question(P).count() == 0 and state()["ai_answers"] == ["false"], state()["ai_answers"])
    ok("... and the badge is green until the next alarm", wait_until(lambda: "Monitoraggio OK" in (badge(P).get_attribute("title") or "")), badge(P).get_attribute("title"))
    badge(P).click(); P.settle(600)
    ok("the panel says it was marked as a false alarm, with the picture to enlarge", "falso allarme" in P.pg.locator("[data-ai-panel]").inner_text() and P.pg.locator("[data-ai-panel] [data-zoom]").count() == 1)
    P.shot_vp(out + "/panel_answered.png")
    P.pg.keyboard.press("Escape"); P.settle(400)
    ok("Escape closes the panel", P.pg.locator("[data-ai-panel]").count() == 0)
    P.close()

    P = start(b, printing=True, detector_status="scanning", has_analysis=True, analysis_action="CANCELLA")
    ok("a CANCEL alarm: red badge, the question in red", wait_until(lambda: question(P).count() == 1) and "ai-question--danger" in question(P).get_attribute("class") and "ANNULLA" in (badge(P).get_attribute("title") or "").upper())
    question(P).locator('[data-ai-answer="right"]').click(); P.settle(600)
    ok("«Problema reale»: it stays, says to pause or cancel if needed, the badge stays red", question(P).get_attribute("data-ai-question") == "answered" and "metti in pausa o annulla" in question(P).inner_text() and "ANNULLA" in (badge(P).get_attribute("title") or "").upper() and state()["ai_answers"] == ["right"])
    # the print ends: the backend closes the alarm
    mock.set(has_analysis=False, detector_status="idle - waiting for a print", printing=False)
    ok("the print ends (the backend closes the alarm): no question, grey badge", wait_until(lambda: badge(P).get_attribute("data-ai-badge") == "idle"))
    P.pg.reload(); P.pg.wait_for_timeout(2500)
    ok("... and nothing comes back after a reload (no old verdict kept in the browser)", badge(P).get_attribute("data-ai-badge") == "idle" and question(P).count() == 0)
    P.close()

    # «Ignora» and the desktop layout
    P = start(b, w=1440, printing=True, detector_status="scanning", has_analysis=True, analysis_action="PAUSA")
    ok("desktop: the question is in the print card too", wait_until(lambda: question(P).count() == 1))
    question(P).locator('[data-ai-answer="ignore"]').click(); P.settle(600)
    ok("«Ignora»: gone, green badge", question(P).count() == 0 and wait_until(lambda: "Monitoraggio OK" in (badge(P).get_attribute("title") or "")) and state()["ai_answers"] == ["ignore"])
    ok("1.67 desktop: no AI strip under the camera any more (the badge says the same)", P.pg.locator(".desk-ai").count() == 0)
    badge(P).click(); P.settle(600)
    ok("desktop: the badge opens the AI panel", P.pg.locator("[data-ai-panel]").count() == 1)
    ok("no errors in the page", not P.errors, P.errors[:3])
    P.close()

    P = start(b, w=320, printing=True, detector_status="scanning", has_analysis=True, analysis_action="PAUSA")
    wait_until(lambda: question(P).count() == 1)
    wide = P.pg.evaluate("() => document.documentElement.scrollWidth")
    ok("320 px: the question fits", wide <= 320, wide)
    P.shot_vp(out + "/question_320.png")
    P.close()
    b.close()

print("\nFAILED: %d %s" % (len(FAILS), FAILS) if FAILS else "\nALL PASS")
sys.exit(1 if FAILS else 0)
