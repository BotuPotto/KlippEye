"""KlippEye release 1.0 in the dashboard: the thresholds of the AI monitor (the backend describes them, the menu draws them), the page
"Aggiornamenti" (releases, check, update, rollback, recovery, restart) and the update dialog that waits for the backend to come back.
Usage: software_test.py <html> <outdir> <port>"""
import sys, os, io, re, json, time, urllib.request
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
FAILS = []


def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:700]) if (extra != "" and not cond) else ""), flush=True)


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def cfg_log():
    return state()["brain_cfg_log"]


def actions():
    return [tuple(a) for a in json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read()).get("actions", [])]


CUR = [None]


def ws_refuses(ws):
    def on_message(msg):
        try: data = json.loads(msg)
        except Exception: return
        if isinstance(data, dict) and "id" in data:
            ws.send(json.dumps({"jsonrpc": "2.0", "id": data["id"], "error": {"code": -32601, "message": "Method not found"}}))
    ws.on_message(on_message)


def wait_until(fn, timeout=4.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn(): return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    try: return bool(fn())
    except Exception: return False


def fresh(b, w=390, h=844, wait=1400, github="1.0.1\n", vz=None, no_klippeye=False, **st):
    mock.reset()
    if no_klippeye: st["klippeye_info"] = None
    elif vz: st["klippeye_info"] = {**state()["klippeye_info"], **vz}
    base_services = {"klipper": ["active", "running"], "moonraker": ["active", "running"], "klippeye": ["active", "running"], "klippeye-notifier": ["active", "running"]}
    mock.set(services=base_services, **st)
    P = Page(b, mock, w, h)
    CUR[0] = P
    # the repository's VERSION file (what the update would install), as raw.githubusercontent.com would answer
    P.pg.route("https://raw.githubusercontent.com/**", lambda route: route.fulfill(status=200, body=github, content_type="text/plain", headers={"access-control-allow-origin": "*"}) if github is not None else route.abort())
    # the real backend has no websocket, so the dashboard falls back to plain HTTP; here the socket exists and refuses every command, which comes to the same
    P.pg.route_web_socket("**/websocket", ws_refuses)
    P.goto("home", wait)
    P.pg.evaluate("() => { window.__marker = 1; }")
    return P


def open_menu(P):
    P.pg.click('button[aria-label="Impostazioni"]'); P.pg.wait_for_selector(".drawer"); P.settle(450)


def go(P, name):
    P.pg.click('.set-entry[data-page="%s"]' % name); P.settle(500)


def reloaded(P, timeout=45.0):
    """The page was loaded again (the marker set before the update is gone)."""
    return wait_until(lambda: P.pg.evaluate("() => !window.__marker"), timeout, 0.3)


def set_range(P, label_text, value):
    P.pg.evaluate("""([label, value]) => {
      const el = [...document.querySelectorAll('.set-num__range')].find(e => e.getAttribute('aria-label') === label);
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(el, String(value)); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true }));
    }""", [label_text, value])


def tile(P, label):
    """The tile of one setting, found by its exact title (the help texts of the others mention words like 'area' too)."""
    return P.pg.locator(".set-num", has=P.pg.locator(".set-num__title", has_text=re.compile("^" + re.escape(label) + "$")))


def num_box(P, label):
    return tile(P, label).locator(".set-num__input")


def type_into(loc, text):
    """The whole text at once, as a paste would put it (typing letter by letter sends every good prefix, as it should)."""
    loc.fill(text)


def last_post():
    log = cfg_log()
    return log[-1] if log else None


def sent_keys():
    keys = []
    for item in cfg_log():
        keys += list(item.keys())
    return keys


with sync_playwright() as p:
    b = p.chromium.launch()

    # ====================================================================================== the list of the menu
    P = fresh(b)
    pg = P.pg
    open_menu(P)
    titles = pg.locator(".set-entry .oui-row__name").all_inner_texts()
    ok("twelve groups, the printer first, then Accesso, the software one and Lingua last", titles == ["Stampante", "Camera", "Indirizzi", "Z-offset", "Notifiche", "Monitor IA", "Soglie del monitor", "Calibra camera", "Registrazioni", "Accesso", "Aggiornamenti", "Lingua"], titles)
    ok("the list says which release is installed", wait_until(lambda: pg.locator('.set-entry[data-page="software"] .set-entry__meta').inner_text() == "Release 1.0.0"), pg.locator('.set-entry[data-page="software"] .set-entry__meta').inner_text())
    ok("no 'Nuovo' sign when nothing is waiting", pg.locator(".set-entry__badge").count() == 0)
    P.close()

    P = fresh(b, vz={"commits_behind": [{"sha": "aaa", "subject": "Release 1.0.1", "date": "1760000000"}], "commits_behind_count": 1, "remote_version": "v0.0.0-4"})
    pg = P.pg
    open_menu(P)
    ok("a waiting update is announced in the list", wait_until(lambda: pg.locator('.set-entry[data-page="software"] .set-entry__badge').count() == 1) and "aggiornamento disponibile" in pg.locator('.set-entry[data-page="software"] .set-entry__meta').inner_text(), pg.locator('.set-entry[data-page="software"]').inner_text())
    P.close()

    P = fresh(b, brain="old")
    open_menu(P)
    ok("an old backend: both new entries say it must be updated", wait_until(lambda: "Backend da aggiornare" in P.pg.locator('.set-entry[data-page="software"] .set-entry__meta').inner_text()), P.pg.locator('.set-entry[data-page="software"] .set-entry__meta').inner_text())
    P.close()

    # ====================================================================================== the thresholds
    P = fresh(b)
    pg = P.pg
    open_menu(P); go(P, "ai")
    ok("Monitor IA page: a row leads to the thresholds", pg.locator('.set-entry[data-page="detector"]').count() == 1)
    pg.click('.set-entry[data-page="detector"]'); P.settle(600)
    ok("the thresholds page opens with its title", pg.locator(".drawer__title").inner_text() == "Soglie del monitor")
    wanted = ["monitor", "rilevamento del movimento", "falsi allarmi", "area controllata", "pause e consumi", "quando comincia a controllare", "modello dell'ia"]
    ok("the groups are the ones the backend declares", wait_until(lambda: [t.lower() for t in pg.locator(".set-group__label").all_inner_texts()] == wanted), pg.locator(".set-group__label").all_inner_texts())
    ok("a line says the monitor is on", "Il monitor è acceso" in pg.locator(".set-status").first.inner_text(), pg.locator(".set-status").first.inner_text())
    ok("a number shows its usual value in its box", num_box(P, "Soglia di cambiamento").input_value() == "35" and num_box(P, "Controlli sospetti prima dell'allarme").input_value() == "3")
    ok("a decimal is shown with a comma", num_box(P, "Movimento ai bordi").input_value() == "2,5", num_box(P, "Movimento ai bordi").input_value())
    ok("nothing was written to the backend by merely looking", cfg_log() == [])
    ok("the reset button is off while nothing differs", pg.locator("button", has_text="Ripristina i valori di sempre").is_disabled())
    P.shot(out + "/detector_top.png")

    type_into(num_box(P, "Soglia di cambiamento"), "50")
    ok("typing a good number sends it to the backend, alone", wait_until(lambda: last_post() == {"sensitivity": 50}, 3.0), cfg_log())
    ok("... the slider follows and the line 'Di serie' appears", tile(P, "Soglia di cambiamento").locator(".set-num__range").input_value() == "50" and tile(P, "Soglia di cambiamento").locator(".set-num__foot").count() == 1)
    n = len(cfg_log())
    type_into(num_box(P, "Soglia di cambiamento"), "3")
    P.settle(1200)
    ok("a number below the minimum is not sent", len(cfg_log()) == n and "da 5 a 100" in tile(P, "Soglia di cambiamento").inner_text(), (len(cfg_log()), n))
    pg.locator(".drawer__title").click()  # leaves the box
    P.settle(300)
    ok("... and the last good value comes back when the box is left", num_box(P, "Soglia di cambiamento").input_value() == "50")
    type_into(num_box(P, "Soglia di cambiamento"), "7,5")
    P.settle(1000)
    ok("a decimal in a whole-number setting is refused too", len(cfg_log()) == n, cfg_log()[-2:])
    pg.locator(".drawer__title").click(); P.settle(300)

    set_range(P, "Ogni quanto guarda la camera", 7)
    ok("moving a slider is sent as well", wait_until(lambda: last_post() == {"check_interval": 7}, 3.0), cfg_log())
    ok("... and shows in the box with its unit", num_box(P, "Ogni quanto guarda la camera").input_value() == "7")
    # two quick changes travel together
    type_into(num_box(P, "Pausa dopo un allarme"), "120")
    type_into(num_box(P, "Attesa dopo l'inizio della stampa"), "60")
    ok("two quick changes are sent as one request", wait_until(lambda: last_post() == {"cooldown": 120, "warmup_seconds": 60}, 3.0), cfg_log()[-3:])

    # the switch
    pg.click(".set-switch:has-text('Monitor attivo')"); P.settle(300)
    ok("switching the monitor off is sent and the line says so", wait_until(lambda: last_post() == {"enabled": False}, 3.0) and "Il monitor è spento" in pg.locator(".set-status").first.inner_text(), cfg_log()[-2:])
    pg.click(".set-switch:has-text('Monitor attivo')"); P.settle(300)
    ok("... and on again", wait_until(lambda: last_post() == {"enabled": True}, 3.0))

    # the area
    area_inputs = tile(P, "Area controllata").locator(".set-grid input")
    ok("the area has four boxes with the usual 20 · 20 · 60 · 60", [area_inputs.nth(i).input_value() for i in range(4)] == ["20", "20", "60", "60"])
    ok("the picture and the drawn rectangle are there", pg.locator(".set-roi__img").count() == 1 and pg.locator(".set-roi__box").count() == 1)
    box0 = pg.locator(".set-roi__box").evaluate("e => e.style.left + '|' + e.style.top + '|' + e.style.width + '|' + e.style.height")
    ok("the rectangle is drawn where the numbers say", box0 == "20%|20%|60%|60%", box0)
    n = len(cfg_log())
    type_into(area_inputs.nth(2), "90")  # 20 + 90 goes past the picture
    P.settle(1200)
    ok("an area that does not fit is not sent and the problem is written", len(cfg_log()) == n and "dentro l'immagine" in tile(P, "Area controllata").inner_text())
    type_into(area_inputs.nth(2), "70")
    ok("a good area is sent as one list of four numbers", wait_until(lambda: last_post() == {"roi": [20.0, 20.0, 70.0, 60.0]}, 3.0), cfg_log()[-2:])
    ok("... and the rectangle moves with it", pg.locator(".set-roi__box").evaluate("e => e.style.width") == "70%")
    pg.locator(".drawer__title").click(); P.settle(300)

    # the model
    model = pg.locator("input[placeholder='predefinito']")
    type_into(model, "gpt 4o")
    P.settle(1300)
    ok("a model name with a space is refused and not sent", "ai_model" not in sent_keys() and "niente spazi" in pg.locator(".set-field__error").first.inner_text(), sent_keys())
    type_into(model, "llama-3.3-70b")
    ok("a good model name is sent", wait_until(lambda: last_post() == {"ai_model": "llama-3.3-70b"}, 3.0), cfg_log()[-2:])
    pg.locator(".drawer__title").click(); P.settle(300)

    # reading it back from the backend (another device changed something)
    pg.reload(); P.settle(1500)
    open_menu(P); go(P, "ai"); pg.click('.set-entry[data-page="detector"]'); P.settle(700)
    ok("after a reload the values are the ones the backend kept", num_box(P, "Soglia di cambiamento").input_value() == "50" and num_box(P, "Ogni quanto guarda la camera").input_value() == "7" and num_box(P, "Pausa dopo un allarme").input_value() == "120")
    ok("the reset button is on now", not pg.locator("button", has_text="Ripristina i valori di sempre").is_disabled())
    pg.locator("button", has_text="Ripristina i valori di sempre").click(); P.settle(300)
    ok("it asks first", pg.locator(".set-confirm").count() == 1)
    pg.locator(".set-confirm button", has_text="No").click(); P.settle(200)
    ok("'No' leaves everything", pg.locator(".set-confirm").count() == 0 and num_box(P, "Soglia di cambiamento").input_value() == "50")
    pg.locator("button", has_text="Ripristina i valori di sempre").click(); P.settle(200)
    pg.locator(".set-confirm button", has_text="Sì, ripristina").click()
    ok("'Sì' brings the usual values back", wait_until(lambda: num_box(P, "Soglia di cambiamento").input_value() == "35" and num_box(P, "Ogni quanto guarda la camera").input_value() == "3" and num_box(P, "Pausa dopo un allarme").input_value() == "90", 4.0))
    ok("... and it was the backend that did it", any(isinstance(x, dict) and "reset" in x for x in cfg_log()))
    P.shot(out + "/detector_full.png")
    ok("[detector] no error in the console", P.errors == [], P.errors)
    P.close()

    # the backend refuses / is away / is old
    P = fresh(b, brain_cfg_fail=500)
    pg = P.pg
    open_menu(P); go(P, "detector")
    type_into(num_box(P, "Soglia di cambiamento"), "60")
    ok("a failed save is told", wait_until(lambda: "La modifica non è stata salvata" in pg.locator(".drawer__body").inner_text(), 4.0), pg.locator(".drawer__body").inner_text()[:300])
    pg.locator(".drawer__title").click()
    ok("... and the box when it is left", wait_until(lambda: num_box(P, "Soglia di cambiamento").input_value() == "35", 3.0))
    P.close()

    P = fresh(b, brain="old")
    open_menu(P); go(P, "detector")
    ok("an old backend: a clear note instead of an empty page", wait_until(lambda: "precedente alla 1.0" in P.pg.locator(".drawer__body").inner_text(), 3.0), P.pg.locator(".drawer__body").inner_text()[:300])
    P.close()

    P = fresh(b, brain_has_cv2=False, brain_running=False)
    open_menu(P); go(P, "detector")
    ok("without OpenCV and with the monitor off, the page says so", wait_until(lambda: "manca OpenCV" in P.pg.locator(".drawer__body").inner_text(), 3.0) and "Il monitor è spento" in P.pg.locator(".drawer__body").inner_text())
    P.close()

    # ====================================================================================== the software page
    P = fresh(b)
    pg = P.pg
    open_menu(P); go(P, "software")
    ok("the page opens with its title", pg.locator(".drawer__title").inner_text() == "Aggiornamenti")
    ok("it lists the release, the page's release and the code version", wait_until(lambda: "1.0.0" in pg.locator(".set-info").first.inner_text()) and pg.locator(".set-info").count() >= 4, pg.locator(".drawer__body").inner_text()[:400])
    txt = pg.locator(".drawer__body").inner_text()
    ok("... with the commit and the branch", "a1b2c3d" in txt and "main" in txt, txt)
    ok("an up-to-date system says so", wait_until(lambda: "KlippEye è aggiornato" in pg.locator(".drawer__body").inner_text(), 4.0))
    ok("no update button then", pg.locator("button", has_text="Aggiorna KlippEye").count() == 0)
    ok("the restart rows are there (the notification service exists)", wait_until(lambda: "Riavvia il backend" in pg.locator(".drawer__body").inner_text() and "Riavvia le notifiche" in pg.locator(".drawer__body").inner_text(), 3.0), pg.locator(".drawer__body").inner_text()[-300:])
    row = pg.locator(".file-action", has_text="Scarica il rapporto di diagnostica")
    ok("1.9.0: a 'Diagnostica' block offers the diagnostic report", row.count() == 1 and "klippeye diagnose" in row.inner_text(), pg.locator(".drawer__body").inner_text()[-500:])
    with pg.expect_download(timeout=8000) as info:
        row.click()
    ok("... a click downloads it from /api/diagnose", "KlippEye diagnostic report" in open(info.value.path(), encoding="utf-8").read(), info.value.suggested_filename)
    choices = lambda: pg.locator(".set-choice", has_text="Release stabili").count() + pg.locator(".set-choice", has_text="Ogni modifica").count()
    ok("1.10.0: the 'Canale degli aggiornamenti' block shows the two channels, 'Ogni modifica' chosen (dev)", wait_until(lambda: choices() == 2, 4.0) and pg.locator('.set-choice[aria-checked="true"]', has_text="Ogni modifica").count() == 1, pg.locator(".drawer__body").inner_text()[-800:])
    pg.locator(".set-choice", has_text="Release stabili").click()
    ok("... choosing 'Release stabili' asks the backend to switch to stable", wait_until(lambda: state()["channel_posts"] == ["stable"], 4.0) and wait_until(lambda: pg.locator('.set-choice[aria-checked="true"]', has_text="Release stabili").count() == 1, 4.0), state()["channel_posts"])
    # check: a new commit appears
    mock.set(klippeye_incoming=[{"sha": "f1", "author": "t", "date": "1760000000", "subject": "Release 1.0.1", "message": ""}, {"sha": "f2", "author": "t", "date": "1759990000", "subject": "Soglie nuove", "message": ""}])
    pg.locator("button", has_text="Controlla se c'è una versione nuova").click()
    ok("'Controlla' asks Moonraker to look", wait_until(lambda: any(a[0] == "refresh" for a in state()["update_log"]), 3.0), state()["update_log"])
    ok("... and the page announces release 1.0.1 with the commits", wait_until(lambda: "Disponibile la release 1.0.1" in pg.locator(".drawer__body").inner_text() and "ora hai la 1.0.0" in pg.locator(".drawer__body").inner_text(), 6.0), pg.locator(".drawer__body").inner_text()[:600])
    ok("... listing what changed", "Release 1.0.1" in pg.locator(".set-commits").inner_text() and "Soglie nuove" in pg.locator(".set-commits").inner_text())
    ok("the update button is there", pg.locator("button", has_text="Aggiorna KlippEye").count() == 1 and not pg.locator("button", has_text="Aggiorna KlippEye").is_disabled())
    P.shot(out + "/software_update.png")
    pg.locator("button", has_text="Aggiorna KlippEye").click(); P.settle(700)
    ok("the menu closes and the confirmation opens", pg.locator(".drawer").count() == 0 and "Aggiornare KlippEye?" in pg.locator(".sheet-card").inner_text())
    sheet = pg.locator(".sheet-card").inner_text()
    ok("it shows the installed and the new release, the commits and what will happen", "1.0.0" in sheet and "1.0.1" in sheet and "Soglie nuove" in sheet and "riavvia il backend" in sheet, sheet)
    P.shot(out + "/update_confirm.png", tall=False)
    pg.locator(".sheet-footer button", has_text="Aggiorna").click()
    ok("the dialog goes to the progress and says the backend is restarting", wait_until(lambda: "Il backend si riavvia" in pg.locator(".sheet-card").inner_text(), 8.0), pg.locator(".sheet-card").inner_text()[:400])
    ok("... the upgrade request went out for klippeye", ("upgrade", "klippeye") in [tuple(a) for a in state()["update_log"]])
    ok("... no failure is shown for the cut connection", "Fallito" not in pg.locator(".sheet-card").inner_text())
    P.shot(out + "/update_progress.png", tall=False)
    ok("when the backend is back the page reloads by itself", reloaded(P, 40.0))
    P.settle(1500)
    ok("... on the new release", state()["brain_release"] == "1.0.1")
    ok("[update] no uncaught error", [e for e in P.errors if "pageerror" in e] == [], P.errors)
    P.close()

    # the update is refused while printing / by Moonraker
    P = fresh(b, printing=True, vz={"commits_behind": [{"sha": "aaa", "subject": "x", "date": "1760000000"}], "commits_behind_count": 1})
    pg = P.pg
    open_menu(P); go(P, "software")
    ok("while printing the button is off and says why", wait_until(lambda: pg.locator("button", has_text="Aggiorna KlippEye").count() == 1, 5.0) and pg.locator("button", has_text="Aggiorna KlippEye").is_disabled() and "stampa in corso" in pg.locator(".drawer__body").inner_text())
    P.close()

    P = fresh(b, update_error="Update Refused: Klippy is printing", vz={"commits_behind": [{"sha": "aaa", "subject": "x", "date": "1760000000"}], "commits_behind_count": 1})
    pg = P.pg
    open_menu(P); go(P, "software")
    wait_until(lambda: pg.locator("button", has_text="Aggiorna KlippEye").count() == 1, 5.0)
    pg.locator("button", has_text="Aggiorna KlippEye").click(); P.settle(500)
    pg.locator(".sheet-footer button", has_text="Aggiorna").click()
    ok("a refusal of Moonraker is shown as a failure, in Italian", wait_until(lambda: "Fallito" in pg.locator(".sheet-card").inner_text() and "stampa in corso" in pg.locator(".sheet-card").inner_text(), 8.0), pg.locator(".sheet-card").inner_text()[:500])
    ok("... and the page is not reloaded", pg.evaluate("() => !!window.__marker"))
    pg.locator(".sheet-footer button", has_text="Chiudi").click(); P.settle(300)
    ok("... 'Chiudi' leaves the dialog", pg.locator(".sheet-card").count() == 0)
    P.close()

    # Moonraker did the update but did not restart the backend: the dashboard restarts it
    P = fresh(b, update_restart="no", vz={"commits_behind": [{"sha": "aaa", "subject": "x", "date": "1760000000"}], "commits_behind_count": 1})
    pg = P.pg
    open_menu(P); go(P, "software")
    wait_until(lambda: pg.locator("button", has_text="Aggiorna KlippEye").count() == 1, 5.0)
    pg.locator("button", has_text="Aggiorna KlippEye").click(); P.settle(500)
    pg.locator(".sheet-footer button", has_text="Aggiorna").click()
    ok("[no restart] the dialog waits, then restarts the backend itself (service klippeye) and reloads", reloaded(P, 70.0) and ("services/restart", "klippeye") in actions(), (actions(), pg.locator(".sheet-card").inner_text()[:300] if pg.locator(".sheet-card").count() else ""))
    P.close()

    # the repository was changed by hand: the page offers the recovery
    P = fresh(b, vz={"is_dirty": True, "is_valid": False, "warnings": ["Repo is dirty: file modificati a mano"]})
    pg = P.pg
    open_menu(P); go(P, "software")
    ok("a dirty repository: a warning and a recovery button instead of Aggiorna", wait_until(lambda: pg.locator("button", has_text="Ripristina i file del programma").count() == 1, 5.0) and "modificati a mano" in pg.locator(".drawer__body").inner_text() and pg.locator("button", has_text="Aggiorna KlippEye").count() == 0, pg.locator(".drawer__body").inner_text()[:500])
    pg.locator("button", has_text="Ripristina i file del programma").click(); P.settle(500)
    ok("the recovery asks first and says what stays untouched", "Ripristinare i file di KlippEye?" in pg.locator(".sheet-card").inner_text() and "non si toccano" in pg.locator(".sheet-card").inner_text())
    pg.locator(".sheet-footer button", has_text="Ripristina").click()
    ok("[recover] the backend restarts, the page reloads", reloaded(P, 45.0) and ("recover", "klippeye") in [tuple(a) for a in state()["update_log"]], state()["update_log"])
    ok("[recover] Moonraker sees the repository in order", state()["klippeye_info"]["is_valid"] and not state()["klippeye_info"]["is_dirty"])
    P.close()

    # rollback
    P = fresh(b, vz={"version": "v0.0.0-4", "remote_version": "v0.0.0-4", "rollback_version": "v0.0.0-3"}, brain_release="1.0.1")
    pg = P.pg
    open_menu(P); go(P, "software")
    ok("a rollback is offered when there is a version to go back to", wait_until(lambda: pg.locator("button", has_text="Torna alla versione precedente").count() == 1, 5.0))
    pg.locator("button", has_text="Torna alla versione precedente").click(); P.settle(500)
    ok("it asks and names the version", "Tornare alla versione precedente?" in pg.locator(".sheet-card").inner_text() and "v0.0.0-3" in pg.locator(".sheet-card").inner_text())
    pg.locator(".sheet-footer button", has_text="Torna indietro").click()
    ok("[rollback] the backend restarts and the page reloads", reloaded(P, 45.0) and ("rollback", "klippeye") in [tuple(a) for a in state()["update_log"]] and state()["brain_release"] == "1.0.0", (state()["update_log"], state()["brain_release"]))
    P.close()

    # Moonraker does not know KlippEye
    P = fresh(b, no_klippeye=True)
    pg = P.pg
    open_menu(P); go(P, "software")
    ok("Moonraker without the klippeye entry: the page tells how to connect it", wait_until(lambda: "Moonraker non conosce ancora KlippEye" in pg.locator(".drawer__body").inner_text() and "install.sh" in pg.locator(".drawer__body").inner_text(), 5.0), pg.locator(".drawer__body").inner_text()[:500])
    P.close()

    # old backend
    P = fresh(b, brain="old")
    pg = P.pg
    open_menu(P); go(P, "software")
    ok("an old backend: the page explains how to install release 1.0", wait_until(lambda: "precedente alla 1.0" in pg.locator(".drawer__body").inner_text() and "install.sh" in pg.locator(".drawer__body").inner_text(), 4.0), pg.locator(".drawer__body").inner_text()[:400])
    P.close()

    # this page and the backend differ
    P = fresh(b, brain_release="2.0.0")
    pg = P.pg
    open_menu(P); go(P, "software")
    ok("the page asks to reload when the backend is a newer release", wait_until(lambda: "ma il backend è la" in pg.locator(".drawer__body").inner_text(), 4.0) and pg.locator("button", has_text="Ricarica").count() == 1, pg.locator(".drawer__body").inner_text()[:400])
    P.close()

    # restart of the backend from the page
    P = fresh(b)
    pg = P.pg
    open_menu(P); go(P, "software")
    wait_until(lambda: pg.locator("button:has-text('Riavvia il backend'), .file-action-row:has-text('Riavvia il backend')").count() >= 1, 5.0)
    pg.locator("text=Riavvia il backend").first.click()
    ok("restarting the backend: the menu closes, the request goes to Moonraker for the service klippeye", wait_until(lambda: ("services/restart", "klippeye") in actions(), 4.0) and wait_until(lambda: pg.locator(".drawer").count() == 0, 3.0), actions())
    ok("... the ring shows 'Riavvio del backend' while it is away", wait_until(lambda: "Riavvio del backend" in pg.locator("body").inner_text(), 4.0), pg.locator("body").inner_text()[:300])
    ok("... and the page reloads by itself afterwards", reloaded(P, 60.0))
    P.close()

    # Klipper is off (Moonraker answers "no Klipper"): the backend is back when it answers, not when Klipper is ready
    P = fresh(b, disconnected=True)
    pg = P.pg
    open_menu(P); go(P, "software")
    wait_until(lambda: "Riavvia il backend" in pg.locator(".drawer__body").inner_text(), 5.0)
    pg.locator("text=Riavvia il backend").first.click()
    ok("[no Klipper] restarting the backend reloads the page once the backend answers again", wait_until(lambda: ("services/restart", "klippeye") in actions(), 4.0) and reloaded(P, 40.0), actions())
    P.close()

    # the power menu
    P = fresh(b)
    pg = P.pg
    pg.locator("button[aria-label='Alimentazione e servizi']").click(); P.settle(800)
    ok("power menu: the backend is listed under its friendly name, the notifications too", wait_until(lambda: pg.locator(".svc-row__name", has_text="KlippEye (backend)").count() == 1 and pg.locator(".svc-row__name", has_text="KlippEye notifiche").count() == 1, 4.0), pg.locator(".svc-row__name").all_inner_texts())
    ok("... the backend has no Stop button (nothing could start it again), the notifications have", pg.locator("button[aria-label='Ferma KlippEye (backend)']").count() == 0 and pg.locator("button[aria-label='Ferma KlippEye notifiche']").count() == 1)
    pg.locator("button[aria-label='Riavvia KlippEye (backend)']").click()
    ok("power menu: restarting the backend asks Moonraker for the service klippeye", wait_until(lambda: ("services/restart", "klippeye") in actions(), 4.0), actions())
    ok("... and the page reloads when the backend is back", reloaded(P, 60.0))
    P.close()

    # while printing, the restart of the backend asks first
    P = fresh(b, printing=True)
    pg = P.pg
    open_menu(P); go(P, "software")
    pg.locator("text=Riavvia il backend").first.click(); P.settle(600)
    ok("printing: the restart of the backend asks first and says the print goes on", "Riavviare il backend?" in pg.locator(".confirm-card").inner_text() and "non si ferma" in pg.locator(".confirm-card").inner_text() and ("services/restart", "klippeye") not in actions(), pg.locator("body").inner_text()[:300])
    pg.locator(".confirm-card button", has_text="Annulla").click(); P.settle(300)
    ok("... 'Annulla' sends nothing", ("services/restart", "klippeye") not in actions())
    P.close()

    # a narrow phone and a wide screen: nothing sticks out
    for vw, vh in ((360, 740), (1280, 800)):
        P = fresh(b, vw, vh, vz={"commits_behind": [{"sha": "aaa", "subject": "Una descrizione molto lunga di una modifica che deve andare a capo senza uscire dal pannello laterale di KlippEye", "date": "1760000000"}], "commits_behind_count": 1})
        pg = P.pg
        open_menu(P); go(P, "software"); P.settle(900)
        o = pg.evaluate("() => { const b = document.querySelector('.drawer__body'); return { page: document.documentElement.scrollWidth - document.documentElement.clientWidth, body: b.scrollWidth - b.clientWidth }; }")
        ok("[%dpx] software page: nothing sticks out sideways" % vw, o["page"] <= 0 and o["body"] <= 0, o)
        P.shot(out + "/software_%d.png" % vw, tall=False)
        pg.click('.drawer button[aria-label="Indietro"]'); P.settle(400); go(P, "detector"); P.settle(900)
        o = pg.evaluate("() => { const b = document.querySelector('.drawer__body'); return { page: document.documentElement.scrollWidth - document.documentElement.clientWidth, body: b.scrollWidth - b.clientWidth }; }")
        ok("[%dpx] thresholds page: nothing sticks out sideways" % vw, o["page"] <= 0 and o["body"] <= 0, o)
        P.shot(out + "/detector_%d.png" % vw, tall=False)
        ghosts = pg.evaluate(GHOST_JS)
        # position-readout is a class of the original dashboard that never had a style
        unknown = [c for c in ghosts["unknown"] if c != "position-readout" and not c.startswith(("is-", "has-"))]
        ok("[%dpx] every class used has a style" % vw, unknown == [], unknown)
        P.close()
    b.close()

print("\nFAILS:", FAILS if FAILS else "none")
print("ALLDONE" if not FAILS else "ALLDONE_WITH_FAILURES")
sys.exit(1 if FAILS else 0)
