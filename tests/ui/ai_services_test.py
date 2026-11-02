"""Release 1.27.0 (roadmap 6a part 3): the AI services (app/59l-ai-services.js). Settings → AI monitor → The AI service: the
service and the model of the monitor (the models read from the service, those that see pictures first), the keys of every
service; the gear of the System logs card: the service and model of the logs, at the top of the card. Against the mock
backend, which applies the same rules as backend/ai_services.py.
Usage: ai_services_test.py <html> <outdir> <port>"""
import json
import os
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright
from lib import *

html, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(out, exist_ok=True)
mock = Mock(html, port)
import atexit
atexit.register(mock.stop)
FAILS = []
CUR = [None]


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[:700]) if (extra != "" and not cond) else ""), flush=True)


def state():
    return json.loads(urllib.request.urlopen(mock.base + "/__mock/state").read())


def wait_until(fn, timeout=5.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        CUR[0].pg.wait_for_timeout(int(step * 1000))
    try:
        return bool(fn())
    except Exception:
        return False


def fresh(b, w=390, h=844, tab="home", **st):
    mock.reset()
    mock.set(**st)
    P = Page(b, mock, w, h)
    CUR[0] = P
    P.goto(tab, 1400)
    return P


def open_ai_page(P):
    P.pg.click('button[aria-label="Impostazioni"]')
    P.pg.wait_for_selector(".drawer")
    P.settle(450)
    P.pg.click('.set-entry[data-page="ai"]')
    P.settle(900)


def body(P):
    return P.pg.locator(".drawer__body").inner_text()


def overflow(P, sel=".drawer__body"):
    return P.pg.evaluate("(s) => { const d = document.querySelector(s); return d.scrollWidth - d.clientWidth; }", sel)


GROQ = "gsk_" + "x" * 40 + "AB12"
GEMINI = "AIzaSy" + "g" * 33

with sync_playwright() as p:
    b = p.chromium.launch()

    # --- the monitor's service and model
    P = fresh(b)
    open_ai_page(P)
    use = P.pg.locator('[data-ai-use="monitor"]')
    ok("AI monitor → The AI service: the service and the model of the monitor", wait_until(lambda: use.count() == 1) and "Servizio per il monitor" in use.inner_text() and "Modello per il monitor" in use.inner_text(), body(P)[-900:])
    ok("... it says what is in use (Groq, its default model for pictures)", "In uso: Groq • qwen/qwen3.8-27b" in body(P), body(P)[-900:])
    ok("... the old free-text model of Monitor thresholds is gone from this page", "Modello IA (facoltativo)" not in body(P))
    model = P.pg.locator('[data-ai-model="monitor"]')
    ok("the models are read from the service (Groq)", wait_until(lambda: "groq" in state()["ai_model_reads"]) and wait_until(lambda: "3 modelli di Groq" in use.inner_text()), use.inner_text())
    groups = P.pg.evaluate("() => [...document.querySelectorAll('[data-ai-model=\"monitor\"] optgroup')].map(g => g.label + ':' + [...g.children].map(o => o.value).join(','))")
    ok("... those that see pictures first, then the unknown ones, then text only", groups == ["Vedono le immagini:qwen/qwen3.8-27b", "Non si sa se vedono le immagini:openai/gpt-oss-20b", "Solo testo (non per il monitor):llama-3.1-8b-instant"], groups)
    first = P.pg.evaluate("() => document.querySelector('[data-ai-model=\"monitor\"] option').textContent")
    ok("... and the first choice is the default, named", first == "Predefinito: qwen/qwen3.8-27b", first)
    model.select_option("llama-3.1-8b-instant")
    ok("choosing a model saves it for the monitor only", wait_until(lambda: {"monitor": {"provider": "groq", "model": "llama-3.1-8b-instant"}} in state()["ai_posts"]), state()["ai_posts"])
    ok("... a text-only model: the page says the monitor needs one that sees pictures", wait_until(lambda: "non vede le immagini" in use.inner_text()), use.inner_text())
    ok("... the logs keep their own (the default of Groq for text)", state()["ai_cfg"]["logs"]["model"] == "" and state()["ai_cfg"]["monitor"]["model"] == "llama-3.1-8b-instant", state()["ai_cfg"])
    model.select_option("__other__")
    P.pg.fill('[data-ai-model-typed="monitor"]', "qwen/qwen-nuovo-vl")
    P.pg.locator('[data-ai-use="monitor"] button', has_text="Usalo").click()
    ok("«Un altro modello»: a name typed by hand", wait_until(lambda: {"monitor": {"provider": "groq", "model": "qwen/qwen-nuovo-vl"}} in state()["ai_posts"]) and wait_until(lambda: model.input_value() == "qwen/qwen-nuovo-vl"), state()["ai_posts"][-1:])
    P.pg.screenshot(path=os.path.join(out, "01_monitor.png"))

    # --- the keys
    keys = P.pg.locator("[data-ai-keys]")
    ok("the keys: one list, folded when a key is saved, says how many", keys.count() == 1 and keys.get_attribute("open") is None and "Chiavi dei servizi IA (1 salvata)" in keys.inner_text(), keys.inner_text()[:200] if keys.count() else "")
    keys.locator("summary").click()
    P.settle(300)
    groq = P.pg.locator('[data-ai-key-row="groq"]')
    gemini = P.pg.locator('[data-ai-key-row="gemini"]')
    ok("... every service: Groq with its key (only the end shown), Gemini without, a free plan marked", "chiave salvata, finisce con …AB12" in groq.inner_text() and GROQ not in P.pg.content() and "nessuna chiave" in gemini.inner_text() and "piano gratuito" in gemini.inner_text(), groq.inner_text() + " | " + gemini.inner_text())
    ok("... with the page where to get a key", P.pg.locator('[data-ai-key-url="gemini"]').get_attribute("href") == "https://aistudio.google.com/apikey")
    ok("... and the services of the list: Groq, Gemini, OpenAI, Anthropic, Mistral, OpenRouter... and another OpenAI-compatible one", P.pg.locator("[data-ai-key-row]").count() == 10 and P.pg.locator('[data-ai-key-row="anthropic"]').count() == 1 and P.pg.locator('[data-ai-key-row="custom"]').count() == 1)
    gemini.locator('[data-ai-key-edit="gemini"]').click()
    P.pg.fill('[data-ai-key-input="gemini"]', GEMINI)
    P.pg.click('[data-ai-key-save="gemini"]')
    ok("a key for Gemini is saved for that service", wait_until(lambda: {"key": {"provider": "gemini", "api_key": GEMINI}} in state()["ai_posts"]) and wait_until(lambda: "finisce con …gggg" in gemini.inner_text()), gemini.inner_text())
    ok("... the list says 2 saved", wait_until(lambda: "(2 salvate)" in keys.inner_text()))
    P.pg.select_option('[data-ai-service="monitor"]', "gemini")
    ok("the monitor moves to Gemini (its default model)", wait_until(lambda: {"monitor": {"provider": "gemini"}} in state()["ai_posts"]) and wait_until(lambda: "In uso: Google Gemini • gemini-3.8-flash" in body(P)), body(P)[-1200:])
    ok("... and the models of Gemini are read", wait_until(lambda: "gemini" in state()["ai_model_reads"]) and wait_until(lambda: "2 modelli di Google Gemini" in use.inner_text()), use.inner_text())
    groq.locator('[data-ai-key-delete="groq"]').click()
    P.pg.click('[data-ai-key-confirm="groq"]')
    ok("deleting the Groq key asks first, then deletes it", wait_until(lambda: {"key": {"provider": "groq", "delete": True}} in state()["ai_posts"]) and wait_until(lambda: "nessuna chiave" in groq.inner_text()), groq.inner_text())
    ok("... the logs, which used Groq, move to the service that still has a key", state()["ai_cfg"]["logs"]["provider"] == "gemini", state()["ai_cfg"])
    ok("no horizontal scrolling (390 px)", overflow(P) <= 0, overflow(P))
    P.pg.screenshot(path=os.path.join(out, "02_keys.png"), full_page=False)
    ok("no JavaScript error", P.errors == [], P.errors)
    P.ctx.close()

    # --- no key at all
    P = fresh(b, ai_key_ok=False)
    open_ai_page(P)
    ok("no key: the page says the monitor cannot judge, and names the free services", wait_until(lambda: "Nessuna chiave IA" in body(P)) and "Google Gemini" in body(P), body(P)[-700:])
    ok("... the list of the keys is open", P.pg.locator("[data-ai-keys]").get_attribute("open") is not None)
    P.pg.locator('[data-ai-key-edit="groq"]').click()
    P.pg.fill('[data-ai-key-input="groq"]', "corta")
    P.pg.click('[data-ai-key-save="groq"]')
    ok("a key too short is not sent", "Chiave troppo corta" in body(P) and state()["ai_posts"] == [], body(P)[-300:])
    P.pg.fill('[data-ai-key-input="groq"]', GROQ)
    P.pg.click('[data-ai-key-save="groq"]')
    ok("the first key saved is used for the monitor and the logs", wait_until(lambda: (state()["ai_cfg"] or {}).get("monitor", {}).get("provider") == "groq" and state()["ai_cfg"]["logs"]["provider"] == "groq") and wait_until(lambda: "In uso: Groq" in body(P)), state()["ai_cfg"])
    P.ctx.close()

    # --- the models cannot be read
    P = fresh(b, ai_models_fail="groq")
    open_ai_page(P)
    ok("a key the service refuses: the page says the list could not be read, with the service's words", wait_until(lambda: P.pg.locator("[data-ai-models-error]").count() == 1) and "Invalid API Key" in P.pg.locator("[data-ai-models-error]").inner_text(), body(P)[-500:])
    P.ctx.close()

    # --- an older backend
    P = fresh(b, brain="old")
    open_ai_page(P)
    ok("a backend before 1.27: 'update KlippEye'", wait_until(lambda: "aggiorna KlippEye per scegliere il servizio e il modello IA" in body(P)), body(P)[-500:])
    P.ctx.close()

    # --- the logs: the gear opens their AI settings at the top of the card
    P = fresh(b, tab="config")
    gear = P.pg.locator("[data-logs-gear]")
    ok("System logs: the gear is there", wait_until(lambda: gear.count() == 1), "")
    gear.click()
    P.settle(600)
    panel = P.pg.locator("[data-logs-settings]")
    ok("... it opens the AI settings of the logs", panel.count() == 1 and "Servizio per i log" in panel.inner_text() and "Modello per i log" in panel.inner_text(), panel.inner_text()[:400] if panel.count() else "")
    where = P.pg.evaluate("""() => { const g = document.querySelector('[data-logs-gear]'); const head = document.querySelector('.logs-analysis__head');
        const s = document.querySelector('[data-logs-settings]').getBoundingClientRect(); const r = document.querySelector('.logs-result').getBoundingClientRect();
        return { inHead: head.contains(g), underHead: s.top >= head.getBoundingClientRect().bottom - 1, aboveResult: s.bottom <= r.top + 1 }; }""")
    ok("... the gear is next to «Analisi errori e suggerimenti»; the settings open right under it, above the result", where == {"inHead": True, "underHead": True, "aboveResult": True}, where)
    ok("... and tapping the gear does not fold the analysis", "is-collapsed" not in (P.pg.locator(".logs-analysis__toggle").get_attribute("class") or ""))
    ok("... with the default text model of Groq", wait_until(lambda: "In uso: Groq • openai/gpt-oss-20b" in panel.inner_text()), panel.inner_text()[:400])
    P.pg.locator('[data-ai-model="logs"]').select_option("openai/gpt-oss-20b")
    ok("choosing the model of the logs saves it for the logs only", wait_until(lambda: {"logs": {"provider": "groq", "model": "openai/gpt-oss-20b"}} in state()["ai_posts"]) and state()["ai_cfg"]["monitor"]["model"] == "", state()["ai_cfg"])
    P.pg.screenshot(path=os.path.join(out, "03_logs.png"))
    ok("no horizontal scrolling on the page", P.pg.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0)
    gear.click()
    P.settle(300)
    ok("the gear closes it again", panel.count() == 0)
    ok("no JavaScript error", P.errors == [], P.errors)
    P.ctx.close()

    P = fresh(b, tab="config", ai_key_ok=False)
    P.pg.locator("button", has_text="Analizza automaticamente").click()
    ok("an analysis without a key: the card says so and opens the AI settings by itself", wait_until(lambda: P.pg.locator("[data-logs-key]").count() == 1 and P.pg.locator("[data-logs-settings]").count() == 1, 6)
       and "ingranaggio accanto ad «Analisi errori e suggerimenti»" in P.pg.locator("[data-logs-key]").inner_text(), P.pg.locator(".logs-result").inner_text()[:300])
    P.ctx.close()

    # --- 360 px
    P = fresh(b, w=360, h=740)
    open_ai_page(P)
    P.pg.locator("[data-ai-keys] summary").click()
    P.pg.locator('[data-ai-key-edit="custom"]').click()
    P.settle(300)
    ok("360 px: no horizontal scrolling, also with the address of another service open", overflow(P) <= 0, overflow(P))
    P.pg.fill("[data-ai-base]", "http://192.168.1.20:11434/v1")
    P.pg.click('[data-ai-key-save="custom"]')
    ok("... the address of an OpenAI-compatible server is saved (no key needed)", wait_until(lambda: {"custom_base": "http://192.168.1.20:11434/v1"} in state()["ai_posts"]) and wait_until(lambda: "192.168.1.20" in P.pg.locator('[data-ai-key-row="custom"]').inner_text()), state()["ai_posts"])
    P.ctx.close()
    b.close()

print("FAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
