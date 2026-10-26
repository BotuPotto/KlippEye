#!/usr/bin/env python3
"""
KlippEye - accesso: password facoltativa, gettoni di accesso, controlli di rete (indirizzo e origine delle richieste).

Usato dal backend (import) e da terminale, per esempio dal comando `klippeye password`:

    python3 accesso.py stato                 dice se la password e' attiva e quali nomi di rete sono ammessi
    python3 accesso.py imposta               chiede una password nuova (due volte) e la attiva
    python3 accesso.py togli                 toglie la password (per chi l'ha dimenticata: serve l'accesso al Raspberry)
    python3 accesso.py esci-tutti            chiude l'accesso su tutti i dispositivi (dovranno rifare l'accesso)
    python3 accesso.py host-aggiungi NOME    ammette un nome di rete in piu' (es. stampante.casa.it)
    python3 accesso.py host-togli NOME
    python3 accesso.py controlli-rete on|off accende/spegne i controlli su nome e origine (spenti = come prima della 1.2.0)

I dati stanno in <cartella dati>/accesso.json (permessi 600): mai la password, solo il suo "hash" PBKDF2 con sale.
Solo libreria standard: niente da installare.
"""
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import sys
import tempfile
import threading
import time

FORMAT = 1
ITERATIONS = 120000          # PBKDF2-SHA256: circa mezzo secondo su un Raspberry lento, impercettibile per chi accede una volta
COOKIE_NAME = "klippeye_accesso"
TOKEN_DAYS = 180             # dopo sei mesi si rifà l'accesso
HEADER_INTERNAL = "X-KlippEye-Token"   # i servizi sul Raspberry (notifiche, comandi) si presentano con il gettone interno
MIN_PASSWORD = 6
MAX_PASSWORD = 256
LOCAL_SUFFIXES = (".local", ".lan", ".home", ".internal", ".home.arpa", ".localdomain")


# ---------------------------------------------------------------------------------------------------------------------
# file
# ---------------------------------------------------------------------------------------------------------------------

def data_dir_default():
    chosen = (os.environ.get("KLIPPEYE_DATA") or "").strip()
    if chosen:
        return os.path.abspath(os.path.expanduser(chosen))
    home = os.path.expanduser("~")
    if os.path.isdir(os.path.join(home, "printer_data")):
        return os.path.join(home, "printer_data", "klippeye")
    return os.path.join(home, "klippeye_data")


def _write_private(path, text):
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def default_settings():
    return {"formato": FORMAT, "enabled": False, "salt": "", "hash": "", "iterations": ITERATIONS,
            "secret": secrets.token_hex(32), "generation": 1, "allowed_hosts": [], "network_checks": True}


class Store:
    """accesso.json, riletto quando cambia sul disco (il comando da terminale e il backend lo condividono)."""

    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, "accesso.json")
        self.internal_path = os.path.join(data_dir, "interno.token")
        self.lock = threading.RLock()
        self._cache = None
        self._stamp = None
        self._internal = None

    def _signature(self):
        try:
            st = os.stat(self.path)
            return (st.st_mtime_ns, st.st_size, st.st_ino)
        except OSError:
            return None

    def load(self):
        with self.lock:
            stamp = self._signature()
            if self._cache is not None and stamp == self._stamp:
                return dict(self._cache)
            data = default_settings()
            fresh = stamp is None
            if not fresh:
                try:
                    with open(self.path, encoding="utf-8") as f:
                        saved = json.load(f)
                    if isinstance(saved, dict):
                        data.update({k: v for k, v in saved.items() if k in data})
                except (OSError, ValueError):
                    fresh = True   # rovinato: si riparte senza password (meglio aperto come prima che chiuso fuori)
            if not isinstance(data.get("allowed_hosts"), list):
                data["allowed_hosts"] = []
            if not data.get("secret"):
                data["secret"] = secrets.token_hex(32)
                fresh = True
            if fresh:
                self._save(data)
                stamp = self._signature()
            self._cache, self._stamp = dict(data), stamp
            return dict(data)

    def _save(self, data):
        _write_private(self.path, json.dumps(data, indent=2, sort_keys=True) + "\n")

    def save(self, data):
        with self.lock:
            self._save(data)
            self._cache, self._stamp = dict(data), self._signature()

    def internal_token(self):
        """Il gettone per i servizi del Raspberry: creato una volta, file 600 leggibile solo dall'utente dei servizi."""
        with self.lock:
            if self._internal:
                return self._internal
            try:
                with open(self.internal_path, encoding="utf-8") as f:
                    value = f.read().strip()
                if len(value) >= 32:
                    self._internal = value
                    return value
            except OSError:
                pass
            value = secrets.token_hex(32)
            _write_private(self.internal_path, value + "\n")
            self._internal = value
            return value


# ---------------------------------------------------------------------------------------------------------------------
# password e gettoni
# ---------------------------------------------------------------------------------------------------------------------

def check_new_password(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        return "La password deve avere almeno %d caratteri" % MIN_PASSWORD
    if len(password) > MAX_PASSWORD:
        return "Password troppo lunga"
    return ""


def hash_password(password, salt_hex=None, iterations=ITERATIONS):
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    return salt.hex(), digest.hex()


def verify_password(settings, password):
    if not settings.get("enabled") or not settings.get("hash") or not isinstance(password, str) or len(password) > MAX_PASSWORD:
        return False
    try:
        _, digest = hash_password(password, settings.get("salt"), settings.get("iterations") or ITERATIONS)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, settings.get("hash", ""))


def set_password(settings, password):
    salt, digest = hash_password(password)
    settings.update({"enabled": True, "salt": salt, "hash": digest, "iterations": ITERATIONS})
    settings["generation"] = int(settings.get("generation") or 1) + 1   # i gettoni di prima non valgono piu'
    return settings


def clear_password(settings):
    settings.update({"enabled": False, "salt": "", "hash": ""})
    settings["generation"] = int(settings.get("generation") or 1) + 1
    return settings


def _b64(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_token(settings, now=None):
    now = int(now or time.time())
    body = _b64(json.dumps({"v": 1, "exp": now + TOKEN_DAYS * 86400, "gen": int(settings.get("generation") or 1)}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(bytes.fromhex(settings["secret"]), body.encode("ascii"), hashlib.sha256).digest())
    return body + "." + sig


def token_valid(settings, token, now=None):
    if not token or not isinstance(token, str) or token.count(".") != 1 or len(token) > 512:
        return False
    body, sig = token.split(".")
    try:
        expected = _b64(hmac.new(bytes.fromhex(settings["secret"]), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, sig):
            return False
        data = json.loads(_unb64(body))
    except (ValueError, TypeError, KeyError):
        return False
    return data.get("v") == 1 and int(data.get("gen", -1)) == int(settings.get("generation") or 1) and int(data.get("exp", 0)) > int(now or time.time())


class Throttle:
    """Dopo 5 password sbagliate dallo stesso indirizzo, attesa che raddoppia (2, 4, 8... fino a 5 minuti)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.failures = {}   # ip -> (quante, fino a quando aspettare)

    def wait_seconds(self, ip, now=None):
        now = now or time.time()
        with self.lock:
            count, until = self.failures.get(ip, (0, 0))
            return max(0, int(until - now + 0.999))

    def failed(self, ip, now=None):
        now = now or time.time()
        with self.lock:
            count, _ = self.failures.get(ip, (0, 0))
            count += 1
            wait = 0 if count < 5 else min(300, 2 ** (count - 4))
            self.failures[ip] = (count, now + wait)
            if len(self.failures) > 1000:   # memoria limitata
                self.failures.pop(next(iter(self.failures)))

    def ok(self, ip):
        with self.lock:
            self.failures.pop(ip, None)


# ---------------------------------------------------------------------------------------------------------------------
# controlli di rete: nome con cui si chiama il Raspberry (contro il "DNS rebinding") e origine delle richieste
# ---------------------------------------------------------------------------------------------------------------------

def split_host(host_header):
    """'192.168.1.17:8085' -> '192.168.1.17'; '[fe80::1]:8085' -> 'fe80::1'; in minuscolo."""
    host = (host_header or "").strip().lower()
    if host.startswith("["):
        return host[1:host.find("]")] if "]" in host else host
    if host.count(":") == 1:
        host = host.split(":")[0]
    return host.rstrip(".")


def host_allowed(host_header, allowed_hosts=()):
    """Un indirizzo IP, 'localhost', un nome senza punti (il nome del Raspberry) o della rete di casa (.local, .lan...),
    oppure un nome aggiunto con `klippeye accesso host-aggiungi`. Un sito internet qualunque che punta al Raspberry no."""
    host = split_host(host_header)
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    if host == "localhost" or "." not in host or host.endswith(LOCAL_SUFFIXES):
        return True
    return host in {str(h).strip().lower().rstrip(".") for h in (allowed_hosts or ())}


def origin_matches(origin, host_header):
    """L'origine dichiarata dal browser e' il Raspberry stesso: stesso nome e porta (lo schema http/https non conta,
    cosi' funziona anche dietro un proxy che aggiunge l'https)."""
    if not origin or origin == "null" or "://" not in origin:
        return False
    return origin.split("://", 1)[1].lower().rstrip("/") == (host_header or "").strip().lower()


# ---------------------------------------------------------------------------------------------------------------------
# comando da terminale
# ---------------------------------------------------------------------------------------------------------------------

def _ask_password():
    import getpass
    while True:
        first = getpass.getpass("Password nuova (almeno %d caratteri): " % MIN_PASSWORD)
        problem = check_new_password(first)
        if problem:
            print(problem)
            continue
        if getpass.getpass("Ripetila: ") != first:
            print("Le due password non coincidono, riprova.")
            continue
        return first


def main(argv):
    store = Store(data_dir_default())
    cmd = argv[1] if len(argv) > 1 else "stato"
    settings = store.load()
    if cmd == "stato":
        print("Password: %s" % ("ATTIVA" if settings["enabled"] else "non attiva (chiunque raggiunga la dashboard la usa)"))
        print("Controlli di rete (nome e origine delle richieste): %s" % ("accesi" if settings.get("network_checks", True) else "SPENTI"))
        extra = settings.get("allowed_hosts") or []
        print("Nomi di rete aggiunti: %s" % (", ".join(extra) if extra else "nessuno (valgono indirizzi IP, nomi .local/.lan e il nome del Raspberry)"))
        print("File: %s" % store.path)
        return 0
    if cmd == "imposta":
        password = argv[2] if len(argv) > 2 and argv[2] != "-" else _ask_password()
        problem = check_new_password(password)
        if problem:
            print(problem)
            return 1
        store.save(set_password(settings, password))
        print("Password attivata. Tutti i dispositivi dovranno fare l'accesso.")
        return 0
    if cmd == "togli":
        store.save(clear_password(settings))
        print("Password tolta: la dashboard si apre di nuovo senza accesso.")
        return 0
    if cmd == "esci-tutti":
        settings["generation"] = int(settings.get("generation") or 1) + 1
        store.save(settings)
        print("Fatto: ogni dispositivo dovrà rifare l'accesso.")
        return 0
    if cmd in ("host-aggiungi", "host-togli") and len(argv) > 2:
        name = split_host(argv[2])
        hosts = [h for h in settings.get("allowed_hosts") or [] if h != name]
        if cmd == "host-aggiungi":
            hosts.append(name)
        settings["allowed_hosts"] = hosts
        store.save(settings)
        print("Nomi di rete aggiunti: %s" % (", ".join(hosts) or "nessuno"))
        return 0
    if cmd == "controlli-rete" and len(argv) > 2 and argv[2] in ("on", "off"):
        settings["network_checks"] = argv[2] == "on"
        store.save(settings)
        print("Controlli di rete %s." % ("accesi" if settings["network_checks"] else "spenti"))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
