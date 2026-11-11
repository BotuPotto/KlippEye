"""A tiny MQTT 3.1.1 broker for the tests (1.100): CONNECT (with an optional user and password), SUBSCRIBE with + and #,
PUBLISH QoS 0 routed to the subscribers, retained messages, the last will when a client goes without DISCONNECT,
PINGREQ. Not for real use."""

import socket
import struct
import sys
import os
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
import mqtt_client as mc  # noqa: E402


def matches(pattern, topic):
    p, t = pattern.split("/"), topic.split("/")
    for i, part in enumerate(p):
        if part == "#":
            return True
        if i >= len(t) or (part != "+" and part != t[i]):
            return False
    return len(p) == len(t)


class FakeBroker:
    def __init__(self, username="", password=""):
        self.username, self.password = username, password
        self.server = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(8)
        self.port = self.server.getsockname()[1]
        self.retained = {}
        self.log = []          # every (topic, payload, retain) published to the broker
        self.clients = []      # [(sock, [patterns], lock)]
        self.connects = []     # (client id, user, accepted)
        self.lock = threading.Lock()
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                sock, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(sock,), daemon=True).start()

    def _send(self, entry, data):
        try:
            with entry[2]:
                entry[0].sendall(data)
        except OSError:
            pass

    def deliver(self, topic, payload, retain):
        with self.lock:
            self.log.append((topic, payload, retain))
            if retain:
                if payload:
                    self.retained[topic] = payload
                else:
                    self.retained.pop(topic, None)
            targets = [c for c in self.clients if any(matches(p, topic) for p in c[1])]
        for entry in targets:
            self._send(entry, mc.publish_packet(topic, payload))

    def publish(self, topic, payload, retain=False):
        """As if another client (Home Assistant) published it."""
        self.deliver(topic, payload.encode() if isinstance(payload, str) else payload, retain)

    def _serve(self, sock):
        reader = mc._Reader(sock)
        entry = (sock, [], threading.Lock())
        will = None
        clean_exit = False
        try:
            kind, body = mc.read_packet(reader)
            if kind >> 4 != 1:
                return
            flags = body[7]
            pos = 10
            def take():
                nonlocal pos
                (n,) = struct.unpack("!H", body[pos:pos + 2])
                value = body[pos + 2:pos + 2 + n]
                pos += 2 + n
                return value
            client_id = take().decode()
            if flags & 0x04:
                will = (take().decode(), take(), bool(flags & 0x20))
            user = take().decode() if flags & 0x80 else ""
            password = take().decode() if flags & 0x40 else ""
            ok = (not self.username) or (user == self.username and password == self.password)
            self.connects.append((client_id, user, ok))
            sock.sendall(mc.packet(0x20, bytes([0, 0 if ok else 4])))
            if not ok:
                return
            with self.lock:
                self.clients.append(entry)
            while True:
                kind, body = mc.read_packet(reader)
                top = kind >> 4
                if top == 3:
                    topic, payload, _ = mc.parse_publish(kind, body)
                    self.deliver(topic, payload, bool(kind & 0x01))
                elif top == 8:
                    packet_id = body[:2]
                    pos = 2
                    while pos < len(body):
                        (n,) = struct.unpack("!H", body[pos:pos + 2])
                        pattern = body[pos + 2:pos + 2 + n].decode()
                        pos += 3 + n
                        entry[1].append(pattern)
                    self._send(entry, mc.packet(0x90, packet_id + b"\x00"))
                    with self.lock:
                        old = [(t, p) for t, p in self.retained.items() if any(matches(x, t) for x in entry[1])]
                    for t, p in old:
                        self._send(entry, mc.publish_packet(t, p, retain=True))
                elif top == 12:
                    self._send(entry, mc.packet(0xD0))
                elif top == 14:
                    clean_exit = True
                    return
        except Exception:
            pass
        finally:
            with self.lock:
                if entry in self.clients:
                    self.clients.remove(entry)
            try:
                sock.close()
            except OSError:
                pass
            if will and not clean_exit:
                self.deliver(will[0], will[1], will[2])

    def drop_clients(self):
        """Closes every connection, as a broker restarting would (the last wills go out)."""
        with self.lock:
            socks = [c[0] for c in self.clients]
        for sock in socks:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def close(self):
        self.server.close()
        self.drop_clients()
