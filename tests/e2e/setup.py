#!/usr/bin/env python3
"""
Prepares the end-to-end test (tests/e2e/e2e_test.py): a real Moonraker, at a fixed commit, in tests/e2e/.work/.

    python3 tests/e2e/setup.py          (once; run again to update it after MOONRAKER_COMMIT changes)
    KLIPPEYE_E2E_NO_PIP=1 python3 tests/e2e/setup.py     (without PyPI: GitHub sources and stand-ins only)

What it does:
  1. clones Moonraker from GitHub at MOONRAKER_COMMIT into .work/moonraker;
  2. makes a virtual environment (.work/venv, with the system packages) and installs Moonraker's requirements with pip;
  3. when pip cannot install a pure-Python requirement (no internet to PyPI, say), it clones its source from GitHub instead
     (.work/deps, added to the path by the test);
  4. compiled libraries that still cannot be imported (dbus-fast, streaming-form-data...) are replaced by the small
     stand-ins in tests/e2e/shims, which are enough for what the test does.
At the end it says what Moonraker will use. Nothing outside tests/e2e/.work is changed.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, ".work")
MOONRAKER_REPO = "https://github.com/Arksine/moonraker.git"
MOONRAKER_COMMIT = "b559b9a81161f958a43c2f527b6ad96f73310d5d"  # 2026-10-21
# module -> (git repository, commit, folder inside it that holds the module): the pure-Python requirements
SOURCES = {
    "tornado": ("https://github.com/tornadoweb/tornado.git", "b5586f3f2956308a9dff1fba2c3ddbbbe1ab29d0", ""),  # v6.5.1
    "inotify_simple": ("https://github.com/chrisjbillington/inotify_simple.git", "2af855f082d0fdbca0192ef110e942179481e105", ""),
    "libnacl": ("https://github.com/saltstack/libnacl.git", "27aa93a7aa6130eef9098c4c22ba2adcb4a1ec20", ""),
    "serial": ("https://github.com/pyserial/pyserial.git", "a5c48d445fbc1943d4fabf8d9090a50fda3172fd", ""),
    "paho": ("https://github.com/eclipse-paho/paho.mqtt.python.git", "6335e3f2d14bce767f9564a00a3044bce7a12799", "src"),
}
SHIMS = ("dbus_fast", "streaming_form_data", "importlib_metadata")
# what Moonraker imports when it starts with the configuration of the test
NEEDED = ("tornado", "inotify_simple", "libnacl", "serial", "paho", "jinja2", "distro", "dbus_fast", "streaming_form_data", "importlib_metadata")


def run(cmd, **kw):
    print("  $ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, **kw)


def fetch(repo, commit, dest):
    """A checkout of `commit` of `repo` in `dest` (only that commit is downloaded)."""
    if os.path.isdir(os.path.join(dest, ".git")):
        head = subprocess.run(["git", "-C", dest, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        if head == commit:
            return
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)
    run(["git", "-C", dest, "init", "-q"], check=True)
    run(["git", "-C", dest, "fetch", "-q", "--depth", "1", repo, commit], check=True)
    run(["git", "-C", dest, "checkout", "-q", "FETCH_HEAD"], check=True)


def importable(python, module, path):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(path))
    return subprocess.run([python, "-c", "import " + module], env=env, capture_output=True).returncode == 0


def main():
    os.makedirs(WORK, exist_ok=True)
    print("1. Moonraker %s" % MOONRAKER_COMMIT[:12])
    moonraker = os.path.join(WORK, "moonraker")
    fetch(MOONRAKER_REPO, MOONRAKER_COMMIT, moonraker)

    print("2. virtual environment and requirements")
    venv = os.path.join(WORK, "venv")
    python = os.path.join(venv, "bin", "python")
    if not os.path.isfile(python):
        run([sys.executable, "-m", "venv", "--system-site-packages", venv], check=True)
    requirements = os.path.join(moonraker, "scripts", "moonraker-requirements.txt")
    lines = [l.strip() for l in open(requirements, encoding="utf-8") if l.strip() and not l.startswith(("#", "--"))]
    if os.environ.get("KLIPPEYE_E2E_NO_PIP"):
        print("  (KLIPPEYE_E2E_NO_PIP set: pip skipped)")
    elif run([python, "-m", "pip", "install", "-q", "--disable-pip-version-check", "--timeout", "20", "--retries", "1"] + lines).returncode != 0:
        print("  pip could not install everything: the missing parts come from GitHub or from the stand-ins")

    print("3. sources of the missing pure-Python requirements")
    path, from_source = [], []
    for module, (repo, commit, inner) in SOURCES.items():
        if importable(python, module, path):
            continue
        dest = os.path.join(WORK, "deps", module)
        fetch(repo, commit, dest)
        path.append(os.path.join(dest, inner) if inner else dest)
        from_source.append(module)

    print("4. stand-ins for the compiled libraries that are still missing")
    shims_dir = os.path.join(WORK, "shims")
    shutil.rmtree(shims_dir, ignore_errors=True)
    os.makedirs(shims_dir)
    shimmed = []
    for module in SHIMS:
        if not importable(python, module, path):
            source = os.path.join(HERE, "shims", module)
            if os.path.isdir(source):
                shutil.copytree(source, os.path.join(shims_dir, module))
            else:
                shutil.copy(source + ".py", shims_dir)
            shimmed.append(module)
    path.append(shims_dir)
    with open(os.path.join(WORK, "pythonpath"), "w") as f:
        f.write(os.pathsep.join(path + [moonraker]) + "\n")

    missing = [m for m in NEEDED if not importable(python, m, path)]
    print("\nMoonraker %s in %s" % (MOONRAKER_COMMIT[:12], moonraker))
    print("  from GitHub sources: %s" % (", ".join(from_source) or "none"))
    print("  stand-ins:           %s" % (", ".join(shimmed) or "none"))
    if missing:
        print("  STILL MISSING:       %s (install them with pip and run this again)" % ", ".join(missing))
        return 1
    print("Ready: python3 tests/e2e/e2e_test.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
