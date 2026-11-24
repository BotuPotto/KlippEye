#!/usr/bin/env python3
"""X2 run 4: clients saving settings at the same moment (threads released together by a barrier).

    python3 run_race.py [rounds=30]

a) /api/ai/config: 9 clients, each saves the key of a different service. How many keys are on disk afterwards?
b) /api/backend/config: 9 clients, each changes a different setting. All 9 kept?
c) /api/backend/config: «In doubt from» 70 and «Sure from» 60 sent together, each valid alone (defaults 35 / 80).
   How often does the file end with sure <= doubt (the rule the backend enforces for a single request)?
Writes out/race.json.
"""
import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import http, new_data, start_backend, start_fake, stop, wait_port  # noqa: E402

ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)
MP, CP, BP = 17401, 17402, 18401
B = "http://127.0.0.1:%d" % BP
PROVIDERS = ["groq", "gemini", "openai", "anthropic", "mistral", "openrouter", "meta", "together", "fireworks"]
SETTINGS = {"sensitivity": 50, "score_threshold": 3.0, "trigger_count": 4, "border": 30, "persist_checks": 4,
            "reference_seconds": 90, "global_change": 40.0, "cooldown": 120, "ai_cooldown": 150}

moon = start_fake("moonraker", MP)
data = new_data({"enabled": False})
back = start_backend(data, BP, MP, log=os.path.join(OUT, "race-backend.log"))
assert wait_port(B + "/api/print/detector/status", 60)


def together(calls):
    barrier = threading.Barrier(len(calls))
    codes = [None] * len(calls)

    def run(i, method, path, body):
        barrier.wait()
        codes[i] = http(method, B + path, body, timeout=20)[0]
    threads = [threading.Thread(target=run, args=(i,) + c) for i, c in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return codes


res = {"ai": [], "config": [], "sure_doubt": []}
for r in range(ROUNDS):
    # a) keys
    http("POST", B + "/api/ai/config", {"delete": True})
    keys = {p: "r%03d%s%022d" % (r, p[:3], r) for p in PROVIDERS}
    codes = together([("POST", "/api/ai/config", {"key": {"provider": p, "api_key": keys[p]}}) for p in PROVIDERS])
    on_disk = (json.load(open(os.path.join(data, "ai.json"))).get("keys") or {})
    kept = [p for p in PROVIDERS if on_disk.get(p) == keys[p]]
    res["ai"].append({"acked": codes.count(200), "kept": len(kept)})
    # b) nine settings
    http("POST", B + "/api/backend/config/reset", {})
    codes = together([("POST", "/api/backend/config", {"values": {k: v}}) for k, v in SETTINGS.items()])
    values = json.load(open(os.path.join(data, "monitor.json")))["values"]
    res["config"].append({"acked": codes.count(200), "kept": sum(values.get(k) == v for k, v in SETTINGS.items())})
    # c) doubt / sure
    http("POST", B + "/api/backend/config/reset", {})
    codes = together([("POST", "/api/backend/config", {"values": {"local_doubt": 70}}), ("POST", "/api/backend/config", {"values": {"local_sure": 60}})])
    values = json.load(open(os.path.join(data, "monitor.json")))["values"]
    res["sure_doubt"].append({"codes": codes, "doubt": values.get("local_doubt"), "sure": values.get("local_sure"),
                              "broken": values.get("local_sure", 80) <= values.get("local_doubt", 35)})

summary = {
    "rounds": ROUNDS,
    "ai_keys_acked_total": sum(x["acked"] for x in res["ai"]), "ai_keys_kept_total": sum(x["kept"] for x in res["ai"]),
    "ai_rounds_with_loss": sum(x["kept"] < x["acked"] for x in res["ai"]),
    "ai_kept_per_round": [x["kept"] for x in res["ai"]],
    "config_kept_per_round": [x["kept"] for x in res["config"]],
    "sure_doubt_broken_rounds": sum(x["broken"] for x in res["sure_doubt"]),
    "sure_doubt_example": next((x for x in res["sure_doubt"] if x["broken"]), None),
}
stop(back)
stop(moon)
json.dump({"summary": summary, "detail": res}, open(os.path.join(OUT, "race.json"), "w"), indent=1)
print(json.dumps(summary, indent=1))
