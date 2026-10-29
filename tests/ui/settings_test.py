"""The settings menu (side panel behind the menu button): opening and closing, every page, how the settings are kept and shared,
what each one does to the camera / Z-offset card / addresses, the wrong values that must not get in, narrow and wide screens.
Usage: settings_test.py <html> <outdir> <port>"""
import sys, os, io, re, json, time, urllib.request
from playwright.sync_api import sync_playwright
from PIL import Image
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
FAILS = []


def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""))


NOW_MS = lambda: int(time.time() * 1000)
buf = io.BytesIO(); Image.new("RGB", (32, 18), (40, 120, 200)).save(buf, "PNG"); PNG = buf.getvalue()


def db():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/db").read())


def stored():
    return db()["db"].get("klippeye/settings")


def db_write(key, value):
    req = urllib.request.Request(mock.base + "/server/database/item", data=json.dumps({"namespace": "klippeye", "key": key, "value": value}).encode(), headers={"content-type": "application/json"}, method="POST")
    urllib.request.urlopen(req).read()


CUR = [None]  # the page whose browser is kept running while we wait (the requests of the page are answered by this process)


def wait_until(fn, timeout=4.0, step=0.1):
    """Waits for fn() to be true, letting the browser go on meanwhile (time.sleep would stop the answers to its requests)."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn(): return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    try: return bool(fn())
    except Exception: return False


def camera_routes(P):
    P.cam = []  # every request for the camera, with its query
    P.pg.on("request", lambda r: P.cam.append(r.url) if "/webcam" in r.url else None)
    # the camera is another address of the Raspberry: answer it with a small picture (as a camera would)
    P.pg.route("**/webcam/**", lambda route: route.fulfill(status=200, body=PNG, content_type="image/png") if route.request.resource_type == "image" else route.fulfill(status=200, body="<html><body style='background:#123'>cam</body></html>", content_type="text/html"))


def fresh(b, w=390, h=844, wait=1400, reset=True, init=None, locale="it-IT", **state):
    if reset: mock.reset()
    if state: mock.set(**state)
    P = Page(b, mock, w, h, locale=locale)
    camera_routes(P)
    if init: P.ctx.add_init_script(init)
    CUR[0] = P
    P.goto("home", wait)
    return P


def settings_now(P):
    return P.pg.evaluate("() => { const v = localStorage.getItem('ke_settings'); return v ? JSON.parse(v).settings : null; }")


def pick_host_fn():
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "frontend", "src", "app", "16-settings.js")).read()
    m = re.search(r"const hostName = .*?function pickCameraHost.*?\n}\n", src, re.S)
    return m.group(0)


def open_menu(P):
    P.pg.click('button[aria-label="Impostazioni"]'); P.pg.wait_for_selector(".drawer"); P.settle(450)


def close_menu(P):
    P.pg.click('.drawer button[aria-label="Chiudi"]'); P.pg.wait_for_selector(".drawer", state="detached"); P.settle(100)


def choice(pg, title):
    """The row of a choice (camera method, address to use) by its exact title: 'Pagina web' is also in the text of the WebRTC row."""
    return pg.locator(".set-choice", has=pg.locator(".set-switch__title", has_text=re.compile("^" + re.escape(title) + "$"))).first


def go(P, name):
    """Opens a page of the menu; 1.19: camcal / detector / recordings are inside "Monitor IA"."""
    for _ in range(2):
        if P.pg.locator('.set-entry[data-page="%s"]' % name).count() or P.pg.locator('.set-entry[data-page="ai"]').count():
            break
        P.pg.click('.drawer button[aria-label="Indietro"]'); P.settle(400)
    if not P.pg.locator('.set-entry[data-page="%s"]' % name).count() and name in ("camcal", "detector", "recordings"):
        P.pg.click('.set-entry[data-page="ai"]'); P.settle(600)
    P.pg.click('.set-entry[data-page="%s"]' % name); P.settle(450)


def back(P):
    P.pg.click('.drawer button[aria-label="Indietro"]'); P.settle(450)


def switch(P, title):
    return P.pg.locator(".set-switch", has=P.pg.locator(".set-switch__title", has_text=title)).first


def checked(P, title):
    return switch(P, title).get_attribute("aria-checked") == "true"


def type_into(loc, text):
    loc.click(); loc.press("Control+A")
    if text: loc.type(text)
    else: loc.press("Delete")


def overflow(P):
    return P.pg.evaluate("() => { const b = document.querySelector('.drawer__body'); return { page: document.documentElement.scrollWidth - document.documentElement.clientWidth, body: b ? b.scrollWidth - b.clientWidth : 0 }; }")


DEFAULTS = None

with sync_playwright() as p:
    b = p.chromium.launch()

    # ============================================================================================ the menu itself
    P = fresh(b)
    pg = P.pg
    ok("the menu button is in the top bar", pg.locator('.app-header button[aria-label="Impostazioni"]').count() == 1)
    ok("the menu is not there until the button is pressed", pg.locator(".drawer").count() == 0)
    open_menu(P)
    box = pg.locator(".drawer").bounding_box()
    ok("it slides in from the left, at most 420 px wide and never covering the whole page", box["x"] == 0 and box["width"] <= 420 and box["width"] <= 390 - 40, box)
    ok("it is a dialog with a name", pg.locator(".drawer").get_attribute("role") == "dialog" and pg.locator(".drawer").get_attribute("aria-label") == "Impostazioni")
    titles = pg.locator(".set-entry .oui-row__name").all_inner_texts()
    ok("ten groups (1.19: everything of the AI monitor is inside 'Monitor IA'), the printer first, in this order", titles == ["Stampante", "Funzioni della stampante", "Camera", "Indirizzi", "Z-offset", "Notifiche", "Monitor IA", "Accesso", "Aggiornamenti", "Lingua"], titles)
    summaries = pg.locator(".set-entry__meta").all_inner_texts()
    ok("each group says what it is set to now", summaries[0] == "KlippEye" and summaries[1] == "WebRTC" and summaries[2] == "192.168.1.17 • 172.25.170.177" and summaries[3] == "0.01 · 0.025 · 0.05 · 0.1 mm" and summaries[4] == "7 su 7 attive" and "Pausa da sola: no" in summaries[5], summaries)
    ok("the page behind cannot scroll while it is open", pg.evaluate("() => document.body.style.overflow") == "hidden")
    ok("the state line says the Raspberry keeps the settings", wait_until(lambda: "Salvate sul Raspberry" in pg.locator(".set-status").first.inner_text()), pg.locator(".set-status").first.inner_text())
    P.shot_vp(f"{out}/menu_home_390.png")
    close_menu(P)
    ok("the X closes it and the page scrolls again", pg.evaluate("() => document.body.style.overflow") == "")
    open_menu(P); pg.mouse.click(380, 400); pg.wait_for_selector(".drawer", state="detached")
    ok("a tap on the strip of page that stays visible closes it", True)
    open_menu(P); pg.keyboard.press("Escape"); pg.wait_for_selector(".drawer", state="detached")
    ok("Escape closes it", True)
    open_menu(P); go(P, "camera"); pg.keyboard.press("Escape"); P.settle(300)
    ok("Escape inside a group goes back to the list first, then closes", pg.locator(".set-entry").count() == 10 and pg.locator(".drawer").count() == 1)
    pg.keyboard.press("Escape"); pg.wait_for_selector(".drawer", state="detached")
    open_menu(P)
    TOUCH = """([sx, ex]) => { const el = document.querySelector('.drawer'); const mk = (type, x) => { const e = new Event(type, { bubbles: true, cancelable: true }); const t = [{ identifier: 1, clientX: x, clientY: 300, target: el }]; e.touches = type === 'touchend' ? [] : t; e.changedTouches = t; return e; }; el.dispatchEvent(mk('touchstart', sx)); el.dispatchEvent(mk('touchend', ex)); }"""
    pg.evaluate(TOUCH, [250, 230]); P.settle(300)
    ok("a short swipe does nothing", pg.locator(".drawer").count() == 1)
    pg.evaluate(TOUCH, [300, 120]); pg.wait_for_selector(".drawer", state="detached")
    ok("a swipe to the left closes it", True)
    open_menu(P); go(P, "camera"); close_menu(P); open_menu(P)
    ok("it always opens on the list of groups", pg.locator(".set-entry").count() == 10)
    close_menu(P)
    for tab in ("controllo", "files", "config", "sistema"):
        P.goto(tab, 700)
        if pg.locator('.app-header button[aria-label="Impostazioni"]').count() != 1:
            ok("the menu button is on every page (%s)" % tab, False); break
    else:
        ok("the menu button is on every page", True)
    P.goto("home", 900)
    P.close()

    # ============================================================================================ how the settings are kept and shared
    P = fresh(b)
    pg = P.pg
    ok("first start: the Raspberry gets the settings (a first copy stamped 0: any choice made anywhere wins over it)", wait_until(lambda: stored() is not None) and stored()["_t"] == 0 and stored()["camera"]["method"] == "webrtc", stored())
    DEFAULTS = {k: v for k, v in stored().items() if k != "_t"}
    ok("... and the page keeps a copy of its own", pg.evaluate("() => JSON.parse(localStorage.getItem('ke_settings')).settings.camera.method") == "webrtc")
    open_menu(P); go(P, "notifications")
    switch(P, "Stampa completata").click()
    ok("a change is written to the Raspberry within a moment", wait_until(lambda: stored()["notifications"]["complete"] is False), stored())
    ok("... as one write (no storm of requests)", sum(1 for r in P.reqs if r["m"] == "POST" and "/server/database/item" in r["u"]) <= 3, [r["u"] for r in P.reqs if r["m"] == "POST"])
    ok("... and the page's own copy follows (nothing waiting to be sent)", wait_until(lambda: pg.evaluate("() => JSON.parse(localStorage.getItem('ke_settings')).dirty") is False))
    P2 = fresh(b, reset=False)
    pg2 = P2.pg
    ok("ANOTHER DEVICE (empty browser) starts with the same settings", wait_until(lambda: settings_now(P2)["notifications"]["complete"] is False), settings_now(P2)["notifications"])
    open_menu(P2); go(P2, "notifications")
    ok("... and the menu shows it", not checked(P2, "Stampa completata") and checked(P2, "Stampante in pausa"))
    P2.pg.reload(); P2.pg.wait_for_timeout(1200)
    ok("reload: still the same", settings_now(P2)["notifications"]["complete"] is False)
    # a change made elsewhere reaches this device when its menu opens
    other = dict(stored()); other["notifications"] = dict(other["notifications"], paused=False); other["_t"] = NOW_MS() + 5000
    db_write("settings", other)
    close_menu(P); open_menu(P); go(P, "notifications")
    ok("a change made on another device arrives when the menu is opened", wait_until(lambda: not checked(P, "Stampante in pausa")), settings_now(P)["notifications"])
    # an older copy on the Raspberry does not overwrite a newer one here
    before = stored()["_t"]
    switch(P, "Filamento esaurito").click(); wait_until(lambda: stored()["notifications"]["runout"] is False)
    ok("the stamp grows with every change", stored()["_t"] > before)
    P2.close(); P.close()

    # the Raspberry cannot be reached / does not accept the settings
    for mode, expect in (("no_route", "HTTP 404"), ("refuse", "Forbidden"), ("down", "HTTP 502")):
        P = fresh(b, db_mode=mode)
        pg = P.pg
        open_menu(P)
        ok("[%s] the state line says 'solo su questo dispositivo' and why" % mode, wait_until(lambda: "Solo su questo dispositivo" in pg.locator(".set-status").first.inner_text()) and expect in pg.locator(".set-status").first.inner_text(), pg.locator(".set-status").first.inner_text())
        go(P, "camera"); choice(pg, "MJPEG").click(); P.settle(300)
        ok("[%s] the change still works here at once" % mode, settings_now(P)["camera"]["method"] == "mjpeg")
        wait_until(lambda: False, 1.2)
        pg.reload(); pg.wait_for_timeout(1200)
        ok("[%s] ... and is still there after a reload (kept by this browser)" % mode, settings_now(P)["camera"]["method"] == "mjpeg")
        if mode == "down":
            mock.set(db_mode="ok")
            open_menu(P)
            ok("[down] the Raspberry is back: what was changed meanwhile is sent to it when the menu opens", wait_until(lambda: (stored() or {}).get("camera", {}).get("method") == "mjpeg", 5), stored())
        ok("[%s] no errors in the page" % mode, not [e for e in P.errors if "pageerror" in e], P.errors[:3])
        P.close()

    # damaged documents
    GARBAGE = {"camera": {"method": "hack", "urls": {"webrtc": "javascript:alert(1)", "mjpeg": 5, "adaptive": "ftp://x/y", "iframe": "http://ok.example/cam"}, "fps": "999", "flipH": "yes"},
               "network": {"localIp": "<script>", "externalIp": "10.1.2.3:99999", "route": "sideways"}, "zOffset": {"steps": ["x", 5, 0.0004, "0,2"]},
               "notifications": {"complete": "no", "error": 0}, "ai": {"autoPause": "true", "autoCancel": 1, "confirmations": 7, "minConfidence": 60, "defects": {"warping": 0, "spaghetti": False}}, "_t": NOW_MS() + 9999}
    mock.reset(); db_write("settings", GARBAGE)
    P = Page(b, mock, 390, 844); camera_routes(P); CUR[0] = P; P.goto("home", 1600)
    s = settings_now(P)
    ok("a damaged document: wrong method / address / numbers become defaults", s["camera"]["method"] == "webrtc" and s["camera"]["urls"]["webrtc"] == "/webcam/webrtc" and s["camera"]["urls"]["mjpeg"] == "/webcam/?action=stream" and s["camera"]["urls"]["adaptive"] == "/webcam/?action=snapshot" and s["camera"]["fps"] == 30 and s["camera"]["flipH"] is False, s["camera"])
    ok("... an address that is fine is kept", s["camera"]["urls"]["iframe"] == "http://ok.example/cam")
    ok("... addresses of the Raspberry that are not addresses become the defaults", s["network"] == {"localIp": "192.168.1.17", "externalIp": "172.25.170.177", "route": "auto"}, s["network"])
    ok("... step sizes with nothing usable become the defaults", s["zOffset"]["steps"] == [0.01, 0.025, 0.05, 0.1], s["zOffset"])
    ok("... switches that are not real booleans are ignored (notifications on, automatic actions OFF)", all(s["notifications"].values()) and s["ai"]["autoPause"] is False and s["ai"]["autoCancel"] is False and s["ai"]["confirmations"] == 1 and s["ai"]["defects"] == {"spaghetti": False, "empty_bed": True, "layer_shift": True, "warping": True}, s["ai"])
    src = P.pg.locator(".camera-frame iframe").get_attribute("src")
    ok("... and the page shows the camera as usual", src == "http://172.25.170.177/webcam/webrtc", src)
    ok("... without errors", not P.errors, P.errors[:3])
    P.close()
    mock.reset()

    # ============================================================================================ camera
    P = fresh(b)
    pg = P.pg
    frame = lambda: pg.locator(".camera-frame")
    ok("default camera: the WebRTC page of the printer, exactly as before the menu existed", pg.locator(".camera-frame iframe.camera-frame__video").get_attribute("src") == "http://172.25.170.177/webcam/webrtc")
    open_menu(P); go(P, "camera")
    P.shot_vp(f"{out}/menu_camera_390.png")
    methods = pg.locator(".set-choice .set-switch__title").all_inner_texts()
    ok("four methods, like Mainsail's webcam page", methods == ["WebRTC", "MJPEG", "MJPEG adaptive", "Pagina web"], methods)
    ok("the chosen one is ticked", pg.locator('.set-choice[aria-checked="true"] .set-switch__title').inner_text() == "WebRTC")
    choice(pg, "MJPEG").click(); P.settle(300)
    ok("MJPEG: the picture is an <img> of the stream (no iframe any more)", frame().locator("img.camera-img").get_attribute("src") == "http://172.25.170.177/webcam/?action=stream" and frame().locator("iframe").count() == 0, frame().inner_html()[:300])
    ok("... with its own address field, filled with the default", pg.locator(".set-field__input").first.input_value() == "/webcam/?action=stream")
    P.cam.clear()
    # the stream fails: the note, and another try later
    STREAM = lambda url: "action=stream" in url
    pg.route(STREAM, lambda route: route.abort())
    choice(pg, "WebRTC").click(); P.settle(200); choice(pg, "MJPEG").click(); P.settle(900)
    ok("a stream that does not come: the picture says so", frame().locator(".camera-note").count() == 1 and "non raggiungibile" in frame().locator(".camera-note").inner_text(), frame().inner_html()[:200])
    count = lambda: len([u for u in P.cam if "action=stream" in u])
    tries = count()
    wait_until(lambda: count() > tries, 5)
    ok("... and it tries again by itself", tries >= 1 and count() > tries, (tries, count()))
    pg.unroute(STREAM)
    # adaptive
    choice(pg, "MJPEG adaptive").click(); P.settle(300)
    ok("MJPEG adaptive: two pictures lie on top of each other", frame().locator(".camera-snaps__img").count() == 2 and frame().locator("iframe").count() == 0)
    P.cam.clear(); P.settle(2000)
    snaps = [u for u in P.cam if "action=snapshot" in u]
    ok("... 5 photos a second at most (default): about ten in two seconds, each with its own '_' so none is cached", 5 <= len(snaps) <= 12 and len(set(snaps)) == len(snaps) and all("_=" in u for u in snaps), (len(snaps), snaps[:3]))
    ok("... the front picture alternates and exactly one is in front", frame().locator(".camera-snaps__img.is-front").count() == 1)
    ok("... no 'non raggiungibile' while pictures arrive", frame().locator(".camera-note").count() == 0)
    ok("... the number of photos a second can be changed", pg.locator(".set-stepper__value").inner_text().strip().startswith("5"))
    for _ in range(4): pg.locator('.set-stepper button[aria-label="Meno foto"]').click()
    P.settle(300); P.cam.clear(); P.settle(2200)
    snaps = [u for u in P.cam if "action=snapshot" in u]
    ok("... 1 photo a second: two or three in two seconds", 1 <= len(snaps) <= 4 and settings_now(P)["camera"]["fps"] == 1, (len(snaps), settings_now(P)["camera"]["fps"]))
    ok("... the minus button stops at 1", pg.locator('.set-stepper button[aria-label="Meno foto"]').is_disabled())
    for _ in range(40):
        if not pg.locator('.set-stepper button[aria-label="Più foto"]').is_disabled(): pg.locator('.set-stepper button[aria-label="Più foto"]').click()
    ok("... and the plus button at 30", settings_now(P)["camera"]["fps"] == 30 and pg.locator('.set-stepper button[aria-label="Più foto"]').is_disabled(), settings_now(P)["camera"]["fps"])
    for _ in range(25): pg.locator('.set-stepper button[aria-label="Meno foto"]').click()
    ok("... 25 steps back down: 5 again", settings_now(P)["camera"]["fps"] == 5 and pg.locator(".set-stepper__value").inner_text().strip().startswith("5"))
    # web page
    choice(pg, "Pagina web").click(); P.settle(300)
    field = pg.locator(".set-field__input").first
    type_into(field, "http://192.168.9.9:8081/stream.html"); P.settle(1300)
    ok("Pagina web: any address, the page is shown as an iframe at exactly that address", frame().locator("iframe").get_attribute("src") == "http://192.168.9.9:8081/stream.html", frame().inner_html()[:200])
    ok("... the address is kept for this method only", settings_now(P)["camera"]["urls"]["iframe"] == "http://192.168.9.9:8081/stream.html" and settings_now(P)["camera"]["urls"]["webrtc"] == "/webcam/webrtc")
    type_into(field, "due parole"); P.settle(1200)
    ok("a wrong address: the field says so, nothing is changed", pg.locator(".set-field__error").count() == 1 and settings_now(P)["camera"]["urls"]["iframe"] == "http://192.168.9.9:8081/stream.html", pg.locator(".set-field__error").all_inner_texts())
    pg.locator(".drawer__title").click(); P.settle(300)
    ok("... and leaving the field puts the last good address back", field.input_value() == "http://192.168.9.9:8081/stream.html" and pg.locator(".set-field__error").count() == 0)
    type_into(field, "javascript:alert(1)"); P.settle(1200); pg.locator(".drawer__title").click(); P.settle(200)
    ok("an address with another protocol (javascript:) never gets in", settings_now(P)["camera"]["urls"]["iframe"] == "http://192.168.9.9:8081/stream.html")
    type_into(field, "webcam2/live"); P.settle(1300)
    ok("a path without the first slash gets it", settings_now(P)["camera"]["urls"]["iframe"] == "/webcam2/live" and frame().locator("iframe").get_attribute("src") == "http://172.25.170.177/webcam2/live", frame().locator("iframe").get_attribute("src"))
    ok("a path that is not the default offers to go back to the default", pg.locator("button:has-text(\"Ripristina l'indirizzo predefinito\")").count() == 1)
    pg.locator("button:has-text(\"Ripristina l'indirizzo predefinito\")").click(); P.settle(400)
    ok("... and does", settings_now(P)["camera"]["urls"]["iframe"] == "/webcam/webrtc" and pg.locator("button:has-text(\"Ripristina l'indirizzo predefinito\")").count() == 0)
    # flips
    choice(pg, "WebRTC").click(); P.settle(300)
    media = lambda: frame().locator("iframe, img.camera-img, .camera-snaps__img").first
    tf = lambda: media().evaluate("e => getComputedStyle(e).transform")
    ok("no flip: the picture is as it comes", tf() == "none")
    switch(P, "Specchia").click(); P.settle(300)
    ok("Specchia: mirrored left to right", tf() == "matrix(-1, 0, 0, 1, 0, 0)", tf())
    switch(P, "Capovolgi").click(); P.settle(300)
    ok("+ Capovolgi: turned half way round", tf() == "matrix(-1, 0, 0, -1, 0, 0)", tf())
    switch(P, "Specchia").click(); P.settle(300)
    ok("only Capovolgi: upside down", tf() == "matrix(1, 0, 0, -1, 0, 0)", tf())
    choice(pg, "MJPEG").click(); P.settle(300)
    ok("the flip holds for the MJPEG picture too", frame().locator("img.camera-img").evaluate("e => getComputedStyle(e).transform") == "matrix(1, 0, 0, -1, 0, 0)")
    choice(pg, "MJPEG adaptive").click(); P.settle(500)
    ok("... and for both pictures of the adaptive one", frame().locator(".camera-snaps__img").evaluate_all("els => els.map(e => getComputedStyle(e).transform)") == ["matrix(1, 0, 0, -1, 0, 0)"] * 2)
    switch(P, "Capovolgi").click()
    choice(pg, "WebRTC").click(); P.settle(300)
    # reload button
    pg.evaluate("() => { document.querySelector('.camera-frame iframe').__mark = 1; }")
    pg.locator('button:has-text("Ricarica la camera")').click(); P.settle(400)
    ok("'Ricarica la camera' loads the picture afresh (a new iframe)", pg.evaluate("() => document.querySelector('.camera-frame iframe').__mark") is None)
    # import from Mainsail
    pg.locator('button:has-text("Importa da Mainsail")').click(); pg.wait_for_selector(".set-choice:has-text('Piatto')")
    rows = pg.locator(".set-group", has=pg.locator(".set-group__label", has_text="Da Mainsail")).locator(".set-choice")
    names = [r.locator(".set-switch__title").inner_text() for r in rows.all()]
    ok("import: the cameras configured in Mainsail are listed", names == ["KlippEye", "Piatto", "Go2rtc"], names)
    ok("... the one this dashboard cannot show is dimmed and says so", rows.nth(2).is_disabled() and "non supportato" in rows.nth(2).inner_text() and not rows.nth(0).is_disabled(), rows.nth(2).inner_text())
    rows.nth(1).click(); P.settle(400)
    s = settings_now(P)["camera"]
    ok("... choosing one sets the method, the address and the flip as Mainsail has them", s["method"] == "mjpeg" and s["urls"]["mjpeg"] == "/webcam2/?action=stream" and s["flipH"] is True and s["flipV"] is False, s)
    ok("... and the camera card follows", frame().locator("img.camera-img").get_attribute("src") == "http://172.25.170.177/webcam2/?action=stream")
    P.shot_vp(f"{out}/menu_camera_import_390.png")
    mock.set(webcams=[])
    back(P); close_menu(P); open_menu(P); go(P, "camera")
    pg.locator('button:has-text("Importa da Mainsail")').click(); P.settle(700)
    ok("import with no camera in Mainsail: says so", "non ha camere configurate" in pg.locator(".set-group__note--warn").inner_text(), pg.locator(".set-group__note").all_inner_texts())
    pg.route("**/server/webcams/list", lambda route: route.abort())
    pg.locator('button:has-text("Importa da Mainsail")').click(); P.settle(900)
    ok("import when Moonraker does not answer: says so", "Non riesco a leggere" in pg.locator(".set-group__note--warn").inner_text(), pg.locator(".set-group__note").all_inner_texts())
    ok("no errors in the page", not [e for e in P.errors if "pageerror" in e], P.errors[:3])
    ok("nothing was sent to the printer by the camera settings", mock.gcode() == [], mock.gcode())
    P.close()

    # the camera panel of the wide layout follows too
    P = fresh(b, 1440, 900)
    pg = P.pg
    ok("[1440] camera panel: WebRTC iframe by default", pg.locator(".desk-camera iframe.desk-camera__video").get_attribute("src") == "http://172.25.170.177/webcam/webrtc")
    open_menu(P); go(P, "camera"); choice(pg, "MJPEG").click(); P.settle(300)
    ok("[1440] ... and the MJPEG picture when chosen", pg.locator(".desk-camera img.desk-camera__video").get_attribute("src") == "http://172.25.170.177/webcam/?action=stream")
    choice(pg, "MJPEG adaptive").click(); P.settle(700)
    ok("[1440] ... and the adaptive one fills the panel", pg.locator(".desk-camera .camera-snaps.desk-camera__video").count() == 1 and pg.locator(".desk-camera .camera-snaps__img").count() == 2)
    bb, pb = pg.locator(".camera-snaps").bounding_box(), pg.locator(".desk-camera").bounding_box()
    ok("[1440] ... the same size as the panel", abs(bb["width"] - pb["width"]) <= 3 and abs(bb["height"] - pb["height"]) <= 3, (bb, pb))
    P.shot_vp(f"{out}/menu_camera_1440.png", 900)
    P.close()

    # ============================================================================================ addresses
    P = fresh(b)
    pg = P.pg
    open_menu(P); go(P, "network")
    P.shot_vp(f"{out}/menu_network_390.png")
    inputs = pg.locator(".set-field__input")
    ok("the two addresses are filled in", inputs.nth(0).input_value() == "192.168.1.17" and inputs.nth(1).input_value() == "172.25.170.177")
    ok("the line at the bottom says which one the camera uses now (the page was opened at 127.0.0.1: the external one)", "esterno 172.25.170.177" in pg.locator(".set-status").first.inner_text(), pg.locator(".set-status").first.inner_text())
    type_into(inputs.nth(0), "999.1.1.1"); P.settle(1200)
    ok("not an address: the field turns red and says why, nothing is saved", pg.locator(".set-field__error").count() == 1 and "valido" in pg.locator(".set-field__error").inner_text() and settings_now(P)["network"]["localIp"] == "192.168.1.17" and stored()["network"]["localIp"] == "192.168.1.17", pg.locator(".set-field__error").all_inner_texts())
    pg.locator(".drawer__title").click(); P.settle(300)
    ok("... leaving it puts the last good one back", inputs.nth(0).input_value() == "192.168.1.17")
    type_into(inputs.nth(0), "192.168.1.5")
    ok("typing: nothing happens while the typing goes on (the camera would reload at every key)", settings_now(P)["network"]["localIp"] == "192.168.1.17")
    P.settle(1300)
    ok("... a moment after the last key it is taken and sent to the Raspberry", settings_now(P)["network"]["localIp"] == "192.168.1.5" and wait_until(lambda: stored()["network"]["localIp"] == "192.168.1.5"), stored()["network"])
    type_into(inputs.nth(0), "http://192.168.1.50/"); inputs.nth(0).press("Enter"); P.settle(400)
    ok("Enter takes it at once, and 'http://' and the slash are dropped", settings_now(P)["network"]["localIp"] == "192.168.1.50" and inputs.nth(0).input_value() == "192.168.1.50", (settings_now(P)["network"], inputs.nth(0).input_value()))
    type_into(inputs.nth(1), "10.9.8.7"); close_menu(P)
    ok("closing the menu straight after typing does not lose the value", wait_until(lambda: settings_now(P)["network"]["externalIp"] == "10.9.8.7" and stored()["network"]["externalIp"] == "10.9.8.7", 4), settings_now(P)["network"])
    ok("... the camera now uses it (the page is not on the home network)", pg.locator(".camera-frame iframe").get_attribute("src") == "http://10.9.8.7/webcam/webrtc", pg.locator(".camera-frame iframe").get_attribute("src"))
    open_menu(P); go(P, "network")
    choice(pg, "Sempre locale").click(); P.settle(300)
    ok("'Sempre locale': the camera uses the local address", pg.locator(".camera-frame iframe").get_attribute("src") == "http://192.168.1.50/webcam/webrtc")
    ok("... and the line says so", "locale 192.168.1.50" in pg.locator(".set-status").first.inner_text())
    choice(pg, "Sempre esterno").click(); P.settle(300)
    ok("'Sempre esterno': the external one", pg.locator(".camera-frame iframe").get_attribute("src") == "http://10.9.8.7/webcam/webrtc")
    ok("the choices carry the address they stand for", choice(pg, "Sempre locale").inner_text().count("192.168.1.50") == 1)
    P.shot_vp(f"{out}/menu_network_after_390.png")
    ok("an address with a port is accepted (a camera on another port)", True)
    type_into(inputs.nth(1), "10.9.8.7:8080"); inputs.nth(1).press("Enter"); P.settle(300)
    ok("... and the camera goes to that port", pg.locator(".camera-frame iframe").get_attribute("src") == "http://10.9.8.7:8080/webcam/webrtc", pg.locator(".camera-frame iframe").get_attribute("src"))
    # which address for which page (the rule, tried on addresses the browser could be at)
    PICK_SRC = pick_host_fn()
    PICK = "([src, host, local, ext, route]) => { const pick = new Function(src + '; return pickCameraHost;')(); const r = pick({ network: { localIp: local, externalIp: ext, route } }, host); return r.side + ' ' + r.host; }"
    cases = [("192.168.1.17", "192.168.1.17", "172.25.170.177", "auto", "local 192.168.1.17"), ("172.25.170.177", "192.168.1.17", "172.25.170.177", "auto", "external 172.25.170.177"),
             ("192.168.77.5", "192.168.1.17", "172.25.170.177", "auto", "local 192.168.1.17"), ("172.25.9.9", "192.168.1.17", "172.25.170.177", "auto", "external 172.25.170.177"),
             ("10.0.0.5", "10.0.0.5", "172.25.170.177", "auto", "local 10.0.0.5"), ("10.0.3.9", "10.0.0.5", "172.25.170.177", "auto", "local 10.0.0.5"),
             ("klippeye.local", "klippeye.local", "172.25.170.177", "auto", "local klippeye.local"), ("klippeye.local", "192.168.1.17", "172.25.170.177", "auto", "external 172.25.170.177"),
             ("KLIPPEYE.LOCAL", "klippeye.local", "172.25.170.177", "auto", "local klippeye.local"), ("localhost", "192.168.1.17", "172.25.170.177", "auto", "external 172.25.170.177"),
             ("203.0.113.9", "192.168.1.17", "172.25.170.177", "auto", "external 172.25.170.177"), ("172.25.170.177", "192.168.1.17", "172.25.170.177", "local", "local 192.168.1.17"),
             ("192.168.1.17", "192.168.1.17", "172.25.170.177", "external", "external 172.25.170.177"), ("192.168.1.17", "192.168.1.17:8080", "172.25.170.177", "auto", "local 192.168.1.17:8080")]
    got = [pg.evaluate(PICK, [PICK_SRC] + list(c[:4])) for c in cases]
    bad = [(c, g) for c, g in zip(cases, got) if g != c[4]]
    ok("which address the camera is asked at, for %d addresses the browser could be at" % len(cases), not bad, bad)
    P.close()

    # ============================================================================================ Z-offset
    P = fresh(b, printing=True)
    pg = P.pg
    zcard = pg.locator(".oui-card:has(.oui-card-title:text-is('Z-offset'))").first
    chips = lambda: zcard.locator(".zoffset-steps .oui-chip").all_inner_texts()
    ok("the card offers the four default steps", chips() == ["0.01", "0.025", "0.05", "0.1"], chips())
    open_menu(P); go(P, "zoffset")
    P.shot_vp(f"{out}/menu_zoffset_390.png")
    slots = pg.locator(".set-grid .set-field__input")
    vals = lambda: [slots.nth(i).input_value() for i in range(4)]
    leave = lambda: (pg.locator(".drawer__title").click(), P.settle(400))
    steps_now = lambda: settings_now(P)["zOffset"]["steps"]
    ok("four fields with the current steps", vals() == ["0.01", "0.025", "0.05", "0.1"], vals())
    # (a field that is left puts the steps in order, so the changes are made from the last field to the first)
    type_into(slots.nth(3), ""); type_into(slots.nth(2), "1"); type_into(slots.nth(1), "0.2"); type_into(slots.nth(0), "0,02"); P.settle(1300)
    ok("the steps typed (a comma works as a decimal point, an empty field is dropped)", steps_now() == [0.02, 0.2, 1], steps_now())
    ok("... and the card behind shows exactly those", chips() == ["0.02", "0.2", "1"], chips())
    ws = zcard.locator(".zoffset-steps .oui-chip").evaluate_all("els => els.map(e => Math.round(e.getBoundingClientRect().width))")
    ok("... three chips share the width of the row", max(ws) - min(ws) <= 1 and sum(ws) > 200, ws)
    ok("... saved on the Raspberry", wait_until(lambda: stored()["zOffset"]["steps"] == [0.02, 0.2, 1]), stored()["zOffset"])
    leave()
    ok("the 'così appaiono nella card' preview shows them", pg.locator(".set-preview .oui-chip").all_inner_texts() == ["0.02", "0.2", "1"])
    BAD = "Ogni valore va da 0,001 a 1 mm."
    for text, problem in (("abc", BAD), ("0", BAD), ("2", BAD), ("0.0004", BAD), ("0.2", "Due valori sono uguali.")):
        type_into(slots.nth(0), text); P.settle(1100)
        ok("a wrong step (%r): says '%s' and nothing is saved" % (text, problem), pg.locator(".set-field__error").count() == 1 and pg.locator(".set-field__error").inner_text() == problem and steps_now() == [0.02, 0.2, 1], (pg.locator(".set-field__error").all_inner_texts(), steps_now()))
    leave()
    ok("leaving the field puts the saved step back and the message goes", vals() == ["0.02", "0.2", "1", ""] and pg.locator(".set-field__error").count() == 0, vals())
    type_into(slots.nth(0), "0.5"); leave()
    ok("typed out of order: they are put in order when the field is left", vals() == ["0.2", "0.5", "1", ""] and steps_now() == [0.2, 0.5, 1], (vals(), steps_now()))
    type_into(slots.nth(0), "0.123456"); leave()
    ok("a step with more than three decimals is rounded to three (the offset has three)", steps_now() == [0.123, 0.5, 1] and vals() == ["0.123", "0.5", "1", ""], (vals(), steps_now()))
    type_into(slots.nth(0), "0.2"); leave()
    close_menu(P)
    # end to end: the step chosen on the card is the one that is sent
    zcard.locator(".zoffset-steps .oui-chip:text-is('0.5')").click(); zcard.locator("button:has-text('Alza')").click(); P.settle(1700)
    sent = [g for g in mock.gcode() if g.startswith("SET_GCODE_OFFSET")]
    ok("a custom step is what the Alza button sends (0.5 mm)", sent == ["SET_GCODE_OFFSET Z_ADJUST=+0.5 MOVE=1"], sent)
    ok("... and the step chosen is remembered", "is-selected" in zcard.locator(".zoffset-steps .oui-chip:text-is('0.5')").get_attribute("class"))
    open_menu(P); go(P, "zoffset")
    type_into(slots.nth(1), ""); leave(); close_menu(P)
    ok("the step in use taken out of the list: the card goes back to the first one", chips() == ["0.2", "1"] and "is-selected" in zcard.locator(".zoffset-steps .oui-chip").first.get_attribute("class") and zcard.locator(".zoffset-steps .oui-chip.is-selected").count() == 1, chips())
    open_menu(P); go(P, "zoffset")
    ok("a non-default list offers 'Ripristina' ...", pg.locator("button:has-text('Ripristina 0,01')").count() == 1)
    pg.locator("button:has-text('Ripristina 0,01')").click(); P.settle(500)
    ok("... which puts 0.01, 0.025, 0.05, 0.1 back (in the fields too)", steps_now() == [0.01, 0.025, 0.05, 0.1] and vals() == ["0.01", "0.025", "0.05", "0.1"] and pg.locator("button:has-text('Ripristina 0,01')").count() == 0, (steps_now(), vals()))
    for _ in range(3): type_into(slots.nth(0), ""); leave()
    ok("fields emptied one by one: the steps get fewer", steps_now() == [0.1] and vals() == ["0.1", "", "", ""], (steps_now(), vals()))
    type_into(slots.nth(0), ""); P.settle(1100)
    ok("the last one emptied: 'Scrivi almeno un valore.' and the step stays", pg.locator(".set-field__error").inner_text() == "Scrivi almeno un valore." and steps_now() == [0.1])
    leave()
    ok("... leaving the field puts it back", vals() == ["0.1", "", "", ""] and pg.locator(".set-field__error").count() == 0)
    P.close()

    # ============================================================================================ notifications
    P = fresh(b)
    pg = P.pg
    open_menu(P); go(P, "notifications")
    P.shot_vp(f"{out}/menu_notifications_390.png")
    rows = pg.locator(".set-switch")
    ok("seven notifications, with the exact texts of the notifications", rows.count() == 7 and [r.locator(".set-switch__detail").inner_text() for r in rows.all()] == [
        "Stampante in errore! Effettuare riavvio.", "Stampa completata!", "Stampa interrotta!", "Stampante in pausa!", "Filamento esaurito, effettuare cambio bobina!",
        "Difetti di stampa rilevati, verificare e mettere in pausa la stampa!", "Difetti gravi di stampa rilevati, verificare e interrompere la stampa"], [r.locator(".set-switch__detail").inner_text() for r in rows.all()])
    ok("all on at first", all(r.get_attribute("aria-checked") == "true" for r in rows.all()))
    ok("no sign of the service yet: the line says so and what to do", "non si è ancora fatto vivo" in pg.locator(".set-status").first.inner_text() and "klippeye status" in pg.locator(".set-status").first.inner_text(), pg.locator(".set-status").first.inner_text())
    switch(P, "Stampante in pausa").click(); switch(P, "IA: difetti gravi").click(); P.settle(300)
    ok("a switch moves at once", not checked(P, "Stampante in pausa") and not checked(P, "IA: difetti gravi") and checked(P, "Stampa completata"))
    ok("... and the Raspberry gets it", wait_until(lambda: stored()["notifications"]["paused"] is False and stored()["notifications"]["ai_cancel"] is False and stored()["notifications"]["complete"] is True), stored()["notifications"])
    back(P)
    ok("the list says how many are on", pg.locator('.set-entry[data-page="notifications"] .set-entry__meta').inner_text() == "5 su 7 attive")
    go(P, "notifications")
    ok("language of the notifications: this device's (Italiano) at first, and the Raspberry has it", choice(pg, "Italiano").get_attribute("aria-checked") == "true" and stored()["language"] == "it", stored().get("language"))
    choice(pg, "English").click(); P.settle(300)
    ok("English: the list shows the texts the phones will get, the page stays Italian", pg.locator(".set-switch__detail").first.inner_text() == "Printer error! Restart it." and pg.locator(".set-switch__title").first.inner_text() == "Stampante in errore", pg.locator(".set-switch__detail").first.inner_text())
    ok("... and the Raspberry gets it", wait_until(lambda: stored()["language"] == "en"), stored().get("language"))
    old = {k: v for k, v in stored().items() if k != "language"}; old["_t"] = NOW_MS() + 5000; db_write("settings", old)
    P.goto("home", 1400); open_menu(P)
    ok("settings saved by an older release (no language): the dashboard adds this device's", wait_until(lambda: stored().get("language") == "it", 5), stored().get("language"))
    close_menu(P)
    db_write("notifier", {"version": "1.1", "seen": int(time.time()) - 10})
    open_menu(P); go(P, "notifications")
    ok("the service is there: version and 'poco fa'", wait_until(lambda: "Servizio attivo" in pg.locator(".set-status").first.inner_text()) and "versione 1.1" in pg.locator(".set-status").first.inner_text() and "poco fa" in pg.locator(".set-status").first.inner_text(), pg.locator(".set-status").first.inner_text())
    ok("... in green", "set-status--ok" in pg.locator(".set-status").first.get_attribute("class"))
    close_menu(P)
    db_write("notifier", {"version": "1.1", "seen": int(time.time()) - 1500})
    open_menu(P); go(P, "notifications")
    ok("not seen for 25 minutes: 'non risponde da 25 min fa' in amber, with the command that checks", wait_until(lambda: "non risponde" in pg.locator(".set-status").first.inner_text()) and "25 min" in pg.locator(".set-status").first.inner_text() and "klippeye status" in pg.locator(".set-status").first.inner_text() and "set-status--warn" in pg.locator(".set-status").first.get_attribute("class"), pg.locator(".set-status").first.inner_text())
    P.close()

    # ============================================================================================ AI monitor
    P = fresh(b)
    pg = P.pg
    open_menu(P); go(P, "ai")
    P.shot_vp(f"{out}/menu_ai_390.png")
    ok("automatic actions are OFF at first", not checked(P, "Metti in pausa da solo") and not checked(P, "Cancella da solo"))
    ok("1 verdict, 70% confidence (the backend's one threshold), every defect counts at first", pg.locator('.set-chips[aria-label="Controlli di fila"] .oui-chip.is-selected').inner_text() == "1 controllo" and wait_until(lambda: pg.locator('.set-chips[aria-label="Fiducia minima dell\'IA"] .oui-chip.is-selected').inner_text() == "70%") and all(checked(P, t) for t in ("Spaghetti", "Piatto vuoto", "Layer shift", "Warping")))
    ok("the service not being there is said (it does the work)", "non si è ancora fatto vivo" in pg.locator(".set-status").first.inner_text())
    switch(P, "Metti in pausa da solo").click(); P.settle(200)
    ok("auto pause: on at once, no question asked", checked(P, "Metti in pausa da solo") and pg.locator(".confirm-overlay").count() == 0 and wait_until(lambda: stored()["ai"]["autoPause"] is True), stored()["ai"])
    switch(P, "Cancella da solo").click(); pg.wait_for_selector(".confirm-overlay"); P.settle(400)
    ok("auto cancel: asks first, with the warning", "Cancellare le stampe da solo?" in pg.locator(".confirm-card").inner_text() and "non si recupera" in pg.locator(".confirm-card").inner_text())
    cx_, cy_ = pg.locator(".confirm-card").bounding_box()["x"] + 40, pg.locator(".confirm-card").bounding_box()["y"] + 40
    ok("... the question lies above the menu", pg.evaluate("([x, y]) => !!document.elementFromPoint(x, y).closest('.confirm-card')", [cx_, cy_]))
    P.shot_vp(f"{out}/menu_ai_confirm_390.png")
    pg.locator(".confirm-card button:has-text('Annulla')").click(); P.settle(400)
    ok("'Annulla': stays off, nothing saved", not checked(P, "Cancella da solo") and stored()["ai"]["autoCancel"] is False)
    switch(P, "Cancella da solo").click(); pg.wait_for_selector(".confirm-overlay"); pg.locator(".confirm-card button:has-text('Attiva')").click(); P.settle(500)
    ok("'Attiva': on, and sent to the Raspberry", checked(P, "Cancella da solo") and wait_until(lambda: stored()["ai"]["autoCancel"] is True), stored()["ai"])
    switch(P, "Cancella da solo").click(); P.settle(300)
    ok("switching it off needs no question", not checked(P, "Cancella da solo") and pg.locator(".confirm-overlay").count() == 0 and wait_until(lambda: stored()["ai"]["autoCancel"] is False))
    pg.locator('.set-chips[aria-label="Controlli di fila"] .oui-chip', has_text="2 di fila").click(); pg.locator('.set-chips[aria-label="Fiducia minima dell\'IA"] .oui-chip', has_text="90%").click(); switch(P, "Warping").click(); P.settle(1500)
    ok("verdicts in a row, defects: each one is a choice that is kept (shared settings)", wait_until(lambda: stored()["ai"]["confirmations"] == 2 and stored()["ai"]["defects"]["warping"] is False and stored()["ai"]["defects"]["spaghetti"] is True), stored()["ai"])
    ok("1.19: the ONE confidence threshold is the backend's (ai_min_confidence), with a warning above 85%", wait_until(lambda: any(e.get("ai_min_confidence") == 90 for e in json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())["brain_cfg_log"]), 4)
       and "potrebbe NON essere fermata" in pg.locator(".fn-confidence").inner_text(), pg.locator(".drawer__body").inner_text()[:600])
    ok("... and the chips show the choice", pg.locator('.set-chips[aria-label="Controlli di fila"] .oui-chip.is-selected').inner_text() == "2 di fila" and pg.locator('.set-chips[aria-label="Fiducia minima dell\'IA"] .oui-chip.is-selected').inner_text() == "90%")
    back(P)
    ok("the list shows the automatic actions", pg.locator('.set-entry[data-page="ai"] .set-entry__meta').inner_text() == "Solo la fascia esterna • Pausa da sola: sì", pg.locator('.set-entry[data-page="ai"] .set-entry__meta').inner_text())
    close_menu(P)
    db_write("notifier", {"version": "1.1", "seen": int(time.time()) - 5, "lastAction": {"kind": "pause", "ok": True, "at": int(time.time()) - 60}})
    open_menu(P); go(P, "ai")
    ok("the last automatic action of the service is reported", wait_until(lambda: "Ultima azione automatica: stampa messa in pausa" in pg.locator(".drawer__body").inner_text()), pg.locator(".drawer__body").inner_text()[:400])
    P.close()

    # ============================================================================================ restore
    P = fresh(b)
    pg = P.pg
    open_menu(P); go(P, "notifications"); switch(P, "Stampa completata").click(); back(P); go(P, "camera"); choice(pg, "MJPEG").click(); back(P); P.settle(300)
    pg.locator('button:has-text("Ripristina i valori iniziali")').click(); pg.wait_for_selector(".confirm-overlay"); pg.locator(".confirm-card button:has-text('Annulla')").click(); P.settle(400)
    ok("restore: 'Annulla' changes nothing", settings_now(P)["camera"]["method"] == "mjpeg" and settings_now(P)["notifications"]["complete"] is False)
    pg.locator('button:has-text("Ripristina i valori iniziali")').click(); pg.wait_for_selector(".confirm-overlay"); pg.locator(".confirm-card button:has-text('Ripristina')").click(); P.settle(600)
    ok("restore: everything is back to the start, here and on the Raspberry", settings_now(P) == DEFAULTS and wait_until(lambda: {k: v for k, v in stored().items() if k != "_t"} == DEFAULTS), (settings_now(P), stored()))
    ok("... the camera too", pg.locator(".camera-frame iframe").get_attribute("src") == "http://172.25.170.177/webcam/webrtc")
    P.close()

    # ============================================================================================ the Android app (addresses)
    WV = "Mozilla/5.0 (Linux; Android 13; Pixel 7 Build/TQ3A; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0 Mobile Safari/537.36"

    def app_init(version, refuse=""):
        """What the app is to the page: its user agent, and the bridge (here it only records what it is told)."""
        agent = "Object.defineProperty(navigator,'userAgent',{get:()=>%s});" % json.dumps(WV + (" KlippEyeApp/%d" % version if version else ""))
        if version >= 4:
            bridge = ("window.__app = { calls: [], pair: { local: '192.168.1.17', external: '172.25.170.177' } };"
                      "window.KlippEyeApp = { saveUrl() {}, setAddresses(l, e) { window.__app.calls.push([l, e]); const refuse = %s; if (refuse) return refuse; window.__app.pair = { local: l, external: e }; return 'ok'; },"
                      " getAddresses() { return JSON.stringify(window.__app.pair); } };") % json.dumps(refuse)
        else:
            bridge = "window.KlippEyeApp = { saveUrl() {} };" if version else ""
        return agent + bridge

    calls = lambda P: P.pg.evaluate("() => window.__app ? window.__app.calls : null")
    app_note = lambda P: P.pg.locator(".drawer__body .set-group__note, .drawer__body .set-status").last.inner_text()

    P = fresh(b)
    open_menu(P); go(P, "network")
    ok("browser: the note says the app takes these addresses (from mk218)", "mk218" in app_note(P) and "set-group__note--warn" not in P.pg.locator(".drawer__body .set-group__note").last.get_attribute("class"), app_note(P))
    ok("browser: there is no bridge to talk to and no klippeyeSetAddresses", P.pg.evaluate("() => typeof window.KlippEyeApp + ' ' + typeof window.klippeyeSetAddresses") == "undefined undefined")
    P.close()

    P = fresh(b, init=app_init(3))
    open_menu(P); go(P, "network")
    ok("an app older than mk218: the note says it has its own addresses, in amber", "ha gli indirizzi scritti dentro" in app_note(P) and "set-group__note--warn" in P.pg.locator(".drawer__body .set-group__note").last.get_attribute("class"), app_note(P))
    ok("... and nothing is sent to it (no setAddresses, no klippeyeSetAddresses)", P.pg.evaluate("() => typeof window.KlippEyeApp.setAddresses + ' ' + typeof window.klippeyeSetAddresses") == "undefined undefined")
    P.close()

    P = fresh(b, init=app_init(4))
    pg = P.pg
    ok("app mk218, first start (nothing stored yet): the app is told the addresses once, as they are", wait_until(lambda: calls(P) == [["192.168.1.17", "172.25.170.177"]]), calls(P))
    open_menu(P); go(P, "network")
    ok("... and the menu says the app will use them (green)", wait_until(lambda: "userà questi indirizzi" in app_note(P)) and "set-status--ok" in pg.locator(".drawer__body .set-status").last.get_attribute("class"), app_note(P))
    inputs = pg.locator(".set-field__input")
    type_into(inputs.nth(0), "192.168.1.50"); inputs.nth(0).press("Enter"); P.settle(400)
    ok("a new local address in the menu: the app has it at once", calls(P)[-1] == ["192.168.1.50", "172.25.170.177"] and len(calls(P)) == 2, calls(P))
    ok("... and the menu still says it will use them", "userà questi indirizzi" in app_note(P), app_note(P))
    type_into(inputs.nth(1), "http://10.9.8.7:8080/"); inputs.nth(1).press("Enter"); P.settle(400)
    ok("an address typed with http:// and a port: the app gets the plain address", calls(P)[-1] == ["192.168.1.50", "10.9.8.7"], calls(P))
    type_into(inputs.nth(1), "999.9.9.9"); P.settle(1300)
    ok("a wrong address is not sent to the app", len(calls(P)) == 3, calls(P))
    inputs.nth(1).press("Enter"); P.settle(300)
    back(P); go(P, "camera"); choice(pg, "MJPEG").click(); P.settle(300)
    ok("a setting that is not an address changed: the app is not told again", len(calls(P)) == 3, calls(P))
    ok("the addresses reached the Raspberry too (one document for everybody; the dashboard keeps the port, for a camera on another one)", wait_until(lambda: stored()["network"]["localIp"] == "192.168.1.50" and stored()["network"]["externalIp"] == "10.9.8.7:8080"), stored()["network"])
    P.close()

    P = fresh(b, init=app_init(4, refuse="L'IP esterno deve essere di una rete privata (ZeroTier, VPN)"))
    pg = P.pg
    wait_until(lambda: calls(P))
    open_menu(P); go(P, "network")
    type_into(pg.locator(".set-field__input").nth(1), "8.8.8.8"); pg.locator(".set-field__input").nth(1).press("Enter"); P.settle(400)
    ok("an address the app refuses (not a private network): the menu says so, in amber", "non ha accettato" in app_note(P) and "set-group__note--warn" in pg.locator(".drawer__body .set-group__note").last.get_attribute("class"), app_note(P))
    ok("... while the dashboard itself keeps the address (the camera may well be there)", settings_now(P)["network"]["externalIp"] == "8.8.8.8")
    P.close()

    # the page of a device that has not asked the Raspberry yet must not tell the app the defaults
    P = fresh(b, init=app_init(4), db_mode="down")
    wait_until(lambda: False, 1.5)
    ok("the Raspberry does not answer and nothing is stored here: the app is told nothing (its own addresses stay)", calls(P) == [], calls(P))
    open_menu(P); go(P, "network")
    ok("... the menu waits instead of claiming anything", "riceve appena sono noti" in app_note(P), app_note(P))
    pg = P.pg
    type_into(pg.locator(".set-field__input").nth(0), "192.168.1.60"); pg.locator(".set-field__input").nth(0).press("Enter"); P.settle(400)
    ok("... once the person changes an address the app gets the pair", calls(P) == [["192.168.1.60", "172.25.170.177"]], calls(P))
    P.close()

    mock.reset()
    other = json.loads(json.dumps(DEFAULTS)); other["network"] = {"localIp": "192.168.1.60", "externalIp": "172.25.9.9", "route": "auto"}; other["camera"]["method"] = "mjpeg"; other["_t"] = NOW_MS() - 1000
    db_write("settings", other)
    P = fresh(b, reset=False, init=app_init(4))
    ok("a device that opens with the Raspberry's settings: the app gets THOSE addresses and never the defaults", wait_until(lambda: calls(P) == [["192.168.1.60", "172.25.9.9"]]), calls(P))
    P.close()

    # the app's own "Indirizzi" window (shown when it cannot connect) tells the page through klippeyeSetAddresses
    mock.reset()
    other2 = json.loads(json.dumps(DEFAULTS)); other2["camera"]["method"] = "mjpeg"; other2["zOffset"]["steps"] = [0.02, 0.2]; other2["_t"] = NOW_MS() - 1000
    db_write("settings", other2)
    P = fresh(b, reset=False, init=app_init(4))
    ok("klippeyeSetAddresses exists in the app", P.pg.evaluate("() => typeof window.klippeyeSetAddresses") == "function")
    P.pg.evaluate("() => window.klippeyeSetAddresses('10.0.0.9', '172.25.1.1')"); P.settle(300)
    ok("... it sets both addresses here", settings_now(P)["network"]["localIp"] == "10.0.0.9" and settings_now(P)["network"]["externalIp"] == "172.25.1.1", settings_now(P)["network"])
    ok("... on the Raspberry too, with all the OTHER settings as they were (not the defaults of a page that had not asked)", wait_until(lambda: stored()["network"]["localIp"] == "10.0.0.9" and stored()["camera"]["method"] == "mjpeg" and stored()["zOffset"]["steps"] == [0.02, 0.2]), stored())
    ok("... and the app ends with the new pair (not with the Raspberry's old one)", calls(P)[-1] == ["10.0.0.9", "172.25.1.1"] and P.pg.evaluate("() => window.__app.pair.local") == "10.0.0.9", calls(P))
    P.pg.evaluate("() => window.klippeyeSetAddresses('999.1.1.1', '172.25.1.1')"); P.settle(300)
    P.pg.evaluate("() => window.klippeyeSetAddresses('', null)"); P.settle(300)
    ok("wrong addresses given to klippeyeSetAddresses change nothing", settings_now(P)["network"]["localIp"] == "10.0.0.9" and stored()["network"]["localIp"] == "10.0.0.9")
    P.close()

    # ============================================================================================ looks: narrow and wide screens, every page
    for w, h in ((390, 844), (360, 740), (320, 640), (1440, 900)):
        P = fresh(b, w, h, printing=True)
        pg = P.pg
        open_menu(P)
        bad = []
        for name in ("home", "camera", "network", "zoffset", "notifications", "ai", "detector", "software"):
            if name != "home": go(P, name)
            if name == "camera":
                choice(pg, "MJPEG adaptive").click(); P.settle(300)
            ov = overflow(P)
            small = pg.evaluate("""() => Array.from(document.querySelectorAll('.drawer button, .drawer input')).filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.height < 34 || r.width < 34) && !e.matches('.oui-btn--sm'); }).map(e => (e.getAttribute('aria-label') || e.textContent || e.className).slice(0, 30))""")
            clipped = pg.evaluate("""() => Array.from(document.querySelectorAll('.drawer .set-switch__title, .drawer .set-switch__detail, .drawer .oui-row__name, .drawer .oui-row__meta, .drawer .set-group__note, .drawer .set-field__label')).filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.textContent.slice(0, 30))""")
            if ov["page"] > 0 or ov["body"] > 0 or small or clipped: bad.append((name, ov, small, clipped))
            P.shot_vp(f"{out}/menu_{name}_{w}.png", h)
            if name != "home": back(P)
        ok("[%d] every page of the menu: no sideways overflow, buttons big enough to touch, no clipped text" % w, not bad, bad)
        box = pg.locator(".drawer").bounding_box()
        ok("[%d] the menu fits the screen" % w, box["x"] == 0 and box["width"] <= min(420, w - 40) + 0.5 and box["y"] == 0 and box["height"] <= h + 1, box)
        close_menu(P)
        hdr = pg.evaluate("() => { const r = document.querySelector('.app-header__actions').getBoundingClientRect(); const m = document.querySelector('.header-btn--menu').getBoundingClientRect(); return { right: r.right, vw: innerWidth, menu: [m.left, m.right], page: document.documentElement.scrollWidth - document.documentElement.clientWidth }; }")
        ok("[%d] the top bar still fits with the new button" % w, hdr["right"] <= w and hdr["page"] <= 0 and hdr["menu"][0] >= 0, hdr)
        ok("[%d] no errors in the page" % w, not [e for e in P.errors if "pageerror" in e], P.errors[:3])
        P.close()

    # ============================================================================================ language
    P = fresh(b)
    pg = P.pg
    open_menu(P)
    meta = lambda: pg.locator('.set-entry[data-page="language"] .set-entry__meta').inner_text()
    ok("language: an Italian device gets the Italian page, and the list says it follows the device", pg.evaluate("() => document.documentElement.lang") == "it" and meta() == "Automatica (Italiano)", meta())
    go(P, "language")
    titles = pg.locator(".set-choice .set-switch__title").all_inner_texts()
    ok("... three choices: automatic (selected), English, Italiano", titles == ["Automatico", "English", "Italiano"] and choice(pg, "Automatico").get_attribute("aria-checked") == "true", titles)
    ok("... the automatic one names the device's language", "Italiano" in choice(pg, "Automatico").inner_text())
    choice(pg, "English").click(); pg.wait_for_load_state("load"); P.settle(1500)
    ok("choosing English reloads the page in English", pg.evaluate("() => document.documentElement.lang") == "en" and pg.locator('.app-header button[aria-label="Settings"]').count() == 1)
    ok("... the choice stays on this device only (the notifications' language, shared, does not change)", pg.evaluate("() => localStorage.getItem('ke_lang')") == "en" and (settings_now(P) or {}).get("language") == "it", (pg.evaluate("() => localStorage.getItem('ke_lang')"), (settings_now(P) or {}).get("language")))
    pg.click('button[aria-label="Settings"]'); pg.wait_for_selector(".drawer"); P.settle(450)
    titles = pg.locator(".set-entry .oui-row__name").all_inner_texts()
    ok("... the menu is in English", titles == ["Printer", "Printer functions", "Camera", "Addresses", "Z-offset", "Notifications", "AI monitor", "Access", "Updates", "Language"] and meta() == "English", (titles, meta()))
    go(P, "language"); choice(pg, "Automatic").click(); pg.wait_for_load_state("load"); P.settle(1500)
    ok("back to automatic: Italian again, and nothing kept", pg.evaluate("() => document.documentElement.lang") == "it" and pg.evaluate("() => localStorage.getItem('ke_lang')") is None)
    ok("no errors in the page", not P.errors, P.errors[:3])
    P.close()

    P = fresh(b, locale="en-US")
    pg = P.pg
    words = pg.evaluate("() => document.body.innerText")
    italian = [w for w in (" della ", " degli ", "Stampante", "Ventol", "Temperatur", "Impostazioni", " non ", "Caricamento") if w in words]
    ok("an English device gets the English page, with no Italian text on it", pg.evaluate("() => document.documentElement.lang") == "en" and not italian, italian)
    for tab in ("controllo", "files", "config", "sistema"):
        P.goto(tab, 900)
        words = pg.evaluate("() => document.body.innerText")
        italian = [w for w in (" della ", " degli ", "Stampante", "Ventol", "Temperatur", "Impostazioni", " non ", "Caricamento", " il ", " di ") if w in words]
        ok("... the %s page too" % tab, not italian, (italian, [l for l in words.splitlines() if any(w.strip() in l for w in italian)][:6]))
    ok("no errors in the page", not P.errors, P.errors[:3])
    P.close()

    # ============================================================================================ nothing else is touched
    P = fresh(b)
    pg = P.pg
    P.reqs.clear()
    open_menu(P)
    for name in ("camera", "network", "zoffset", "notifications", "ai", "detector", "software"):
        go(P, name); back(P)
    close_menu(P); P.settle(800)
    other = [r for r in P.reqs if r["m"] != "GET" and "/server/database/item" not in r["u"]]
    ok("looking at every page of the menu sends nothing to the printer (no G-code, no commands)", not other and mock.gcode() == [], (other, mock.gcode()))
    ok("... and reads only the settings, the service's key and the update channel", all("/server/database/item" in r["u"] or r["u"].split("?")[0].startswith(POLL_PATHS + ("/api/update/channel", "/api/ai/config")) or r["u"].startswith("EXT") for r in P.reqs if r["m"] == "GET"), [r["u"] for r in P.reqs if r["m"] == "GET" and "/server/database/item" not in r["u"] and not r["u"].split("?")[0].startswith(POLL_PATHS)][:5])
    ok("no errors in the page", not P.errors, P.errors[:3])
    P.close()
    b.close()

print("FAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
