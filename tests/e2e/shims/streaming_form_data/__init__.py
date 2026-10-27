"""Test stand-in for streaming-form-data: buffers the request and parses the multipart body as it arrives."""
import re

from .targets import BaseTarget  # noqa: F401


class ParseFailedException(Exception):
    pass


class StreamingFormDataParser:
    def __init__(self, headers):
        ctype = headers.get("Content-Type", "")
        m = re.search(r'boundary="?([^";]+)"?', ctype)
        if not m:
            raise ParseFailedException("no boundary")
        self.boundary = b"--" + m.group(1).encode()
        self.targets = {}
        self.buffer = b""
        self.done = set()

    def register(self, name, target):
        self.targets.setdefault(name, []).append(target)

    def data_received(self, chunk):
        self.buffer += chunk
        parts = self.buffer.split(self.boundary)
        # every part between two boundaries is complete; the last one may still grow
        for index, part in enumerate(parts[1:-1], start=1):
            if index in self.done:
                continue
            head, _, body = part.partition(b"\r\n\r\n")
            if body.endswith(b"\r\n"):
                body = body[:-2]
            name = re.search(rb'name="([^"]*)"', head)
            filename = re.search(rb'filename="([^"]*)"', head)
            if not name:
                continue
            for target in self.targets.get(name.group(1).decode(), []):
                target.start(filename.group(1).decode() if filename else None)
                target.data(body)
                target.finish()
            self.done.add(index)
