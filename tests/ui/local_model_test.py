"""Release 1.106: the local model on Settings → AI monitor: none installed (it says the monitor works without, no switches),
KlippEye's model in use (version, last look, what it did, its switches, the way to its thresholds); its thresholds in their
own group on Monitor thresholds; 320 px. Release 1.107: the personal layer (off at first: only its switch; on: how many
examples, learn now, import / export / remove the imported ones). Against the mock.
Usage: local_model_test.py <html> <outdir> <port>"""
import json
import os
import sys
import urllib.request
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit
atexit.register(mock.stop)
FAILS = []


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def open_page(b, page, w=390, h=844, **st):
    mock.reset()
    mock.set(**st)
    P = Page(b, mock, w, h)
    P.goto("home", 1400)
    P.pg.locator(".header-btn--menu").click()
    P.pg.wait_for_selector(".drawer")
    P.settle(450)
    P.pg.click('.set-entry[data-page="%s"]' % page)
    P.settle(1200)
    return P


with sync_playwright() as p:
    b = p.chromium.launch()
    P = open_page(b, "ai")
    box = P.pg.locator("[data-local-model]")
    ok("no model installed: it says so, the monitor works without; no switches", box.count() == 1 and box.get_attribute("data-local-model") == "none"
       and "Nessun modello locale" in box.inner_text() and P.pg.locator('.set-switch:has-text("Usa il modello locale")').count() == 0, box.inner_text() if box.count() else "")
    P.close()

    model = {"available": True, "source": "base", "version": "20261120-1015", "threshold": 0.62, "size": 224,
             "last": {"score": 87.4, "checks": 120, "filtered": 9, "asked": 3}}
    P = open_page(b, "ai", local_model=model)
    box = P.pg.locator("[data-local-model]")
    page = P.pg.locator(".drawer__body").inner_text()
    ok("KlippEye's model in use: its version and last look", box.get_attribute("data-local-model") == "base" and "il modello di KlippEye" in box.inner_text()
       and "20261120-1015" in box.inner_text() and "87%" in box.inner_text(), box.inner_text())
    ok("... what it did, its three switches, the way to its thresholds", "allarmi tenuti lontano dall'IA online: 9" in page and "Usa il modello locale" in page
       and "Ferma col solo modello locale" in page and P.pg.locator('[data-go="detector"]').count() >= 1, page[-900:])
    P.shot(os.path.join(out, "local_model_ai.png"))
    P.pg.locator("[data-local-test]").click()
    P.settle(800)
    ok("1.124: «Try the local model now» on the AI monitor page: its score, its verdict, the views", "62,5%" in P.pg.locator("[data-local-try]").inner_text()
       and "in dubbio" in P.pg.locator("[data-local-try]").inner_text() and "sul pezzo" in P.pg.locator("[data-local-try]").inner_text(), P.pg.locator(".monitor-try").inner_text())
    P.pg.locator('[data-go="detector"]').last.click()
    P.settle(1000)
    page = P.pg.locator(".drawer__body").inner_text()
    ok("1.124: Monitor thresholds: «How watchful it is», Balanced chosen; the numbers folded under «Fine adjustments»",
       "QUANTO È ATTENTO" in page.upper() and P.pg.locator('.set-chips .is-selected').inner_text() == "Equilibrato" and "In dubbio da" not in page
       and P.pg.locator('[data-fine="closed"]').count() == 1, page[:900])
    P.pg.locator("[data-fine]").click()
    P.settle(600)
    page = P.pg.locator(".drawer__body").inner_text()
    ok("... opened: the group «Local model» with its three thresholds (the switches are not repeated)",
       "MODELLO LOCALE" in page.upper() and "In dubbio da" in page and "Sicuro da" in page and "Ogni quanto guarda da solo" in page and "Usa il modello locale" not in page, page[-1200:])
    doubt = P.pg.locator('.set-num:has(#set-num-local_doubt) .set-num__bounds').inner_text()
    sure = P.pg.locator('.set-num:has(#set-num-local_sure) .set-num__bounds').inner_text()
    ok("... «In doubt from» ends below «Sure from» (75% with 80%), «Sure from» starts above «In doubt from» (36%)", "75" in doubt and "36" in sure, (doubt, sure))
    P.pg.locator('.set-chips .oui-chip', has_text="Nota di più").first.click()
    P.settle(1600)
    sent = [c for c in state()["brain_cfg_log"] if "local_doubt" in c]
    ok("1.124: «Notices more»: OpenCV and the local model set together in one change",
       sent and sent[-1].get("local_doubt") == 25 and sent[-1].get("score_threshold") == 1.5 and sent[-1].get("trigger_count") == 2, sent[-1:])
    P.pg.fill("#set-num-sensitivity", "33")
    P.settle(1600)
    ok("... a number changed by hand: «Custom», the fine adjustments stay open", P.pg.locator('.set-chips .is-selected').inner_text() == "Personalizzato"
       and P.pg.locator("#set-num-sensitivity").count() == 1 and P.pg.locator("[data-fine='closed']").count() == 0)
    P.shot(os.path.join(out, "local_model_thresholds.png"))
    P.close()

    personal = {"enabled": False, "trained": False, "training": False, "error": "", "imported": [], "have": {"failed": 2, "fine": 8}, "needed": {"failed": 5, "fine": 20}}
    P = open_page(b, "ai", local_model=dict(model, personal=personal))
    switch = P.pg.locator('.set-switch:has-text("Impara dalle stampe di questa stampante")')
    ok("the personal layer: off at first, only its switch", switch.count() == 1 and P.pg.locator("[data-personal]").count() == 0
       and P.pg.locator("[data-personal-train]").count() == 0, P.pg.locator(".drawer__body").inner_text()[-800:])
    switch.click()
    P.settle(1500)
    status = P.pg.locator("[data-personal]")
    ok("... switched on: saved, and how many examples it still needs", any(c.get("personal_learning") is True for c in state()["brain_cfg_log"])
       and status.count() == 1 and status.get_attribute("data-personal") == "waiting" and "2 di 5" in status.inner_text() and "8 di 20" in status.inner_text(),
       status.inner_text() if status.count() else state()["brain_cfg_log"])
    P.pg.locator("[data-personal-train]").click()
    P.settle(1800)
    status = P.pg.locator("[data-personal]")
    ok("... «Learn now»: asked, then what it learned and how often it was right", {"train": True} in state()["personal_posts"]
       and status.get_attribute("data-personal") == "trained" and "31 esempi" in status.inner_text() and "94%" in status.inner_text(), status.inner_text())
    with P.pg.expect_download() as download:
        P.pg.locator("[data-personal-export]").click()
    ok("... «Export the examples»: a zip", download.value.suggested_filename.endswith(".zip"), download.value.suggested_filename)
    zip_path = os.path.join(out, "examples.zip")
    import zipfile
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("labels.json", json.dumps({"format": 1, "pictures": {}}))
    P.pg.locator("[data-personal-import] ~ input[type=file]").set_input_files(zip_path)
    P.settle(1800)
    posts = state()["personal_posts"]
    listed = P.pg.locator("[data-personal-imported]")
    ok("... «Import examples»: the file sent, the printer it came from listed", any(p.get("import") == "examples.zip" and p.get("bytes", 0) > 0 for p in posts)
       and listed.count() == 1 and "voron (40)" in listed.inner_text(), (posts, listed.inner_text() if listed.count() else ""))
    P.shot(os.path.join(out, "local_model_personal.png"))
    P.pg.locator("[data-personal-forget]").click()
    P.settle(1800)
    ok("... the imported ones removed", {"forget_imported": True} in state()["personal_posts"] and P.pg.locator("[data-personal-imported]").count() == 0)
    P.close()

    # 1.119: «Who judges the pictures»: the online AI (usual) or the local model alone
    P = open_page(b, "ai", local_model=model)
    judge = P.pg.locator("[data-judge]")
    ok("1.119: the online AI is the usual judge: its service and keys shown", judge.get_attribute("data-judge") == "online"
       and P.pg.locator("[data-ai-ready]").count() == 1 and "Chiedi all'IA online solo se il modello locale ha un dubbio" in P.pg.locator(".drawer__body").inner_text())
    P.pg.locator('.oui-chip:has-text("Solo il modello locale")').click()
    P.settle(1200)
    page = P.pg.locator(".drawer__body").inner_text()
    ok("... «Local model only»: saved (ai_online off), the service and its keys hidden, the switches about the online AI too",
       any(c.get("ai_online") is False for c in state()["brain_cfg_log"]) and P.pg.locator("[data-judge]").get_attribute("data-judge") == "local"
       and P.pg.locator("[data-ai-ready]").count() == 0 and "Chiedi all'IA online solo" not in page and "Ferma col solo modello locale" not in page
       and "Nessuna foto esce dal Raspberry" in page and "Usa il modello locale" in page, page[-1500:])
    P.shot(os.path.join(out, "local_only.png"))
    P.close()
    P = open_page(b, "ai")   # no local model installed
    P.pg.locator('.oui-chip:has-text("Solo il modello locale")').click()
    P.settle(1200)
    judge = P.pg.locator("[data-judge]")
    ok("... with no local model: a warning that nothing can judge", judge.get_attribute("data-judge") == "nobody"
       and "set-group__note--warn" in judge.get_attribute("class") and "non può giudicare nulla" in judge.inner_text(), judge.inner_text())
    P.close()

    P = open_page(b, "ai", 320, 700, local_model=dict(model, personal=dict(personal, enabled=True, trained=True, examples=31, failed=9, fine=22,
                                                                                          imported=[{"origin": "a", "printer": "a-printer-with-a-very-long-name", "pictures": 12}])))
    P.pg.locator('.set-switch:has-text("Impara dalle stampe di questa stampante")').click()
    P.settle(1200)
    wide = P.pg.evaluate("() => { const d = document.querySelector('.drawer__body'); return d.scrollWidth - d.clientWidth; }")
    ok("320 px: nothing sideways", wide <= 0, wide)
    P.close()
    b.close()

print("%d FAIL" % len(FAILS))
sys.exit(1 if FAILS else 0)
