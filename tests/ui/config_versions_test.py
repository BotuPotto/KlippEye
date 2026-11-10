"""Release 1.81: the earlier versions of a config file in the editor: the text a file had is kept by the service
before each save from here; «Versions» lists them (and Klipper's printer-YYYYMMDD_HHMMSS.cfg backups for printer.cfg),
shows what putting one back changes and puts it back in the editor (unsaved; Undo takes it back).
Usage: config_versions_test.py <html> <outdir> <port>"""
import json
import requests
import os
import urllib.request
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



def value(P):
    return P.pg.evaluate("() => %s.state.doc.toString()" % VIEW)


def errs(P):
    return [e for e in P.errors if "pageerror" in e or "console.error" in e]


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def open_cfg(b, name="printer.cfg", w=390, h=844, reset=True):
    if reset:
        mock.reset()
    P = Page(b, mock, w, h)
    CUR[0] = P
    P.goto("config", 1800)
    P.pg.locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^" + re.escape(name) + "$"))).first.locator(".cfg-row__main").click()
    P.pg.wait_for_selector(".screen--editor .cm-editor")
    P.pg.wait_for_timeout(500)
    return P


def open_versions(P):
    P.pg.locator("[data-editor-versions]").click()
    dialog = P.pg.locator(".cfg-versions")
    wait_until(lambda: dialog.count() == 1 and "Caricamento" not in dialog.inner_text())
    return dialog


with sync_playwright() as p:
    b = p.chromium.launch()

    P = open_cfg(b)
    pg = P.pg
    original = value(P)
    ok("the editor of a config file has «Versions»", pg.locator("[data-editor-versions]").count() == 1)
    dialog = open_versions(P)
    ok("no version yet: said in words", wait_until(lambda: dialog.locator("[data-versions-empty]").count() == 1), dialog.inner_text())
    ok("the dialog is above the editor", pg.evaluate("() => { const r = document.querySelector('.cfg-versions').getBoundingClientRect(); const e = document.elementFromPoint(r.left + r.width / 2, r.top + 20); return !!(e && e.closest('.cfg-versions')); }"))
    dialog.get_by_role("button", name="Chiudi", exact=True).click()
    ok("closed", wait_until(lambda: dialog.count() == 0))

    # a change, saved: the text the file had is kept first
    pg.evaluate("() => { const v = %s; v.dispatch({ changes: { from: 0, insert: '# a line added by the test\\n' } }); }" % VIEW)
    pg.locator(".editor-save").first.click()
    ok("the save keeps the old text first (POST /api/config/versions for printer.cfg)", wait_until(lambda: state().get("versions_log") == ["printer.cfg"], 6), state().get("versions_log"))
    wait_until(lambda: pg.locator(".screen--editor").count() == 0, 6)

    # reopened: the version, what putting it back changes, put back
    P.close()
    P = open_cfg(b, reset=False)
    pg = P.pg
    ok("reopened: the saved text", value(P).startswith("# a line added by the test\n"))
    dialog = open_versions(P)
    rows = dialog.locator("[data-version]")
    ok("one version, kept before the save from here", wait_until(lambda: rows.count() == 1 and rows.first.get_attribute("data-version") == "kept" and "Prima di un salvataggio da qui" in rows.first.inner_text()), [rows.count(), dialog.evaluate("e => e.outerHTML.slice(0, 1500)")])
    rows.first.click()
    ok("chosen: putting it back takes the added line away (1 goes, 0 come back)", wait_until(lambda: dialog.locator("[data-diff-sum]").get_attribute("data-diff-sum") == "1-0"), dialog.inner_text()[:400])
    ok("the line that goes is shown with −", dialog.locator(".cfg-diff__line--del").count() == 1 and "a line added by the test" in dialog.locator(".cfg-diff__line--del").inner_text())
    pg.screenshot(path=out + "/diff_phone.png")
    dialog.locator("[data-version-restore]").click()
    ok("put back: the editor has the old text, marked as changed, nothing written yet", wait_until(lambda: value(P) == original) and pg.locator(".editor-title-row .oui-badge--warn").count() == 1 and state()["gcode_log"].count("UPLOAD:/printer.cfg") == 1, state()["gcode_log"][-3:])
    ok("the status says to save", wait_until(lambda: "Salva per tenerla" in pg.locator(".editor-status").inner_text()), pg.locator(".editor-status").inner_text())
    pg.evaluate("() => CM.undo(%s)" % VIEW)
    ok("Undo takes it back", wait_until(lambda: value(P).startswith("# a line added by the test")))
    ok("no page errors", not errs(P), errs(P)[:2])
    P.close()

    # Klipper's backup of printer.cfg (SAVE_CONFIG): listed too, with what is different
    backup = original.replace("[printer]", "[printer]\n# old setting", 1) if "[printer]" in original else "# old\n" + original
    requests.post(mock.base + "/server/files/upload", data={"root": "config"}, files={"file": ("printer-20261108_203000.cfg", backup.encode())})
    P = open_cfg(b, w=1440, h=900, reset=False)
    pg = P.pg
    dialog = open_versions(P)
    rows = dialog.locator("[data-version]")
    ok("[1440] Klipper's backup listed with the version kept here, newest first", wait_until(lambda: rows.count() == 2 and dialog.locator('[data-version="klipper"]').count() == 1 and "08/11/26" in dialog.locator('[data-version="klipper"]').inner_text()), dialog.inner_text())
    dialog.locator('[data-version="klipper"]').click()
    ok("[1440] the backup: one line comes back, the test line goes", wait_until(lambda: dialog.locator("[data-diff-sum]").count() == 1 and dialog.locator(".cfg-diff__line--add").count() >= 1 and dialog.locator(".cfg-diff__line--del").count() >= 1), dialog.inner_text()[:500])
    pg.screenshot(path=out + "/diff_desktop.png")
    dialog.get_by_role("button", name="Indietro", exact=True).click()
    ok("[1440] back to the list", wait_until(lambda: rows.count() == 2))
    ok("[1440] no sideways scroll, no page errors", pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth") and not errs(P), errs(P)[:2])
    P.close()

    # another file: no Klipper backups, its own versions only
    P = open_cfg(b, name="moonraker.conf")
    dialog = open_versions(P)
    ok("moonraker.conf: no version, no Klipper backup", wait_until(lambda: dialog.locator("[data-versions-empty]").count() == 1))
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
