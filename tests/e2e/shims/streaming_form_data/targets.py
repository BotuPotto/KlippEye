"""Test stand-in for streaming-form-data (a compiled library): enough for Moonraker's file upload."""
import hashlib


class BaseTarget:
    def __init__(self, *a, **k):
        self.multipart_filename = None
        self._data = b""

    def start(self, filename=None):
        self.multipart_filename = filename
        self._data = b""

    def data(self, chunk):
        self._data += chunk

    def finish(self):
        pass

    def on_finish(self):
        pass


class ValueTarget(BaseTarget):
    @property
    def value(self):
        return self._data


class NullTarget(BaseTarget):
    pass


class ExceptionTarget(BaseTarget):
    pass


class FileTarget(BaseTarget):
    def __init__(self, filename, *a, **k):
        super().__init__()
        self.filename = filename

    def finish(self):
        with open(self.filename, "wb") as fh:
            fh.write(self._data)


class SHA256Target(BaseTarget):
    @property
    def value(self):
        return hashlib.sha256(self._data).hexdigest()
