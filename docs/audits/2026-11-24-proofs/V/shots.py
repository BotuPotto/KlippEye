import os as _os; ROOT = _os.environ.get("KE_ROOT") or _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../.."))
"""Scratch: pictures of every page for the visual audit. Run: PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 shots.py [group...]
Groups: pages states widths langs. Writes shots/<name>.png and shots/measure.jsonl."""
import base64, json, os, sys, time
sys.path.insert(0, ROOT + "/tests/ui")
from playwright.sync_api import sync_playwright
from lib import Mock, Page

ROOT = ROOT + ""
OUT = os.path.join(ROOT, ".superpowers/audit/shots")
HTML = os.path.join(ROOT, "frontend/klippeye_frontend.html")
with open(os.path.join(ROOT, "tests/ui/docs_camera.jpg"), "rb") as f:
    CAM = ("<html><body style='margin:0;background:#000'><img style='width:100vw;height:100vh;object-fit:cover' src='data:image/jpeg;base64,"
           + base64.b64encode(f.read()).decode() + "'></body></html>")
LOC = {"en": "en-US", "it": "it-IT", "de": "de-DE", "fr": "fr-FR", "es": "es-ES", "pt": "pt-PT", "pl": "pl-PL", "ru": "ru-RU", "uk": "uk-UA", "zh": "zh-CN"}
TABS = ["home", "controllo", "files", "config", "sistema"]
mock = Mock(HTML, 9931)
MEAS = open(os.path.join(OUT, "measure.jsonl"), "a")
COUNT = [0]

MEASURE_JS = r"""() => {
  const vw = document.documentElement.clientWidth, out = {vw, docScroll: document.documentElement.scrollWidth, bodyScroll: document.body.scrollWidth, over: [], small: [], tiny: [], clipped: []};
  const desc = (e) => (e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\s+/).slice(0, 3).join('.') : '') + ' "' + (e.innerText || e.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 30) + '"');
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none'; };
  for (const e of document.body.querySelectorAll('*')) {
    if (e.closest('svg') && e.tagName.toLowerCase() !== 'svg') continue;
    if (!vis(e)) continue;
    const r = e.getBoundingClientRect();
    if (r.right > vw + 1 && !e.closest('[data-presence="leaving"]')) { let p = e.parentElement, sc = false; while (p) { const o = getComputedStyle(p).overflowX; if ((o === 'auto' || o === 'scroll' || o === 'hidden') && p.getBoundingClientRect().right <= vw + 1) { sc = true; break; } p = p.parentElement; } if (!sc && out.over.length < 8) out.over.push(desc(e) + ' right=' + Math.round(r.right)); }
    const own = [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    const cs = getComputedStyle(e);
    if (own) { const fs = parseFloat(cs.fontSize); if (fs < 12 && out.tiny.length < 8) out.tiny.push(desc(e) + ' ' + fs + 'px');
      if (e.scrollWidth > e.clientWidth + 1 && (cs.overflowX === 'hidden' || cs.textOverflow === 'ellipsis') && out.clipped.length < 8) out.clipped.push(desc(e) + ' ' + cs.textOverflow + ' sw=' + e.scrollWidth + ' cw=' + e.clientWidth); }
    const clk = e.matches('button, a[href], [role=button], [role=switch], [role=tab], input:not([type=hidden]), select, summary') && !e.closest('svg');
    if (clk && (r.height < 44 || r.width < 44) && r.bottom > 0 && out.small.length < 40) out.small.push(desc(e) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
  }
  return out;
}"""
WAIT_JS = "() => document.getAnimations().filter(a => { try { return a.effect.getComputedTiming().iterations !== Infinity && a.playState === 'running'; } catch (e) { return false; } }).length"


def settle(P, extra=300):
    for _ in range(25):
        try:
            if P.pg.evaluate(WAIT_JS) == 0: break
        except Exception: break
        P.pg.wait_for_timeout(100)
    P.pg.wait_for_timeout(extra)


def snap(P, name, desktop):
    path = os.path.join(OUT, name + ".png")
    settle(P)
    try:
        m = P.pg.evaluate(MEASURE_JS)
    except Exception as e:
        m = {"error": str(e)[:100]}
    m["file"] = name + ".png"
    MEAS.write(json.dumps(m) + "\n"); MEAS.flush()
    P.pg.screenshot(path=path, full_page=not desktop, animations="allow")
    COUNT[0] += 1


def make(b, w, h, theme, lang, **state):
    mock.reset()
    if state: mock.set(**state)
    P = Page(b, mock, w, h, locale=LOC[lang])
    P.ctx.add_init_script("try { localStorage.setItem('ke_lang', %s); %s } catch (e) {}" % (
        json.dumps(lang), "localStorage.setItem('ke_layout', JSON.stringify({collapsed:{},devices:{},mode:'light'}));" if theme == "light" else ""))
    P.pg.route("**/webcam/webrtc*", lambda route: route.fulfill(content_type="text/html", body=CAM))
    return P


def open_menu(P):
    P.pg.locator(".header-btn--menu").click()
    P.pg.wait_for_selector(".drawer", timeout=5000)
    settle(P, 500)


def entries(P):
    return [e.get_attribute("data-page") for e in P.pg.locator(".drawer .set-entry[data-page]").all()]


def settings_pages(b):
    """first level and second level names"""
    P = make(b, 390, 844, "dark", "en"); P.goto("home", 1800); open_menu(P)
    first = entries(P); tree = {}
    for n in first:
        P.goto("home", 1000); open_menu(P)
        P.pg.click('.drawer .set-entry[data-page="%s"]' % n); settle(P, 500)
        tree[n] = [s for s in entries(P) if s not in first and s != n]
    P.close()
    return first, tree


def shoot_settings(b, w, h, theme, lang, names, desktop, tag):
    """names: list of (page, sub|None)"""
    P = make(b, w, h, theme, lang)
    P.goto("home", 1800)
    for page, sub in names:
        name = "%s-set-%s%s" % (tag, page, "-" + sub if sub else "")
        if os.path.exists(os.path.join(OUT, name + ".png")): continue
        try:
            P.goto("home", 900); open_menu(P)
            if page != "menu":
                P.pg.click('.drawer .set-entry[data-page="%s"]' % page); settle(P, 500)
                if sub:
                    P.pg.click('.drawer .set-entry[data-page="%s"]' % sub); settle(P, 500)
            snap(P, name, True)   # the drawer is a fixed layer: viewport picture
        except Exception as e:
            print("FAIL", name, str(e)[:100], flush=True)
    P.close()


def shoot_tabs(b, w, h, theme, lang, tabs, desktop, tag, **state):
    P = make(b, w, h, theme, lang, **state)
    for t in tabs:
        name = "%s-%s" % (tag, t)
        if os.path.exists(os.path.join(OUT, name + ".png")): continue
        try:
            P.goto(t, 2200); snap(P, name, desktop)
        except Exception as e:
            print("FAIL", name, str(e)[:100], flush=True)
    P.close()


STATES = {
    "idle": {},
    "heating": dict(ext_t=120.0, ext_target=220, bed_t=40.0, bed_target=60),
    "printing": dict(printing=True),
    "paused": dict(printing=True, paused=True),
    "alarm": dict(printing=True, detector_status="scanning", has_analysis=True, analysis_action="PAUSA"),
    "finished": dict(print_state="complete"),
    "piDown": None,   # Moonraker / Pi not answering: set after the page loaded
    "nocamera": dict(webcams=[]),
}


def main(groups):
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        first, tree = settings_pages(b)
        allset = [("menu", None)] + [(p, None) for p in first] + [(p, s) for p in first for s in tree[p]]
        print("settings pages", len(first), "subpages", sum(len(v) for v in tree.values()), flush=True)
        phone = {"w": 360, "h": 780}; desk = {"w": 1280, "h": 800}
        if "pages" in groups:   # every page, 360 and 1280, dark, English
            for (w, h, d) in ((360, 780, False), (1280, 800, True)):
                shoot_tabs(b, w, h, "dark", "en", TABS, d, "%d-dark-en" % w)
                shoot_settings(b, w, h, "dark", "en", allset, d, "%d-dark-en" % w)
        if "widths" in groups:  # other widths and light, on the four main pages
            main4 = ["home", "controllo", "files", "sistema"]
            for (w, h, d, th) in ((320, 700, False, "dark"), (412, 860, False, "dark"), (1600, 900, True, "dark"),
                                  (320, 700, False, "light"), (360, 780, False, "light"), (412, 860, False, "light"), (1280, 800, True, "light"), (1600, 900, True, "light")):
                tag = "%d-%s-en" % (w, th)
                shoot_tabs(b, w, h, th, "en", main4 + ["config"] if th == "light" and w in (360, 1280) else main4, d, tag)
                shoot_settings(b, w, h, th, "en", [("menu", None), ("appearance", None), ("camera", None), ("ai", None)], d, tag)
        if "states" in groups:
            for sname, st in STATES.items():
                for (w, h, d) in ((360, 780, False), (1280, 800, True)):
                    name = "%d-state-%s" % (w, sname)
                    if os.path.exists(os.path.join(OUT, name + ".png")): continue
                    try:
                        P = make(b, w, h, "dark", "en", **(st or {}))
                        P.goto("home", 2400)
                        if st is None:
                            mock.set(moonraker_down=True); P.pg.wait_for_timeout(6000)
                        snap(P, name, d); P.close()
                    except Exception as e:
                        print("FAIL", name, str(e)[:100], flush=True)
            # light-theme alarm and a print too
            for sname in ("printing", "alarm"):
                shoot_tabs(b, 360, 780, "light", "en", ["home"], False, "360-light-state-" + sname, **STATES[sname])
        if "langs" in groups:
            for lang in ("de", "pl", "ru"):
                shoot_tabs(b, 360, 780, "dark", lang, TABS, False, "360-dark-" + lang)
                shoot_settings(b, 360, 780, "dark", lang, allset, False, "360-dark-" + lang)
                shoot_tabs(b, 1280, 800, "dark", lang, ["home", "files"], True, "1280-dark-" + lang)
            for lang in ("it", "fr", "es", "pt", "uk", "zh"):
                shoot_tabs(b, 360, 780, "dark", lang, ["home"], False, "360-dark-" + lang)
                shoot_settings(b, 360, 780, "dark", lang, [("menu", None)], False, "360-dark-" + lang)
        b.close()
    mock.stop()
    print("pictures this run:", COUNT[0])


main(sys.argv[1:] or ["pages", "widths", "states", "langs"])
