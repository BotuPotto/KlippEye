"""A secure address without the browser's warning (1.116): a free DuckDNS name and a Let's Encrypt certificate for it.

The certificate KlippEye makes itself (https_relay.py) is signed by nobody, so a browser warns the first time. A
browser trusts a certificate only when it is for a name and signed by an authority it knows. Here:

- the person makes a free name at duckdns.org (one minute, a Google or GitHub account) and pastes its token;
- the name points to the Raspberry's address at home (IPv4) and, when the line has one, to its IPv6 address: some
  home routers refuse a public name that points inside the home (a protection called DNS rebinding), and an IPv6
  address is not "inside" for them, so the name keeps working there too. Nothing is opened to the internet: the
  router does not let connections in, on IPv4 or IPv6;
- Let's Encrypt signs a certificate for the name after a DNS check (dns-01): the Raspberry writes a TXT record at
  DuckDNS, no port has to be reachable from outside. It lasts 90 days and is renewed 30 days before the end.

The ACME client (RFC 8555) is small and uses only `openssl` (as https_relay.py) and `requests`: the account key and
the certificate's key are EC P-256, the messages are signed with ES256.

The certificate is used only when a browser asks for the name (SNI): opened by the address (192.168.x.x) or by the
Android app, KlippEye keeps answering with its own certificate, whose fingerprint the app knows.
"""

import base64
import datetime
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import threading
import time

LETSENCRYPT = "https://acme-v02.api.letsencrypt.org/directory"
LETSENCRYPT_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"
DUCKDNS = "https://www.duckdns.org/update"
TERMS = "https://letsencrypt.org/repository/"
RENEW_DAYS = 30            # a new certificate when fewer days than this are left
DNS_WAIT_S = 45            # after writing the TXT record, before asking Let's Encrypt to look at it
POLL_S = 3
POLL_TRIES = 40
NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
TOKEN_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class PublicNameError(Exception):
    pass


def b64u(data):
    if isinstance(data, str):
        data = data.encode()
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def clean_name(text):
    """The DuckDNS name from what the person wrote ("mine", "mine.duckdns.org", "https://mine.duckdns.org/"), or None."""
    name = (text or "").strip().lower()
    name = re.sub(r"^https?://", "", name).split("/")[0].split(":")[0]
    if name.endswith(".duckdns.org"):
        name = name[: -len(".duckdns.org")]
    return name if NAME_RE.match(name) and "." not in name else None


def clean_token(text):
    token = (text or "").strip().lower()
    return token if TOKEN_RE.match(token) else None


def full_name(name):
    return name + ".duckdns.org"


# ---- the Raspberry's addresses -----------------------------------------------------------------------------------

def global_ipv6(run=subprocess.run):
    """The Raspberry's IPv6 address that can be reached (not a temporary one, not fe80::/fc00::), or None."""
    try:
        out = run(["ip", "-6", "-o", "addr", "show", "scope", "global"], capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001 - no `ip`: no IPv6
        return None
    found = []
    for line in out.splitlines():
        match = re.search(r"inet6\s+([0-9a-f:]+)/\d+", line)
        if not match or "temporary" in line or "deprecated" in line or "tentative" in line:
            continue
        try:
            address = ipaddress.IPv6Address(match.group(1))
        except ValueError:
            continue
        if address.is_global:
            found.append((0 if "mngtmpaddr" in line or "dynamic" not in line else 1, str(address)))
    return sorted(found)[0][1] if found else None


# ---- openssl ---------------------------------------------------------------------------------------------------

def _openssl(arguments, data=None):
    done = subprocess.run(["openssl"] + arguments, input=data, capture_output=True, timeout=60)
    if done.returncode != 0:
        raise PublicNameError("openssl: " + done.stderr.decode(errors="replace")[-300:])
    return done.stdout


def new_key(path):
    _openssl(["ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", path + ".new"])
    os.chmod(path + ".new", 0o600)
    os.replace(path + ".new", path)


def public_jwk(key_path):
    """The account key's public half as a JWK (EC P-256)."""
    der = _openssl(["ec", "-in", key_path, "-pubout", "-outform", "DER"])
    point = der[-65:]
    if point[0] != 4:
        raise PublicNameError("unexpected public key")
    return {"crv": "P-256", "kty": "EC", "x": b64u(point[1:33]), "y": b64u(point[33:])}


def thumbprint(jwk):
    canonical = json.dumps({"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"], "y": jwk["y"]}, separators=(",", ":"), sort_keys=True)
    return b64u(hashlib.sha256(canonical.encode()).digest())


def der_to_raw(signature):
    """An ECDSA signature from DER (what openssl writes) to the 64 bytes r||s that ES256 wants."""
    if len(signature) < 8 or signature[0] != 0x30:
        raise PublicNameError("unexpected signature")
    index = 2 if signature[1] < 0x80 else 3
    parts = []
    for _ in range(2):
        if signature[index] != 0x02:
            raise PublicNameError("unexpected signature")
        length = signature[index + 1]
        value = signature[index + 2:index + 2 + length].lstrip(b"\x00")
        if len(value) > 32:
            raise PublicNameError("unexpected signature")
        parts.append(value.rjust(32, b"\x00"))
        index += 2 + length
    return parts[0] + parts[1]


def sign(key_path, data):
    return der_to_raw(_openssl(["dgst", "-sha256", "-sign", key_path], data))


def csr_der(key_path, name):
    return _openssl(["req", "-new", "-key", key_path, "-subj", "/CN=" + name, "-addext", "subjectAltName=DNS:" + name, "-outform", "DER"])


def certificate_end(pem_path):
    """When the certificate in `pem_path` stops being valid (UTC), or None."""
    try:
        out = _openssl(["x509", "-in", pem_path, "-noout", "-enddate"]).decode().strip()
        return datetime.datetime.strptime(out.split("=", 1)[1], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=datetime.timezone.utc)
    except Exception:  # noqa: BLE001
        return None


# ---- the ACME client -------------------------------------------------------------------------------------------

class Acme:
    def __init__(self, directory_url, account_key, http, log=print):
        self.http, self.key, self.log = http, account_key, log
        response = http.get(directory_url, timeout=20)
        response.raise_for_status()
        self.directory = response.json()
        self.jwk = public_jwk(account_key)
        self.kid = None
        self.nonce = None

    def _nonce(self):
        if self.nonce:
            nonce, self.nonce = self.nonce, None
            return nonce
        response = self.http.head(self.directory["newNonce"], timeout=20)
        return response.headers["Replay-Nonce"]

    def post(self, url, payload, tries=3):
        """A signed request (payload None = POST-as-GET); a badNonce is retried with the new nonce."""
        for attempt in range(tries):
            protected = {"alg": "ES256", "nonce": self._nonce(), "url": url}
            if self.kid:
                protected["kid"] = self.kid
            else:
                protected["jwk"] = self.jwk
            body_protected = b64u(json.dumps(protected))
            body_payload = "" if payload is None else b64u(json.dumps(payload))
            signature = b64u(sign(self.key, (body_protected + "." + body_payload).encode()))
            response = self.http.post(url, data=json.dumps({"protected": body_protected, "payload": body_payload, "signature": signature}),
                                      headers={"Content-Type": "application/jose+json"}, timeout=30)
            self.nonce = response.headers.get("Replay-Nonce")
            if response.status_code < 400:
                return response
            problem = {}
            try:
                problem = response.json()
            except ValueError:
                pass
            if problem.get("type", "").endswith(":badNonce") and attempt + 1 < tries:
                continue
            raise PublicNameError("Let's Encrypt: %s" % (problem.get("detail") or response.status_code))
        raise PublicNameError("Let's Encrypt: no answer")

    def account(self):
        response = self.post(self.directory["newAccount"], {"termsOfServiceAgreed": True})
        self.kid = response.headers["Location"]
        return self.kid

    def poll(self, url, until, sleep):
        for _ in range(POLL_TRIES):
            body = self.post(url, None).json()
            if body.get("status") in until:
                return body
            if body.get("status") == "invalid":
                detail = ""
                for challenge in body.get("challenges", []):
                    detail = (challenge.get("error") or {}).get("detail") or detail
                raise PublicNameError("Let's Encrypt refused: %s" % (detail or (body.get("error") or {}).get("detail") or "invalid"))
            sleep(POLL_S)
        raise PublicNameError("Let's Encrypt: still waiting after %d s" % (POLL_S * POLL_TRIES))


# ---- DuckDNS ---------------------------------------------------------------------------------------------------

def duckdns(http, name, token, base=DUCKDNS, **values):
    """One update call (ip=, ipv6=, txt=, clear=): True when DuckDNS says OK."""
    params = {"domains": name, "token": token, "verbose": "true", **values}
    response = http.get(base, params=params, timeout=20)
    text = (response.text or "").strip()
    if not text.startswith("OK"):
        raise PublicNameError("DuckDNS refused the update (%s): check the name and the token" % (text[:40] or response.status_code))
    return text


# ---- the whole thing -------------------------------------------------------------------------------------------

class PublicName:
    """The settings (public.json: name, token), the certificate (public-cert.pem / public-key.pem) and its renewal, in
    `folder` (DATA_DIR/https). `addresses()` gives the Raspberry's IPv4 at home."""

    def __init__(self, folder, http, addresses, directory=LETSENCRYPT, duckdns_url=DUCKDNS, sleep=time.sleep,
                 ipv6=global_ipv6, log=print, on_new_certificate=None):
        self.folder, self.http, self.addresses = folder, http, addresses
        self.directory, self.duckdns_url, self.sleep, self.ipv6, self.log = directory, duckdns_url, sleep, ipv6, log
        self.on_new_certificate = on_new_certificate
        self.lock = threading.Lock()
        self.state = {"busy": False, "step": "", "error": "", "last_try": None}
        os.makedirs(folder, exist_ok=True)

    # files
    @property
    def settings_path(self):
        return os.path.join(self.folder, "public.json")

    @property
    def cert_path(self):
        return os.path.join(self.folder, "public-cert.pem")

    @property
    def key_path(self):
        return os.path.join(self.folder, "public-key.pem")

    def settings(self):
        try:
            with open(self.settings_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            data = {}
        return {"name": clean_name(data.get("name")) or "", "token": clean_token(data.get("token")) or "",
                "points_to": data.get("points_to") or {}}

    def save(self, **values):
        data = dict(self.settings(), **values)
        with open(self.settings_path + ".tmp", "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.chmod(self.settings_path + ".tmp", 0o600)  # the token is a key to the person's DuckDNS names
        os.replace(self.settings_path + ".tmp", self.settings_path)

    def ready(self):
        """(cert, key, name) when there is a certificate for the name in use, else None."""
        settings = self.settings()
        if settings["name"] and os.path.exists(self.cert_path) and os.path.exists(self.key_path):
            return self.cert_path, self.key_path, full_name(settings["name"])
        return None

    def status(self):
        settings = self.settings()
        end = certificate_end(self.cert_path) if os.path.exists(self.cert_path) else None
        return {"name": settings["name"], "address": full_name(settings["name"]) if settings["name"] else "",
                "token_set": bool(settings["token"]), "certificate": bool(end), "valid_until": end.isoformat() if end else None,
                "points_to": settings["points_to"], **self.state}

    def forget(self):
        with self.lock:
            settings = self.settings()
            if settings["name"] and settings["token"]:
                try:
                    duckdns(self.http, settings["name"], settings["token"], self.duckdns_url, txt="", clear="true")
                except Exception:  # noqa: BLE001 - the name stays at DuckDNS; nothing else to undo
                    pass
            for path in (self.settings_path, self.cert_path, self.key_path, os.path.join(self.folder, "acme-account.pem")):
                if os.path.exists(path):
                    os.remove(path)
            self.state.update(error="", step="")

    # the address the name points to
    def point(self):
        settings = self.settings()
        if not (settings["name"] and settings["token"]):
            return None
        home = (self.addresses() or [""])[0]
        if not home:  # an empty ip= would make DuckDNS take the router's public address: never
            raise PublicNameError("the Raspberry's address at home is not known")
        six = self.ipv6()
        values = {"ip": home}
        if six:
            values["ipv6"] = six
        if settings["points_to"] == {"ipv4": home, "ipv6": six}:
            return settings["points_to"]
        duckdns(self.http, settings["name"], settings["token"], self.duckdns_url, **values)
        self.save(points_to={"ipv4": home, "ipv6": six})
        self.log("[NAME] %s → %s%s" % (full_name(settings["name"]), home, (" and " + six) if six else ""))
        return {"ipv4": home, "ipv6": six}

    def needs_certificate(self, now=None):
        settings = self.settings()
        if not (settings["name"] and settings["token"]):
            return False
        end = certificate_end(self.cert_path) if os.path.exists(self.cert_path) else None
        now = now or datetime.datetime.now(datetime.timezone.utc)
        return end is None or end - now < datetime.timedelta(days=RENEW_DAYS)

    def obtain(self):
        """Points the name and gets a certificate for it from Let's Encrypt. Returns the status; the error is in it."""
        if not self.lock.acquire(blocking=False):
            return self.status()
        self.state.update(busy=True, error="", step="name", last_try=time.time())
        txt_written = False
        settings = self.settings()
        try:
            if not (settings["name"] and settings["token"]):
                raise PublicNameError("the name and the token are needed")
            self.point()
            name = full_name(settings["name"])
            account_key = os.path.join(self.folder, "acme-account.pem")
            if not os.path.exists(account_key):
                new_key(account_key)
            self.state["step"] = "account"
            acme = Acme(self.directory, account_key, self.http, self.log)
            acme.account()
            order_response = acme.post(acme.directory["newOrder"], {"identifiers": [{"type": "dns", "value": name}]})
            order_url, order = order_response.headers.get("Location"), order_response.json()
            for authorization_url in order["authorizations"]:
                authorization = acme.post(authorization_url, None).json()
                if authorization.get("status") == "valid":
                    continue
                challenge = next((one for one in authorization["challenges"] if one["type"] == "dns-01"), None)
                if not challenge:
                    raise PublicNameError("Let's Encrypt offered no DNS check")
                value = b64u(hashlib.sha256((challenge["token"] + "." + thumbprint(acme.jwk)).encode()).digest())
                self.state["step"] = "check"
                duckdns(self.http, settings["name"], settings["token"], self.duckdns_url, txt=value)
                txt_written = True
                self.sleep(DNS_WAIT_S)
                acme.post(challenge["url"], {})
                acme.poll(authorization_url, ("valid",), self.sleep)
            self.state["step"] = "certificate"
            key_new = self.key_path + ".next"
            new_key(key_new)
            acme.post(order["finalize"], {"csr": b64u(csr_der(key_new, name))})
            order = acme.poll(order_url, ("valid",), self.sleep)
            chain = acme.post(order["certificate"], None).text
            if "BEGIN CERTIFICATE" not in chain:
                raise PublicNameError("Let's Encrypt sent no certificate")
            with open(self.cert_path + ".next", "w", encoding="ascii") as handle:
                handle.write(chain)
            os.replace(key_new, self.key_path)
            os.replace(self.cert_path + ".next", self.cert_path)
            self.state.update(step="done")
            self.log("[NAME] certificate for %s until %s" % (name, certificate_end(self.cert_path)))
            if self.on_new_certificate:
                self.on_new_certificate()
        except PublicNameError as error:
            self.state.update(error=str(error)[:300], step="")
            self.log("[NAME] %s" % error)
        except Exception as error:  # noqa: BLE001 - the network, an answer of an unexpected shape
            self.state.update(error=("%s: %s" % (type(error).__name__, error))[:300], step="")
            self.log("[NAME] %s" % error)
        finally:
            if txt_written:
                try:
                    duckdns(self.http, settings["name"], settings["token"], self.duckdns_url, txt="", clear="true")
                except Exception:  # noqa: BLE001
                    pass
            self.state["busy"] = False
            self.lock.release()
        return self.status()

    def tick(self):
        """Once in a while (the service's daily check): the address the name points to, and the certificate when it ends
        within RENEW_DAYS. A failure is kept in the status and tried again at the next tick."""
        try:
            self.point()
        except Exception as error:  # noqa: BLE001
            self.state["error"] = str(error)[:300]
        if self.needs_certificate():
            last = self.state.get("last_try") or 0
            if time.time() - last > 6 * 3600:  # Let's Encrypt allows few failures an hour: at most every six hours
                self.obtain()
