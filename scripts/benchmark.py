#!/usr/bin/env python3
"""
KlippEye benchmark: how much of the Raspberry KlippEye and the printer's services use, measured for a while.

    python3 scripts/benchmark.py [--seconds 30] [--repo DIR] [--json]

Run by `klippeye benchmark`. For --seconds it samples, every second, the processor time and the memory of:
KlippEye (the service and the notifier), Moonraker, Klipper and the camera streamer, and of the whole Raspberry
(processor, memory, temperature). Then it times the AI monitor's check of one picture on this processor (it needs
OpenCV, as the monitor does) and says what that costs at the monitor's pace.
It only READS: nothing is changed, nothing is sent anywhere. Best run while a print is going, with the monitor on.
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
    lines += [""] + ["- " + note for note in result["verdict"]]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="How much of the Raspberry KlippEye and the printer's services use.")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-monitor", action="store_true", help="do not time the AI monitor's check")
    args = parser.parse_args(argv)
    seconds = max(2.0, min(600.0, args.seconds))
    show = None
    if not args.json and sys.stderr.isatty():
        show = lambda elapsed: sys.stderr.write("\rMeasuring... %d/%d s " % (elapsed, seconds)) or sys.stderr.flush()
    result = sample(seconds, show)
    if show:
        sys.stderr.write("\r" + " " * 30 + "\r")
    result["monitor"] = None if args.no_monitor else monitor_cost(args.repo)
    result["verdict"] = verdict(result)
    print(json.dumps(result, indent=2) if args.json else report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
