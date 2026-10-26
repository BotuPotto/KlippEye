"""The browser tab: the name "KlippEye" and the KlippEye icon (embedded, three sizes), on every tab of the page.
Usage: title_icon_test.py <html> <outdir> <port>"""
import sys, os, re, io, base64
from playwright.sync_api import sync_playwright
from PIL import Image
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
FAILS = []


def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:400]) if (extra != "" and not cond) else ""))


LINKS = """() => Array.from(document.querySelectorAll('head link[rel~="icon"], head link[rel="apple-touch-icon"]')).map(l => ({ rel: l.getAttribute('rel'), sizes: l.getAttribute('sizes'), type: l.getAttribute('type'), href: l.getAttribute('href') }))"""
DECODE = """(href) => new Promise((resolve) => { const im = new Image(); im.onload = () => resolve([im.naturalWidth, im.naturalHeight]); im.onerror = () => resolve(null); im.src = href; })"""

with sync_playwright() as p:
    b = p.chromium.launch()
    for w, h in ((390, 844), (1440, 900)):
        mock.reset()
        P = Page(b, mock, w, h); P.goto("controllo", 1500)
        pg = P.pg
        ok("%d: the tab is called \"KlippEye\"" % w, pg.title() == "KlippEye", pg.title())
        links = pg.evaluate(LINKS)
        ok("%d: three icon links: 32 px, 64 px, and the 180 px one for \"add to home screen\"" % w, [(l["rel"], l["sizes"]) for l in links] == [("icon", "32x32"), ("icon", "64x64"), ("apple-touch-icon", "180x180")], links)
        ok("%d: they are embedded (data URIs): no file is requested from the Raspberry" % w, all(l["href"].startswith("data:image/png;base64,") for l in links))
        for l in links:
            want = int(l["sizes"].split("x")[0])
            raw = base64.b64decode(l["href"].split(",", 1)[1]); im = Image.open(io.BytesIO(raw)).convert("RGBA")
            shown = pg.evaluate(DECODE, l["href"])
            ok("%d: %s %s decodes in the browser at %d x %d" % (w, l["rel"], l["sizes"], want, want), im.size == (want, want) and shown == [want, want], (im.size, shown))
            corner, centre = im.getpixel((0, 0)), im.getpixel((want // 2, want // 2))
            if l["rel"] == "icon":
                ok("%d: %s has rounded transparent corners" % (w, l["sizes"]), corner[3] == 0 and centre[3] == 255, (corner, centre))
            else:
                ok("%d: the home-screen icon is a full opaque square" % w, corner[3] == 255 and centre[3] == 255, (corner, centre))
            violet = sum(1 for px in list(im.getdata()) if px[3] > 200 and px[2] > 170 and 90 < px[0] < 215 and px[1] < px[0] - 20)  # the bars of the logo (#a98cff to #6f4df5), not the white nozzle
            ok("%d: %s shows the violet of the KlippEye logo (%d px)" % (w, l["sizes"], violet), violet >= want * want * 0.03, violet)
        for tab in ("config", "console", "sistema", "controllo"):
            P.goto(tab, 700)
            if pg.title() != "KlippEye":
                ok("%d: the name stays on tab %s" % (w, tab), False, pg.title()); break
        else:
            ok("%d: the name stays the same on every tab" % w, True)
        ok("%d: no request for /favicon.ico (the page says where its icon is)" % w, not any("favicon.ico" in (r.get("u") or "") for r in P.reqs), [r["u"] for r in P.reqs if "favicon" in r["u"]])
        ok("%d: no errors in the page" % w, not P.errors, P.errors[:3])
        P.ctx.close()
    b.close()
print("FAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
