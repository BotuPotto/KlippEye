"""Download of config files, logs and images: in a browser, in the app that can save files (KlippEyeApp/3), in older apps."""
import sys, os, re, json, urllib.request
from playwright.sync_api import sync_playwright
from lib import *
html, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
mock = Mock(html, 9560)
import atexit; atexit.register(mock.stop)
FONT = "document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');s.textContent=':root{--oui-font:Inter,sans-serif}';document.head.appendChild(s)})"
WV = "Mozilla/5.0 (Linux; Android 13; Pixel 7 Build/TQ3A; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0 Mobile Safari/537.36"
def ua(extra=""): return "Object.defineProperty(navigator,'userAgent',{get:()=>'%s'})" % (WV + extra)
# what the app's Kotlin bridge is: window.KlippEyeApp.saveUrl(url, name); here it only records its calls
BRIDGE = "window.__saved = []; window.KlippEyeApp = { saveUrl: (u, n) => window.__saved.push([u, n]) };"
NOW = 1760000000
EXTRA = {"my file.cfg": "[a]\n", "è accent.cfg": "[b]\n"}
def tree():
    files = {"printer.cfg": None, "notes.txt": "hello", "macros/led.cfg": None, "img/bed.png": None}
    files.update(EXTRA)
    return {"dirs": {"macros": NOW, "img": NOW}, "files": {p: {"size": 10, "modified": NOW - i, "content": c} for i, (p, c) in enumerate(files.items())}}
def fresh(init=None, w=390, h=844):
    mock.reset(); mock.set(cfg=tree())
    P = Page(b, mock, w, h)
    P.ctx.add_init_script(FONT)
    if init: P.ctx.add_init_script(init)
    P.downloads = []; P.pg.on("download", lambda d: P.downloads.append(d))
    P.goto("config", 1500)
    return P
FAILS = []
def ok(name, cond, extra=""):
    if not cond: FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra != "" else ""))
def card(P): return P.pg.locator(".oui-card:has(.oui-card-title:text-is('File di configurazione'))").first
def row(P, name): return card(P).locator(".cfg-row", has=P.pg.locator(".cfg-row__name", has_text=re.compile("^" + re.escape(name) + "$"))).first
def open_menu(P, name):
    row(P, name).locator(".cfg-row__more").click(); P.pg.wait_for_selector(".sheet-overlay--actions"); P.pg.wait_for_timeout(520)  # the early-click guard
def sheet_titles(P): return P.pg.locator(".sheet-overlay--actions .file-action").all_inner_texts()
def pick(P, title):
    P.pg.locator(".sheet-overlay--actions .file-action", has_text=title).click(); P.pg.wait_for_timeout(500)
def toast(P): return " | ".join(P.pg.locator(".toast").all_inner_texts())
def saved(P): return P.pg.evaluate("window.__saved || null")
def enter(P, folder): row(P, folder).locator(".cfg-row__main").click(); P.pg.wait_for_timeout(500)
def log_download(P, name): P.pg.locator(".log-row", has_text=name).locator("button[aria-label='Download']").click(); P.pg.wait_for_timeout(600)
def get(url): return urllib.request.urlopen(mock.base + url).read().decode()

with sync_playwright() as p:
    b = p.chromium.launch()

    # ---------------------------------------------------------------- browser
    P = fresh()
    open_menu(P, "printer.cfg")
    titles = sheet_titles(P)
    ok("file menu offers 'Scarica' right after 'Apri'", any("Scarica" in t for t in titles) and "Scarica" in titles[1], titles)
    ok("browser: subtitle", any("Salva una copia sul dispositivo" in t for t in titles), titles)
    P.pg.screenshot(path=f"{out}/menu_file.png", animations="disabled")
    with P.pg.expect_download() as dl: pick(P, "Scarica")
    d = dl.value
    ok("browser: file downloaded under its own name", d.suggested_filename == "printer.cfg" and d.url.endswith("/server/files/config/printer.cfg"), (d.suggested_filename, d.url))
    ok("browser: content is the server's", open(d.path()).read() == get("/server/files/config/printer.cfg") and len(open(d.path()).read()) > 20)
    ok("browser: menu closed after the choice", P.pg.locator(".sheet-overlay--actions").count() == 0)
    open_menu(P, "macros")
    ok("folder menu has no 'Scarica'", not any("Scarica" in t for t in sheet_titles(P)), sheet_titles(P))
    P.pg.locator(".sheet-overlay--actions .sheet-footer button").click(); P.pg.wait_for_timeout(300)
    enter(P, "macros")
    open_menu(P, "led.cfg")
    with P.pg.expect_download() as dl: pick(P, "Scarica")
    ok("browser: file inside a folder", dl.value.suggested_filename == "led.cfg" and dl.value.url.endswith("/server/files/config/macros/led.cfg"), (dl.value.suggested_filename, dl.value.url))
    P.pg.reload(); P.pg.wait_for_timeout(1500)
    for name, expect_url in (("my file.cfg", "/server/files/config/my%20file.cfg"), ("è accent.cfg", "/server/files/config/%C3%A8%20accent.cfg")):
        open_menu(P, name)
        with P.pg.expect_download() as dl: pick(P, "Scarica")
        ok("browser: odd name '%s'" % name, dl.value.suggested_filename == name and dl.value.url.endswith(expect_url) and open(dl.value.path()).read() in EXTRA.values(), (dl.value.suggested_filename, dl.value.url))
    # long press opens the same menu
    box = row(P, "notes.txt").bounding_box()
    P.pg.mouse.move(box["x"] + 60, box["y"] + box["height"] / 2); P.pg.mouse.down(); P.pg.wait_for_timeout(900); P.pg.mouse.up(); P.pg.wait_for_timeout(600)
    ok("long press menu also has 'Scarica'", any("Scarica" in t for t in sheet_titles(P)) if P.pg.locator(".sheet-overlay--actions").count() else False)
    P.pg.keyboard.press("Escape"); P.pg.locator(".sheet-overlay--actions .sheet-footer button").click() if P.pg.locator(".sheet-overlay--actions").count() else None
    P.pg.wait_for_timeout(300)
    # logs
    n_before = len(P.downloads)
    log_download(P, "klippy.log")
    ok("browser: log downloaded as an attachment", len(P.downloads) == n_before + 1 and P.downloads[-1].suggested_filename == "klippy.log" and "/api/logs/download?file=klippy.log" in P.downloads[-1].url, [(x.suggested_filename, x.url) for x in P.downloads])
    ok("browser: no popup opened for the log", len(P.ctx.pages) == 1, len(P.ctx.pages))
    # image viewer
    enter(P, "img"); row(P, "bed.png").locator(".cfg-row__main").click(); P.pg.wait_for_selector(".screen--viewer"); P.pg.wait_for_timeout(500)
    with P.pg.expect_download() as dl: P.pg.locator(".viewer-actions button:has-text('Scarica')").click()
    ok("browser: image 'Scarica'", dl.value.suggested_filename == "bed.png" and dl.value.url.endswith("/server/files/config/img/bed.png"), (dl.value.suggested_filename, dl.value.url))
    ok("browser: no page errors", not [e for e in P.errors if "pageerror" in e], P.errors[:3])
    P.close()

    # ---------------------------------------------------------------- the app that saves files (KlippEyeApp/3)
    P = fresh(init=ua(" KlippEyeApp/3") + ";" + BRIDGE)
    open_menu(P, "printer.cfg")
    ok("app: subtitle says Download", any("cartella Download" in t for t in sheet_titles(P)), sheet_titles(P))
    P.pg.screenshot(path=f"{out}/menu_file_app.png", animations="disabled")
    pick(P, "Scarica")
    ok("app: config file goes to the app's bridge with its name", saved(P) == [["/server/files/config/printer.cfg", "printer.cfg"]], saved(P))
    ok("app: no browser download attempted", len(P.downloads) == 0 and toast(P) == "", (len(P.downloads), toast(P)))
    open_menu(P, "my file.cfg"); pick(P, "Scarica")
    ok("app: the address is percent-encoded", saved(P)[-1] == ["/server/files/config/my%20file.cfg", "my file.cfg"], saved(P))
    enter(P, "macros"); open_menu(P, "led.cfg"); pick(P, "Scarica")
    ok("app: file in a folder", saved(P)[-1] == ["/server/files/config/macros/led.cfg", "led.cfg"], saved(P))
    log_download(P, "moonraker.log")
    ok("app: log goes to the bridge", saved(P)[-1] == ["/api/logs/download?file=moonraker.log", "moonraker.log"], saved(P))
    ok("app: log opens no window and downloads nothing itself", len(P.ctx.pages) == 1 and len(P.downloads) == 0)
    enter(P, "..") if False else None
    card(P).locator("button[title='Cartella principale']").click(); P.pg.wait_for_timeout(500)
    enter(P, "img"); row(P, "bed.png").locator(".cfg-row__main").click(); P.pg.wait_for_selector(".screen--viewer"); P.pg.wait_for_timeout(400)
    P.pg.locator(".viewer-actions button:has-text('Scarica')").click(); P.pg.wait_for_timeout(300)
    ok("app: image download goes to the bridge", saved(P)[-1] == ["/server/files/config/img/bed.png", "bed.png"], saved(P))
    P.pg.locator(".viewer-bar button").first.click(); P.pg.wait_for_timeout(300)
    card(P).locator("button:has-text('Nuovo')").click(); P.pg.wait_for_selector(".oui-menu")
    it = P.pg.locator(".oui-menu__item", has_text="Carica file")
    ok("app 3: upload still enabled", it.is_enabled() and "Dal dispositivo" in it.inner_text(), it.inner_text())
    ok("app: no page errors", not [e for e in P.errors if "pageerror" in e], P.errors[:3])
    P.close()

    # ---------------------------------------------------------------- older apps: told to update, nothing happens silently
    for label, extra in (("app without marker", ""), ("app KlippEyeApp/2", " KlippEyeApp/2")):
        P = fresh(init=ua(extra))
        open_menu(P, "printer.cfg"); pick(P, "Scarica")
        ok(label + ": config download explains", "aggiornala" in toast(P) and len(P.downloads) == 0, toast(P))
        P.pg.wait_for_timeout(300)
        log_download(P, "klippy.log")
        ok(label + ": log download explains, nothing downloaded", "aggiornala" in toast(P) and len(P.downloads) == 0 and len(P.ctx.pages) == 1, (toast(P), len(P.downloads)))
        if extra:
            card(P).locator("button:has-text('Nuovo')").click(); P.pg.wait_for_selector(".oui-menu")
            it = P.pg.locator(".oui-menu__item", has_text="Carica file")
            ok(label + ": upload still enabled", it.is_enabled(), it.inner_text())
        P.close()

    b.close()
print("\nFAILS:", FAILS or "none")
sys.exit(1 if FAILS else 0)
