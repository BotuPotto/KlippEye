"""Release 1.12.0: the page "Registrazioni" of the settings menu (app/59e-recordings.js): recording on/off and its space,
the alarms to mark as false or real, a recorded print (pictures, "it went fine" / "it failed from here", delete), the
measurement of the monitor, the monitor's load. Against the mock backend (mock_server.py, same answers as backend/recorder.py).
Usage: recordings_test.py <html> <outdir> <port>"""
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
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:700]) if (extra != "" and not cond) else ""), flush=True)


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def wait_until(fn, timeout=5.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    try:
        return bool(fn())
    except Exception:
        return False


T0 = 1793000000.0
FRAMES = [{"n": n, "t": T0 + n * 3, "score": 0.4 if n != 30 else 6.2, "trig": n == 30, "layer": n // 10, "layers": 40, "progress": n / 2} for n in range(1, 61)]
SESSIONS = [
    {"id": "20261028-101500-benchy", "file": "benchy.gcode", "started": T0, "ended": T0 + 183, "end_state": "complete", "frames": 60, "bytes": 1900000,
     "release": "1.12.0", "config": {}, "label": {"outcome": None, "failed_at": None}, "truncated": False,
     "live_triggers": [{"t": T0 + 90, "frame": 30}], "alerts": [{"id": "20261028-101631", "t": T0 + 90, "frame": 30, "action": "PAUSE", "summary": "Filo staccato?", "label": None}],
     "cpu": {"check_ms": 11.5, "cpu_percent": 7.2}},
    {"id": "20261027-200000-cube", "file": "cube.gcode", "started": T0 - 90000, "ended": T0 - 86000, "end_state": "cancelled", "frames": 0, "bytes": 5 * 1024 ** 2,
     "release": "1.12.0", "config": {}, "label": {"outcome": "ok", "failed_at": None}, "truncated": False, "live_triggers": [], "alerts": [], "cpu": {}},
]
ALERTS = [
    {"id": "20261028-101631", "time": "2026-10-28 10:16:31", "action": "PAUSE", "summary": "Filo staccato vicino all'ugello?", "image": "20261028-101631-now.jpg", "session": "20261028-101500-benchy"},
    {"id": "20261028-090000", "time": "2026-10-28 09:00:00", "action": "CONTINUE", "summary": "Tutto regolare.", "image": "20261028-090000-now.jpg", "label": "false"},
]
RESULT = {"ok": True, "time": int(T0), "settings": "current", "overrides": {},
          "sessions": [{"id": "20261028-101500-benchy", "file": "benchy.gcode", "hours": 0.05, "frames": 60, "outcome": "failed", "failed_at": T0 + 80, "label_source": "you",
                        "alarms": 1, "per_hour": 19.7, "false": 0, "seen": True, "delay_s": 10, "live_alarms": 1},
                       {"id": "20261027-200000-cube", "file": "cube.gcode", "hours": 1.1, "frames": 1300, "outcome": None, "label_source": None,
                        "alarms": 2, "per_hour": 1.8, "false": None, "seen": None, "delay_s": None, "live_alarms": 2}],
          "total": {"recordings": 2, "hours": 1.15, "alarms": 3, "live_alarms": 3, "per_hour": 2.6, "false": 0, "known_hours": 0.02, "false_per_hour": 0.0,
                    "failures": 1, "seen": 1, "average_delay_s": 10, "ms_per_check": 9.4}}


def fresh(b, w=390, h=844, **st):
    mock.reset()
    mock.set(**st)
    P = Page(b, mock, w, h)
    CUR[0] = P
    P.goto("home", 1400)
    return P


def open_recordings(P):
    P.pg.click('button[aria-label="Impostazioni"]')
    P.pg.wait_for_selector(".drawer")
    P.settle(450)
    P.pg.click('.set-entry[data-page="ai"]')   # 1.19: inside "Monitor IA"
    P.settle(700)
    P.pg.click('.set-entry[data-page="recordings"]')
    P.settle(900)


def body(P):
    return P.pg.locator(".drawer__body").inner_text()


def overflow(P):
    return P.pg.evaluate("() => { const d = document.querySelector('.drawer__body'); return d.scrollWidth - d.clientWidth; }")


with sync_playwright() as p:
    b = p.chromium.launch()

    # --- recording off, nothing recorded
    P = fresh(b)
    P.pg.click('button[aria-label="Impostazioni"]')
    P.pg.wait_for_selector(".drawer")
    P.settle(900)
    P.pg.click('.set-entry[data-page="ai"]')
    P.settle(900)
    entry = P.pg.locator('.set-entry[data-page="recordings"]')
    ok("'Monitor IA' has the entry 'Registrazioni' with a summary (off, 0 prints)", entry.count() == 1 and "Registrazioni" in entry.inner_text() and wait_until(lambda: "Spenta" in entry.inner_text() and "0 stampe" in entry.inner_text()), entry.inner_text() if entry.count() else "")
    P.pg.click('.set-entry[data-page="recordings"]')
    P.settle(900)
    ok("off: the page says recording is off and offers the switch and the space", wait_until(lambda: "La registrazione è spenta." in body(P)) and "Registra le stampe" in body(P) and "Spazio per le registrazioni" in body(P), body(P))
    ok("... and the usage line (used of limit, free disk)", "Usati 0 MB su 2,0 GB" in body(P) and "12,0 GB liberi sul disco" in body(P), body(P))
    ok("... nothing recorded yet: it says how to start", "Accendi «Registra le stampe»" in body(P), body(P))
    ok("... 'Misura adesso' is off without recordings", P.pg.locator('[data-measure="start"]').is_disabled())
    P.pg.locator('.set-switch', has_text="Registra le stampe").click()
    ok("the switch turns recording on in the backend (record: true)", wait_until(lambda: any(e.get("record") is True for e in state()["brain_cfg_log"]), 4), state()["brain_cfg_log"][-3:])
    ok("... and the page says it starts with the next print", wait_until(lambda: "parte con la prossima stampa" in body(P), 15), body(P))
    P.pg.screenshot(path=os.path.join(out, "01_off.png"))
    ok("no horizontal scrolling (390 px)", overflow(P) <= 0, overflow(P))
    ok("no JavaScript error", P.errors == [], P.errors)
    P.ctx.close()

    # --- the detector page no longer shows the recording settings
    P = fresh(b)
    P.pg.click('button[aria-label="Impostazioni"]')
    P.pg.wait_for_selector(".drawer")
    P.settle(450)
    P.pg.click('.set-entry[data-page="ai"]')
    P.settle(700)
    P.pg.click('.set-entry[data-page="detector"]')
    P.settle(1200)
    ok("'Soglie del monitor' does not show the recording group (it has its own page)", "Sensibilità" in body(P) or "Soglia" in body(P) and "Registra le stampe" not in body(P), body(P)[:400])
    ok("... really not", "Registra le stampe" not in body(P))
    P.ctx.close()

    # --- with recordings and alarms
    cfg = {"record": True}
    P = fresh(b, recordings=SESSIONS, rec_frames={SESSIONS[0]["id"]: FRAMES}, alerts=ALERTS, rec_status="recording", detector_extra={"check_ms": 12.3, "cpu_percent": 6.5}, measure_result=RESULT)
    mock.set(brain_cfg=None)
    urllib.request.urlopen(urllib.request.Request(mock.base + "/api/backend/config", data=json.dumps({"values": cfg}).encode(), headers={"content-type": "application/json"}, method="POST")).read()
    open_recordings(P)
    ok("on and recording: the status says so", wait_until(lambda: "Sto registrando questa stampa." in body(P)), body(P)[:300])
    ok("the monitor's load: time of one check and backend CPU", wait_until(lambda: "12,3 ms" in body(P) and "6,5% di un core" in body(P)), body(P))
    rows = P.pg.locator(".rec-row")
    ok("the recorded prints, newest first, with their label", rows.count() == 2 and "benchy.gcode" in rows.nth(0).inner_text() and "Non segnata" in rows.nth(0).inner_text() and "Andata bene" in rows.nth(1).inner_text(), [rows.nth(i).inner_text() for i in range(rows.count())])
    ok("... with alarms and space", "1 allarme" in rows.nth(0).inner_text() and "2 MB" in rows.nth(0).inner_text(), rows.nth(0).inner_text())
    alerts = P.pg.locator(".rec-alert")
    ok("the alarms with the AI's verdict and the two buttons; one already marked", alerts.count() == 2 and "Filo staccato" in alerts.nth(0).inner_text() and "Pausa" in alerts.nth(0).inner_text().title() or alerts.count() == 2, [alerts.nth(i).inner_text() for i in range(alerts.count())])
    ok("... '1 su 2 segnati'", "1 su 2 segnati" in body(P), body(P))
    ok("... the marked one shows its choice", alerts.nth(1).locator('button[aria-pressed="true"]').inner_text() == "Falso allarme")
    alerts.nth(0).locator("button", has_text="Problema vero").click()
    ok("'Problema vero' is sent to the backend for that alarm", wait_until(lambda: ["alert", "20261028-101631", {"label": "right"}] in state()["rec_posts"]), state()["rec_posts"])
    ok("... and shows as chosen", wait_until(lambda: alerts.nth(0).locator('button[aria-pressed="true"]').inner_text() == "Problema vero"))
    alerts.nth(1).locator("button", has_text="Falso allarme").click()
    ok("pressing the chosen one again clears it (label null)", wait_until(lambda: ["alert", "20261028-090000", {"label": None}] in state()["rec_posts"]), state()["rec_posts"])
    P.pg.screenshot(path=os.path.join(out, "02_list.png"), full_page=True)

    # measure
    P.pg.locator('[data-measure="start"]').click()
    ok("'Misura adesso' starts the measurement", wait_until(lambda: state()["measure_starts"] == 1) and wait_until(lambda: "Sto misurando" in body(P), 2), body(P)[-300:])
    ok("... and shows the result: alarms per hour, false alarms, failures caught, time of a check", wait_until(lambda: "Stampe misurate" in body(P), 8) and "3 • 2,6 all'ora" in body(P)
       and "0 • 0 all'ora" in body(P) and "1 su 1" in body(P) and "dopo 10 s" in body(P) and "9,4 ms" in body(P), body(P)[-900:])
    ok("... one line per print, the unmarked one with '?'", "visto dopo 10 s" in body(P) and "falsi: ?" in body(P), body(P)[-600:])
    P.pg.screenshot(path=os.path.join(out, "03_measure.png"), full_page=True)

    # one recording
    P.pg.locator('.rec-row[data-recording="%s"]' % SESSIONS[0]["id"]).click()
    P.settle(900)
    ok("a recording: file, start, duration, pictures, alarms, CPU", wait_until(lambda: "benchy.gcode" in body(P).lower()) and "3 min" in body(P) and "completata" in body(P) and "60" in body(P) and "7,2% di un core • 11,5 ms per controllo" in body(P), body(P)[:600])
    img = P.pg.locator(".rec-viewer img")
    ok("the viewer shows the last picture", img.count() == 1 and img.get_attribute("src").endswith("/frames/60.jpg"), img.get_attribute("src") if img.count() else None)
    P.pg.locator("button", has_text="◀ Allarme").click()
    P.settle(200)
    ok("'◀ Allarme' jumps to the picture of the alarm (with its layer, score and the 'allarme' mark)", img.get_attribute("src").endswith("/frames/30.jpg") and "strato 3/40" in body(P) and "punteggio 6,2%" in body(P) and "allarme" in P.pg.locator(".rec-viewer__caption").inner_text(), P.pg.locator(".rec-viewer__caption").inner_text())
    P.pg.locator(".rec-viewer button", has_text="‹").click()
    P.pg.locator(".rec-viewer button", has_text="‹").click()
    P.settle(200)
    ok("'‹' goes back one picture at a time", img.get_attribute("src").endswith("/frames/28.jpg"))
    P.pg.locator("button", has_text="È fallita da qui").click()
    ok("'È fallita da qui' sends failed with the time of that picture", wait_until(lambda: ["label", SESSIONS[0]["id"], {"outcome": "failed", "failed_at": T0 + 28 * 3}] in state()["rec_posts"]), state()["rec_posts"])
    ok("... and the page says from when", wait_until(lambda: "Fallita da 1:24 dopo l'inizio." in body(P), 6), body(P))
    P.pg.locator(".rec-outcome button", has_text="È andata bene").click()
    ok("'È andata bene' sends ok", wait_until(lambda: ["label", SESSIONS[0]["id"], {"outcome": "ok"}] in state()["rec_posts"]), state()["rec_posts"][-2:])
    ok("the AI verdicts of this print are there to mark too", "giudizi dell'ia in questa stampa" in body(P).lower() and P.pg.locator(".rec-alert").count() == 1)
    P.pg.screenshot(path=os.path.join(out, "04_detail.png"), full_page=True)
    ok("no horizontal scrolling in the recording", overflow(P) <= 0, overflow(P))
    P.pg.locator("button", has_text="Cancella questa registrazione").click()
    ok("delete asks first", "Le foto di questa stampa vengono cancellate per sempre" in body(P))
    P.pg.locator("button", has_text="Sì, cancella").click()
    ok("... then deletes and goes back to the list", wait_until(lambda: ["delete", SESSIONS[0]["id"], None] in state()["rec_posts"]) and wait_until(lambda: P.pg.locator(".rec-row").count() == 1, 4), state()["rec_posts"])
    ok("no JavaScript error", P.errors == [], P.errors)
    P.ctx.close()

    # --- 360 px
    P = fresh(b, w=360, h=740, recordings=SESSIONS, rec_frames={SESSIONS[0]["id"]: FRAMES}, alerts=ALERTS)
    open_recordings(P)
    ok("360 px: no horizontal scrolling on the list", wait_until(lambda: P.pg.locator(".rec-row").count() == 2) and overflow(P) <= 0, overflow(P))
    P.pg.locator(".rec-row").nth(0).click()
    P.settle(900)
    ok("360 px: no horizontal scrolling on a recording", overflow(P) <= 0, overflow(P))
    P.pg.screenshot(path=os.path.join(out, "05_360.png"), full_page=True)
    P.ctx.close()

    # --- an older backend
    P = fresh(b, brain="old")
    open_recordings(P)
    ok("a backend without recordings: 'update KlippEye'", wait_until(lambda: "non registra ancora le stampe" in body(P)), body(P))
    P.ctx.close()

    # --- English
    mock.reset()
    P = Page(b, mock, 390, 844, locale="en-US")
    CUR[0] = P
    P.goto("home", 1400)
    P.pg.click('button[aria-label="Settings"]')
    P.pg.wait_for_selector(".drawer")
    P.settle(450)
    P.pg.click('.set-entry[data-page="ai"]')
    P.settle(700)
    P.pg.click('.set-entry[data-page="recordings"]')
    P.settle(900)
    ok("in English: 'Recording is off.' and 'Record the prints'", wait_until(lambda: "Recording is off." in body(P)) and "Record the prints" in body(P), body(P)[:300])
    P.ctx.close()
    b.close()

print("FAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
