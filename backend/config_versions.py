"""Release 1.81: the earlier versions of the config files, kept by the KlippEye service.

Before the dashboard's editor writes a file of the config folder over, it hands the text the file had to the service,
which keeps it here (data folder, config_versions/): the last MAX_VERSIONS of each file, newest first, an identical
text only once. The editor lists them, shows what changed and puts one back in the editor (it is saved by hand).
Klipper's own backups (printer-YYYYMMDD_HHMMSS.cfg, written by SAVE_CONFIG) are listed by the dashboard itself.
This file knows nothing of Flask.
"""
import hashlib
import json
import os
import threading
import time

FOLDER = "config_versions"
MAX_VERSIONS = 30
MAX_BYTES = 2 * 1024 * 1024
REASONS = ("save", "restore")


class VersionError(ValueError):
    pass


def clean_path(path):
    """A file's path in the config folder (no leading slash, no ".." or empty parts), or VersionError."""
    if not isinstance(path, str):
        raise VersionError("path")
    path = path.strip().lstrip("/")
    if path.startswith("config/"):
        path = path[len("config/"):]
    if not path or len(path) > 512 or "\x00" in path or "\n" in path or "\\" in path or any(part in ("", ".", "..") for part in path.split("/")):
        raise VersionError("path")
    return path


class ConfigVersions:
    def __init__(self, data_dir, now=time.time):
        self.root = os.path.join(data_dir, FOLDER)
        self.now = now
        self.lock = threading.Lock()

    def _folder(self, path):
        return os.path.join(self.root, hashlib.sha1(path.encode("utf-8")).hexdigest()[:20])

    def _index(self, folder):
        try:
            with open(os.path.join(folder, "index.json"), encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) and isinstance(data.get("versions"), list) else {"versions": []}
        except (OSError, ValueError):
            return {"versions": []}

    def _write_index(self, folder, index):
        tmp = os.path.join(folder, ".index.tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(index, handle, indent=1)
        os.replace(tmp, os.path.join(folder, "index.json"))

    def list(self, path):
        path = clean_path(path)
        with self.lock:
            return [dict(v) for v in self._index(self._folder(path))["versions"]]

    def add(self, path, content, reason="save"):
        """Keeps `content` as the newest version of `path`; the same text as the newest one is not kept twice.
        Answers the version ({id, time, size, lines, reason}), or None when it was the same text."""
        path = clean_path(path)
        if not isinstance(content, str):
            raise VersionError("content")
        data = content.encode("utf-8")
        if len(data) > MAX_BYTES:
            raise VersionError("too_large")
        digest = hashlib.sha1(data).hexdigest()
        with self.lock:
            folder = self._folder(path)
            os.makedirs(folder, exist_ok=True)
            index = self._index(folder)
            versions = index["versions"]
            if versions and versions[0].get("sha1") == digest:
                return None
            stamp = self.now()
            version_id = "%d-%s" % (int(stamp * 1000), digest[:8])
            with open(os.path.join(folder, version_id + ".txt"), "wb") as handle:
                handle.write(data)
            version = {"id": version_id, "time": stamp, "size": len(data), "lines": content.count("\n") + (0 if content.endswith("\n") or not content else 1),
                       "sha1": digest, "reason": reason if reason in REASONS else "save"}
            versions.insert(0, version)
            for old in versions[MAX_VERSIONS:]:
                try:
                    os.remove(os.path.join(folder, old["id"] + ".txt"))
                except OSError:
                    pass
            index = {"path": path, "versions": versions[:MAX_VERSIONS]}
            self._write_index(folder, index)
            return dict(version)

    def read(self, path, version_id):
        path = clean_path(path)
        if not isinstance(version_id, str) or not version_id or any(c not in "0123456789abcdef-" for c in version_id):
            raise VersionError("version")
        with self.lock:
            folder = self._folder(path)
            if not any(v.get("id") == version_id for v in self._index(folder)["versions"]):
                raise VersionError("not_found")
            with open(os.path.join(folder, version_id + ".txt"), "rb") as handle:
                return handle.read().decode("utf-8", errors="replace")
