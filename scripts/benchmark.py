#!/usr/bin/env python3
"""
KlippEye benchmark: how much of the Raspberry KlippEye and the printer's services use, measured for a while.

    python3 scripts/benchmark.py [--seconds 30] [--repo DIR] [--json]
    python3 scripts/benchmark.py --models download     # 1.129: also time the networks that could replace the local model

Run by `klippeye benchmark`. For --seconds it samples, every second, the processor time and the memory of:
KlippEye (the service and the notifier), Moonraker, Klipper and the camera streamer, and of the whole Raspberry
(processor, memory, temperature). Then it times the AI monitor's check of one picture on this processor (it needs
OpenCV, as the monitor does) and says what that costs at the monitor's pace.
1.129: it also times the local model on this processor (each picture is judged in up to 3 views: the whole picture, the
part, the place that changed), with 1 core, with the cores KlippEye lets OpenCV use, and with all of them. With --models
it times other networks too: a folder of .onnx files, or "download" for the candidates KlippEye publishes (random
weights, only for timing: ml/export_candidates.py), kept in a folder of the data.
It only READS: nothing is changed, nothing is sent anywhere (--models download only downloads the candidates). Best run
while a print is going, with the monitor on.
Standard library only, except OpenCV and NumPy for the monitor part (skipped without them).
"""
import argparse
import json
import os
import subprocess
import sys
import time

GROUPS = [  # (name, words of the command line that make a process part of it)
    ("KlippEye", ("klippeye_backend.py", "klippeye-notifiche", "klippeye_notifier", "notifier.py")),
    ("Moonraker", ("moonraker",)),
    ("Klipper", ("klippy.py", "klippy/klippy", "-m klippy")),
    ("Camera", ("ustreamer", "camera-streamer", "crowsnest", "mjpg_streamer", "go2rtc", "mediamtx")),
]
HZ = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def processes():
    """{pid: group name} of the processes of the groups (this script excluded)."""
    out = {}
    me = os.getpid()
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) == me:
            continue
        cmd = _read("/proc/%s/cmdline" % entry).replace("\x00", " ")
        if not cmd or "benchmark.py" in cmd:
            continue
        for name, words in GROUPS:
            if any(word in cmd for word in words):
                out[int(entry)] = name
                break
    return out


def process_ticks(pid):
    """utime + stime of a process (clock ticks), or None when it is gone."""
    stat = _read("/proc/%d/stat" % pid)
    if not stat:
        return None
    fields = stat.rsplit(")", 1)[-1].split()
    try:
        return int(fields[11]) + int(fields[12])
    except (IndexError, ValueError):
        return None


def process_rss(pid):
    """Resident memory of a process, in bytes (0 when it is gone)."""
    statm = _read("/proc/%d/statm" % pid).split()
    try:
        return int(statm[1]) * PAGE
    except (IndexError, ValueError):
        return 0


def cpu_times():
    """(busy, total) jiffies of the whole processor."""
    first = _read("/proc/stat").splitlines()[0].split()[1:]
    values = [int(v) for v in first]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values) - idle, sum(values)


def memory():
    info = {}
    for line in _read("/proc/meminfo").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            info[parts[0].rstrip(":")] = int(parts[1]) * 1024
    return info.get("MemTotal", 0), info.get("MemAvailable", 0)


def temperature():
    """The processor's temperature in °C, or None."""
    raw = _read("/sys/class/thermal/thermal_zone0/temp").strip()
    try:
        return int(raw) / 1000.0
    except ValueError:
        return None


def throttled():
    """The Raspberry's own word on under-voltage and heat (vcgencmd), or None where there is no such command."""
    try:
        text = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=5).stdout.strip()
        value = int(text.split("=")[1], 16)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None
    notes = []
    if value & 0x1 or value & 0x10000:
        notes.append("under-voltage" + (" now" if value & 0x1 else " since start"))
    if value & 0x4 or value & 0x40000:
        notes.append("slowed down by heat" + (" now" if value & 0x4 else " since start"))
    return {"raw": hex(value), "notes": notes}


def sample(seconds, progress=None):
    pids = processes()
    first = {pid: process_ticks(pid) for pid in pids}
    busy0, total0 = cpu_times()
    start = time.monotonic()
    peak_rss = {name: 0 for name, _ in GROUPS}
    temps = []
    while True:
        rss = {name: 0 for name, _ in GROUPS}
        for pid, name in pids.items():
            rss[name] += process_rss(pid)
        for name in rss:
            peak_rss[name] = max(peak_rss[name], rss[name])
        t = temperature()
        if t is not None:
            temps.append(t)
        elapsed = time.monotonic() - start
        if progress:
            progress(elapsed)
        if elapsed >= seconds:
            break
        time.sleep(min(1.0, seconds - elapsed))
    elapsed = time.monotonic() - start
    busy1, total1 = cpu_times()
    cores = os.cpu_count() or 1
    groups = {}
    for name, _ in GROUPS:
        ticks = 0
        count = 0
        for pid, group in pids.items():
            if group != name or first.get(pid) is None:
                continue
            last = process_ticks(pid)
            if last is not None:
                ticks += last - first[pid]
                count += 1
        groups[name] = {"processes": count, "cpu_core_percent": round(ticks / HZ / elapsed * 100, 1), "rss_mb": round(peak_rss[name] / 1048576, 1)}
    total_mem, available = memory()
    return {
        "seconds": round(elapsed, 1),
        "cores": cores,
        "groups": groups,
        "system": {
            "cpu_percent": round((busy1 - busy0) * 100.0 / max(1, total1 - total0), 1),
            "memory_mb": round(total_mem / 1048576),
            "memory_available_mb": round(available / 1048576),
            "load": [round(v, 2) for v in os.getloadavg()],
            "temperature_max": round(max(temps), 1) if temps else None,
            "throttled": throttled(),
        },
    }


def monitor_cost(repo, rounds=12):
    """How long the AI monitor takes to check one picture here (ms), on a made-up camera picture of 1920x1080."""
    sys.path.insert(0, os.path.join(repo, "backend"))
    try:
        import monitor_core
    except Exception as error:
        return {"skipped": "the monitor cannot load here (%s)" % str(error)[:80]}
    if not monitor_core.HAS_CV2:
        return {"skipped": "OpenCV is not installed (the monitor needs it too)"}
    cv2, np = monitor_core.cv2, monitor_core.np
    judge = monitor_core.FrameJudge()
    judge.verbose = False
    rng = np.random.default_rng(1)
    base = rng.integers(0, 255, (1080, 1920, 3), dtype=np.uint8)
    spent = []
    now = time.time()
    for i in range(rounds):
        frame = base.copy()
        cv2.circle(frame, (900 + i * 7, 500), 40, (255, 255, 255), -1)  # something that moves
        _, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        raw = encoded.tobytes()
        started = time.perf_counter()  # as the monitor does: decode the camera's picture, then judge it
        decoded = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        judge.judge(decoded, raw, now + i * judge.check_interval)
        spent.append((time.perf_counter() - started) * 1000)
    spent = sorted(spent[2:]) or spent  # the first ones warm up
    per_check = spent[len(spent) // 2]
    return {"ms_per_check": round(per_check, 1), "interval_s": judge.check_interval,
            "cpu_core_percent": round(per_check / 1000.0 / judge.check_interval * 100, 1)}


LOCAL_VIEWS = 3   # the local model judges up to 3 views of each picture (whole, part, change)
RELEASES = "https://api.github.com/repos/BotuPotto/KlippEye/releases?per_page=30"


def download_candidates(folder):
    """The candidate networks attached to KlippEye's releases (bench-<name>.onnx), into `folder`. -> the folder."""
    import urllib.request

    os.makedirs(folder, exist_ok=True)
    request = urllib.request.Request(RELEASES, headers={"Accept": "application/vnd.github+json", "User-Agent": "klippeye-benchmark"})
    with urllib.request.urlopen(request, timeout=30) as answer:
        releases = json.loads(answer.read().decode("utf-8"))
    for release in releases:
        assets = [a for a in release.get("assets") or [] if a.get("name", "").startswith("bench-") and a["name"].endswith(".onnx")]
        if not assets:
            continue
        for asset in assets:
            target = os.path.join(folder, asset["name"][len("bench-"):])
            if os.path.isfile(target) and os.path.getsize(target) == asset.get("size"):
                continue
            sys.stderr.write("Downloading %s (%.1f MB)...\n" % (asset["name"], asset.get("size", 0) / 1048576.0))
            urllib.request.urlretrieve(asset["browser_download_url"], target + ".part")
            os.replace(target + ".part", target)
        return folder
    raise RuntimeError("no candidate networks published yet")


def model_cost(repo, folder=None, rounds=12, interval=3.0):
    """How long the local model (and each .onnx of `folder`) takes to judge one view here (ms), with 1 core, with the
    cores KlippEye lets OpenCV use, and with all of them; and what a check costs at the monitor's pace."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return {"skipped": "OpenCV is not installed (the monitor needs it too)"}
    sys.path.insert(0, os.path.join(repo, "backend"))
    try:
        import monitor_core
        allowed = monitor_core.opencv_threads()
    except Exception:  # noqa: BLE001 - an older checkout: the same rule
        allowed = max(1, min(2, (os.cpu_count() or 1) - 1))
    models = []
    base = os.path.join(repo, "models", "base", "model.onnx")
    if os.path.isfile(base):
        models.append(("in use (MobileNetV3-Small)", base))
    if folder:
        for name in sorted(os.listdir(folder)):
            if name.endswith(".onnx"):
                models.append((name[:-5], os.path.join(folder, name)))
    if not models:
        return {"skipped": "no local model here"}
    rng = np.random.default_rng(2)
    frame = rng.integers(0, 255, (1080, 1920, 3), dtype=np.uint8)
    cores = os.cpu_count() or 1
    thread_counts = sorted({1, allowed, cores})
    before = cv2.getNumThreads()
    out = []
    try:
        for label, path in models:
            try:
                net = cv2.dnn.readNetFromONNX(path)
                names = net.getUnconnectedOutLayersNames()
            except Exception as error:  # noqa: BLE001 - OpenCV's own errors
                out.append({"model": label, "error": str(error).splitlines()[0][:120]})
                continue
            row = {"model": label, "mb": round(os.path.getsize(path) / 1048576.0, 1), "ms": {}}
            for threads in thread_counts:
                cv2.setNumThreads(threads)
                spent = []
                for _ in range(rounds + 2):
                    started = time.perf_counter()   # as the monitor does: resize, normalise, run
                    small = cv2.resize(frame, (224, 224), interpolation=cv2.INTER_AREA)
                    blob = cv2.dnn.blobFromImage(small, 1 / 255.0, (224, 224), swapRB=True)
                    net.setInput(blob)
                    net.forward(names)
                    spent.append((time.perf_counter() - started) * 1000)
                spent = sorted(spent[2:])
                row["ms"][threads] = round(spent[len(spent) // 2], 1)
            row["ort_ms"] = _ort_ms(path, allowed, frame, rounds, cv2, np)   # 1.133: None without onnxruntime
            ms = row["ms"][allowed]
            row["check_ms"] = round(ms * LOCAL_VIEWS, 1)
            row["core_percent"] = round(ms * LOCAL_VIEWS / 1000.0 / interval * 100, 1)
            out.append(row)
    finally:
        cv2.setNumThreads(before)
    return {"cores": cores, "allowed": allowed, "threads": thread_counts, "views": LOCAL_VIEWS, "interval_s": interval, "models": out}


def _ort_ms(path, threads, frame, rounds, cv2, np):
    """1.133: ms per view with onnxruntime (the monitor uses it when installed), with `threads` cores; None without it."""
    try:
        import onnxruntime
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads, options.inter_op_num_threads = threads, 1
        session = onnxruntime.InferenceSession(path, options, providers=["CPUExecutionProvider"])
    except Exception:  # noqa: BLE001 - not installed, or it cannot run the file
        return None
    name, spent = session.get_inputs()[0].name, []
    for _ in range(rounds + 2):
        started = time.perf_counter()
        small = cv2.resize(frame, (224, 224), interpolation=cv2.INTER_AREA)
        session.run(None, {name: cv2.dnn.blobFromImage(small, 1 / 255.0, (224, 224), swapRB=True)})
        spent.append((time.perf_counter() - started) * 1000)
    spent = sorted(spent[2:])
    return round(spent[len(spent) // 2], 1)


def model_report(cost):
    if cost.get("skipped"):
        return ["Local model: not measured (%s)" % cost["skipped"]]
    lines = ["", "Local model: ms per view (up to %d views per check, a check every %s s; KlippEye lets it use %d core%s)"
             % (cost["views"], cost["interval_s"], cost["allowed"], "s" if cost["allowed"] > 1 else "")]
    lines.append("%-28s %6s " % ("", "MB") + " ".join("%9s" % ("%d core%s" % (t, "s" if t > 1 else "")) for t in cost["threads"]) + "   per check   of 1 core")
    for row in cost["models"]:
        if row.get("error"):
            lines.append("%-28s  OpenCV cannot run it: %s" % (row["model"][:28], row["error"]))
            continue
        lines.append("%-28s %6s " % (row["model"][:28], row["mb"]) + " ".join("%9s" % row["ms"][t] for t in cost["threads"])
                     + "   %6s ms   %6s%%" % (row["check_ms"], row["core_percent"]))
        if row.get("ort_ms") is not None:
            lines.append("%-28s %6s %9s   with onnxruntime, %d core%s" % ("", "", row["ort_ms"], cost["allowed"], "s" if cost["allowed"] > 1 else ""))
    return lines


def verdict(result):
    """Plain words on what the figures mean."""
    notes = []
    s = result["system"]
    if s["cpu_percent"] >= 85:
        notes.append("The processor is almost always busy (%s%%): the camera or Klipper may stutter." % s["cpu_percent"])
    elif s["cpu_percent"] >= 60:
        notes.append("The processor is quite busy (%s%%)." % s["cpu_percent"])
    if s["memory_mb"] and s["memory_available_mb"] < s["memory_mb"] * 0.15:
        notes.append("Little memory left (%s MB of %s MB)." % (s["memory_available_mb"], s["memory_mb"]))
    if s["temperature_max"] is not None and s["temperature_max"] >= 80:
        notes.append("The processor reached %s °C: at 80-85 °C the Raspberry slows down; a heatsink or a fan helps." % s["temperature_max"])
    for note in ((s.get("throttled") or {}).get("notes") or []):
        notes.append("The Raspberry reports %s: check the power supply%s." % (note, " and the cooling" if "heat" in note else ""))
    klippeye = result["groups"].get("KlippEye", {})
    if klippeye.get("processes") == 0:
        notes.append("The KlippEye service is not running: its figures are 0.")
    mon = result.get("monitor") or {}
    if mon.get("cpu_core_percent", 0) >= 50:
        notes.append("The AI monitor's check takes %s ms every %s s: raise «How often it looks at the camera» (Settings → Monitor thresholds)." % (mon["ms_per_check"], mon["interval_s"]))
    for row in (result.get("local") or {}).get("models") or []:
        if row.get("core_percent", 0) >= 35:
            notes.append("%s: %s ms per check every %s s, too much for this Raspberry while it prints."
                         % (row["model"], row["check_ms"], result["local"]["interval_s"]))
    if not notes:
        notes.append("All fine: the Raspberry has room to spare.")
    return notes


def report(result):
    lines = ["KlippEye benchmark · %s s · %s cores" % (result["seconds"], result["cores"]), ""]
    lines.append("%-10s %10s %18s %10s" % ("", "processes", "processor (1 core)", "memory"))
    for name, _ in GROUPS:
        g = result["groups"][name]
        lines.append("%-10s %10d %17s%% %7s MB" % (name, g["processes"], g["cpu_core_percent"], g["rss_mb"]))
    s = result["system"]
    lines += ["", "Raspberry: processor %s%% busy (all cores), load %s, memory %s MB free of %s MB" % (s["cpu_percent"], " ".join(str(v) for v in s["load"]), s["memory_available_mb"], s["memory_mb"])]
    if s["temperature_max"] is not None:
        lines.append("Temperature: up to %s °C" % s["temperature_max"])
    if s["throttled"] is not None:
        lines.append("Power and heat: %s" % (", ".join(s["throttled"]["notes"]) or "no problem reported"))
    mon = result.get("monitor") or {}
    if mon.get("skipped"):
        lines.append("AI monitor: not measured (%s)" % mon["skipped"])
    elif mon:
        lines.append("AI monitor: %s ms per picture, one every %s s = %s%% of one core" % (mon["ms_per_check"], mon["interval_s"], mon["cpu_core_percent"]))
    if result.get("local"):
        lines += model_report(result["local"])
    lines += [""] + ["- " + note for note in result["verdict"]]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="How much of the Raspberry KlippEye and the printer's services use.")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-monitor", action="store_true", help="do not time the AI monitor's check")
    parser.add_argument("--models", default="", help='a folder of .onnx networks to time too, or "download" for the candidates')
    parser.add_argument("--model-only", action="store_true", help="only time the local model (no sampling of the services)")
    parser.add_argument("--rounds", type=int, default=12)
    args = parser.parse_args(argv)
    folder = args.models or None
    if folder == "download":
        data = os.environ.get("KLIPPEYE_DATA") or os.path.expanduser("~/printer_data/klippeye")
        folder = download_candidates(os.path.join(data if os.path.isdir(data) else os.path.expanduser("~"), "bench-models"))
    if args.model_only:
        cost = model_cost(args.repo, folder, max(1, args.rounds))
        print(json.dumps(cost, indent=2) if args.json else "\n".join(model_report(cost)).strip())
        return 0 if not cost.get("skipped") and not any(r.get("error") for r in cost.get("models", [])) else 1
    seconds = max(2.0, min(600.0, args.seconds))
    show = None
    if not args.json and sys.stderr.isatty():
        show = lambda elapsed: sys.stderr.write("\rMeasuring... %d/%d s " % (elapsed, seconds)) or sys.stderr.flush()
    result = sample(seconds, show)
    if show:
        sys.stderr.write("\r" + " " * 30 + "\r")
    result["monitor"] = None if args.no_monitor else monitor_cost(args.repo)
    result["local"] = None if args.no_monitor else model_cost(args.repo, folder, max(1, args.rounds))
    result["verdict"] = verdict(result)
    print(json.dumps(result, indent=2) if args.json else report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
