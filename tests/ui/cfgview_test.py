"""Release 1.39.0 (roadmap 6c part 1): the configuration files in the chosen order (name A→Z / Z→A, last change, size),
with Klipper's backups and the hidden files shown on request, the choice kept on this device. Against the mock.
Usage: cfgview_test.py <html> <outdir> <port>"""
import os
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
NOW = 1760000000


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


def names(P):
    return P.pg.evaluate("() => [...document.querySelectorAll('.cfg-card .cfg-row__name')].map(e => e.firstChild.textContent.trim())")


def choose(P, key):
    P.pg.locator(".cfg-view-btn").click()
    P.pg.wait_for_selector(".oui-menu")
    P.pg.locator('.oui-menu [data-view-option="%s"]' % key).click()
    P.settle(300)
    if P.pg.locator(".oui-menu").count():
        P.pg.keyboard.press("Escape")
        P.settle(200)


TREE = {"dirs": {"macros": NOW - 5000, "img": NOW - 100, ".git": NOW - 50}, "files": {
    "printer.cfg": {"size": 52000, "modified": NOW - 10, "content": None},
    "moonraker.conf": {"size": 4100, "modified": NOW - 3000, "content": None},
    "printer-20240101_101010.cfg": {"size": 51000, "modified": NOW - 900000, "content": None},
    "notes.txt": {"size": 77, "modified": NOW - 20, "content": None},
    "mainsail.cfg.bak": {"size": 900, "modified": NOW - 400, "content": None},
    ".moonraker.conf.bkp": {"size": 4000, "modified": NOW - 500, "content": None},
    "README": {"size": 10, "modified": NOW - 9000, "content": None},
    "macros/park.cfg": {"size": 1200, "modified": NOW - 5000, "content": None}}}

with sync_playwright() as p:
    b = p.chromium.launch()
    mock.reset()
    mock.set(cfg=TREE)
    P = Page(b, mock, 390, 844)
    CUR[0] = P
    P.goto("config", 2200)
    ok("by default: folders then files A→Z, no backups, no hidden names", wait_until(lambda: names(P) == ["img", "macros", "moonraker.conf", "notes.txt", "printer.cfg", "README"]), names(P))
    left = P.pg.locator(".cfg-left")
    ok("... and it says what is left out: 2 backup files, 2 hidden", left.count() == 1 and "2 file di backup" in left.inner_text() and "2 nascosti" in left.inner_text(), left.inner_text() if left.count() else "")
    P.pg.locator(".cfg-view-btn").click()
    P.pg.wait_for_selector(".oui-menu")
    P.pg.screenshot(path=out + "/menu.png")
    P.pg.keyboard.press("Escape")
    P.settle(200)
    choose(P, "name-desc")
    ok("Nome Z→A", wait_until(lambda: names(P) == ["macros", "img", "README", "printer.cfg", "notes.txt", "moonraker.conf"]), names(P))
    choose(P, "modified")
    ok("Ultima modifica prima (folders too, still first)", wait_until(lambda: names(P) == ["img", "macros", "printer.cfg", "notes.txt", "moonraker.conf", "README"]), names(P))
    choose(P, "size")
    ok("Più grandi prima (folders by name)", wait_until(lambda: names(P) == ["img", "macros", "printer.cfg", "moonraker.conf", "notes.txt", "README"]), names(P))
    choose(P, "backups")
    ok("File di backup: SAVE_CONFIG's printer-….cfg and the .bak, tagged", wait_until(lambda: "printer-20240101_101010.cfg" in names(P) and "mainsail.cfg.bak" in names(P)) and P.pg.locator('[data-tag="backup"]').count() == 2, names(P))
    choose(P, "hidden")
    ok("File nascosti: .git and the hidden backup", wait_until(lambda: ".git" in names(P) and ".moonraker.conf.bkp" in names(P)) and P.pg.locator('[data-tag="hidden"]').count() == 2, names(P))
    ok("nothing left out: no line about it", P.pg.locator(".cfg-left").count() == 0)
    P.pg.screenshot(path=out + "/all.png", full_page=True)
    P.pg.reload()
    P.pg.wait_for_timeout(2200)
    ok("the choice stays on this device after a reload", wait_until(lambda: names(P)[:3] == [".git", "img", "macros"] and names(P)[3] == "printer.cfg"), names(P))
    choose(P, "name")
    choose(P, "backups")
    choose(P, "hidden")
    ok("back to A→Z, no backups, no hidden", wait_until(lambda: names(P) == ["img", "macros", "moonraker.conf", "notes.txt", "printer.cfg", "README"]), names(P))
    P.pg.locator(".cfg-left").click()
    ok("the line about what is left out shows it all", wait_until(lambda: len(names(P)) == 10), names(P))
    ok("no horizontal overflow", P.pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"))
    P.close()
    b.close()

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
