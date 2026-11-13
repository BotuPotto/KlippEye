"""A look at every page of the settings, in every language, look and mode, for what a person would see as wrong:
the page scrolling sideways, a text cut off or running out of its box, two things on top of each other, a text too
pale on its background, a button too small to tap. It does not check what the pages do (settings_test.py does).
Usage: settings_audit.py <html> <outdir> <port> [--shots] [--langs it,de] [--looks oneui,glass] [--modes dark,light] [--width 390]
--shots also saves a picture of each page (in <outdir>/<lang>-<look>-<mode>/<page>.png)."""
import sys, os, json, argparse
from playwright.sync_api import sync_playwright
from lib import Mock, Page

ap = argparse.ArgumentParser()
ap.add_argument("html"); ap.add_argument("out"); ap.add_argument("port", type=int)
ap.add_argument("--shots", action="store_true")
ap.add_argument("--langs", default="en,it,de,es,fr,pl,pt,ru,uk,zh")
ap.add_argument("--looks", default="oneui")
ap.add_argument("--modes", default="dark")
ap.add_argument("--width", type=int, default=390)
args = ap.parse_args()
os.makedirs(args.out, exist_ok=True)
mock = Mock(args.html, args.port)
import atexit; atexit.register(mock.stop)

# the pages of the menu, and those inside another page (opened by their row)
PAGES = ["printers", "functions", "macros", "motion", "materials", "camera", "ai", "camcal", "detector", "recordings",
         "notifications", "appearance", "language", "network", "access", "homeauto", "software"]
INSIDE_AI = ("camcal", "detector", "recordings")

# runs in the page: every problem found in the open settings panel, as {kind, text, detail}
AUDIT_JS = r"""
() => {
  const root = document.querySelector('.drawer') || document.body;
  const out = [];
  const label = (el) => (el.innerText || el.getAttribute('aria-label') || el.className || el.tagName).toString().trim().replace(/\s+/g, ' ').slice(0, 90);
  const visible = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && Number(s.opacity) > 0.05; };
  // 1. the page scrolls sideways
  if (document.documentElement.scrollWidth > window.innerWidth + 1) out.push({ kind: 'page-scrolls-sideways', text: '', detail: document.documentElement.scrollWidth + ' > ' + window.innerWidth });
  const vw = window.innerWidth;
  const all = [...root.querySelectorAll('*')].filter(visible);
  for (const el of all) {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    const ownText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    // 2. out of the screen on the right or left (not inside something that scrolls on purpose)
    let scroller = el.parentElement, scrolls = false;
    while (scroller && scroller !== root) { const ss = getComputedStyle(scroller); if (/(auto|scroll)/.test(ss.overflowX) && scroller.scrollWidth > scroller.clientWidth) { scrolls = true; break; } scroller = scroller.parentElement; }
    if (!scrolls && (r.right > vw + 1 || r.left < -1) && r.width < vw * 2 && el.closest('.drawer') && !el.closest('[aria-hidden="true"]'))
      out.push({ kind: 'off-screen', text: label(el), detail: Math.round(r.left) + '..' + Math.round(r.right) });
    // 3. text cut off: its box hides part of it
    if (ownText && (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.textOverflow === 'ellipsis') && el.scrollWidth > el.clientWidth + 1)
      out.push({ kind: 'text-cut', text: label(el), detail: el.scrollWidth + ' > ' + el.clientWidth });
    if (ownText && s.overflow === 'hidden' && el.scrollHeight > el.clientHeight + 2 && s.webkitLineClamp === 'none')
      out.push({ kind: 'text-cut-height', text: label(el), detail: el.scrollHeight + ' > ' + el.clientHeight });
    // 4. text running out of its parent's box (a long word, a label wider than its button)
    if (ownText && el.parentElement && s.position !== 'absolute' && s.position !== 'fixed') {
      const p = el.parentElement.getBoundingClientRect();
      if (r.right > p.right + 2 && getComputedStyle(el.parentElement).overflow === 'visible' && el.scrollWidth > el.clientWidth + 1)
        out.push({ kind: 'text-overflows', text: label(el), detail: Math.round(r.right - p.right) + 'px' });
    }
    // 5. contrast of a text with the colour actually behind it (only on solid backgrounds that can be read)
    if (ownText) {
      const parse = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(',').map(Number); return { r: v[0], g: v[1], b: v[2], a: v.length > 3 ? v[3] : 1 }; };
      const fg = parse(s.color);
      let bg = null, node = el;
      const layers = [];
      while (node && node.nodeType === 1) { const b = parse(getComputedStyle(node).backgroundColor); const img = getComputedStyle(node).backgroundImage; if (img && img !== 'none') { layers.length = 0; bg = 'image'; break; } if (b && b.a > 0) { layers.push(b); if (b.a >= 0.95) break; } node = node.parentElement; }
      if (fg && bg !== 'image' && layers.length && layers[layers.length - 1].a >= 0.95) {
        let c = layers.pop(); while (layers.length) { const t = layers.pop(); c = { r: t.r * t.a + c.r * (1 - t.a), g: t.g * t.a + c.g * (1 - t.a), b: t.b * t.a + c.b * (1 - t.a), a: 1 }; }
        const f = { r: fg.r * fg.a + c.r * (1 - fg.a), g: fg.g * fg.a + c.g * (1 - fg.a), b: fg.b * fg.a + c.b * (1 - fg.a) };
        const lum = (x) => { const k = [x.r, x.g, x.b].map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * k[0] + 0.7152 * k[1] + 0.0722 * k[2]; };
        const L1 = lum(f), L2 = lum(c), ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
        const big = parseFloat(s.fontSize) >= 18.5 || (parseFloat(s.fontSize) >= 14 && Number(s.fontWeight) >= 700);
        const disabled = el.closest('[disabled], [aria-disabled="true"]');
        if (!disabled && ratio < (big ? 3 : 4.5)) out.push({ kind: 'low-contrast', text: label(el), detail: ratio.toFixed(2) + ' ' + s.color + ' on rgb(' + [c.r, c.g, c.b].map(Math.round) + ')' });
      }
      // 6. text too small to read
      if (parseFloat(s.fontSize) < 11) out.push({ kind: 'tiny-text', text: label(el), detail: s.fontSize });
    }
  }
  // 7. buttons and switches too small to tap, or two of them on top of each other
  const taps = [...root.querySelectorAll('button, a[href], input, select, textarea, [role="switch"]')].filter(visible).filter((el) => !el.closest('[hidden]') && el.type !== 'hidden' && el.type !== 'file');
  for (const el of taps) { const r = el.getBoundingClientRect(); if ((r.width < 24 || r.height < 24) && el.type !== 'range') out.push({ kind: 'small-tap', text: label(el), detail: Math.round(r.width) + 'x' + Math.round(r.height) }); }
  for (let i = 0; i < taps.length; i++) for (let j = i + 1; j < taps.length; j++) {
    const a = taps[i].getBoundingClientRect(), b = taps[j].getBoundingClientRect();
    if (taps[i].contains(taps[j]) || taps[j].contains(taps[i])) continue;
    const w = Math.min(a.right, b.right) - Math.max(a.left, b.left), hgt = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    if (w > 4 && hgt > 4) out.push({ kind: 'overlap', text: label(taps[i]) + '  ×  ' + label(taps[j]), detail: Math.round(w) + 'x' + Math.round(hgt) });
  }
  return out;
}
"""


def main():
    report = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for lang in args.langs.split(","):
            for look in args.looks.split(","):
                for mode in args.modes.split(","):
                    combo = "%s-%s-%s" % (lang, look, mode)
                    mock.reset()
                    P = Page(browser, mock, args.width, 844, locale={"en": "en-US", "zh": "zh-CN"}.get(lang, lang + "-" + lang.upper()))
                    P.ctx.add_init_script("try { localStorage.setItem('ke_lang', %s); localStorage.setItem('ke_layout', %s); } catch (e) {}"
                                          % (json.dumps(lang), json.dumps(json.dumps({"look": look, "mode": mode, "collapsed": {}, "devices": {}}))))
                    P.goto("home", 1500)
                    P.pg.evaluate("() => { const b = [...document.querySelectorAll('button[aria-label]')].find((x) => /settings|impostazioni|einstellungen|ajustes|réglages|ustawienia|configura|настрой|налашт|设置/i.test(x.getAttribute('aria-label'))); b && b.click(); }")
                    P.pg.wait_for_selector(".drawer", timeout=5000); P.settle(500)
                    for page in PAGES:
                        try:
                            goto_page(P, page)
                        except Exception as error:
                            report.setdefault(combo, {})[page] = [{"kind": "not-opened", "text": str(error)[:200], "detail": ""}]
                            continue
                        problems = P.pg.evaluate(AUDIT_JS)
                        english = []
                        if lang not in ("en",):
                            english = P.pg.evaluate("""(lang) => [...document.querySelectorAll('.drawer *')].filter((e) => [...e.childNodes].some((n) => n.nodeType === 3 && /\\b(the|and|with|when|this|your|not|of|is|are)\\b/.test(n.textContent)) && !e.closest('code, pre, .cm-editor, input, textarea')).map((e) => e.innerText.trim().slice(0, 100)).slice(0, 10)""", lang)
                        problems += [{"kind": "english-text", "text": t, "detail": ""} for t in english]
                        if problems:
                            report.setdefault(combo, {})[page] = problems
                        if args.shots:
                            folder = os.path.join(args.out, combo); os.makedirs(folder, exist_ok=True)
                            P.pg.locator(".drawer").screenshot(path=os.path.join(folder, page + ".png"))
                    if P.errors:
                        report.setdefault(combo, {})["_errors"] = [{"kind": "console", "text": e, "detail": ""} for e in P.errors[:10]]
                    P.close()
        browser.close()
    with open(os.path.join(args.out, "report.json"), "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    kinds = {}
    for combo, pages in report.items():
        for page, problems in pages.items():
            for p in problems:
                kinds.setdefault(p["kind"], []).append((combo, page, p["text"], p["detail"]))
    for kind, items in sorted(kinds.items()):
        print("== %s: %d" % (kind, len(items)))
        seen = set()
        for combo, page, text, detail in items:
            key = (page, text)
            if key in seen:
                continue
            seen.add(key)
            print("   %-22s %-13s %s  [%s]" % (combo, page, text, detail))


def goto_page(P, page):
    target = "ai" if page in INSIDE_AI else page
    for _ in range(4):
        if P.pg.locator('.drawer .set-entry[data-page="%s"]' % target).count():
            break
        back = P.pg.locator('.drawer .drawer__head button.drawer__btn')  # the arrow back to the list (a page inside one)
        if not back.count():
            break
        back.first.click(); P.settle(350)
    P.pg.locator('.drawer .set-entry[data-page="%s"]' % target).first.click(); P.settle(800)
    if page in INSIDE_AI:
        P.pg.locator('.drawer .set-entry[data-page="%s"]' % page).first.click(); P.settle(800)
    P.pg.evaluate("() => { const b = document.querySelector('.drawer__body'); if (b) b.scrollTop = 0; }")


main()
