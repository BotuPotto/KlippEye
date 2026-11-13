"""One live connection from the KlippEye service to Moonraker (1.92).

Every dashboard open on a phone or a computer asks the printer's state several times a second (temperatures, fans,
position, the print...). Until now each of those questions went on to Moonraker and Klipper. Here the service keeps a
single WebSocket to Moonraker, subscribes to the objects the dashboards ask for and receives their changes as they
happen; the questions are then answered from this copy, at once, without touching Moonraker.

- `query(objects)`: the status of these objects ({name: [fields] or None}) from the copy, or None when it cannot
  answer (not connected, Klipper not ready, an object not subscribed yet). Then the caller asks Moonraker as before
  and calls `want(names)`: the objects are added to the subscription.
- Klipper restarting or shutting down: the copy stops answering until Klipper is ready and the subscription is
  renewed. No message for a while (Moonraker sends its load every second): the connection is replaced.
- Nothing to install: a small WebSocket client (RFC 6455) on a plain socket.
"""

import base64
import json
import os
import random
import select
import socket
import struct
import threading
import time
from urllib.parse import urlparse

# not kept live: configfile is large and changes only when Klipper restarts (it is read now and then anyway)
NOT_LIVE = {"configfile"}
MAX_OBJECTS = 300
SILENCE_S = 12.0          # no message for this long: the connection is dead
RETRY_S = (2, 5, 10, 30)  # waits before connecting again, growing while Moonraker is away
RESUBSCRIBE_DELAY_S = 0.15


class WebSocketClosed(Exception):
    pass


class MiniWebSocket:
    """A text-only WebSocket client: enough for Moonraker's JSON-RPC."""

    def __init__(self, url, timeout=5.0):
        parts = urlparse(url)
        self.sock = socket.create_connection((parts.hostname, parts.port or 80), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        path = parts.path or "/"
        request = ("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n") % (path, parts.hostname, parts.port or 80, key)
        self.sock.sendall(request.encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise WebSocketClosed("no handshake")
            head += chunk
            if len(head) > 16384:
                raise WebSocketClosed("handshake too long")
        head, self.buffer = head.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise WebSocketClosed("handshake refused: " + head.split(b"\r\n", 1)[0].decode(errors="replace"))
        self.sock.settimeout(10.0)  # inside a message the rest follows at once; waiting for one uses select
        self.lock = threading.Lock()

    def _read(self, size):
        while len(self.buffer) < size:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise WebSocketClosed("closed")
            self.buffer += chunk
        data, self.buffer = self.buffer[:size], self.buffer[size:]
        return data

    def send_frame(self, opcode, payload):
        header = bytes([0x80 | opcode])
        size = len(payload)
        if size < 126:
            header += bytes([0x80 | size])
        elif size < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", size)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", size)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        with self.lock:
            self.sock.sendall(header + mask + masked)

    def send_text(self, text):
        self.send_frame(0x1, text.encode())

    def receive(self):
        """The next text message (str), or None when nothing arrived within a second."""
        if not self.buffer and not select.select([self.sock], [], [], 1.0)[0]:
            return None
        message = b""
        while True:
            first = self._read(2)
            fin, opcode = first[0] & 0x80, first[0] & 0x0F
            size = first[1] & 0x7F
            if size == 126:
                size = struct.unpack(">H", self._read(2))[0]
            elif size == 127:
                size = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if first[1] & 0x80 else None
            payload = self._read(size) if size else b""
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x8:
                raise WebSocketClosed("closed by Moonraker")
            if opcode == 0x9:
                self.send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode in (0x1, 0x2):
                message = payload
            elif opcode == 0x0:
                message += payload
            if fin:
                return message.decode("utf-8", "replace")

    def close(self):
        try:
            self.send_frame(0x8, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class MoonrakerLive:
    def __init__(self, moonraker_url, log=print):
        parts = urlparse(moonraker_url)
        self.ws_url = "ws://%s:%d/websocket" % (parts.hostname or "127.0.0.1", parts.port or 80)
        self.log = log
        self.lock = threading.Lock()
        self.status = {}          # object -> its fields, kept up to date
        self.subscribed = set()   # what the subscription Moonraker answered covers
        self.wanted = set()       # what the dashboards asked for
        self.ready = False        # connected, Klipper ready, subscription answered
        self.last_message = 0.0
        self.eventtime = 0.0
        self.ws = None
        self.next_id = 1
        self.subscribe_id = None
        self.resubscribe_at = 0.0
        self.thread = None
        self.stopped = False
        self.failures = 0
        self.answered = 0         # questions answered from the copy (for the diagnostics)

    # ---- the dashboards' side ----------------------------------------------------------------------------------
    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, name="moonraker-live", daemon=True)
            self.thread.start()

    def stop(self):
        self.stopped = True
        if self.ws:
            self.ws.close()

    def want(self, names):
        names = {name for name in names if name and name not in NOT_LIVE}
        with self.lock:
            new = names - self.wanted
            if not new or len(self.wanted) >= MAX_OBJECTS:
                return
            self.wanted |= set(list(new)[: MAX_OBJECTS - len(self.wanted)])
            self.resubscribe_at = time.time() + RESUBSCRIBE_DELAY_S
        self.start()

    def live(self):
        return self.ready and time.time() - self.last_message < SILENCE_S

    def query(self, objects):
        """{name: fields or None} -> {name: {...}} from the copy, or None."""
        if not objects or not self.live():
            return None
        with self.lock:
            if any(name in NOT_LIVE or name not in self.subscribed for name in objects):
                return None
            out = {}
            for name, fields in objects.items():
                if name not in self.status:
                    continue  # Klipper has no such object: Moonraker leaves it out too
                values = self.status[name]
                out[name] = {key: values[key] for key in fields if key in values} if fields else dict(values)
            self.answered += 1
            return out

    def info(self):
        return {"connected": self.ws is not None, "live": self.live(), "objects": len(self.subscribed), "answered": self.answered}

    # ---- the connection --------------------------------------------------------------------------------------------
    def _send(self, method, params=None):
        with self.lock:
            ident = self.next_id
            self.next_id += 1
        self.ws.send_text(json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}, "id": ident}))
        return ident

    def _subscribe(self):
        with self.lock:
            objects = sorted(self.wanted)
            self.resubscribe_at = 0.0
        if not objects:
            return
        self.subscribe_id = self._send("printer.objects.subscribe", {"objects": {name: None for name in objects}})
        self.pending_subscription = set(objects)

    def _handle(self, data):
        method = data.get("method")
        if method == "notify_status_update":
            params = data.get("params") or [{}]
            with self.lock:
                for name, fields in (params[0] or {}).items():
                    if isinstance(fields, dict):
                        self.status.setdefault(name, {}).update(fields)
                if len(params) > 1 and isinstance(params[1], (int, float)):
                    self.eventtime = params[1]
        elif method in ("notify_klippy_disconnected", "notify_klippy_shutdown"):
            with self.lock:
                self.ready = False
                self.subscribed = set()
        elif method == "notify_klippy_ready":
            self.resubscribe_at = time.time()
        elif data.get("id") is not None and data.get("id") == self.subscribe_id:
            result = data.get("result")
            if isinstance(result, dict):
                with self.lock:
                    self.status = {name: dict(fields) for name, fields in (result.get("status") or {}).items()}
                    self.subscribed = set(getattr(self, "pending_subscription", set()))
                    self.eventtime = result.get("eventtime", self.eventtime)
                    self.ready = True
            else:  # Klipper not ready: try again in a moment
                with self.lock:
                    self.ready = False
                self.resubscribe_at = time.time() + 2.0

    def _run(self):
        while not self.stopped:
            try:
                self.ws = MiniWebSocket(self.ws_url)
                if self.failures:
                    self.log("[LIVE] connected to Moonraker again")
                self.failures = 0
                self.last_message = time.time()
                self.resubscribe_at = time.time()
                while not self.stopped:
                    if self.resubscribe_at and time.time() >= self.resubscribe_at:
                        self._subscribe()
                    text = self.ws.receive()
                    if text is None:
                        if time.time() - self.last_message > SILENCE_S:
                            raise WebSocketClosed("silent")
                        continue
                    self.last_message = time.time()
                    try:
                        self._handle(json.loads(text))
                    except ValueError:
                        pass
            except Exception as error:
                if self.failures == 0 and not self.stopped:
                    self.log("[LIVE] no live connection to Moonraker (%s): the dashboards ask it directly" % error)
                self.failures += 1
            finally:
                with self.lock:
                    self.ready = False
                    self.subscribed = set()
                if self.ws:
                    self.ws.close()
                self.ws = None
            if not self.stopped:
                time.sleep(RETRY_S[max(0, min(self.failures, len(RETRY_S)) - 1)] + random.random())


def parse_query(args):
    """Flask's request.args of /printer/objects/query -> {name: [fields] or None}."""
    out = {}
    for name in args.keys():
        value = args.get(name, "")
        out[name] = [field for field in value.split(",") if field] or None
    return out
