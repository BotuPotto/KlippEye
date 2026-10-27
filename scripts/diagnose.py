#!/usr/bin/env python3
"""
KlippEye diagnostic report: what is needed to understand a problem, in one text you can share.

    python3 scripts/diagnose.py [--repo DIR] [--data DIR] [--backend URL] [--moonraker URL]

Run by `klippeye diagnose` (terminal) and by the backend for Settings -> Updates -> "Diagnostic report" (/api/diagnose).
It only READS. Secrets are never printed: the AI key, the password hash, the internal token and the Firebase keys are
not read at all (only whether the files exist, their size and permissions), and anything that looks like a key or a
token in the logs is replaced by [hidden].

Standard library only. Every section survives a failure of its own (a missing command, a service that does not answer):
the report says what could not be read and goes on.
"""
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request

HIDDEN = "[hidden]"
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]+-----[\s\S]*?-----END [A-Z ]+-----"),        # private keys
    re.compile(r"\b(gsk_|sk-or-|sk-|xai-|LLM-|AIza)[A-Za-z0-9_\-]{8,}"),        # AI and Google API keys
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)(\"?(api_key|apikey|password|passwd|token|secret|authorization|private_key)\"?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|\S+)"),
    re.compile(r"(?i)(klippeye_session=)[^;\s]+"),
    re.compile(r"(https?://)[^/\s:@]+:[^/\s@]+@"),                             # credentials inside an address
]


def redact(text):
    """`text` with everything that looks like a secret replaced by [hidden]."""
    text = str(text)
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 3:
            text = pattern.sub(lambda m: m.group(1) + HIDDEN, text)
        elif pattern.groups == 1 and pattern.pattern.startswith("(https?"):
            text = pattern.sub(lambda m: m.group(1) + HIDDEN + "@", text)
        elif pattern.groups >= 1 and pattern.pattern.startswith("(?i)("):
            text = pattern.sub(lambda m: m.group(1) + HIDDEN, text)
        else:
            text = pattern.sub(HIDDEN, text)
    return text


OUT = []


def line(text=""):
    OUT.append(redact(text))


def section(title):
    line()
    line("== " + title)


def run(args, timeout=10, cwd=None):
    """The output of a command (stdout + stderr, stripped), or '(not available: reason)'."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd, stdin=subprocess.DEVNULL)
        return (r.stdout + (("\n" + r.stderr) if r.stderr.strip() else "")).rstrip()
    except FileNotFoundError:
        return "(not available: %s is not installed)" % args[0]
    except subprocess.TimeoutExpired:
        return "(not available: %s did not answer within %d s)" % (args[0], timeout)
    except OSError as error:
        return "(not available: %s)" % error


def get_json(url, headers=None, timeout=5):
    """(data, None) or (None, reason)."""
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace")), None
    except Exception as error:  # noqa: BLE001 - any failure is reported, never raised
        return None, str(error)


def read_text(path, limit=4000):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return None


def human_size(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return ("%d %s" % (size, unit)) if unit == "B" else ("%.1f %s" % (size, unit))
        size /= 1024.0
    return str(size)


# ----------------------------------------------------------------------------------------------------------------- sections
def program(repo):
    section("KlippEye")
    release = (read_text(os.path.join(repo, "VERSION"), 64) or "unknown").strip()
    line("release:        %s" % release)
    line("program folder: %s" % repo)
    if not os.path.isdir(os.path.join(repo, ".git")):
        line("git:            not a git repository (updates from the dashboard cannot work)")
        return
    line("commit:         %s" % run(["git", "-C", repo, "log", "-1", "--format=%h %cd %s", "--date=short"]))
    line("branch:         %s" % run(["git", "-C", repo, "rev-parse", "--abbrev-ref", "HEAD"]))
    line("origin:         %s" % run(["git", "-C", repo, "remote", "get-url", "origin"]))
    changed = run(["git", "-C", repo, "status", "--porcelain", "-uno"])
    line("changed files:  %s" % ("none" if not changed else ""))
    for entry in changed.splitlines()[:30] if changed else []:
        line("    " + entry)
    tags = run(["git", "-C", repo, "describe", "--tags", "--abbrev=0"])
    line("latest tag:     %s" % (tags if tags and "fatal" not in tags else "none"))


def system(data):
    section("System")
    os_release = read_text("/etc/os-release") or ""
    pretty = re.search(r'^PRETTY_NAME="?([^"\n]*)"?', os_release, re.M)
    line("os:             %s" % (pretty.group(1) if pretty else platform.platform()))
    line("kernel:         %s %s" % (platform.release(), platform.machine()))
    model = (read_text("/proc/device-tree/model", 200) or "").strip("\x00\n ")
    if model:
        line("board:          %s" % model)
    uptime = read_text("/proc/uptime", 100)
    if uptime:
        line("up for:         %.1f hours" % (float(uptime.split()[0]) / 3600))
    try:
        load = os.getloadavg()
        line("load:           %.2f %.2f %.2f (%d CPUs)" % (load[0], load[1], load[2], os.cpu_count() or 0))
    except OSError:
        pass
    meminfo = read_text("/proc/meminfo") or ""
    total = re.search(r"MemTotal:\s+(\d+)", meminfo)
    available = re.search(r"MemAvailable:\s+(\d+)", meminfo)
    if total and available:
        line("memory:         %s free of %s" % (human_size(int(available.group(1)) * 1024), human_size(int(total.group(1)) * 1024)))
    for label, path in (("disk /", "/"), ("disk data", data)):
        try:
            usage = shutil.disk_usage(path)
            line("%-15s %s free of %s" % (label + ":", human_size(usage.free), human_size(usage.total)))
        except OSError:
            pass
    temp = read_text("/sys/class/thermal/thermal_zone0/temp", 20)
    if temp and temp.strip().isdigit():
        line("cpu temperature: %.1f C" % (int(temp) / 1000))
    line("python:         %s (%s)" % (platform.python_version(), sys.executable))
    for module in ("flask", "flask_cors", "requests", "numpy", "cv2"):
        found = run([sys.executable, "-W", "ignore", "-c", "import %s as m; print(getattr(m, '__version__', 'installed'))" % module]).strip()
        line("  %-13s %s" % (module, found if "Error" not in found else "missing"))


def services():
    section("Services")
    for name in ("klippeye", "klippeye-notifier", "moonraker", "klipper", "crowsnest"):
        state = run(["systemctl", "is-active", name], timeout=5).strip().splitlines()
        state = (state[0] if state else "?")[:60]
        line("  %-18s %s" % (name, state))


def backend(url, token):
    section("Backend (%s)" % url)
    headers = {"X-KlippEye-Token": token} if token else {}
    version, error = get_json(url + "/api/version", headers)
    if error:
        line("does NOT answer: %s" % error)
        return
    for key in ("release", "api", "uptime", "data_dir", "repair"):
        if key in version:
            line("%-15s %s" % (key + ":", json.dumps(version[key], ensure_ascii=False)))
    auth, _ = get_json(url + "/api/auth/status", headers)
    if isinstance(auth, dict):
        line("password:       %s; network checks: %s; extra host names: %s" % (
            "on" if auth.get("enabled") else "off", "on" if auth.get("network_checks", True) else "off", ", ".join(auth.get("allowed_hosts") or []) or "none"))
    detector, _ = get_json(url + "/api/print/detector/status", headers)
    if isinstance(detector, dict):
        stats = detector.get("stats") or {}
        line("AI monitor:     %s; status: %s; checks: %s; last score: %s%%" % (
            "on" if detector.get("enabled", stats.get("enabled")) else "off", stats.get("status", "?"), stats.get("frames_checked", "?"), stats.get("last_score", "?")))
        if "check_ms" in stats or "cpu_percent" in stats:
            line("monitor load:   %s ms per check; backend CPU %s%% of one core (last minute)" % (stats.get("check_ms", "?"), stats.get("cpu_percent", "?")))
    recordings, _ = get_json(url + "/api/recordings", headers)
    if isinstance(recordings, dict) and "sessions" in recordings:
        sessions = recordings.get("sessions") or []
        marked = sum(1 for s in sessions if (s.get("label") or {}).get("outcome"))
        line("recordings:     %s; %d print(s), %d marked, %d MB of %d MB; %s" % (
            "on" if recordings.get("enabled") else "off", len(sessions), marked, (recordings.get("used_bytes") or 0) // 1024 ** 2,
            (recordings.get("max_bytes") or 0) // 1024 ** 2, recordings.get("status", "?")))
    ai, _ = get_json(url + "/api/ai/config", headers)
    if isinstance(ai, dict):
        line("AI service:     %s" % ("%s, model %s" % (ai.get("provider", "?"), ai.get("model") or "default") if ai.get("configured") else "no key"))
    app, _ = get_json(url + "/api/app/version", headers)
    if isinstance(app, dict):
        line("android app:    %s" % (app.get("version") if app.get("available") else "not offered (%s)" % app.get("reason", "?")))


def moonraker(url):
    section("Moonraker (%s)" % url)
    info, error = get_json(url + "/server/info")
    if error:
        line("does NOT answer: %s" % error)
        return
    result = (info or {}).get("result") or {}
    line("moonraker:      %s" % result.get("moonraker_version", "?"))
    line("klippy:         %s" % result.get("klippy_state", "?"))
    printer, _ = get_json(url + "/printer/info")
    printer = (printer or {}).get("result") or {}
    if printer:
        line("klipper:        %s (%s)" % (printer.get("software_version", "?"), printer.get("state", "?")))
        message = (printer.get("state_message") or "").strip()
        if message and printer.get("state") != "ready":
            line("klipper says:   %s" % message.splitlines()[0][:200])
    status, _ = get_json(url + "/machine/update/status?refresh=false", timeout=15)
    entry = (((status or {}).get("result") or {}).get("version_info") or {})
    ours = entry.get("klippeye")
    if ours is None:
        line("update manager: KlippEye is NOT listed (run scripts/install.sh again)")
    else:
        line("update manager: version %s, remote %s, channel %s, valid %s, dirty %s, %s commit(s) behind" % (
            ours.get("version", "?"), ours.get("remote_version", "?"), ours.get("channel", "?"), ours.get("is_valid", "?"),
            ours.get("is_dirty", "?"), ours.get("commits_behind_count", len(ours.get("commits_behind") or []))))
        for warning in (ours.get("warnings") or [])[:5]:
            line("    warning: %s" % warning)
    settings, _ = get_json(url + "/server/database/item?namespace=klippeye&key=settings")
    value = ((settings or {}).get("result") or {}).get("value")
    if isinstance(value, dict):
        notes = value.get("notifications") or {}
        ai = value.get("ai") or {}
        line("dashboard settings: language %s; notifications off: %s; automatic pause %s, cancel %s" % (
            value.get("language", "?"), ", ".join(k for k, v in notes.items() if v is False) or "none",
            "on" if ai.get("autoPause") else "off", "on" if ai.get("autoCancel") else "off"))
    else:
        line("dashboard settings: not saved yet")
    notifier, _ = get_json(url + "/server/database/item?namespace=klippeye&key=notifier")
    value = ((notifier or {}).get("result") or {}).get("value")
    if isinstance(value, dict):
        seen = value.get("seen")
        line("notifier:       version %s, last seen %s s ago" % (value.get("version", "?"), int(time.time() - seen) if isinstance(seen, (int, float)) else "?"))


def data_folder(data):
    section("Data folder (%s)" % data)
    if not os.path.isdir(data):
        line("missing")
        return
    for name in sorted(os.listdir(data)):
        path = os.path.join(data, name)
        try:
            st = os.stat(path)
        except OSError:
            continue
        kind = "folder" if os.path.isdir(path) else human_size(st.st_size)
        line("  %-24s %-10s mode %s" % (name, kind, oct(st.st_mode & 0o777)[2:]))  # names and sizes only: contents are never read
    mark = read_text(os.path.join(data, "repair.json"), 2000)
    if mark:
        line("last self-repair: %s" % mark.strip())
    if os.path.exists(os.path.join(data, "no-repair")):
        line("self-repair is OFF (no-repair exists)")
    log = read_text(os.path.join(data, "repair.log"), 200000)
    if log:
        line("repair.log (last lines):")
        for entry in log.strip().splitlines()[-8:]:
            line("    " + entry)


def logs():
    for unit in ("klippeye", "klippeye-notifier"):
        section("Log of %s (last 40 lines)" % unit)
        text = run(["journalctl", "-u", unit, "-n", "40", "--no-pager", "-o", "short-iso"], timeout=15)
        for entry in text.splitlines()[-40:]:
            line("    " + entry[:300])


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description="KlippEye diagnostic report (nothing secret is included)")
    parser.add_argument("--repo", default=os.path.dirname(here))
    parser.add_argument("--data", default=os.environ.get("KLIPPEYE_DATA") or os.path.expanduser("~/printer_data/klippeye"))
    parser.add_argument("--backend", default=os.environ.get("KLIPPEYE_BRAIN_URL") or "http://127.0.0.1:8085")
    parser.add_argument("--moonraker", default=os.environ.get("KLIPPEYE_MOONRAKER_URL") or "http://127.0.0.1:7125")
    parser.add_argument("--no-logs", action="store_true", help="leave out the service logs")
    args = parser.parse_args(argv)
    token = (read_text(os.path.join(args.data, "internal.token"), 200) or "").strip()
    line("KlippEye diagnostic report - %s" % time.strftime("%Y-%m-%d %H:%M:%S %z"))
    line("Nothing secret is included: keys, password and tokens are never read or are shown as %s." % HIDDEN)
    for step in (lambda: program(args.repo), lambda: system(args.data), services, lambda: backend(args.backend.rstrip("/"), token),
                 lambda: moonraker(args.moonraker.rstrip("/")), lambda: data_folder(args.data)) + (() if args.no_logs else (logs,)):
        try:
            step()
        except Exception as error:  # noqa: BLE001 - one broken section must not hide the others
            line("(this section failed: %s)" % error)
    sys.stdout.write("\n".join(OUT) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
