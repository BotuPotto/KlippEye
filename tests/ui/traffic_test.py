"""How much the dashboard asks of the printer while it sits there, and that the savings do not cost reactivity.
Usage: traffic_test.py <html> <outdir> <port>"""
import sys, os, json, time, collections
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
FAILS = []


def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra != "" else ""))


def socket_handler(P, deliver):
    """A websocket that answers the console subscription (like Moonraker does) and can push lines."""
    sockets = []
    def handler(ws):
        sockets.append(ws)
        def on_message(msg):
            try: data = json.loads(msg)
            except Exception: return
            if data.get("method") == "server.gcode_store.subscribe":
                ws.send(json.dumps({"jsonrpc": "2.0", "id": data["id"], "result": {"gcode_store": []}}))
        ws.on_message(on_message)
    P.pg.route_web_socket("**/websocket", handler)
    return sockets


def rate(P, secs, ok_fn=lambda r: True):
    P.take_reqs(); P.pg.wait_for_timeout(int(secs * 1000))
    reqs = [r for r in P.take_reqs() if r["m"] == "GET" and ok_fn(r)]
    c = collections.Counter(r["u"].split("?")[0] for r in reqs)
    return reqs, c


with sync_playwright() as p:
    b = p.chromium.launch()

    # ---- idle Home, websocket delivering the console: the lean rate
    mock.reset(); P = Page(b, mock, 390, 844)
    sockets = socket_handler(P, True); P.goto("home", 3500)
    reqs, c = rate(P, 20)
    total = len(reqs) / 20
    print("   ", dict(c))
    ok("[idle home] total requests <= 5 per second", total <= 5.0, round(total, 2))
    ok("[idle home] the console store is read at most every 3 s (websocket live)", c["/server/gcode_store"] <= 8, c["/server/gcode_store"])
    ok("[idle home] the list of fans is not asked every second", c["/printer/objects/list"] <= 2, c["/printer/objects/list"])
    ok("[idle home] the light is asked at most every 1.4 s", len([r for r in reqs if "VAR_LUCI" in r["u"]]) <= 16, len([r for r in reqs if "VAR_LUCI" in r["u"]]))
    ok("[idle home] temperatures still every second", c["/api/printer"] >= 18, c["/api/printer"])
    ok("[idle home] no page errors", not [e for e in P.errors if "pageerror" in e or "console.error" in e], P.errors[:2]); P.close()

    # ---- no live websocket: the console keeps its quick rhythm
    mock.reset(); P = Page(b, mock, 390, 844); P.goto("home", 3500)
    reqs, c = rate(P, 10)
    ok("[no websocket] the console is read every 0.5 s as before", c["/server/gcode_store"] >= 18, c["/server/gcode_store"])
    P.close()

    # ---- the file being printed: its metadata is asked once, not at every poll
    mock.reset(); mock.set(printing=True); P = Page(b, mock, 390, 844); P.goto("home", 500)
    P.pg.wait_for_timeout(14000)
    asked = len([r for r in P.reqs if r["u"].startswith("/server/files/metadata")])
    ok("[printing] metadata of the current file asked once in 14 s (not at every poll)", 1 <= asked <= 2, asked)
    P.close()

    # ---- reactivity that has to stay
    mock.reset(); P = Page(b, mock, 390, 844); P.goto("home", 3000)
    mock.set(light=1)
    t0 = time.time()
    while time.time() - t0 < 6 and not P.pg.evaluate("() => document.querySelector('.light-btn').classList.contains('is-on')"):
        P.pg.wait_for_timeout(100)
    ok("[light changed elsewhere] shown within 3.5 s", time.time() - t0 <= 3.5, round(time.time() - t0, 1))
    mock.set(ext_t=240.0); t0 = time.time()
    while time.time() - t0 < 4 and "240.0" not in P.pg.locator("button.heater-tile").first.inner_text():
        P.pg.wait_for_timeout(100)
    ok("[temperature] still follows within 1.5 s", time.time() - t0 <= 1.5, round(time.time() - t0, 1))
    P.close()
    b.close()
print("\nFAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
