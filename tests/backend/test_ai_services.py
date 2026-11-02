"""Release 1.27.0: backend/ai_services.py (the AI services, their keys and models) and its use by the backend: /api/ai/config,
/api/ai/models, the logs analysis, the monitor and «Analyse the print» each with their own service and model. No network:
requests.get / requests.post are replaced by fakes that record what was asked."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import ai_services as ai  # noqa: E402
import requests  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   -> " + str(extra)[:600]) if (extra != "" and not cond) else ""), flush=True)


class Resp:
    def __init__(self, status=200, data=None, text=None, headers=None):
        self.status_code, self.ok = status, 200 <= status < 300
        self._data = data
        self.text = text if text is not None else json.dumps(data)
        self.headers = headers or {}

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


CALLS = []


def fake_post(replies):
    replies = list(replies)

    def post(url, headers=None, json=None, timeout=None):
        CALLS.append({"url": url, "headers": headers, "json": json})
        return replies.pop(0) if replies else Resp(200, {"choices": [{"message": {"content": "ok"}}]})
    return post


GOT = []


def fake_get(reply):
    def get(url, headers=None, timeout=None):
        GOT.append({"url": url, "headers": headers})
        return reply
    return get


print("== ai_services: the settings")
old = ai.normalize({"api_key": "gsk_" + "a" * 40, "provider": "groq", "model": "gpt-4o-mini"})
check("ai.json of before 1.27: that key for that service, used for logs and monitor; the gpt-4o-mini written for every service is dropped",
      old["keys"] == {"groq": "gsk_" + "a" * 40} and old["logs"] == {"provider": "groq", "model": ""} and old["monitor"] == {"provider": "groq", "model": ""}, old)
check("... OpenAI keeps its gpt-4o-mini", ai.normalize({"api_key": "sk-" + "b" * 40, "provider": "openai", "model": "gpt-4o-mini"})["logs"]["model"] == "gpt-4o-mini")
check("... the old names: llama -> meta, an unknown service is dropped", ai.normalize({"api_key": "LLM" + "c" * 30, "provider": "llama"})["keys"] == {"meta": "LLM" + "c" * 30}
      and ai.normalize({"keys": {"nobody": "x" * 30}})["keys"] == {})
check("nothing saved: no service for either use", ai.normalize({}) == {"version": 2, "keys": {}, "custom_base": "", "logs": {"provider": "", "model": ""}, "monitor": {"provider": "", "model": ""}})
check("which service a key belongs to, from how it starts", [ai.guess_provider(k) for k in ("sk-ant-x", "sk-or-x", "sk-x", "gsk_x", "AIzax", "LLMx", "fw_x", "zzz")]
      == ["anthropic", "openrouter", "openai", "groq", "gemini", "meta", "fireworks", "groq"])

cfg, err = ai.apply({}, {"key": {"provider": "gemini", "api_key": "AIza" + "g" * 35}})
check("a first key: saved for its service and used for both uses", err is None and cfg["keys"] == {"gemini": "AIza" + "g" * 35} and cfg["logs"]["provider"] == "gemini" and cfg["monitor"]["provider"] == "gemini", cfg)
cfg, err = ai.apply(cfg, {"key": {"provider": "groq", "api_key": "gsk_" + "a" * 40}})
check("a second key does not move the uses", cfg["logs"]["provider"] == "gemini" and cfg["monitor"]["provider"] == "gemini" and set(cfg["keys"]) == {"gemini", "groq"})
cfg, err = ai.apply(cfg, {"logs": {"provider": "groq", "model": "openai/gpt-oss-20b"}, "monitor": {"model": "gemini-3.8-flash-lite"}})
check("each use its own service and model", cfg["logs"] == {"provider": "groq", "model": "openai/gpt-oss-20b"} and cfg["monitor"] == {"provider": "gemini", "model": "gemini-3.8-flash-lite"}, cfg)
cfg2, _ = ai.apply(cfg, {"monitor": {"provider": "groq"}})
check("another service without a model: its default", cfg2["monitor"] == {"provider": "groq", "model": ""})
cfg3, _ = ai.apply(cfg, {"key": {"provider": "gemini", "delete": True}})
check("deleting a key: the use that had it moves to a service that still has one", "gemini" not in cfg3["keys"] and cfg3["monitor"] == {"provider": "groq", "model": ""} and cfg3["logs"]["provider"] == "groq", cfg3)
check("bad values are refused", [ai.apply(cfg, b)[1] for b in ({"key": {"provider": "groq", "api_key": "short"}}, {"key": {"provider": "nobody", "api_key": "x" * 30}},
                                                                {"logs": {"model": "bad model name!"}}, {"custom_base": "ftp://x"}, {"api_key": "x"})]
      == ["key_short", "unknown", "bad_model", "bad_base", "key_short"])
legacy, _ = ai.apply(cfg, {"api_key": "sk-" + "o" * 40})
check("the old way ({api_key}): the key goes to the service it looks like, for both uses", legacy["keys"]["openai"] == "sk-" + "o" * 40 and legacy["logs"]["provider"] == "openai" and legacy["monitor"]["provider"] == "openai")
check("the old way ({delete: true}): every key goes", ai.apply(cfg, {"delete": True})[0]["keys"] == {})
custom, err = ai.apply({}, {"custom_base": "http://192.168.1.20:11434/v1/", "monitor": {"provider": "custom", "model": "llava"}})
check("another OpenAI-compatible server: an address, no key needed", err is None and custom["custom_base"] == "http://192.168.1.20:11434/v1"
      and ai.resolve(custom, "monitor")["endpoint"] == "http://192.168.1.20:11434/v1/chat/completions" and ai.resolve(custom, "monitor")["key"] == "", custom)

t = ai.resolve(cfg, "logs")
check("resolve: address, key and model of a use", t["endpoint"] == "https://api.groq.com/openai/v1/chat/completions" and t["model"] == "openai/gpt-oss-20b" and t["key"].startswith("gsk_"), t)
check("... the monitor's default model of a service, and the old model of Monitor thresholds when none is chosen",
      ai.resolve(cfg2, "monitor")["model"] == "qwen/qwen3.8-27b" and ai.resolve(cfg2, "monitor", "mio/modello")["model"] == "mio/modello" and ai.resolve(cfg, "monitor", "mio/modello")["model"] == "gemini-3.8-flash-lite")
try:
    ai.resolve({"keys": {"groq": "gsk_" + "a" * 40}, "monitor": {"provider": "openai"}}, "monitor")
    check("a service without its key: AiError no_key", False)
except ai.AiError as error:
    check("a service without its key: AiError no_key", error.code == "no_key")

s = ai.summary(cfg)
check("summary: never a whole key, only its end; every service with its page for the keys", "a" * 40 not in json.dumps(s) and [x["key_preview"] for x in s["services"] if x["id"] == "groq"] == ["…aaaa"]
      and len(s["services"]) == len(ai.ORDER) and all(x["key_url"] or x["id"] == "custom" for x in s["services"]), s)
check("... the two uses with their default model and whether they can be used", s["logs"] == {"provider": "groq", "model": "openai/gpt-oss-20b", "default_model": "openai/gpt-oss-20b", "usable": True}
      and s["monitor"]["usable"] and s["configured"] and s["provider"] == "groq")

print("== ai_services: the models of a service")
requests.get = fake_get(Resp(200, {"data": [{"id": "qwen/qwen3.8-27b"}, {"id": "whisper-large-v3"}, {"id": "openai/gpt-oss-20b"}, {"id": "llama-3.1-8b-instant"},
                                            {"id": "meta-llama/llama-prompt-guard-2-86m"}, {"id": "playai-tts"}, {"id": "old", "active": False}]}))
models = ai.list_models(cfg, "groq", now=1000)
check("the list read from the service with its key, chat models only, sorted", [m["id"] for m in models] == ["llama-3.1-8b-instant", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
      and GOT[-1]["url"] == "https://api.groq.com/openai/v1/models" and GOT[-1]["headers"]["Authorization"] == "Bearer gsk_" + "a" * 40, (models, GOT[-1:]))
check("... the ones known to see pictures are marked", {m["id"]: m["vision"] for m in models} == {"llama-3.1-8b-instant": None, "openai/gpt-oss-20b": None, "qwen/qwen3.8-27b": True})
ai.list_models(cfg, "groq", now=1100)
check("... kept 10 minutes (no second request)", len(GOT) == 1)
ai.list_models(cfg, "groq", now=1000 + ai.MODELS_TTL_S + 1)
check("... then read again", len(GOT) == 2)
requests.get = fake_get(Resp(200, {"data": [{"id": "meta-llama/llama-4-scout", "architecture": {"input_modalities": ["text", "image"]}}, {"id": "deepseek/r1", "architecture": {"input_modalities": ["text"]}}]}))
cfg_or, _ = ai.apply({}, {"key": {"provider": "openrouter", "api_key": "sk-or-" + "r" * 40}})
check("OpenRouter says which models see pictures", {m["id"]: m["vision"] for m in ai.list_models(cfg_or, "openrouter")} == {"meta-llama/llama-4-scout": True, "deepseek/r1": False})
requests.get = fake_get(Resp(200, {"data": [{"id": "models/gemini-3.8-flash"}, {"id": "models/gemini-2.5-flash-image"}, {"id": "models/gemini-embedding-001"}]}))
check("Gemini: 'models/' taken away, image makers and embeddings left out", [m["id"] for m in ai.list_models(cfg, "gemini")] == ["gemini-3.8-flash"])
requests.get = fake_get(Resp(200, {"data": [{"id": "claude-haiku-5-5", "type": "model"}]}))
cfg_an, _ = ai.apply({}, {"key": {"provider": "anthropic", "api_key": "sk-ant-" + "z" * 40}})
ai.list_models(cfg_an, "anthropic")
check("Anthropic: its own headers too (x-api-key, anthropic-version)", GOT[-1]["headers"].get("x-api-key") == "sk-ant-" + "z" * 40 and GOT[-1]["headers"].get("anthropic-version"))
requests.get = fake_get(Resp(401, {"error": {"message": "Invalid API Key in org_ABC123"}}))
try:
    ai.list_models(cfg_or, "openrouter", now=10 ** 10)
    check("a refused key: AiError with the service's words", False)
except ai.AiError as error:
    check("a refused key: AiError with the service's words (no account id)", error.code == "http_401" and str(error) == "Invalid API Key in org_…", str(error))

print("== ai_services: a request")
del CALLS[:]
requests.post = fake_post([Resp(200, {"choices": [{"message": {"content": "{}"}}]})])
ai.chat(ai.resolve(cfg2, "monitor"), [{"role": "user", "content": "x"}], temperature=0.1, max_tokens=900, json_mode=True)
check("a request: model, temperature, JSON mode, the key", CALLS[-1]["json"]["model"] == "qwen/qwen3.8-27b" and CALLS[-1]["json"]["temperature"] == 0.1
      and CALLS[-1]["json"]["response_format"] == {"type": "json_object"} and CALLS[-1]["headers"]["Authorization"].startswith("Bearer gsk_"), CALLS[-1])
ai.chat(ai.resolve(cfg_an, "monitor"), [{"role": "user", "content": "x"}], temperature=0.1, json_mode=True)
check("Anthropic: no JSON mode and no temperature (its OpenAI layer refuses them)", "response_format" not in CALLS[-1]["json"] and "temperature" not in CALLS[-1]["json"]
      and CALLS[-1]["url"] == "https://api.anthropic.com/v1/chat/completions", CALLS[-1]["json"])
del CALLS[:]
requests.post = fake_post([Resp(400, {"error": {"message": "response_format json_object is not supported"}}), Resp(200, {"choices": [{"message": {"content": "{}"}}]})])
r = ai.chat(ai.resolve(cfg2, "monitor"), [{"role": "user", "content": "x"}], temperature=0.1, json_mode=True)
check("a service that refuses the JSON mode is asked once more without it", r.ok and len(CALLS) == 2 and "response_format" not in CALLS[1]["json"], CALLS)
del CALLS[:]
requests.post = fake_post([Resp(400, {"error": {"message": "two images not allowed"}})])
r = ai.chat(ai.resolve(cfg2, "monitor"), [{"role": "user", "content": "x"}], temperature=0.1, json_mode=True)
check("... any other refusal is not repeated (the monitor tries one picture itself)", not r.ok and len(CALLS) == 1)
check("the answer's text, also when it comes in parts", ai.answer_text(Resp(200, {"choices": [{"message": {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}}]})) == "ab")

print("== ai_precision: the AI's response against the real print")
import ai_precision as ap  # noqa: E402
A = [{"id": "1", "action": "PAUSE", "confidence": 85, "label": "right"}, {"id": "2", "action": "PAUSE", "confidence": 72, "label": "false"},
     {"id": "3", "action": "CONTINUE", "original_action": "PAUSE", "confidence": 60, "label": "right"}, {"id": "4", "action": "CONTINUE", "confidence": 10, "label": "false"},
     {"id": "5", "outcome": "AI error 429", "label": "right"}, {"id": "6", "action": "PAUSE", "confidence": 90}]
p = ap.precision(A, 70)
check("the four cases: stop right, false stop, problem missed, continue right; an AI error apart; an unjudged alarm left out",
      (p["judged"], p["no_verdict"], p["stop_right"], p["stop_wrong"], p["continue_wrong"], p["continue_right"]) == (4, 1, 1, 1, 1, 1) and p["correct_pct"] == 50 and not p["enough"], p)
rows = {r["threshold"]: (r["false_stops"], r["missed"]) for r in p["thresholds"]}
check("each minimum confidence on the same alarms (a stop kept when proposed and confident enough)", rows == {50: (1, 0), 60: (1, 0), 70: (1, 1), 80: (0, 1), 90: (0, 2), 95: (0, 2)}, rows)
check("the advice: the value that misses fewest, then fewest false stops, nearest to the one in use", p["advice"] == {"kind": "lower", "threshold": 60, "false_stops": 1, "missed": 0}, p["advice"])
check("... keep when the one in use is as good", ap.precision(A, 60)["advice"]["kind"] == "keep" and ap.precision([], 70)["advice"] is None)
check("a threshold in use outside the list is added to it", 75 in [r["threshold"] for r in ap.precision(A, 75)["thresholds"]])
m = ap.merge([{"id": "a", "action": "PAUSE"}, {"id": "b", "action": "PAUSE", "label": "false"}], [{"alerts": [{"id": "a", "label": "right", "t": 5}, {"id": "b", "label": "right"}, {"id": "c", "label": "false"}]}])
m = {x["id"]: x for x in m}
check("history and recordings once each: the history's label wins when it has one, else the recording's", m["a"]["label"] == "right" and m["a"]["t"] == 5 and m["b"]["label"] == "false" and m["c"]["label"] == "false" and len(m) == 3, m)

print("== the backend")
sys.path.insert(0, HERE)
data = tempfile.mkdtemp()
os.environ["KLIPPEYE_DATA"] = data
json.dump({"values": {"enabled": False}}, open(os.path.join(data, "brain.json"), "w"))
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("kb_ai", os.path.join(ROOT, "backend", "klippeye_backend.py"))
bk = importlib.util.module_from_spec(spec)
real_get, real_post = requests.get, requests.post
sys.modules["kb_ai"] = bk
spec.loader.exec_module(bk)
bk.AI_CONFIG_PATH = os.path.join(data, "ai.json")
client = bk.app.test_client()
g = client.get("/api/ai/config").get_json()
check("GET /api/ai/config with nothing saved: every service, no use, says how to start", g["configured"] is False and len(g["services"]) == len(ai.ORDER) and "message" in g, g)
r = client.post("/api/ai/config", json={"key": {"provider": "groq", "api_key": "gsk_" + "k" * 40}})
check("POST a key: saved in ai.json, mode 600, the answer is the summary", r.status_code == 200 and r.get_json()["logs"]["provider"] == "groq" and oct(os.stat(bk.AI_CONFIG_PATH).st_mode & 0o777) == "0o600"
      and json.load(open(bk.AI_CONFIG_PATH))["keys"]["groq"] == "gsk_" + "k" * 40, r.get_json())
check("POST bad values: 400 with a reason", client.post("/api/ai/config", json={"key": {"provider": "groq", "api_key": "x"}}).status_code == 400
      and client.post("/api/ai/config", json={"logs": {"model": "no spaces allowed"}}).status_code == 400)
bk.set_brain_config({"ai_model": "vecchio/modello"})
check("the model chosen before 1.27 in Monitor thresholds is shown as the monitor's", client.get("/api/ai/config").get_json()["monitor"]["model"] == "vecchio/modello")
client.post("/api/ai/config", json={"monitor": {"provider": "groq", "model": ""}})
check("... choosing the monitor's model here clears it", bk.detector.ai_model == "" and client.get("/api/ai/config").get_json()["monitor"]["model"] == "")
requests.get = fake_get(Resp(200, {"data": [{"id": "qwen/qwen3.8-27b"}]}))
ai._models_cache.clear()
m = client.get("/api/ai/models?provider=groq")
check("GET /api/ai/models: the models of the service", m.status_code == 200 and m.get_json()["models"] == [{"id": "qwen/qwen3.8-27b", "vision": True}], m.get_json())
check("... of a service without a key: 400 no_key", client.get("/api/ai/models?provider=gemini").get_json()["code"] == "no_key")
requests.get = fake_get(Resp(401, {"error": {"message": "Invalid API Key"}}))
ai._models_cache.clear()
m = client.get("/api/ai/models?provider=groq")
check("... a refused key: 502 with the service's words", m.status_code == 502 and m.get_json()["error"] == "Invalid API Key", m.get_json())

client.post("/api/ai/config", json={"key": {"provider": "gemini", "api_key": "AIza" + "g" * 35}})
client.post("/api/ai/config", json={"logs": {"provider": "gemini", "model": "gemini-3.8-flash-lite"}})
del CALLS[:]
requests.post = fake_post([Resp(200, {"choices": [{"message": {"content": "## Conclusion\nall fine"}}]})])
logs_dir = os.path.join(data, "logs")
os.makedirs(logs_dir, exist_ok=True)
open(os.path.join(logs_dir, "klippy.log"), "w").write("Klipper state: Ready\n")
bk._logs_dir = lambda: logs_dir
a = client.post("/api/logs/analyze")
check("the logs are analysed by their own service and model (Gemini), the monitor keeps Groq", a.status_code == 200 and a.get_json()["provider"] == "gemini" and a.get_json()["model"] == "gemini-3.8-flash-lite"
      and CALLS[-1]["url"].startswith("https://generativelanguage.googleapis.com/") and CALLS[-1]["headers"]["Authorization"] == "Bearer AIza" + "g" * 35, (a.get_json(), CALLS[-1:]))
requests.post = fake_post([Resp(429, {"error": {"message": "quota exceeded"}})])
a = client.post("/api/logs/analyze")
check("... an error of the service comes back with its words", a.status_code == 500 and "quota exceeded" in a.get_json()["error"] and "Google Gemini" in a.get_json()["error"], a.get_json())
client.post("/api/ai/config", json={"key": {"provider": "gemini", "delete": True}})
client.post("/api/ai/config", json={"key": {"provider": "groq", "delete": True}})
a = client.post("/api/logs/analyze")
check("... without any key: 400 'API key not set' (the dashboard opens the AI settings)", a.status_code == 400 and "API key" in a.get_json()["error"] and a.get_json()["configured"] is False, a.get_json())
requests.get, requests.post = real_get, real_post

print("\n%d FAIL" % len(FAILS) if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
