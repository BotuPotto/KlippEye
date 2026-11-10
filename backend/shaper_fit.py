"""Klipper's input shaper fitting, run on the file SHAPER_CALIBRATE leaves (1.90).

Ported from Klipper (klippy/extras/shaper_defs.py and shaper_calibrate.py, GNU GPLv3, as KlippEye): the shapers'
impulses, the vibrations a shaper leaves, its smoothing, its suggested max acceleration, the search of each shaper's
frequency and the choice of the best one. The file's vibrations (psd_xyz) are the ones Klipper fitted on (already
normalised), so with Klipper's damping ratio (0.1) this gives Klipper's own result; with the damping ratio measured on
the curve it gives the shapers tuned to this printer.

Needs numpy (installed with the backend); without it `available()` is False and nothing here is used.
"""

import math

try:
    import numpy as np
except ImportError:  # pragma: no cover - the installer adds it
    np = None

SHAPER_VIBRATION_REDUCTION = 20.0
DEFAULT_DAMPING_RATIO = 0.1
TEST_DAMPING_RATIOS = (0.075, 0.1, 0.15)
MAX_SHAPER_FREQ = 150.0
TARGET_SMOOTHING = 0.12
AUTOTUNE_SHAPERS = ("zv", "mzv", "ei", "2hump_ei", "3hump_ei")
MIN_FREQ = {"zv": 21.0, "mzv": 23.0, "zvd": 29.0, "ei": 29.0, "2hump_ei": 39.0, "3hump_ei": 48.0}
MAX_DAMPING = {"zv": 0.99, "mzv": 0.99, "zvd": 0.99, "ei": 0.4, "2hump_ei": 0.3, "3hump_ei": 0.2}
# the performance pick: the shaper with the highest max acceleration among those leaving less than this
PERFORMANCE_MAX_VIBRATIONS = 0.05


def available():
    return np is not None


# ---- the shapers (shaper_defs.py) ------------------------------------------------------------------------------------
def _zv(freq, dr):
    df = math.sqrt(1.0 - dr ** 2)
    k = math.exp(-dr * math.pi / df)
    t_d = 1.0 / (freq * df)
    return [1.0, k], [0.0, 0.5 * t_d]


def _zvd(freq, dr):
    df = math.sqrt(1.0 - dr ** 2)
    k = math.exp(-dr * math.pi / df)
    t_d = 1.0 / (freq * df)
    return [1.0, 2.0 * k, k ** 2], [0.0, 0.5 * t_d, t_d]


def _mzv(freq, dr):
    # Klipper's get_mzv_shaper with n=3, t=0.75: its coefficients are 1-1/√2, √2-1, 1-1/√2
    df = math.sqrt(1.0 - dr ** 2)
    k = math.exp(-0.75 * dr * math.pi / df)
    t_d = 1.0 / (freq * df)
    a1 = 1.0 - 1.0 / math.sqrt(2.0)
    return [a1, (math.sqrt(2.0) - 1.0) * k, a1 * k * k], [0.0, 0.375 * t_d, 0.75 * t_d]


def _ei(freq, dr, v_tol=1.0 / SHAPER_VIBRATION_REDUCTION):
    df = math.sqrt(1.0 - dr ** 2)
    t_d = 1.0 / (freq * df)
    a1 = (0.24968 + 0.24961 * v_tol) + ((0.80008 + 1.23328 * v_tol) + (0.49599 + 3.17316 * v_tol) * dr) * dr
    a3 = (0.25149 + 0.21474 * v_tol) + ((-0.83249 + 1.41498 * v_tol) + (0.85181 - 4.90094 * v_tol) * dr) * dr
    a2 = 1.0 - a1 - a3
    t2 = 0.4999 + (((0.46159 + 8.57843 * v_tol) * v_tol) + (((4.26169 - 108.644 * v_tol) * v_tol) + ((1.75601 + 336.989 * v_tol) * v_tol) * dr) * dr) * dr
    return [a1, a2, a3], [0.0, t2 * t_d, t_d]


def _expansion(freq, dr, t, a):
    tau = 1.0 / freq
    times, amps = [], []
    k = len(a[0])
    for i in range(len(a)):
        u, v = t[i][k - 1], a[i][k - 1]
        for j in range(k - 1):
            u = u * dr + t[i][k - j - 2]
            v = v * dr + a[i][k - j - 2]
        times.append(u * tau)
        amps.append(v)
    return amps, times


def _2hump_ei(freq, dr):
    t = [[0.0, 0.0, 0.0, 0.0], [0.49890, 0.16270, -0.54262, 6.16180], [0.99748, 0.18382, -1.58270, 8.17120], [1.49920, -0.09297, -0.28338, 1.85710]]
    a = [[0.16054, 0.76699, 2.26560, -1.22750], [0.33911, 0.45081, -2.58080, 1.73650], [0.34089, -0.61533, -0.68765, 0.42261], [0.15997, -0.60246, 1.00280, -0.93145]]
    return _expansion(freq, dr, t, a)


def _3hump_ei(freq, dr):
    t = [[0.0, 0.0, 0.0, 0.0], [0.49974, 0.23834, 0.44559, 12.4720], [0.99849, 0.29808, -2.36460, 23.3990], [1.49870, 0.10306, -2.01390, 17.0320], [1.99960, -0.28231, 0.61536, 5.40450]]
    a = [[0.11275, 0.76632, 3.29160, -1.44380], [0.23698, 0.61164, -2.57850, 4.85220], [0.30008, -0.19062, -2.14560, 0.13744], [0.23775, -0.73297, 0.46885, -2.08650], [0.11244, -0.45439, 0.96382, -1.46000]]
    return _expansion(freq, dr, t, a)


SHAPERS = {"zv": _zv, "mzv": _mzv, "zvd": _zvd, "ei": _ei, "2hump_ei": _2hump_ei, "3hump_ei": _3hump_ei}


def init_shaper(name, freq, dr=DEFAULT_DAMPING_RATIO):
    make = SHAPERS.get(name)
    return make(freq, dr) if make and freq > 0 else None


# ---- the figures (shaper_calibrate.py) -------------------------------------------------------------------------------
def smoothing(shaper, accel=5000.0, scv=5.0):
    amps, times = shaper
    half_accel = accel * 0.5
    inv_d = 1.0 / sum(amps)
    ts = sum(a * t for a, t in zip(amps, times)) * inv_d
    offset_90 = offset_180 = 0.0
    for a, t in zip(amps, times):
        if t >= ts:
            offset_90 += a * (scv + half_accel * (t - ts)) * (t - ts)
        offset_180 += a * half_accel * (t - ts) ** 2
    return max(offset_90 * inv_d * math.sqrt(2.0), offset_180 * inv_d)


def max_accel(shaper, scv=5.0):
    def ok(accel):
        return smoothing(shaper, accel, scv) <= TARGET_SMOOTHING
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


def response(shaper, dr, freqs):
    """How much of a vibration at each frequency (of damping ratio dr) the shaper lets through."""
    amps, times = np.array(shaper[0]), np.array(shaper[1])
    omega = 2.0 * math.pi * freqs
    damping = dr * omega
    omega_d = omega * math.sqrt(1.0 - dr ** 2)
    w = amps * np.exp(np.outer(-damping, times[-1] - times))
    s = (w * np.sin(np.outer(omega_d, times))).sum(axis=1)
    c = (w * np.cos(np.outer(omega_d, times))).sum(axis=1)
    return np.sqrt(s ** 2 + c ** 2) / amps.sum()


def remaining(shaper, freqs, psd):
    """(vibrations left 0..1, the response): the worst over the test damping ratios, above a twentieth of the peak."""
    threshold = psd.max() / SHAPER_VIBRATION_REDUCTION
    total = np.maximum(psd - threshold, 0).sum()
    worst, vals = 0.0, np.zeros(freqs.shape)
    for dr in TEST_DAMPING_RATIOS:
        r = response(shaper, dr, freqs)
        vals = np.maximum(vals, r)
        left = np.maximum(r * psd - threshold, 0).sum() / total if total > 0 else 0.0
        worst = max(worst, float(left))
    return worst, vals


def _result(name, freq, shaper, freqs, psd, scv):
    vibrs, vals = remaining(shaper, freqs, psd)
    smooth = smoothing(shaper, scv=scv)
    return {"name": name, "freq": float(freq), "vibrs": float(vibrs), "smoothing": float(smooth), "max_accel": float(max_accel(shaper, scv)),
            "score": float(smooth * (vibrs ** 1.5 + vibrs * 0.2 + 0.01)), "vals": vals}


def fit_shaper(name, freqs, psd, damping_ratio, scv, max_smoothing=None):
    """Klipper's fit_shaper: [selected] + every frequency tried (highest first)."""
    test_freqs = np.arange(min(MIN_FREQ[name], MAX_SHAPER_FREQ - 1e-7), MAX_SHAPER_FREQ, 0.2)
    best, results = None, []
    for test_freq in test_freqs[::-1]:
        shaper = init_shaper(name, test_freq, damping_ratio)
        if max_smoothing and smoothing(shaper, scv=scv) > max_smoothing and best:
            return [best] + results
        results.append(_result(name, test_freq, shaper, freqs, psd, scv))
        if best is None or best["vibrs"] > results[-1]["vibrs"]:
            best = results[-1]
    selected = best
    for res in results[::-1]:
        if res["vibrs"] < best["vibrs"] * 1.1 + 0.0005 and res["score"] < selected["score"]:
            selected = res
    return [selected] + results


def find_best_shaper(freqs, psd, damping_ratio=DEFAULT_DAMPING_RATIO, scv=5.0, max_smoothing=None, shapers=AUTOTUNE_SHAPERS):
    """Klipper's find_best_shaper: (best, [the fitted shaper of each kind])."""
    freqs = np.asarray(freqs, dtype=float)
    psd = np.asarray(psd, dtype=float)
    best, fitted = None, []
    for name in shapers:
        if damping_ratio > MAX_DAMPING[name]:
            continue
        found = fit_shaper(name, freqs, psd, damping_ratio, scv, max_smoothing)
        shaper, results = found[0], found[1:]
        if best is None or shaper["score"] * 1.2 < best["score"] or (shaper["score"] * 1.05 < best["score"] and shaper["smoothing"] * 1.1 < best["smoothing"]):
            best = shaper
        for res in results[::-1]:
            if res["vibrs"] < best["vibrs"] and res["smoothing"] < best["smoothing"]:
                best = shaper = res
        fitted.append(shaper)
    if best is not None and best["name"] == "zv":
        for tuned in fitted:
            if tuned["name"] != "zv" and tuned["vibrs"] * 1.1 < best["vibrs"]:
                best = tuned
                break
    return best, fitted


def performance_pick(shapers, chosen):
    """The shaper with the highest max acceleration among those leaving under 5 % of the vibrations, when it is not
    the chosen one and allows at least its acceleration; else None. `shapers`: [{name, vibrations (%), max_accel}]."""
    pick = None
    for one in shapers:
        if one.get("max_accel") and one["vibrations"] < PERFORMANCE_MAX_VIBRATIONS * 100 and (pick is None or one["max_accel"] > pick["max_accel"]):
            pick = one
    base = next((one for one in shapers if one["name"] == chosen), None)
    if pick is None or base is None or pick["name"] == chosen or (pick["max_accel"] or 0) < (base.get("max_accel") or 0):
        return None
    return pick["name"]
