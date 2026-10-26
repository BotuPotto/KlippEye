"""An HTTP/1.1 keep-alive proxy that can silently kill its connections, the way a sleeping phone's connections die
(NAT / Wi-Fi drop). The mock server closes every connection after one answer (Werkzeug does), so the proxy is the one
that keeps the browser's connections open: it forwards each request to the mock on a fresh connection and answers on
the browser's long-lived one.
After freeze(), every browser connection that exists at that moment swallows what it receives and answers nothing,
without ever being closed: requests sent on it hang for ever. Connections opened afterwards work normally.
Usage: p = Proxy(listen_port, target_port); p.freeze(); p.opened (connections made so far); p.stop()"""
import socket, threading, http.client

HOP = {"connection", "keep-alive", "proxy-connection", "transfer-encoding", "upgrade", "te", "trailer", "content-length"}


class Proxy:
    def __init__(self, listen_port, target_port):
        self.target_port = target_port
        self.server = socket.socket(); self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", listen_port)); self.server.listen(64)
        self.conns = []          # (state, socket): state[0] True = dead
        self.opened = 0
        self.running = True
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while self.running:
            try:
                client, _ = self.server.accept()
            except OSError:
                return
            state = [False]
            self.conns.append((state, client)); self.opened += 1
            threading.Thread(target=self._serve, args=(state, client), daemon=True).start()

    def _forward(self, method, path, headers, body):
        up = http.client.HTTPConnection("127.0.0.1", self.target_port, timeout=120)
        try:
            up.request(method, path, body=body, headers={k: v for k, v in headers.items() if k.lower() not in HOP})
            r = up.getresponse()
            data = r.read()
            return r.status, r.reason, [(k, v) for k, v in r.getheaders() if k.lower() not in HOP], data
        finally:
            up.close()

    def _serve(self, state, client):
        buf = b""
        try:
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    return
                if state[0]:
                    continue                       # dead: swallowed
                buf += chunk
                while b"\r\n\r\n" in buf:
                    head, rest = buf.split(b"\r\n\r\n", 1)
                    lines = head.decode("latin-1").split("\r\n")
                    method, path, _ = lines[0].split(" ", 2)
                    headers = {}
                    for line in lines[1:]:
                        k, _, v = line.partition(":"); headers[k.strip()] = v.strip()
                    length = int(next((v for k, v in headers.items() if k.lower() == "content-length"), 0))
                    if len(rest) < length:
                        break
                    body, buf = rest[:length], rest[length:]
                    status, reason, out_headers, data = self._forward(method, path, headers, body or None)
                    if state[0]:
                        continue                   # frozen while the mock was answering: the answer never gets out
                    msg = f"HTTP/1.1 {status} {reason}\r\n" + "".join(f"{k}: {v}\r\n" for k, v in out_headers)
                    msg += f"Content-Length: {len(data)}\r\nConnection: keep-alive\r\n\r\n"
                    client.sendall(msg.encode("latin-1") + data)
        except (OSError, ValueError):
            pass
        finally:
            if not state[0]:
                try: client.close()
                except OSError: pass

    def alive(self):
        return sum(1 for s, _ in self.conns if not s[0])

    def freeze(self):
        for state, _ in self.conns:
            state[0] = True

    def stop(self):
        self.running = False
        try: self.server.close()
        except OSError: pass
        for _, c in self.conns:
            try: c.close()
            except OSError: pass
