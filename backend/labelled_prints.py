"""
The prints the person has judged, read from KlippEye's data folder: the labelled recordings (recorder.py) and the
answers to «How did the print go?» with their small pictures (print_review.py).

One reader for everything that learns or measures from them: the local model's personal layer (personal_layer.py)
and the training tools (ml/datasets.py, ml/evaluate.py). Standard library only.
"""
import glob
import json
import os

FAILED_AFTER = 60   # seconds after the moment the person chose from which the pictures show the failure
OUTCOMES = ("ok", "failed")


def _json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _json_lines(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _print(kind, folder, document, label, entries, name_format):
    pictures = [(entry.get("n", 0), entry.get("t", 0), os.path.join(folder, name_format % entry.get("n", 0))) for entry in entries]
    return {"id": document.get("id") or os.path.basename(folder), "kind": kind, "outcome": label["outcome"], "failed_at": label.get("failed_at"),
            "started": document.get("started"), "ended": document.get("ended"),
            "pictures": [picture for picture in pictures if os.path.isfile(picture[2])]}


def prints_of(data_dir):
    """-> [{id, kind: "recording" | "review", outcome: "ok" | "failed", failed_at, started, ended,
            pictures: [(number, time, path)]}]: the judged prints that still have pictures, in the order of their folders."""
    found = []
    for session_file in sorted(glob.glob(os.path.join(data_dir, "recordings", "*", "session.json"))):
        folder = os.path.dirname(session_file)
        try:
            session, frames = _json(session_file), _json_lines(os.path.join(folder, "frames.jsonl"))
        except (OSError, ValueError):
            continue
        label = session.get("label") or {}
        if label.get("outcome") in OUTCOMES:
            found.append(_print("recording", folder, session, label, frames, "%06d.jpg"))
    for review_file in sorted(glob.glob(os.path.join(data_dir, "reviews", "*", "review.json"))):
        folder = os.path.dirname(review_file)
        try:
            review = _json(review_file)
        except (OSError, ValueError):
            continue
        answer = review.get("answer") or {}
        if answer.get("outcome") in OUTCOMES:
            found.append(_print("review", folder, review, answer, review.get("thumbs") or [], "%04d.jpg"))
    return [one for one in found if one["pictures"]]


def label_at(one, t):
    """What a picture taken at `t` of the print `one` shows: 0 fine, 1 failed, None not known (the minute after the
    moment the person chose, or a failed print without a moment)."""
    moment = one["failed_at"]
    if one["outcome"] == "ok" or (moment is not None and t < moment):
        return 0
    if moment is not None and t >= moment + FAILED_AFTER:
        return 1
    return None
