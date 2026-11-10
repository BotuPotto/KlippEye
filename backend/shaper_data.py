"""The results of Klipper's resonance measurement (SHAPER_CALIBRATE), for the input shaper graphs (1.80).

SHAPER_CALIBRATE writes, for each axis it measured, a file /tmp/calibration_data_<axis>_<date>.csv: a row per frequency
with the vibrations measured (psd_x, psd_y, psd_z and their sum psd_xyz) and, for each shaper Klipper tried, how much of
the vibration at that frequency it lets through (a column "mzv(53.8)": the shaper and the frequency it fitted).
Here: the list of those files and one file read into lists the dashboard draws, with the vibrations each shaper leaves
(measured as Klipper does: the part of the vibration above a twentieth of the peak that is still there).
"""

import os
import re

FILE_RE = re.compile(r"^calibration_data_([a-z0-9]+)_([0-9_]+)\.csv$", re.IGNORECASE)
SHAPER_COLUMN_RE = re.compile(r"^([a-z0-9_]+)\(([0-9.]+)\)$", re.IGNORECASE)
MAX_FREQ = 200.0  # Klipper looks at the vibrations up to 200 Hz
VIBRATION_REDUCTION = 20.0  # what Klipper counts as a vibration: above a twentieth of the peak
MAX_ROWS = 1200
MAX_FILES = 40


class ShaperError(Exception):
    pass


def default_dirs():
    """Where the files are: /tmp (Klipper's own place) unless KLIPPEYE_SHAPER_DIRS names others (the tests)."""
    named = os.environ.get("KLIPPEYE_SHAPER_DIRS", "")
    return [d for d in named.split(os.pathsep) if d] if named else ["/tmp"]


def list_files(dirs=None):
    """The measurement files, newest first: [{name, axis, modified, size}]."""
    out = []
    seen = set()
    for folder in dirs or default_dirs():
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            match = FILE_RE.match(name)
            if not match or name in seen:
                continue
            full = os.path.join(folder, name)
            try:
                stat = os.stat(full)
            except OSError:
                continue
            if not os.path.isfile(full):
                continue
            seen.add(name)
            out.append({"name": name, "axis": match.group(1).lower(), "modified": int(stat.st_mtime), "size": stat.st_size})
    out.sort(key=lambda one: one["modified"], reverse=True)
    return out[:MAX_FILES]


def find_file(name, dirs=None):
    """The full path of a file of the list, or ShaperError: only a name of the list (no folder, no other file)."""
    if not name or not FILE_RE.match(name) or "/" in name or "\\" in name:
        raise ShaperError("invalid file name")
    for folder in dirs or default_dirs():
        full = os.path.join(folder, name)
        if os.path.isfile(full):
            return full
    raise ShaperError("file not found")


def _number(text):
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value == value and value not in (float("inf"), float("-inf")) else None


def remaining_vibrations(psd, response):
    """The part of the vibrations a shaper leaves (0..1), as Klipper measures it."""
    peak = max(psd) if psd else 0.0
    if peak <= 0:
        return 0.0
    threshold = peak / VIBRATION_REDUCTION
    left = sum(max(r * p - threshold, 0.0) for p, r in zip(psd, response))
    total = sum(max(p - threshold, 0.0) for p in psd)
    return left / total if total > 0 else 0.0


def parse(text):
    """A measurement file → {freq, psd: {x,y,z,sum}, shapers: [{name, freq, response, vibrations}], peak}."""
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if not lines:
        raise ShaperError("empty file")
    header = [cell.strip() for cell in lines[0].split(",")]
    if not header or header[0].lower() != "freq":
        raise ShaperError("not a resonance measurement")
    columns = {name.lower(): index for index, name in enumerate(header)}
    psd_columns = {"x": "psd_x", "y": "psd_y", "z": "psd_z", "sum": "psd_xyz"}
    shapers = []
    for index, name in enumerate(header):
        match = SHAPER_COLUMN_RE.match(name)
        if match:
            shapers.append({"name": match.group(1).lower(), "freq": float(match.group(2)), "index": index, "response": []})
    freq = []
    psd = {key: [] for key in psd_columns if psd_columns[key] in columns}
    for line in lines[1:]:
        cells = line.split(",")
        if len(cells) < len(header):
            continue
        value = _number(cells[0])
        if value is None or value > MAX_FREQ:
            continue
        freq.append(round(value, 2))
        for key in psd:
            psd[key].append(_number(cells[columns[psd_columns[key]]]) or 0.0)
        for shaper in shapers:
            shaper["response"].append(_number(cells[shaper["index"]]) or 0.0)
        if len(freq) >= MAX_ROWS:
            break
    if not freq:
        raise ShaperError("no data in the file")
    total = psd.get("sum") or [sum(values) for values in zip(*[psd[k] for k in ("x", "y", "z") if k in psd])] or [0.0] * len(freq)
    for shaper in shapers:
        shaper["vibrations"] = round(remaining_vibrations(total, shaper["response"]) * 100, 1)
        del shaper["index"]
    peak_at = max(range(len(total)), key=lambda i: total[i]) if total else 0
    return {"freq": freq, "psd": psd, "shapers": shapers, "peak": {"freq": freq[peak_at], "value": total[peak_at] if total else 0}}


def read(name, dirs=None):
    full = find_file(name, dirs)
    if os.path.getsize(full) > 4 * 1024 * 1024:
        raise ShaperError("file too large")
    with open(full, "r", encoding="utf-8", errors="ignore") as handle:
        data = parse(handle.read())
    match = FILE_RE.match(name)
    data.update({"name": name, "axis": match.group(1).lower(), "modified": int(os.path.getmtime(full))})
    return data
