import json, os, re, subprocess, sys, time, hashlib, urllib.request
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
POLL_PATHS = ("/printer/objects/query", "/api/printer", "/server/gcode_store", "/server/files/metadata",
              "/printer/objects/list", "/api/calibration/selected", "/api/macros/list",
              "/api/print/detector/status", "/api/print/last_analysis", "/server/files/list",
              "/machine/proc_stats", "/machine/system_info", "/machine/update/status", "/printer/info",
              "/api/logs/list", "/server/files/gcodes/", "/api/status", "/server/files/directory",
              "/api/version", "/api/backend/config", "/api/print/snapshot", "/api/app/version", "/api/logos", "/logos/", "/api/auth/status", "/api/recordings", "/api/print/alerts/history", "/api/camera/calibration")

class Mock:
    def __init__(self, html, port):
        self.port = port
        self.proc = subprocess.Popen([sys.executable, os.path.join(HERE, "mock_server.py"), html, str(port)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.base = f"http://127.0.0.1:{port}"
        for _ in range(50):
            try:
                urllib.request.urlopen(self.base + "/__mock/gcode", timeout=0.5); break
            except Exception:
                time.sleep(0.2)
    def set(self, **kw):
        req = urllib.request.Request(self.base + "/__mock/set", data=json.dumps(kw).encode(), headers={"content-type": "application/json"}, method="POST")
        urllib.request.urlopen(req).read()
    def reset(self):
        urllib.request.urlopen(urllib.request.Request(self.base + "/__mock/reset", data=b"{}", method="POST")).read()
    def gcode(self):
        return json.loads(urllib.request.urlopen(self.base + "/__mock/gcode").read())
    def stop(self):
        self.proc.terminate()

SIG_JS = r"""
() => {
  const out = [];
  const rd = (n) => Math.round(n * 10) / 10;
  const hash = (s) => { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return h; };
  const P = ['color','backgroundColor','backgroundImage','backgroundSize','backgroundPosition','borderTopWidth','borderRightWidth','borderBottomWidth','borderLeftWidth',
    'borderTopColor','borderRightColor','borderBottomColor','borderLeftColor','borderTopStyle','borderRightStyle','borderBottomStyle','borderLeftStyle',
    'borderTopLeftRadius','borderTopRightRadius','borderBottomRightRadius','borderBottomLeftRadius','boxShadow','fontFamily','fontSize','fontWeight','fontStyle',
    'letterSpacing','lineHeight','textTransform','textAlign','textDecorationLine','opacity','filter','backdropFilter','transform','zIndex','position','overflow',
    'cursor','mixBlendMode','textShadow','whiteSpace','outlineStyle','outlineWidth','outlineColor','paddingTop','paddingRight','paddingBottom','paddingLeft','objectFit','pointerEvents','visibility'];
  const all = document.body.querySelectorAll('*');
  for (const el of all) {
    const tag = el.tagName.toLowerCase();
    if (['script','style','link','meta','head','title','noscript','path','circle','rect','line','polyline','polygon','g','defs','ellipse','use','text','tspan','clippath','mask','lineargradient','radialgradient','stop','pattern','filter','fedropshadow','feflood','fecomposite','feblend','fegaussianblur','feoffset','fecolormatrix','femerge','femergenode'].includes(tag)) continue;
    if (el.closest('svg') && tag !== 'svg') continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none') continue;
    const r = el.getBoundingClientRect();
    let own = '';
    for (const n of el.childNodes) if (n.nodeType === 3) own += n.textContent;
    own = own.replace(/\s+/g, ' ').trim();
    const bw = ['Top','Right','Bottom','Left'].some(s => parseFloat(cs['border'+s+'Width']) > 0 && cs['border'+s+'Style'] !== 'none');
    const bgc = cs.backgroundColor;
    const hasBg = bgc && !/rgba\(0, 0, 0, 0\)|transparent/.test(bgc);
    const isTx = ['img','svg','canvas','input','select','textarea','video','iframe','button'].includes(tag);
    if (!(own || bw || hasBg || cs.backgroundImage !== 'none' || cs.boxShadow !== 'none' || isTx || cs.outlineStyle !== 'none')) continue;
    if (r.width === 0 && r.height === 0) continue;
    const rec = { tag, x: rd(r.x), y: rd(r.y + 0), w: rd(r.width), h: rd(r.height) };
    rec._c = (el.getAttribute('class') || '').slice(0, 220);
    if (own) rec.text = own.replace(/\d\d:\d\d:\d\d/g, 'HH:MM:SS');
    if (tag === 'input' || tag === 'textarea' || tag === 'select') { rec.value = el.value; rec.ph = el.placeholder || ''; rec.itype = el.type; rec.dis = el.disabled; rec.chk = el.checked; }
    if (tag === 'img') rec.src = (el.getAttribute('src') || '').length + ':' + hash(el.getAttribute('src') || '');
    if (tag === 'svg') rec.svg = hash(el.innerHTML);
    if (tag === 'iframe') rec.src = el.getAttribute('src');
    if (tag === 'button') rec.dis = el.disabled;
    const st = {};
    for (const p of P) {
      let v = cs[p];
      if (p === 'backgroundImage' && v.length > 120) v = v.slice(0, 40) + '#' + hash(v);
      st[p] = v;
    }
    rec.st = st;
    out.push(rec);
  }
  return out;
}
"""

GHOST_JS = r"""
() => {
  // every class token present in the DOM, and the ones no style rule of any sheet mentions
  const known = new Set();
  const add = (sel) => { for (const m of sel.matchAll(/\.((?:\\.|[A-Za-z0-9_-])+)/g)) known.add(m[1].replace(/\\(.)/g, '$1')); };
  const walk = (rules) => { for (const r of rules) { if (r.selectorText) add(r.selectorText); if (r.cssRules) walk(r.cssRules); } };
  for (const sh of document.styleSheets) { try { walk(sh.cssRules); } catch (e) {} }
  const used = new Set();
  for (const el of document.querySelectorAll('*')) { if (el.closest('svg') && el.tagName.toLowerCase() !== 'svg') continue; for (const c of el.classList) used.add(c); }
  return { used: [...used], unknown: [...used].filter(c => !known.has(c)) };
}
"""

KILL_ANIM_JS = """() => { for (const a of document.getAnimations()) { try { const t = a.effect && a.effect.getComputedTiming(); if (t && t.iterations === Infinity) a.cancel(); else a.finish(); } catch (e) { try { a.cancel(); } catch (_) {} } } }"""

CLICKABLES_JS = r"""
() => {
  const sels = 'button, a[href], [role=button], input, select, textarea, summary, label, [onclick]';
  const cand = new Set(document.body.querySelectorAll(sels));
  for (const el of document.body.querySelectorAll('*')) {
    if (el.closest('svg') && el.tagName.toLowerCase() !== 'svg') continue;
    if (getComputedStyle(el).cursor === 'pointer') cand.add(el);
  }
  const res = [];
  for (const el of cand) {
    if (el.closest('#vz-custom-bottom-nav, .bottom-nav')) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.pointerEvents === 'none') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    // topmost pointer ancestor only (avoid duplicates of the same click target)
    let anc = el.parentElement, dup = false;
    while (anc) { if (cand.has(anc) && !['LABEL'].includes(anc.tagName) && !['INPUT','SELECT','TEXTAREA'].includes(el.tagName)) { dup = true; break; } anc = anc.parentElement; }
    if (dup) continue;
    // must be hit-testable at its center
    const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
    if (cx < 0 || cy < 0 || cx > innerWidth || cy > innerHeight + 5000) continue;
    const label = (el.innerText || el.value || el.getAttribute('aria-label') || el.title || el.placeholder || el.id || '').replace(/\s+/g, ' ').trim().slice(0, 40);
    res.push({ tag: el.tagName.toLowerCase(), type: el.type || '', label, x: Math.round(cx), y: Math.round(cy), w: Math.round(r.width), h: Math.round(r.height) });
  }
  res.sort((a, b) => a.y - b.y || a.x - b.x);
  return res;
}
"""

def norm_req(method, url, body, base):
    path = url.replace(base, "")
    return {"m": method, "u": path, "b": body}

class Page:
    def __init__(self, browser, mock, vw=390, vh=844, tall=2600, locale="it-IT"):
        self.mock = mock; self.vw = vw; self.vh = vh; self.tall = tall
        self.ctx = browser.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=1, timezone_id="Europe/Rome", locale=locale,
                                       permissions=[], accept_downloads=True)
        self.pg = self.ctx.new_page()
        self.errors = []; self.reqs = []; self.dialogs = []
        pg = self.pg
        pg.on("pageerror", lambda e: self.errors.append("pageerror: " + str(e)[:300]))
        # the answer "nothing stored yet" of Moonraker's database is a 404 the browser logs by itself: an expected answer, not an error
        expected = lambda m: "/server/database/item" in (m.location or {}).get("url", "") and "404" in m.text
        pg.on("console", lambda m: self.errors.append("console." + m.type + ": " + m.text[:200]) if m.type in ("error", "warning") and not expected(m) else None)
        pg.on("dialog", lambda d: (self.dialogs.append((d.type, d.message)), d.accept("test") if d.type == "prompt" else d.accept()))
        pg.on("request", self._on_req)
        pg.route_web_socket("**/websocket", lambda ws: None)
        pg.route("**/*", self._route)
    def _route(self, route):
        u = route.request.url
        if u.startswith(self.mock.base):
            route.continue_()
        else:
            route.fulfill(status=200, body="<html><body style='background:#111;color:#999'>ext</body></html>" if route.request.resource_type == "document" else "", content_type="text/html" if route.request.resource_type == "document" else "text/plain")
    def _on_req(self, r):
        if not r.url.startswith(self.mock.base):
            self.reqs.append({"m": r.method, "u": "EXT " + r.url.split("?")[0], "b": None}); return
        body = None
        try:
            body = r.post_data
        except Exception:
            pass
        self.reqs.append(norm_req(r.method, r.url, body, self.mock.base))
    def goto(self, tab=None, wait=1800):
        self.pg.goto(self.mock.base + "/")
        if tab and tab != "home":
            self.pg.evaluate("(t) => { try { localStorage.setItem('ke_current_tab', t) } catch(e){} }", tab)
            self.pg.reload()
        self.pg.wait_for_timeout(wait)
    def settle(self, ms=500):
        self.pg.wait_for_timeout(ms)
        try: self.pg.evaluate(KILL_ANIM_JS)
        except Exception: pass
    def sig(self):
        self.settle(100)
        return self.pg.evaluate(SIG_JS)
    def shot(self, path, tall=True):
        self.settle(100)
        if tall:
            self.pg.set_viewport_size({"width": self.vw, "height": self.tall})
            self.pg.wait_for_timeout(250)
            try: self.pg.evaluate(KILL_ANIM_JS)
            except Exception: pass
            self.pg.screenshot(path=path, animations="disabled")
            self.pg.set_viewport_size({"width": self.vw, "height": self.vh})
            self.pg.wait_for_timeout(250)
        else:
            self.pg.screenshot(path=path, animations="disabled")
    def shot_vp(self, path, vh=844):
        self.pg.set_viewport_size({"width": self.vw, "height": vh}); self.pg.wait_for_timeout(300)
        try: self.pg.evaluate(KILL_ANIM_JS)
        except Exception: pass
        self.pg.screenshot(path=path, animations="disabled")
        self.pg.set_viewport_size({"width": self.vw, "height": self.vh}); self.pg.wait_for_timeout(300)
    def clickables(self):
        return self.pg.evaluate(CLICKABLES_JS)
    def take_reqs(self):
        r = self.reqs; self.reqs = []; return r
    def close(self):
        self.ctx.close()

def is_poll(req):
    if req["m"] == "GET" and req["u"].startswith("EXT "): return False
    if req["m"] == "GET":
        p = req["u"].split("?")[0]
        return any(p.startswith(x) for x in POLL_PATHS)
    return False

def is_noise(req):
    return req["u"].endswith(".png") or req["u"] == "/" or "fonts.g" in req["u"]
