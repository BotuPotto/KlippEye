"""Tests of ci/release.py (when a release gets its vX.Y.Z tag) on throw-away git repositories. Usage: python3 release_test.py"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "ci"))
import release  # noqa: E402

FAILS = []


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if extra != "" and not cond else ""))


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def world():
    """A bare "GitHub" origin and a clone, like the checkout of the workflow."""
    base = tempfile.mkdtemp(prefix="release-test-")
    origin, work = os.path.join(base, "origin.git"), os.path.join(base, "work")
    sh(base, "git", "init", "-q", "--bare", "-b", "main", origin)
    sh(base, "git", "clone", "-q", origin, work)
    for key, value in (("user.name", "t"), ("user.email", "t@t")):
        sh(work, "git", "config", key, value)
    return work


def commit(work, files, message):
    for path, text in files.items():
        full = os.path.join(work, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "w").write(text)
    sh(work, "git", "add", "-A")
    sh(work, "git", "commit", "-q", "-m", message)
    sh(work, "git", "push", "-q", "origin", "HEAD:main")
    sh(work, "git", "fetch", "-q", "origin")
    return sh(work, "git", "rev-parse", "HEAD")


CHANGELOG = "# Changelog\n\n## 1.1.0\n\n* New thing.\n* Other thing.\n\n## 1.0.0\n\n* First.\n"

# --- a plain release: tested commit = tip
w = world()
a = commit(w, {"VERSION": "1.0.0\n", "CHANGELOG.md": CHANGELOG}, "first")
d = release.decide(w, a)
ok("tests passed on the tip: tag v1.0.0 on it", d["tag"] and d["version"] == "1.0.0" and d["sha"] == a, d)
ok("... the notes are the CHANGELOG section of that release", d["notes"] == "* First.", d.get("notes"))
release.main(["--tested-sha", a, "--repo", w])
ok("main(): the annotated tag is created and pushed to GitHub", sh(w, "git", "ls-remote", "--tags", "origin") .count("refs/tags/v1.0.0") >= 1 and sh(w, "git", "cat-file", "-t", "v1.0.0") == "tag")
d = release.decide(w, a)
ok("once tagged: not again (VERSION must be raised for a new release)", not d["tag"] and "already exists" in d["reason"], d)

# --- the same VERSION in a later commit: no second tag
b = commit(w, {"README.md": "x\n"}, "docs")
d = release.decide(w, b)
ok("a later commit with the same VERSION is not tagged", not d["tag"] and "already exists" in d["reason"], d)

# --- a newer change than the tested commit: its own tests decide
c = commit(w, {"VERSION": "1.1.0\n", "backend.py": "x\n"}, "1.1.0")
d = release.decide(w, b)
ok("changes newer than the tested commit (not only apk/): no tag now", not d["tag"] and "newer than the tested commit" in d["reason"], d)
d = release.decide(w, c)
ok("their tests passed: tag v1.1.0, with its notes", d["tag"] and d["version"] == "1.1.0" and d["notes"] == "* New thing.\n* Other thing.", d)

# --- a release with a new Android app: the tag waits for the app workflow's commit
w = world()
commit(w, {"VERSION": "1.0.0\n", "android/VERSION": "1.0.0\n", "apk/version.json": json.dumps({"version": "1.0.0"})}, "first")
m = commit(w, {"VERSION": "1.2.0\n", "android/VERSION": "1.1.0\n", "android/app.kt": "new\n"}, "merge 1.2.0 with app 1.1.0")
d = release.decide(w, m)
ok("android/VERSION newer than the built app: the tag waits for the App Android workflow", not d["tag"] and "not built yet" in d["reason"], d)
apk = commit(w, {"apk/version.json": json.dumps({"version": "1.1.0"}), "apk/KlippEye.apk": "binary\n"}, "App Android 1.1.0")
d = release.decide(w, m)
ok("after the app commit (only apk/ changed since the tested merge): tag v1.2.0 on the app commit", d["tag"] and d["sha"] == apk and d["version"] == "1.2.0", d)
d = release.decide(w, "0" * 40)
ok("an unknown tested commit: no tag", not d["tag"], d)

# --- a broken VERSION is never tagged
w = world()
x = commit(w, {"VERSION": "sviluppo\n"}, "x")
d = release.decide(w, x)
ok("VERSION without a release number: no tag", not d["tag"] and "release number" in d["reason"], d)
release.main(["--tested-sha", x, "--repo", w])
ok("main() with nothing to tag ends without error and without tags", sh(w, "git", "tag") == "")

print("FAILS:", FAILS if FAILS else "none")
sys.exit(1 if FAILS else 0)
