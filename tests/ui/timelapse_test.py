"""Release 1.46.0 (roadmap 6d part 5): moonraker-timelapse as the third part of the Files page (only when Moonraker has
it): the videos (preview, play, download, delete), the frames of the last print and "Crea il video", the settings (a
setting fixed in moonraker.conf locked), the warning without the TIMELAPSE_TAKE_FRAME macro. Against the mock.
Usage: timelapse_test.py <html> <outdir> <port>"""
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
CUR = [None]


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
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    return bool(fn())


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def videos(P):
    return [e.get_attribute("data-video") for e in P.pg.locator(".timelapse-row").all()]


def errs(P):
    return [e for e in P.errors if "pageerror" in e or "console.error" in e]


def fresh(b, w=390, h=844, **st):
    mock.reset()
    mock.set(**st)
    P = Page(b, mock, w, h)
    CUR[0] = P
    P.goto("files", 2200)
    return P


with sync_playwright() as p:
    b = p.chromium.launch()

    P = fresh(b)
    ok("without the timelapse component: still three parts (1.56)", P.pg.locator("[data-files-section]").count() == 3)
    P.pg.locator('[data-files-section="timelapse"]').click()
    ok("... the timelapse part says what to install, with the commands", wait_until(lambda: P.pg.locator(".timelapse-missing").count() == 1) and "moonraker-timelapse" in P.pg.locator(".timelapse-missing").inner_text() and P.pg.locator(".timelapse-missing .ai-codeblock").count() == 3)
    ok("... and asks Moonraker for nothing of the timelapse", not [r for r in P.take_reqs() if "/machine/timelapse" in r["u"]])
    P.shot(out + "/timelapse_missing.png")
    P.close()

    P = fresh(b, timelapse_on=True, timelapse_frames=42)
    pg = P.pg
    pg.locator('[data-files-section="timelapse"]').click()
    ok("'Timelapse': the videos, newest first", wait_until(lambda: videos(P) == ["timelapse_Benchy_20261103_2210.mp4", "timelapse_Vase_20261101_1010.mp4"]), videos(P))
    ok("... the Benchy with its preview picture, the vase without", pg.locator('.timelapse-row[data-video^="timelapse_Benchy"] img').count() == 1 and pg.locator('.timelapse-row[data-video^="timelapse_Vase"] img').count() == 0)
    ok("the 42 frames of the last print wait to be a video", "42 foto" in pg.locator(".timelapse-frames").inner_text())
    ok("no warning: the macro is there", pg.locator(".timelapse-macro").count() == 0)
    pg.screenshot(path=out + "/page.png", full_page=True)
    pg.locator(".timelapse-render").click()
    ok("'Crea il video' asks Moonraker to render", wait_until(lambda: "RENDER" in state()["timelapse_log"]))
    ok("... and the new video appears", wait_until(lambda: videos(P)[0] == "timelapse_Bracket_new.mp4", 10) and wait_until(lambda: pg.locator(".timelapse-frames").count() == 0), videos(P))
    pg.locator('.timelapse-row[data-video="timelapse_Benchy_20261103_2210.mp4"] .timelapse-row__preview').click()
    ok("a tap on the preview plays the video full screen", wait_until(lambda: pg.locator(".timelapse-viewer video").count() == 1) and "timelapse_Benchy" in pg.locator(".timelapse-viewer video").get_attribute("src"))
    pg.keyboard.press("Escape")
    ok("... Esc closes it", wait_until(lambda: pg.locator(".timelapse-viewer").count() == 0))
    pg.locator('.timelapse-row[data-video="timelapse_Vase_20261101_1010.mp4"] .timelapse-delete').click()
    pg.locator(".confirm-card").get_by_role("button", name="Elimina").click()
    ok("deleting a video", wait_until(lambda: "timelapse_Vase_20261101_1010.mp4" not in state()["timelapse_files"]) and wait_until(lambda: "timelapse_Vase_20261101_1010.mp4" not in videos(P)))

    # settings
    sett = pg.locator(".timelapse-settings")
    sett.scroll_into_view_if_needed()
    sett.get_by_role("button", name="Ogni tot secondi").click()
    ok("hyperlapse: saved, and its seconds appear", wait_until(lambda: state()["timelapse_settings"]["mode"] == "hyperlapse") and wait_until(lambda: sett.locator('[data-setting="hyperlapse_cycle"]').count() == 1))
    field = sett.locator('[data-setting="hyperlapse_cycle"] input')
    field.fill("15")
    field.press("Enter")
    ok("... every 15 s", wait_until(lambda: state()["timelapse_settings"]["hyperlapse_cycle"] == 15), state()["timelapse_settings"]["hyperlapse_cycle"])
    sett.locator('[data-setting="parkhead"] [role=switch]').click()
    ok("park the head: on, with where", wait_until(lambda: state()["timelapse_settings"]["parkhead"] is True) and wait_until(lambda: sett.get_by_role("button", name="Centro").count() == 1))
    sett.get_by_role("button", name="Centro").click()
    ok("... in the centre", wait_until(lambda: state()["timelapse_settings"]["parkpos"] == "center"))
    sett.locator('[data-setting="variable_fps"] [role=switch]').click()
    ok("frames a second from the length: the length field instead of the rate", wait_until(lambda: sett.locator('[data-setting="targetlength"]').count() == 1 and sett.locator('[data-setting="output_framerate"]').count() == 0))
    crf = sett.locator('[data-setting="constant_rate_factor"] input')
    crf.fill("80")
    crf.press("Enter")
    P.settle(500)
    ok("a CRF of 80 is refused", state()["timelapse_settings"]["constant_rate_factor"] == 23)
    pg.screenshot(path=out + "/settings.png", full_page=True)
    sett.locator('[data-setting="enabled"] [role=switch]').click()
    ok("timelapse off: the other settings hide", wait_until(lambda: state()["timelapse_settings"]["enabled"] is False) and wait_until(lambda: sett.locator('[data-setting="autorender"]').count() == 0))
    ok("no horizontal overflow", pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    ok("no page errors", not errs(P), errs(P)[:2])
    P.close()

    # a setting locked in moonraker.conf; no macro
    mock.reset()
    mock.set(timelapse_on=True, timelapse_macro=False)
    s = state()["timelapse_settings"]
    s["blockedsettings"] = ["snapshoturl", "autorender"]
    mock.set(timelapse_settings=s)
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("files", 2200)
    P.pg.locator('[data-files-section="timelapse"]').click()
    ok("without TIMELAPSE_TAKE_FRAME it says to include timelapse.cfg", wait_until(lambda: P.pg.locator(".timelapse-macro").count() == 1) and "timelapse.cfg" in P.pg.locator(".timelapse-macro").inner_text())
    ok("a setting fixed in moonraker.conf is locked and says so", wait_until(lambda: P.pg.locator('[data-setting="autorender"] [role=switch]').is_disabled()) and "moonraker.conf" in P.pg.locator('[data-setting="autorender"]').inner_text())
    P.close()

    # computer
    P = fresh(b, 1440, 900, timelapse_on=True)
    P.pg.locator('[data-files-section="timelapse"]').click()
    ok("desktop: videos and settings side by side", wait_until(lambda: P.pg.locator(".desk-split--timelapse .timelapse-settings").count() == 1 and len(videos(P)) == 2))
    P.pg.screenshot(path=out + "/desktop.png")
    ok("desktop: no page errors", not errs(P), errs(P)[:2])
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
