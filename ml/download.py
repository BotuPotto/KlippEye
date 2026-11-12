"""
Downloads every public dataset listed in ml/sources.json from Roboflow Universe (the latest version of each, YOLO format
for detection and segmentation, folders for classification) into ml/data/, and writes ml/data/CREDITS.md with each
dataset's licence and address (most are CC BY 4.0: they may be used, naming the author).

It needs a free Roboflow account: roboflow.com → sign up → Settings → API Keys → «Private API Key». Then
    pip install roboflow
    ROBOFLOW_API_KEY=... python ml/download.py            (or --key ...)
A dataset that cannot be downloaded (removed, private) is skipped and said; the others go on. Run it again to fetch only
the missing ones.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


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
            for line in open(path, encoding="utf-8", errors="replace"):
                if "license" in line.lower() or "licence" in line.lower():
                    return line.strip().split(":", 1)[-1].strip() or line.strip()
    return "see the dataset's page"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--key", default=os.environ.get("ROBOFLOW_API_KEY", ""))
    parser.add_argument("--sources", default=os.path.join(HERE, "sources.json"))
    parser.add_argument("--out", default=os.path.join(HERE, "data"))
    args = parser.parse_args(argv)
    if not args.key:
        print("A Roboflow key is needed: --key ... or ROBOFLOW_API_KEY (roboflow.com → Settings → API Keys, free).")
        return 1
    try:
        from roboflow import Roboflow
    except ImportError:
        print("pip install roboflow")
        return 1
    sources = json.load(open(args.sources, encoding="utf-8"))["roboflow"]
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
            fmt = "folder" if "classification" in kind else "yolov8"
            if not os.path.isdir(folder) or not os.listdir(folder):
                print("downloading %s (version %d, %s)…" % (slug, number, kind))
                project.version(number).download(fmt, location=folder, overwrite=True)
            else:
                print("already here: %s" % slug)
            json.dump({"slug": slug, "version": number, "type": kind, "format": fmt}, open(os.path.join(folder, "klippeye-source.json"), "w"))
            credits.append("- [%s](https://universe.roboflow.com/%s) v%d (%s): %s" % (slug, slug, number, kind, licence_of(folder)))
            done += 1
        except Exception as error:  # noqa: BLE001 - one dataset less, the others go on
            print("SKIPPED %s: %s" % (slug, str(error)[:200]))
            skipped.append(slug)
    with open(os.path.join(args.out, "CREDITS.md"), "w", encoding="utf-8") as handle:
        handle.write("# The datasets the local model was trained on\n\n" + "\n".join(credits) + "\n")
    print("\n%d datasets in %s (%d skipped%s)" % (done, args.out, len(skipped), (": " + ", ".join(skipped)) if skipped else ""))
    return 0 if done else 1


if __name__ == "__main__":
    sys.exit(main())
