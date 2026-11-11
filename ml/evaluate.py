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
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
import local_model  # noqa: E402

THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
FAILED_AFTER = 60


def prints_of(data):
    """-> [{id, kind: recording | review, outcome, failed_at, started, ended, pictures: [(time, path)]}]"""
    out = []
    for session_file in sorted(glob.glob(os.path.join(data, "recordings", "*", "session.json"))):
        folder = os.path.dirname(session_file)
        try:
            session = json.load(open(session_file, encoding="utf-8"))
            frames = [json.loads(line) for line in open(os.path.join(folder, "frames.jsonl"), encoding="utf-8") if line.strip()]
        except (OSError, ValueError):
            continue
        label = session.get("label") or {}
        if label.get("outcome") not in ("ok", "failed"):
            continue
        pictures = [(f.get("t", 0), os.path.join(folder, "%06d.jpg" % f.get("n", 0))) for f in frames]
        out.append({"id": session.get("id", os.path.basename(folder)), "kind": "recording", "outcome": label["outcome"], "failed_at": label.get("failed_at"),
                    "started": session.get("started"), "ended": session.get("ended"), "pictures": [p for p in pictures if os.path.isfile(p[1])]})
    for review_file in sorted(glob.glob(os.path.join(data, "reviews", "*", "review.json"))):
        folder = os.path.dirname(review_file)
        try:
            review = json.load(open(review_file, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        answer = review.get("answer") or {}
        if answer.get("outcome") not in ("ok", "failed"):
            continue
        pictures = [(t.get("t", 0), os.path.join(folder, "%04d.jpg" % t.get("n", 0))) for t in review.get("thumbs") or []]
        out.append({"id": review.get("id", os.path.basename(folder)), "kind": "review", "outcome": answer["outcome"], "failed_at": answer.get("failed_at"),
                    "started": review.get("started"), "ended": review.get("ended"), "pictures": [p for p in pictures if os.path.isfile(p[1])]})
    return [p for p in out if p["pictures"]]


def alarms(scored, threshold, consecutive, cooldown):
    """The times of the alarms of one print: scored = [(time, score)]."""
    out, run, quiet_until = [], 0, None
    for t, score in scored:
        run = run + 1 if score >= threshold else 0
        if run >= consecutive and (quiet_until is None or t >= quiet_until):
            out.append(t)
            quiet_until, run = t + cooldown, 0
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, help="the model's folder (model.onnx + model.json)")
    parser.add_argument("--data", required=True, help="KlippEye's data folder (recordings/, reviews/)")
    parser.add_argument("--every", type=int, default=1, help="score one picture in N of the recordings (faster)")
    parser.add_argument("--consecutive", type=int, default=1)
    parser.add_argument("--cooldown", type=float, default=120)
    parser.add_argument("--json", help="write the details here")
    args = parser.parse_args(argv)
    import cv2
    import numpy as np
    model = local_model.load(args.model, cv2, np)
    if model is None:
        print("No model in %s (model.onnx and model.json are needed)" % args.model)
        return 1
    prints = prints_of(args.data)
    if not prints:
        print("No labelled print in %s: label some (Recordings, or «How did the print go?») and copy the folder again." % args.data)
        return 1
    print("model %s (threshold %.2f), %d labelled prints" % (model.version, model.threshold, len(prints)))
    results = []
    for one in prints:
        pictures = one["pictures"][:: args.every] if one["kind"] == "recording" else one["pictures"]
        scored = []
        for t, path in pictures:
            image = cv2.imread(path)
            if image is not None:
                scored.append((t, model.predict(image)[0]))
        one = dict(one, scored=scored)
        one.pop("pictures")
        results.append(one)
        print("  %-40s %-6s %4d pictures, highest score %.2f" % (one["id"][:40], one["outcome"], len(scored), max([s for _, s in scored] or [0])))
    thresholds = sorted(set(THRESHOLDS + (round(model.threshold, 2),)))
    print("\nthreshold | false alarms/hour on fine prints | failures caught | median delay")
    table = []
    for threshold in thresholds:
        fine_hours, false_alarms, caught, failed, delays = 0.0, 0, 0, 0, []
        for one in results:
            times = alarms(one["scored"], threshold, args.consecutive, args.cooldown)
            if not one["scored"]:
                continue
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
        per_hour = false_alarms / fine_hours if fine_hours > 0 else 0.0
        delays.sort()
        median = delays[len(delays) // 2] if delays else None
        mark = " ← the model's" if abs(threshold - model.threshold) < 1e-6 else ""
        print("   %.2f   | %6.2f (%d in %.1f h)               | %d of %d        | %s%s" % (
            threshold, per_hour, false_alarms, fine_hours, caught, failed, ("%.0f s" % median) if median is not None else "-", mark))
        table.append({"threshold": threshold, "false_alarms_per_hour": round(per_hour, 3), "false_alarms": false_alarms, "fine_hours": round(fine_hours, 2),
                      "caught": caught, "failed": failed, "median_delay_s": median})
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump({"model": model.info, "table": table, "prints": results}, handle)
        print("details in %s" % args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
