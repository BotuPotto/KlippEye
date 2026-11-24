# Python mirror of three Kotlin rules (copied literally) to show what the bridge accepts. Run: python3 -I bridge_mirror.py
import re, json
# PushSettings.kt:88-89
TOPIC = re.compile(r"^[-_A-Za-z0-9]{1,64}$")
SERVER = re.compile(r"^https?://[A-Za-z0-9.\-]+(:\d{1,5})?(/[A-Za-z0-9._~\-/]*)?$")
payload = {"receive": True, "ntfy": {"server": "http://attacker.example.com:8080", "topic": "x", "token": "t"}}
n = payload["ntfy"]
print("notifySetup accepts a public server:", bool(SERVER.match(n["server"].rstrip("/"))) and bool(TOPIC.match(n["topic"])))
# Addresses.kt:40-41 variants(): http fallback is always listed, even when a certificate is pinned
def variants(host, with_cert):
    return (["https://%s/" % host] if with_cert else []) + ["http://%s/" % host, "http://%s:8085/" % host]
print("pinned host still tries:", variants("pi.local", True))
# MainActivity.isKlippEye / Addresses.isKlippEye: what the probe needs from an address
body = '{"enabled": false}'
print("fake KlippEye answer accepted:", "json" in "application/json" and bool(re.search(r'"enabled"\s*:\s*(true|false)', body)))
