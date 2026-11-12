"""HTTPS for the dashboard (1.93): an encrypted entrance next to the usual one.

The KlippEye service answers on http://<raspberry>:8085. When HTTPS is switched on, this file also listens on
https://<raspberry>:8443: each connection is decrypted here and handed to the service on 8085, with two headers that
say who is on the other side (X-Forwarded-For) and that the connection was encrypted (X-Forwarded-Proto: https);
the service trusts them only from this relay (waitress' trusted_proxy, 127.0.0.1). WebSocket upgrades and long
answers (the camera's stream) pass through as they are.

The certificate is made on the Raspberry (openssl, an EC P-256 key, ten years) for its names and addresses: no
authority signed it, so a browser warns the first time and has to be told to trust it. Its SHA-256 fingerprint is
shown in the dashboard, to compare with what the browser shows.
"""

import hashlib
import ipaddress
import os
import select
import socket
import ssl
import subprocess
import threading

MAX_CONNECTIONS = 64
HEAD_LIMIT = 64 * 1024
HANDSHAKE_TIMEOUT_S = 10
IDLE_TIMEOUT_S = 300


def local_addresses():
    """The Raspberry's IPv4 addresses (not 127.x), as far as it can tell without extra packages."""
    found = set()
    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=3).stdout
        found |= {word for word in out.split() if "." in word}
    except Exception:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("10.255.255.255", 1))
        found.add(probe.getsockname()[0])
        probe.close()
    except Exception:
        pass
    out = []
    for address in sorted(found):
        try:
            if ipaddress.ip_address(address).version == 4 and not address.startswith("127."):
                out.append(address)
        except ValueError:
            pass
    return out


def fingerprint(cert_path):
    """The certificate's SHA-256 fingerprint as browsers show it (AB:CD:...)."""
    with open(cert_path, "r", encoding="ascii") as handle:
        der = ssl.PEM_cert_to_DER_cert(handle.read())
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


def ensure_certificate(folder, names=None, addresses=None):
    """(cert, key) in `folder`, made now when missing: self-signed, for the Raspberry's names and addresses."""
    os.makedirs(folder, exist_ok=True)
    cert, key = os.path.join(folder, "https-cert.pem"), os.path.join(folder, "https-key.pem")
    if os.path.exists(cert) and os.path.exists(key):
        return cert, key
    host = socket.gethostname() or "klippeye"
    names = names or [host, host + ".local", "localhost"]
    addresses = (addresses if addresses is not None else local_addresses()) + ["127.0.0.1"]
    san = ",".join(["DNS:" + name for name in dict.fromkeys(names)] + ["IP:" + ip for ip in dict.fromkeys(addresses)])
    subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                    "-days", "3650", "-subj", "/CN=KlippEye " + host, "-addext", "subjectAltName=" + san,
                    "-keyout", key + ".new", "-out", cert + ".new"], check=True, capture_output=True, timeout=60)
    os.chmod(key + ".new", 0o600)
    os.replace(key + ".new", key)
    os.replace(cert + ".new", cert)
    return cert, key


def forward_head(head, client_ip):
    """The request head as it goes to the service: the client's X-Forwarded-* removed and ours added; one request per
    connection (Connection: close) unless it is a WebSocket upgrade."""
    lines = head.split(b"\r\n")
    request_line, headers = lines[0], [line for line in lines[1:] if line]
    upgrade = any(line.lower().startswith(b"upgrade:") for line in headers)
    kept = []
    for line in headers:
        name = line.split(b":", 1)[0].strip().lower()
        if name in (b"x-forwarded-for", b"x-forwarded-proto", b"x-forwarded-host", b"forwarded"):
            continue
        if name in (b"connection", b"keep-alive") and not upgrade:
            continue
        kept.append(line)
    if not upgrade:
        kept.append(b"Connection: close")
    kept += [b"X-Forwarded-For: " + client_ip.encode(), b"X-Forwarded-Proto: https"]
    return b"\r\n".join([request_line] + kept) + b"\r\n\r\n"


def _server_context(cert, key):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    return context


class HttpsRelay:
    """public: (cert, key, name) of the secure address (public_name.py, 1.116), used when the browser asks for that
    name (SNI); everyone else (the address, the Android app) gets the Raspberry's own certificate."""

    def __init__(self, port, backend_port, cert, key, log=print, public=None):
        self.port, self.backend_port, self.log = port, backend_port, log
        self.context = _server_context(cert, key)
        self.public_name = None
        if public:
            self.public_context, self.public_name = _server_context(public[0], public[1]), public[2].lower()
            self.context.sni_callback = self._pick
        self.server = None
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self.stopped = False

    def _pick(self, tls, server_name, _context):
        if server_name and server_name.lower() == self.public_name:
            tls.context = self.public_context
        return None

    def start(self):
        try:  # 1.116: IPv4 and IPv6 (the secure address may point to the IPv6 one)
            server = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            server.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("::", self.port))
        except OSError:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("0.0.0.0", self.port))
        server.listen(32)
        self.server = server
        threading.Thread(target=self._accept, name="https-relay", daemon=True).start()
        self.log("[HTTPS] the dashboard also on https://<raspberry>:%d" % self.port)

    def stop(self):
        self.stopped = True
        if self.server:
            try:
                self.server.shutdown(socket.SHUT_RDWR)  # wakes the accept() waiting in its thread, so the port is free at once
            except OSError:
                pass
            try:
                self.server.close()
            except OSError:
                pass

    def running(self):
        return self.server is not None and not self.stopped

    def _accept(self):
        while not self.stopped:
            try:
                conn, address = self.server.accept()
            except OSError:
                return
            if not self.slots.acquire(blocking=False):
                conn.close()  # too many at once: the browser tries again
                continue
            client = address[0][7:] if address[0].startswith("::ffff:") else address[0]  # an IPv4 client on the IPv6 socket
            threading.Thread(target=self._serve, args=(conn, client), daemon=True).start()

    def _serve(self, raw, client_ip):
        tls = backend = None
        try:
            raw.settimeout(HANDSHAKE_TIMEOUT_S)
            tls = self.context.wrap_socket(raw, server_side=True)
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = tls.recv(16384)
                if not chunk:
                    return
                head += chunk
                if len(head) > HEAD_LIMIT:
                    tls.sendall(b"HTTP/1.1 431 Request Header Fields Too Large\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
                    return
            head, rest = head.split(b"\r\n\r\n", 1)
            backend = socket.create_connection(("127.0.0.1", self.backend_port), timeout=10)
            backend.sendall(forward_head(head, client_ip) + rest)
            tls.settimeout(None)
            backend.settimeout(None)
            self._pump(tls, backend)
        except (OSError, ssl.SSLError, ValueError):
            pass
        finally:
            for one in (backend, tls or raw):
                if one is not None:
                    try:
                        one.close()
                    except OSError:
                        pass
            self.slots.release()

    def _pump(self, tls, backend):
        """Both ways until one side closes (or nothing moves for five minutes)."""
        while True:
            # data already decrypted inside the TLS layer does not wake select: read it first
            ready = [tls] if tls.pending() else select.select([tls, backend], [], [], IDLE_TIMEOUT_S)[0]
            if not ready:
                return
            for source in ready:
                target = backend if source is tls else tls
                data = source.recv(65536)
                if not data:
                    return
                target.sendall(data)
