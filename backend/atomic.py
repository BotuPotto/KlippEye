"""
KlippEye - one way to write a file safely: a temporary file next to it, forced to the disk, then swapped in. A power cut
(common on a Raspberry pulled from the wall) leaves the old file or the new one, never half of one. Standard library only.
"""
import os
import tempfile


def write_text(path, text, private=False):
    """`text` into `path`; mode 600 when `private` (keys, passwords), else 644. The folder is made when missing."""
    path = os.path.realpath(path)  # 1.143.0: a link (printer.cfg kept in a config repository) stays a link: its target is written
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=folder)  # a name of its own: two writers never share it
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600 if private else 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
