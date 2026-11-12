"""Release 1.116: backend/public_name.py (a DuckDNS name and a Let's Encrypt certificate for it). Against a fake
Let's Encrypt (ACME, RFC 8555) that checks every signature and a fake DuckDNS, in the same process: no network.
The fake signs a real certificate for the name with its own small authority, so the files are real PEM."""
import base64
import datetime
import hashlib
import json
import os
import sys
import tempfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.x509.oid import NameOID

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "backend"))
import public_name as pn  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   -> " + str(extra)[:300]) if (extra != "" and not cond) else ""), flush=True)


def unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Answer:
    def __init__(self, status=200, body=None, headers=None, text=None):
        self.status_code, self.headers = status, dict(headers or {})
        self._body = body
        self.text = text if text is not None else (json.dumps(body) if body is not None else "")

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class Fake:
    """Let's Encrypt and DuckDNS. DuckDNS: one name, one token; it remembers ip, ipv6, txt."""
    BASE = "https://acme.test"

    def __init__(self, token, name, txt_ok=True, bad_nonce_once=False, days=90):
        self.token, self.name, self.txt_ok, self.bad_nonce_once, self.days = token, name, txt_ok, bad_nonce_once, days
        self.dns = {"ip": None, "ipv6": None, "txt": ""}
        self.duck_calls = []
        self.nonces = set()
        self.n = 0
        self.accounts = {}
        self.orders = {}
        self.signatures_checked = 0
        self.ca_key = ec.generate_private_key(ec.SECP256R1())
        self.terms_agreed = False

    # DuckDNS
    def get(self, url, params=None, timeout=None):
        if url == "https://duck.test/update":
            self.duck_calls.append(dict(params))
            if params.get("token") != self.token or params.get("domains") != self.name:
                return Answer(200, text="KO")
            for key in ("ip", "ipv6", "txt"):
                if key in params:
                    self.dns[key] = params[key]
            if params.get("clear") == "true":
                self.dns["txt"] = ""
            return Answer(200, text="OK\n%s\n%s\nUPDATED" % (self.dns["ip"], self.dns["ipv6"] or ""))
        if url == self.BASE + "/directory":
            return Answer(200, {k: self.BASE + "/" + k for k in ("newNonce", "newAccount", "newOrder")})
        raise AssertionError("unexpected GET " + url)

    def _nonce(self):
        self.n += 1
        nonce = "nonce%d" % self.n
        self.nonces.add(nonce)
        return nonce

    def head(self, url, timeout=None):
        return Answer(200, headers={"Replay-Nonce": self._nonce()})

    def _verify(self, envelope, url):
        protected = json.loads(unb64(envelope["protected"]))
        assert protected["alg"] == "ES256" and protected["url"] == url, protected
        if self.bad_nonce_once:
            self.bad_nonce_once = False
            self.nonces.discard(protected["nonce"])
            return None, {"type": "urn:ietf:params:acme:error:badNonce", "detail": "old nonce"}
        assert protected["nonce"] in self.nonces, "unknown nonce"
        self.nonces.discard(protected["nonce"])
        if "jwk" in protected:
            jwk = protected["jwk"]
        else:
            jwk = self.accounts[protected["kid"]]
        key = ec.EllipticCurvePublicNumbers(int.from_bytes(unb64(jwk["x"]), "big"), int.from_bytes(unb64(jwk["y"]), "big"), ec.SECP256R1()).public_key()
        raw = unb64(envelope["signature"])
        assert len(raw) == 64, "ES256 signatures are 64 bytes"
        key.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
                   (envelope["protected"] + "." + envelope["payload"]).encode(), ec.ECDSA(hashes.SHA256()))
        self.signatures_checked += 1
        payload = json.loads(unb64(envelope["payload"])) if envelope["payload"] else None
        return (protected, jwk, payload), None

    def post(self, url, data=None, headers=None, timeout=None):
        envelope = json.loads(data)
        checked, problem = self._verify(envelope, url)
        if problem:
            return Answer(400, problem, {"Replay-Nonce": self._nonce()})
        protected, jwk, payload = checked
        nonce = {"Replay-Nonce": self._nonce()}
        if url.endswith("/newAccount"):
            self.terms_agreed = payload.get("termsOfServiceAgreed") is True
            kid = self.BASE + "/acct/1"
            self.accounts[kid] = jwk
            self.thumb = pn.thumbprint(jwk)
            return Answer(201, {"status": "valid"}, dict(nonce, Location=kid))
        if url.endswith("/newOrder"):
            value = payload["identifiers"][0]["value"]
            self.orders["o1"] = {"name": value, "status": "pending", "authz": "pending", "token": "tok-123"}
            return Answer(201, {"status": "pending", "authorizations": [self.BASE + "/authz/1"], "finalize": self.BASE + "/finalize/1"},
                          dict(nonce, Location=self.BASE + "/order/1"))
        order = self.orders["o1"]
        if url.endswith("/authz/1"):
            return Answer(200, {"status": order["authz"], "identifier": {"type": "dns", "value": order["name"]},
                                "challenges": [{"type": "http-01", "url": self.BASE + "/chall/http", "token": "x"},
                                               {"type": "dns-01", "url": self.BASE + "/chall/1", "token": order["token"],
                                                **({"error": {"detail": "no TXT record found"}} if order["authz"] == "invalid" else {})}]}, nonce)
        if url.endswith("/chall/1"):
            expected = pn.b64u(hashlib.sha256((order["token"] + "." + self.thumb).encode()).digest())
            order["txt_seen"] = self.dns["txt"]
            order["authz"] = "valid" if (self.txt_ok and self.dns["txt"] == expected) else "invalid"
            return Answer(200, {"status": "processing"}, nonce)
        if url.endswith("/finalize/1"):
            csr = x509.load_der_x509_csr(unb64(payload["csr"]))
            names = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
            assert names == [order["name"]], names
            now = datetime.datetime.now(datetime.timezone.utc)
            cert = (x509.CertificateBuilder().subject_name(csr.subject)
                    .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Fake Authority")]))
                    .public_key(csr.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(now - datetime.timedelta(minutes=1)).not_valid_after(now + datetime.timedelta(days=self.days))
                    .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False)
                    .sign(self.ca_key, hashes.SHA256()))
            order["pem"] = cert.public_bytes(serialization.Encoding.PEM).decode()
            order["status"] = "valid"
            return Answer(200, {"status": "processing"}, nonce)
        if url.endswith("/order/1"):
            return Answer(200, {"status": order["status"], "certificate": self.BASE + "/cert/1"}, nonce)
        if url.endswith("/cert/1"):
            return Answer(200, None, nonce, text=order["pem"])
        raise AssertionError("unexpected POST " + url)


TOKEN = "0a1b2c3d-4e5f-6789-abcd-ef0123456789"
naps = []


def make(folder, fake, ipv6="2a01:db8::17", addresses=("192.168.1.17",)):
    return pn.PublicName(folder, fake, lambda: list(addresses), directory=Fake.BASE + "/directory", duckdns_url="https://duck.test/update",
                         sleep=naps.append, ipv6=lambda: ipv6, log=lambda *a: None)


# ---- what the person writes
check("the name: «mine», «Mine.duckdns.org», «https://mine.duckdns.org/» are all «mine»",
      pn.clean_name("mine") == pn.clean_name("Mine.duckdns.org") == pn.clean_name("https://mine.duckdns.org/") == "mine")
check("... a name with dots, spaces or another domain: refused", pn.clean_name("a.b") is None and pn.clean_name("my printer") is None and pn.clean_name("x.example.com") is None)
check("the token: a DuckDNS token (with spaces around) kept; anything else refused", pn.clean_token(" " + TOKEN.upper() + " ") == TOKEN and pn.clean_token("abc") is None)

# ---- openssl helpers
tmp = tempfile.mkdtemp()
key = os.path.join(tmp, "k.pem")
pn.new_key(key)
jwk = pn.public_jwk(key)
check("a P-256 key and its JWK", jwk["kty"] == "EC" and jwk["crv"] == "P-256" and len(unb64(jwk["x"])) == 32 and len(unb64(jwk["y"])) == 32)
check("the key file is private (0600)", oct(os.stat(key).st_mode & 0o777) == "0o600")
sig = pn.sign(key, b"hello")
public = ec.EllipticCurvePublicNumbers(int.from_bytes(unb64(jwk["x"]), "big"), int.from_bytes(unb64(jwk["y"]), "big"), ec.SECP256R1()).public_key()
try:
    public.verify(encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")), b"hello", ec.ECDSA(hashes.SHA256()))
    check("an ES256 signature (64 bytes r||s) that verifies", len(sig) == 64)
except Exception as error:  # noqa: BLE001
    check("an ES256 signature (64 bytes r||s) that verifies", False, error)
check("the JWK thumbprint (RFC 7638): 43 characters, only the key's own members count", len(pn.thumbprint(jwk)) == 43 and pn.thumbprint(jwk) == pn.thumbprint(dict(jwk, extra=1)))

# ---- IPv6 address
out = """2: eth0    inet6 2a01:db8::aaaa/64 scope global temporary dynamic
2: eth0    inet6 fd00::17/64 scope global dynamic mngtmpaddr
2: eth0    inet6 2a01:db8::17/64 scope global dynamic mngtmpaddr
2: eth0    inet6 fe80::1/64 scope link"""
class Done:
    stdout = out
check("IPv6: the stable public one (not the temporary one, not fd00::/fe80::)", pn.global_ipv6(lambda *a, **k: Done()) == "2a01:db8::17", pn.global_ipv6(lambda *a, **k: Done()))
class NoSix:
    stdout = "2: eth0    inet6 fd00::17/64 scope global dynamic"
check("... none: None", pn.global_ipv6(lambda *a, **k: NoSix()) is None)

# ---- the whole way
folder = tempfile.mkdtemp()
fake = Fake(TOKEN, "mine")
p = make(folder, fake)
check("nothing set: no certificate needed, not ready", p.needs_certificate() is False and p.ready() is None and p.status()["token_set"] is False)
p.save(name="mine", token=TOKEN)
check("the token file is private (0600)", oct(os.stat(p.settings_path).st_mode & 0o777) == "0o600")
check("... the status does not show the token", TOKEN not in json.dumps(p.status()) and p.status()["token_set"] is True)
status = p.obtain()
check("obtained: a certificate for mine.duckdns.org, no error", status["certificate"] and status["error"] == "" and status["address"] == "mine.duckdns.org", status)
check("... the name points to the address at home and to the IPv6 one", fake.dns["ip"] == "192.168.1.17" and fake.dns["ipv6"] == "2a01:db8::17", fake.dns)
check("... Let's Encrypt saw the right TXT record; it is cleared afterwards", fake.orders["o1"].get("txt_seen") and fake.dns["txt"] == "", fake.orders["o1"])
check("... it waited for the TXT record to spread before the check", pn.DNS_WAIT_S in naps)
check("... every request signed and checked (account, order, authorization, challenge, finalize, certificate)", fake.signatures_checked >= 7, fake.signatures_checked)
check("... the terms of Let's Encrypt accepted (the person tapped the button)", fake.terms_agreed)
ready = p.ready()
check("ready: the certificate, its key, the name", ready and ready[2] == "mine.duckdns.org" and "BEGIN CERTIFICATE" in open(ready[0]).read() and oct(os.stat(ready[1]).st_mode & 0o777) == "0o600", ready)
check("... valid for 90 days: no renewal yet", p.needs_certificate() is False)
check("... in 70 days: renewal", p.needs_certificate(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=70)))

calls = len(fake.duck_calls)
p.point()
check("the address unchanged: DuckDNS is not called again", len(fake.duck_calls) == calls)
p.addresses = lambda: ["192.168.1.40"]
p.point()
check("... the address changed (a new one from the router): updated", fake.dns["ip"] == "192.168.1.40" and len(fake.duck_calls) == calls + 1)

# a stale nonce once: retried
folder2 = tempfile.mkdtemp()
fake2 = Fake(TOKEN, "mine", bad_nonce_once=True)
p2 = make(folder2, fake2, ipv6=None)
p2.save(name="mine", token=TOKEN)
check("a refused nonce: tried again, the certificate comes", p2.obtain()["certificate"])
check("... without IPv6: only the IPv4 address is set", fake2.dns["ip"] == "192.168.1.17" and fake2.dns["ipv6"] is None and "ipv6" not in fake2.duck_calls[0])

# the check fails
folder3 = tempfile.mkdtemp()
fake3 = Fake(TOKEN, "mine", txt_ok=False)
p3 = make(folder3, fake3)
p3.save(name="mine", token=TOKEN)
status = p3.obtain()
check("Let's Encrypt does not find the record: said, no certificate, the record cleared", not status["certificate"] and "no TXT record found" in status["error"] and fake3.dns["txt"] == "" and not status["busy"], status)

# a wrong token
folder4 = tempfile.mkdtemp()
fake4 = Fake(TOKEN, "mine")
p4 = make(folder4, fake4)
p4.save(name="mine", token="11111111-2222-3333-4444-555555555555")
status = p4.obtain()
check("a wrong token: DuckDNS refuses, said in plain words", "DuckDNS refused" in status["error"] and not status["certificate"], status)
check("... and the daily check does not hammer Let's Encrypt (at most every six hours)", (p4.tick(), fake4.signatures_checked)[1] == 0)

# forgetting
p.forget()
check("forget: the token, the name, the certificate and the account key removed", p.ready() is None and os.listdir(folder) == [], os.listdir(folder))
folder5 = tempfile.mkdtemp()
p5 = make(folder5, Fake(TOKEN, "mine"), addresses=())
p5.save(name="mine", token=TOKEN)
status = p5.obtain()
check("the address at home not known: nothing sent to DuckDNS (an empty ip= would make it take the public one)", "not known" in status["error"] and not p5.http.duck_calls, status)

print("\n%d failure(s)" % len(FAILS) + (": " + ", ".join(FAILS) if FAILS else ""))
sys.exit(1 if FAILS else 0)
