"""Release 1.59: Settings → Camera lists every camera, each with its page. The main camera (KlippEye's own, the one the AI
monitor watches) keeps its page; the webcams kept by Moonraker (the same ones Mainsail and Fluidd show) are changed,
added and removed from here, as in Mainsail; one written in moonraker.conf can only be read. Timelapse: its settings
(and which camera it uses) or how to install it. Against the mock.
Usage: camera_settings_test.py <html> <outdir> <port>"""
import json
import os
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


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


def wait_until(fn, timeout=6.0, step=0.15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(step)
    return False


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def posts():
    return [b for kind, b in state()["webcam_log"] if kind == "post"]


def open_cameras(b, **st):
    mock.reset()
    if st:
        mock.set(**st)
    P = Page(b, mock, 390, 844)
    P.goto("home", 2000)
    P.pg.click('button[aria-label="Impostazioni"]'); P.pg.wait_for_selector(".drawer"); P.settle(450)
    P.pg.locator('.set-entry[data-page="camera"]').click(); P.settle(900)
    return P


def title(P):
    return P.pg.locator(".drawer__title").inner_text()


def back(P):
    P.pg.click('.drawer button[aria-label="Indietro"]'); P.settle(500)


with sync_playwright() as p:
    b = p.chromium.launch()

    P = open_cameras(b)
    pg = P.pg
    ok("the page lists the main camera, Moonraker's three webcams, Timelapse and the calibration", pg.locator('[data-page="camera-main"]').count() == 1
       and [e.get_attribute("data-page") for e in pg.locator("[data-webcams] .set-entry").all()] == ["webcam:u-klippeye", "webcam:u-piatto", "webcam:u-go2rtc"]
       and pg.locator('[data-page="camera-timelapse"]').count() == 1 and pg.locator('[data-page="camcal"]').count() == 1)
    ok("... each webcam says its kind and address", "MJPEG · /webcam2/?action=stream" in pg.locator('[data-page="webcam:u-piatto"]').inner_text(), pg.locator('[data-page="webcam:u-piatto"]').inner_text())
    P.shot(out + "/cameras.png")

    pg.locator('[data-page="camera-main"]').click(); P.settle(600)
    ok("the main camera's page: method, address, snapshot (as before)", title(P) == "Camera principale" and pg.locator(".set-choice", has_text="WebRTC").count() >= 1 and pg.locator("[data-snapshot-now]").count() == 1)
    back(P)

    # ------------------------------------------------------------------ a webcam of Moonraker, changed as in Mainsail
    pg.locator('[data-page="webcam:u-piatto"]').click(); P.settle(700)
    ok("a webcam's page, titled with its name: name, on, kind, addresses, fps, image", title(P) == "Piatto" and pg.locator(".set-choice.is-selected", has_text="MJPEG").count() == 1 and "Indirizzo del video" in pg.locator(".drawer__body").inner_text())
    P.shot(out + "/webcam.png")
    name = pg.locator("input.set-field__input").first
    name.fill("Piatto alto"); name.press("Enter"); P.settle(900)
    ok("renaming: saved to Moonraker with its uid, the title follows", wait_until(lambda: posts() and posts()[-1].get("uid") == "u-piatto" and posts()[-1].get("name") == "Piatto alto") and wait_until(lambda: title(P) == "Piatto alto"), posts()[-1:] if posts() else state()["webcam_log"])
    pg.locator(".set-switch", has_text="Specchia").click(); P.settle(600)
    ok("mirror off: saved (flip_horizontal false), the rest kept", wait_until(lambda: posts()[-1].get("flip_horizontal") is False and posts()[-1].get("stream_url") == "/webcam2/?action=stream"), posts()[-1])
    pg.locator(".oui-chip", has_text="90°").click(); P.settle(600)
    ok("rotation 90°", wait_until(lambda: posts()[-1].get("rotation") == 90), posts()[-1])
    pg.locator(".set-choice", has_text="WebRTC").first.click(); P.settle(600)
    ok("kind WebRTC", wait_until(lambda: posts()[-1].get("service") == "webrtc-camerastreamer"), posts()[-1])
    back(P)
    ok("back on the list: the new name", "Piatto alto" in pg.locator("[data-webcams]").inner_text())

    # ------------------------------------------------------------------ one written in moonraker.conf: read only
    pg.locator('[data-page="webcam:u-go2rtc"]').click(); P.settle(700)
    ok("a webcam of moonraker.conf: says so, nothing can be changed or removed", pg.locator("[data-webcam-config]").count() == 1 and pg.locator("fieldset.webcam-fields[disabled]").count() == 1 and pg.locator("[data-webcam-delete]").count() == 0)
    ok("... an unknown kind (go2rtc) is shown as it is, with a note", pg.locator(".set-choice.is-selected", has_text="webrtc-go2rtc").count() == 1)
    back(P)

    # ------------------------------------------------------------------ add and remove
    n = len(posts())
    pg.locator("[data-webcam-add]").click()
    ok("Add a camera: a new webcam in Moonraker, and its page opens", wait_until(lambda: len(posts()) == n + 1 and "uid" not in posts()[-1]) and wait_until(lambda: title(P) == "Camera 4"), (posts()[-1:], title(P)))
    pg.locator("[data-webcam-delete]").click(); P.settle(400)
    pg.locator(".confirm-card").get_by_role("button", name="Togli", exact=True).click(); P.settle(900)
    ok("Remove: deleted from Moonraker, back to the list", wait_until(lambda: state()["webcam_log"][-1][0] == "delete") and wait_until(lambda: pg.locator("[data-webcams] .set-entry").count() == 3), state()["webcam_log"][-1])

    # ------------------------------------------------------------------ timelapse without the component
    pg.locator('[data-page="camera-timelapse"]').click(); P.settle(700)
    ok("Timelapse without moonraker-timelapse: how to install it", "moonraker-timelapse" in pg.locator(".drawer__body").inner_text() and pg.locator(".drawer__body .ai-codeblock").count() == 3)
    ok("no page errors", not [e for e in P.errors if "pageerror" in e], P.errors[:3])
    P.close()

    # ------------------------------------------------------------------ timelapse with it: its settings and the camera
    P = open_cameras(b, timelapse_on=True)
    pg = P.pg
    pg.locator('[data-page="camera-timelapse"]').click(); P.settle(1200)
    ok("Timelapse: its settings, here in the menu", wait_until(lambda: pg.locator('.drawer [data-setting="enabled"]').count() == 1) and pg.locator('.drawer [data-setting="autorender"]').count() == 1)
    pg.locator(".set-choice", has_text="Piatto").click(); P.settle(800)
    ok("... which camera: Piatto, saved in moonraker-timelapse", wait_until(lambda: state()["timelapse_settings"]["camera"] == "Piatto"), state()["timelapse_log"][-2:])
    pg.locator('.drawer [data-setting="autorender"] .set-switch').click(); P.settle(800)
    ok("... a switch changes it", wait_until(lambda: state()["timelapse_settings"]["autorender"] is False), state()["timelapse_settings"]["autorender"])
    P.shot(out + "/timelapse.png")
    ok("no page errors", not [e for e in P.errors if "pageerror" in e], P.errors[:3])
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
