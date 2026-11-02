"""
The AI services KlippEye can use (roadmap phase 6a, part 3, release 1.27.0).

Every service here speaks the OpenAI "chat completions" protocol (POST <base>/chat/completions, GET <base>/models), so one
way of calling covers them all; what differs is written in PROVIDERS (address, where to get a key, the models used when
none is chosen, a few quirks). "custom" is any other OpenAI-compatible server (a model on the home network, LM Studio,
Ollama...), with its own address and an optional key.

Two uses, each with its own service and model:
    logs     the analysis of the system logs (text only);
    monitor  the AI print monitor and «Analyse the print» (it must see pictures).

ai.json (data folder, mode 600: it holds passwords), version 2:
    {"version": 2, "keys": {"groq": "gsk_...", "gemini": "AIza..."},
     "logs": {"provider": "groq", "model": ""}, "monitor": {"provider": "gemini", "model": "gemini-3.8-flash"},
     "custom_base": "http://192.168.1.20:11434/v1"}
An empty model is the service's default. The file of before 1.27 ({"provider", "api_key", "model"}) is read as: that key
for that service, used for both, its model for the logs.
"""
import re
import time

import requests

PROVIDERS = {
    "groq": {"name": "Groq", "base": "https://api.groq.com/openai/v1", "key_url": "https://console.groq.com/keys", "prefix": "gsk_",
             "free": True, "logs": "openai/gpt-oss-20b", "monitor": "qwen/qwen3.8-27b"},
    "gemini": {"name": "Google Gemini", "base": "https://generativelanguage.googleapis.com/v1beta/openai", "key_url": "https://aistudio.google.com/apikey",
               "prefix": "AIza", "free": True, "logs": "gemini-3.8-flash", "monitor": "gemini-3.8-flash", "json_mode": False},
    "openai": {"name": "OpenAI", "base": "https://api.openai.com/v1", "key_url": "https://platform.openai.com/api-keys", "prefix": "sk-",
               "free": False, "logs": "gpt-4o-mini", "monitor": "gpt-4o-mini"},
    "anthropic": {"name": "Anthropic (Claude)", "base": "https://api.anthropic.com/v1", "key_url": "https://platform.claude.com/settings/keys",
                  "prefix": "sk-ant-", "free": False, "logs": "claude-haiku-5-5", "monitor": "claude-haiku-5-5",
                  "json_mode": False, "temperature": False},   # its OpenAI layer refuses json_object and a temperature below 1
    "mistral": {"name": "Mistral", "base": "https://api.mistral.ai/v1", "key_url": "https://console.mistral.ai/api-keys", "prefix": "",
                "free": True, "logs": "mistral-small-latest", "monitor": "mistral-small-latest"},
    "openrouter": {"name": "OpenRouter", "base": "https://openrouter.ai/api/v1", "key_url": "https://openrouter.ai/keys", "prefix": "sk-or-",
                   "free": True, "logs": "meta-llama/llama-3.3-70b-instruct", "monitor": "meta-llama/llama-4-scout-17b-16e-instruct",
                   "headers": {"HTTP-Referer": "https://klippeye.local", "X-Title": "KlippEye"}},
    "meta": {"name": "Meta Llama", "base": "https://api.llama.com/compat/v1", "key_url": "https://llama.developer.meta.com", "prefix": "LLM",
             "free": True, "logs": "Llama-4-Maverick-17B-128E-Instruct-FP8", "monitor": "Llama-4-Scout-17B-16E-Instruct"},
    "together": {"name": "Together AI", "base": "https://api.together.xyz/v1", "key_url": "https://api.together.ai/settings/api-keys", "prefix": "",
                 "free": False, "logs": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", "monitor": "meta-llama/Llama-4-Scout-17B-16E-Instruct"},
    "fireworks": {"name": "Fireworks AI", "base": "https://api.fireworks.ai/inference/v1", "key_url": "https://fireworks.ai/account/api-keys", "prefix": "fw_",
                  "free": False, "logs": "accounts/fireworks/models/llama-v3p3-70b-instruct", "monitor": "accounts/fireworks/models/llama4-scout-instruct-basic"},
    "custom": {"name": "Other (OpenAI-compatible)", "base": "", "key_url": "", "prefix": "", "free": True, "logs": "", "monitor": "", "key_optional": True},
}
ORDER = ["groq", "gemini", "openai", "anthropic", "mistral", "openrouter", "meta", "together", "fireworks", "custom"]
ALIASES = {"llama": "meta", "llama.com": "meta", "google": "gemini", "claude": "anthropic"}
USES = ("logs", "monitor")
KEY_RE = re.compile(r"^[A-Za-z0-9._~+/=:\-]{8,300}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9._:/@+\-]{1,120}$")
BASE_RE = re.compile(r"^https?://[A-Za-z0-9.\-\[\]:]+(/[A-Za-z0-9._~\-/]*)?$")
MODELS_TTL_S = 600
MODELS_TIMEOUT_S = 12

# the models list also has models that cannot chat: speech, embeddings, image making, moderation...
NOT_CHAT = re.compile(r"(whisper|tts|embed|guard|moderation|dall-e|imagen|image-|-image|audio|transcribe|realtime|rerank|playai|orpheus|"
                      r"veo|lyria|aqa|davinci|babbage|computer-use|omni-moderation|search-preview|sora|distil-whisper|prompt-guard)", re.I)
# models known to see pictures when the service does not say it
SEES = re.compile(r"(vision|[-/]vl\b|-vl-|gpt-4o|gpt-4\.1|gpt-5|\bo3\b|\bo4|gemini|claude|llama-4|llama4|scout|maverick|pixtral|"
                  r"mistral-(small|medium|large)|magistral|qwen[\w.-]*vl|qwen3\.[5-9]|qwen3\.8|gemma-3|gemma3|llava|grok-4|grok-2-vision|"
                  r"minicpm-v|moondream|internvl|phi-4-multimodal)", re.I)

_models_cache = {}  # (provider, base, key end) -> (time, list)


class AiError(Exception):
    """A setting that cannot be used (no key for the chosen service, a bad address): .code says which."""

    def __init__(self, code, text):
        Exception.__init__(self, text)
        self.code = code


def provider_id(name):
    name = str(name or "").strip().lower()
    name = ALIASES.get(name, name)
    return name if name in PROVIDERS else ("openai" if not name else name)


def guess_provider(key, fallback="groq"):
    """The service a key belongs to, from how it starts (sk-ant- before sk-or- before sk-)."""
    for pid in ("anthropic", "openrouter", "groq", "gemini", "meta", "fireworks", "openai"):
        prefix = PROVIDERS[pid]["prefix"]
        if prefix and str(key).startswith(prefix):
            return pid
    return fallback


def normalize(raw):
    """ai.json as it is on disk (either version) -> the version 2 shape. Never fails."""
    raw = raw if isinstance(raw, dict) else {}
    keys = {}
    if isinstance(raw.get("keys"), dict):
        for pid, key in raw["keys"].items():
            pid = provider_id(pid)
            if pid in PROVIDERS and isinstance(key, str) and key:
                keys[pid] = key
    legacy_key = raw.get("api_key") or raw.get("key")
    legacy_provider = provider_id(raw.get("provider"))
    if isinstance(legacy_key, str) and legacy_key and legacy_provider in PROVIDERS:
        keys.setdefault(legacy_provider, legacy_key)
    out = {"version": 2, "keys": keys, "custom_base": str(raw.get("custom_base") or "").strip().rstrip("/")}
    for use in USES:
        one = raw.get(use) if isinstance(raw.get(use), dict) else {}
        provider = provider_id(one.get("provider")) if one.get("provider") else (legacy_provider if legacy_key else "")
        model = str(one.get("model") or "")
        if not one and use == "logs" and legacy_key:
            model = str(raw.get("model") or "")
            if model == "gpt-4o-mini" and legacy_provider != "openai":
                model = ""   # the default written by releases before 1.27 for every service: only OpenAI has it
        out[use] = {"provider": provider if provider in PROVIDERS else "", "model": model if MODEL_RE.match(model) else ""}
    # a use without a service takes the first one with a key
    first = next((pid for pid in ORDER if pid in keys), "")
    for use in USES:
        if not out[use]["provider"]:
            out[use]["provider"] = first
    return out


def base_of(cfg, provider):
    return (cfg.get("custom_base") or "") if provider == "custom" else PROVIDERS[provider]["base"]


def resolve(cfg, use, fallback_model=""):
    """-> {provider, name, base, key, model, default_model} for one use. AiError when it cannot be used."""
    cfg = normalize(cfg)
    one = cfg[use]
    provider = one["provider"]
    if not provider:
        raise AiError("no_key", "no AI key")
    spec = PROVIDERS[provider]
    key = cfg["keys"].get(provider, "")
    if not key and not spec.get("key_optional"):
        raise AiError("no_key", "no key for %s" % spec["name"])
    base = base_of(cfg, provider)
    if not base:
        raise AiError("no_base", "no address for the OpenAI-compatible service")
    default = spec[use]
    model = one["model"] or fallback_model or default
    if not model:
        raise AiError("no_model", "choose a model for %s" % spec["name"])
    return {"provider": provider, "name": spec["name"], "base": base, "key": key, "model": model, "default_model": default,
            "endpoint": base + "/chat/completions"}


def headers_for(provider, key):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    if provider == "anthropic":
        headers["x-api-key"] = key
        headers["anthropic-version"] = "2023-06-01"
    headers.update(PROVIDERS[provider].get("headers") or {})
    return headers


def chat(target, messages, temperature=None, max_tokens=1000, json_mode=False, timeout=40):
    """One request to the service of `target` (from resolve). -> the requests Response. A service that refuses the JSON mode
    or the temperature (400) is asked once more without them."""
    spec = PROVIDERS[target["provider"]]
    payload = {"model": target["model"], "messages": messages, "max_tokens": max_tokens}
    if temperature is not None and spec.get("temperature", True):
        payload["temperature"] = temperature
    if json_mode and spec.get("json_mode", True):
        payload["response_format"] = {"type": "json_object"}
    headers = headers_for(target["provider"], target["key"])
    response = requests.post(target["endpoint"], headers=headers, json=payload, timeout=timeout)
    refused = (response.text or "").lower() if response.status_code == 400 else ""
    if refused and any(word in refused for word in ("response_format", "json", "temperature")) and ("response_format" in payload or "temperature" in payload):
        payload.pop("response_format", None)
        payload.pop("temperature", None)
        response = requests.post(target["endpoint"], headers=headers, json=payload, timeout=timeout)
    return response


def answer_text(response):
    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return str(data)[:2000]
    if isinstance(content, list):   # some services answer with parts
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""


def sees_pictures(model_id, info=None):
    """True / False when the service says it, else True when the name is of a model known to see pictures, else None."""
    info = info if isinstance(info, dict) else {}
    arch = info.get("architecture") if isinstance(info.get("architecture"), dict) else {}
    modalities = arch.get("input_modalities") or info.get("input_modalities")
    if isinstance(modalities, list):
        return "image" in modalities
    caps = info.get("capabilities") if isinstance(info.get("capabilities"), dict) else {}
    if "vision" in caps:
        return bool(caps.get("vision"))
    return True if SEES.search(model_id) else None


def list_models(cfg, provider, now=None):
    """The models of a service, read from it with the saved key: [{id, vision}] (vision: True, False or None = not known),
    chat models only, sorted. Kept 10 minutes. AiError when there is no key; requests errors pass through."""
    cfg = normalize(cfg)
    provider = provider_id(provider)
    if provider not in PROVIDERS:
        raise AiError("unknown", "unknown service")
    key = cfg["keys"].get(provider, "")
    if not key and not PROVIDERS[provider].get("key_optional"):
        raise AiError("no_key", "no key for %s" % PROVIDERS[provider]["name"])
    base = base_of(cfg, provider)
    if not base:
        raise AiError("no_base", "no address for the OpenAI-compatible service")
    now = time.time() if now is None else now
    cache_key = (provider, base, key[-6:])
    cached = _models_cache.get(cache_key)
    if cached and now - cached[0] < MODELS_TTL_S:
        return cached[1]
    response = requests.get(base + "/models", headers=headers_for(provider, key), timeout=MODELS_TIMEOUT_S)
    if not response.ok:
        raise AiError("http_%d" % response.status_code, error_detail(response) or ("HTTP %d" % response.status_code))
    data = response.json()
    rows = data.get("data") if isinstance(data, dict) else data
    if not isinstance(rows, list) and isinstance(data, dict):
        rows = data.get("models")
    models = {}
    for row in rows or []:
        info = row if isinstance(row, dict) else {"id": str(row)}
        model_id = str(info.get("id") or info.get("name") or "")
        if model_id.startswith("models/"):
            model_id = model_id[len("models/"):]
        if not model_id or not MODEL_RE.match(model_id) or NOT_CHAT.search(model_id):
            continue
        if info.get("active") is False:
            continue
        models[model_id] = {"id": model_id, "vision": sees_pictures(model_id, info)}
    result = sorted(models.values(), key=lambda m: m["id"].lower())
    _models_cache[cache_key] = (now, result)
    return result


def error_detail(response):
    """The service's own words about an error, without account ids."""
    text = ""
    try:
        data = response.json()
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, list) and error:
            error = error[0]
        text = error.get("message", "") if isinstance(error, dict) else str(error or (data.get("message", "") if isinstance(data, dict) else ""))
    except ValueError:
        text = response.text or ""
    text = re.sub(r"\b(org|user|proj)_[A-Za-z0-9]+", r"\1_…", str(text))
    return re.sub(r"\s+", " ", text).strip()[:300]


def summary(cfg):
    """What the dashboard may see: the services (with whether a key is saved and its last 4 characters, never the key),
    the two uses with their default models, and the legacy fields of before 1.27 (configured, provider, model, key_preview)."""
    cfg = normalize(cfg)
    services = []
    for pid in ORDER:
        spec = PROVIDERS[pid]
        key = cfg["keys"].get(pid, "")
        services.append({"id": pid, "name": spec["name"], "key_set": bool(key), "key_preview": ("…" + key[-4:]) if key else "",
                         "key_url": spec["key_url"], "free": spec["free"], "key_optional": bool(spec.get("key_optional")),
                         "defaults": {"logs": spec["logs"], "monitor": spec["monitor"]}})
    uses = {}
    for use in USES:
        one = cfg[use]
        spec = PROVIDERS.get(one["provider"]) if one["provider"] else None
        usable = bool(one["provider"]) and (bool(cfg["keys"].get(one["provider"])) or bool(spec and spec.get("key_optional")))
        uses[use] = {"provider": one["provider"], "model": one["model"], "default_model": spec[use] if spec else "", "usable": usable}
    logs = uses["logs"]
    return {"version": 2, "services": services, "logs": uses["logs"], "monitor": uses["monitor"], "custom_base": cfg["custom_base"],
            "configured": logs["usable"] or uses["monitor"]["usable"], "provider": logs["provider"] or uses["monitor"]["provider"],
            "model": logs["model"] or logs["default_model"],
            "key_preview": ("…" + cfg["keys"].get(logs["provider"], "")[-4:]) if cfg["keys"].get(logs["provider"]) else ""}


def apply(cfg, body):
    """A change from the dashboard -> (new cfg, None) or (None, error code). The body may carry:
        {"key": {"provider": "gemini", "api_key": "AIza..."}}      save a key (or {"provider", "delete": true})
        {"logs": {"provider": "groq", "model": ""}}                  the service and model of a use ("" = its default)
        {"monitor": {...}}, {"custom_base": "http://..."}
        {"api_key": "...", "provider": "groq"}                       before 1.27: that key, for the uses with no service
        {"delete": true}                                             before 1.27: every key
    """
    cfg = normalize(cfg)
    if body.get("delete") is True and "key" not in body:
        return normalize({}), None
    if "api_key" in body or "key" in body and isinstance(body.get("key"), str):
        key = str(body.get("api_key") or body.get("key") or "").strip()
        if len(key) < 20 or not KEY_RE.match(key):
            return None, "key_short"
        provider = provider_id(body.get("provider")) if body.get("provider") else guess_provider(key, cfg["logs"]["provider"] or "openai")
        if provider not in PROVIDERS:
            return None, "unknown"
        cfg["keys"][provider] = key
        model = str(body.get("model") or "")
        for use in USES:   # as before 1.27: one key for everything
            keep = cfg[use]["model"] if cfg[use]["provider"] == provider else ""
            cfg[use] = {"provider": provider, "model": model if use == "logs" and model and MODEL_RE.match(model) and model != "gpt-4o-mini" else keep}
        return cfg, None
    if isinstance(body.get("key"), dict):
        one = body["key"]
        provider = provider_id(one.get("provider"))
        if provider not in PROVIDERS:
            return None, "unknown"
        if one.get("delete") is True:
            cfg["keys"].pop(provider, None)
            for use in USES:   # a use left without its key goes to another service with a key, if there is one
                if cfg[use]["provider"] == provider and not PROVIDERS[provider].get("key_optional"):
                    others = [pid for pid in ORDER if pid in cfg["keys"]]
                    cfg[use] = {"provider": others[0] if others else "", "model": ""}
        else:
            key = str(one.get("api_key") or "").strip()
            if len(key) < 8 or not KEY_RE.match(key):
                return None, "key_short"
            cfg["keys"][provider] = key
            for use in USES:   # the first key saved is used for what has none
                if not cfg[use]["provider"] or (not cfg["keys"].get(cfg[use]["provider"]) and not PROVIDERS[cfg[use]["provider"]].get("key_optional")):
                    cfg[use] = {"provider": provider, "model": ""}
    if "custom_base" in body:
        base = str(body.get("custom_base") or "").strip().rstrip("/")
        if base and not BASE_RE.match(base):
            return None, "bad_base"
        cfg["custom_base"] = base
    for use in USES:
        if isinstance(body.get(use), dict):
            one = body[use]
            provider = provider_id(one.get("provider")) if one.get("provider") else cfg[use]["provider"]
            if provider and provider not in PROVIDERS:
                return None, "unknown"
            model = str(one.get("model") or "").strip()
            if model and not MODEL_RE.match(model):
                return None, "bad_model"
            if provider != cfg[use]["provider"] and "model" not in one:
                model = ""   # another service: its default, unless a model is given
            elif "model" not in one:
                model = cfg[use]["model"]
            cfg[use] = {"provider": provider, "model": model}
    return cfg, None
