"""The results of Klipper's resonance measurement (SHAPER_CALIBRATE), for the input shaper graphs (1.80).

SHAPER_CALIBRATE writes, for each axis it measured, a file /tmp/calibration_data_<axis>_<date>.csv: a row per frequency
with the vibrations measured (psd_x, psd_y, psd_z and their sum psd_xyz) and, for each shaper Klipper tried, how much of
the vibration at that frequency it lets through (a column "mzv(53.8)": the shaper and the frequency it fitted).
Here: the list of those files and one file read into lists the dashboard draws, with the vibrations each shaper leaves
(measured as Klipper does: the part of the vibration above a twentieth of the peak that is still there).
"""

import math
import os
import re

FILE_RE = re.compile(r"^calibration_data_([a-z0-9]+)_([0-9_]+)\.csv$", re.IGNORECASE)
SHAPER_COLUMN_RE = re.compile(r"^([a-z0-9_]+)\(([0-9.]+)\)$", re.IGNORECASE)
MAX_FREQ = 200.0  # Klipper looks at the vibrations up to 200 Hz
VIBRATION_REDUCTION = 20.0  # what Klipper counts as a vibration: above a twentieth of the peak
MAX_ROWS = 1200
MAX_FILES = 40


PEAKS_DETECTION = 0.05   # a peak counts above this part of the highest one (the «relax» band below it)
PEAKS_EFFECT = 0.12      # above this part it shakes the prints (the «warning» band below it)
TARGET_SMOOTHING = 0.12  # Klipper's choice for the suggested max acceleration
SHAPER_ORDER = ("zv", "mzv", "zvd", "ei", "2hump_ei", "3hump_ei")


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


# ---------------------------------------------------------------------------------------------------------------------
# 1.89: smoothing, suggested max acceleration, the recommended shapers, the damping ratio and the peaks — as Klipper
# computes them (klippy/extras/shaper_defs.py and shaper_calibrate.py), from the shaper and frequency in the file.
# ---------------------------------------------------------------------------------------------------------------------
def shaper_pulses(name, freq, damping=0.1):
    """The shaper's impulses (amplitudes, times), or None for an unknown shaper."""
    if freq <= 0:
        return None
    v_tol = 1.0 / 20
    df = math.sqrt(1.0 - damping ** 2)
    k = math.exp(-damping * math.pi / df)
    t_d = 1.0 / (freq * df)
    if name == "zv":
        return [1.0, k], [0.0, 0.5 * t_d]
    if name == "zvd":
        return [1.0, 2.0 * k, k * k], [0.0, 0.5 * t_d, t_d]
    if name == "mzv":
        k = math.exp(-0.75 * damping * math.pi / df)
        a1 = 1.0 - 1.0 / math.sqrt(2.0)
        return [a1, (math.sqrt(2.0) - 1.0) * k, a1 * k * k], [0.0, 0.375 * t_d, 0.75 * t_d]
    if name == "ei":
        a1 = 0.25 * (1.0 + v_tol)
        return [a1, 0.5 * (1.0 - v_tol) * k, a1 * k * k], [0.0, 0.5 * t_d, t_d]
    if name == "2hump_ei":
        v2 = v_tol ** 2
        x = (v2 * (math.sqrt(1.0 - v2) + 1.0)) ** (1.0 / 3)
        a1 = (3.0 * x * x + 2.0 * x + 3.0 * v2) / (16.0 * x)
        a2 = (0.5 - a1) * k
        return [a1, a2, a2 * k, a1 * k ** 3], [0.0, 0.5 * t_d, t_d, 1.5 * t_d]
    if name == "3hump_ei":
        k2 = k * k
        a1 = 0.0625 * (1.0 + 3.0 * v_tol + 2.0 * math.sqrt(2.0 * (v_tol + 1.0) * v_tol))
        a2 = 0.25 * (1.0 - v_tol) * k
        a3 = (0.5 * (1.0 + v_tol) - 2.0 * a1) * k2
        return [a1, a2, a3, a2 * k2, a1 * k2 * k2], [0.0, 0.5 * t_d, t_d, 1.5 * t_d, 2.0 * t_d]
    return None


def shaper_smoothing(pulses, accel=5000.0, scv=5.0):
    amps, times = pulses
    half_accel = accel * 0.5
    inv_d = 1.0 / sum(amps)
    ts = sum(a * t for a, t in zip(amps, times)) * inv_d
    offset_90 = offset_180 = 0.0
    for a, t in zip(amps, times):
        if t >= ts:
            offset_90 += a * (scv + half_accel * (t - ts)) * (t - ts)
        offset_180 += a * half_accel * (t - ts) ** 2
    return max(offset_90 * inv_d * math.sqrt(2.0), offset_180 * inv_d)


def shaper_max_accel(pulses, scv=5.0):
    """The highest acceleration that keeps the smoothing under Klipper's target (bisection, as Klipper does)."""
    ok = lambda accel: shaper_smoothing(pulses, accel, scv) <= TARGET_SMOOTHING
    left = right = 1.0
    if not ok(1e-9):
        return 0.0
    while not ok(left):
        right = left
        left *= 0.5
    if right == left:
        while ok(right):
            right *= 2.0
    while right - left > 1e-8:
        middle = (left + right) * 0.5
        if ok(middle):
            left = middle
        else:
            right = middle
    return left


def damping_estimate(freq, psd):
    """(resonance frequency, damping ratio) from the half-power width of the highest peak, or (peak, None)."""
    if not psd:
        return None, None
    i = max(range(len(psd)), key=lambda n: psd[n])
    half = psd[i] / 2.0
    def cross(step):
        j = i
        while 0 <= j + step < len(psd) and psd[j + step] > half:
            j += step
        k = j + step
        if not 0 <= k < len(psd):
            return None
        span = psd[j] - psd[k]
        return freq[j] + (freq[k] - freq[j]) * ((psd[j] - half) / span if span else 0.0)
    low, high = cross(-1), cross(1)
    if low is None or high is None or freq[i] <= 0:
        return freq[i], None
    return freq[i], round((high - low) / (2.0 * freq[i]), 3)


def find_peaks(freq, psd, min_gap=5.0):
    """The local highs above PEAKS_DETECTION of the highest, at least min_gap Hz apart: [{freq, value}], by frequency."""
    if not psd:
        return []
    top = max(psd)
    floor = top * PEAKS_DETECTION
    found = []
    for i in range(1, len(psd) - 1):
        lo, hi = max(0, i - 3), min(len(psd), i + 4)
        if psd[i] > floor and psd[i] == max(psd[lo:hi]) and psd[i] > psd[i - 1]:
            if found and freq[i] - found[-1]["freq"] < min_gap:
                if psd[i] > found[-1]["value"]:
                    found[-1] = {"freq": freq[i], "value": psd[i]}
                continue
            found.append({"freq": freq[i], "value": psd[i]})
    return found[:12]


def analyse(data, scv=5.0, damping=0.1):
    """Adds to a parsed file: each shaper's smoothing, max_accel and score, the two recommendations, ω0 and ζ, the
    peaks and the two bands."""
    total = data["psd"].get("sum") or []
    for shaper in data["shapers"]:
        pulses = shaper_pulses(shaper["name"], shaper["freq"], damping)
        if not pulses:
            shaper["smoothing"] = shaper["max_accel"] = None
            continue
        shaper["smoothing"] = round(shaper_smoothing(pulses, scv=scv), 3)
        shaper["max_accel"] = int(round(shaper_max_accel(pulses, scv) / 10.0) * 10)
        vib = shaper["vibrations"] / 100.0
        shaper["score"] = shaper_smoothing(pulses, scv=scv) * (vib ** 1.5 + vib * 0.2 + 0.01)
    known = [sh for sh in data["shapers"] if sh.get("smoothing") is not None]
    known.sort(key=lambda sh: SHAPER_ORDER.index(sh["name"]) if sh["name"] in SHAPER_ORDER else 99)
    best = None
    for sh in known:  # Klipper's own choice (find_best_shaper)
        if best is None or sh["score"] * 1.2 < best["score"] or (sh["score"] * 1.05 < best["score"] and sh["smoothing"] * 1.1 < best["smoothing"]):
            best = sh
    calm = min(known, key=lambda sh: (sh["vibrations"], sh["smoothing"])) if known else None
    for sh in data["shapers"]:
        sh.pop("score", None)
    omega, zeta = damping_estimate(data["freq"], total)
    top = max(total) if total else 0.0
    data.update({
        "recommended": {"performance": best["name"] if best else None, "low_vibrations": calm["name"] if calm else None},
        "resonance": {"freq": omega, "damping": zeta},
        "peaks": find_peaks(data["freq"], total),
        "bands": {"relax": top * PEAKS_DETECTION, "warning": top * PEAKS_EFFECT},
        "scv": scv,
    })
    return data


def number_arg(text, default, low, high):
    """A query-string number within [low, high], else the default."""
    try:
        value = float(text)
    except (TypeError, ValueError):
        return default
    return value if low <= value <= high and value == value else default


def read(name, dirs=None, scv=5.0, damping=0.1):
    full = find_file(name, dirs)
    if os.path.getsize(full) > 4 * 1024 * 1024:
        raise ShaperError("file too large")
    with open(full, "r", encoding="utf-8", errors="ignore") as handle:
        data = parse(handle.read())
    match = FILE_RE.match(name)
    data.update({"name": name, "axis": match.group(1).lower(), "modified": int(os.path.getmtime(full))})
    return analyse(data, scv, damping)
