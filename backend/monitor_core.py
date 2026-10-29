"""
The judging part of KlippEye's AI print monitor: given the camera pictures of a print, one after the other, it decides when
something suspicious stays in the picture long enough to call the AI (a "trigger").

It is used in two places, so that they always judge the same way:
  * the backend (klippeye_backend.py, LightDetector), live, on the pictures of the camera;
  * the replay (scripts/replay.py), on the pictures recorded during earlier prints (recorder.py), to count how many alarms a
    given set of thresholds would have raised.
Time is passed in (`now`), never read here, so a replay runs as fast as the computer allows. Needs OpenCV and numpy.

The machine masks (phase 4b, machine_masks.py): with each picture the caller may give `ignore`, the parts of the picture
where the toolhead and the gantry are at that moment. They are left out of everything: of the comparison, of the background
(each background picture keeps its own mask and the background is the median of the pictures that saw that point free) and
of the "the whole picture changed" check.
"""
import time
from collections import deque

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:  # the backend still starts without them; the monitor stays off
    cv2 = None
    np = None
    HAS_CV2 = False

OPENCV_WIDTH = 1080   # the pictures are looked at in this size (the filter works at half of it)
OPENCV_HEIGHT = 720
REFERENCE_SAMPLES = 7  # background pictures (median)
REFERENCE_MIN = 5  # below this number the comparison is not ready
GLOBAL_STREAK_MAX = 10  # checks in a row with a "global" change before it counts as real


class FrameJudge:
    """The thresholds and the memory of the monitor (background, recent changes, counters) and the decision for one picture."""

    def __init__(self):
        self.verbose = True  # live: a line in the log for every anomaly; the replay is quiet
        self.last_frames = deque(maxlen=5)
        self.roi = None
        # The thresholds below are the defaults; apply_config() puts the saved ones (monitor.json).
        self.sensitivity = 35
        self.trigger_count = 0
        self.trigger_threshold = 3
        self.cooldown_until = 0
        self.cooldown_sec = 90
        self.ai_cooldown = 120
        self.score_threshold = 2.5  # % of the outer band that must move
        self.check_interval = 3  # seconds between two checks
        self.border = 0.25  # width of the outer band, fraction of the watched area
        self.warmup = 90  # seconds of printing before checking starts
        self.min_progress = 2  # % of progress before checking starts
        self.hotend_tol = 8  # how far the nozzle may be from its target temperature
        self.ai_model = ""
        self.persistent_filter = True  # the filter against false alarms (see _persistent_score)
        self.persist_checks = 3
        self.machine_masks = True  # leave out the toolhead and the gantry (the caller gives the mask: machine_masks.py)
        self.reference_seconds = 60
        self.global_change = 30.0
        self.ai_min_confidence = 70
        self.ai_send_reference = True
        self.recent_masks = deque(maxlen=3)
        self.ref_small = deque(maxlen=REFERENCE_SAMPLES)  # (time, small grey picture) for the background
        self.ref_jpegs = deque(maxlen=REFERENCE_SAMPLES)  # (time, picture as the camera sent it) to show the AI "how it was before"
        self.ref_ignore = deque(maxlen=REFERENCE_SAMPLES)  # the machine mask of each background picture (or None)
        self.bg = None
        self.bg_unknown = None  # points that no background picture saw free of the toolhead (not compared)
        self.last_ignore = None  # the mask of the previous picture (the comparison without the filter)
        self.global_streak = 0
        self.global_streak_max = GLOBAL_STREAK_MAX
        self.stats = {
            "frames_checked": 0,
            "anomalies": 0,
            "last_trigger": None,
            "last_score": 0,
            "status": "idle - waiting for a print",
        }

    def log(self, text):
        if self.verbose:
            print(text)

    def apply_config(self, values):
        """Puts the thresholds in use (the settings of monitor.json). They apply from the next check, nothing is restarted.
        A key that is missing keeps its value (the replay may give only some)."""
        get = values.get
        self.sensitivity = get("sensitivity", self.sensitivity)
        self.score_threshold = get("score_threshold", self.score_threshold)
        self.trigger_threshold = get("trigger_count", self.trigger_threshold)
        self.check_interval = get("check_interval", self.check_interval)
        self.border = get("border", self.border * 100.0) / 100.0
        self.cooldown_sec = get("cooldown", self.cooldown_sec)
        self.ai_cooldown = get("ai_cooldown", self.ai_cooldown)
        self.warmup = get("warmup_seconds", self.warmup)
        self.min_progress = get("min_progress", self.min_progress)
        self.hotend_tol = get("hotend_tolerance", self.hotend_tol)
        self.ai_model = get("ai_model", self.ai_model)
        self.persistent_filter = get("persistent_filter", self.persistent_filter)
        self.machine_masks = get("machine_masks", self.machine_masks)
        persist = get("persist_checks", self.persist_checks)
        if persist != self.persist_checks or self.recent_masks.maxlen != persist:
            self.recent_masks = deque(maxlen=persist)
        self.persist_checks = persist
        self.reference_seconds = get("reference_seconds", self.reference_seconds)
        self.global_change = get("global_change", self.global_change)
        self.ai_min_confidence = get("ai_min_confidence", self.ai_min_confidence)
        self.ai_send_reference = get("ai_send_reference", self.ai_send_reference)
        if "roi" in values:
            x, y, w, h = values["roi"]  # in % of the picture -> pixels of the resized picture (1080x720)
            self.roi = (int(OPENCV_WIDTH * x / 100), int(OPENCV_HEIGHT * y / 100), int(OPENCV_WIDTH * w / 100), int(OPENCV_HEIGHT * h / 100))

    def judge(self, frame, raw, now, ignore=None):
        """One check of one picture (`frame` decoded by OpenCV, `raw` as the camera sent it) taken at `now` (seconds).
        `ignore`: the machine mask of this picture (uint8, any size, 255 = leave out) or None.
        -> (score in % or None when there is nothing to count yet, True when this check triggers the alarm).
        After a trigger the monitor rests until `cooldown_until`: the caller does not judge pictures before then."""
        score = self._persistent_score(frame, raw, now, ignore) if self.persistent_filter else self._motion_score(frame, ignore)
        if score is None:  # the comparison is not ready yet, or this check is to be ignored (light change)
            return None, False
        self.stats["last_score"] = round(score, 2)
        # threshold: more than 2.5% (default) of the outer pixels moving = suspicious
        if score > self.score_threshold:
            self.trigger_count += 1
            self.stats["anomalies"] += 1
            self.log(f"[OPENCV] Anomalia {self.trigger_count}/{self.trigger_threshold} score={score:.2f}%")
        else:
            self.trigger_count = max(0, self.trigger_count - 1)
        if self.trigger_count < self.trigger_threshold:
            return score, False
        self.log(f"[OPENCV] TRIGGER spaghetti! score={score:.2f}%")
        self.stats["last_trigger"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
        self.stats["status"] = f"TRIGGERED score={score:.2f}%"
        self.cooldown_until = now + self.cooldown_sec
        self.trigger_count = 0
        return score, True

    @staticmethod
    def _fit_mask(ignore, shape):
        """The machine mask at the size of the picture being looked at (None stays None)."""
        if ignore is None:
            return None
        h, w = shape[:2]
        if ignore.shape[:2] != (h, w):
            ignore = cv2.resize(ignore, (w, h), interpolation=cv2.INTER_NEAREST)
        return ignore

    def _note_masked(self, ignore):
        self.stats["masked"] = None if ignore is None else round(cv2.countNonZero(ignore) * 100.0 / ignore.size, 1)

    def _motion_score(self, frame, ignore=None):
        """The older detection (filter off): how much the outer band moves between two pictures in a row, in % of the area."""
        small = cv2.resize(frame, (OPENCV_WIDTH, OPENCV_HEIGHT))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        self.last_frames.append(gray)
        self.stats["frames_checked"] += 1
        self.stats["status"] = "scanning"
        if len(self.last_frames) < 3:
            return None
        prev = self.last_frames[-2]  # compare with the previous picture (simple background subtraction)
        diff = cv2.absdiff(prev, gray)
        thresh = cv2.threshold(diff, self.sensitivity, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        now_mask, before = self._fit_mask(ignore, thresh.shape), self.last_ignore
        self.last_ignore = now_mask
        both = now_mask if before is None or now_mask is None else cv2.bitwise_or(now_mask, before)
        self._note_masked(both)
        if both is not None:
            thresh = cv2.bitwise_and(thresh, cv2.bitwise_not(both))  # where the toolhead is now or was in the previous picture
        return self._periphery_score(thresh, 1.0)

    def _roi_rect(self, shape, scale):
        """The watched area (pixels of the 1080x720 picture) at the scale of the picture being looked at."""
        h, w = shape[:2]
        if self.roi is None:
            return int(w * 0.2), int(h * 0.2), int(w * 0.6), int(h * 0.6)
        x, y, rw, rh = self.roi
        return int(x * scale), int(y * scale), int(rw * scale), int(rh * scale)

    def _periphery_mask(self, h, w):
        border = self.border  # outer band: 25% by default
        mask = np.zeros((h, w), np.uint8)
        mask[:int(h * border), :] = 255  # top
        mask[int(h * (1 - border)):, :] = 255  # bottom
        mask[:, :int(w * border)] = 255  # left
        mask[:, int(w * (1 - border)):] = 255  # right
        return mask

    def _periphery_score(self, thresh, scale):
        """% of the watched area covered by "changed" points in the outer band."""
        x, y, rw, rh = self._roi_rect(thresh.shape, scale)
        roi_thresh = thresh[y:y + rh, x:x + rw]
        h_roi, w_roi = roi_thresh.shape
        if h_roi == 0 or w_roi == 0:
            return 0.0
        moved = cv2.bitwise_and(roi_thresh, roi_thresh, mask=self._periphery_mask(h_roi, w_roi))
        return (cv2.countNonZero(moved) / (w_roi * h_roi)) * 100

    def _reset_reference(self):
        self.ref_small.clear()
        self.ref_jpegs.clear()
        self.ref_ignore.clear()
        self.recent_masks.clear()
        self.bg = None
        self.bg_unknown = None
        self.last_ignore = None
        self.global_streak = 0

    def _persistent_score(self, frame, raw, now=None, ignore=None):
        """
        The filter against false alarms. Instead of comparing two pictures in a row (the passing print head is enough to trigger):
          1. the BACKGROUND is the median of 7 pictures spread over the last `reference_seconds`: what stays in a place only
             for a moment (print head, hand, reflection) is not part of it;
          2. the average brightness is aligned to the background's (the camera adjusting its exposure is not movement);
          3. if more than `global_change`% of the whole picture changes at once (light, camera moved) the check is ignored, but
             if it lasts more than GLOBAL_STREAK_MAX checks in a row it is a real change;
          4. only what changed against the background, in the outer band of the area, in ALL the last `persist_checks` checks counts;
          5. the machine masks (`ignore`) are left out of all of it.
        It works at half resolution: 4 times fewer points to look at. -> % of the area, or None (nothing to count now).
        """
        now = time.time() if now is None else now
        small = cv2.resize(frame, (OPENCV_WIDTH // 2, OPENCV_HEIGHT // 2), interpolation=cv2.INTER_AREA)
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (11, 11), 0)
        ignore = self._fit_mask(ignore, gray.shape)
        self._note_masked(ignore)
        self.stats["frames_checked"] += 1
        if self.ref_small and now - self.ref_small[-1][0] > 2 * self.reference_seconds:
            self._reset_reference()  # a long pause: the old background is no longer valid
        result = None
        if self.bg is not None and self.bg.shape == gray.shape:
            result = self._compare_with_background(gray, ignore)
        else:
            self.stats["status"] = "preparing the comparison (%d/%d pictures)" % (len(self.ref_small), REFERENCE_MIN)
        step = max(self.check_interval, self.reference_seconds / REFERENCE_SAMPLES)
        if not self.ref_small or now - self.ref_small[-1][0] >= step:
            self.ref_small.append((now, gray))
            self.ref_jpegs.append((now, raw))
            self.ref_ignore.append(ignore)
            if len(self.ref_small) >= REFERENCE_MIN:
                self._make_background()
        return result

    def _make_background(self):
        """The median of the background pictures; with machine masks, for each point only the pictures that saw it free."""
        stack = np.stack([g for _, g in self.ref_small])
        masks = list(self.ref_ignore)
        if all(m is None for m in masks) or any(m is not None and m.shape != stack.shape[1:] for m in masks):
            self.bg, self.bg_unknown = np.median(stack, axis=0).astype(np.uint8), None
            return
        hidden = np.stack([np.zeros(stack.shape[1:], bool) if m is None else m > 0 for m in masks])
        values = np.where(hidden, 999, stack.astype(np.int16))
        values.sort(axis=0)
        free = (~hidden).sum(axis=0)
        pick = np.maximum(free - 1, 0) // 2  # the (lower) median of the free values, which come first after sorting
        bg = np.take_along_axis(values, pick[None], axis=0)[0]
        unknown = free == 0
        self.bg = np.where(unknown, 0, bg).astype(np.uint8)
        self.bg_unknown = unknown.astype(np.uint8) * 255 if unknown.any() else None

    def _compare_with_background(self, gray, ignore=None):
        leave_out = ignore
        if self.bg_unknown is not None:
            leave_out = self.bg_unknown if leave_out is None else cv2.bitwise_or(leave_out, self.bg_unknown)
        keep = None if leave_out is None else cv2.bitwise_not(leave_out)
        if keep is None:
            shift = float(gray.mean()) - float(self.bg.mean())
        else:
            shift = float(cv2.mean(gray, mask=keep)[0]) - float(cv2.mean(self.bg, mask=keep)[0])
        if abs(shift) > 1:
            gray = cv2.convertScaleAbs(gray, alpha=1.0, beta=-shift)
        thresh = cv2.threshold(cv2.absdiff(self.bg, gray), self.sensitivity, 255, cv2.THRESH_BINARY)[1]
        if keep is not None:
            thresh = cv2.bitwise_and(thresh, keep)
        visible = thresh.size if keep is None else max(1, cv2.countNonZero(keep))
        changed = cv2.countNonZero(thresh) * 100.0 / visible
        self.stats["global_change"] = round(changed, 1)
        if changed > self.global_change:
            self.global_streak += 1
            self.recent_masks.clear()
            if self.global_streak < self.global_streak_max:
                self.stats["ignored_global"] = self.stats.get("ignored_global", 0) + 1
                self.stats["status"] = f"light change or camera moved ({changed:.0f}% of the picture): ignored"
                return None
            self.stats["status"] = "scanning (large lasting change)"
            return changed  # it lasted many checks: not a flash of light
        self.global_streak = 0
        thresh = cv2.dilate(thresh, None, iterations=1)
        x, y, rw, rh = self._roi_rect(thresh.shape, 0.5)
        roi = thresh[y:y + rh, x:x + rw]
        if roi.size == 0:
            return 0.0
        if self.recent_masks and self.recent_masks[-1].shape != roi.shape:
            self.recent_masks.clear()  # the area was changed from the menu
        self.recent_masks.append(roi)
        self.stats["status"] = "scanning"
        if len(self.recent_masks) < self.recent_masks.maxlen:
            return 0.0
        persistent = self.recent_masks[0]
        for other in list(self.recent_masks)[1:]:
            persistent = cv2.bitwise_and(persistent, other)
        h_roi, w_roi = persistent.shape
        stays = cv2.bitwise_and(persistent, persistent, mask=self._periphery_mask(h_roi, w_roi))
        return (cv2.countNonZero(stays) / (w_roi * h_roi)) * 100
