"""
Measures a local model on KlippEye's labelled prints, as the Raspberry would run it (OpenCV's DNN module), before it
is used: for each print the person said went fine, how many false alarms an hour; for each failed one, whether it was
caught and how long after the moment the person chose.

    python ml/evaluate.py --model ml/out/model --data ~/klippeye-data
(--data: KlippEye's data folder copied from the Raspberry, with recordings/ and reviews/; on the Raspberry itself:
~/printer_data/klippeye or the folder KLIPPEYE_DATA says.)

An alarm is counted when the score stays over the threshold for --consecutive pictures in a row; after an alarm the
next one is counted only --cooldown seconds later (as the monitor rests between two AI calls).
Writes a table for several thresholds and, with --json, the details.

1.132: the last row, «monitor», counts the times the monitor's local model asks by itself, with its own rule: one look
every --every-s seconds (local_every), two «sure» looks in a row or three «in doubt» in a row (the model's levels), and
in the first --warmup seconds of the print (LOCAL_WARMUP_S) only three «sure» looks. The recordings start when the
monitor starts checking, so their first picture is the print's real start.

1.130: --box x,y,w,h (fractions of the picture) judges only that part of each picture, as the monitor judges the bed of a
calibrated camera instead of the whole picture (the box is "bed_view" in http://RASPBERRY:8085/api/local_model).
Without it, the whole picture, as a monitor without calibration.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
import labelled_prints  # noqa: E402
from labelled_prints import same_print_once  # noqa: E402  (1.150.0: moved there, datasets.py counts a print the same way)
import local_model  # noqa: E402

THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
FAILED_AFTER = labelled_prints.FAILED_AFTER


def alarms(scored, threshold, consecutive, cooldown):
    """The times of the alarms of one print: scored = [(time, score)]."""
    out, run, quiet_until = [], 0, None
    for t, score in scored:
        run = run + 1 if score >= threshold else 0
        if run >= consecutive and (quiet_until is None or t >= quiet_until):
            out.append(t)
            quiet_until, run = t + cooldown, 0
    return out


def monitor_asks(scored, doubt, sure, every=15.0, warmup=300.0, cooldown=120.0):
    """The times the monitor's local model asks the online AI by itself (klippeye_backend _local_look): scored =
    [(time, score 0..1)], doubt and sure in %."""
    out, sure_run, doubt_run, quiet_until, next_look = [], 0, 0, None, None
    start = scored[0][0] if scored else 0
    for t, score in scored:
        if next_look is not None and t < next_look:
            continue
        next_look = t + every
        sure_run = sure_run + 1 if score * 100 >= sure else 0
        doubt_run = doubt_run + 1 if score * 100 >= doubt else 0
        if quiet_until is not None and t < quiet_until:
            continue
        early = t - start < warmup
        if sure_run >= (3 if early else 2) or (doubt_run >= 3 and not early):
            out.append(t)
            quiet_until, sure_run, doubt_run = t + cooldown, 0, 0
    return out


def whole_asks(scored, triggers, doubt, sure, fine_until, every=15.0, warmup=300.0, cooldown=120.0, fine_memory=600.0):
    """1.135: the monitor's asks with motion detection too: the local model's own asks (monitor_asks) plus the motion
    triggers recorded live that it lets through (its latest look at least «in doubt», local_filter); one rest between
    asks, longer after an ask while the print is still fine (the online AI, taken as right, calls the scene fine and the
    false-alarm memory keeps it fine_memory s, 1.134.3). fine_until = the moment the print failed, None if it never did.
    shortcut: the triggers come from the live run (its thresholds, its boost from the old model's doubt), so a new model
    that would have lowered the motion thresholds less is not seen; good enough to compare models, not to tune motion."""
    moved = []
    for t in triggers:
        last = [score for when, score in scored if when <= t]
        if last and last[-1] * 100 >= doubt:
            moved.append(t)
    out, quiet_until = [], None
    for t in sorted(monitor_asks(scored, doubt, sure, every, warmup, cooldown) + moved):
        if quiet_until is not None and t < quiet_until:
            continue
        out.append(t)
        fine = fine_until is None or t < fine_until
        quiet_until = t + (fine_memory if fine else cooldown)
    return out


def motion_triggers(one):
    """1.135: the times the motion detection triggered in a recording (frames.jsonl "trig"); none for an answer."""
    if one["kind"] != "recording" or not one["pictures"]:
        return []
    rows = labelled_prints._json_lines(os.path.join(os.path.dirname(one["pictures"][0][2]), "frames.jsonl"))
    return [row["t"] for row in rows if row.get("trig")]


def levels_of(info, threshold):
    """The model's «in doubt» and «sure» levels in % (model.json "levels", else as ml/train.py chooses them)."""
    levels = info.get("levels") or {}
    if levels.get("doubt") and levels.get("sure"):
        return float(levels["doubt"]), float(levels["sure"])
    sure = round(threshold * 100)
    return float(5 * (sure // 5) - 10), float(sure)


def count(results, times_of):
    """-> (false alarms an hour on fine prints, false alarms, fine hours, caught, failed, median delay or None)."""
    fine_hours, false_alarms, caught, failed, delays = 0.0, 0, 0, 0, []
    for one in results:
        if not one["scored"]:
            continue
        times = times_of(one["scored"])
        span = (one["scored"][-1][0] - one["scored"][0][0]) / 3600.0
        if one["outcome"] == "ok":
            fine_hours += span
            false_alarms += len(times)
        else:
            failed += 1
            moment = one["failed_at"]
            after = [t for t in times if moment is None or t >= moment - 30]
            before = [t for t in times if moment is not None and t < moment - 30]
            false_alarms += len(before)
            fine_hours += ((moment - one["scored"][0][0]) / 3600.0) if moment else 0.0
            if after:
                caught += 1
                if moment is not None:
                    delays.append(max(0.0, after[0] - moment))
    delays.sort()
    per_hour = false_alarms / fine_hours if fine_hours > 0 else 0.0
    return per_hour, false_alarms, fine_hours, caught, failed, (delays[len(delays) // 2] if delays else None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, help="the model's folder (model.onnx + model.json)")
    parser.add_argument("--data", required=True, help="KlippEye's data folder (recordings/, reviews/)")
    parser.add_argument("--every", type=int, default=1, help="score one picture in N of the recordings (faster)")
    parser.add_argument("--consecutive", type=int, default=1)
    parser.add_argument("--cooldown", type=float, default=120)
    parser.add_argument("--every-s", type=float, default=15, help="«monitor» row: how often the local model looks by itself (local_every)")
    parser.add_argument("--warmup", type=float, default=300, help="«monitor» row: the first seconds of a print, with a stricter rule")
    parser.add_argument("--json", help="write the details here")
    parser.add_argument("--trained", action="store_true", help="these prints were in the training: the numbers are not an independent measure")
    parser.add_argument("--box", default="", help="x,y,w,h in fractions: judge only that part of each picture (the bed)")
    args = parser.parse_args(argv)
    box = None
    if args.box:
        try:
            box = [float(v) for v in args.box.split(",")]
            assert len(box) == 4 and all(0 <= v <= 1 for v in box) and box[2] > 0 and box[3] > 0
        except (ValueError, AssertionError):
            print("--box: four numbers from 0 to 1, x,y,w,h (for example 0.15,0.36,0.70,0.61)")
            return 1
    import cv2
    import numpy as np
    model = local_model.load(args.model, cv2, np)
    if model is None:
        print("No model in %s (model.onnx and model.json are needed)" % args.model)
        return 1
    prints = same_print_once(labelled_prints.prints_of(args.data))
    if not prints:
        print("No labelled print in %s: label some (Recordings, or «How did the print go?») and copy the folder again." % args.data)
        return 1
    print("model %s (threshold %.2f), %d labelled prints" % (model.version, model.threshold, len(prints)))
    if args.trained:   # 1.150.0
        print("WARNING: the model learned from these prints, so these numbers are too good. Measure on prints it has not seen.")
    results = []
    for one in prints:
        pictures = one["pictures"][:: args.every] if one["kind"] == "recording" else one["pictures"]
        scored = []
        for _, t, path in pictures:
            image = cv2.imread(path)
            if image is not None:
                if box:
                    h, w = image.shape[:2]
                    image = image[int(box[1] * h):int((box[1] + box[3]) * h), int(box[0] * w):int((box[0] + box[2]) * w)]
                scored.append((t, model.predict(image)[0]))
        one = dict(one, scored=scored, triggers=motion_triggers(one))
        one.pop("pictures")
        results.append(one)
        print("  %-40s %-6s %4d pictures, highest score %.2f" % (one["id"][:40], one["outcome"], len(scored), max([s for _, s in scored] or [0])))
    thresholds = sorted(set(THRESHOLDS + (round(model.threshold, 2),)))
    print("\nthreshold | false alarms/hour on fine prints | failures caught | median delay")
    table = []
    for threshold in thresholds:
        per_hour, false_alarms, fine_hours, caught, failed, median = count(
            results, lambda scored, threshold=threshold: alarms(scored, threshold, args.consecutive, args.cooldown))
        mark = " ← the model's" if abs(threshold - model.threshold) < 1e-6 else ""
        print("   %.2f   | %6.2f (%d in %.1f h)               | %d of %d        | %s%s" % (
            threshold, per_hour, false_alarms, fine_hours, caught, failed, ("%.0f s" % median) if median is not None else "-", mark))
        table.append({"threshold": threshold, "false_alarms_per_hour": round(per_hour, 3), "false_alarms": false_alarms, "fine_hours": round(fine_hours, 2),
                      "caught": caught, "failed": failed, "median_delay_s": median})
    doubt, sure = levels_of(model.info, model.threshold)
    by_scored = {id(one["scored"]): dict(one, fine_until=None if one["outcome"] == "ok" else (one["failed_at"] or 0) - 30)
                 for one in results}
    per_hour, false_alarms, fine_hours, caught, failed, median = count(
        results, lambda scored: monitor_asks(scored, doubt, sure, args.every_s, args.warmup, args.cooldown))
    print(" monitor  | %6.2f (%d in %.1f h)               | %d of %d        | %s  (in doubt %.0f%%, sure %.0f%%, a look every %.0f s, warm-up %.0f s)" % (
        per_hour, false_alarms, fine_hours, caught, failed, ("%.0f s" % median) if median is not None else "-", doubt, sure, args.every_s, args.warmup))
    table.append({"monitor": True, "doubt": doubt, "sure": sure, "every_s": args.every_s, "warmup_s": args.warmup,
                  "false_alarms_per_hour": round(per_hour, 3), "false_alarms": false_alarms, "fine_hours": round(fine_hours, 2),
                  "caught": caught, "failed": failed, "median_delay_s": median})
    per_hour, false_alarms, fine_hours, caught, failed, median = count(results, lambda scored: whole_asks(
        scored, by_scored[id(scored)]["triggers"], doubt, sure, by_scored[id(scored)]["fine_until"], args.every_s, args.warmup, args.cooldown))
    print(" + motion |  %6.2f (%d in %.1f h)               | %d of %d        | %s  (and the motion triggers recorded live, an online «fine» kept 10 min)" % (
        per_hour, false_alarms, fine_hours, caught, failed, ("%.0f s" % median) if median is not None else "-"))
    table.append({"monitor_and_motion": True, "false_alarms_per_hour": round(per_hour, 3), "false_alarms": false_alarms,
                  "fine_hours": round(fine_hours, 2), "caught": caught, "failed": failed, "median_delay_s": median})
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump({"model": model.info, "table": table, "prints": results, "independent": not args.trained}, handle)
        print("details in %s" % args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
