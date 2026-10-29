#!/usr/bin/env python3
"""KlippEye runs on any Klipper machine, with any user (roadmap phase 5): no file of the program may name a fixed home folder
like /home/pi. The folders come from Moonraker (backend/printer_paths.py) or from the home of the user running KlippEye.

    python3 tests/test_no_fixed_paths.py

Fails, listing file and line, when "/home/<name>/" appears in the program, its scripts, the app or the guides. The tests
themselves (fake paths in fixtures), the changelog (history) and generated files are not checked."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = ["backend", "frontend/src", "scripts", "notifier", "android", "systemd", "ci", "docs", "README.md", "CONTRIBUTING.md"]
SKIP_DIRS = {"__pycache__", "node_modules", "build", ".gradle", ".work"}
EXTENSIONS = (".py", ".js", ".sh", ".md", ".kt", ".kts", ".xml", ".json", ".service", ".conf", ".cfg", ".css", ".html", ".txt")
FIXED = re.compile(r"/home/(?!\$|<|\{)[A-Za-z0-9_.-]+/?")


def files():
    for item in CHECK:
        path = os.path.join(ROOT, item)
        if os.path.isfile(path):
            yield path
        for folder, dirs, names in os.walk(path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in names:
                if name.endswith(EXTENSIONS):
                    yield os.path.join(folder, name)


def main():
    found = []
    for path in files():
        try:
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    if FIXED.search(line):
                        found.append("%s:%d: %s" % (os.path.relpath(path, ROOT), n, line.strip()[:160]))
        except (UnicodeDecodeError, OSError):
            continue
    for line in found:
        print("  FIXED PATH  " + line)
    print("%d fixed home folder(s) found" % len(found))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
