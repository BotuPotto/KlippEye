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

import shaper_fit

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
TEST_DAMPING_RATIOS = (0.075, 0.1, 0.15)  # Klipper keeps the worst of the three when it counts the vibrations left
DEFAULT_DAMPING = 0.1  # the damping ratio Klipper fits the shapers with in SHAPER_CALIBRATE

# 1.89: what SHAPER_CALIBRATE says in the console (and in klippy.log), so the card shows Klipper's own figures
KLIPPER_START_RE = re.compile(r"Calculating the best input shaper parameters for (\w+) axis")
KLIPPER_FIT_RE = re.compile(r"Fitted shaper '(\w+)' frequency = ([\d.]+) Hz \(vibrations = ([\d.]+)%, smoothing ~= ([\d.]+)\)")
KLIPPER_ACCEL_RE = re.compile(r"To avoid too much smoothing with '(\w+)', suggested max_accel <= ([\d.]+) mm/sec")
KLIPPER_BEST_RE = re.compile(r"Recommended shaper_type_(\w+) = (\w+), shaper_freq_\w+ = ([\d.]+) Hz")
KLIPPER_FILE_RE = re.compile(r"(?:Shaper calibration data|Calibration data) written to (\S+?) file", re.IGNORECASE)
KLIPPER_FOUND = {}  # file name -> Klipper's results (the names carry the date: they never change)


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
    # 1.90: a measurement over several points has a column per point instead: their highest value stands for the sum
    shaper_indexes = {shaper["index"] for shaper in shapers}
    points = [index for index, name in enumerate(header) if index and index not in shaper_indexes and name and not name.endswith(":")] if not psd else []
    if points:
        psd["sum"] = []
    for line in lines[1:]:
        cells = line.split(",")
        if len(cells) < len(header):
            continue
        value = _number(cells[0])
        if value is None or value > MAX_FREQ:
            continue
        freq.append(round(value, 2))
        if points:
            psd["sum"].append(max(_number(cells[index]) or 0.0 for index in points))
        else:
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
# 1.89 / 1.90: the analysis. Klipper's figures (what SHAPER_CALIBRATE said in the console, else its own fitting run
# again on the file with its damping ratio, 0.1) or the shapers fitted again with the damping ratio measured on the
# curve; the recommendation for low vibrations (Klipper's choice) and for performance; the resonance, the peaks and the
# two bands.
# ---------------------------------------------------------------------------------------------------------------------
def damping_estimate(freq, psd):
    """(resonance frequency, damping ratio): the half-power bandwidth of the highest peak (at peak/√2, interpolated),
    ζ = √(1/2 − √(1/(4 + 4β² − β⁴))) with β = bandwidth / f0; (peak, None) when it cannot be measured."""
    if not psd:
        return None, None
    i = max(range(len(psd)), key=lambda n: psd[n])
    f0, half = freq[i], psd[i] / math.sqrt(2.0)
    below = [n for n in range(i) if psd[n] <= half]
    above = [n for n in range(i, len(psd)) if psd[n] <= half]
    if not below or not above or f0 <= 0:
        return f0, None
    lo, hi = below[-1], above[0]
    try:
        f1 = freq[lo] + (half - psd[lo]) * (freq[lo + 1] - freq[lo]) / (psd[lo + 1] - psd[lo])
        f2 = freq[hi - 1] + (half - psd[hi - 1]) * (freq[hi] - freq[hi - 1]) / (psd[hi] - psd[hi - 1])
        b1 = ((f2 - f1) / f0) ** 2
        zeta = math.sqrt(0.5 - math.sqrt(1.0 / (4.0 + 4.0 * b1 - b1 * b1)))
    except (ZeroDivisionError, ValueError):
        return f0, None
    return f0, round(zeta, 4)


def find_peaks(freq, psd, window=5, vicinity=3):
    """The peaks: where a moving average (5 points) turns down above PEAKS_DETECTION of the highest vibration, moved
    to the highest point nearby. [{freq, value}], by frequency."""
    if len(psd) < window + 2:
        return []
    top = max(psd)
    smooth = [sum(psd[:window]) / window] * (window // 2) + [sum(psd[i:i + window]) / window for i in range(len(psd) - window + 1)]
    found = []
    for i in range(1, len(smooth) - 1):
        if smooth[i - 1] < smooth[i] > smooth[i + 1] and smooth[i] > top * PEAKS_DETECTION:
            lo, hi = max(0, i - vicinity), min(len(psd), i + vicinity + 1)
            at = max(range(lo, hi), key=lambda n: psd[n])
            if not found or found[-1]["index"] != at:
                found.append({"index": at, "freq": freq[at], "value": psd[at]})
    for one in found:
        del one["index"]
    return found[:12]


def shaper_pulses(name, freq, damping=0.1):
    return shaper_fit.init_shaper(name, freq, damping)


def klipper_vibrations(freq, psd, pulses):
    """Without numpy: the part of the vibrations the shaper leaves (0..1) as SHAPER_CALIBRATE counts it."""
    if not psd or max(psd) <= 0:
        return 0.0
    threshold = max(psd) / VIBRATION_REDUCTION
    total = sum(max(p - threshold, 0.0) for p in psd)
    worst = 0.0
    for damping in TEST_DAMPING_RATIOS:
        worst = max(worst, sum(max(_response(pulses, f, damping) * p - threshold, 0.0) for f, p in zip(freq, psd)))
    return worst / total if total > 0 else 0.0


def _response(pulses, freq, damping):
    amps, times = pulses
    omega = 2.0 * math.pi * freq
    decay, omega_d = damping * omega, omega * math.sqrt(1.0 - damping ** 2)
    s = c = 0.0
    for a, t in zip(amps, times):
        w = a * math.exp(-decay * (times[-1] - t))
        s += w * math.sin(omega_d * t)
        c += w * math.cos(omega_d * t)
    return math.sqrt(s * s + c * c) / sum(amps)


def klipper_results(lines):
    """Klipper's console lines → {file name: {axis, shapers: {name: {freq, vibrations, smoothing, max_accel}},
    recommended: {name, freq}}}, for each measurement whose file it says it wrote."""
    found, block = {}, None
    for entry in lines:
        for line in str(entry or "").split("\n"):
            line = re.sub(r"^(//|!!)\s?", "", line.strip())
            match = KLIPPER_START_RE.search(line)
            if match:
                block = {"axis": match.group(1).lower(), "shapers": {}, "recommended": None}
                continue
            if block is None:
                continue
            match = KLIPPER_FIT_RE.search(line)
            if match:
                block["shapers"][match.group(1).lower()] = {"freq": float(match.group(2)), "vibrations": float(match.group(3)), "smoothing": float(match.group(4)), "max_accel": None}
                continue
            match = KLIPPER_ACCEL_RE.search(line)
            if match and match.group(1).lower() in block["shapers"]:
                block["shapers"][match.group(1).lower()]["max_accel"] = int(float(match.group(2)))
                continue
            match = KLIPPER_BEST_RE.search(line)
            if match:
                block["recommended"] = {"name": match.group(2).lower(), "freq": float(match.group(3))}
                continue
            match = KLIPPER_FILE_RE.search(line)
            if match:
                found[os.path.basename(match.group(1))] = block
                block = None
    return found


def find_klipper_results(name, sources):
    """Klipper's results for the file `name`, from the first source (a function giving console lines) that has them."""
    if name in KLIPPER_FOUND:
        return KLIPPER_FOUND[name]
    for source in sources or []:
        try:
            block = klipper_results(source()).get(name)
        except Exception:
            block = None
        if block and block["shapers"]:
            KLIPPER_FOUND[name] = block
            return block
    return None


FIT_CACHE = {}  # (file, scv, damping) -> fitted shapers: the fit takes seconds on a Raspberry


def _fitted(data, scv, damping, max_smoothing=None, accel_step=100):
    """Klipper's fitting on the file. accel_step: the max accel rounded as Klipper's console (100) or to 10."""
    key = (data.get("name"), data.get("modified"), round(scv, 3), round(damping, 4), max_smoothing, accel_step)
    if key not in FIT_CACHE:
        total = data["psd"].get("sum") or []
        best, fitted = shaper_fit.find_best_shaper(data["freq"], total, damping_ratio=damping, scv=scv, max_smoothing=max_smoothing)
        freqs = shaper_fit.np.asarray(data["freq"], dtype=float)
        shapers = []
        for one in fitted:
            vals = shaper_fit.remaining(shaper_fit.init_shaper(one["name"], one["freq"], damping), freqs, shaper_fit.np.asarray(total, dtype=float))[1]
            shapers.append({"name": one["name"], "freq": round(one["freq"], 1), "vibrations": round(one["vibrs"] * 100, 1), "smoothing": round(one["smoothing"], 3),
                            "max_accel": int(round(one["max_accel"] / accel_step) * accel_step), "response": [round(float(v), 3) for v in vals]})
        if len(FIT_CACHE) > 32:
            FIT_CACHE.clear()
        FIT_CACHE[key] = {"shapers": shapers, "recommended": {"name": best["name"], "freq": round(best["freq"], 1)} if best else None}
    found = FIT_CACHE[key]
    return {"shapers": [dict(one) for one in found["shapers"]], "recommended": dict(found["recommended"]) if found["recommended"] else None}


def _estimated(data, scv):
    """Without numpy and without Klipper's messages: the shapers of the file, their figures counted as Klipper does."""
    total = data["psd"].get("sum") or []
    shapers, scores = [], {}
    for one in data["shapers"]:
        pulses = shaper_fit.init_shaper(one["name"], one["freq"], DEFAULT_DAMPING)
        if not pulses:
            continue
        vib = klipper_vibrations(data["freq"], total, pulses) if total else one["vibrations"] / 100.0
        smooth = shaper_fit.smoothing(pulses, scv=scv)
        shapers.append({"name": one["name"], "freq": one["freq"], "vibrations": round(vib * 100, 1), "smoothing": round(smooth, 3),
                        "max_accel": int(round(shaper_fit.max_accel(pulses, scv) / 100.0) * 100), "response": one["response"]})
        scores[one["name"]] = smooth * (vib ** 1.5 + vib * 0.2 + 0.01)
    best = None
    for sh in sorted(shapers, key=lambda sh: SHAPER_ORDER.index(sh["name"]) if sh["name"] in SHAPER_ORDER else 99):
        if best is None or scores[sh["name"]] * 1.2 < scores[best["name"]] or (scores[sh["name"]] * 1.05 < scores[best["name"]] and sh["smoothing"] * 1.1 < best["smoothing"]):
            best = sh
    return {"shapers": shapers, "recommended": {"name": best["name"], "freq": best["freq"]} if best else None}


def analyse(data, scv=5.0, mode="measured", klipper=None, max_smoothing=None):
    """Adds to a parsed file the resonance (ω0, ζ), the peaks, the bands and `analysis`: the shapers (frequency,
    vibrations %, smoothing, max accel, response) and the recommendations, for `mode`:
    - "measured" (the default): Klipper's fitting run on the file with the damping ratio measured on the curve (0.1 when
      it cannot be measured), the printer's square corner velocity and the allowed smoothing (source "computed");
    - "klipper": SHAPER_CALIBRATE's own result — its messages in the console (source "console"), else its fitting run
      again on the file with its damping ratio 0.1 (source "computed"), else, without numpy, the file's shapers with
      their figures counted as Klipper does (source "estimate")."""
    total = data["psd"].get("sum") or []
    omega, zeta = damping_estimate(data["freq"], total)
    top = max(total) if total else 0.0
    measurable = shaper_fit.available() and bool(total)
    if mode == "measured" and measurable:
        damping = min(max(zeta, 0.01), 0.3) if zeta is not None else DEFAULT_DAMPING
        found, source = _fitted(data, scv, damping, max_smoothing, accel_step=10), "computed"
    elif klipper:
        by_name = {one["name"]: one for one in data["shapers"]}
        shapers = []
        for name, said in klipper["shapers"].items():
            own = by_name.get(name)
            shapers.append({"name": name, "freq": said["freq"], "vibrations": said["vibrations"], "smoothing": said["smoothing"], "max_accel": said["max_accel"],
                            "response": own["response"] if own and abs(own["freq"] - said["freq"]) < 0.25 else None})
        if any(one["response"] is None for one in shapers) and shaper_fit.available():
            freqs = shaper_fit.np.asarray(data["freq"], dtype=float)
            for one in shapers:
                if one["response"] is None and total:
                    vals = shaper_fit.remaining(shaper_fit.init_shaper(one["name"], one["freq"], DEFAULT_DAMPING), freqs, shaper_fit.np.asarray(total, dtype=float))[1]
                    one["response"] = [round(float(v), 3) for v in vals]
        found, source, damping = {"shapers": shapers, "recommended": klipper.get("recommended")}, "console", DEFAULT_DAMPING
    elif measurable:
        found, source, damping = _fitted(data, scv, DEFAULT_DAMPING, max_smoothing), "computed", DEFAULT_DAMPING
    else:
        found, source, damping = _estimated(data, scv), "estimate", DEFAULT_DAMPING
    shapers = sorted(found["shapers"], key=lambda sh: SHAPER_ORDER.index(sh["name"]) if sh["name"] in SHAPER_ORDER else 99)
    chosen = found["recommended"]["name"] if found["recommended"] else None
    fast = shaper_fit.performance_pick(shapers, chosen) if chosen else None
    fast_one = next((one for one in shapers if one["name"] == fast), None)
    data.update({
        "analysis": {
            "mode": "measured" if mode == "measured" and measurable else "klipper",
            "source": source,
            "damping": damping,
            "max_smoothing": max_smoothing,
            "max_smoothing_computed": max((one["smoothing"] or 0 for one in shapers), default=0),
            "shapers": shapers,
            "low_vibrations": found["recommended"],
            "performance": {"name": fast_one["name"], "freq": fast_one["freq"]} if fast_one else None,
        },
        "measured_available": measurable,
        "resonance": {"freq": omega, "damping": zeta},
        "peaks": find_peaks(data["freq"], total),
        "bands": {"relax": top * PEAKS_DETECTION, "warning": top * PEAKS_EFFECT},
        "scv": scv,
    })
    data.pop("shapers", None)
    return data


def number_arg(text, default, low, high):
    """A query-string number within [low, high], else the default."""
    try:
        value = float(text)
    except (TypeError, ValueError):
        return default
    return value if low <= value <= high and value == value else default


def read(name, dirs=None, scv=5.0, mode="measured", sources=None, max_smoothing=None):
    full = find_file(name, dirs)
    if os.path.getsize(full) > 4 * 1024 * 1024:
        raise ShaperError("file too large")
    with open(full, "r", encoding="utf-8", errors="ignore") as handle:
        data = parse(handle.read())
    match = FILE_RE.match(name)
    data.update({"name": name, "axis": match.group(1).lower(), "modified": int(os.path.getmtime(full))})
    return analyse(data, scv, mode, find_klipper_results(name, sources) if mode == "klipper" else None, max_smoothing)
