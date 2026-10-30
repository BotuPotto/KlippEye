"""The guided set-up, the "?" guides and the settings menu in groups (1.22.0, roadmap phase 5e).
Usage: setup_test.py <html> <outdir> <port>"""
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


def stored():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/db").read())["db"].get("klippeye/settings") or {}


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


def open_page(b, offer=True, reset=True, width=390, height=844, **st):
    if reset: mock.reset()
    if st: mock.set(**st)
    P = Page(b, mock, width, height, offer_setup=offer)
    CUR[0] = P
    P.pg.goto(mock.base + "/"); P.pg.wait_for_timeout(2500)
    return P


def step_id(P):
    return P.pg.locator("[data-setup-step]").get_attribute("data-setup-step")


with sync_playwright() as p:
    b = p.chromium.launch()

    # ------------------------------------------------------------------ a new installation
    P = open_page(b)
    ok("new installation: the guided set-up opens by itself on the welcome", wait_until(lambda: P.pg.locator(".setup").count() == 1) and step_id(P) == "welcome" and "Benvenuto in KlippEye" in P.pg.locator(".setup").inner_text())
    ok("... it says how many steps there are, and has «Salta la guida»", "Passo 1 di 9" in P.pg.locator(".setup__head").inner_text() and P.pg.locator("[data-setup-skip-all]").count() == 1)
    P.shot_vp(out + "/welcome.png")
    order = []
    for _ in range(8):
        P.pg.locator("[data-setup-next]").click(); P.settle(700)
        order.append(step_id(P))
    ok("the steps, in order: name, camera, addresses, functions, notifications, AI, password, ready", order == ["printer", "camera", "network", "functions", "notifications", "ai", "access", "done"], order)
    ok("the last step sums up each part (done / to do / optional) and offers «Fine»", P.pg.locator("[data-setup-summary]").count() == 7 and P.pg.locator('[data-setup-summary="functions"]').get_attribute("data-status") == "todo" and P.pg.locator('[data-setup-summary="network"]').get_attribute("data-status") == "optional" and P.pg.locator("[data-setup-finish]").count() == 1)
    P.shot_vp(out + "/summary.png")
    P.pg.locator('[data-setup-summary="camera"]').click(); P.settle(600)
    ok("... a part of the summary leads back to its step", step_id(P) == "camera")
    ok("the camera step shows the preview over the camera settings", P.pg.locator(".setup-camera").count() == 1 and P.pg.locator(".setup .set-group").count() >= 3)
    P.pg.locator(".setup .drawer__help").click(); P.settle(600)
    ok("«?» in the set-up opens the guide of that step (camera), over it", P.pg.locator('[data-help-open="camera"]').count() == 1 and "Quale metodo" in P.pg.locator(".help-sheet").inner_text())
    P.pg.keyboard.press("Escape"); P.settle(500)
    ok("Escape closes the guide only, the set-up stays", P.pg.locator(".help-sheet").count() == 0 and P.pg.locator(".setup").count() == 1)
    P.pg.locator("[data-setup-back]").click(); P.settle(500)
    ok("«Indietro» goes back one step", step_id(P) == "printer")
    P.pg.reload(); P.pg.wait_for_timeout(2500)
    ok("a reload does not open it again by itself (it was offered on this device)", P.pg.locator(".setup").count() == 0)
    P.pg.click('button[aria-label="Impostazioni"]'); P.pg.wait_for_selector(".drawer"); P.settle(500)
    guide = P.pg.locator('.set-entry[data-page="setup"]')
    ok("the menu starts with «Configurazione guidata», marked «Avvia» while it is not done", guide.count() == 1 and "Avvia" in guide.inner_text())
    guide.click(); P.settle(800)
    ok("... it opens the set-up again where it was left (Nome e logo)", P.pg.locator(".setup").count() == 1 and P.pg.locator(".drawer").count() == 0 and step_id(P) == "printer")
    while P.pg.locator("[data-setup-next]").count(): P.pg.locator("[data-setup-next]").click(); P.settle(300)
    P.pg.locator("[data-setup-finish]").click(); P.settle(1500)
    ok("«Fine»: closed, and saved as done on the Raspberry (for every device)", P.pg.locator(".setup").count() == 0 and wait_until(lambda: stored().get("setup", {}).get("done") is True), stored().get("setup"))
    P.close()

    P = open_page(b, reset=False)
    ok("another device of the same installation: not shown again", P.pg.locator(".setup").count() == 0)
    P.close()

    # skipped
    P = open_page(b)
    P.pg.locator("[data-setup-skip-all]").click(); P.settle(1200)
    ok("«Salta la guida»: closed, and not shown by itself any more (done on the Raspberry)", P.pg.locator(".setup").count() == 0 and wait_until(lambda: stored().get("setup", {}).get("done") is True))
    P.close()

    # an installation of a release before 1.22: settings saved already, without "setup"
    mock.reset()
    req = urllib.request.Request(mock.base + "/server/database/item", data=json.dumps({"namespace": "klippeye", "key": "settings", "value": {"printer": {"brand": "vzbot", "name": "VzBot.287"}, "language": "it", "_t": 1}}).encode(), headers={"content-type": "application/json"}, method="POST")
    urllib.request.urlopen(req).read()
    P = open_page(b, reset=False)
    ok("an installation already set up (settings saved by an older release): the guide is not forced on it", P.pg.locator(".setup").count() == 0)
    P.pg.click('button[aria-label="Impostazioni"]'); P.pg.wait_for_selector(".drawer"); P.settle(500)
    ok("... the menu offers it without the «Avvia» badge", "Avvia" not in P.pg.locator('.set-entry[data-page="setup"]').inner_text())

    # ------------------------------------------------------------------ the menu in groups
    groups = P.pg.locator("[data-group]").evaluate_all("els => els.map(e => [e.dataset.group, [...e.querySelectorAll('[data-page]')].map(x => x.dataset.page)])")
    ok("the menu in four groups: printer / camera and AI / phone and network / system", groups == [["printer", ["printer", "functions", "zoffset"]], ["watch", ["camera", "ai"]], ["phone", ["notifications", "network"]], ["system", ["access", "software", "language"]]], groups)
    P.shot(out + "/menu.png")
    P.pg.locator(".drawer__help").click(); P.settle(500)
    ok("«?» on the menu: how the settings work", P.pg.locator('[data-help-open="home"]').count() == 1 and "Salvate sul Raspberry" in P.pg.locator(".help-sheet").inner_text())
    P.pg.locator(".help-sheet .drawer__btn").click(); P.settle(400)

    # every page has its guide, opened from its title bar
    for page in ["printer", "functions", "zoffset", "camera", "ai", "notifications", "network", "access", "software", "language"]:
        P.pg.locator('.set-entry[data-page="%s"]' % page).click(); P.settle(500)
        P.pg.locator(".drawer__help").click(); P.settle(400)
        good = P.pg.locator('[data-help-open="%s"]' % page).count() == 1 and P.pg.locator(".help-section").count() >= 1
        if not good: ok("page %s: «?» opens its guide" % page, False)
        P.pg.locator(".help-sheet .drawer__btn").click(); P.settle(300)
        P.pg.locator('.drawer__head [aria-label="Indietro"]').click(); P.settle(400)
    ok("every page of the menu has a «?» that opens its own guide", not [f for f in FAILS if f.startswith("page ")])

    # a group's own "?": opened at its section, with the drawing
    P.pg.locator('.set-entry[data-page="network"]').click(); P.settle(500)
    P.pg.locator('.set-group [data-help="network#what"]').click(); P.settle(600)
    ok("a group's small «?» opens the guide at its part, with the drawing", P.pg.locator('.help-section.is-highlight[data-help-section="what"]').count() == 1 and P.pg.locator(".help-section.is-highlight svg.help-fig").count() == 1)
    P.shot_vp(out + "/help_network.png")
    P.pg.locator(".help-sheet .drawer__btn").click(); P.settle(300)
    P.pg.locator('.drawer__head [aria-label="Indietro"]').click(); P.settle(400)
    P.pg.locator('.set-entry[data-page="camera"]').click(); P.settle(500)
    ok("Camera leads to the camera calibration of the AI monitor", P.pg.locator('.set-entry[data-page="camcal"]').count() == 1)
    P.pg.locator('.set-entry[data-page="camcal"]').click(); P.settle(600)
    P.pg.locator(".drawer__help").click(); P.settle(400)
    ok("... whose guide shows where to tap", "punta estrema dell'ugello" in P.pg.locator(".help-sheet").inner_text() and P.pg.locator(".help-sheet svg.help-fig").count() >= 1)
    P.pg.locator(".help-sheet .drawer__btn").click(); P.settle(300)
    ok("no errors in the page", not P.errors, P.errors[:3])
    P.close()

    # addresses not set: the camera uses the address of the page
    P = open_page(b, offer=False)
    src = P.pg.locator(".camera-frame iframe").first.get_attribute("src")
    ok("addresses not set (a new installation): the camera uses the address the dashboard was opened at", src == "http://127.0.0.1/webcam/webrtc", src)
    P.close()

    # narrow phone: the set-up fits
    P = open_page(b, width=320, height=640)
    wide = P.pg.evaluate("() => document.querySelector('.setup').scrollWidth")
    ok("320 px: the set-up fits, no sideways scroll", wide <= 320, wide)
    P.shot_vp(out + "/narrow.png")
    P.close()
    b.close()

print("\nFAILED: %d %s" % (len(FAILS), FAILS) if FAILS else "\nALL PASS")
sys.exit(1 if FAILS else 0)
