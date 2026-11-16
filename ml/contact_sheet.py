"""Sheets of numbered small pictures, to look at many pictures at once: for example the last picture of each Bambu
timelapse (ml/download.py --bambu), to find the prints that failed and list them in failed.txt.

    python ml/contact_sheet.py ml/data/bambu-timelapses/last-pictures --out ml/work/sheets
writes sheet_000.jpg, sheet_040.jpg... (40 pictures each, numbered) and names.txt (number -> file name, without .jpg).
"""
import argparse
import glob
import os
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder")
    parser.add_argument("--out", default="ml/work/sheets")
    parser.add_argument("--per-sheet", type=int, default=40)
    parser.add_argument("--columns", type=int, default=5)
    args = parser.parse_args(argv)
    import cv2
    import numpy as np

    pictures = sorted(glob.glob(os.path.join(args.folder, "*.jpg")))
    os.makedirs(args.out, exist_ok=True)
    w, h = 320, 180
    for start in range(0, len(pictures), args.per_sheet):
        tiles = []
        for number, path in enumerate(pictures[start:start + args.per_sheet], start):
            image = cv2.imread(path)
            tile = cv2.resize(image, (w, h)) if image is not None else np.zeros((h, w, 3), np.uint8)
            cv2.putText(tile, str(number), (6, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4)
            cv2.putText(tile, str(number), (6, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            tiles.append(tile)
        while len(tiles) % args.columns:
            tiles.append(np.zeros((h, w, 3), np.uint8))
        rows = [np.hstack(tiles[i:i + args.columns]) for i in range(0, len(tiles), args.columns)]
        cv2.imwrite(os.path.join(args.out, "sheet_%03d.jpg" % start), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 82])
    with open(os.path.join(args.out, "names.txt"), "w", encoding="utf-8") as handle:
        handle.write("".join("%d %s\n" % (i, os.path.splitext(os.path.basename(p))[0]) for i, p in enumerate(pictures)))
    print("%d pictures on %d sheets in %s" % (len(pictures), (len(pictures) + args.per_sheet - 1) // args.per_sheet, args.out))
    return 0 if pictures else 1


if __name__ == "__main__":
    sys.exit(main())
