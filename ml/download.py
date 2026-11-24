"""
Downloads every public dataset listed in ml/sources.json from Roboflow Universe (the latest version of each, YOLO format
for detection and segmentation, folders for classification) into ml/data/, and writes ml/data/CREDITS.md with each
dataset's licence and address (most are CC BY 4.0: they may be used, naming the author).

It needs a free Roboflow account: roboflow.com → sign up → Settings → API Keys → «Private API Key». Then
    pip install roboflow
    ROBOFLOW_API_KEY=... python ml/download.py            (or --key ...)
A dataset that cannot be downloaded (removed, private) is skipped and said; the others go on. Run it again to fetch only
the missing ones.

Collections whose licence does not let the trained model be shared with everyone (ShareAlike, NonCommercial,
NoDerivatives, private) are deleted again and said (--any-licence keeps them, for a model you do not share); one whose
licence is not written in the download is kept and marked in CREDITS.md, to check on its page.

1.130: --bambu also downloads the Bambu Timelapse Dataset (Hugging Face, CC BY 4.0, ~3 GB of timelapses of real prints
seen from the printer's own camera, no key needed: pip install huggingface_hub) and takes a few pictures from each
timelapse: pictures of prints going well, from many printers and filaments, which the public collections lack. The
timelapses have no label: a print that failed is recognised by its last picture (the current model scores it; above
--bambu-doubt it is left out) and you can leave out more by name in ml/data/bambu-timelapses/failed.txt (one file name
per line; ml/data/bambu-timelapses/last-pictures/ has the last picture of each, to look at).
"""
import argparse
import glob
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# the licences that let the trained model be shared with everyone (attribution is kept in CREDITS.md)
OPEN_LICENCE = re.compile(r"cc\s*by\s*4\.0|cc-by-4\.0|attribution 4\.0|cc0|public\s*domain|\bmit\b|apache", re.I)
CLOSED_LICENCE = re.compile(r"\bsa\b|share.?alike|\bnc\b|non.?commercial|\bnd\b|no.?deriv|private|unknown|proprietary", re.I)
BAMBU_REPO = "v2thegreat/bambu-timelapse-dataset"
BAMBU_FOLDER = "bambu-timelapses"
BAMBU_FRAMES = 8          # pictures taken from each timelapse, spread from BAMBU_FROM to BAMBU_TO of its length
BAMBU_FROM, BAMBU_TO = 0.12, 0.85   # not the very start (an empty bed) nor the end (where a failure would be clearest)
BAMBU_DOUBT = 0.5         # a timelapse whose last picture the current model scores this high is left out (may have failed)


def licence_is_open(text):
    """1.150.0: an allow-list. A licence that is not found, or that is not known to let the model be shared, is not open."""
    return bool(OPEN_LICENCE.search(text or "")) and not CLOSED_LICENCE.search(text or "")


def latest_version(project):
    numbers = []
    for version in project.versions():
        text = str(getattr(version, "version", "") or getattr(version, "id", ""))
        tail = text.rstrip("/").split("/")[-1]
        if tail.isdigit():
            numbers.append(int(tail))
    return max(numbers) if numbers else None


def licence_of(folder):
    for name in ("README.roboflow.txt", "README.dataset.txt"):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if "license" in line.lower() or "licence" in line.lower():
                        return line.strip().split(":", 1)[-1].strip() or line.strip()
    return "see the dataset's page"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--key", default=os.environ.get("ROBOFLOW_API_KEY", ""))
    parser.add_argument("--sources", default=os.path.join(HERE, "sources.json"))
    parser.add_argument("--out", default=os.path.join(HERE, "data"))
    parser.add_argument("--any-licence", action="store_true", help="keep collections whose licence does not allow sharing the model")
    parser.add_argument("--bambu", action="store_true", help="also the Bambu Timelapse Dataset (Hugging Face, CC BY 4.0, ~3 GB)")
    parser.add_argument("--bambu-only", action="store_true", help="only the Bambu Timelapse Dataset (no Roboflow key needed)")
    parser.add_argument("--bambu-doubt", type=float, default=BAMBU_DOUBT)
    parser.add_argument("--model", default=os.path.join(HERE, "..", "models", "base"), help="the model that scores the last pictures")
    args = parser.parse_args(argv)
    if args.bambu_only:
        return 0 if bambu(args.out, args.model, args.bambu_doubt) else 1
    if not args.key:
        print("A Roboflow key is needed: --key ... or ROBOFLOW_API_KEY (roboflow.com → Settings → API Keys, free).")
        return 1
    try:
        from roboflow import Roboflow
    except ImportError:
        print("pip install roboflow")
        return 1
    with open(args.sources, encoding="utf-8") as handle:
        sources = json.load(handle)["roboflow"]
    os.makedirs(args.out, exist_ok=True)
    rf = Roboflow(api_key=args.key)
    credits, done, skipped = [], 0, []
    for slug in sources:
        workspace, _, name = slug.partition("/")
        folder = os.path.join(args.out, workspace + "__" + name)
        try:
            project = rf.workspace(workspace).project(name)
            kind = str(getattr(project, "type", "") or "object-detection")
            number = latest_version(project)
            if number is None:
                raise RuntimeError("no version to download")
            multi = "multi" in kind.lower()
            fmt = "multiclass" if multi else "folder" if "classification" in kind else "yolov8"
            if not os.path.isfile(os.path.join(folder, "klippeye-source.json")):   # 1.150.0: a folder cut short is not «here»
                print("downloading %s (version %d, %s)…" % (slug, number, kind))
                project.version(number).download(fmt, location=folder, overwrite=True)
            else:
                print("already here: %s" % slug)
            with open(os.path.join(folder, "klippeye-source.json"), "w", encoding="utf-8") as handle:
                json.dump({"slug": slug, "version": number, "type": kind, "format": fmt}, handle)
            licence = licence_of(folder)
            if not licence_is_open(licence):
                if not args.any_licence:
                    shutil.rmtree(folder, ignore_errors=True)
                    raise RuntimeError("its licence (%s) is not known to let the model be shared: left out (--any-licence keeps it)" % (licence or "not found"))
                licence += " (check it on the page before sharing the model)"
            credits.append("- [%s](https://universe.roboflow.com/%s) v%d (%s): %s" % (slug, slug, number, kind, licence))
            done += 1
        except Exception as error:  # noqa: BLE001 - one dataset less, the others go on
            print("SKIPPED %s: %s" % (slug, str(error)[:200]))
            skipped.append(slug)
    if args.bambu:
        line = bambu(args.out, args.model, args.bambu_doubt)
        if line:
            credits.append(line)
            done += 1
    with open(os.path.join(args.out, "CREDITS.md"), "w", encoding="utf-8") as handle:
        handle.write("# The datasets the local model was trained on\n\n" + "\n".join(credits) + "\n")
    print("\n%d datasets in %s (%d skipped%s)" % (done, args.out, len(skipped), (": " + ", ".join(skipped)) if skipped else ""))
    return 0 if done else 1


def frames_of(video, count, start, end, cv2):
    """`count` pictures spread between `start` and `end` (shares of its length) of a video, and its last one."""
    capture = cv2.VideoCapture(video)
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total < 2:   # some files do not say how long they are: read them through
        pictures = []
        while True:
            ok, picture = capture.read()
            if not ok:
                break
            pictures.append(picture)
        capture.release()
        if not pictures:
            return [], None
        total = len(pictures)
        picks = sorted({int(total * (start + (end - start) * i / max(1, count - 1))) for i in range(count)})
        return [pictures[min(i, total - 1)] for i in picks], pictures[-1]
    out = []
    for i in range(count):
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(total * (start + (end - start) * i / max(1, count - 1))))
        ok, picture = capture.read()
        if ok:
            out.append(picture)
    capture.set(cv2.CAP_PROP_POS_FRAMES, total - 1)
    ok, last = capture.read()
    capture.release()
    return out, (last if ok else (out[-1] if out else None))


def bambu(out, model_dir, doubt, videos=None):
    """The Bambu Timelapse Dataset as pictures of prints going well: <out>/bambu-timelapses/frames/<video>/*.jpg.
    videos: the timelapse files (tests); by default downloaded from Hugging Face. -> its CREDITS line, or None."""
    import cv2
    import numpy as np

    folder = os.path.join(out, BAMBU_FOLDER)
    if videos is None:
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            print("pip install huggingface_hub (for --bambu)")
            return None
        print("downloading the Bambu Timelapse Dataset's timelapses (~3 GB)…")
        snapshot_download(BAMBU_REPO, repo_type="dataset", local_dir=os.path.join(folder, "source"),
                          allow_patterns=["train/timelapses/**", "originals/timelapses/**", "metadata/*", "README.md"])
        # train/timelapses/<contributor>/*.mp4 (the card speaks of originals/timelapses: both are looked at)
        videos = sorted(glob.glob(os.path.join(folder, "source", "*", "timelapses", "**", "*.*"), recursive=True))
        videos = [v for v in videos if v.lower().endswith((".mp4", ".avi", ".mkv", ".mov"))]
    sys.path.insert(0, os.path.join(HERE, "..", "backend"))
    import local_model

    judge = local_model.load(model_dir, cv2, np) if model_dir and os.path.isdir(model_dir) else None
    frames_dir, last_dir = os.path.join(folder, "frames"), os.path.join(folder, "last-pictures")
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(last_dir, exist_ok=True)
    doubtful, kept = [], 0
    for video in videos:
        name = re.sub(r"[^A-Za-z0-9_.-]+", "_", os.path.relpath(video, os.path.dirname(os.path.dirname(video))))[:120]
        target = os.path.join(frames_dir, name)
        if os.path.isdir(target) and os.listdir(target):
            kept += 1
            continue
        pictures, last = frames_of(video, BAMBU_FRAMES, BAMBU_FROM, BAMBU_TO, cv2)
        if not pictures or last is None:
            continue
        cv2.imwrite(os.path.join(last_dir, name + ".jpg"), last)
        if judge is not None and judge.predict(last)[0] >= doubt:
            doubtful.append(name)   # the end of this print looks like a failure: none of its pictures is used
            continue
        os.makedirs(target, exist_ok=True)
        for i, picture in enumerate(pictures):
            cv2.imwrite(os.path.join(target, "%02d.jpg" % i), picture, [cv2.IMWRITE_JPEG_QUALITY, 90])
        kept += 1
    with open(os.path.join(folder, "doubtful.txt"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(doubtful) + ("\n" if doubtful else ""))
    failed = os.path.join(folder, "failed.txt")
    if not os.path.isfile(failed):
        with open(failed, "w", encoding="utf-8") as handle:
            handle.write("# timelapses that failed, one name per line (as in last-pictures/, without .jpg): left out\n")
    with open(os.path.join(folder, "klippeye-source.json"), "w", encoding="utf-8") as handle:
        json.dump({"slug": BAMBU_REPO, "type": "timelapse-frames", "format": "frames-fine", "licence": "CC BY 4.0"}, handle)
    print("Bambu timelapses: %d kept as prints going well, %d left out (their end looks like a failure: doubtful.txt)" % (kept, len(doubtful)))
    return ("- [Bambu Timelapse Dataset](https://huggingface.co/datasets/%s) (timelapses, %d prints): CC BY 4.0" % (BAMBU_REPO, kept)) if kept else None


if __name__ == "__main__":
    sys.exit(main())
