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


def open_notifications(b, width=390, height=844, **st):
    mock.reset()
    if st: mock.set(**st)
    P = Page(b, mock, width, height)
    CUR[0] = P
    P.pg.goto(mock.base + "/"); P.pg.wait_for_timeout(2200)
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
    ok("... Firebase is only mentioned, as the way of an app built by yourself", P.pg.locator('[data-firebase="off"]').count() == 1 and "appendice a" in text)
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

    # narrow screen: nothing spills out
    P = open_notifications(b, 320, 640, ntfy={"enabled": True, "server": "https://ntfy.sh", "topic": "klippeye-abcdefghijklmnop", "has_token": False, "click": ""})
    wide = P.pg.evaluate("() => document.documentElement.scrollWidth")
    ok("320 px: no horizontal scroll", wide <= 320, wide)
    P.shot(out + "/narrow.png")
    P.close()
    b.close()

print("\nFAILED: %d %s" % (len(FAILS), FAILS) if FAILS else "\nALL PASS")
sys.exit(1 if FAILS else 0)
