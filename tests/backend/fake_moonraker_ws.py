"""A tiny Moonraker WebSocket for the tests of backend/moonraker_live.py: answers printer.objects.subscribe with the
objects it knows, sends notify_status_update and the other notifications on request, sends its load every
`heartbeat` seconds as Moonraker does."""

import base64
import hashlib
import json
import socket
import struct
import threading
import time

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class FakeMoonrakerWS:
    def __init__(self, objects, heartbeat=0.5):
        self.objects = objects          # name -> fields (what "Klipper" has)
        self.heartbeat = heartbeat
        self.ready = True               # Klipper ready: subscriptions are answered
        self.clients = []
        self.subscriptions = []         # what each subscribe asked
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(5)
        self.port = self.server.getsockname()[1]
        self.silent = False             # stop the heartbeat (a dead connection)
        self.lock = threading.Lock()
        threading.Thread(target=self._accept, daemon=True).start()
        threading.Thread(target=self._beat, daemon=True).start()

    def _accept(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _send(self, conn, data):
        payload = json.dumps(data).encode()
        size = len(payload)
        if size < 126:
            header = bytes([0x81, size])
        elif size < 65536:
            header = bytes([0x81, 126]) + struct.pack(">H", size)
        else:
            header = bytes([0x81, 127]) + struct.pack(">Q", size)
        with self.lock:
            try:
                conn.sendall(header + payload)
            except OSError:
                pass

    def broadcast(self, data):
        for conn in list(self.clients):
            self._send(conn, data)

    def update(self, diff):
        for name, fields in diff.items():
            self.objects.setdefault(name, {}).update(fields)
        self.broadcast({"jsonrpc": "2.0", "method": "notify_status_update", "params": [diff, time.time()]})

    def drop_all(self):
        for conn in list(self.clients):
            try:
                conn.shutdown(socket.SHUT_RDWR)
                conn.close()
            except OSError:
                pass
        self.clients = []

    def _beat(self):
        while True:
            time.sleep(self.heartbeat)
            if not self.silent:
                self.broadcast({"jsonrpc": "2.0", "method": "notify_proc_stat_update", "params": [{"cpu_temp": 40}]})

    def _read(self, conn, size):
        data = b""
        while len(data) < size:
            chunk = conn.recv(size - len(data))
            if not chunk:
                raise OSError("closed")
            data += chunk
        return data

    def _serve(self, conn):
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = conn.recv(1024)
            if not chunk:
                return
            head += chunk
        key = [line.split(b":", 1)[1].strip() for line in head.split(b"\r\n") if line.lower().startswith(b"sec-websocket-key")][0]
        accept = base64.b64encode(hashlib.sha1(key + GUID.encode()).digest()).decode()
        conn.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n" % accept).encode())
        self.clients.append(conn)
        try:
            while True:
                first = self._read(conn, 2)
                size = first[1] & 0x7F
                if size == 126:
                    size = struct.unpack(">H", self._read(conn, 2))[0]
                elif size == 127:
                    size = struct.unpack(">Q", self._read(conn, 8))[0]
                mask = self._read(conn, 4)
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(self._read(conn, size)))
                if first[0] & 0x0F == 0x8:
                    return
                if first[0] & 0x0F != 0x1:
                    continue
                message = json.loads(payload)
                if message.get("method") == "printer.objects.subscribe":
                    asked = message["params"]["objects"]
                    self.subscriptions.append(sorted(asked))
                    if not self.ready:
                        self._send(conn, {"jsonrpc": "2.0", "error": {"code": 503, "message": "Klippy Host not ready"}, "id": message["id"]})
                        continue
                    status = {name: dict(self.objects[name]) for name in asked if name in self.objects}
                    self._send(conn, {"jsonrpc": "2.0", "result": {"eventtime": time.time(), "status": status}, "id": message["id"]})
        except (OSError, ValueError):
            pass
        finally:
            if conn in self.clients:
                self.clients.remove(conn)
