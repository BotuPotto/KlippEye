"""Release 1.41.0 (roadmap 6c part 3): the text editor on CodeMirror 6, like Mainsail. Line numbers and colours, the
[sections] folded / unfolded and listed (tap one to go there), the reference page of the section under the caret, search
and replace in CodeMirror's panel (in Italian), Annulla / Ripristina, and the comment bar of the earlier editor
(# in a config file, ; in G-code), Ctrl+S, Ctrl+/. Against the mock.
Usage: editor_test.py <html> <outdir> <port>"""
import os
import re
import sys
import time
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit
atexit.register(mock.stop)
FAILS = []
CUR = [None]

VIEW = "CM.EditorView.findFromDOM(document.querySelector('.screen--editor .cm-editor'))"


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


def wait_until(fn, timeout=5.0, step=0.15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    return bool(fn())


def ref(text, a, b, mode, mark="#"):
    """The comment model: -> (new text, selection start, selection end, count) or None."""
    line_of = lambda off: text.count("\n", 0, off)
    first = line_of(a)
    last = line_of(b - 1) if (b > a and text[b - 1] == "\n") else line_of(b)
    lines = text.split("\n")
    block = lines[first:last + 1]
    filled = [l for l in block if l.strip()]
    has = lambda l: l.lstrip().startswith(mark)
    if mode == "toggle":
        mode = "uncomment" if filled and all(has(l) for l in filled) else "comment"
    count = 0
    new = []
    if mode == "comment":
        indent = min((len(l) - len(l.lstrip()) for l in filled), default=0)
        for l in block:
            if not l.strip():
                new.append(l)
                continue
            count += 1
            new.append(l[:indent] + mark + l[indent:])
    else:
        for l in block:
            if not has(l):
                new.append(l)
                continue
            count += 1
            lead = len(l) - len(l.lstrip())
            new.append(l[:lead] + l[lead + len(mark):])
    if count == 0:
        return None
    before = "\n".join(lines[:first])
    start = len(before) + (1 if first else 0)
    replaced = "\n".join(new)
    return "\n".join(lines[:first] + new + lines[last + 1:]), start, start + len(replaced), count


def offset(text, line, col):
    lines = text.split("\n")
    return sum(len(l) + 1 for l in lines[:line - 1]) + (len(lines[line - 1]) if col is None else col)


def value(P):
    return P.pg.evaluate("() => %s.state.doc.toString()" % VIEW)


def sel(P):
    return P.pg.evaluate("() => { const r = %s.state.selection.main; return [r.from, r.to]; }" % VIEW)


def select(P, a, b):
    P.pg.evaluate("([a, b]) => { const v = %s; v.focus(); v.dispatch({ selection: { anchor: a, head: b } }); }" % VIEW, [a, b])


def press(P, label):
    P.pg.locator(".editor-tools .oui-btn", has_text=re.compile("^" + label + "$")).click()
    P.pg.wait_for_timeout(150)


def status(P):
    return P.pg.locator(".editor-status").inner_text()


def focused(P):
    return P.pg.evaluate("() => %s.hasFocus" % VIEW)


def dirty(P):
    return P.pg.locator(".editor-title-row .oui-badge--warn").count() == 1


def errs(P):
    return [e for e in P.errors if "pageerror" in e or "console.error" in e]


def open_cfg(b, name="printer.cfg", w=390, h=844):
    mock.reset()
    P = Page(b, mock, w, h)
    CUR[0] = P
    P.goto("config", 1800)
    P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^" + re.escape(name) + "$"))).first.locator(".cfg-row__main").click()
    P.pg.wait_for_selector(".screen--editor .cm-editor")
    P.pg.wait_for_timeout(500)
    return P


with sync_playwright() as p:
    b = p.chromium.launch()

    # ------------------------------------------------------------------ it fits, on every phone
    for w, hh in ((390, 844), (360, 740), (320, 640)):
        P = open_cfg(b, w=w, h=hh)
        pg = P.pg
        ok(f"[{w}] CodeMirror with line numbers and the fold arrows", pg.locator(".cm-lineNumbers").count() == 1 and pg.locator(".cm-foldGutter").count() == 1)
        row = [x for x in (e.bounding_box() for e in pg.locator(".editor-tools > *").all()) if x]
        ok(f"[{w}] the tools in one row, inside the screen, none over another, >= 40 px tall",
           len(row) >= 6 and len({round(x["y"]) for x in row}) == 1 and all(x["x"] >= 0 and x["x"] + x["width"] <= w + 0.5 and x["height"] >= 40 for x in row)
           and all(row[i]["x"] + row[i]["width"] <= row[i + 1]["x"] + 0.5 for i in range(len(row) - 1)), row)
        body = pg.locator(".editor-body").bounding_box()
        ok(f"[{w}] the text keeps room (>= 250 px)", body["height"] >= 250, body)
        ok(f"[{w}] no sideways scrolling", pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0)
        if w == 390:
            pg.screenshot(path=out + "/phone.png")
        ok(f"[{w}] no page errors", not errs(P), errs(P)[:2])
        P.close()

    # ------------------------------------------------------------------ colours, sections, folding, reference
    P = open_cfg(b)
    pg = P.pg
    original = value(P)
    ok("the file is in the editor", "[stepper_x]" in original, original[:80])
    ok("the caret is in the text when it opens", focused(P))
    colours = pg.evaluate("""() => { const c = (s) => { const e = [...document.querySelectorAll('.cm-line span')].find(e => e.textContent === s); return e ? getComputedStyle(e).color : null; };
        return { type: c('stepper_x'), key: c('step_pin'), comment: [...document.querySelectorAll('.cm-line span')].map(e => getComputedStyle(e).color).includes('rgb(106, 153, 85)') }; }""")
    ok("colours: the section's type, the key (a pin) and the comments each in their colour", colours["type"] == "rgb(78, 201, 176)" and colours["key"] == "rgb(220, 220, 170)" and colours["comment"], colours)
    pg.locator(".editor-sections-btn").click()
    pg.wait_for_selector(".oui-menu")
    items = pg.locator(".oui-menu .editor-section-item[data-section-line]")
    names = [t.split("\n")[0] for t in items.all_inner_texts()]
    ok("'Sezioni del file' lists every [section] with its line", len(names) >= 3 and names[0].startswith("[") and "riga" in items.first.inner_text(), names[:5])
    ok("... the menu is over the editor", pg.evaluate("() => { const m = document.querySelector('.oui-menu').getBoundingClientRect(); const e = document.elementFromPoint(m.x + m.width / 2, m.y + 20); return !!e.closest('.oui-menu'); }"))
    pg.screenshot(path=out + "/sections.png")
    target = items.nth(len(names) - 1)
    line = int(target.get_attribute("data-section-line"))
    target.click()
    pg.wait_for_timeout(300)
    caret_line = pg.evaluate("() => { const v = %s; return v.state.doc.lineAt(v.state.selection.main.head).number; }" % VIEW)
    ok("tapping one puts the caret on it (and it is on view)", caret_line == line and pg.locator(".cm-activeLine", has_text=names[-1]).count() == 1, (caret_line, line))
    href = pg.locator(".editor-docs").get_attribute("href") or ""
    ok("the reference button opens Klipper's page of the section under the caret", href.startswith("https://www.klipper3d.org/Config_Reference.html#"), href)
    select(P, offset(original, 4, 0), offset(original, 4, 0))
    pg.wait_for_timeout(200)
    ok("... [stepper_x] is [stepper] there", pg.locator(".editor-docs").get_attribute("href").endswith("#stepper"), pg.locator(".editor-docs").get_attribute("href"))
    pg.locator(".editor-sections-btn").click()
    pg.locator(".oui-menu .editor-section-item", has_text="Chiudi tutte le sezioni").click()
    pg.wait_for_timeout(300)
    ok("'Chiudi tutte le sezioni': each section folds to its first line", pg.locator(".cm-foldPlaceholder").count() == 2 and pg.locator(".cm-line", has_text="step_pin").count() == 0, pg.locator(".cm-foldPlaceholder").count())
    pg.screenshot(path=out + "/folded.png")
    pg.locator(".editor-sections-btn").click()
    pg.locator(".oui-menu .editor-section-item", has_text="Apri tutte le sezioni").click()
    pg.wait_for_timeout(300)
    ok("... and 'Apri tutte' opens them", pg.locator(".cm-foldPlaceholder").count() == 0)
    pg.locator(".cm-foldGutter .cm-gutterElement .editor-fold-mark").filter(visible=True).first.click()
    pg.wait_for_timeout(200)
    ok("the arrow next to a [section] folds just that one", pg.locator(".cm-foldPlaceholder").count() == 1)
    ok("folding does not change the text", value(P) == original and not dirty(P))

    # ------------------------------------------------------------------ search and replace
    pg.evaluate("() => CM.unfoldAll(%s)" % VIEW)
    pg.locator(".editor-search-btn").click()
    ok("the search button opens CodeMirror's panel, in Italian", wait_until(lambda: pg.locator(".cm-search").count() == 1) and pg.locator(".cm-search input[name=search]").get_attribute("placeholder") == "Trova"
       and pg.locator(".cm-search button[name=replaceAll]").inner_text() == "sostituisci tutti", pg.locator(".cm-search").inner_text() if pg.locator(".cm-search").count() else "")
    pg.locator(".cm-search input[name=search]").press_sequentially("step_pin")
    pg.wait_for_timeout(300)
    ok("the matches are marked in the text", wait_until(lambda: pg.locator(".cm-searchMatch").count() >= 1), pg.locator(".cm-content").inner_text()[:200])
    pg.screenshot(path=out + "/search.png")
    pg.locator(".cm-search input[name=replace]").fill("STEP_PIN_X")
    pg.locator(".cm-search button[name=replaceAll]").click()
    pg.wait_for_timeout(300)
    ok("'sostituisci tutti' replaces every match (folded ones too)", "step_pin" not in value(P) and value(P).count("STEP_PIN_X") == original.count("step_pin") and dirty(P))
    pg.locator(".editor-tools button[aria-label=Annulla]").click()
    pg.wait_for_timeout(200)
    ok("Annulla takes the whole replacement back at once", value(P) == original, value(P)[:80])
    pg.keyboard.press("Escape")
    ok("Esc closes the panel", wait_until(lambda: pg.locator(".cm-search").count() == 0))
    ok("no page errors", not errs(P), errs(P)[:2])
    P.close()

    # ------------------------------------------------------------------ Annulla / Ripristina
    P = open_cfg(b)
    pg = P.pg
    orig = value(P)
    u = pg.locator(".editor-tools button[aria-label=Annulla]")
    r = pg.locator(".editor-tools button[aria-label=Ripristina]")
    ok("titles say the shortcuts", "Ctrl+Z" in u.get_attribute("title") and "Ctrl+Y" in r.get_attribute("title"))
    ok("nothing to undo or redo yet: both disabled", u.is_disabled() and r.is_disabled())
    end = len(orig)
    select(P, end, end)
    pg.keyboard.type("hello")
    pg.wait_for_timeout(200)
    ok("typing: 'Modificato', Annulla on, Ripristina off", dirty(P) and u.is_enabled() and r.is_disabled())
    u.click()
    pg.wait_for_timeout(200)
    ok("Annulla takes the whole word back at once", value(P) == orig, value(P)[-20:])
    ok("... the text keeps the focus (the keyboard of a phone stays up)", focused(P))
    ok("... back to the original: not 'Modificato' any more, Ripristina on", not dirty(P) and u.is_disabled() and r.is_enabled())
    r.click()
    pg.wait_for_timeout(200)
    ok("Ripristina puts the word back", value(P) == orig + "hello" and dirty(P))
    pg.keyboard.press("Control+z")
    ok("Ctrl+Z works too", wait_until(lambda: value(P) == orig))
    P.close()

    # ------------------------------------------------------------------ the comment bar
    P = open_cfg(b)
    pg = P.pg
    original = value(P)
    lines = original.split("\n")
    cases = [("the caret's line (nothing selected)", 2, 3, 2, 3), ("three lines", 1, 0, 3, None), ("a selection ending at the start of a line", 2, 0, 4, 0)]
    for name, l1, c1, l2, c2 in cases:
        cur = value(P)
        a, z = offset(cur, l1, c1), offset(cur, l2, c2)
        want = ref(cur, a, z, "comment")
        select(P, a, z)
        press(P, "Commenta")
        ok(f"comment: {name}: text as the model says", want and value(P) == want[0], value(P)[:120])
        ok(f"comment: {name}: the changed lines stay selected", want and sel(P) == [want[1], want[2]], (sel(P), want and want[1:3]))
        ok(f"comment: {name}: the text keeps the focus", focused(P))
        press(P, "Decommenta")
        ok(f"comment: {name}: Decommenta gives the original back exactly", value(P) == cur)
    ok("after all that the text is the original again and the file is not dirty", value(P) == original and not dirty(P))
    blank = next((i + 1 for i, l in enumerate(lines) if not l.strip()), None)
    if blank:
        select(P, offset(original, blank, 0), offset(original, blank, 0))
        press(P, "Commenta")
        ok("comment: a blank line -> nothing changes and it says so", value(P) == original and "Nessuna riga da commentare" in status(P), status(P))
    select(P, offset(original, 2, 0), offset(original, 2, 0))
    press(P, "Decommenta")
    ok("uncomment: a line without # -> nothing changes and it says so", value(P) == original and "Nessuna riga con #" in status(P), status(P))
    select(P, 0, offset(original, 4, None))
    press(P, "Commenta")
    ok("status: '4 righe commentate'", "4 righe commentate" in status(P), status(P))
    ok("the new comments are coloured as comments", pg.evaluate("() => [...document.querySelectorAll('.cm-line')].slice(0, 4).every(l => [...l.querySelectorAll('span')].some(s => getComputedStyle(s).color === 'rgb(106, 153, 85)'))"))
    pg.keyboard.press("Control+z")
    ok("Ctrl+Z takes the whole comment back in one step", wait_until(lambda: value(P) == original))
    pg.keyboard.press("Control+/")
    ok("Ctrl+/ comments the selected lines", wait_until(lambda: value(P) == ref(original, 0, offset(original, 4, None), "comment")[0]), value(P)[:80])
    pg.keyboard.press("Control+/")
    ok("Ctrl+/ again uncomments (toggle)", wait_until(lambda: value(P) == original))
    pg.keyboard.press("Control+/")
    pg.wait_for_timeout(150)
    pg.keyboard.press("Control+s")
    ok("Ctrl+S saves the file (and closes the phone's editor)", wait_until(lambda: any(g.startswith("UPLOAD:") for g in mock.gcode())) and wait_until(lambda: pg.locator(".screen--editor").count() == 0, 4), mock.gcode()[-2:])
    ok("no page errors", not errs(P), errs(P)[:2])
    P.close()

    # ------------------------------------------------------------------ G-code: ; and no sections
    mock.reset()
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("files", 2200)
    pg = P.pg
    card = pg.locator(".file-card").first
    box = card.bounding_box()
    pg.mouse.move(box["x"] + 40, box["y"] + 40)
    pg.mouse.down()
    pg.wait_for_timeout(700)
    pg.mouse.up()
    pg.wait_for_selector(".sheet-overlay--actions")
    pg.wait_for_timeout(400)
    pg.locator(".file-action", has_text="Editor").click()
    ok("[gcode] the G-code opens in CodeMirror", wait_until(lambda: pg.locator(".screen--editor .cm-editor").count() == 1, 6))
    pg.wait_for_timeout(400)
    if pg.locator(".editor-tools .editor-comment").count():
        cur = value(P)
        want = ref(cur, 0, offset(cur, 2, None), "comment", ";")
        select(P, 0, offset(cur, 2, None))
        press(P, "Commenta")
        ok("[gcode] Commenta puts ; (a # line is no comment in G-code)", want and value(P) == want[0], value(P)[:100])
        press(P, "Decommenta")
        ok("[gcode] Decommenta takes the ; off again", value(P) == cur)
    ok("[gcode] no sections, no reference button, no fold arrows", pg.locator(".editor-sections-btn").count() == 0 and pg.locator(".editor-docs").count() == 0 and pg.locator(".cm-foldGutter").count() == 0)
    colours = pg.evaluate("() => [...document.querySelectorAll('.cm-line span')].map(e => getComputedStyle(e).color)")
    ok("[gcode] commands coloured", "rgb(215, 186, 125)" in colours, colours[:6])
    pg.screenshot(path=out + "/gcode.png")
    P.close()

    # ------------------------------------------------------------------ moonraker.conf: Moonraker's reference
    P = open_cfg(b, "moonraker.conf")
    href = P.pg.locator(".editor-docs").get_attribute("href") if P.pg.locator(".editor-docs").count() else ""
    ok("moonraker.conf: the reference is Moonraker's configuration page", href.startswith("https://moonraker.readthedocs.io/en/latest/configuration/"), href)
    P.close()

    # ------------------------------------------------------------------ computer: the editor inline
    mock.reset()
    P = Page(b, mock, 1440, 900)
    CUR[0] = P
    P.goto("config", 2000)
    P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^printer.cfg$"))).first.locator(".cfg-row__main").click()
    ok("[desktop] the editor inline with CodeMirror", wait_until(lambda: P.pg.locator(".desk-editor .screen--inline .cm-editor").count() == 1))
    P.pg.wait_for_timeout(400)
    P.pg.screenshot(path=out + "/desktop.png")
    P.pg.locator(".editor-sections-btn").click()
    ok("[desktop] the sections menu opens", wait_until(lambda: P.pg.locator(".oui-menu .editor-section-item").count() >= 3))
    P.pg.keyboard.press("Escape")
    ok("[desktop] no page errors", not errs(P), errs(P)[:2])
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
