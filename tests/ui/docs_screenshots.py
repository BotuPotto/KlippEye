"""The pictures of the documentation (docs/images), taken from the dashboard against the mock, in English and Italian.
Run it again after a change to a page shown in the guides:
    cd tests/ui && python3 docs_screenshots.py ../../frontend/klippeye_frontend.html ../../docs/images 9910  [en it]
The camera shows a drawn picture (tests/ui/docs_camera.jpg): the pictures say they show demo data."""
import base64
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import Mock, Page  # noqa: E402

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(out, exist_ok=True)
HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "docs_camera.jpg"), "rb") as f:
    CAM = ("<html><body style='margin:0;background:#000'><img style='width:100vw;height:100vh;object-fit:cover' "
           "src='data:image/jpeg;base64," + base64.b64encode(f.read()).decode() + "'></body></html>")
LOCALES = {"en": "en-US", "it": "it-IT"}
MODEL = {"available": True, "source": "base", "version": "20261120-1015", "threshold": 0.62, "size": 224,
         "last": {"score": 12.0, "checks": 240, "filtered": 9, "asked": 3}}
mock = Mock(html, port)
with open(os.path.join(HERE, "..", "..", "VERSION")) as f:
    RELEASE = f.read().strip()
SUMMARY = {"en": "Spaghetti on the bed: the part came off.", "it": "Spaghetti sul piatto, il pezzo si è staccato."}


def shot(P, locator, margin=12):
    """A part of the page with a little of the page around it."""
    box = locator.bounding_box()
    vw = P.pg.viewport_size["width"]
    x, y = max(0, box["x"] - margin), max(0, box["y"] - margin)
    return P.pg.screenshot(clip={"x": x, "y": y, "width": min(vw - x, box["width"] + 2 * margin), "height": box["height"] + 2 * margin},
                           full_page=True)


def save(png, name, lang, width=None):
    """PNG bytes -> docs/images/<name>-<lang>.jpg (smaller than a PNG; the pictures are photos of a screen)."""
    path = os.path.join(out, "%s-%s.jpg" % (name, lang))
    tmp = path + ".png"
    with open(tmp, "wb") as f:
        f.write(png)
    image = Image.open(tmp).convert("RGB")
    if width and image.width > width:
        image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
    image.save(path, quality=84, optimize=True)
    os.remove(tmp)
    print("saved", path, image.size)


def page(browser, lang, w=390, h=844, tab="home", setup=False, **state):
    mock.reset()
    if state:
        mock.set(**state)
    P = Page(browser, mock, w, h, locale=LOCALES[lang], offer_setup=setup)
    P.pg.route("**/webcam/webrtc*", lambda route: route.fulfill(content_type="text/html", body=CAM))
    P.goto(tab, 2600)
    return P


def settings(P, *pages):
    P.pg.locator(".header-btn--menu").click()
    P.pg.wait_for_selector(".drawer")
    P.settle(1500)
    for name in pages:
        P.pg.locator('.drawer .set-entry[data-page="%s"]' % name).first.click()
        P.settle(1200)


def run(browser, lang):
    # 0. the dashboard during a print, on a computer and on a phone (the README)
    P = page(browser, lang, w=1440, h=900, extra_temps=True, power_on=True, spoolman_on=True, printing=True)
    P.settle(1500)
    save(P.pg.screenshot(), "desktop", lang)
    P.close()
    P = page(browser, lang, printing=True, spoolman_on=True)
    P.settle(1500)
    save(P.pg.screenshot(), "phone", lang)
    P.close()

    # 1. the guided set-up, as it opens the first time
    P = page(browser, lang, setup=True)
    P.pg.wait_for_selector(".setup", timeout=8000)
    P.settle(600)
    save(P.pg.screenshot(), "setup", lang)
    P.close()

    # 2. the settings menu on a phone
    P = page(browser, lang)
    settings(P)
    save(P.pg.screenshot(), "settings", lang)
    P.close()

    # 3. Settings → AI monitor → The AI service: who judges the pictures
    P = page(browser, lang, local_model=MODEL)
    settings(P, "ai")
    group = P.pg.locator(".set-group").filter(has=P.pg.locator("[data-judge]")).first
    group.scroll_into_view_if_needed()
    P.settle(400)
    save(shot(P, group), "ai-service", lang)
    P.close()

    # 4. an alarm of the AI during a print: the print card asks
    def in_language(route):  # the mock's AI writes in Italian: the verdict in the language of the picture
        answer = route.fetch().json()
        if answer.get("analysis"):
            answer["analysis"]["summary"] = SUMMARY[lang]
        route.fulfill(content_type="application/json", body=json.dumps(answer))
    mock.reset()
    mock.set(printing=True, detector_status="scanning", has_analysis=True, analysis_action="PAUSA")
    P = Page(browser, mock, 390, 844, locale=LOCALES[lang])
    P.pg.route("**/webcam/webrtc*", lambda route: route.fulfill(content_type="text/html", body=CAM))
    P.pg.route("**/api/print/detector/status*", in_language)
    P.goto("home", 2600)
    P.pg.wait_for_selector("[data-ai-question]", timeout=10000)
    P.settle(600)
    save(shot(P, P.pg.locator("[data-ai-question]")), "ai-alarm", lang)
    P.close()

    # 6. notifications on a phone browser: the QR code for the ntfy app
    P = page(browser, lang, w=1280, h=900, db={"klippeye/notifier": {"version": RELEASE, "seen": time.time(), "last": None}},
             ntfy={"enabled": True, "server": "https://ntfy.sh", "topic": "klippeye-demo4f7a2c9e81b3", "has_token": False, "click": ""})
    settings(P, "notifications")
    save(P.pg.locator(".drawer").screenshot(), "notifications", lang, width=1100)
    P.close()

    # 7. Settings → Updates
    P = page(browser, lang, backend_release=RELEASE, update_channel="stable")
    settings(P, "software")
    save(P.pg.screenshot(), "updates", lang)
    P.close()

    # 8. the bed mesh on a computer
    P = page(browser, lang, w=1440, h=1300, tab="controllo")
    card = P.pg.locator(".mesh-card").first
    P.settle(800)
    save(shot(P, card), "bedmesh", lang, width=900)
    P.close()

    # 9. Settings → Printer functions
    P = page(browser, lang)
    settings(P, "functions")
    save(P.pg.screenshot(), "functions", lang)
    P.close()


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for lang in sys.argv[4:] or ("en", "it"):
        run(browser, lang)
    browser.close()
mock.stop()
