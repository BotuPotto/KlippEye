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
    # 1.63: «Installato: controlla di nuovo» restarts Moonraker (it loads its components when it starts), then asks again
    P.pg.locator(".timelapse-recheck").click()
    ok("... «controlla di nuovo» restarts Moonraker", wait_until(lambda: ["services/restart", "moonraker"] in [list(a) for a in state()["actions"]], 6), state()["actions"][-3:])
    ok("... and says when it is still not there (the [timelapse] section)", wait_until(lambda: P.pg.locator('[data-recheck="missing"]').count() == 1, 20) and "[timelapse]" in P.pg.locator('[data-recheck="missing"]').inner_text())
    mock.set(timelapse_on=True)
    P.pg.locator(".timelapse-recheck").click()
    ok("... installed: the page reloads with the timelapse", wait_until(lambda: P.pg.locator(".timelapse-videos").count() == 1, 25))
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

    # settings (1.67: changed here, written in moonraker.conf with «Salva», then Moonraker restarts)
    sett = pg.locator(".timelapse-settings")
    sett.scroll_into_view_if_needed()
    ok("1.67: nothing to save yet; it says where they are kept", sett.locator('[data-timelapse-save="clean"]').count() == 1 and "moonraker.conf" in sett.locator(".timelapse-save").inner_text())
    sett.get_by_role("button", name="A intervalli (hyperlapse)").click()
    ok("hyperlapse: its seconds appear, nothing sent yet", wait_until(lambda: sett.locator('[data-setting="hyperlapse_cycle"]').count() == 1) and state()["timelapse_settings"]["mode"] == "layermacro" and sett.locator('[data-timelapse-save="dirty"]').count() == 1)
    field = sett.locator('[data-setting="hyperlapse_cycle"] input')
    field.fill("15")
    field.press("Enter")
    sett.locator('[data-setting="parkhead"] [role=switch]').click()
    ok("park the head: on, with where", wait_until(lambda: sett.get_by_role("button", name="Centro").count() == 1))
    sett.get_by_role("button", name="Personalizzato").click() if sett.get_by_role("button", name="Personalizzato").count() else sett.get_by_role("button", name="Centro").click()
    crf = sett.locator('[data-setting="constant_rate_factor"] input')
    crf.fill("80")
    crf.press("Enter")
    P.settle(300)
    ok("a CRF of 80 is refused", crf.input_value() != "80" or sett.locator('[data-setting="constant_rate_factor"]').inner_text().find("Da 0 a 51") >= 0)
    # advanced
    ok("«Avanzate» closed: the specific ones are hidden", sett.locator('[data-setting="park_travel_speed"]').count() == 0 and sett.locator('[data-setting="pixelformat"]').count() == 0)
    sett.locator("[data-timelapse-advanced]").click(); P.settle(300)
    ok("«Avanzate» open: parking, the photo, the video", sett.locator('[data-setting="park_travel_speed"]').count() == 1 and sett.locator('[data-setting="stream_delay_compensation"]').count() == 1 and sett.locator('[data-setting="pixelformat"]').count() == 1 and sett.locator('[data-setting="rotation"]').count() == 1)
    if sett.locator('[data-setting="park_custom_pos_x"]').count():
        x = sett.locator('[data-setting="park_custom_pos_x"] input'); x.fill("120.5"); x.press("Enter")
    sett.locator('[data-setting="rotation"]').get_by_role("button", name="180°").click()
    sett.locator('[data-setting="flip_x"] [role=switch]').click()
    bad = sett.locator('[data-setting="extraoutputparams"] input'); bad.fill("-tune film # x"); P.settle(200)
    ok("an option with a comment mark is refused (it would cut the line in moonraker.conf)", "Una riga sola" in sett.locator('[data-setting="extraoutputparams"]').inner_text())
    bad.fill("-tune film"); bad.press("Enter")
    pg.screenshot(path=out + "/settings.png", full_page=True)
    # save
    sett.locator("[data-timelapse-save-btn]").click()
    ok("«Salva e riavvia Moonraker»: moonraker.conf written, Moonraker restarted", wait_until(lambda: ["services/restart", "moonraker"] in [list(a) for a in state()["actions"]], 8))
    conf = state()["cfg"]["files"]["moonraker.conf"]["content"] or ""
    section = conf.split("[timelapse]")[1].split("[update_manager")[0] if "[timelapse]" in conf else ""
    ok("... in its [timelapse] section: what differs from the defaults", all(line in section for line in ("mode: hyperlapse", "hyperlapse_cycle: 15", "parkhead: True", "rotation: 180", "flip_x: True", "extraoutputparams: -tune film")) and "constant_rate_factor" not in section, section)
    ok("... the rest of the file as it was (comment, output_path, the other sections)", "# made by the installer" in section and "output_path: ~/printer_data/timelapse/" in section and conf.count("[timelapse]") == 1 and "[update_manager timelapse]" in conf and conf.startswith("[server]"))
    ok("... back: saved, the settings are what was written", wait_until(lambda: sett.locator('[data-timelapse-save="clean"]').count() == 1, 25) and state()["timelapse_settings"]["mode"] == "hyperlapse" and state()["timelapse_settings"]["hyperlapse_cycle"] == 15)
    ok("... and still editable here (locked for Mainsail, not for this card)", not sett.locator('[data-setting="parkhead"] [role=switch]').is_disabled())
    # undo
    sett.locator('[data-setting="flip_y"] [role=switch]').click()
    ok("a change, then «Annulla modifiche»: back as saved", sett.locator('[data-timelapse-save="dirty"]').count() == 1 and (sett.get_by_role("button", name="Annulla modifiche").click() or True) and sett.locator('[data-timelapse-save="clean"]').count() == 1)
    sett.locator('[data-setting="enabled"] [role=switch]').click()
    ok("timelapse off: the other settings hide", wait_until(lambda: sett.locator('[data-setting="autorender"]').count() == 0))
    ok("no horizontal overflow", pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    ok("no page errors (but Moonraker's 502 while it restarts)", not [e for e in errs(P) if "502" not in e], errs(P)[:2])
    P.close()

    # 1.69: what the card shows is moonraker.conf's [timelapse] (the defaults for what it does not say), not the add-on's database
    mock.reset()
    cfg = state()["cfg"]
    conf_text = urllib.request.urlopen(mock.base + "/server/files/config/moonraker.conf").read().decode()
    cfg["files"]["moonraker.conf"]["content"] = conf_text.replace("output_path: ~/printer_data/timelapse/", "output_path: ~/printer_data/timelapse/\nparkhead: yes  # parked for the photo\nparkpos: center\nconstant_rate_factor: 18\nflip_x: True")
    db = state()["timelapse_settings"]
    db.update({"parkhead": False, "constant_rate_factor": 30, "duplicatelastframe": 0, "flip_x": False, "rotation": 90})
    mock.set(timelapse_on=True, cfg=cfg, timelapse_settings=db)
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("files", 2200)
    P.pg.locator('[data-files-section="timelapse"]').click()
    sett = P.pg.locator(".timelapse-settings")
    ok("1.69: the settings read from moonraker.conf: park the head on (a yes with its comment), at the centre",
       wait_until(lambda: sett.locator('[data-setting="parkhead"] [role=switch]').get_attribute("aria-checked") == "true") and sett.locator('[data-setting="parkpos"] [aria-pressed="true"], [data-setting="parkpos"] [aria-checked="true"]').inner_text().strip() == "Centro",
       sett.inner_text()[:400] if sett.count() else "")
    ok("... CRF 18 from the file (the add-on's database says 30)", sett.locator('[data-setting="constant_rate_factor"] input').input_value() == "18")
    ok("... not in the file: the add-on's default (the last frame 5 times), not its database's 0", sett.locator('[data-setting="duplicatelastframe"] input').input_value() == "5")
    sett.locator("[data-timelapse-advanced]").click(); P.settle(300)
    ok("... mirror left-right on (file), the video not turned (default, the database says 90°)", sett.locator('[data-setting="flip_x"] [role=switch]').get_attribute("aria-checked") == "true" and sett.locator('[data-setting="rotation"] [aria-pressed="true"], [data-setting="rotation"] [aria-checked="true"]').inner_text().strip() == "0°")
    ok("... and nothing asked to the add-on's settings, nothing sent to it", not [r for r in P.take_reqs() if "/machine/timelapse/settings" in r["u"]] and not [l for l in state()["timelapse_log"] if l.startswith("SET:")])
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
    P.close()

    # 1.67: not while printing
    P = fresh(b, timelapse_on=True, printing=True)
    P.pg.locator('[data-files-section="timelapse"]').click()
    sett = P.pg.locator(".timelapse-settings")
    wait_until(lambda: sett.locator('[data-setting="autorender"]').count() == 1)
    sett.locator('[data-setting="autorender"] [role=switch]').click()
    sett.locator("[data-timelapse-save-btn]").click()
    ok("1.67: printing: «Salva» says to wait for the end, nothing written or restarted", wait_until(lambda: "Non durante una stampa" in P.pg.locator(".toast--action").inner_text()) and ["services/restart", "moonraker"] not in [list(a) for a in state()["actions"]] and state()["cfg"]["files"]["moonraker.conf"]["content"] is None)
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
