#!/usr/bin/env python3
"""
Measures KlippEye's AI print monitor on the recorded prints: it runs the monitor's judging (backend/monitor_core.py, the same
code the backend uses live) again on the pictures kept by the recorder (backend/recorder.py) and counts the alarms.

    klippeye replay                          every recording, with the thresholds each print was recorded with
    klippeye replay --current                with the thresholds in use now (monitor.json)
    klippeye replay --set sensitivity=45 --set persist_checks=4      what if: other thresholds
    klippeye replay --session 20261028-101500-benchy                 only that recording (repeatable)
    klippeye replay --json result.json       also writes the result as JSON (the dashboard uses this)

An alarm is the moment the monitor would call the AI. Whether it was false comes from your labels (Settings → Recordings):
  * a print marked "went fine": every alarm is false;
  * a print marked "failed from here": the alarms before that moment are false, the first one after it caught the problem;
  * not marked: when one of its alarms is marked "right" the print failed from that alarm; when all its alarms are marked
    "false alarm" and the print completed, it went fine; otherwise it is not known.
The AI itself is never called: this measures the local check that decides when to ask it.

Machine masks (phase 4b): with a camera calibration (camera.json) the toolhead and the gantry are left out at every picture
that was recorded with the toolhead position (KlippEye 1.13 and later), as the live monitor does. To compare:
    klippeye replay --set machine_masks=off
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "backend"))
import machine_masks  # noqa: E402
import monitor_core  # noqa: E402
from monitor_core import FrameJudge  # noqa: E402

ID_CHARS = "0123456789-_.abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def default_data_dir():
    chosen = os.environ.get("KLIPPEYE_DATA", "").strip()
    if chosen:
        return os.path.expanduser(chosen)
    home = os.path.expanduser("~")
    return os.path.join(home, "printer_data", "klippeye") if os.path.isdir(os.path.join(home, "printer_data")) else os.path.join(home, "klippeye_data")


def parse_value(text):
    """A --set value: a number, yes/no, or a list of numbers (roi=20,20,60,60)."""
    low = text.strip().lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if "," in text and not text.strip().startswith(","):
        return [float(part) for part in text.split(",")]
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def read_json(path, fallback=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return fallback


def truth_of(session):
    """(outcome "ok" | "failed" | None, failed_at, where it comes from: "you" | "alerts" | None)."""
    label = session.get("label") or {}
    if label.get("outcome") in ("ok", "failed"):
        return label["outcome"], label.get("failed_at"), "you"
    alerts = [a for a in session.get("alerts") or [] if a.get("label") in ("false", "right")]
    right = sorted(a.get("t") for a in alerts if a.get("label") == "right" and isinstance(a.get("t"), (int, float)))
    if right:
        return "failed", right[0], "alerts"
    every = session.get("alerts") or []
    if every and len(alerts) == len(every) and session.get("end_state") == "complete":
        return "ok", None, "alerts"
    return None, None, None


def load_masks(data_dir):
    """The camera calibration and the shape of the moving parts, when the calibration is good enough. -> dict or None."""
    calibration = read_json(os.path.join(data_dir, "camera.json"))
    if not isinstance(calibration, dict) or calibration.get("quality") not in ("good", "fair") or not calibration.get("params"):
        return None
    stored = read_json(os.path.join(data_dir, "machine_shape.json"))
    try:
        shape = machine_masks.clean_shape(stored) if stored else machine_masks.from_toolhead_box(calibration.get("toolhead"))
    except ValueError:
        shape = machine_masks.from_toolhead_box(calibration.get("toolhead"))
    return {"calibration": calibration, "shape": shape, "x_range": shape.get("x_range")}


def replay_session(folder, session, settings, masks=None):
    """Runs the monitor on one recording. -> dict with the alarms and the time it took.
    `masks` (load_masks): leave out the toolhead and the gantry at the recorded positions (unless machine_masks is off)."""
    cv2, np = monitor_core.cv2, monitor_core.np
    use_masks = masks is not None and settings.get("machine_masks", True) is not False
    judge = FrameJudge()
    judge.verbose = False
    judge.apply_config(settings)
    frames = []
    try:
        with open(os.path.join(folder, "frames.jsonl"), encoding="utf-8") as f:
            for line in f:
                try:
                    frames.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    frames.sort(key=lambda row: row.get("n", 0))
    alarms, judged, spent, masked = [], 0, 0.0, 0
    for row in frames:
        t = row.get("t")
        if not isinstance(t, (int, float)) or t < judge.cooldown_until:
            continue
        try:
            with open(os.path.join(folder, "%06d.jpg" % row["n"]), "rb") as f:
                raw = f.read()
        except (OSError, KeyError):
            continue
        started = time.perf_counter()
        frame = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            continue
        ignore = None
        if use_masks and row.get("live"):
            ignore = machine_masks.mask(cv2, np, masks["calibration"], masks["shape"], [row.get("live"), row.get("live2")],
                                        monitor_core.OPENCV_WIDTH // 2, monitor_core.OPENCV_HEIGHT // 2, masks["x_range"])
            masked += ignore is not None
        _, triggered = judge.judge(frame, raw, t, ignore)
        spent += time.perf_counter() - started
        judged += 1
        if triggered:
            alarms.append({"t": round(t, 2), "frame": row["n"], "layer": row.get("layer"), "progress": row.get("progress")})
    times = [row["t"] for row in frames if isinstance(row.get("t"), (int, float))]
    return {"frames": len(frames), "judged": judged, "alarms": alarms, "masked": masked, "ms_per_check": round(spent * 1000 / judged, 1) if judged else None,
            "first": min(times) if times else session.get("started"), "last": max(times) if times else (session.get("ended") or session.get("started"))}


def measure(data_dir, ids=None, current=False, overrides=None):
    root = os.path.join(data_dir, "recordings")
    now_values = (read_json(os.path.join(data_dir, "monitor.json"), {}) or {}).get("values") or {}
    masks = load_masks(data_dir)
    try:
        names = sorted(n for n in os.listdir(root) if all(c in ID_CHARS for c in n) and os.path.isfile(os.path.join(root, n, "session.json")))
    except OSError:
        names = []
    if ids:
        names = [n for n in names if n in ids]
    sessions, total = [], {"hours": 0.0, "alarms": 0, "false": 0, "known_hours": 0.0, "failures": 0, "seen": 0, "delays": [], "live": 0, "ms": []}
    for name in names:
        session = read_json(os.path.join(root, name, "session.json"))
        if not isinstance(session, dict):
            continue
        settings = dict(session.get("config") or {})
        if current:
            settings.update(now_values)
        settings.update(overrides or {})
        result = replay_session(os.path.join(root, name), session, settings, masks)
        outcome, failed_at, source = truth_of(session)
        hours = max(0.0, (result["last"] or 0) - (result["first"] or 0)) / 3600.0
        false = seen = delay = None
        known_hours = 0.0
        if outcome == "ok":
            false, known_hours = len(result["alarms"]), hours
        elif outcome == "failed" and isinstance(failed_at, (int, float)):
            before = [a for a in result["alarms"] if a["t"] < failed_at]
            after = [a for a in result["alarms"] if a["t"] >= failed_at]
            false, known_hours = len(before), max(0.0, failed_at - result["first"]) / 3600.0
            seen = bool(after)
            delay = round(after[0]["t"] - failed_at) if after else None
        labels = [a.get("label") for a in session.get("alerts") or []]
        row = {"id": name, "file": session.get("file", ""), "end_state": session.get("end_state"), "hours": round(hours, 2), "frames": result["frames"],
               "outcome": outcome, "failed_at": failed_at, "label_source": source, "alarms": len(result["alarms"]),
               "alarm_list": result["alarms"], "per_hour": round(len(result["alarms"]) / hours, 2) if hours > 0 else None,
               "false": false, "seen": seen, "delay_s": delay, "live_alarms": len(session.get("live_triggers") or []),
               "alerts_false": labels.count("false"), "alerts_right": labels.count("right"),
               "ms_per_check": result["ms_per_check"], "live_cpu": session.get("cpu") or {}, "masked_frames": result["masked"]}
        sessions.append(row)
        total["hours"] += hours
        total["alarms"] += row["alarms"]
        total["live"] += row["live_alarms"]
        if false is not None:
            total["false"] += false
            total["known_hours"] += known_hours
        if outcome == "failed":
            total["failures"] += 1
            if seen:
                total["seen"] += 1
                total["delays"].append(delay)
        if result["ms_per_check"] is not None:
            total["ms"].append(result["ms_per_check"])
    summary = {
        "recordings": len(sessions), "hours": round(total["hours"], 2), "alarms": total["alarms"], "live_alarms": total["live"],
        "per_hour": round(total["alarms"] / total["hours"], 2) if total["hours"] > 0 else None,
        "false": total["false"], "known_hours": round(total["known_hours"], 2),
        "false_per_hour": round(total["false"] / total["known_hours"], 2) if total["known_hours"] > 0 else None,
        "failures": total["failures"], "seen": total["seen"],
        "average_delay_s": round(sum(total["delays"]) / len(total["delays"])) if total["delays"] else None,
        "ms_per_check": round(sum(total["ms"]) / len(total["ms"]), 1) if total["ms"] else None,
        "masked_frames": sum(s["masked_frames"] for s in sessions), "frames": sum(s["frames"] for s in sessions),
        "masks": "off" if (overrides or {}).get("machine_masks") is False else ("on" if masks else "no calibration"),
    }
    return {"ok": True, "time": int(time.time()), "settings": "current" if current else "as recorded", "overrides": overrides or {},
            "sessions": sessions, "total": summary}


def fmt(value, suffix=""):
    return "-" if value is None else "%s%s" % (value, suffix)


def table(result):
    rows = [("Recording", "File", "Hours", "Label", "Alarms", "/hour", "False", "Problem seen", "Live")]
    for s in result["sessions"]:
        if s["outcome"] == "failed":
            label = "failed" + ("" if s["label_source"] == "you" else " (alerts)")
        elif s["outcome"] == "ok":
            label = "went fine" + ("" if s["label_source"] == "you" else " (alerts)")
        else:
            label = "not marked"
        seen = "-" if s["seen"] is None else ("yes, after %s" % minutes(s["delay_s"]) if s["seen"] else "NO")
        rows.append((s["id"][:15], (s["file"] or "")[:24], "%.1f" % s["hours"], label, str(s["alarms"]), fmt(s["per_hour"]), fmt(s["false"]), seen, str(s["live_alarms"])))
    t = result["total"]
    rows.append(("TOTAL", "%d print%s" % (t["recordings"], "" if t["recordings"] == 1 else "s"), "%.1f" % t["hours"], "", str(t["alarms"]), fmt(t["per_hour"]), fmt(t["false"]),
                 "%d of %d" % (t["seen"], t["failures"]) if t["failures"] else "-", str(t["live_alarms"])))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(r)).rstrip() for r in rows]
    lines.insert(1, "-" * len(lines[0]))
    lines.insert(len(lines) - 1, "-" * len(lines[0]))
    out = "\n".join(lines)
    out += "\n\nThresholds: %s%s" % (result["settings"], (" + " + ", ".join("%s=%s" % kv for kv in result["overrides"].items())) if result["overrides"] else "")
    out += "\nToolhead and gantry left out: %s" % {"on": "yes, in %d of %d pictures (those with the toolhead position)" % (t.get("masked_frames", 0), t.get("frames", 0)),
                                                "off": "no (machine_masks=off)", "no calibration": "no (the camera is not calibrated)"}.get(t.get("masks"), "-")
    out += "\nFalse alarms per hour of print known to be fine: %s" % fmt(t["false_per_hour"])
    if t["failures"]:
        out += "\nFailed prints whose problem was caught: %d of %d%s" % (t["seen"], t["failures"], (", on average after " + minutes(t["average_delay_s"])) if t["average_delay_s"] is not None else "")
    if t["ms_per_check"] is not None:
        out += "\nTime of one check on this computer: %.1f ms" % t["ms_per_check"]
    out += "\n'Live' is what the monitor really did during the print; 'Alarms' is this replay."
    return out


def minutes(seconds):
    if seconds is None:
        return "-"
    return "%d s" % seconds if abs(seconds) < 90 else "%.0f min" % (seconds / 60.0)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measures the AI monitor on the recorded prints (see the top of this file).")
    parser.add_argument("--data", default=default_data_dir(), help="the data folder (default ~/printer_data/klippeye)")
    parser.add_argument("--session", action="append", help="only this recording (repeatable)")
    parser.add_argument("--current", action="store_true", help="the thresholds in use now instead of those of each recording")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="another value for a threshold (repeatable)")
    parser.add_argument("--json", metavar="FILE", help="also write the result as JSON")
    args = parser.parse_args(argv)
    if not monitor_core.HAS_CV2:
        message = "OpenCV is missing (sudo apt install python3-opencv): the monitor cannot be replayed."
        if args.json:
            write_result(args.json, {"ok": False, "error": message})
        print(message, file=sys.stderr)
        return 1
    overrides = {}
    for item in args.set:
        key, sep, value = item.partition("=")
        if not sep:
            parser.error("--set needs KEY=VALUE, e.g. --set sensitivity=45")
        overrides[key.strip()] = parse_value(value)
    try:
        result = measure(args.data, args.session, args.current, overrides)
    except Exception as error:  # the dashboard must get an answer
        if args.json:
            write_result(args.json, {"ok": False, "error": str(error)})
        raise
    if args.json:
        write_result(args.json, result)
    if not result["sessions"]:
        print("No recordings in %s. Turn on Settings → Recordings → Record the prints, print, and run this again." % os.path.join(args.data, "recordings"))
        return 0
    print(table(result))
    return 0


def write_result(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


if __name__ == "__main__":
    sys.exit(main())
