"""The editor's comment bar: Commenta / Decommenta (and Ctrl+/) on the selected lines. Usage: editor_comment_test.py <html> <outdir> <port>"""
import sys, os, re, json
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
FAILS = []


def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra != "" else ""))


# ---------------------------------------------------------------- an independent model of what the buttons must do
def ref(text, a, b, mode, mark="#"):
    """-> (new text, new selection start, new selection end, count) or None"""
    line_of = lambda off: text.count("\n", 0, off)
    first = line_of(a)
    last = line_of(b - 1) if (b > a and text[b - 1] == "\n") else line_of(b)
    lines = text.split("\n")
    block = lines[first:last + 1]
    filled = [l for l in block if l.strip()]
    has = lambda l: l.lstrip().startswith(mark)
    if mode == "toggle": mode = "uncomment" if filled and all(has(l) for l in filled) else "comment"
    count = 0; new = []
    if mode == "comment":
        indent = min((len(l) - len(l.lstrip()) for l in filled), default=0)
        for l in block:
            if not l.strip(): new.append(l); continue
            count += 1; new.append(l[:indent] + mark + l[indent:])
    else:
        for l in block:
            if not has(l): new.append(l); continue
            count += 1; lead = len(l) - len(l.lstrip()); new.append(l[:lead] + l[lead + len(mark):])
    if count == 0: return None
    before = "\n".join(lines[:first]); start = len(before) + (1 if first else 0)
    replaced = "\n".join(new)
    result = "\n".join(lines[:first] + new + lines[last + 1:])
    return result, start, start + len(replaced), count


def offset(text, line, col):
    """line is 1-based, col 0-based; col None = end of the line"""
    lines = text.split("\n")
    base = sum(len(l) + 1 for l in lines[:line - 1])
    return base + (len(lines[line - 1]) if col is None else col)


def fresh_phone(w=390, h=844):
    mock.reset()
    P = Page(b, mock, w, h)
    P.goto("config", 1800)
    P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^printer.cfg$"))).first.locator(".cfg-row__main").click()
    P.pg.wait_for_selector(".editor-input"); P.pg.wait_for_timeout(500)
    return P


def value(P): return P.pg.evaluate("() => document.querySelector('.editor-input').value")
def sel(P): return P.pg.evaluate("() => [document.querySelector('.editor-input').selectionStart, document.querySelector('.editor-input').selectionEnd]")
def select(P, a, b): P.pg.evaluate("([a, b]) => { const t = document.querySelector('.editor-input'); t.focus(); t.setSelectionRange(a, b); }", [a, b])
def press(P, label): P.pg.locator(".editor-tools .oui-btn", has_text=re.compile("^" + label + "$")).click(); P.pg.wait_for_timeout(120)
def errs(P): return [e for e in P.errors if "pageerror" in e or "console.error" in e]
def status(P): return P.pg.locator(".editor-status").inner_text()
def active_is_text(P): return P.pg.evaluate("() => document.activeElement && document.activeElement.classList.contains('editor-input')")


with sync_playwright() as p:
    b = p.chromium.launch()

    # ------------------------------------------------------------------ the bar is there, fits, and keeps the editor usable
    for w, h in ((390, 844), (360, 740), (320, 640)):
        P = fresh_phone(w, h)
        tools = P.pg.locator(".editor-tools")
        boxes = [tools.locator(".oui-btn:not(.editor-history)").nth(i).bounding_box() for i in range(2)]
        body = P.pg.locator(".editor-body").bounding_box()
        ok(f"[{w}] comment bar: two buttons 'Commenta' and 'Decommenta' inside the screen", tools.count() == 1 and tools.locator(".oui-btn:not(.editor-history)").all_inner_texts() == ["Commenta", "Decommenta"] and all(x and x["x"] >= 0 and x["x"] + x["width"] <= w for x in boxes), boxes)
        ok(f"[{w}] comment bar: buttons side by side and wide enough to tap", boxes[0]["y"] == boxes[1]["y"] and all(x["width"] >= 90 and x["height"] >= 40 for x in boxes), boxes)
        ok(f"[{w}] editor body keeps room (>= 250 px)", body["height"] >= 250, body)
        ok(f"[{w}] no sideways scrolling", P.pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0)
        P.pg.screenshot(path=f"{out}/bar_{w}.png", animations="disabled")
        P.close()

    # ------------------------------------------------------------------ what the buttons do, against the model
    P = fresh_phone()
    original = value(P)
    L = lambda n: n  # readability
    cases = [
        ("whole lines 4-7",                    (4, 0, 7, None), "comment"),
        ("selection starting and ending mid-line", (4, 3, 6, 5), "comment"),
        ("indented macro body (keeps its shape)", (16, 0, 19, None), "comment"),
        ("with blank lines inside (they stay blank)", (8, 0, 12, None), "comment"),
        ("a single line by the caret",         (5, 4, 5, 4), "comment"),
        ("ending at the very start of a line (that line is not touched)", (4, 0, 7, 0), "comment"),
        ("the whole file",                     (1, 0, 21, None), "comment"),
    ]
    for name, (l1, c1, l2, c2), mode in cases:
        P.pg.evaluate("() => 0");
        cur = value(P)
        a, bb = offset(cur, l1, c1), offset(cur, l2, c2)
        want = ref(cur, a, bb, mode)
        select(P, a, bb); press(P, "Commenta")
        got = value(P)
        ok(f"comment: {name}: text as the model says", want and got == want[0], (got[:120] if want else "model: none"))
        ok(f"comment: {name}: the changed lines stay selected", want and sel(P) == [want[1], want[2]], (sel(P), want and want[1:3]))
        ok(f"comment: {name}: the textarea keeps the focus", active_is_text(P))
        # and the other button takes it all back
        press(P, "Decommenta")
        ok(f"comment: {name}: Decommenta gives the original back exactly", value(P) == cur, value(P)[:120])
        P.pg.evaluate("() => 0")
    ok("after all that the text is the original again and the file is not dirty", value(P) == original and P.pg.locator(".editor-title-row .oui-badge--warn").count() == 0, P.pg.locator(".editor-title-row .oui-badge--warn").count())

    # ---------------------------------------------------- uncomment: only lines that have a mark lose ONE, whatever the indent
    mixed = "# KlippEye\n[stepper_x]\n#step_pin: PB13\n##dir_pin: !PB12\n    # indented\nenable_pin: !PB14\n\n#\nmicrosteps: 32\n"
    P.pg.evaluate("(t) => { const el = document.querySelector('.editor-input'); el.focus(); el.select(); document.execCommand('insertText', false, t); }", mixed)
    P.pg.wait_for_timeout(200)
    ok("[setup] the editor holds the mixed text", value(P) == mixed, value(P)[:60])
    select(P, 0, len(mixed)); press(P, "Decommenta")
    want = "KlippEye\n[stepper_x]\nstep_pin: PB13\n#dir_pin: !PB12\n     indented\nenable_pin: !PB14\n\n\nmicrosteps: 32\n"
    ok("uncomment: one # off every line that has one (## -> #, indented too), others untouched", value(P) == want.replace("KlippEye", " KlippEye"), value(P))
    ok("uncomment: says how many lines", re.search(r"5 righe decommentate", status(P)) is not None, status(P))
    # nothing to do -> says so, text untouched
    before = value(P); select(P, offset(before, 2, 0), offset(before, 2, None)); press(P, "Decommenta")
    ok("uncomment: a line without # -> nothing changes and it says so", value(P) == before and "Nessuna riga con #" in status(P), status(P))
    select(P, offset(before, 7, 0), offset(before, 7, 0)); press(P, "Commenta")
    ok("comment: a blank line -> nothing changes and it says so", value(P) == before and "Nessuna riga da commentare" in status(P), status(P))
    ok("the status goes away by itself", (P.pg.wait_for_timeout(3000) or True) and status(P) == "", status(P))
    P.close()

    # ------------------------------------------------------------------ undo, dirty, highlight, save
    P = fresh_phone()
    original = value(P)
    select(P, offset(original, 4, 0), offset(original, 7, None)); press(P, "Commenta")
    ok("dirty badge and Salva after commenting", P.pg.locator(".editor-title-row .oui-badge--warn").count() == 1 and P.pg.locator(".editor-save", has_text=re.compile("^Salva$")).is_enabled())
    ok("status: '4 righe commentate'", "4 righe commentate" in status(P), status(P))
    hl = P.pg.evaluate("() => [...document.querySelectorAll('.editor-layer .hl-comment')].map((e) => e.textContent)")
    ok("the colour layer shows the new comments", sum(1 for t in hl if t.startswith("#")) >= 5, hl[:6])
    P.pg.screenshot(path=f"{out}/commented_phone.png", animations="disabled")
    P.pg.locator(".editor-input").focus(); P.pg.keyboard.press("Control+z"); P.pg.wait_for_timeout(200)
    ok("Ctrl+Z takes the whole comment back in one step", value(P) == original, value(P)[:100])
    P.pg.keyboard.press("Control+Shift+z"); P.pg.wait_for_timeout(200)
    ok("and Ctrl+Shift+Z does it again", value(P) != original and value(P).count("#") > original.count("#"))
    P.pg.locator(".editor-save", has_text=re.compile("^Salva$")).click(); P.pg.wait_for_timeout(1500)
    ok("saving sends the commented text", any(g.startswith("UPLOAD:") for g in mock.gcode()), mock.gcode()[-2:])
    ok("no page errors", not errs(P), errs(P)[:2]); P.close()

    # ------------------------------------------------------------------ a real selection by keyboard + tapping the button with the mouse
    P = fresh_phone()
    original = value(P)
    P.pg.locator(".editor-input").click(); P.pg.keyboard.press("Control+Home"); P.pg.keyboard.press("ArrowDown"); P.pg.keyboard.press("ArrowDown")
    for _ in range(3): P.pg.keyboard.press("Shift+ArrowDown")
    s = sel(P); P.pg.locator(".editor-tools .oui-btn", has_text=re.compile("^Commenta$")).first.hover()
    press(P, "Commenta")
    want = ref(original, s[0], s[1], "comment")
    ok("selection made with the keyboard: lines commented as the model says", want and value(P) == want[0], (s, value(P)[:100]))
    ok("the typing caret is still in the text after the click", active_is_text(P))
    P.close()

    # ------------------------------------------------------------------ Ctrl+/ toggles (desktop)
    mock.reset(); P = Page(b, mock, 1440, 900); P.goto("config", 1800)
    P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^printer.cfg$"))).first.locator(".cfg-row__main").click()
    P.pg.wait_for_selector(".editor-input"); P.pg.wait_for_timeout(600)
    original = value(P)
    ok("[desktop] comment bar in the inline editor", P.pg.locator(".desk-editor .editor-tools .oui-btn:not(.editor-history)").count() == 2)
    select(P, offset(original, 4, 0), offset(original, 7, None))
    P.pg.keyboard.press("Control+/"); P.pg.wait_for_timeout(150)
    want = ref(original, offset(original, 4, 0), offset(original, 7, None), "comment")
    ok("[desktop] Ctrl+/ comments", value(P) == want[0], value(P)[:80])
    P.pg.keyboard.press("Control+/"); P.pg.wait_for_timeout(150)
    ok("[desktop] Ctrl+/ again uncomments (toggle)", value(P) == original)
    select(P, offset(original, 4, 0), offset(original, 9, None)); press(P, "Commenta"); P.pg.keyboard.press("Control+/"); P.pg.wait_for_timeout(150)
    ok("[desktop] Ctrl+/ on a block that is all commented -> uncomments it", value(P) == original, value(P)[:80])
    # mixed block: toggle comments (not every line has a mark)
    select(P, offset(original, 3, 0), offset(original, 6, None)); press(P, "Commenta")
    select(P, offset(value(P), 3, 0), offset(value(P), 8, None)); cur = value(P); P.pg.keyboard.press("Control+/"); P.pg.wait_for_timeout(150)
    want = ref(cur, offset(cur, 3, 0), offset(cur, 8, None), "toggle")
    ok("[desktop] Ctrl+/ on a half-commented block comments all of it", want and value(P) == want[0] and value(P) != cur, (value(P)[:100]))
    P.pg.screenshot(path=f"{out}/desktop_commented.png", animations="disabled")
    ok("[desktop] no page errors", not errs(P), errs(P)[:2]); P.close()

    # ------------------------------------------------------------------ G-code takes ; and a big G-code file has no bar
    mock.reset(); P = Page(b, mock, 390, 844); P.goto("files", 1800)
    P.pg.locator(".file-card").nth(2).click(button="right"); P.pg.wait_for_timeout(650)
    P.pg.locator(".file-action", has_text="Apri nell'editor").click(); P.pg.wait_for_selector(".editor-input"); P.pg.wait_for_timeout(700)
    cur = value(P)
    a, bb = offset(cur, 3, 0), offset(cur, 5, None)
    select(P, a, bb); press(P, "Commenta")
    want = ref(cur, a, bb, "comment", ";")
    ok("[gcode] Commenta puts ; (a # line is no comment in G-code)", want and value(P) == want[0] and "#" not in value(P)[:200], value(P)[:140])
    press(P, "Decommenta")
    ok("[gcode] Decommenta takes the ; off again", value(P) == cur)
    ok("[gcode] the button titles say ;", ";" in (P.pg.locator(".editor-tools .oui-btn:not(.editor-history)").first.get_attribute("title") or ""))
    P.close()
    mock.reset(); P = Page(b, mock, 390, 844); P.goto("files", 1800)
    P.pg.locator(".file-card").nth(3).click(button="right"); P.pg.wait_for_timeout(650)
    P.pg.locator(".file-action", has_text="Apri nell'editor").click(); P.pg.wait_for_selector(".editor-input"); P.pg.wait_for_timeout(1200)
    ok("[read-only] a big G-code file has no comment bar", P.pg.locator(".editor-tools").count() == 0 and P.pg.evaluate("() => document.querySelector('.editor-input').readOnly"))
    P.pg.locator(".editor-input").focus(); P.pg.keyboard.press("Control+/"); P.pg.wait_for_timeout(150)
    ok("[read-only] Ctrl+/ does nothing there", "Modificato" not in P.pg.locator(".editor-title-row").inner_text())
    P.close()

    b.close()
print("\nFAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
