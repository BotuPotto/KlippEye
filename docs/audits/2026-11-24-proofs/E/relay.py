"""HTTPS relay: only the first request head is rewritten. A client that adds any `Upgrade:` header keeps the connection
open, and its next request reaches the service as sent, with its own X-Forwarded-For (trusted from 127.0.0.1)."""
import os, socket, ssl, sys, tempfile, threading, time
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import https_relay
def free():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
received = []
bport, rport = free(), free()
def backend():
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); srv.bind(("127.0.0.1", bport)); srv.listen(5)
    conn, _ = srv.accept(); buf = b""
    while True:
        data = conn.recv(65536)
        if not data: return
        buf += data
        while b"\r\n\r\n" in buf:
            head, buf = buf.split(b"\r\n\r\n", 1); received.append(head.decode())
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
threading.Thread(target=backend, daemon=True).start()
cert, key = https_relay.ensure_certificate(tempfile.mkdtemp(), names=["localhost"], addresses=[])
relay = https_relay.HttpsRelay(rport, bport, cert, key, log=lambda *a: None); relay.start()
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
tls = ctx.wrap_socket(socket.create_connection(("127.0.0.1", rport)), server_hostname="localhost")
tls.sendall(b"POST /api/auth/login HTTP/1.1\r\nHost: x\r\nUpgrade: nothing\r\nConnection: keep-alive\r\nContent-Length: 0\r\n\r\n")
time.sleep(0.3); tls.recv(1000)
tls.sendall(b"POST /api/auth/login HTTP/1.1\r\nHost: x\r\nX-Forwarded-For: 10.9.9.9\r\nContent-Length: 0\r\n\r\n")
time.sleep(0.3)
for i, head in enumerate(received, 1):
    xff = [l for l in head.split("\r\n") if l.lower().startswith("x-forwarded-for")]
    print("request %d reached the service with %s" % (i, xff))
relay.stop()
