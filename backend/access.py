#!/usr/bin/env python3
"""
KlippEye - access: optional password, access tokens, network checks (host name and origin of requests).

Used by the backend (import) and from the terminal, for example through `klippeye password`:

    python3 access.py status                    is the password on, which host names are allowed
    python3 access.py set                       asks for a new password (twice) and turns it on
    python3 access.py remove                    removes the password (forgotten password: needs access to the Raspberry)
    python3 access.py logout-all                every device has to log in again
    python3 access.py guest-set                 asks for a guest password (1.82: look only, no commands)
    python3 access.py guest-remove              removes the guest password (guests are logged out)
    python3 access.py host-add NAME             allows one more host name (e.g. printer.example.com)
    python3 access.py host-remove NAME
    python3 access.py network-checks on|off     turns the host/origin checks on or off (off = behaviour before 1.2.0)

Data lives in <data dir>/access.json (mode 600): never the password, only its salted PBKDF2 hash.
Standard library only: nothing to install.
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
ITERATIONS = 120000          # PBKDF2-SHA256: about half a second on a slow Raspberry, unnoticeable for a one-off login
COOKIE_NAME = "klippeye_session"
TOKEN_DAYS = 180             # log in again after six months
HEADER_INTERNAL = "X-KlippEye-Token"   # services on the Raspberry (notifier, CLI) present the internal token
MIN_PASSWORD = 6
MAX_PASSWORD = 256
LOCAL_SUFFIXES = (".local", ".lan", ".home", ".internal", ".home.arpa", ".localdomain")


# ---------------------------------------------------------------------------------------------------------------------
# files
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
            "secret": secrets.token_hex(32), "generation": 1, "allowed_hosts": [], "network_checks": True,
            # 1.82: a second password for guests, who can look but not command (only with the main password on)
            "guest_enabled": False, "guest_salt": "", "guest_hash": "", "guest_iterations": ITERATIONS, "guest_generation": 1}


class Store:
    """access.json, read again when it changes on disk (shared by the CLI and the backend)."""

    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, "access.json")
        self.internal_path = os.path.join(data_dir, "internal.token")
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
                    fresh = True   # damaged (e.g. power loss): start again without a password rather than locking the owner out
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
        """The token of the services on the Raspberry: created once, mode 600, readable only by the service user."""
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
# passwords and tokens
# ---------------------------------------------------------------------------------------------------------------------

def check_new_password(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        return "The password must be at least %d characters long" % MIN_PASSWORD
    if len(password) > MAX_PASSWORD:
        return "Password too long"
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
    settings["generation"] = int(settings.get("generation") or 1) + 1   # tokens issued before stop working
    return settings


def verify_guest_password(settings, password):
    """The guest password, when there is one (and the main password is on: without it everyone may do everything)."""
    if not settings.get("enabled") or not settings.get("guest_enabled") or not settings.get("guest_hash"):
        return False
    return verify_password({"enabled": True, "salt": settings.get("guest_salt"), "hash": settings.get("guest_hash"), "iterations": settings.get("guest_iterations")}, password)


def set_guest_password(settings, password):
    salt, digest = hash_password(password)
    settings.update({"guest_enabled": True, "guest_salt": salt, "guest_hash": digest, "guest_iterations": ITERATIONS})
    settings["guest_generation"] = int(settings.get("guest_generation") or 1) + 1   # guests logged in before must log in again
    return settings


def clear_guest_password(settings):
    settings.update({"guest_enabled": False, "guest_salt": "", "guest_hash": ""})
    settings["guest_generation"] = int(settings.get("guest_generation") or 1) + 1
    return settings


def clear_password(settings):
    settings.update({"enabled": False, "salt": "", "hash": "", "guest_enabled": False, "guest_salt": "", "guest_hash": ""})
    settings["generation"] = int(settings.get("generation") or 1) + 1
    return settings


def _b64(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_token(settings, now=None, role="admin"):
    now = int(now or time.time())
    data = {"v": 1, "exp": now + TOKEN_DAYS * 86400, "gen": int(settings.get("generation") or 1)}
    if role == "guest":
        data.update({"role": "guest", "ggen": int(settings.get("guest_generation") or 1)})
    body = _b64(json.dumps(data, separators=(",", ":")).encode())
    sig = _b64(hmac.new(bytes.fromhex(settings["secret"]), body.encode("ascii"), hashlib.sha256).digest())
    return body + "." + sig


def token_valid(settings, token, now=None):
    return token_role(settings, token, now) is not None


def token_role(settings, token, now=None):
    """Who the token is for: "admin" (the password), "guest" (the guest password, 1.82), or None (not valid)."""
    if not token or not isinstance(token, str) or token.count(".") != 1 or len(token) > 512:
        return None
    body, sig = token.split(".")
    try:
        expected = _b64(hmac.new(bytes.fromhex(settings["secret"]), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, sig):
            return None
        data = json.loads(_unb64(body))
        if not (data.get("v") == 1 and int(data.get("gen", -1)) == int(settings.get("generation") or 1) and int(data.get("exp", 0)) > int(now or time.time())):
            return None
        if data.get("role") == "guest":
            ok = settings.get("guest_enabled") and int(data.get("ggen", -1)) == int(settings.get("guest_generation") or 1)
            return "guest" if ok else None
        return "admin" if data.get("role") in (None, "admin") else None
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


# ---------------------------------------------------------------------------------------------------------------------
# 1.82: what a guest may do: look (the printer, the camera, the files to print, the history), never command, never read
# the configuration, the logs or the settings (they hold keys and passwords). Everything else is refused.
# ---------------------------------------------------------------------------------------------------------------------
GUEST_GET_EXACT = {
    "/", "/api/auth/status", "/api/health", "/api/status", "/api/printer", "/api/version", "/api/app/version", "/api/logos",
    "/api/print/detector/status", "/api/print/last_analysis", "/api/print/alerts/history", "/api/print/snapshot",
    "/api/camera/snapshot", "/api/schedule", "/api/printers/self", "/api/macros/list",
    "/printer/info", "/printer/gcode/help", "/printer/query_endstops/status",
    "/server/info", "/server/files/list", "/server/files/metadata", "/server/files/directory", "/server/files/content",
    "/server/history/list", "/server/history/totals", "/server/history/job", "/server/job_queue/status",
    "/server/temperature_store", "/server/gcode_store", "/server/webcams/list", "/server/spoolman/status",
    "/server/spoolman/spool_id", "/server/database/item",
    "/machine/system_info", "/machine/proc_stats", "/machine/update/status", "/machine/device_power/devices",
    "/machine/timelapse/lastframeinfo",
}
GUEST_GET_PREFIXES = ("/logos/", "/api/print/alerts/image/", "/api/shaper/", "/printer/objects/", "/server/files/gcodes/",
                      "/webcam")
GUEST_POST = {"/api/auth/logout"}
GUEST_FILE_ROOTS = ("gcodes", "timelapse")   # the folders a guest may list or read (never config: it holds keys)


def guest_may(method, path, args=None):
    """True when a guest may make this request. `args`: the query string as a dict."""
    args = args or {}
    method = (method or "").upper()
    if method == "POST":
        return path in GUEST_POST
    if method not in ("GET", "HEAD"):
        return False
    if "/.." in path or "//" in path:
        return False
    if path == "/server/files/list" or path == "/server/files/content":
        return str(args.get("root") or "gcodes") in GUEST_FILE_ROOTS
    if path == "/server/files/directory":
        return str(args.get("path") or "gcodes").strip("/").split("/")[0] in GUEST_FILE_ROOTS
    if path == "/machine/update/status":
        return str(args.get("refresh") or "false").lower() in ("false", "0", "")
    if path in GUEST_GET_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in GUEST_GET_PREFIXES)


class Throttle:
    """After 5 wrong passwords from the same address, a wait that doubles each time (2, 4, 8... up to 5 minutes)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.failures = {}   # ip -> (count, wait until)

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
            if len(self.failures) > 1000:   # bounded memory
                self.failures.pop(next(iter(self.failures)))

    def ok(self, ip):
        with self.lock:
            self.failures.pop(ip, None)


# ---------------------------------------------------------------------------------------------------------------------
# network checks: the host name the Raspberry is called with (against DNS rebinding) and the origin of requests
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
    """An IP address, 'localhost', a dotless name (the Raspberry's own name), a home-network name (.local, .lan...), or a
    name added with `klippeye access host-add`. Not an arbitrary internet domain that happens to point at the Raspberry."""
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
    """The origin declared by the browser is the Raspberry itself: same host and port (the http/https scheme is ignored,
    so it also works behind a proxy that adds https)."""
    if not origin or origin == "null" or "://" not in origin:
        return False
    return origin.split("://", 1)[1].lower().rstrip("/") == (host_header or "").strip().lower()


# ---------------------------------------------------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------------------------------------------------

def _ask_password():
    import getpass
    while True:
        first = getpass.getpass("New password (at least %d characters): " % MIN_PASSWORD)
        problem = check_new_password(first)
        if problem:
            print(problem)
            continue
        if getpass.getpass("Repeat it: ") != first:
            print("The two passwords do not match, try again.")
            continue
        return first


def main(argv):
    store = Store(data_dir_default())
    cmd = argv[1] if len(argv) > 1 else "status"
    settings = store.load()
    if cmd == "status":
        print("Password: %s" % ("ON" if settings["enabled"] else "off (anyone who can reach the dashboard can use it)"))
        print("Guest password (look only): %s" % ("ON" if settings["enabled"] and settings.get("guest_enabled") else "off"))
        print("Network checks (host name and origin of requests): %s" % ("on" if settings.get("network_checks", True) else "OFF"))
        extra = settings.get("allowed_hosts") or []
        print("Extra host names: %s" % (", ".join(extra) if extra else "none (IP addresses, .local/.lan names and the Raspberry's own name are always allowed)"))
        print("File: %s" % store.path)
        return 0
    if cmd == "set":
        password = argv[2] if len(argv) > 2 and argv[2] != "-" else _ask_password()
        problem = check_new_password(password)
        if problem:
            print(problem)
            return 1
        store.save(set_password(settings, password))
        print("Password set. Every device will have to log in.")
        return 0
    if cmd == "remove":
        store.save(clear_password(settings))
        print("Password removed: the dashboard opens without logging in again.")
        return 0
    if cmd == "guest-set":
        if not settings["enabled"]:
            print("Set the main password first (access.py set): without it everyone can already do everything.")
            return 1
        password = argv[2] if len(argv) > 2 and argv[2] != "-" else _ask_password()
        problem = check_new_password(password)
        if problem:
            print(problem)
            return 1
        if verify_password(settings, password):
            print("The guest password must be different from the main one.")
            return 1
        store.save(set_guest_password(settings, password))
        print("Guest password set: who logs in with it can look, not command.")
        return 0
    if cmd == "guest-remove":
        store.save(clear_guest_password(settings))
        print("Guest password removed: guests are logged out.")
        return 0
    if cmd == "logout-all":
        settings["generation"] = int(settings.get("generation") or 1) + 1
        store.save(settings)
        print("Done: every device will have to log in again.")
        return 0
    if cmd in ("host-add", "host-remove") and len(argv) > 2:
        name = split_host(argv[2])
        hosts = [h for h in settings.get("allowed_hosts") or [] if h != name]
        if cmd == "host-add":
            hosts.append(name)
        settings["allowed_hosts"] = hosts
        store.save(settings)
        print("Extra host names: %s" % (", ".join(hosts) or "none"))
        return 0
    if cmd == "network-checks" and len(argv) > 2 and argv[2] in ("on", "off"):
        settings["network_checks"] = argv[2] == "on"
        store.save(settings)
        print("Network checks %s." % ("on" if settings["network_checks"] else "off"))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
