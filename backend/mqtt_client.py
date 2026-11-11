"""A small MQTT 3.1.1 client (1.100), with only Python's standard library: KlippEye talks to a broker (the Mosquitto
add-on of Home Assistant, or any other) without installing anything on the Raspberry.

What it does: connects (user and password, TLS if asked), keeps the connection alive (PINGREQ), leaves a "last will"
(the broker publishes it when KlippEye disappears), publishes with QoS 0 (retained or not), subscribes with QoS 0 and
hands the messages that arrive to a function. When the connection drops it tries again, waiting a little longer each time
(2, 4, 8... up to 60 seconds). What is published while it is not connected is dropped: the bridge publishes the whole
state again on every connection.
"""

import select
import socket
import ssl
import struct
import threading
import time

CONNACK_ERRORS = {
    1: "the broker refused the protocol version",
    2: "the broker refused the client name",
    3: "the broker is not available",
    4: "wrong user name or password",
    5: "not authorised",
}


class MqttError(Exception):
    pass


def _string(text):
    data = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    return struct.pack("!H", len(data)) + data


def _length(n):
    out = bytearray()
    while True:
        byte, n = n % 128, n // 128
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def packet(kind, body=b""):
    return bytes([kind]) + _length(len(body)) + body


def connect_packet(client_id, username="", password="", keepalive=30, will=None):
    flags = 0x02  # clean session
    payload = _string(client_id)
    if will:
        topic, message, retain = will
        flags |= 0x04 | (0x20 if retain else 0)
        payload += _string(topic) + _string(message)
    if username:
        flags |= 0x80
        payload += _string(username)
        if password:
            flags |= 0x40
            payload += _string(password)
    return packet(0x10, _string("MQTT") + bytes([4, flags]) + struct.pack("!H", keepalive) + payload)


def publish_packet(topic, payload, retain=False):
    data = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
    return packet(0x30 | (0x01 if retain else 0), _string(topic) + data)


def subscribe_packet(packet_id, topics):
    return packet(0x82, struct.pack("!H", packet_id) + b"".join(_string(t) + b"\x00" for t in topics))


def read_packet(sock_file):
    """(kind byte, body) from a file-like reader; raises MqttError on a closed connection."""
    first = sock_file.read(1)
    if not first:
        raise MqttError("the broker closed the connection")
    multiplier, length = 1, 0
    for _ in range(4):
        byte = sock_file.read(1)
        if not byte:
            raise MqttError("the broker closed the connection")
        length += (byte[0] & 0x7F) * multiplier
        if not byte[0] & 0x80:
            break
        multiplier *= 128
    body = b""
    while len(body) < length:
        chunk = sock_file.read(length - len(body))
        if not chunk:
            raise MqttError("the broker closed the connection")
        body += chunk
    return first[0], body


def parse_publish(kind, body):
    """(topic, payload bytes, packet id or None)."""
    (size,) = struct.unpack("!H", body[:2])
    topic = body[2:2 + size].decode("utf-8", "replace")
    rest = body[2 + size:]
    qos = (kind >> 1) & 0x03
    packet_id = None
    if qos:
        (packet_id,) = struct.unpack("!H", rest[:2])
        rest = rest[2:]
    return topic, rest, packet_id


class _Reader:
    """Reads exactly what is asked from a socket (TLS or not)."""

    def __init__(self, sock):
        self.sock = sock

    def read(self, n):
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                return data
            data += chunk
        return data


class MqttClient:
    def __init__(self, host, port=1883, client_id="klippeye", username="", password="", tls=False, keepalive=30, will=None,
                 subscriptions=(), on_message=None, on_connect=None, timeout=10):
        self.host, self.port, self.client_id = host, int(port), client_id
        self.username, self.password, self.tls = username or "", password or "", bool(tls)
        self.keepalive, self.will, self.timeout = int(keepalive), will, timeout
        self.subscriptions = list(subscriptions)
        self.on_message, self.on_connect = on_message, on_connect
        self.sock = None
        self.lock = threading.Lock()
        self.connected = False
        self.error = None
        self.since = None
        self._stop = threading.Event()
        self._thread = None
        self._packet_id = 0

    # --- one connection ------------------------------------------------------------------------------------------
    def connect_once(self):
        raw = socket.create_connection((self.host, self.port), timeout=self.timeout)
        if self.tls:
            context = ssl.create_default_context()
            raw = context.wrap_socket(raw, server_hostname=self.host)
        raw.settimeout(self.timeout)
        raw.sendall(connect_packet(self.client_id, self.username, self.password, self.keepalive, self.will))
        kind, body = read_packet(_Reader(raw))
        if kind >> 4 != 2 or len(body) < 2:
            raw.close()
            raise MqttError("the broker did not answer as an MQTT broker")
        if body[1] != 0:
            raw.close()
            raise MqttError(CONNACK_ERRORS.get(body[1], "the broker refused the connection (%d)" % body[1]))
        self.sock = raw
        if self.subscriptions:
            self._packet_id = self._packet_id % 65535 + 1
            raw.sendall(subscribe_packet(self._packet_id, self.subscriptions))
        self.connected, self.error, self.since = True, None, time.time()

    def close(self):
        self.connected = False
        sock, self.sock = self.sock, None
        if sock:
            try:
                sock.sendall(packet(0xE0))
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def publish(self, topic, payload, retain=False):
        """False when it could not be sent now (not connected, or the connection broke)."""
        data = publish_packet(topic, payload, retain)
        with self.lock:
            if not self.sock:
                return False
            try:
                self.sock.sendall(data)
                return True
            except OSError as error:
                self.error = str(error)
                self.close()
                return False

    def _send(self, data):
        with self.lock:
            if self.sock:
                self.sock.sendall(data)

    def serve(self):
        """Reads until the connection breaks (or stop): PINGREQ every half keepalive, messages to on_message."""
        reader = _Reader(self.sock)
        last_ping = time.time()
        while not self._stop.is_set() and self.sock:
            ready, _, _ = select.select([self.sock], [], [], 1.0)
            if not ready and not (hasattr(self.sock, "pending") and self.sock.pending()):
                if time.time() - last_ping >= self.keepalive / 2:
                    self._send(packet(0xC0))
                    last_ping = time.time()
                continue
            kind, body = read_packet(reader)
            if kind >> 4 == 3:
                topic, payload, packet_id = parse_publish(kind, body)
                if packet_id is not None:
                    self._send(packet(0x40, struct.pack("!H", packet_id)))
                if self.on_message:
                    try:
                        self.on_message(topic, payload)
                    except Exception as error:  # noqa: BLE001 - one bad message must not drop the connection
                        print("[MQTT] message on %s not handled: %s" % (topic, error))
            if time.time() - last_ping >= self.keepalive / 2:
                self._send(packet(0xC0))
                last_ping = time.time()

    # --- the thread that keeps it connected ------------------------------------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="mqtt", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        with self.lock:
            self.close()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        wait = 2
        while not self._stop.is_set():
            try:
                self.connect_once()
                wait = 2
                print("[MQTT] connected to %s:%d" % (self.host, self.port))
                if self.on_connect:
                    self.on_connect()
                self.serve()
            except Exception as error:  # noqa: BLE001 - kept for the page, then tried again
                self.error = str(error) or error.__class__.__name__
                if self.connected:
                    print("[MQTT] connection lost: %s" % self.error)
            with self.lock:
                self.close()
            if self._stop.wait(wait):
                break
            wait = min(60, wait * 2)


def test_connection(host, port=1883, username="", password="", tls=False, timeout=6):
    """(ok, message): connects once and leaves, for the «Test» button."""
    client = MqttClient(host, port, "klippeye-test-%d" % int(time.time()), username, password, tls, timeout=timeout)
    try:
        client.connect_once()
        return True, ""
    except (OSError, MqttError, ssl.SSLError) as error:
        return False, str(error) or error.__class__.__name__
    finally:
        client.close()
