"""The file icons: prints without a preview, the config files and folders, the logs. Usage: icons_test.py <html> <outdir> <port>"""
import sys, os, re, json
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
FAILS = []
OLD_GLYPHS = "◧◫≡◎📁🖼"
NOW = 1760000000


def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra != "" else ""))


# name -> tone the tile must have: every .cfg and .conf wears the blue sliders, every .bkp the grey page (the one
# ".moonraker.conf.bkp" has), every .log telegram.log's terminal, whatever the name
EXPECTED = {
    "macros": "warn", "img": "warn",
    "printer.cfg": "accent", "moonraker.conf": "accent", "crowsnest.conf": "accent", "KlipperScreen.conf": "accent",
    "mainsail.cfg": "accent", "macros.cfg": "accent", "adxl.cfg": "accent", "config.json": "neutral", "backup.sh": "cool",
    "notes.txt": "neutral", "README": "neutral", "old.cfg.bak": "neutral", "bed.png": "ok", "test.gcode": "accent",
    "moonraker.conf.bkp": "neutral", ".moonraker.conf.bkp": "neutral", "printer.cfg.bkp": "neutral", "telegram.log": "neutral", "klippy.log": "neutral", "moonraker.log.1": "neutral",
}
SAME_AS = {"printer.cfg": ["moonraker.conf", "crowsnest.conf", "KlipperScreen.conf", "mainsail.cfg", "macros.cfg", "adxl.cfg"],
           "README": ["moonraker.conf.bkp", ".moonraker.conf.bkp", "printer.cfg.bkp"],
           "telegram.log": ["klippy.log", "moonraker.log.1"]}
FILES = {n: {"size": 100 + 37 * i, "modified": NOW - 5000 * i, "content": None} for i, n in enumerate(n for n in EXPECTED if n not in ("macros", "img"))}
FILES["macros/led.cfg"] = {"size": 800, "modified": NOW - 9000, "content": None}
CFG = {"dirs": {"macros": NOW - 5000, "img": NOW - 7000}, "files": FILES}


def fresh(tab, w=390, h=844, wait=1800, **state):
    mock.reset()
    mock.set(**state)
    P = Page(b, mock, w, h)
    P.goto(tab, wait)
    return P


def errs(P): return [e for e in P.errors if "pageerror" in e or "console.error" in e]
def overflow(P): return P.pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
def body_has_old(P): return [c for c in OLD_GLYPHS if c in P.pg.evaluate("() => document.body.innerText")]


def centred(P, frame_sel, glyph_sel):
    """The glyph sits in the middle of its frame and is neither tiny nor wider than it."""
    r = P.pg.evaluate("""([f, g]) => { const a = document.querySelector(f), b = document.querySelector(g); if (!a || !b) return null;
        const A = a.getBoundingClientRect(), B = b.getBoundingClientRect();
        return { dx: Math.abs((A.left + A.width / 2) - (B.left + B.width / 2)), dy: Math.abs((A.top + A.height / 2) - (B.top + B.height / 2)), ratio: B.width / A.width, w: B.width, square: Math.abs(B.width - B.height) } }""", [frame_sel, glyph_sel])
    return r


def tone_of(P, scope, name_sel, name):
    return P.pg.evaluate("""([scope, nameSel, name]) => { const rows = [...document.querySelectorAll(scope)];
        const row = rows.find((r) => { const n = r.querySelector(nameSel); return n && n.innerText.trim() === name; });
        if (!row) return null; const fi = row.querySelector('.fi'); if (!fi) return 'NOGLYPH';
        const m = [...fi.classList].find((c) => c.startsWith('fi--') && !['fi--lg', 'fi--placeholder'].includes(c)); return m ? m.slice(4) : '' }""", [scope, name_sel, name])


def svg_of(P, scope, name_sel, name):
    return P.pg.evaluate("""([scope, nameSel, name]) => { const row = [...document.querySelectorAll(scope)].find((r) => { const n = r.querySelector(nameSel); return n && n.innerText.trim() === name; });
        const svg = row && row.querySelector('.fi svg'); return svg ? svg.innerHTML : null }""", [scope, name_sel, name])


with sync_playwright() as p:
    b = p.chromium.launch()

    # ------------------------------------------------------------------ prints without a preview: the file tiles
    for label, w, h in (("phone", 390, 844), ("narrow", 360, 740)):
        P = fresh("files", w, h, no_thumbs=["Vase", "Bracket"])
        tiles = P.pg.locator(".file-card")
        names = P.pg.locator(".file-card__name").all_inner_texts()
        ph = [n for n in names if "Vase" in n or "Bracket" in n]
        ok(f"[{label}] files: tiles without preview show the placeholder, the others the picture",
           P.pg.locator(".file-card .fi--placeholder").count() == 2 and P.pg.locator(".file-card img.file-thumb").count() == len(names) - 2, (P.pg.locator(".file-card .fi--placeholder").count(), len(names)))
        ok(f"[{label}] files: no old symbol is left on the page", not body_has_old(P), body_has_old(P))
        c = centred(P, ".file-card:has(.fi--placeholder) .file-card__preview", ".file-card .fi--placeholder")
        ok(f"[{label}] files: placeholder centred, square, sensible size", c and c["dx"] < 1.5 and c["dy"] < 1.5 and c["square"] < 1 and 28 <= c["w"] <= 90 and 0.4 < c["ratio"] < 0.7, c)
        ok(f"[{label}] files: no sideways scrolling", overflow(P) <= 0, overflow(P))
        P.pg.screenshot(path=f"{out}/files_{label}.png", animations="disabled")
        # print confirmation of a file without preview
        P.pg.locator(".file-card", has_text="Vase_mode").first.locator("button", has_text="Stampa").click(); P.pg.wait_for_timeout(500)
        c = centred(P, ".print-preview", ".print-preview .fi--placeholder")
        ok(f"[{label}] confirm dialog: placeholder centred", c and c["dx"] < 1.5 and c["dy"] < 1.5 and 40 <= c["w"] <= 130, c)
        P.pg.screenshot(path=f"{out}/confirm_{label}.png", animations="disabled")
        P.pg.keyboard.press("Escape")
        P.pg.locator(".confirm-card button", has_text=re.compile("Annulla|No", re.I)).first.click() if P.pg.locator(".confirm-card").count() else None
        P.pg.wait_for_timeout(300)
        # the file menu (long press)
        box = P.pg.locator(".file-card", has_text="Vase_mode").first.bounding_box()
        P.pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2); P.pg.mouse.down(); P.pg.wait_for_timeout(900); P.pg.mouse.up(); P.pg.wait_for_timeout(700)
        c = centred(P, ".file-sheet__thumb", ".file-sheet__thumb .fi--placeholder")
        ok(f"[{label}] file menu: placeholder centred in its frame", c and c["dx"] < 1.5 and c["dy"] < 1.5 and 28 <= c["w"] <= 50, c)
        P.pg.screenshot(path=f"{out}/filemenu_{label}.png", animations="disabled")
        ok(f"[{label}] no page errors", not errs(P), errs(P)[:2]); P.close()

    # ------------------------------------------------------------------ Home: the card of the running print
    P = fresh("home", 390, 844, printing=True, no_thumbs=["Benchy", "Calibration", "Vase", "Bracket", "Nested"])
    P.pg.wait_for_timeout(1200)
    c = centred(P, ".print-thumb", ".print-thumb .fi--placeholder")
    ok("[home] running print without preview: placeholder centred in the 72 px frame", c and c["dx"] < 1.5 and c["dy"] < 1.5 and 30 <= c["w"] <= 50, c)
    ok("[home] no old symbol", not body_has_old(P), body_has_old(P))
    P.pg.locator(".print-thumb").first.screenshot(path=f"{out}/home_print_thumb.png", animations="disabled")
    P.pg.screenshot(path=f"{out}/home_printing.png", animations="disabled")
    ok("[home] no page errors", not errs(P), errs(P)[:2]); P.close()

    # ------------------------------------------------------------------ config files + logs on the phone
    for label, w, h in (("phone", 390, 844), ("narrow", 360, 740)):
        P = fresh("config", w, h, cfg=CFG)
        P.pg.wait_for_timeout(600)
        bad = {}
        for name, tone in EXPECTED.items():
            got = tone_of(P, ".cfg-row", ".cfg-row__name", name)
            if got != tone: bad[name] = (got, tone)
        ok(f"[{label}] config: every file and folder has the tile of its kind", not bad, bad)
        wrong = {}
        for ref_name, others in SAME_AS.items():
            ref = svg_of(P, ".cfg-row", ".cfg-row__name", ref_name)
            for other in others:
                if not ref or svg_of(P, ".cfg-row", ".cfg-row__name", other) != ref: wrong[other] = ref_name
        ok(f"[{label}] config: .cfg/.conf share one drawing, .bkp the page, .log telegram.log's", not wrong, wrong)
        ok(f"[{label}] config: the .cfg drawing is the sliders (3 knobs), the .bkp one the page (no knob)", (svg_of(P, ".cfg-row", ".cfg-row__name", "printer.cfg") or "").count("<circle") == 3 and "<circle" not in (svg_of(P, ".cfg-row", ".cfg-row__name", ".moonraker.conf.bkp") or "<circle"))
        glyphs = P.pg.evaluate("() => [...document.querySelectorAll('.cfg-row .fi')].map((e) => e.querySelector('svg').innerHTML)")
        ok(f"[{label}] config: icons differ from kind to kind (>= 8 different drawings)", len(set(glyphs)) >= 8, len(set(glyphs)))
        sizes = P.pg.evaluate("() => [...new Set([...document.querySelectorAll('.cfg-row .fi')].map((e) => { const r = e.getBoundingClientRect(); return Math.round(r.width) + 'x' + Math.round(r.height) }))]")
        ok(f"[{label}] config: all tiles 40x40", sizes == ["40x40"], sizes)
        ok(f"[{label}] config: no old symbol", not body_has_old(P), body_has_old(P))
        ok(f"[{label}] config: no sideways scrolling", overflow(P) <= 0, overflow(P))
        card = P.pg.locator(".oui-card:has(.oui-card-title:text-is('File di configurazione'))").first
        card.screenshot(path=f"{out}/config_{label}.png", animations="disabled")
        # the row menu: a large tile in the thumbnail's place
        P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^printer.cfg$"))).first.locator(".cfg-row__more").click()
        P.pg.wait_for_selector(".sheet-overlay--actions"); P.pg.wait_for_timeout(560)
        c = centred(P, ".file-sheet__thumb", ".file-sheet__thumb .fi--lg")
        ok(f"[{label}] row menu: 64 px tile in the thumbnail's place", c and c["dx"] < 1.5 and c["dy"] < 1.5 and abs(c["w"] - 64) < 1, c)
        P.pg.screenshot(path=f"{out}/cfg_menu_{label}.png", animations="disabled")
        # folder menu -> move chooser shows folder tiles
        P.pg.locator(".sheet-overlay--actions .sheet-footer button").click(); P.pg.wait_for_timeout(400)
        P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^notes.txt$"))).first.locator(".cfg-row__more").click()
        P.pg.wait_for_selector(".sheet-overlay--actions"); P.pg.wait_for_timeout(560)
        P.pg.locator(".sheet-overlay--actions .file-action", has_text="Sposta").click(); P.pg.wait_for_timeout(600)
        tones = P.pg.evaluate("() => [...document.querySelectorAll('.cfg-pick .fi')].map((e) => [...e.classList].join(' '))")
        ok(f"[{label}] move chooser: folders have the amber folder tile", len(tones) == 2 and all("fi--warn" in t for t in tones), tones)
        ok(f"[{label}] move chooser: no tile inside a round disc", P.pg.locator(".cfg-pick .oui-row__icon .fi").count() == 0)
        P.pg.screenshot(path=f"{out}/cfg_move_{label}.png", animations="disabled")
        ok(f"[{label}] no page errors (config)", not errs(P), errs(P)[:2]); P.close()

        P = fresh("config", w, h, cfg=CFG)
        logs = P.pg.locator(".log-row")
        n = logs.count()
        want = {"klippy.log": "neutral", "moonraker.log": "neutral", "crowsnest.log": "neutral"}
        got = {name: tone_of(P, ".log-row", ".log-row__name", name) for name in want}
        ok(f"[{label}] logs: every log has a tile of its kind", n == 3 and got == want, got)
        ref = svg_of(P, ".cfg-row", ".cfg-row__name", "telegram.log")
        ok(f"[{label}] logs: every log wears the drawing of telegram.log", ref and all(svg_of(P, ".log-row", ".log-row__name", n) == ref for n in want), [n for n in want if svg_of(P, ".log-row", ".log-row__name", n) != ref])
        ok(f"[{label}] logs: tile left of the name, same height as 40 px", P.pg.evaluate("""() => [...document.querySelectorAll('.log-row')].every((r) => { const t = r.querySelector('.fi').getBoundingClientRect(), n = r.querySelector('.log-row__name').getBoundingClientRect(); return t.right <= n.left + 1 && Math.round(t.width) === 40 })"""))
        ok(f"[{label}] logs: name and size still readable (not squeezed to a sliver)", P.pg.evaluate("() => [...document.querySelectorAll('.log-row__name')].every((e) => e.getBoundingClientRect().width > 60)"))
        ok(f"[{label}] logs: buttons inside the row", P.pg.evaluate("""() => [...document.querySelectorAll('.log-row')].every((r) => { const R = r.getBoundingClientRect(); return [...r.querySelectorAll('button')].every((b) => { const x = b.getBoundingClientRect(); return x.left >= R.left - 1 && x.right <= R.right + 1 }) })"""))
        ok(f"[{label}] logs: no sideways scrolling", overflow(P) <= 0, overflow(P))
        P.pg.locator(".oui-card:has(.oui-card-title:text-is('Log di sistema'))").first.screenshot(path=f"{out}/logs_{label}.png", animations="disabled")
        ok(f"[{label}] no page errors (logs)", not errs(P), errs(P)[:2]); P.close()

    # ------------------------------------------------------------------ desktop
    P = fresh("files", 1440, 900, no_thumbs=["Vase", "Bracket", "Benchy"])
    P.pg.wait_for_timeout(600)
    ok("[desktop] files: tiles show placeholders", P.pg.locator(".file-card .fi--placeholder").count() >= 3, P.pg.locator(".file-card .fi--placeholder").count())
    c = centred(P, ".desk-thumb", ".desk-thumb .fi--placeholder")
    ok("[desktop] detail panel: placeholder centred in the big preview", c is None or (c["dx"] < 1.5 and c["dy"] < 1.5), c)
    ok("[desktop] no old symbol", not body_has_old(P), body_has_old(P))
    P.pg.screenshot(path=f"{out}/files_desktop.png", animations="disabled")
    ok("[desktop] no page errors (files)", not errs(P), errs(P)[:2]); P.close()

    P = fresh("config", 1440, 900, cfg=CFG)
    P.pg.wait_for_timeout(600)
    bad = {name: (tone_of(P, ".cfg-row", ".cfg-row__name", name), tone) for name, tone in EXPECTED.items() if tone_of(P, ".cfg-row", ".cfg-row__name", name) != tone}
    ok("[desktop] config: kinds right", not bad, bad)
    P.pg.screenshot(path=f"{out}/config_desktop.png", animations="disabled")
    ok("[desktop] no page errors (config)", not errs(P), errs(P)[:2]); P.close()

    P = fresh("sistema", 1440, 900)
    P.pg.wait_for_timeout(600)
    ok("[desktop] logs on the system page have tiles", P.pg.locator(".log-row .fi").count() == 3, P.pg.locator(".log-row .fi").count())
    P.pg.screenshot(path=f"{out}/system_desktop.png", animations="disabled")
    ok("[desktop] no page errors (system)", not errs(P), errs(P)[:2]); P.close()

    b.close()
print("\nFAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
