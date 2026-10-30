"""Settings -> Notifications -> where they arrive (1.20.0, roadmap phase 5c): notifications without a Firebase of your own,
through the free ntfy app, paired by a QR code. Usage: notifications_test.py <html> <outdir> <port>"""
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


# The KlippEye app 1.3.0 (KlippEyeApp/6), played by a fake bridge that behaves like Ascolto.kt
APP = """(() => {
  const ua = navigator.userAgent + ' KlippEyeApp/%d';
  Object.defineProperty(navigator, 'userAgent', { get: () => ua });
  const s = { permission: false, askPermission: true, battery: false, receive: false, chosen: false, mode: '', firebaseBuilt: true, ntfyTopic: '', firebaseTopic: '', connected: false, lastMessageAt: 0, lastTitle: '' };
  const mode = () => (s.firebaseTopic && (s.receive || !s.chosen)) ? 'firebase' : (s.receive && s.ntfyTopic ? 'ntfy' : '');
  const state = () => { s.mode = mode(); s.connected = s.mode === 'ntfy'; return JSON.stringify(s); };
  window.__app = { s, setups: [] };
  window.KlippEyeApp = {
    appInfo: () => JSON.stringify({ version: '1.3.0', code: 10300, canInstall: true }),
    notifySetup: (json) => { const d = JSON.parse(json); window.__app.setups.push(d);
      if ('ricevi' in d) { s.receive = d.ricevi; s.chosen = true; }
      if ('ntfy' in d) s.ntfyTopic = d.ntfy ? d.ntfy.topic : '';
      if ('firebaseTopic' in d) s.firebaseTopic = d.firebaseTopic || '';
      return state(); },
    notifyState: () => state(),
    askNotificationPermission: () => { s.permission = true; },
    askBatteryExemption: () => { s.battery = true; },
    openNotificationSettings: () => { window.__app.settingsOpened = true; },
  };
})();"""


def open_notifications(b, width=390, height=844, app=0, page=True, **st):
    mock.reset()
    if st: mock.set(**st)
    P = Page(b, mock, width, height)
    CUR[0] = P
    if app: P.pg.add_init_script(APP % app)
    P.pg.goto(mock.base + "/"); P.pg.wait_for_timeout(2200)
    if not page: return P
    P.pg.click('button[aria-label="Impostazioni"]'); P.pg.wait_for_selector(".drawer"); P.settle(450)
    P.pg.locator('.set-entry[data-page="notifications"]').click(); P.settle(900)
    return P


def body(P):
    return P.pg.locator(".drawer__body").inner_text()


with sync_playwright() as p:
    b = p.chromium.launch()

    P = open_notifications(b)
    text = body(P).lower()
    ok("nothing set up: the page says no channel is on, and offers ntfy first", P.pg.locator('[data-ntfy="off"]').count() == 1 and "nessun canale è attivo" in text and "dove arrivano" in text and P.pg.locator("[data-ntfy-on]").count() == 1, text[:700])
    ok("... the group comes before the choice of which notifications", text.index("dove arrivano") < text.index("quali notifiche ricevere"), text[:400])
    P.shot(out + "/off.png")

    P.pg.locator("[data-ntfy-on]").click(); P.settle(900)
    st = state()
    ok("turned on with one tap: the backend is asked to turn ntfy on and to open this dashboard from the notification", st["ntfy_posts"] and st["ntfy_posts"][0].get("enabled") is True and st["ntfy_posts"][0].get("click") == mock.base + "/", st["ntfy_posts"])
    topic = st["ntfy"]["topic"]
    ok("... the page shows the three steps, the private topic and the QR code that subscribes the ntfy app", P.pg.locator('[data-ntfy="on"]').count() == 1 and P.pg.locator(".nt-steps > li").count() == 3
       and P.pg.locator('[data-ntfy-topic="%s"]' % topic).count() == 1 and P.pg.locator('svg.nt-qr[data-qr="ntfy://ntfy.sh/%s?display=KlippEye"]' % topic).count() == 1, body(P)[:900])
    ok("... the QR code is drawn (black squares on white), big enough to scan", P.pg.locator("svg.nt-qr path").get_attribute("d").count("h1v1h-1z") > 200 and P.pg.locator("svg.nt-qr").bounding_box()["width"] >= 180)
    ok("... the links of the app stores are there (Google Play, F-Droid, App Store)", P.pg.locator(".nt-links a").count() == 3)
    P.shot(out + "/on.png")

    P.pg.locator("[data-ntfy-test]").click()
    ok("test notification: the result is shown per channel", wait_until(lambda: P.pg.locator('[data-test-result="ok"]').count() == 1) and "ntfy: inviata" in body(P) and state()["ntfy_tests"] == 1, body(P)[-600:])
    mock.set(ntfy_test_fail="ntfy not reachable (timed out)")
    P.pg.locator("[data-ntfy-test]").click()
    ok("... and when it fails, why (in plain words)", wait_until(lambda: P.pg.locator('[data-test-result="failed"]').count() == 1) and "NON inviata (ntfy not reachable" in body(P), body(P)[-600:])

    P.pg.locator("[data-ntfy-new]").click(); P.settle(900)
    ok("a new address (after a confirmation): another topic, another QR code", state()["ntfy"]["topic"] != topic and P.pg.locator('svg.nt-qr[data-qr*="%s"]' % state()["ntfy"]["topic"]).count() == 1)

    P.pg.locator(".nt-own summary").click(); P.settle(300)
    P.pg.locator("[data-ntfy-server]").fill("ftp://bad"); P.pg.locator("[data-ntfy-save-server]").click(); P.settle(700)
    ok("own server: a wrong address is refused and the reason is shown", "deve iniziare con http" in body(P), body(P)[-500:])
    P.pg.locator("[data-ntfy-server]").fill("http://192.168.1.9:8080"); P.pg.locator("[data-ntfy-save-server]").click(); P.settle(900)
    ok("... a home server over http: the QR code tells the app to use http", P.pg.locator('svg.nt-qr[data-qr$="&secure=false"]').count() == 1 and "192.168.1.9:8080" in body(P))

    P.pg.locator("[data-ntfy-off]").click(); P.settle(900)
    ok("turned off: back to the button, the topic is kept for next time", P.pg.locator("[data-ntfy-on]").count() == 1 and state()["ntfy"]["topic"] != "" and state()["ntfy"]["enabled"] is False)
    P.close()

    # on the phone's own browser: a button that opens the ntfy app directly
    P = open_notifications(b, ntfy={"enabled": True, "server": "https://ntfy.sh", "topic": "klippeye-abcdefghijklmnop", "has_token": False, "click": ""}, firebase_on=True)
    ok("Firebase set up too: both shown as on", P.pg.locator('[data-firebase="on"]').count() == 1 and P.pg.locator('[data-ntfy="on"]').count() == 1)
    P.pg.locator("[data-ntfy-test]").click()
    ok("... the test reports both channels", wait_until(lambda: P.pg.locator(".nt-results li").count() == 2), body(P)[-500:])
    P.close()

    # the notification service has not shown up: the page says which command installs it
    P = open_notifications(b)
    ok("no sign of the service: the command that installs it is shown", wait_until(lambda: "bash /home/x/klippeye/scripts/install.sh" in body(P), 10) or P.pg.locator('[data-service="missing"]').count() == 0, body(P)[:500])
    P.close()

    # ================================================================== the KlippEye app 1.3.0: the guided procedure
    P = open_notifications(b, app=6, page=False)
    ok("app: the dashboard tells the app what the Raspberry says, as soon as it opens (no channel yet)", wait_until(lambda: P.pg.evaluate("() => window.__app.setups.length") >= 1) and P.pg.evaluate("() => window.__app.setups[0]") == {"ntfy": None, "firebaseTopic": ""}, P.pg.evaluate("() => window.__app.setups"))
    invite = P.pg.locator("[data-notify-invite]")
    ok("app, first time: an invitation to receive the notifications on this phone", invite.count() == 1 and "Vuoi ricevere le notifiche" in invite.inner_text(), invite.count())
    P.shot(out + "/app_invite.png")
    invite.locator("button", has_text="Imposta").click(); P.settle(900)
    text = body(P).lower()
    ok("... 'Imposta' opens Notifications on the procedure 'Questo telefono', before the ntfy app's", P.pg.locator(".nt-phone-step").count() == 5 and text.index("questo telefono") < text.index("altri telefoni"), text[:600])
    ok("... and the invitation does not come back", P.pg.locator("[data-notify-invite]").count() == 0 and P.pg.evaluate("() => localStorage.getItem('ke_notify_invite_closed')") == "1")
    cur = lambda: P.pg.locator(".nt-phone-step.is-current").get_attribute("data-phone-step")
    ok("step 1 is the current one: allow the notifications", cur() == "1" and P.pg.locator('[data-phone-action="permission"]').count() == 1)
    P.shot(out + "/app_steps_start.png")
    P.pg.locator('[data-phone-action="permission"]').click(); P.settle(1800)
    ok("permission given -> step 2: make the private address", wait_until(lambda: cur() == "2") and P.pg.locator('[data-phone-step="1"]').get_attribute("data-done") == "1")
    P.pg.locator('[data-phone-action="channel"]').click(); P.settle(1200)
    topic = state()["ntfy"]["topic"]
    ok("... the Raspberry turns ntfy on and the app gets the topic", topic and wait_until(lambda: P.pg.evaluate("() => window.__app.s.ntfyTopic") == topic) and cur() == "3", (topic, P.pg.evaluate("() => window.__app.s")))
    P.pg.locator('[data-phone-action="receive"]').click(); P.settle(1800)
    ok("'Ricevi qui': the app listens to ntfy (no ntfy app), the page says it is connected", P.pg.evaluate("() => window.__app.s.receive") is True and wait_until(lambda: P.pg.locator('[data-phone="on"]').count() == 1) and "collegato" in body(P) and cur() == "4", body(P)[:400])
    ok("... step 4 explains the small fixed notification and the battery", "KlippEye in ascolto" in body(P) and "batteria" in body(P))
    P.pg.locator('[data-phone-action="battery"]').click(); P.settle(1800)
    ok("battery allowed -> step 5: the test", wait_until(lambda: cur() == "5"))
    n = state()["ntfy_tests"]
    P.pg.locator('[data-phone-action="proof"]').click(); P.settle(1500)
    ok("test: the Raspberry sends it and the page waits for it on this phone", state()["ntfy_tests"] == n + 1 and "In attesa" in body(P))
    P.pg.evaluate("() => { window.__app.s.lastMessageAt = Date.now(); }")
    ok("... the app says it arrived: 'Arrivata su questo telefono', every step done", wait_until(lambda: P.pg.locator('[data-proof="arrived"]').count() == 1, 6) and P.pg.locator('.nt-phone-step[data-done="1"]').count() == 5)
    P.shot(out + "/app_steps_done.png")
    P.pg.locator('[data-phone-action="stop"]').click(); P.settle(1500)
    ok("'Non ricevere su questo telefono': the app stops listening", P.pg.evaluate("() => window.__app.s.receive") is False and wait_until(lambda: P.pg.locator('[data-phone="off"]').count() == 1))
    ok("app: no store links and no ntfy:// button inside the app (the app cannot open them)", P.pg.locator(".nt-links a").count() == 0 and P.pg.locator("[data-ntfy-link]").count() == 0)
    P.close()

    # the maintainer's installation: Firebase set up on the Raspberry -> the app subscribes to the Firebase topic it is given
    P = open_notifications(b, app=6, firebase_on=True)
    ok("Firebase on the Raspberry: the app receives the Firebase topic, and receives without any step (as with app 1.2.0)", wait_until(lambda: P.pg.evaluate("() => window.__app.s.firebaseTopic") == "klippeye-fb-secret0000000000") and wait_until(lambda: P.pg.locator('[data-phone="on"]').count() == 1) and "Firebase" in body(P), body(P)[:400])
    ok("... no invitation, and only three steps (no private address, no battery)", P.pg.locator("[data-notify-invite]").count() == 0 and P.pg.locator(".nt-phone-step").count() == 3)
    P.close()

    # an older app (1.2.0, KlippEyeApp/5): asked to update
    P = open_notifications(b, app=5)
    ok("app 1.2.0: the page asks to update the app to receive without ntfy", P.pg.locator('[data-phone="old-app"]').count() == 1 and P.pg.locator("[data-notify-invite]").count() == 0)
    P.close()

    # a browser: Firebase is not mentioned when it is not set up, the KlippEye app is
    P = open_notifications(b)
    ok("browser: no word about Firebase when it is not set up; a hint about the KlippEye app", P.pg.locator("[data-firebase]").count() == 0 and "Firebase" not in body(P) and P.pg.locator("[data-app-hint]").count() == 1)
    P.close()

    # narrow screen: nothing spills out
    P = open_notifications(b, 320, 640, ntfy={"enabled": True, "server": "https://ntfy.sh", "topic": "klippeye-abcdefghijklmnop", "has_token": False, "click": ""})
    wide = P.pg.evaluate("() => document.documentElement.scrollWidth")
    ok("320 px: no horizontal scroll", wide <= 320, wide)
    P.shot(out + "/narrow.png")
    P.close()
    b.close()

print("\nFAILED: %d %s" % (len(FAILS), FAILS) if FAILS else "\nALL PASS")
sys.exit(1 if FAILS else 0)
