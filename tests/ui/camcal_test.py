"""Release 1.13.0: "Calibra la telecamera" (roadmap phase 4a) with the REAL backend, a fake Klipper that moves when told and a
fake camera that draws the printer as a fisheye camera in front of it would see it (bed, markers, toolhead, nozzle tip).
The test taps where the nozzle tip and the markers really are, as a person would, and checks the whole path: kind of printer,
homing, the markers (quick blobs, then the printed pyramids read from their G-code), twelve points with the magnified view, calculation, saving, the live drawing, the camera moved.
Usage: camcal_test.py <html> <outdir> <port>"""
import importlib.util
import os
import shutil
import sys
import tempfile
import threading
import time
from playwright.sync_api import sync_playwright

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(out, exist_ok=True)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tests", "backend"))
sys.path.insert(0, os.path.join(ROOT, "tests", "backend", "stubs"))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import fakes  # noqa: E402
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import camera_model as cm  # noqa: E402

FAILS = []


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:500]) if (extra != "" and not cond) else ""), flush=True)


# --- the virtual camera: in front of the bed, high, looking down (like the user's), fisheye
W, H = 1280, 720


def look_at(cam, target):
    fwd = np.asarray(target, float) - cam
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    rot = np.stack([right, np.cross(fwd, right), fwd])
    return rot, -rot @ cam


ROT, T = look_at(np.array([175.0, -70.0, 110.0]), [175.0, 210.0, -60.0])
CAM = {"model": "fisheye", "width": W, "height": H, "params": [W / 3.0, W / 2 + 12, H / 2 - 8, 0.02, -0.01] + list(cm.rotation_to_vector(ROT)) + list(T)}
rng = np.random.default_rng(5)
BACKGROUND = cv2.GaussianBlur((rng.random((H + 60, W + 60)) * 120 + 40).astype(np.uint8), (7, 7), 0)


def px(points):
    uv, front = cm.project(CAM, points)
    return (uv * [W, H]).astype(np.int32), front


def render(state):
    dx, dy = state.get("cam_shift", (0, 0))
    img = cv2.cvtColor(BACKGROUND[30 + dy:30 + dy + H, 30 + dx:30 + dx + W], cv2.COLOR_GRAY2BGR)
    x, y, z = state["position"]
    bed_z = -z
    edge = [[a, b, bed_z] for a, b in [(0, 0), (350, 0), (350, 350), (0, 350)]]
    corners = []
    for i in range(4):
        for s in np.linspace(0, 1, 20):
            corners.append(np.array(edge[i]) + (np.array(edge[(i + 1) % 4]) - np.array(edge[i])) * s)
    pts, front = px(corners)
    cv2.fillPoly(img, [pts[front]], (60, 70, 120))
    for mx, my, mh in state.get("markers") or []:   # what is on the bed: the printed pyramids (their tips) or the blobs
        p, f = px([[mx, my, bed_z + mh]])
        if f[0]:
            cv2.circle(img, tuple(int(c) for c in p[0]), 5, (60, 220, 90), -1)
    box = cm.box_corners(x - 30, x + 30, y - 35, y + 35, 1, 70)
    outline = cm.box_outline(CAM, box)
    if outline:
        cv2.fillPoly(img, [(np.array(outline) * [W, H]).astype(np.int32)], (30, 30, 30))
    p, f = px([[x, y, 0.0]])
    if f[0]:
        cv2.circle(img, tuple(int(c) for c in p[0]), 4, (40, 40, 255), -1)
    return fakes.jpeg(img)


root = tempfile.mkdtemp(prefix="ke-camcal-")
repo, data = os.path.join(root, "klippeye"), os.path.join(root, "data")
os.makedirs(os.path.join(repo, "backend"))
os.makedirs(os.path.join(repo, "frontend"))
for name in os.listdir(os.path.join(ROOT, "backend")):
    if name.endswith(".py"):
        shutil.copy(os.path.join(ROOT, "backend", name), os.path.join(repo, "backend", name))
shutil.copy(html, os.path.join(repo, "frontend", "klippeye_frontend.html"))
shutil.copytree(os.path.join(ROOT, "frontend", "src", "i18n"), os.path.join(repo, "frontend", "src", "i18n"))   # the backend's messages in Italian
open(os.path.join(repo, "VERSION"), "w").write("1.13.0\n")
os.environ["KLIPPEYE_DATA"] = data
fake = fakes.Fake()
fake.state.update({"render": render, "print_state": "standby", "homed": "", "position": [175.0, 175.0, 20.0]})
PRINTED = fakes.sliced_markers(fake.state["axis_min"], fake.state["axis_max"], 3.0, -2.0)
fake.state["gcodes"] = {"vase.gcode": "G90\nM83\nG1 Z0.2\nG1 X10 Y10 E5\n", "klippeye-camera-markers_0.2mm_PLA.gcode": PRINTED}
os.makedirs(data, exist_ok=True)
open(os.path.join(data, "monitor.json"), "w").write('{"values": {"enabled": false}}')
spec = importlib.util.spec_from_file_location("ke_backend", os.path.join(repo, "backend", "klippeye_backend.py"))
b = importlib.util.module_from_spec(spec)
sys.modules["ke_backend"] = b
spec.loader.exec_module(b)
b.MOONRAKER_URL = fake.url
b.CAMERA_NGINX_URL = fake.url + "/webcam"
from werkzeug.serving import make_server  # noqa: E402
server = make_server("127.0.0.1", port, b.app, threaded=True)
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % port


def wait(pg, fn, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        pg.wait_for_timeout(150)
    return False


def body(pg):
    return pg.locator(".drawer__body").inner_text()


def click_fraction(pg, locator, u, v):
    locator.scroll_into_view_if_needed()
    pg.wait_for_timeout(400)   # the menu scrolls smoothly: measure once it has stopped
    box = locator.bounding_box()
    pg.mouse.click(box["x"] + u * box["width"], box["y"] + v * box["height"])


def truth(frame):
    uv, _ = cm.project(CAM, [frame])
    return float(uv[0][0]), float(uv[0][1])


with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_context(viewport={"width": 390, "height": 844}, locale="it-IT").new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(BASE + "/")
    pg.wait_for_selector('.app-header button[aria-label="Impostazioni"]', timeout=15000)
    pg.wait_for_timeout(800)
    pg.click('button[aria-label="Impostazioni"]')
    pg.wait_for_selector(".drawer")
    pg.wait_for_timeout(1500)
    pg.click('.set-entry[data-page="ai"]')   # 1.19: inside "Monitor IA"
    pg.wait_for_timeout(1500)
    ok("Monitor IA says what it looks at: only the outer band until the camera is calibrated", "Solo la fascia esterna" in body(pg), body(pg)[:400])
    entry = pg.locator('.set-entry[data-page="camcal"]')
    ok("'Monitor IA' has 'Calibrazione della telecamera', 'Non calibrata'", entry.count() == 1 and wait(pg, lambda: "Non calibrata" in entry.inner_text()), entry.inner_text() if entry.count() else "")
    entry.click()
    pg.wait_for_timeout(1200)
    ok("not calibrated: the page says so and offers to calibrate", wait(pg, lambda: "La telecamera non è calibrata" in body(pg)) and pg.locator('[data-start="1"]').count() == 1, body(pg)[:300])
    pg.click('[data-start="1"]')
    pg.wait_for_timeout(800)
    ok("step 1: how Z moves, guessed from Klipper (Z moves the bed)", "come si muove l'asse z?" in body(pg).lower() and "Dalla configurazione di Klipper sembra: Z muove il piatto." in body(pg), body(pg)[:600])
    pg.screenshot(path=os.path.join(out, "01_kind.png"))
    pg.locator("button", has_text="Avanti").click()
    # 1.128: Z moves the bed: first offered without printing anything (a detail of the toolhead), markers as the other way
    method = pg.locator('[role="radiogroup"][aria-label="Come calibrare"]')
    ok("1.128: 'Come calibrare': a detail of the toolhead chosen by default, with how to choose it", wait(pg, lambda: method.count() == 1)
       and "Un dettaglio della testina (niente da stampare)" in method.locator('[aria-checked="true"]').inner_text()
       and pg.locator("[data-detail-help]").count() == 1 and "la testa di una vite" in pg.locator("[data-detail-help]").inner_text(), body(pg)[-900:])
    ok("... nothing to print: no markers step, 12 points (the tip and the detail at six places)", pg.locator(".cal-target").count() == 12 and "Stampa i segni (consigliato)" not in body(pg)
       and "Piatto vuoto" in body(pg), body(pg)[-600:])
    ok("... before any tap: tap the tip and the detail at the first place, then it follows them", "segue da solo" in pg.locator('[data-auto="no-template"]').inner_text())
    pg.locator('.cal-target[data-target="feat1"]').click()
    words = pg.locator(".cal-instruction").inner_text()
    ok("... point 2: tap the detail of the toolhead (with its drawing)", "DETTAGLIO DELLA TESTINA" in words and pg.locator('.cal-instruction-row .cal-hint[aria-label*="dettaglio"]').count() == 1, words)
    pg.locator('.cal-target[data-target="tip1"]').click()
    ok("... point 1: the nozzle tip, the bed under it, no marker", "PUNTO PIÙ BASSO DELL'UGELLO" in pg.locator(".cal-instruction").inner_text() and "segno" not in pg.locator(".cal-instruction").inner_text())
    pg.locator(".drawer").screenshot(path=os.path.join(out, "01b_detail.png"))
    method.locator("button", has_text="Segni sul piatto").click()
    ok("1.128: 'Segni sul piatto': the markers' way as before", wait(pg, lambda: b.camera_cal.method() == "markers"))
    ok("... 'Avanti' keeps it: the markers step, no points yet", wait(pg, lambda: "segni sul piatto" in body(pg).lower() and "Stampa i segni (consigliato)" in body(pg)) and pg.locator(".cal-target").count() == 0, body(pg)[-600:])
    stl = pg.evaluate("async () => { const r = await fetch('/api/camera/markers.stl'); return [r.status, (await r.arrayBuffer()).byteLength]; }")
    ok("the STL link downloads the six pyramids", pg.locator('[data-stl="1"]').count() == 1 and stl == [200, 84 + 36 * 50], stl)
    ok("the printed file is offered first (its name says markers)", wait(pg, lambda: pg.locator('[data-file="1"]').input_value() == "klippeye-camera-markers_0.2mm_PLA.gcode"), body(pg)[-400:])
    ok("1.29.1 the markers step says where Z is homed (here: not known, Klipper's settings do not say)", "Non si sa dove fa l'homing di Z" in body(pg), body(pg)[-900:])
    pg.locator("button", has_text="Fai l'homing").click()
    risks = pg.locator("[data-risks]")
    ok("1.29.1 homing with the markers maybe on the bed: it asks first (place not known, no z_hop), nothing sent", wait(pg, lambda: risks.count() == 1) and risks.get_attribute("data-risks") == "unknown,no_hop"
       and "Se i segni stampati sono sul piatto" in risks.inner_text() and "z_hop" in risks.inner_text() and "G28" not in fake.scripts, risks.inner_text() if risks.count() else body(pg)[-500:])
    pg.click("[data-home-anyway]")
    ok("home: G28 sent and 'Homing fatto.'", wait(pg, lambda: "Homing fatto." in body(pg)) and "G28" in fake.scripts, fake.scripts)
    ok("1.29.1 ... and the motors stay on during the calibration (a long idle timeout)", any(sc.startswith("SET_IDLE_TIMEOUT TIMEOUT=3600") for sc in fake.scripts), fake.scripts[-4:])
    pg.locator(".oui-chip", has_text="Gocce rapide").click()
    ok("quick blobs: the temperatures can be chosen (210 / 60 to start)", wait(pg, lambda: pg.locator('[data-temp="nozzle"]').input_value() == "210" and pg.locator('[data-temp="bed"]').input_value() == "60"))
    pg.locator('[data-temp="nozzle"]').fill("225")
    pg.locator('[data-temp="bed"]').fill("70")
    pg.click('[data-marks="start"]')
    ok("the 6 blobs: the chosen temperatures, retraction and Z hop; the page says so", wait(pg, lambda: "6 gocce create" in body(pg), 12)
       and any("M109 S225" in sc and "M190 S70" in sc and sc.count("G0 Z5 F1200") == 6 for sc in fake.scripts) and pg.locator(".cal-target").count() == 12, body(pg)[-500:])
    pg.screenshot(path=os.path.join(out, "01b_blobs.png"))
    pg.locator(".oui-chip", has_text="Stampa i segni").click()
    wait(pg, lambda: pg.locator('[data-file="1"]').count() == 1)
    pg.locator('[data-file="1"]').select_option("vase.gcode")
    pg.click('[data-read="1"]')
    ok("a file without markers: the page says, next to the button, to print the markers file", wait(pg, lambda: "stampa il file dei segni di KlippEye" in pg.locator('[data-markers-error="1"]').inner_text()), body(pg)[:900])
    pg.locator('[data-file="1"]').select_option("klippeye-camera-markers_0.2mm_PLA.gcode")
    pg.click('[data-read="1"]')
    ok("the printed markers read from their G-code: 'trovati', 12 points", wait(pg, lambda: "6 segni trovati in klippeye-camera-markers_0.2mm_PLA.gcode" in body(pg)) and pg.locator(".cal-target").count() == 12, body(pg)[-500:])
    fake.state["markers"] = b.camera_cal.draft["markers"]["points"]
    pg.locator(".drawer").screenshot(path=os.path.join(out, "01c_markers.png"))
    targets = b.camera_cal.target_list()
    ok("1.29 before any tap: the page says to tap the nozzle once by hand, no 'find' button yet", pg.locator('[data-auto="no-template"]').count() == 1 and pg.locator("[data-find-all]").count() == 0)
    for n, t in enumerate(targets):
        if 1 <= n <= 5:
            continue   # 1.29: the other nozzle points are found by themselves (below)
        if n == 6:
            # --- 1.29: after one nozzle tapped by hand, the others found by themselves
            find_all = pg.locator("[data-find-all]")
            ok("1.29 after one nozzle tapped by hand: 'Trova l'ugello da solo negli altri 5 punti'", wait(pg, lambda: find_all.count() == 1 and "altri 5 punti" in find_all.inner_text()), body(pg)[-800:])
            find_all.click()
            ok("... it runs point by point, then says how many were found", wait(pg, lambda: pg.locator("[data-auto-done]").count() == 1, 90), body(pg)[-600:])
            props = b.camera_cal.draft.get("proposals") or {}
            errs = []
            for tt in targets[1:6]:
                pp = props.get(tt["id"]) or {}
                xx, yy, zz = pp.get("machine") or [0, 0, 0]
                tu_, tv_ = truth([xx, yy, 0.0])
                errs.append((tt["id"], pp.get("found"), round(abs((pp.get("u") or 0) - tu_) * W, 1), round(abs((pp.get("v") or 0) - tv_) * H, 1), pp.get("score")))
            ok("... the nozzle found at the 5 points, within 4 px of the real tip", all(e[1] and e[2] < 4 and e[3] < 4 for e in errs), errs)
            ok("... the toolhead went aside twice at each point and back (3 moves per point)", sum(1 for sc in fake.scripts if sc.startswith("G90\nG0 X") and sc.endswith("M400")) >= 15, fake.scripts[-6:])
            ok("... the numbers found are blue until used", pg.locator(".cal-target.is-proposed").count() == 5)
            pg.locator(".drawer").screenshot(path=os.path.join(out, "02b_found.png"))
            pg.click("[data-accept]")
            ok("'Usa i 5 punti trovati': they become points (marked as found)", wait(pg, lambda: len(b.camera_cal.draft.get("points") or {}) == 6)
               and all((b.camera_cal.draft["points"][tt["id"]].get("source") == "found") for tt in targets[1:6]), list((b.camera_cal.draft.get("points") or {}).keys()))
        pg.locator('.cal-target[data-target="%s"]' % t["id"]).click()
        if n in (0, 6):
            hint = pg.locator(".cal-instruction-row .cal-hint")
            words = pg.locator(".cal-instruction").inner_text()
            ok("point %d: a drawing and words say what to tap (%s)" % (n + 1, "the nozzle" if t["kind"] == "nozzle" else "the tip of the marker"), hint.count() == 1
               and (("PUNTO PIÙ BASSO DELL'UGELLO" in words and "non il segno" in words) if t["kind"] == "nozzle" else "PUNTA IN ALTO del segno" in words), words)
        pg.click('[data-go="%s"]' % t["id"])
        wait(pg, lambda: pg.locator(".cal-pick .cal-frame__img").count() == 1)
        pg.wait_for_timeout(500)
        x, y, z = fake.state["position"]
        frame = [x, y, 0.0] if t["kind"] == "nozzle" else [t["x"], t["y"], t["height"] - z]
        u, v = truth(frame)
        img = pg.locator(".cal-pick .cal-frame__img")
        click_fraction(pg, img, u + 0.01, v - 0.012)   # a first, rough tap
        wait(pg, lambda: pg.locator(".cal-loupe").count() == 1)
        loupe = pg.locator(".cal-loupe")
        line = pg.locator(".cal-pick .cal-frame .cal-cross--tap line").first   # where the page put the rough tap
        ru, rv = float(line.get_attribute("x1")) + 0.03, float(line.get_attribute("y1"))
        if n == 0:
            ok("the rough tap is where it was clicked (within about one screen pixel)", abs(ru - (u + 0.01)) * W < 6 and abs(rv - (v - 0.012)) * H < 6, (ru, rv, u + 0.01, v - 0.012))
        size = 1 / 4
        left = min(1 - size, max(0, ru - size / 2))
        top = min(1 - size, max(0, rv - size / 2))
        click_fraction(pg, loupe, (u - left) / size, (v - top) / size)   # the precise one in the magnified view
        if n == 0:
            pg.screenshot(path=os.path.join(out, "02_point.png"), full_page=False)
            pg.locator(".drawer").screenshot(path=os.path.join(out, "02_point_drawer.png"))
        pg.click('[data-keep="%s"]' % t["id"])
        wait(pg, lambda: t["id"] in (b.camera_cal.draft.get("points") or {}), 4)
    pts = b.camera_cal.draft.get("points") or {}
    ok("12 points taken through the page (7 by hand, 5 found by themselves)", len(pts) == 12, list(pts))
    ok("1.29 the nozzle template was kept after the first tap", b.camera_cal.has_template() or os.path.isfile(os.path.join(data, "camera_tip.png")))
    first = pts[targets[0]["id"]]
    tu, tv = truth([targets[0]["x"], targets[0]["y"], 0.0])
    ok("... the magnified tap lands within 2 px of the real nozzle tip", abs(first["u"] - tu) * W < 2.5 and abs(first["v"] - tv) * H < 2.5, (first, tu, tv))
    ok("the targets turn green when taken", wait(pg, lambda: pg.locator(".cal-target.is-done").count() == 12), pg.locator(".cal-target.is-done").count())
    pg.click('[data-fit="1"]')
    ok("calculate: average error in pixels, 'buona'", wait(pg, lambda: "Errore medio" in body(pg) and "buona" in body(pg), 30), body(pg)[-600:])
    ok("... the live picture with the toolhead and the bed drawn", wait(pg, lambda: pg.locator(".cal-toolhead").count() == 1 and pg.locator(".cal-bed").count() == 1 and pg.locator(".cal-cross--nozzle").count() == 1))
    pg.locator(".drawer__body").evaluate("e => e.scrollTop = e.scrollHeight")
    pg.wait_for_timeout(1600)
    pg.locator(".drawer").screenshot(path=os.path.join(out, "03_fit.png"))
    pg.click('[data-save="1"]')
    ok("save: 'Calibrata il … con 12 punti'", wait(pg, lambda: "con 12 punti" in body(pg), 10) and os.path.isfile(os.path.join(data, "camera.json")), body(pg)[:300])
    ok("1.29.1 ... Klipper's idle timeout put back (600 s, the default)", any(sc == "SET_IDLE_TIMEOUT TIMEOUT=600" for sc in fake.scripts), [sc for sc in fake.scripts if "IDLE" in sc])
    ok("... and the camera is said to be in place", wait(pg, lambda: "ancora al suo posto" in body(pg)), body(pg)[:400])
    pg.locator("button", has_text="X +20").click()
    pg.wait_for_timeout(2200)
    ov = b.camera_cal.overlay()
    tx_, ty_ = truth([fake.state["position"][0], fake.state["position"][1], 0.0])
    ok("live check: after a jog the nozzle is drawn where it really is (within 1%)", abs(ov["nozzle"][0] - tx_) < 0.01 and abs(ov["nozzle"][1] - ty_) < 0.01, (ov["nozzle"], tx_, ty_))
    pg.locator(".drawer").screenshot(path=os.path.join(out, "04_saved.png"))
    ok("saved page: toolhead and gantry drawn on the live picture, with their sizes", wait(pg, lambda: pg.locator(".cal-gantry").count() == 10 and pg.locator(".cal-toolhead").count() == 1)
       and pg.locator('[data-value="toolhead.left"]').inner_text().startswith("30"), body(pg)[-800:])
    before = pg.locator(".cal-toolhead").get_attribute("points")
    pg.click('[data-size="toolhead.left.plus"]')
    ok("+ on 'left of the nozzle': 35 mm, saved, and the purple outline grows", wait(pg, lambda: pg.locator('[data-value="toolhead.left"]').inner_text().startswith("35")
       and b.camera_cal.get_shape()["toolhead"]["left"] == 35.0 and pg.locator(".cal-toolhead").get_attribute("points") != before), b.camera_cal.get_shape())
    # --- 1.29: the dots on the picture
    handle = pg.locator('[data-handle="toolhead.top"]')
    ok("1.29 the live picture has dots for the sizes (up to 5 of the toolhead and 2 of the gantry, never on top of each other: few on this small, far camera), the top one among them", wait(pg, lambda: 2 <= pg.locator("[data-handle]").count() <= 7 and pg.locator("[data-handle=\"toolhead.top\"]").count() == 1), pg.locator("[data-handle]").count())
    top0 = b.camera_cal.get_shape()["toolhead"]["top"]
    ov = b.camera_cal.overlay()
    per = next(hh["per_mm"] for hh in ov["handles"] if hh["key"] == "toolhead.top")
    frame_box = pg.locator(".cal-frame").first.bounding_box()
    handle.scroll_into_view_if_needed()
    pg.wait_for_timeout(400)
    hb = handle.bounding_box()
    frame_box = pg.locator(".cal-frame").first.bounding_box()
    cx_, cy_ = hb["x"] + hb["width"] / 2, hb["y"] + hb["height"] / 2
    pg.mouse.move(cx_, cy_)
    pg.mouse.down()
    for k in range(1, 11):   # drag 20 mm higher, along the dot's own direction
        pg.mouse.move(cx_ + per[0] * frame_box["width"] * 2 * k, cy_ + per[1] * frame_box["height"] * 2 * k)
        pg.wait_for_timeout(60)
    ok("... dragging the top dot shows the size while dragging", "Sopra la punta dell'ugello" in pg.locator("[data-handle-line]").inner_text(), pg.locator("[data-handle-line]").inner_text())
    pg.mouse.up()
    ok("... and on release the height of the toolhead is 20 mm more (saved)", wait(pg, lambda: abs(b.camera_cal.get_shape()["toolhead"]["top"] - (top0 + 20)) <= 1, 4)
       and wait(pg, lambda: pg.locator('[data-value="toolhead.top"]').inner_text().startswith(str(int(b.camera_cal.get_shape()["toolhead"]["top"])))), (top0, b.camera_cal.get_shape()["toolhead"]))
    pg.locator(".cal-frame").first.screenshot(path=os.path.join(out, "05b_handles.png"))
    pg.locator(".set-switch", has_text="Escludi anche il gantry").click()
    ok("gantry switched off: the orange bar goes away (and its dots)", wait(pg, lambda: pg.locator(".cal-gantry").count() == 0) and b.camera_cal.get_shape()["gantry"]["on"] is False and wait(pg, lambda: pg.locator("[data-handle^=\"gantry\"]").count() == 0))
    pg.locator(".set-switch", has_text="Escludi anche il gantry").click()
    wait(pg, lambda: pg.locator(".cal-gantry").count() == 10)
    # 1.127: the bed the monitor watches (no mesh in this fake Klipper: the travel, which may go beyond the plate)
    ok("1.127: «Bed area»: where it comes from and its four edges", wait(pg, lambda: pg.locator('[data-bed-source="travel"]').count() == 1 and pg.locator("[data-bed-value]").count() == 4)
       and "AREA DEL PIATTO" in body(pg).upper(), body(pg)[-900:])
    x1 = b.camera_cal.bed_area()[0][1][0]
    pg.click('[data-bed="x1.minus"]')
    ok("... − on the right edge: 5 mm less, set by the person, the dashed outline follows", wait(pg, lambda: b.camera_cal.bed_area() == (b.camera_cal.bed_area()[0], "person")
       and abs(b.camera_cal.bed_area()[0][1][0] - (x1 - 5)) < 0.01 and pg.locator('[data-bed-source="person"]').count() == 1), b.camera_cal.bed_area())
    pg.click("[data-bed-auto]")
    ok("... «Work it out again by itself»: back to the travel", wait(pg, lambda: b.camera_cal.bed_area()[1] == "travel" and pg.locator('[data-bed-source="travel"]').count() == 1), b.camera_cal.bed_area())
    pg.click('[data-size="toolhead.below.minus"]')
    ok("'below the nozzle tip' goes down to 0 (not refused) and stops there", wait(pg, lambda: pg.locator('[data-value="toolhead.below"]').inner_text().startswith("0")
       and b.camera_cal.get_shape()["toolhead"]["below"] == 0.0) and pg.locator('[data-size="toolhead.below.minus"]').is_disabled(), b.camera_cal.get_shape()["toolhead"])
    b.detector.zone = {"file": "two.gcode", "source": "exclude_object", "objects": [{"name": "A", "polygon": [[100, 100], [140, 100], [140, 140], [100, 140]]}, {"name": "B", "polygon": [[200, 200], [240, 200], [240, 240], [200, 240]]}]}
    ok("during a print: the expected zone of the parts drawn in green, with where it comes from", wait(pg, lambda: pg.locator(".cal-zone").count() == 2 and "exclude_object di Klipper" in body(pg)), body(pg)[-600:])
    pg.locator(".cal-frame").first.screenshot(path=os.path.join(out, "06_zone.png"))
    b.detector.zone = {}
    pg.locator(".cal-shape").scroll_into_view_if_needed()
    pg.wait_for_timeout(500)
    pg.locator(".drawer").screenshot(path=os.path.join(out, "05_shape.png"))
    fake.state["cam_shift"] = (25, 12)
    pg.click('[data-check="1"]')
    # 1.127: a small move is looked at again, then corrected by itself from what stays still in the picture
    ok("1.127: camera moved a little: the page says it checks again before correcting (1 of 3)", wait(pg, lambda: '[data-watch="waiting"]' and pg.locator('[data-watch="waiting"]').count() == 1
       and "1 di 3" in body(pg), 10), body(pg)[:400])
    for _ in range(2):
        pg.click('[data-check="1"]')
        pg.wait_for_timeout(1500)
    ok("... three looks agree: corrected by itself, the monitor uses the calibration again", wait(pg, lambda: pg.locator('[data-watch="corrected"]').count() == 1, 10)
       and b.camera_cal.usable() and "corretta da sola" in body(pg), body(pg)[:500])
    pg.locator(".cal-frame").first.screenshot(path=os.path.join(out, "07_corrected.png"))
    pg.click("[data-undo-correction]")
    ok("... «Do not trust it»: the page says to calibrate again", wait(pg, lambda: "La telecamera si è spostata dalla calibrazione" in body(pg), 10) and not b.camera_cal.usable(), body(pg)[:400])
    pg.click('button[aria-label="Indietro"]')
    pg.wait_for_timeout(1500)
    ok("... and the menu line says it too", wait(pg, lambda: "Telecamera spostata" in pg.locator('.set-entry[data-page="camcal"]').inner_text(), 20), pg.locator('.set-entry[data-page="camcal"]').inner_text())
    overflow = pg.evaluate("() => { const d = document.querySelector('.drawer__body'); return d.scrollWidth - d.clientWidth; }")
    ok("no horizontal scrolling", overflow <= 0, overflow)
    ok("no JavaScript error", errors == [], errors)
    browser.close()

server.shutdown()
fake.close()
print("FAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
