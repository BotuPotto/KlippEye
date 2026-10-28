"""Release 1.13.0: "Calibra la camera" (roadmap phase 4a) with the REAL backend, a fake Klipper that moves when told and a
fake camera that draws the printer as a fisheye camera in front of it would see it (bed, blobs, toolhead, nozzle tip).
The test taps where the nozzle tip and the blobs really are, as a person would, and checks the whole path: kind of printer,
homing, blobs, twelve points with the magnified view, calculation, saving, the live drawing, the camera moved.
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
MARKS = [(52.5, 70.0), (175.0, 70.0), (297.5, 70.0), (297.5, 280.0), (175.0, 280.0), (52.5, 280.0)]


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
    if any("M109" in sc for sc in fake.scripts):   # the blobs, once made
        for mx, my in MARKS:
            p, f = px([[mx, my, bed_z + 0.6]])
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
open(os.path.join(repo, "VERSION"), "w").write("1.13.0\n")
os.environ["KLIPPEYE_DATA"] = data
fake = fakes.Fake()
fake.state.update({"render": render, "print_state": "standby", "homed": "", "position": [175.0, 175.0, 20.0]})
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
    entry = pg.locator('.set-entry[data-page="camcal"]')
    ok("the menu has 'Calibra camera', 'Non calibrata'", entry.count() == 1 and wait(pg, lambda: "Non calibrata" in entry.inner_text()), entry.inner_text() if entry.count() else "")
    entry.click()
    pg.wait_for_timeout(1200)
    ok("not calibrated: the page says so and offers to calibrate", wait(pg, lambda: "La camera non è calibrata" in body(pg)) and pg.locator('[data-start="1"]').count() == 1, body(pg)[:300])
    pg.click('[data-start="1"]')
    pg.wait_for_timeout(800)
    ok("step 1: how Z moves, guessed from Klipper (Z moves the bed)", "come si muove l'asse z?" in body(pg).lower() and "Dalla configurazione di Klipper sembra: Z muove il piatto." in body(pg), body(pg)[:600])
    pg.screenshot(path=os.path.join(out, "01_kind.png"))
    pg.locator("button", has_text="Avanti").click()
    ok("... 'Avanti' keeps it: the points appear (12) and the blobs step", wait(pg, lambda: pg.locator(".cal-target").count() == 12 and "Fai i 6 segni" in body(pg)), body(pg)[-600:])
    pg.locator("button", has_text="Fai l'homing").click()
    ok("home: G28 sent and 'Homing fatto.'", wait(pg, lambda: "Homing fatto." in body(pg)) and "G28" in fake.scripts, fake.scripts)
    pg.click('[data-marks="start"]')
    ok("the 6 blobs: heated, made, cooled; the page says so", wait(pg, lambda: "Segni fatti" in body(pg), 12) and any("M109" in sc and sc.count("G1 E4.00") == 6 for sc in fake.scripts), body(pg)[-500:])
    targets = b.camera_cal.target_list()
    for n, t in enumerate(targets):
        pg.locator('.cal-target[data-target="%s"]' % t["id"]).click()
        pg.click('[data-go="%s"]' % t["id"])
        wait(pg, lambda: pg.locator(".cal-pick .cal-frame__img").count() == 1)
        pg.wait_for_timeout(500)
        x, y, z = fake.state["position"]
        frame = [x, y, 0.0] if t["kind"] == "nozzle" else [t["x"], t["y"], 0.6 - z]
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
    ok("12 points taken through the page", len(pts) == 12, list(pts))
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
    ok("... and the camera is said to be in place", wait(pg, lambda: "ancora al suo posto" in body(pg)), body(pg)[:400])
    pg.locator("button", has_text="X +20").click()
    pg.wait_for_timeout(2200)
    ov = b.camera_cal.overlay()
    tx_, ty_ = truth([fake.state["position"][0], fake.state["position"][1], 0.0])
    ok("live check: after a jog the nozzle is drawn where it really is (within 1%)", abs(ov["nozzle"][0] - tx_) < 0.01 and abs(ov["nozzle"][1] - ty_) < 0.01, (ov["nozzle"], tx_, ty_))
    pg.locator(".drawer").screenshot(path=os.path.join(out, "04_saved.png"))
    fake.state["cam_shift"] = (25, 12)
    pg.click('[data-check="1"]')
    ok("camera moved: the page says to calibrate again", wait(pg, lambda: "La camera si è spostata dalla calibrazione" in body(pg), 10), body(pg)[:400])
    pg.click('button[aria-label="Indietro"]')
    pg.wait_for_timeout(1500)
    ok("... and the menu line says it too", wait(pg, lambda: "Camera spostata" in pg.locator('.set-entry[data-page="camcal"]').inner_text(), 20), pg.locator('.set-entry[data-page="camcal"]').inner_text())
    overflow = pg.evaluate("() => { const d = document.querySelector('.drawer__body'); return d.scrollWidth - d.clientWidth; }")
    ok("no horizontal scrolling", overflow <= 0, overflow)
    ok("no JavaScript error", errors == [], errors)
    browser.close()

server.shutdown()
fake.close()
print("FAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
