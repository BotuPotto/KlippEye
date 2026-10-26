"""The Klipper state panel (Mainsail's 'Klipper reports: ...') and the header's power menu.
Usage: klipper_state_test.py <html> <outdir> <port> [--repro]   (--repro: only print, never fail)"""
import sys, os, re, json, time, urllib.request
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
REPRO = "--repro" in sys.argv
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
FAILS = []

SHUT_MSG = "MCU 'mcu' shutdown: Timer too close\nOnce the underlying issue is corrected, use the\n\"FIRMWARE_RESTART\" command to reset the firmware,\nreload the config, and restart the host software.\nPrinter is shutdown"
CFG_ERR = "Option 'sensor_pin' in section 'extruder' must be specified\nOnce the underlying issue is corrected, use the\n\"RESTART\" command to reload the config"

BANNER = """() => { const b = document.querySelector('.klipper-state'); if (!b) return null;
  const q = (s) => b.querySelector(s);
  return { tone: b.dataset.tone, loading: b.classList.contains('is-loading'), role: b.getAttribute('role'), title: q('.klipper-state__title').innerText,
           message: q('.klipper-state__message') ? q('.klipper-state__message').innerText : null,
           text: q('.klipper-state__text') ? q('.klipper-state__text').innerText : null,
           buttons: [...b.querySelectorAll('.klipper-state__actions button')].map((x) => x.innerText.trim()) }; }"""
SAMPLER = """() => { window.__samples = []; window.__mark = 'alive'; setInterval(() => { const b = document.querySelector('.klipper-state');
  window.__samples.push(b ? [b.dataset.tone, b.classList.contains('is-loading'), b.querySelector('.klipper-state__title').innerText,
    b.querySelector('.klipper-state__message') ? b.querySelector('.klipper-state__message').innerText : ''] : null); }, 40); }"""


def ok(name, cond, extra=""):
    if not cond and not REPRO: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra != "" else ""))


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def fresh(w=390, h=844, wait=1800, tab="home", **st):
    mock.reset()
    if st: mock.set(**st)
    P = Page(b, mock, w, h)
    P.goto(tab, wait)
    P.pg.evaluate(SAMPLER)
    return P


def banner(P): return P.pg.evaluate(BANNER)
def errs(P):
    # the browser logs every 502 / 503 answer: Moonraker saying "no Klipper" is what these tests provoke on purpose
    return [e for e in P.errors if ("pageerror" in e or "console.error" in e) and not re.search(r"status of (502|503)", e)]


def wait_for(P, pred, limit):
    t0 = time.time()
    while time.time() - t0 < limit:
        try:
            if pred(): return round(time.time() - t0, 1)
        except Exception:
            pass
        P.pg.wait_for_timeout(100)
    return None


def reloaded(P): return P.pg.evaluate("() => window.__mark") is None
def click(P, text, exact=True):
    P.pg.get_by_role("button", name=text, exact=exact).first.click()
def actions(): return [tuple(a) for a in state()["actions"]]
def samples(P): return P.pg.evaluate("() => window.__samples")


with sync_playwright() as p:
    b = p.chromium.launch()

    # ------------------------------------------------------------ 1. all well: no panel, light traffic
    P = fresh(wait=1500)
    P.take_reqs(); P.pg.wait_for_timeout(9000)
    infos = [r for r in P.take_reqs() if r["u"].startswith("/printer/info")]
    ok("[ready] no panel", banner(P) is None)
    ok("[ready] Klipper asked only now and then (<= 4 times in 9 s)", len(infos) <= 4, len(infos))
    ok("[ready] no page errors", not errs(P), errs(P)[:2]); P.close()

    # ------------------------------------------------------------ 2. shutdown / error at start-up
    P = fresh(webhooks="shutdown", webhooks_msg=SHUT_MSG)
    bn = banner(P)
    ok("[shutdown] panel shown with the orange tone and Mainsail's title", bn and bn["tone"] == "warn" and bn["title"] == "Klipper segnala: SHUTDOWN" and not bn["loading"], bn)
    ok("[shutdown] Klipper's own message, line breaks included", bn and bn["message"] == SHUT_MSG, bn and bn["message"])
    ok("[shutdown] restart and log buttons", bn and bn["buttons"] == ["Firmware restart", "Klipper restart", "Log Klipper", "Log Moonraker"], bn and bn["buttons"])
    ok("[shutdown] announced as an alert", bn and bn["role"] == "alert")
    P.shot_vp(f"{out}/shutdown_phone.png"); P.close()
    P = fresh(webhooks="error", webhooks_msg=CFG_ERR)
    bn = banner(P)
    ok("[error] red tone, title ERROR", bn and bn["tone"] == "error" and bn["title"] == "Klipper segnala: ERROR", bn)
    P.shot_vp(f"{out}/error_phone.png"); P.close()
    P = fresh(webhooks="startup", webhooks_msg="Printer is not ready\nThe klippy host software is attempting to connect.  Please\nretry in a few moments.")
    bn = banner(P)
    ok("[startup] blue tone, ring, message", bn and bn["tone"] == "info" and bn["loading"] and "attempting to connect" in (bn["message"] or ""), bn)
    P.shot_vp(f"{out}/startup_phone.png"); P.close()

    # ------------------------------------------------------------ 3. Firmware restart that works: ring, then the page reloads
    P = fresh(webhooks="shutdown", webhooks_msg=SHUT_MSG)
    click(P, "Firmware restart"); P.pg.wait_for_timeout(300)
    bn = banner(P)
    ok("[restart ok] the ring appears at once", bn and bn["loading"] and bn["title"] == "Riavvio del firmware...", bn)
    ok("[restart ok] the old message is gone while it restarts", bn and bn["message"] is None, bn)
    P.pg.screenshot(path=f"{out}/restarting_phone.png")
    t = wait_for(P, lambda: reloaded(P), 20)
    ok("[restart ok] when Klipper is ready again the page reloads", t is not None, t)
    P.pg.wait_for_timeout(1500)
    ok("[restart ok] and no panel after it", banner(P) is None)
    ok("[restart ok] one request to Moonraker's endpoint, no G-code on top", [a for a in actions() if a[0].startswith(("printer/", "gcode:"))] == [("printer/firmware_restart", "")], actions())
    P.close()

    # ------------------------------------------------------------ 4. Klipper restart that fails: the panel comes back with the NEW error
    P = fresh(webhooks="shutdown", webhooks_msg=SHUT_MSG, restart_result="error", restart_result_msg=CFG_ERR)
    click(P, "Klipper restart"); P.pg.wait_for_timeout(300)
    ok("[restart fails] ring while restarting", (banner(P) or {}).get("loading") is True, banner(P))
    t = wait_for(P, lambda: (banner(P) or {}).get("tone") == "error" and not (banner(P) or {}).get("loading"), 20)
    bn = banner(P)
    ok("[restart fails] the panel is back, red, with the new error", t is not None and bn["message"] == CFG_ERR and bn["title"] == "Klipper segnala: ERROR", bn)
    ok("[restart fails] with the restart buttons again", bn and "Firmware restart" in bn["buttons"], bn and bn["buttons"])
    P.pg.wait_for_timeout(250)
    seen = samples(P)
    after_click = [s for s in seen[seen.index(next(s for s in seen if s and s[1])) :]] if any(s and s[1] for s in seen) else []
    ok("[restart fails] the old message never showed again once the ring was up", all(not (s and s[3] == SHUT_MSG) for s in after_click), [s for s in after_click if s and s[3] == SHUT_MSG][:1])
    ok("[restart fails] the page did not reload", not reloaded(P))
    ok("[restart fails] ring phases seen: loading then error", any(s and s[1] for s in seen) and any(s and s[0] == "error" and not s[1] for s in seen))
    P.shot_vp(f"{out}/restart_failed_phone.png")
    ok("[restart fails] no page errors", not errs(P), errs(P)[:2]); P.close()

    # ------------------------------------------------------------ 5. the endpoint refuses: G-code is the fallback; if that fails too, it says so
    P = fresh(webhooks="shutdown", webhooks_msg=SHUT_MSG, restart_refuse=500)
    click(P, "Firmware restart")
    t = wait_for(P, lambda: reloaded(P), 20)
    ok("[endpoint refuses] the G-code fallback restarts it anyway", t is not None and ("gcode:FIRMWARE_RESTART", "") in actions(), (t, actions()))
    P.close()
    P = fresh(webhooks="shutdown", webhooks_msg=SHUT_MSG, restart_refuse=500, gcode_refuse=True)
    click(P, "Firmware restart"); P.pg.wait_for_timeout(1500)
    bn = banner(P)
    ok("[all refused] no ring, the old panel stays", bn and not bn["loading"] and bn["message"] == SHUT_MSG, bn)
    ok("[all refused] it says why", "Riavvio non riuscito" in " ".join(P.pg.locator(".toast").all_inner_texts()), P.pg.locator(".toast").all_inner_texts())
    ok("[all refused] nothing restarted", not reloaded(P)); P.close()

    # ------------------------------------------------------------ 6. Moonraker has no Klipper (disconnected)
    P = fresh(disconnected=True)
    bn = banner(P)
    ok("[disconnected] right after: ring + title 'Moonraker segnala: DISCONNECTED'", bn and bn["loading"] and bn["title"] == "Moonraker segnala: DISCONNECTED" and bn["tone"] == "neutral", bn)
    t = wait_for(P, lambda: not (banner(P) or {"loading": True})["loading"], 40)
    bn = banner(P)
    ok("[disconnected] after a while the explanation and the way out", t is not None and "klippy_uds_address" in (bn["text"] or "") and bn["buttons"] == ["Riavvia il servizio Klipper", "Log Moonraker"], (t, bn))
    P.shot_vp(f"{out}/disconnected_phone.png")
    click(P, "Riavvia il servizio Klipper"); P.pg.wait_for_timeout(300)
    ok("[disconnected] restart of the service shows the ring", (banner(P) or {}).get("loading") is True and "servizio Klipper" in banner(P)["title"], banner(P))
    t = wait_for(P, lambda: reloaded(P), 25)
    ok("[disconnected] and the page reloads when Klipper is back", t is not None and ("services/restart", "klipper") in actions(), (t, actions())); P.close()

    # ------------------------------------------------------------ 7. emergency stop, console line, Moonraker away
    P = fresh()
    P.pg.locator("button[aria-label='Emergency stop']").click()
    t = wait_for(P, lambda: banner(P) is not None, 5)
    bn = banner(P)
    ok("[emergency stop] the panel appears within 2 s with Klipper's own message", t is not None and t <= 2 and bn and "M112" in (bn["message"] or ""), (t, bn))
    P.close()
    P = fresh()
    mock.set(webhooks="shutdown", webhooks_msg=SHUT_MSG)
    t = wait_for(P, lambda: banner(P) is not None, 8)
    ok("[console line] a shutdown line asks Klipper at once (panel within 2.5 s)", t is not None and t <= 2.5, t); P.close()
    P = fresh()
    mock.set(moonraker_down=True); P.pg.wait_for_timeout(7000)
    ok("[Moonraker away, nobody asked] no panel (it says nothing about Klipper)", banner(P) is None, banner(P))
    mock.set(moonraker_down=False); P.pg.wait_for_timeout(5000)
    ok("[Moonraker back] still no panel, no reload", banner(P) is None and not reloaded(P)); P.close()

    # ------------------------------------------------------------ 8. SAVE_CONFIG restarts Klipper: ring, no reload, capabilities read again
    P = fresh()
    P.pg.locator("button[aria-label='Save config']").click(); P.pg.wait_for_timeout(500)
    P.pg.get_by_role("button", name="Salva", exact=True).click(); P.pg.wait_for_timeout(300)
    bn = banner(P)
    ok("[SAVE_CONFIG] ring at once", bn and bn["loading"] and bn["title"].startswith("Salvataggio e riavvio"), bn)
    P.take_reqs()
    t = wait_for(P, lambda: banner(P) is None, 20)
    ok("[SAVE_CONFIG] gone when Klipper is back", t is not None, t)
    P.pg.wait_for_timeout(1500)
    ok("[SAVE_CONFIG] the page did not reload", not reloaded(P))
    ok("[SAVE_CONFIG] capabilities read again", any(r["u"].startswith("/printer/gcode/help") for r in P.take_reqs()))
    P.close()

    # ------------------------------------------------------------ 9. the power menu
    P = fresh()
    P.pg.locator("button[aria-label='Alimentazione e servizi']").click(); P.pg.wait_for_timeout(700)
    sheet = P.pg.locator(".sheet-overlay--power")
    ok("[menu] opens", sheet.count() == 1)
    names = P.pg.locator(".svc-row__name").all_inner_texts()
    ok("[menu] services as Mainsail lists them (klipper_mcu left out, sorted)", names == ["KlipperScreen", "Crowsnest", "Klipper", "Moonraker", "Sonar"], names)
    states = P.pg.locator(".svc-row__state").all_inner_texts()
    ok("[menu] states in Italian", states[0].startswith("in errore") and states[1].startswith("attivo") and states[4].startswith("fermo"), states)
    ok("[menu] Moonraker has no stop button, a stopped service offers start", P.pg.locator("button[aria-label='Ferma Moonraker']").count() == 0 and P.pg.locator("button[aria-label='Avvia Sonar']").count() == 1 and P.pg.locator("button[aria-label='Ferma Sonar']").is_disabled())
    sections = P.pg.locator(".power-sheet__label").all_text_contents()
    ok("[menu] sections Klipper / Servizi / Raspberry", sections == ["Klipper", "Servizi", "Raspberry"], sections)
    P.pg.screenshot(path=f"{out}/menu_phone.png")
    P.pg.locator("button[aria-label='Riavvia Crowsnest']").click(); P.pg.wait_for_timeout(600)
    ok("[menu] a service restarts at once when nothing prints", ("services/restart", "crowsnest") in actions() and P.pg.locator(".confirm-overlay").count() == 0, actions())
    ok("[menu] the sheet closes after the action", P.pg.locator(".sheet-overlay--power").count() == 0)
    P.pg.evaluate("() => { document.querySelector('iframe').dataset.mark = 'old'; }")
    t = wait_for(P, lambda: P.pg.evaluate("() => document.querySelector('iframe').dataset.mark") is None, 12)
    ok("[menu] restarting the camera service loads the camera view again", t is not None, t)
    ok("[menu] no page errors", not errs(P), errs(P)[:2]); P.close()

    P = fresh()
    P.pg.locator("button[aria-label='Alimentazione e servizi']").click(); P.pg.wait_for_timeout(600)
    P.pg.locator("button[aria-label='Ferma Sonar']").is_disabled()
    P.pg.locator("button[aria-label='Avvia Sonar']").click(); P.pg.wait_for_timeout(500)
    ok("[menu] start of a stopped service", ("services/start", "sonar") in actions(), actions())
    P.pg.locator("button[aria-label='Alimentazione e servizi']").click(); P.pg.wait_for_timeout(600)
    P.pg.locator("button[aria-label='Ferma Crowsnest']").click(); P.pg.wait_for_timeout(500)
    ok("[menu] stop of a service", ("services/stop", "crowsnest") in actions(), actions())
    P.close()

    # a print is running: asked first
    P = fresh(printing=True)
    P.pg.locator("button[aria-label='Alimentazione e servizi']").click(); P.pg.wait_for_timeout(600)
    click(P, "Klipper restart", exact=False); P.pg.wait_for_timeout(500)
    ok("[menu, printing] asks first and says the print will fail", P.pg.locator(".confirm-card").count() == 1 and "fallirà" in P.pg.locator(".confirm-card").inner_text(), P.pg.locator(".confirm-card").all_inner_texts())
    P.pg.screenshot(path=f"{out}/confirm_printing_phone.png")
    click(P, "Annulla"); P.pg.wait_for_timeout(500)
    ok("[menu, printing] cancel: nothing sent", [a for a in actions() if a[0].startswith("printer/")] == [])
    P.pg.locator("button[aria-label='Alimentazione e servizi']").click(); P.pg.wait_for_timeout(600)
    click(P, "Klipper restart", exact=False); P.pg.wait_for_timeout(500)
    P.pg.locator(".confirm-card").get_by_role("button", name="Riavvia", exact=True).click(); P.pg.wait_for_timeout(500)
    ok("[menu, printing] confirmed: restart goes out, ring shows", ("printer/restart", "") in actions() and (banner(P) or {}).get("loading") is True, (actions(), banner(P)))
    P.close()

    # Moonraker restarting itself: its answer is cut, the ring waits, the page reloads
    P = fresh()
    P.pg.locator("button[aria-label='Alimentazione e servizi']").click(); P.pg.wait_for_timeout(600)
    P.pg.locator("button[aria-label='Riavvia Moonraker']").click(); P.pg.wait_for_timeout(700)
    bn = banner(P)
    ok("[Moonraker restart] ring 'Riavvio di Moonraker' (the cut answer is no failure)", bn and bn["loading"] and bn["title"] == "Riavvio di Moonraker...", bn)
    t = wait_for(P, lambda: reloaded(P), 30)
    ok("[Moonraker restart] reloads once Moonraker and Klipper are back", t is not None, t); P.close()

    # the Raspberry
    P = fresh()
    P.pg.locator("button[aria-label='Alimentazione e servizi']").click(); P.pg.wait_for_timeout(600)
    click(P, "Riavvia il Raspberry", exact=False); P.pg.wait_for_timeout(500)
    ok("[Raspberry reboot] always asks first", P.pg.locator(".confirm-card").count() == 1 and ("reboot", "") not in actions())
    P.pg.locator(".confirm-card").get_by_role("button", name="Riavvia", exact=True).click(); P.pg.wait_for_timeout(2500)
    bn = banner(P)
    ok("[Raspberry reboot] ring while the machine is away, with the right words", bn and bn["loading"] and bn["title"] == "Riavvio del Raspberry..." and "Raspberry" in (bn["text"] or ""), bn)
    P.pg.screenshot(path=f"{out}/reboot_phone.png")
    t = wait_for(P, lambda: reloaded(P), 40)
    ok("[Raspberry reboot] reloads when everything is back", t is not None, t); P.close()

    P = fresh()
    P.pg.locator("button[aria-label='Alimentazione e servizi']").click(); P.pg.wait_for_timeout(600)
    click(P, "Spegni il Raspberry", exact=False); P.pg.wait_for_timeout(500)
    P.pg.locator(".confirm-card").get_by_role("button", name="Spegni", exact=True).click(); P.pg.wait_for_timeout(2500)
    bn = banner(P)
    ok("[Raspberry shutdown] says it is shutting down, no ring", bn and not bn["loading"] and bn["title"] == "Il Raspberry si sta spegnendo", bn)
    ok("[Raspberry shutdown] request sent", ("shutdown", "") in actions())
    P.pg.screenshot(path=f"{out}/shutdown_host_phone.png"); P.close()

    # Klipper away: its controls are not offered, the services are
    P = fresh(disconnected=True)
    P.pg.locator("button[aria-label='Alimentazione e servizi']").click(); P.pg.wait_for_timeout(700)
    sections = P.pg.locator(".power-sheet__label").all_text_contents()
    ok("[menu, no Klipper] the Klipper section is hidden", sections == ["Servizi", "Raspberry"], sections); P.close()

    # a restart in progress: its entries are greyed out
    P = fresh(webhooks="shutdown", webhooks_msg=SHUT_MSG)
    click(P, "Klipper restart"); P.pg.wait_for_timeout(400)
    P.pg.locator("button[aria-label='Alimentazione e servizi']").click(); P.pg.wait_for_timeout(600)
    ok("[menu, restarting] Klipper entries disabled", P.pg.get_by_role("button", name="Klipper restart", exact=False).first.is_disabled())
    P.close()

    # ------------------------------------------------------------ 10. layouts
    for w, h_, tag in ((360, 780, "360"), (390, 844, "390"), (1440, 900, "wide")):
        P = fresh(w, h_, webhooks="shutdown", webhooks_msg=SHUT_MSG)
        hdr = P.pg.evaluate("() => { const r = document.querySelector('.app-header__bar'); const kids = [...document.querySelectorAll('.app-header__actions > button')].map(b => b.getBoundingClientRect()); return { w: r.scrollWidth, cw: r.clientWidth, actions: kids.length, right: Math.max(...kids.map(k => k.right)), left: Math.min(...kids.map(k => k.left)), brandRight: document.querySelector('.app-header__brand').getBoundingClientRect().right }; }")
        ok(f"[header {tag}] 3 round buttons fit beside the brand", hdr["actions"] == 3 and hdr["w"] <= hdr["cw"] and hdr["left"] >= hdr["brandRight"] + 4 and hdr["right"] <= w, hdr)
        P.shot_vp(f"{out}/header_{tag}.png", vh=h_)
        P.pg.locator("button[aria-label='Alimentazione e servizi']").click(); P.pg.wait_for_timeout(700)
        P.pg.screenshot(path=f"{out}/menu_{tag}.png")
        ok(f"[menu {tag}] fits the screen", P.pg.evaluate("() => { const c = document.querySelector('.sheet-overlay--power .sheet-card').getBoundingClientRect(); return c.top >= 0 && c.bottom <= innerHeight && c.left >= 0 && c.right <= innerWidth; }"))
        ok(f"[page {tag}] no page errors", not errs(P), errs(P)[:2]); P.close()

    b.close()
print("\nFAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
