#!/usr/bin/env python3
"""
End-to-end test of KlippEye on a simulated Raspberry Pi: the real install script, the real backend and notifier, a real
Moonraker (tests/e2e/setup.py prepares it) and a local "GitHub" to update from. See tests/e2e/README.md.

    python3 tests/e2e/e2e_test.py              every scenario
    python3 tests/e2e/e2e_test.py -k NAME      only the scenarios whose name contains NAME

Each scenario builds a fresh world in tests/e2e/.work/worlds/<scenario>:
  * a fake home folder with printer_data/ and Moonraker's configuration;
  * a small systemd (fakebin/systemctl) that really starts and stops the programs of the .service files;
  * a bare git repository playing GitHub, and the "developer's computer" that pushes releases to it (tagged vX.Y.Z, as the
    release workflow does);
  * the program cloned from that GitHub into ~/klippeye, as the guide says, then scripts/install.sh.
Scenarios: install, update, undo, channel, fails, no-um, printing, ui, app, blackout, safety.
"ui" and "app" need Playwright with Chromium (pip install playwright; playwright install chromium) and are skipped
without it; the Kotlin part of "app" also needs kotlinc and java (KOTLINC_HOME or kotlinc on the PATH).
"""
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
WORK = os.path.join(HERE, ".work")
WORLDS = os.path.join(WORK, "worlds")
FAKEBIN = os.path.join(HERE, "fakebin")
BACKEND = "http://127.0.0.1:8085"
MOON = "http://127.0.0.1:7125"
FILTER = sys.argv[sys.argv.index("-k") + 1] if "-k" in sys.argv else ""

sys.path.insert(0, os.path.join(ROOT, "tests", "notifier"))
from fake_google import Google, ISSUER                     # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.hazmat.primitives import serialization   # noqa: E402

if not os.path.isfile(os.path.join(WORK, "pythonpath")):
    sys.exit("Moonraker is not prepared: run  python3 tests/e2e/setup.py  first.")
MOONRAKER_PATH = open(os.path.join(WORK, "pythonpath")).read().strip()
MOONRAKER_PYTHON = os.path.join(WORK, "venv", "bin", "python")

FAILS = []
SKIPPED = []


ON_GITHUB = bool(os.environ.get("GITHUB_ACTIONS"))


def annotate(title, text):
    """On GitHub, an error annotation (shown on the workflow run page, readable without the logs)."""
    if ON_GITHUB:
        print("::error title=%s::%s" % (title.replace(":", " ")[:200], str(text).replace("%", "%25").replace("\r", "").replace("\n", "%0A")[-3000:]), flush=True)


def ok(name, cond, extra=""):
    if not cond:
        FAILS.append(name)
        annotate(name, extra if extra != "" else "failed")
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)[-900:]) if (extra != "" and not cond) else ""), flush=True)


def _on_crash(kind, value, tb):
    import traceback
    annotate("e2e test crashed", "".join(traceback.format_exception(kind, value, tb)))
    sys.__excepthook__(kind, value, tb)


sys.excepthook = _on_crash


def scenario(name):
    return (not FILTER) or FILTER in name


def has_playwright():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False


def built_dashboard(release):
    """The real dashboard built with this release number (cached in .work/)."""
    out = os.path.join(WORK, "dashboard-%s.html" % release)
    if not os.path.isfile(out) or os.path.getmtime(out) < max(os.path.getmtime(os.path.join(ROOT, "frontend", "klippeye_frontend.html")), os.path.getmtime(__file__)):
        subprocess.run([sys.executable, os.path.join(ROOT, "frontend", "build.py"), out], check=True, capture_output=True, env=dict(os.environ, KLIPPEYE_RELEASE=release))
    return out


# ------------------------------------------------------------------------------------------------ a fresh world
class World:
    def __init__(self, name, extra_env=None):
        self.name = name
        self.root = os.path.join(WORLDS, name)
        self.home = os.path.join(self.root, "home")
        self.pd = os.path.join(self.home, "printer_data")
        self.units = os.path.join(self.root, "units")
        self.state = os.path.join(self.root, "state")
        self.bin = os.path.join(self.root, "bin")
        self.origin = os.path.join(self.root, "origin.git")
        self.dev = os.path.join(self.root, "dev")        # the developer's computer, which pushes to GitHub
        self.repo = os.path.join(self.home, "klippeye")
        self.data = os.path.join(self.pd, "klippeye")
        self.tmp = os.path.join(self.root, "tmp")
        self.real_dash = False
        self.env = {
            "HOME": self.home, "PATH": FAKEBIN + ":" + os.environ["PATH"],
            "KLIPPEYE_SYSTEMD_DIR": self.units, "FAKE_SYSTEMD_STATE": self.state, "KLIPPEYE_BIN_DIR": self.bin,
            "KLIPPEYE_ALLOW_ROOT": "1", "TMPDIR": self.tmp, "LANG": "C.UTF-8",
        }
        self.env.update(extra_env or {})
        self.google = None

    def run(self, cmd, timeout=240, env_extra=None, cwd=None):
        env = dict(self.env)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout, cwd=cwd or self.home)

    def git(self, *args, cwd=None):
        r = self.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.com", "-c", "init.defaultBranch=main"] + list(args), cwd=cwd or self.dev)
        if r.returncode != 0:
            raise RuntimeError("git %s: %s" % (" ".join(args), r.stdout + r.stderr))
        return r.stdout.strip()

    def systemctl(self, *args):
        return self.run(["systemctl"] + list(args))

    def calls(self):
        try:
            return open(os.path.join(self.state, "calls.log")).read().splitlines()
        except OSError:
            return []

    def service_log(self, name):
        try:
            return open(os.path.join(self.state, name + ".log"), errors="replace").read()
        except OSError:
            return ""

    def pid(self, name):
        try:
            return open(os.path.join(self.state, name + ".pid")).read()
        except OSError:
            return None

    def build(self, notifier=True, update_manager=True):
        shutil.rmtree(self.root, ignore_errors=True)
        for d in (self.home, self.units, self.state, self.bin, self.tmp, os.path.join(self.pd, "config"), os.path.join(self.pd, "logs"), self.data):
            os.makedirs(d, exist_ok=True)
        # what the person has before installing: an AI key and, if they set notifications up (guide, section 6), the
        # Firebase key and notifier.json in the data folder
        json.dump({"api_key": "sk-test", "provider": "openai"}, open(os.path.join(self.data, "ai.json"), "w"))
        if notifier:
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
            self.google = Google(key, 7391)
            self.google.start()
            json.dump({"type": "service_account", "project_id": "klippeye-test", "private_key_id": "x", "private_key": pem, "client_email": ISSUER,
                       "token_uri": "http://127.0.0.1:7391/token"}, open(os.path.join(self.data, "service-account.json"), "w"))
            json.dump({"topic": "test-topic", "service_account_file": "service-account.json", "moonraker_url": MOON,
                       "brain_url": BACKEND, "fcm_url": "http://127.0.0.1:7391/v1/projects/{project}/messages:send"}, open(os.path.join(self.data, "notifier.json"), "w"))
        # Moonraker (real)
        conf = ("[server]\nhost: 127.0.0.1\nport: 7125\nklippy_uds_address: %s/klippy_uds\n\n[machine]\nprovider: systemd_cli\n\n"
                "[authorization]\ntrusted_clients:\n  127.0.0.0/8\ncors_domains:\n  *\n\n" % self.root)
        if update_manager:
            conf += "[update_manager]\nenable_auto_refresh: False\nenable_system_updates: False\n"
        open(os.path.join(self.pd, "config", "moonraker.conf"), "w").write(conf)
        open(os.path.join(self.pd, "moonraker.asvc"), "w").write("klipper_mcu\nwebcamd\nMoonCord\nKlipperScreen\ncrowsnest")  # no final newline, on purpose
        with open(os.path.join(self.units, "moonraker.service"), "w") as f:
            f.write(("[Service]\nWorkingDirectory=/\nEnvironment=PYTHONPATH=%s\n"
                     "ExecStart=%s -m moonraker -d %s -c %s/config/moonraker.conf -l %s/logs/moonraker.log\nRestart=always\nRestartSec=1\n")
                    % (MOONRAKER_PATH, MOONRAKER_PYTHON, self.pd, self.pd, self.pd))
        # "GitHub" and the developer's computer: release 1.0.0 of this repository
        subprocess.run(["git", "init", "--bare", "-q", "-b", "main", self.origin], check=True)
        shutil.copytree(ROOT, self.dev, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "docs", ".git", "apk", "tests", ".work"))
        for version_file in ("VERSION", os.path.join("android", "VERSION")):  # the test always starts from 1.0.0, whatever the repository's release
            open(os.path.join(self.dev, version_file), "w").write("1.0.0\n")
        self.write_dashboard("1.0.0")
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "KlippEye 1.0.0")
        self.git("tag", "-a", "v1.0.0", "-m", "KlippEye 1.0.0")
        self.git("remote", "add", "origin", self.origin)
        self.git("push", "-q", "--follow-tags", "origin", "main")
        self.run(["git", "clone", "-q", self.origin, self.repo])
        self.systemctl("start", "moonraker")
        if not wait(lambda: http("GET", MOON + "/server/info", timeout=3)[0] == 200, 90):
            raise RuntimeError("Moonraker does not start: " + self.service_log("moonraker")[-2000:])

    def write_dashboard(self, release):
        target = os.path.join(self.dev, "frontend", "klippeye_frontend.html")
        if self.real_dash:
            shutil.copy(built_dashboard(release), target)
        else:  # a tiny page that says which release it is
            open(target, "w").write("<!doctype html><html><head><title>KlippEye dashboard %s</title></head><body>%s</body></html>" % (release, release))

    def install(self, *args, env_extra=None):
        return self.run(["bash", os.path.join(self.repo, "scripts", "install.sh")] + list(args), env_extra=env_extra, timeout=300)

    def publish(self, release, message, mutate=None, tag=True):
        """What a developer does: change the files and push them to GitHub (tagged, as the release workflow does)."""
        open(os.path.join(self.dev, "VERSION"), "w").write(release + "\n")
        self.write_dashboard(release)
        if mutate:
            mutate(self.dev)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        if tag and "v" + release not in self.git("tag").split():
            time.sleep(1.1)  # tags are ordered by date: one per second at least
            self.git("tag", "-a", "v" + release, "-m", message)
        self.git("push", "-q", "--follow-tags", "origin", "main")

    def teardown(self):
        for name in ("klippeye", "klippeye-notifier", "moonraker"):
            self.systemctl("stop", name)
        time.sleep(0.5)
        if self.google and self.google.server:
            try:
                self.google.server.shutdown()
                self.google.server.server_close()
            except Exception:
                pass


def http(method, url, body=None, timeout=15):
    """-> (status, json or text), or (None, error)"""
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"} if data is not None else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except ValueError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw
    except Exception as e:
        return None, repr(e)


def wait(fn, seconds):
    end = time.time() + seconds
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def backend_release():
    st, body = http("GET", BACKEND + "/api/version", timeout=3)
    return body.get("release") if st == 200 and isinstance(body, dict) else None


def mr_program(name="klippeye"):
    st, body = http("GET", MOON + "/machine/update/status?refresh=false", timeout=30)
    try:
        return body["result"]["version_info"][name]
    except Exception:
        return None


def cleanup_all():
    """Stops the services a previous run may have left behind."""
    if not os.path.isdir(WORLDS):
        return
    for name in os.listdir(WORLDS):
        state = os.path.join(WORLDS, name, "state")
        if os.path.isdir(state):
            for f in os.listdir(state):
                if f.endswith(".pid"):
                    try:
                        os.kill(int(open(os.path.join(state, f)).read().strip()), signal.SIGTERM)
                    except Exception:
                        pass
    time.sleep(2)


def tree_clean(w):
    return w.git("status", "--porcelain", cwd=w.repo)


# ====================================================================================================================
cleanup_all()
os.makedirs(WORLDS, exist_ok=True)

# ----------------------------------------------------------------------------------- install, update, undo
if scenario("install") or scenario("update") or scenario("undo"):
    w = World("main")
    w.build()
    r = w.install()
    out = r.stdout + r.stderr
    open(os.path.join(w.root, "install1.out"), "w").write(out)
    ok("[install] exits with 0", r.returncode == 0, out)
    ok("[install] the backend answers with release 1.0.0 and serves the repository's dashboard", backend_release() == "1.0.0" and "KlippEye dashboard 1.0.0" in str(http("GET", BACKEND + "/", timeout=5)[1]), out)
    ok("[install] data folder with mode 700", stat.S_IMODE(os.stat(w.data).st_mode) == 0o700, oct(os.stat(w.data).st_mode))
    ai = os.path.join(w.data, "ai.json")
    ok("[install] the AI key stays and gets mode 600", stat.S_IMODE(os.stat(ai).st_mode) == 0o600 and json.load(open(ai))["api_key"] == "sk-test")
    unit = open(os.path.join(w.units, "klippeye.service")).read()
    ok("[install] klippeye.service: right paths, no placeholders left", ("WorkingDirectory=" + w.repo) in unit and ("KLIPPEYE_DATA=" + w.data) in unit
       and (w.repo + "/backend/klippeye_backend.py") in unit and "@" not in unit.split("[Service]")[1], unit)
    nunit = open(os.path.join(w.units, "klippeye-notifier.service")).read()
    ok("[install] klippeye-notifier.service: the program of the repository, the configuration of the data folder", (w.repo + "/notifier/klippeye_notifier.py") in nunit and (w.data + "/notifier.json") in nunit, nunit)
    ok("[install] the notifier runs", w.pid("klippeye-notifier") is not None and w.systemctl("is-active", "klippeye-notifier").returncode == 0)
    ok("[install] the notification check ran (the Firebase key works; without Klipper Moonraker answers 404, normal here)", "Google sign-in works" in out and "The notification check reports something" in out, out)
    ok("[install] no service, command or folder with the old VzBot names", not any(os.path.exists(os.path.join(w.units, n + ".service")) for n in ("vzbot", "vzbot-notifier"))
       and not any(os.path.exists(os.path.join(w.bin, n)) for n in ("vzbot", "vzbot-notifiche")) and not os.path.exists(os.path.join(w.pd, "vzbot")), (os.listdir(w.units), os.listdir(w.bin)))
    conf = open(os.path.join(w.pd, "config", "moonraker.conf")).read()
    ok("[install] moonraker.conf: [update_manager klippeye] is right", "[update_manager klippeye]" in conf and ("path: " + w.repo) in conf and ("origin: " + w.origin) in conf
       and "primary_branch: main" in conf and "managed_services: klippeye" in conf and conf.count("[update_manager]") == 1, conf)
    asvc = open(os.path.join(w.pd, "moonraker.asvc")).read().split("\n")
    ok("[install] moonraker.asvc: klippeye and klippeye-notifier added on lines of their own", "klippeye" in asvc and "klippeye-notifier" in asvc and "crowsnest" in asvc and "crowsnestklippeye" not in asvc, asvc)
    ok("[install] Moonraker restarted by the installer", any(c.startswith("restart moonraker") for c in w.calls()), w.calls())
    entry = mr_program()
    ok("[install] Moonraker sees KlippEye: valid, clean, version known", bool(entry) and entry.get("is_valid") and not entry.get("is_dirty") and entry.get("version"), entry)
    ok("[install] the Raspberry's repository is clean", tree_clean(w) == "", tree_clean(w))
    ok("[install] commands installed", os.path.isfile(os.path.join(w.bin, "klippeye")) and os.path.isfile(os.path.join(w.bin, "klippeye-notifiche")))
    st = w.run([os.path.join(w.bin, "klippeye"), "status"], env_extra={"KLIPPEYE_BRAIN_URL": BACKEND})
    ok("[install] klippeye status: the backend answers with its release", st.returncode == 0 and "The backend answers: release 1.0.0" in st.stdout, st.stdout + st.stderr)
    st = w.run([os.path.join(w.bin, "klippeye"), "stato"], env_extra={"KLIPPEYE_BRAIN_URL": BACKEND})
    ok("[install] the Italian command names of before 1.3.0 still work (klippeye stato)", st.returncode == 0 and "The backend answers" in st.stdout, st.stdout + st.stderr)
    vv = w.run([os.path.join(w.bin, "klippeye"), "version"])
    ok("[install] klippeye version", "KlippEye 1.0.0" in vv.stdout, vv.stdout + vv.stderr)
    dg = w.run([os.path.join(w.bin, "klippeye"), "diagnose"], env_extra={"KLIPPEYE_BRAIN_URL": BACKEND})
    ok("[install] klippeye diagnose: a report with the services and the update manager entry, no secret in it", dg.returncode == 0 and "klippeye-notifier" in dg.stdout
       and "update manager: version" in dg.stdout and "sk-test" not in dg.stdout, dg.stdout[-1500:] + dg.stderr)

    # run again: nothing changes
    calls_before = len(w.calls())
    pid_before = w.pid("klippeye")
    backups_before = sorted(os.listdir(os.path.join(w.data, "backup"))) if os.path.isdir(os.path.join(w.data, "backup")) else []
    r2 = w.install()
    out2 = r2.stdout + r2.stderr
    new_calls = w.calls()[calls_before:]
    ok("[install] run again: exits with 0", r2.returncode == 0, out2)
    ok("[install] run again: no service or Moonraker restart, same backend process", not any(c.startswith("restart") for c in new_calls) and w.pid("klippeye") == pid_before, new_calls)
    ok("[install] run again: no new backup, moonraker.conf the same", (sorted(os.listdir(os.path.join(w.data, "backup"))) if os.path.isdir(os.path.join(w.data, "backup")) else []) == backups_before
       and open(os.path.join(w.pd, "config", "moonraker.conf")).read() == conf, out2)

    if scenario("update"):
        def touch_notifier(dev):
            open(os.path.join(dev, "notifier", "klippeye_notifier.py"), "a").write("\n# test change 1.0.1\n")
        w.publish("1.0.1", "KlippEye 1.0.1", touch_notifier)
        notifier_starts = w.service_log("klippeye-notifier").count("--- start")
        st, body = http("POST", BACKEND + "/machine/update/refresh?name=klippeye", timeout=120)
        entry = mr_program()
        ok("[update] check (through the backend): 1 commit coming, with its title", st == 200 and entry and entry.get("commits_behind_count") == 1 and entry["commits_behind"][0]["subject"] == "KlippEye 1.0.1", (st, entry))
        st, body = http("POST", BACKEND + "/machine/update/upgrade?name=klippeye", timeout=240)
        ok("[update] the backend comes back with release 1.0.1", wait(lambda: backend_release() == "1.0.1", 90), (st, body, w.service_log("klippeye")[-800:]))
        ok("[update] Moonraker restarted the klippeye service", any(c == "restart klippeye" for c in w.calls()), w.calls()[-8:])
        ok("[update] the dashboard served is 1.0.1 and the repository is clean", "KlippEye dashboard 1.0.1" in str(http("GET", BACKEND + "/", timeout=5)[1])
           and w.git("log", "-1", "--format=%s", cwd=w.repo) == "KlippEye 1.0.1" and tree_clean(w) == "")
        ok("[update] the data is untouched", json.load(open(ai))["api_key"] == "sk-test" and os.path.isfile(os.path.join(w.data, "notifier.json")))
        ok("[update] the notifier restarted by itself because its file changed", wait(lambda: w.service_log("klippeye-notifier").count("--- start") > notifier_starts, 30), w.service_log("klippeye-notifier")[-600:])
        entry = mr_program()
        ok("[update] Moonraker: no commit coming, a rollback version", entry and entry.get("commits_behind_count") == 0 and entry.get("rollback_version"), entry)

        st, body = http("POST", BACKEND + "/machine/update/rollback?name=klippeye", timeout=240)
        ok("[update] rollback: back to 1.0.0 (backend, dashboard, repository)", wait(lambda: backend_release() == "1.0.0", 90) and "KlippEye dashboard 1.0.0" in str(http("GET", BACKEND + "/", timeout=5)[1])
           and w.git("log", "-1", "--format=%s", cwd=w.repo) == "KlippEye 1.0.0", (st, body, backend_release()))

        # a file changed by hand: the update is refused, "recover" puts it right
        w.publish("1.0.2", "KlippEye 1.0.2")
        http("POST", BACKEND + "/machine/update/refresh?name=klippeye", timeout=120)
        open(os.path.join(w.repo, "VERSION"), "w").write("changed by hand\n")
        http("POST", MOON + "/machine/update/refresh?name=klippeye", timeout=120)
        entry = mr_program()
        ok("[update] a file changed by hand: Moonraker marks it dirty or invalid, with a warning", entry and (entry.get("is_dirty") or not entry.get("is_valid")) and entry.get("warnings"), entry)
        st, body = http("POST", MOON + "/machine/update/upgrade?name=klippeye", timeout=120)
        ok("[update] ... and refuses to update", st != 200 and backend_release() == "1.0.0", (st, body))
        pid_before = w.pid("klippeye")
        st, body = http("POST", BACKEND + "/machine/update/recover?name=klippeye&hard=false", timeout=240)
        ok("[update] recover (soft): the backend restarts, still at 1.0.0", wait(lambda: backend_release() == "1.0.0" and w.pid("klippeye") != pid_before, 60), (st, body))
        http("POST", MOON + "/machine/update/refresh?name=klippeye", timeout=120)
        entry = mr_program()
        ok("[update] recover (soft): clean and valid, still 1.0.0", entry and entry.get("is_valid") and not entry.get("is_dirty") and tree_clean(w) == ""
           and open(os.path.join(w.repo, "VERSION")).read().strip() == "1.0.0", entry)
        open(os.path.join(w.repo, "VERSION"), "w").write("damaged\n")
        http("POST", MOON + "/machine/update/refresh?name=klippeye", timeout=120)
        st, body = http("POST", BACKEND + "/machine/update/recover?name=klippeye&hard=true", timeout=240)
        ok("[update] recover (hard): clean again, backend at 1.0.0", wait(lambda: backend_release() == "1.0.0", 60) and tree_clean(w) == ""
           and open(os.path.join(w.repo, "VERSION")).read().strip() == "1.0.0", (st, body))
        http("POST", MOON + "/machine/update/refresh?name=klippeye", timeout=120)
        st, body = http("POST", BACKEND + "/machine/update/upgrade?name=klippeye", timeout=240)
        ok("[update] after recovering the update works (1.0.2)", wait(lambda: backend_release() == "1.0.2", 90), (st, body, backend_release()))

        # a broken release: the backend does not start; rollback from Moonraker (as from Mainsail)
        def break_backend(dev):
            open(os.path.join(dev, "backend", "klippeye_backend.py"), "a").write("\nthis is not python (\n")
        w.publish("1.0.3", "KlippEye 1.0.3 broken", break_backend)
        http("POST", MOON + "/machine/update/refresh?name=klippeye", timeout=120)
        http("POST", MOON + "/machine/update/upgrade?name=klippeye", timeout=240)
        time.sleep(4)
        ok("[update] broken release: the backend does not answer (as expected)", backend_release() is None, backend_release())
        st, body = http("POST", MOON + "/machine/update/rollback?name=klippeye", timeout=240)
        ok("[update] broken release: rollback from Moonraker brings back 1.0.2", wait(lambda: backend_release() == "1.0.2", 90), (st, body, w.service_log("klippeye")[-500:]))

    if scenario("undo"):
        expected = backend_release()
        ra = w.install("--undo")
        outa = ra.stdout + ra.stderr
        ok("[undo] exits with 0", ra.returncode == 0, outa)
        ok("[undo] the KlippEye services are stopped and removed", not os.path.exists(os.path.join(w.units, "klippeye.service")) and not os.path.exists(os.path.join(w.units, "klippeye-notifier.service"))
           and wait(lambda: backend_release() is None, 20), os.listdir(w.units))
        confa = open(os.path.join(w.pd, "config", "moonraker.conf")).read()
        ok("[undo] [update_manager klippeye] removed, [update_manager] stays", "[update_manager klippeye]" not in confa and "[update_manager]" in confa and "enable_auto_refresh" in confa, confa)
        asvca = open(os.path.join(w.pd, "moonraker.asvc")).read().split("\n")
        ok("[undo] klippeye and klippeye-notifier removed from moonraker.asvc, the rest stays", "klippeye" not in asvca and "klippeye-notifier" not in asvca and "crowsnest" in asvca and "klipper_mcu" in asvca, asvca)
        ok("[undo] commands removed", not os.path.exists(os.path.join(w.bin, "klippeye")) and not os.path.exists(os.path.join(w.bin, "klippeye-notifiche")))
        ok("[undo] the data folder and the program folder stay", os.path.isfile(ai) and os.path.isdir(w.repo))
        rr = w.install()
        ok("[undo] it installs again without problems", rr.returncode == 0 and wait(lambda: backend_release() == expected, 30), rr.stdout + rr.stderr)
    w.teardown()

# ----------------------------------------------------------------------------------- update channel
if scenario("channel"):
    w = World("channel")
    w.build(notifier=False)
    r = w.install()
    conf_path = os.path.join(w.pd, "config", "moonraker.conf")
    ok("[channel] install: Moonraker's entry uses the stable channel", r.returncode == 0 and "channel: stable" in open(conf_path).read(), r.stdout[-600:])
    wait(lambda: http("POST", BACKEND + "/machine/update/refresh?name=klippeye", timeout=120)[0] == 200 and (mr_program() or {}).get("is_valid"), 90)
    entry = mr_program()
    ok("[channel] Moonraker sees KlippEye at v1.0.0, stable, valid", bool(entry) and entry.get("channel") == "stable" and entry.get("is_valid") and str(entry.get("version", "")).startswith("v1.0.0"), entry)
    st, body = http("GET", BACKEND + "/api/update/channel", timeout=10)
    ok("[channel] /api/update/channel says stable", st == 200 and body.get("channel") == "stable" and body.get("listed") is True, (st, body))
    w.publish("1.0.1", "work in progress", tag=False)
    http("POST", BACKEND + "/machine/update/refresh?name=klippeye", timeout=120)
    entry = mr_program()
    ok("[channel] a change without a tag is NOT offered on the stable channel", bool(entry) and entry.get("commits_behind_count", 0) == 0 and str(entry.get("remote_version", "")).startswith("v1.0.0"), entry)
    w.publish("1.0.2", "KlippEye 1.0.2")
    http("POST", BACKEND + "/machine/update/refresh?name=klippeye", timeout=120)
    entry = mr_program()
    ok("[channel] the release tagged v1.0.2 is offered (2 commits coming)", bool(entry) and str(entry.get("remote_version", "")).startswith("v1.0.2") and entry.get("commits_behind_count") == 2, entry)
    http("POST", BACKEND + "/machine/update/upgrade?name=klippeye", timeout=240)
    ok("[channel] update: the backend comes back with 1.0.2", wait(lambda: backend_release() == "1.0.2", 90), backend_release())
    entry = mr_program()
    ok("[channel] ... Moonraker says v1.0.2, clean and valid", bool(entry) and str(entry.get("version", "")).startswith("v1.0.2") and entry.get("is_valid") and not entry.get("is_dirty"), entry)
    w.publish("1.0.3", "work in progress 2", tag=False)
    st, body = http("POST", BACKEND + "/api/update/channel", {"channel": "dev"}, timeout=20)
    ok("[channel] the dashboard switches to dev: moonraker.conf changed (with a copy) and Moonraker restarted", st == 200 and body.get("changed") is True and "channel: dev" in open(conf_path).read()
       and any(n.startswith("moonraker.conf-") for n in os.listdir(os.path.join(w.data, "backup"))), (st, body))
    ok("[channel] Moonraker comes back on the dev channel", wait(lambda: (mr_program() or {}).get("channel") == "dev", 90), mr_program())
    http("POST", BACKEND + "/machine/update/refresh?name=klippeye", timeout=120)
    entry = mr_program()
    ok("[channel] on dev the untagged change is offered", bool(entry) and entry.get("commits_behind_count") == 1, entry)
    st, body = http("POST", BACKEND + "/api/update/channel", {"channel": "nonsense"}, timeout=10)
    ok("[channel] an unknown channel is refused (400)", st == 400, (st, body))
    r = w.install("--channel=stable")
    ok("[channel] install.sh --channel=stable puts the stable channel back", r.returncode == 0 and "channel: stable" in open(conf_path).read() and "Update channel set to 'stable'" in r.stdout, r.stdout[-800:])
    w.teardown()

# ----------------------------------------------------------------------------------- an install that fails
if scenario("fails"):
    w = World("fails")
    w.build(notifier=False)
    open(os.path.join(w.repo, "backend", "klippeye_backend.py"), "a").write("\nthis is not python (\n")
    # broken in the release itself (a file damaged only on disk would be put right by the self-repair)
    w.git("add", "-A", cwd=w.repo)
    w.git("commit", "-q", "-m", "broken release", cwd=w.repo)
    r = w.install(env_extra={"KLIPPEYE_IGNORE_MISSING": "1"})
    out = r.stdout + r.stderr
    ok("[fails] broken backend: the installer exits with an error and says so", r.returncode != 0 and "ERROR" in out and "does not answer" in out, out)
    ok("[fails] ... the KlippEye service is taken off again", not os.path.exists(os.path.join(w.units, "klippeye.service")) and w.pid("klippeye") is None, os.listdir(w.units))
    ok("[fails] ... moonraker.conf is not touched", "[update_manager klippeye]" not in open(os.path.join(w.pd, "config", "moonraker.conf")).read())
    w.teardown()

# ----------------------------------------------------------------------------------- moonraker.conf without [update_manager]
if scenario("no-um"):
    w = World("no-um")
    w.build(notifier=False, update_manager=False)
    r = w.install()
    out = r.stdout + r.stderr
    conf = open(os.path.join(w.pd, "config", "moonraker.conf")).read()
    ok("[no-um] [update_manager] is added too, once, before [update_manager klippeye]", r.returncode == 0 and conf.count("[update_manager]") == 1 and conf.index("[update_manager]") < conf.index("[update_manager klippeye]"), out + conf)
    ok("[no-um] Moonraker sees KlippEye", wait(lambda: bool(mr_program()), 60), out)
    ok("[no-um] notifications not set up: no notifier service and no asvc line", not os.path.exists(os.path.join(w.units, "klippeye-notifier.service")) and "klippeye-notifier" not in open(os.path.join(w.pd, "moonraker.asvc")).read(), out)
    w.teardown()

# ----------------------------------------------------------------------------------- printing: Moonraker is not restarted
if scenario("printing"):
    class Printing(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = json.dumps({"result": {"status": {"print_stats": {"state": "printing"}}}}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    fake = ThreadingHTTPServer(("127.0.0.1", 7455), Printing)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    w = World("printing")
    w.build(notifier=False)
    r = w.install(env_extra={"KLIPPEYE_MOONRAKER_URL": "http://127.0.0.1:7455"})
    out = r.stdout + r.stderr
    ok("[printing] the installer succeeds but does NOT restart Moonraker, and says so", r.returncode == 0 and not any(c.startswith("restart moonraker") for c in w.calls()) and "Printing" in out, out)
    ok("[printing] the entry is written to moonraker.conf anyway", "[update_manager klippeye]" in open(os.path.join(w.pd, "config", "moonraker.conf")).read())
    fake.shutdown()
    fake.server_close()
    w.teardown()

# ----------------------------------------------------------------------------------- the real dashboard against Moonraker and the backend
PLAYWRIGHT = None
if scenario("ui") or scenario("app"):
    PLAYWRIGHT = has_playwright()
    if not PLAYWRIGHT:
        SKIPPED.append("ui, app (Playwright with Chromium is not installed)")

if scenario("ui") and PLAYWRIGHT:
    from playwright.sync_api import sync_playwright
    w = World("ui")
    w.real_dash = True
    w.build(notifier=False)
    r = w.install()
    ok("[ui] install: backend 1.0.0 with the real dashboard", r.returncode == 0 and backend_release() == "1.0.0", r.stdout + r.stderr)
    wait(lambda: (mr_program() or {}).get("is_valid"), 60)
    time.sleep(4)  # Moonraker checks GitHub once after its restart: 1.0.1 must arrive after that
    w.publish("1.0.1", "KlippEye 1.0.1")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="it-IT")
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)[:300]))
        posts = []
        pg.on("request", lambda r: posts.append((r.method, r.url.replace(BACKEND, "")[:60])) if r.method == "POST" else None)
        pg.route("**/*", lambda route: route.continue_() if route.request.url.startswith("http://127.0.0.1") else route.abort())
        body = lambda: pg.locator(".drawer__body").inner_text()

        def open_software():
            pg.wait_for_timeout(2500)
            pg.evaluate("() => { window.__marker = 1 }")
            pg.click('button[aria-label="Impostazioni"]')
            pg.wait_for_selector(".drawer")
            pg.wait_for_timeout(500)
            pg.click('.set-entry[data-page="software"]')
            pg.wait_for_timeout(1200)

        def reloaded(seconds):
            return wait(lambda: pg.evaluate("() => !window.__marker"), seconds)

        def pumped(fn, seconds):
            """Like wait(), but lets the browser's routed requests through meanwhile (Python must call Playwright for that)."""
            end = time.time() + seconds
            while time.time() < end:
                try:
                    if fn():
                        return True
                except Exception:
                    pass
                pg.wait_for_timeout(300)
            return False

        def sheet():
            return pg.locator(".sheet-card").inner_text() if pg.locator(".sheet-card").count() else ""
        pg.goto(BACKEND + "/")
        open_software()
        ok("[ui] the Updates page shows release 1.0.0", wait(lambda: "1.0.0" in body() and "Dashboard (questa pagina)" in body(), 20), body())
        ok("[ui] ... and says everything is up to date", wait(lambda: "KlippEye è aggiornato" in body(), 30), body())
        pg.locator("button", has_text="Controlla se c'è una versione nuova").click()
        ok("[ui] 'Check': Moonraker sees 1 change coming and lists it", wait(lambda: "1 modifica in arrivo" in body() and "KlippEye 1.0.1" in body(), 60), body())
        pg.locator("button", has_text="Aggiorna KlippEye").click()
        pg.wait_for_timeout(700)
        ok("[ui] the confirmation says what happens", "Aggiornare KlippEye?" in sheet() and "riavvia il backend" in sheet(), sheet())
        pg.locator(".sheet-footer button", has_text="Aggiorna").click()
        ok("[ui] UPDATE: the page reloads by itself after the backend restarts", reloaded(170), sheet())
        ok("[ui] ... the backend is 1.0.1 and the repository is clean", backend_release() == "1.0.1" and tree_clean(w) == "", (backend_release(), tree_clean(w)))
        open_software()
        ok("[ui] after the reload the page is 1.0.1 and up to date, no page/backend mismatch", wait(lambda: "KlippEye è aggiornato" in body(), 30) and "1.0.1" in body() and "ricaricala" not in body(), body())
        ok("[ui] the 'Go back to the previous version' button is there", wait(lambda: pg.locator("button", has_text="Torna alla versione precedente").count() == 1, 20), body())
        pg.locator("button", has_text="Torna alla versione precedente").click()
        pg.wait_for_timeout(700)
        pg.locator(".sheet-footer button", has_text="Torna indietro").click()
        ok("[ui] GO BACK: the page reloads and the backend is 1.0.0 again", reloaded(170) and wait(lambda: backend_release() == "1.0.0", 60), (backend_release(), sheet()))
        open(os.path.join(w.repo, "VERSION"), "w").write("changed by hand\n")
        pg.reload()
        open_software()
        pg.locator("button", has_text="Controlla se c'è una versione nuova").click()  # Moonraker notices changed files when it checks
        ok("[ui] a file changed by hand: the page offers to recover", wait(lambda: pg.locator("button", has_text="Ripristina i file del programma").count() == 1, 40), body())
        pg.locator("button", has_text="Ripristina i file del programma").click()
        pg.wait_for_timeout(700)
        pg.locator(".sheet-footer button", has_text="Ripristina").click()
        ok("[ui] RECOVER: the page reloads, the repository is clean", reloaded(170) and wait(lambda: tree_clean(w) == "", 30), (tree_clean(w), sheet()))
        open_software()
        pid_before = w.pid("klippeye")
        pg.locator("text=Riavvia il backend").first.click()
        ok("[ui] RESTART THE BACKEND: Moonraker restarts the klippeye service and the backend comes back", wait(lambda: w.pid("klippeye") != pid_before, 60) and wait(lambda: backend_release() == "1.0.0", 60))
        pg.goto(BACKEND + "/")
        pg.wait_for_timeout(2500)
        pg.click('button[aria-label="Impostazioni"]')
        pg.wait_for_selector(".drawer")
        pg.wait_for_timeout(500)
        pg.click('.set-entry[data-page="detector"]')
        pg.wait_for_timeout(1500)
        ok("[ui] AI monitor thresholds (real backend): the default values are shown", wait(lambda: pg.locator("#set-num-sensitivity").count() == 1 and pg.locator("#set-num-sensitivity").input_value() == "35", 15), body())
        pg.locator("#set-num-sensitivity").fill("50")
        ok("[ui] ... a new value reaches the backend and is written to monitor.json", pumped(lambda: json.load(open(os.path.join(w.data, "monitor.json")))["values"]["sensitivity"] == 50, 10), (posts[-6:], body()[:300]))
        st, cfg = http("GET", BACKEND + "/api/backend/config")
        ok("[ui] ... and the backend uses it at once", st == 200 and cfg["values"]["sensitivity"] == 50, cfg)
        ok("[ui] no JavaScript error in the whole test", errors == [], errors)
        browser.close()
    w.teardown()

# ----------------------------------------------------------------------------------- the Android app: GitHub -> Moonraker -> backend -> dashboard -> the app's Kotlin code
if scenario("app") and PLAYWRIGHT:
    import hashlib
    import zipfile
    from playwright.sync_api import sync_playwright

    kotlin_home = os.environ.get("KOTLINC_HOME") or (os.path.dirname(os.path.dirname(os.path.realpath(shutil.which("kotlinc")))) if shutil.which("kotlinc") else "")
    KOTLIN = bool(kotlin_home) and os.path.isfile(os.path.join(kotlin_home, "bin", "kotlinc")) and bool(shutil.which("java"))
    KTOUT = os.path.join(WORK, "kotlin")
    if KOTLIN:
        src = os.path.join(ROOT, "android", "app", "src", "main", "java", "com", "klippeye", "app", "Aggiornamento.kt")
        main_kt = os.path.join(HERE, "AppDownload.kt")
        if not os.path.isdir(KTOUT) or os.path.getmtime(KTOUT) < max(os.path.getmtime(src), os.path.getmtime(main_kt)):
            shutil.rmtree(KTOUT, ignore_errors=True)
            subprocess.run([os.path.join(kotlin_home, "bin", "kotlinc"), "-jvm-target", "1.8", src, main_kt, "-d", KTOUT], check=True, capture_output=True)
    else:
        SKIPPED.append("app: the checks with the app's Kotlin code (kotlinc or java not found)")

    def kotlin_download(version, sha, size, installed_code, outdir):
        """The app's Kotlin code (Aggiornamento.kt) downloading from the real backend: -> (exit code, lines)"""
        stdlib = [os.path.join(kotlin_home, "lib", n) for n in ("kotlin-stdlib.jar",)]
        r = subprocess.run(["java", "-cp", ":".join([KTOUT] + stdlib), "AppDownloadKt", BACKEND + "/", version, sha, str(size), str(installed_code), outdir],
                           capture_output=True, text=True, timeout=120)
        return r.returncode, [l for l in r.stdout.splitlines() if l.startswith(("OK", "ERROR"))]

    def make_apk(path, tag):
        with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
            z.writestr("AndroidManifest.xml", b"manifest")
            z.writestr("classes.dex", os.urandom(40000))
            z.writestr("resources.arsc", os.urandom(180000))
            z.writestr("tag.txt", tag)

    def publish_app(w, app_version, release, message):
        """What GitHub does (ci/app_ci.py publishes the APK it built) and then commits: the new APK reaches the repository."""
        code = str(int(app_version.split(".")[0]) * 10000 + int(app_version.split(".")[1]) * 100 + int(app_version.split(".")[2]))

        def mutate(dev):
            open(os.path.join(dev, "android", "VERSION"), "w").write(app_version + "\n")
            apk = os.path.join(w.tmp, "built.apk")
            make_apk(apk, "app " + app_version)
            env = dict(os.environ, PATH=os.path.join(HERE, "fakeapk") + ":" + os.environ["PATH"], FAKE_APK_VERSION=app_version, FAKE_APK_CODE=code)
            for sdk in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):  # app_ci.py looks in the SDK first: the fake tools must win
                env.pop(sdk, None)
            r = subprocess.run([sys.executable, os.path.join(dev, "ci", "app_ci.py"), "--radice", dev, "pubblica", "--apk", apk, "--sorgente", "abc123"], capture_output=True, text=True, env=env)
            if r.returncode != 0:
                raise RuntimeError("publish: " + r.stdout + r.stderr)
        w.publish(release, message, mutate)

    def app_info():
        st, body = http("GET", BACKEND + "/api/app/version", timeout=5)
        return body if st == 200 and isinstance(body, dict) else None

    def fetch_bytes(url):
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.status, dict(resp.headers), resp.read()

    w = World("app")
    w.real_dash = True
    w.build(notifier=False)
    r = w.install()
    ok("[app] install: backend 1.0.0, no app yet", r.returncode == 0 and backend_release() == "1.0.0", r.stdout + r.stderr)
    info = app_info()
    ok("[app] without apk/: /api/app/version says 'no app' and the file is 404", info and info["available"] is False and "no app published" in info["reason"]
       and http("GET", BACKEND + "/app/KlippEye.apk", timeout=5)[0] == 404, info)
    ok("[app] the address of the VzBot days (/app/VzBot.apk) is gone", http("GET", BACKEND + "/app/VzBot.apk", timeout=5)[0] == 404)

    publish_app(w, "1.0.0", "1.0.1", "KlippEye 1.0.1 + app 1.0.0")
    http("POST", BACKEND + "/machine/update/refresh?name=klippeye", timeout=120)
    st, body = http("POST", BACKEND + "/machine/update/upgrade?name=klippeye", timeout=240)
    ok("[app] after Moonraker's update the backend is 1.0.1", wait(lambda: backend_release() == "1.0.1", 90), (st, body, backend_release()))
    apk_dev = open(os.path.join(w.dev, "apk", "KlippEye.apk"), "rb").read()
    apk_sha = hashlib.sha256(apk_dev).hexdigest()
    info = app_info()
    ok("[app] the backend offers app 1.0.0: version, code, size and fingerprint of the file", info and info["available"] and info["version"] == "1.0.0" and info["code"] == 10000
       and info["size"] == len(apk_dev) and info["sha256"] == apk_sha, info)
    st, headers, data = fetch_bytes(BACKEND + "/app/KlippEye.apk")
    ok("[app] /app/KlippEye.apk: the same file as in the repository, as an APK, with the right size", st == 200 and data == apk_dev
       and headers.get("Content-Type") == "application/vnd.android.package-archive" and int(headers.get("Content-Length", "0")) == len(apk_dev), (st, headers))
    ok("[app] the repository is clean after the APK arrived", tree_clean(w) == "", tree_clean(w))
    if KOTLIN:
        outdir = os.path.join(w.root, "kt_download")
        code, lines = kotlin_download("1.0.0", apk_sha, len(apk_dev), 5, outdir)
        ok("[app] the app's Kotlin code downloads from the real backend and gets the same file", code == 0 and lines and lines[0].startswith("OK")
           and open(lines[0].split()[1], "rb").read() == apk_dev and lines[0].split()[2] == apk_sha, (code, lines))
        code, lines = kotlin_download("1.0.0", apk_sha, len(apk_dev), 10000, outdir)
        ok("[app] ... with the same version installed it says it is up to date", code == 2 and lines and "già aggiornata" in lines[0], (code, lines))
        code, lines = kotlin_download("1.0.0", "0" * 64, len(apk_dev), 5, outdir)
        ok("[app] ... with a wrong fingerprint it throws the file away", code == 2 and lines and "rovinato" in lines[0]
           and not any(f.endswith((".apk", ".parte")) for f in os.listdir(outdir)), (code, lines, os.listdir(outdir)))

    publish_app(w, "1.0.1", "1.0.2", "KlippEye 1.0.2 + app 1.0.1")
    http("POST", BACKEND + "/machine/update/refresh?name=klippeye", timeout=120)
    st, body = http("POST", BACKEND + "/machine/update/upgrade?name=klippeye", timeout=240)
    ok("[app] update to 1.0.2: the backend offers app 1.0.1", wait(lambda: backend_release() == "1.0.2" and (app_info() or {}).get("version") == "1.0.1", 90), (st, body, app_info()))
    apk_dev2 = open(os.path.join(w.dev, "apk", "KlippEye.apk"), "rb").read()
    apk_sha2 = hashlib.sha256(apk_dev2).hexdigest()
    info = app_info()
    ok("[app] ... with the size and fingerprint of the new file", info["size"] == len(apk_dev2) and info["sha256"] == apk_sha2 and apk_sha2 != apk_sha and info["code"] == 10001, info)

    open(os.path.join(w.repo, "apk", "KlippEye.apk"), "ab").write(b"damaged")
    info = app_info()
    ok("[app] an APK damaged on the Raspberry is not offered and the file is 404", info and info["available"] is False and http("GET", BACKEND + "/app/KlippEye.apk", timeout=5)[0] == 404, info)
    http("POST", MOON + "/machine/update/refresh?name=klippeye", timeout=120)
    st, body = http("POST", BACKEND + "/machine/update/recover?name=klippeye&hard=false", timeout=240)
    ok("[app] 'Recover the program files' puts the right APK back and the backend offers it again", wait(lambda: (app_info() or {}).get("available") is True and tree_clean(w) == "", 90)
       and fetch_bytes(BACKEND + "/app/KlippEye.apk")[2] == apk_dev2, (st, body, app_info(), tree_clean(w)))

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def new_page(script=None):
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="it-IT", accept_downloads=True)
            pg = ctx.new_page()
            pg.errors = []
            pg.on("pageerror", lambda e: pg.errors.append(str(e)[:300]))
            pg.route("**/*", lambda route: route.continue_() if route.request.url.startswith("http://127.0.0.1") else route.abort())
            if script:
                pg.add_init_script(script)
            return pg

        def open_software(pg):
            pg.goto(BACKEND + "/")
            pg.wait_for_timeout(2500)
            pg.click('button[aria-label="Impostazioni"]')
            pg.wait_for_selector(".drawer")
            pg.wait_for_timeout(500)
            pg.click('.set-entry[data-page="software"]')
            pg.wait_for_timeout(1500)

        def block(pg):
            return pg.locator(".set-group", has=pg.locator(".set-group__label", has_text="App Android")).inner_text()
        bridge_js = """(() => {
          const ua = navigator.userAgent + ' KlippEyeApp/5';
          Object.defineProperty(navigator, 'userAgent', { get: () => ua });
          window.__bridge = { updates: [] };
          window.KlippEyeApp = { appInfo: () => JSON.stringify({ version: '1.0.0', code: 10000, canInstall: true }), updateApp: (p, v, s, z) => { window.__bridge.updates.push([p, v, s, z]); }, saveUrl: () => {} };
        })();"""
        pg = new_page(bridge_js)
        open_software(pg)
        ok("[app] real dashboard inside the app: 'app 1.0.1 available (you have 1.0.0)' and the button", wait(lambda: "Disponibile l'app 1.0.1 (hai la 1.0.0)" in block(pg) and "Aggiorna l'app" in block(pg), 30), block(pg))
        pg.locator("button", has_text="Aggiorna l'app").click()
        pg.wait_for_timeout(500)
        calls = pg.evaluate("() => window.__bridge.updates")
        ok("[app] the button gives the app exactly what the backend announces (path, version, fingerprint, size)", calls == [["/app/KlippEye.apk", "1.0.1", apk_sha2, str(len(apk_dev2))]], calls)
        if KOTLIN:
            code, lines = kotlin_download(calls[0][1], calls[0][2], int(calls[0][3]), 10000, os.path.join(w.root, "kt_download2"))
            ok("[app] ... and with those values the app's Kotlin code downloads the right file (as on the phone)", code == 0 and lines and lines[0].startswith("OK")
               and open(lines[0].split()[1], "rb").read() == apk_dev2, (code, lines))
        ok("[app] no JavaScript error (app)", pg.errors == [], pg.errors)
        pg = new_page()
        open_software(pg)
        ok("[app] real dashboard in a browser: app ready and the 'Download the app' button", wait(lambda: "L'app Android 1.0.1 è pronta" in block(pg) and "Scarica l'app" in block(pg), 30), block(pg))
        with pg.expect_download() as dl:
            pg.locator("button", has_text="Scarica l'app").click()
        ok("[app] ... and the browser downloads the right file (KlippEye-1.0.1.apk)", dl.value.suggested_filename == "KlippEye-1.0.1.apk" and open(dl.value.path(), "rb").read() == apk_dev2, dl.value.suggested_filename)
        ok("[app] no JavaScript error (browser)", pg.errors == [], pg.errors)
        browser.close()
    w.teardown()

# ----------------------------------------------------------------------------------- power cut: self-repair of the files
if scenario("blackout"):
    w = World("blackout")
    w.build(notifier=False)
    r = w.install()
    ok("[blackout] install: exits with 0 and the backend answers", r.returncode == 0 and wait(lambda: backend_release() == "1.0.0", 60), r.stdout + r.stderr)
    unit = open(os.path.join(w.units, "klippeye.service")).read()
    ok("[blackout] the service has the ExecStartPre line with the repair script", ("ExecStartPre=-/bin/bash " + w.repo + "/scripts/repair.sh --quiet") in unit, unit)
    clean = w.run(["bash", os.path.join(w.repo, "scripts", "repair.sh")])
    ok("[blackout] files intact: 'intact', no log and no mark", clean.returncode == 0 and "intact" in clean.stdout
       and not os.path.exists(os.path.join(w.data, "repair.log")) and not os.path.exists(os.path.join(w.data, "repair.json")), clean.stdout + clean.stderr)
    old = w.run(["bash", os.path.join(w.repo, "scripts", "ripara.sh"), "--silenzioso"])
    ok("[blackout] the old name scripts/ripara.sh (services installed before 1.3.0) still works", old.returncode == 0, old.stdout + old.stderr)
    dash = os.path.join(w.repo, "frontend", "klippeye_frontend.html")
    be = os.path.join(w.repo, "backend", "klippeye_backend.py")
    nt = os.path.join(w.repo, "notifier", "klippeye_notifier.py")
    cli = os.path.join(w.repo, "scripts", "klippeye")
    good = {p: open(p, "rb").read() for p in (dash, be, nt, cli)}
    # the person's data (outside the program) and a file of theirs inside the folder: never touched
    open(os.path.join(w.data, "ai.json"), "w").write('{"api_key": "sk-mine"}')
    open(os.path.join(w.repo, "frontend", "mine.txt"), "w").write("my notes")
    open(os.path.join(w.repo, "README.md"), "a").write("\nmy change\n")
    ai_before = open(os.path.join(w.data, "ai.json")).read()

    def corrupt_all():
        open(dash, "wb").close()                                   # empty (the classic: a blank page)
        open(be, "wb").write(good[be][: len(good[be]) // 2])       # half written
        open(nt, "wb").write(b"\x00" * len(good[nt]))              # all zeros
        os.remove(cli)                                             # gone

    w.systemctl("stop", "klippeye")
    corrupt_all()
    ok("[blackout] before the restart: the half backend would not even start", subprocess.run([sys.executable, "-m", "py_compile", be], capture_output=True).returncode != 0)
    w.systemctl("start", "klippeye")
    ok("[blackout] power back: the backend starts by itself", wait(lambda: backend_release() == "1.0.0", 60), w.service_log("klippeye")[-1500:])
    ok("[blackout] the 4 files are the same as the originals", all(open(p, "rb").read() == good[p] for p in good), [p for p in good if not os.path.isfile(p) or open(p, "rb").read() != good[p]])
    mark = json.load(open(os.path.join(w.data, "repair.json")))
    ok("[blackout] repair.json lists the restored files, no failure", sorted(mark["restored"]) == sorted(["frontend/klippeye_frontend.html", "backend/klippeye_backend.py", "notifier/klippeye_notifier.py", "scripts/klippeye"])
       and mark["failed"] == [], mark)
    ok("[blackout] repair.log tells what happened", "Restored (4)" in open(os.path.join(w.data, "repair.log")).read())
    st, body = http("GET", BACKEND + "/", timeout=5)
    ok("[blackout] the dashboard opens (no longer blank)", st == 200 and "KlippEye dashboard 1.0.0" in str(body), (st, str(body)[:200]))
    ok("[blackout] /api/version reports the last repair", (http("GET", BACKEND + "/api/version", timeout=5)[1].get("repair") or {}).get("restored") == mark["restored"])
    ok("[blackout] the repository is clean but for the person's own things", sorted(l.split()[-1] for l in tree_clean(w).splitlines()) == ["README.md", "frontend/mine.txt"], tree_clean(w))
    ok("[blackout] the person's data, file and change are untouched", open(os.path.join(w.data, "ai.json")).read() == ai_before
       and open(os.path.join(w.repo, "frontend", "mine.txt")).read() == "my notes" and "my change" in open(os.path.join(w.repo, "README.md")).read())
    vv = w.run([os.path.join(w.bin, "klippeye"), "status"], env_extra={"KLIPPEYE_BRAIN_URL": BACKEND})
    ok("[blackout] 'klippeye status' says self-repair is on and shows the last restore", "Self-repair        on; last restore" in vv.stdout, vv.stdout + vv.stderr)

    time.sleep(10)  # the check at backend start runs after 2 seconds, and two checks are at least 5 seconds apart
    open(dash, "wb").close()
    st, body = http("GET", BACKEND + "/", timeout=60)
    ok("[blackout] blank page with the service on: the request repairs it and gets the right dashboard", st == 200 and "KlippEye dashboard 1.0.0" in str(body) and open(dash, "rb").read() == good[dash], (st, str(body)[:200]))
    time.sleep(6)
    open(dash, "wb").write(good[dash][:-30])
    st, body = http("GET", BACKEND + "/", timeout=60)
    ok("[blackout] truncated page: repaired too", st == 200 and open(dash, "rb").read() == good[dash], (st, str(body)[:200]))

    time.sleep(6)
    open(os.path.join(w.data, "no-repair"), "w").close()
    open(dash, "wb").close()
    st, body = http("GET", BACKEND + "/", timeout=60)
    ok("[blackout] repair off: 503 with the emergency page (which reloads itself)", st == 503 and "putting its files back in order" in str(body) and 'http-equiv="refresh"' in str(body), (st, str(body)[:200]))
    ok("[blackout] repair off: the file is not touched", os.path.getsize(dash) == 0)
    os.remove(os.path.join(w.data, "no-repair"))
    time.sleep(6)
    st, body = http("GET", BACKEND + "/", timeout=60)
    ok("[blackout] 'no-repair' removed: at the next load the dashboard is back", st == 200 and open(dash, "rb").read() == good[dash], (st, str(body)[:200]))

    w.systemctl("stop", "klippeye")
    raw = bytearray(good[dash])
    mid = len(raw) // 2
    raw[mid:mid + 20] = b"\x00" * 20
    open(dash, "wb").write(bytes(raw))
    w.systemctl("start", "klippeye")
    ok("[blackout] a hole in the middle (same length): repaired at start by the fingerprints", wait(lambda: backend_release() == "1.0.0" and open(dash, "rb").read() == good[dash], 60), w.service_log("klippeye")[-800:])

    lock = os.path.join(w.repo, ".git", "index.lock")
    open(lock, "w").close()
    open(dash, "wb").close()
    r = w.run(["bash", os.path.join(w.repo, "scripts", "repair.sh")])
    ok("[blackout] a fresh git lock (an update running?): it stays out of the way", "Git is working" in r.stdout and os.path.getsize(dash) == 0 and os.path.exists(lock), r.stdout + r.stderr)
    an_hour_ago = time.time() - 3600
    os.utime(lock, (an_hour_ago, an_hour_ago))
    r = w.run(["bash", os.path.join(w.repo, "scripts", "repair.sh")])
    ok("[blackout] an hour-old lock (left by the power cut): removed, and the file repaired", not os.path.exists(lock) and open(dash, "rb").read() == good[dash], r.stdout + r.stderr)
    ok("[blackout] ... and git works afterwards", sorted(l.split()[-1] for l in tree_clean(w).splitlines()) == ["README.md", "frontend/mine.txt"])

    broken = os.path.join(w.root, "broken_copy")
    shutil.copytree(w.repo, broken, symlinks=True)
    open(os.path.join(broken, ".git", "HEAD"), "w").write("ref: refs/heads/missing\n")
    open(os.path.join(broken, "frontend", "klippeye_frontend.html"), "wb").close()
    r = w.run(["bash", os.path.join(broken, "scripts", "repair.sh")], env_extra={"KLIPPEYE_DATA": os.path.join(broken, "data")})
    ok("[blackout] git damaged: exits with 0, logs the error with the remedy (Recover), invents nothing", r.returncode == 0 and "Recover" in open(os.path.join(broken, "data", "repair.log")).read()
       and os.path.getsize(os.path.join(broken, "frontend", "klippeye_frontend.html")) == 0, r.stdout + r.stderr)
    nogit = os.path.join(w.root, "no_git")
    shutil.copytree(w.repo, nogit, symlinks=True, ignore=shutil.ignore_patterns(".git"))
    r = w.run(["bash", os.path.join(nogit, "scripts", "repair.sh")], env_extra={"KLIPPEYE_DATA": os.path.join(nogit, "data")})
    ok("[blackout] a folder without git: does nothing, no error", r.returncode == 0 and not os.path.exists(os.path.join(nogit, "data")), r.stdout + r.stderr)

    # a service installed before release 1.2 (no ExecStartPre): the backend adds the drop-in by itself
    w.systemctl("stop", "klippeye")
    old_unit = "\n".join(l for l in unit.splitlines() if "repair.sh" not in l and "Before every start" not in l) + "\n"
    open(os.path.join(w.units, "klippeye.service"), "w").write(old_unit)
    dropin = os.path.join(w.units, "klippeye.service.d", "repair.conf")
    os.remove(os.path.join(w.data, "repair.log"))
    w.systemctl("start", "klippeye")
    ok("[blackout] service without ExecStartPre: at start the backend adds the drop-in (klippeye.service.d/repair.conf)",
       wait(lambda: os.path.isfile(dropin), 30) and "ExecStartPre=-/bin/bash %s/scripts/repair.sh" % w.repo in open(dropin).read(), os.listdir(w.units))
    ok("[blackout] ... reloads systemd and logs it", wait(lambda: any(c == "daemon-reload" for c in w.calls()) and "Enabled the file check" in open(os.path.join(w.data, "repair.log")).read(), 15))
    time.sleep(3)
    w.systemctl("stop", "klippeye")
    corrupt_all()
    w.systemctl("start", "klippeye")
    ok("[blackout] at the next power cut the drop-in does the job: it starts by itself", wait(lambda: backend_release() == "1.0.0" and all(open(p, "rb").read() == good[p] for p in good), 60), w.service_log("klippeye")[-800:])
    n_before = open(os.path.join(w.data, "repair.log")).read().count("Enabled the file check")
    w.systemctl("restart", "klippeye")
    wait(lambda: backend_release() == "1.0.0", 60)
    time.sleep(4)
    ok("[blackout] the drop-in is added once only", open(os.path.join(w.data, "repair.log")).read().count("Enabled the file check") == n_before)
    os.remove(dropin)
    os.rmdir(os.path.dirname(dropin))
    r = w.run(["bash", os.path.join(w.repo, "scripts", "repair.sh"), "--enable-at-start", "--quiet"], env_extra={"KLIPPEYE_SUDO": "false"})
    r2 = w.run(["bash", os.path.join(w.repo, "scripts", "ripara.sh"), "--attiva-avvio", "--silenzioso"], env_extra={"KLIPPEYE_SUDO": "false"})  # old name and options too
    lg = open(os.path.join(w.data, "repair.log")).read()
    ok("[blackout] no password-less sudo: no drop-in, the warning logged ONCE, exit 0", r.returncode == 0 and r2.returncode == 0 and not os.path.exists(dropin) and lg.count("Cannot enable the check") == 1, lg)
    os.makedirs(os.path.dirname(dropin), exist_ok=True)
    old_dropin = os.path.join(w.units, "klippeye.service.d", "ripara.conf")  # the drop-in written by 1.1.x/1.2.x
    open(old_dropin, "w").write("[Service]\nExecStartPre=-/bin/bash %s/scripts/ripara.sh --silenzioso\n" % w.repo)
    open(dropin, "w").write("[Service]\nExecStartPre=-/bin/bash %s/scripts/repair.sh --quiet\n" % w.repo)
    r = w.install()
    ok("[blackout] install.sh: the line back in the service file, the old and new drop-ins removed (one line, not two)",
       r.returncode == 0 and "repair.sh" in open(os.path.join(w.units, "klippeye.service")).read() and not os.path.exists(dropin) and not os.path.exists(old_dropin)
       and wait(lambda: backend_release() == "1.0.0", 60), r.stdout + r.stderr)
    w.systemctl("stop", "klippeye")
    open(os.path.join(w.data, "no-repair"), "w").close()
    open(be, "wb").write(good[be][: len(good[be]) // 2])
    w.systemctl("start", "klippeye")
    time.sleep(8)
    ok("[blackout] with 'no-repair' the file is not touched (whoever edits by hand keeps their changes)", len(open(be, "rb").read()) == len(good[be]) // 2 and backend_release() is None)
    os.remove(os.path.join(w.data, "no-repair"))
    for name, text in (("riparazioni.log", "old log\n"), ("ripristino.json", '{"time": 5, "restored": ["x"], "failed": []}')):
        open(os.path.join(w.data, name), "w").write(text)
    os.remove(os.path.join(w.data, "repair.log"))
    os.remove(os.path.join(w.data, "repair.json"))
    w.systemctl("restart", "klippeye")
    ok("[blackout] the data files with their names of before 1.3.0 are renamed (repair.log, repair.json)",
       wait(lambda: os.path.isfile(os.path.join(w.data, "repair.json")) and "old log" in open(os.path.join(w.data, "repair.log")).read(), 60)
       and not os.path.exists(os.path.join(w.data, "riparazioni.log")), os.listdir(w.data))
    ok("[blackout] 'no-repair' removed: repaired at the next start", wait(lambda: backend_release() == "1.0.0" and open(be, "rb").read() == good[be], 60))
    w.teardown()

# ----------------------------------------------------------------------------------- safety checks of the installer
if scenario("safety"):
    w = World("safety")
    w.build(notifier=False)
    env = dict(w.env)
    env.pop("KLIPPEYE_ALLOW_ROOT")
    if os.geteuid() == 0:
        r = subprocess.run(["bash", os.path.join(w.repo, "scripts", "install.sh")], capture_output=True, text=True, env=env, cwd=w.home, timeout=60)
        ok("[safety] run as root without permission: refuses and changes nothing", r.returncode != 0 and "Do not run me" in (r.stdout + r.stderr)
           and not os.path.exists(os.path.join(w.data, "backup")) and not os.path.exists(os.path.join(w.units, "klippeye.service")), r.stdout + r.stderr)
    r = w.install("--nonsense")
    ok("[safety] unknown option: a clear error", r.returncode != 0 and "Unknown option" in (r.stdout + r.stderr), r.stdout + r.stderr)
    r = w.install("--help")
    ok("[safety] --help shows the usage", r.returncode == 0 and "--undo" in r.stdout, r.stdout)
    r = w.install("--aiuto")
    ok("[safety] the Italian options of older releases still work (--aiuto)", r.returncode == 0 and "--undo" in r.stdout, r.stdout)
    w.teardown()

print("\nRESULT: %d check(s) failed" % len(FAILS))
for f in FAILS:
    print("   FAILED:", f)
for s in SKIPPED:
    print("   skipped:", s)
print("ALLDONE" if not FAILS else "ALLDONE_WITH_FAILURES")
sys.exit(1 if FAILS else 0)
