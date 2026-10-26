"""The editor's Annulla / Ripristina buttons and Ctrl+Z / Ctrl+Y. Usage: editor_undo_test.py <html> <outdir> <port>"""
import sys, os, re
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3]); os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit; atexit.register(mock.stop)
FAILS = []


def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra != "" else ""))


def offset(text, line, col):
    lines = text.split("\n")
    return sum(len(l) + 1 for l in lines[:line - 1]) + (len(lines[line - 1]) if col is None else col)


def open_cfg(w=390, h=844, name="printer.cfg"):
    mock.reset()
    P = Page(b, mock, w, h)
    P.goto("config", 1800)
    P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^" + re.escape(name) + "$"))).first.locator(".cfg-row__main").click()
    P.pg.wait_for_selector(".editor-input"); P.pg.wait_for_timeout(500)
    return P


def value(P): return P.pg.evaluate("() => document.querySelector('.editor-input').value")
def sel(P): return P.pg.evaluate("() => [document.querySelector('.editor-input').selectionStart, document.querySelector('.editor-input').selectionEnd]")
def select(P, a, b): P.pg.evaluate("([a, b]) => { const t = document.querySelector('.editor-input'); t.focus(); t.setSelectionRange(a, b); }", [a, b])
def undo_btn(P): return P.pg.locator(".editor-tools .editor-history[aria-label='Annulla']")
def redo_btn(P): return P.pg.locator(".editor-tools .editor-history[aria-label='Ripristina']")
def tap(P, btn): btn.click(); P.pg.wait_for_timeout(80)
def press_c(P, label): P.pg.locator(".editor-tools .oui-btn", has_text=re.compile("^" + label + "$")).click(); P.pg.wait_for_timeout(100)
def dirty(P): return P.pg.locator(".editor-title-row .oui-badge--warn").count() == 1
def errs(P): return [e for e in P.errors if "pageerror" in e or "console.error" in e]
def active_is_text(P): return P.pg.evaluate("() => document.activeElement && document.activeElement.classList.contains('editor-input')")
def to_end(P): P.pg.locator(".editor-input").click(); P.pg.keyboard.press("Control+End")


with sync_playwright() as p:
    b = p.chromium.launch()

    # ------------------------------------------------------------------ the buttons are there and fit
    for w, h in ((390, 844), (360, 740), (320, 640)):
        P = open_cfg(w, h)
        u, r = undo_btn(P), redo_btn(P)
        ub, rb = u.bounding_box(), r.bounding_box()
        row = P.pg.locator(".editor-tools .oui-btn").evaluate_all("(els) => els.map((e) => { const b = e.getBoundingClientRect(); return [b.left, b.right, b.top, b.height]; })")
        ok(f"[{w}] four buttons in one row: Annulla, Ripristina, Commenta, Decommenta", len(row) == 4 and len({round(x[2]) for x in row}) == 1 and P.pg.locator(".editor-tools .oui-btn:not(.editor-history)").all_inner_texts() == ["Commenta", "Decommenta"], row)
        ok(f"[{w}] all inside the screen, none over another, all >= 40 px tall", all(x[0] >= 0 and x[1] <= w and x[3] >= 40 for x in row) and all(row[i][1] <= row[i + 1][0] for i in range(3)), row)
        ok(f"[{w}] titles say the shortcuts", "Ctrl+Z" in u.get_attribute("title") and "Ctrl+Y" in r.get_attribute("title"))
        ok(f"[{w}] nothing to undo or redo yet: both disabled", u.is_disabled() and r.is_disabled())
        ok(f"[{w}] no sideways scrolling", P.pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0)
        P.pg.screenshot(path=f"{out}/bar_{w}.png", animations="disabled")
        P.close()

    # ------------------------------------------------------------------ typing is one step, the caret comes back
    P = open_cfg()
    orig = value(P)
    to_end(P); caret = sel(P)
    P.pg.keyboard.type("hello", delay=15); P.pg.wait_for_timeout(100)
    ok("typing: Annulla enabled, Ripristina not", undo_btn(P).is_enabled() and redo_btn(P).is_disabled())
    P.pg.screenshot(path=f"{out}/typed_phone.png", animations="disabled")
    tap(P, undo_btn(P))
    ok("Annulla takes back the whole word at once", value(P) == orig, value(P)[-20:])
    ok("the caret is where it was before typing", sel(P) == caret, (sel(P), caret))
    ok("the text keeps the focus (the keyboard of a phone stays up)", active_is_text(P))
    ok("back to the original: not 'Modificato' any more", not dirty(P))
    ok("now Annulla is off and Ripristina on", undo_btn(P).is_disabled() and redo_btn(P).is_enabled())
    tap(P, redo_btn(P))
    ok("Ripristina puts the word back", value(P) == orig + "hello" and dirty(P), value(P)[-20:])
    ok("... with the caret after it", sel(P) == [len(orig) + 5] * 2, sel(P))
    ok("... and Ripristina is off again", redo_btn(P).is_disabled())
    # a pause starts a new step
    P.pg.keyboard.type("abc", delay=15); P.pg.wait_for_timeout(1100); P.pg.keyboard.type("def", delay=15); P.pg.wait_for_timeout(100)
    tap(P, undo_btn(P)); ok("a pause between two words: one Annulla takes back only the second", value(P) == orig + "helloabc", value(P)[-12:])
    tap(P, undo_btn(P)); ok("... the next one the first", value(P) == orig + "hello", value(P)[-12:])
    # a new edit throws the redo list away
    P.pg.keyboard.type("Z", delay=15); P.pg.wait_for_timeout(50)
    ok("a new edit after Annulla: nothing left to ripristinare", redo_btn(P).is_disabled(), value(P)[-12:])
    ok("no page errors", not errs(P), errs(P)[:2]); P.close()

    # ------------------------------------------------------------------ erasing: a run of backspaces is one step
    P = open_cfg(); orig = value(P)
    to_end(P); P.pg.keyboard.press("Control+Home"); P.pg.keyboard.press("End")  # end of line 1
    start = sel(P)
    for _ in range(5): P.pg.keyboard.press("Backspace")
    after_erase = value(P)
    ok("[setup] five characters erased", len(after_erase) == len(orig) - 5)
    tap(P, undo_btn(P))
    ok("five backspaces in a row: one Annulla gives all five back", value(P) == orig, value(P)[:40])
    ok("... and the caret is after the restored text", sel(P) == start, (sel(P), start))
    tap(P, redo_btn(P)); ok("Ripristina erases them again", value(P) == after_erase)
    for _ in range(2): P.pg.keyboard.press("Delete")   # forward delete at the caret
    tap(P, undo_btn(P)); ok("Delete (forward) erased and undone as well", value(P) == after_erase, value(P)[:40])
    P.close()

    # ------------------------------------------------------------------ keyboard
    P = open_cfg(1440, 900); orig = value(P)
    P.pg.locator(".editor-input").click(); P.pg.keyboard.press("Control+End"); P.pg.keyboard.type("xyz", delay=15)
    P.pg.keyboard.press("Control+z"); P.pg.wait_for_timeout(100)
    ok("[kbd] Ctrl+Z", value(P) == orig)
    P.pg.keyboard.press("Control+y"); P.pg.wait_for_timeout(100)
    ok("[kbd] Ctrl+Y", value(P) == orig + "xyz")
    P.pg.keyboard.press("Control+z"); P.pg.keyboard.press("Control+Shift+z"); P.pg.wait_for_timeout(100)
    ok("[kbd] Ctrl+Shift+Z (redo, as in most editors)", value(P) == orig + "xyz")
    P.pg.keyboard.press("Meta+z"); P.pg.wait_for_timeout(100)
    ok("[kbd] Cmd+Z (Mac)", value(P) == orig)
    P.pg.keyboard.press("Meta+Shift+z"); P.pg.wait_for_timeout(100)
    ok("[kbd] Cmd+Shift+Z (Mac)", value(P) == orig + "xyz")
    P.pg.keyboard.press("Control+z"); P.pg.keyboard.press("Control+z"); P.pg.keyboard.press("Control+z"); P.pg.wait_for_timeout(100)
    ok("[kbd] Ctrl+Z with nothing left to undo does nothing (and breaks nothing)", value(P) == orig and not errs(P))
    # the browser's own undo command (keyboard of a phone, context menu) goes to the same list
    P.pg.keyboard.type("native", delay=15); P.pg.wait_for_timeout(100)
    P.pg.evaluate("() => document.execCommand('undo')"); P.pg.wait_for_timeout(100)
    ok("[kbd] the browser's own undo command (execCommand) is taken over by the editor's list", value(P) == orig, value(P)[-12:])
    ok("[kbd] ... and the redo list has it, for the button / Ctrl+Y", redo_btn(P).is_enabled())
    P.pg.keyboard.press("Control+y"); P.pg.wait_for_timeout(100)
    ok("[kbd] ... which does it again", value(P) == orig + "native", value(P)[-12:])
    P.pg.screenshot(path=f"{out}/desktop_buttons.png", animations="disabled")
    ok("[desktop] the buttons are in the inline editor", P.pg.locator(".desk-editor .editor-history").count() == 2)
    P.close()

    # ------------------------------------------------------------------ Tab, comment, replace, paste: all in one list, in order
    P = open_cfg(); orig = value(P)
    snaps = [orig]
    to_end(P); P.pg.keyboard.type("abc", delay=15); snaps.append(value(P))
    P.pg.keyboard.press("Tab"); snaps.append(value(P))
    ok("[setup] Tab put two spaces in", snaps[-1] == snaps[-2] + "  ", snaps[-1][-12:])
    select(P, offset(snaps[-1], 3, 0), offset(snaps[-1], 5, None)); press_c(P, "Commenta"); snaps.append(value(P))
    P.pg.keyboard.insert_text("XY"); snaps.append(value(P))               # a paste over the selected lines
    P.pg.keyboard.type("q", delay=15); snaps.append(value(P))
    select(P, 0, 6); P.pg.keyboard.press("Backspace"); snaps.append(value(P))   # erase a selection
    n = len(snaps) - 1
    for i in range(n):
        tap(P, undo_btn(P))
        ok(f"undo {i + 1}/{n}: the text of that moment comes back", value(P) == snaps[n - 1 - i], (value(P)[:40], snaps[n - 1 - i][:40]))
    ok("everything undone: original text, not 'Modificato', Annulla off", value(P) == orig and not dirty(P) and undo_btn(P).is_disabled())
    for i in range(n):
        tap(P, redo_btn(P))
        ok(f"redo {i + 1}/{n}: the text of that moment again", value(P) == snaps[i + 1], (value(P)[:40], snaps[i + 1][:40]))
    ok("everything redone: Ripristina off", redo_btn(P).is_disabled())
    ok("no page errors", not errs(P), errs(P)[:2]); P.close()

    # ------------------------------------------------------------------ Tab stays undoable
    P = open_cfg(1440, 900); orig = value(P)
    P.pg.locator(".editor-input").click(); P.pg.keyboard.press("Control+Home")
    P.pg.keyboard.press("Tab"); P.pg.keyboard.press("Tab"); P.pg.wait_for_timeout(50)
    ok("[tab] two Tabs: four spaces", value(P).startswith("    # KlippEye"), value(P)[:20])
    P.pg.keyboard.press("Control+z"); P.pg.wait_for_timeout(50)
    ok("[tab] Ctrl+Z takes back one Tab", value(P).startswith("  # KlippEye"), value(P)[:20])
    ok("[tab] the caret sits at the end of the remaining indent", sel(P) == [2, 2], sel(P))
    P.pg.keyboard.press("Control+z"); ok("[tab] and the other", value(P) == orig)
    P.close()

    # ------------------------------------------------------------------ the saved state: dirty follows the undo
    P = open_cfg(); orig = value(P)
    to_end(P); P.pg.keyboard.type("# note", delay=15)
    P.pg.locator(".editor-save", has_text=re.compile("^Salva$")).click(); P.pg.wait_for_timeout(1500)
    P.close()
    P = open_cfg(1440, 900); orig = value(P)
    P.pg.locator(".editor-input").click(); P.pg.keyboard.press("Control+End"); P.pg.keyboard.type("# note", delay=15)
    ok("[save] dirty after typing", dirty(P))
    P.pg.locator(".editor-save", has_text=re.compile("^Salva$")).click(); P.pg.wait_for_timeout(1500)
    ok("[save] saved: no longer dirty, and the file stays open (inline)", not dirty(P) and P.pg.locator(".editor-input").count() == 1)
    ok("[save] after saving Annulla still has the history", undo_btn(P).is_enabled())
    tap(P, undo_btn(P))
    ok("[save] Annulla after a save: back to the old text and dirty again (it differs from the saved one)", value(P) == orig and dirty(P) and P.pg.locator(".editor-save", has_text=re.compile("^Salva$")).is_enabled())
    tap(P, redo_btn(P))
    ok("[save] Ripristina: the saved text again, not dirty", value(P) == orig + "# note" and not dirty(P))
    P.close()

    # ------------------------------------------------------------------ a change far away is brought into view
    P = open_cfg(); 
    big = "\n".join(f"line {i:03d}: value" for i in range(1, 181)) + "\n"
    P.pg.evaluate("(t) => { const el = document.querySelector('.editor-input'); el.focus(); el.select(); document.execCommand('insertText', false, t); }", big)
    P.pg.wait_for_timeout(200)
    select(P, offset(big, 3, 0), offset(big, 3, None)); press_c(P, "Commenta")
    P.pg.evaluate("() => { const t = document.querySelector('.editor-input'); t.scrollTop = t.scrollHeight; t.dispatchEvent(new Event('scroll')); }"); P.pg.wait_for_timeout(100)
    far = P.pg.evaluate("() => document.querySelector('.editor-input').scrollTop")
    tap(P, undo_btn(P))
    top = P.pg.evaluate("() => ({ t: document.querySelector('.editor-input').scrollTop, l: document.querySelector('.editor-layer').scrollTop, n: document.querySelector('.editor-lines').scrollTop })")
    ok("far from line 3: Annulla scrolls back to show it", far > 1000 and top["t"] <= 3 * 21 and top["l"] == top["t"] and top["n"] == top["t"], (far, top))
    ok("... and the text was put back", value(P) == big and sel(P) == [offset(big, 3, 0), offset(big, 3, None)], sel(P))
    P.pg.evaluate("() => { const t = document.querySelector('.editor-input'); t.scrollTop = t.scrollHeight; }"); P.pg.wait_for_timeout(100)
    tap(P, redo_btn(P))
    top = P.pg.evaluate("() => document.querySelector('.editor-input').scrollTop")
    ok("... and Ripristina too", top <= 3 * 21 and value(P).split("\n")[2].startswith("#"), top)
    P.close()

    # ------------------------------------------------------------------ a phone keyboard builds words (composition): a word is one step
    P = open_cfg(); orig = value(P)
    to_end(P)
    cdp = P.ctx.new_cdp_session(P.pg)
    for part in ("c", "ci", "cia", "ciao"):
        cdp.send("Input.imeSetComposition", {"text": part, "selectionStart": len(part), "selectionEnd": len(part)}); P.pg.wait_for_timeout(30)
    cdp.send("Input.insertText", {"text": "ciao"}); P.pg.wait_for_timeout(100)
    got = value(P)
    ok("[ime] the composed word is in the text", got == orig + "ciao", got[-12:])
    tap(P, undo_btn(P))
    ok("[ime] one Annulla takes the whole composed word back", value(P) == orig, value(P)[-12:])
    P.close()

    # ------------------------------------------------------------------ the list is limited (300 steps)
    P = open_cfg(); orig = value(P)
    n = P.pg.evaluate("""async () => {
      const tick = () => new Promise((r) => setTimeout(r, 0));   // React draws between two clicks, as it does between two taps
      const t = document.querySelector('.editor-input'); t.focus(); t.setSelectionRange(0, 5);
      const btn = (label) => [...document.querySelectorAll('.editor-tools .oui-btn')].find((e) => e.textContent === label);
      const un = document.querySelector('.editor-history[aria-label=Annulla]');
      for (let i = 0; i < 310; i++) { btn(i % 2 ? 'Decommenta' : 'Commenta').click(); await tick(); }
      let n = 0, last = t.value;
      for (let i = 0; i < 400; i++) { un.click(); await tick(); if (t.value !== last) { n++; last = t.value; } }
      return n;
    }""")
    ok("the history keeps 300 steps", n == 300, n)
    P.pg.wait_for_timeout(100)
    ok("... and then Annulla is disabled", undo_btn(P).is_disabled())
    ok("no page errors", not errs(P), errs(P)[:2]); P.close()

    # ------------------------------------------------------------------ G-code: undo works for a commented line (;)
    mock.reset(); P = Page(b, mock, 390, 844); P.goto("files", 1800)
    P.pg.locator(".file-card").nth(2).click(button="right"); P.pg.wait_for_timeout(650)
    P.pg.locator(".file-action", has_text="Apri nell'editor").click(); P.pg.wait_for_selector(".editor-input"); P.pg.wait_for_timeout(700)
    orig = value(P)
    select(P, offset(orig, 3, 0), offset(orig, 5, None)); press_c(P, "Commenta")
    ok("[gcode] Annulla takes the ; back", (tap(P, undo_btn(P)) or True) and value(P) == orig)
    P.close()

    # ------------------------------------------------------------------ read-only (a long G-code file): nothing to undo, nothing breaks
    mock.reset(); P = Page(b, mock, 390, 844); P.goto("files", 1800)
    P.pg.locator(".file-card").nth(3).click(button="right"); P.pg.wait_for_timeout(650)
    P.pg.locator(".file-action", has_text="Apri nell'editor").click(); P.pg.wait_for_selector(".editor-input"); P.pg.wait_for_timeout(1200)
    before = value(P)
    P.pg.locator(".editor-input").focus(); P.pg.keyboard.press("Control+z"); P.pg.keyboard.press("Control+y"); P.pg.wait_for_timeout(150)
    ok("[read-only] no tools bar, Ctrl+Z / Ctrl+Y change nothing, no errors", P.pg.locator(".editor-history").count() == 0 and value(P) == before and not errs(P), errs(P)[:2])
    P.close()

    b.close()

print("\nFAILED: " + str(len(FAILS)) + " " + str(FAILS) if FAILS else "\nALL PASS")
sys.exit(1 if FAILS else 0)
