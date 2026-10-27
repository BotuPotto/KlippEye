"""
The judging part of KlippEye's AI print monitor: given the camera pictures of a print, one after the other, it decides when
something suspicious stays in the picture long enough to call the AI (a "trigger").

It is used in two places, so that they always judge the same way:
  * the backend (klippeye_backend.py, LightDetector), live, on the pictures of the camera;
  * the replay (scripts/replay.py), on the pictures recorded during earlier prints (recorder.py), to count how many alarms a
    given set of thresholds would have raised.
Time is passed in (`now`), never read here, so a replay runs as fast as the computer allows. Needs OpenCV and numpy.
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
        self.reference_seconds = 60
        self.global_change = 30.0
        self.ai_min_confidence = 70
        self.ai_send_reference = True
        self.recent_masks = deque(maxlen=3)
        self.ref_small = deque(maxlen=REFERENCE_SAMPLES)  # (time, small grey picture) for the background
        self.ref_jpegs = deque(maxlen=REFERENCE_SAMPLES)  # (time, picture as the camera sent it) to show the AI "how it was before"
        self.bg = None
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

    def judge(self, frame, raw, now):
        """One check of one picture (`frame` decoded by OpenCV, `raw` as the camera sent it) taken at `now` (seconds).
        -> (score in % or None when there is nothing to count yet, True when this check triggers the alarm).
        After a trigger the monitor rests until `cooldown_until`: the caller does not judge pictures before then."""
        score = self._persistent_score(frame, raw, now) if self.persistent_filter else self._motion_score(frame)
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

    def _motion_score(self, frame):
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
        self.recent_masks.clear()
        self.bg = None
        self.global_streak = 0

    def _persistent_score(self, frame, raw, now=None):
        """
        The filter against false alarms. Instead of comparing two pictures in a row (the passing print head is enough to trigger):
          1. the BACKGROUND is the median of 7 pictures spread over the last `reference_seconds`: what stays in a place only
             for a moment (print head, hand, reflection) is not part of it;
          2. the average brightness is aligned to the background's (the camera adjusting its exposure is not movement);
          3. if more than `global_change`% of the whole picture changes at once (light, camera moved) the check is ignored, but
             if it lasts more than GLOBAL_STREAK_MAX checks in a row it is a real change;
          4. only what changed against the background, in the outer band of the area, in ALL the last `persist_checks` checks counts.
        It works at half resolution: 4 times fewer points to look at. -> % of the area, or None (nothing to count now).
        """
        now = time.time() if now is None else now
        small = cv2.resize(frame, (OPENCV_WIDTH // 2, OPENCV_HEIGHT // 2), interpolation=cv2.INTER_AREA)
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (11, 11), 0)
        self.stats["frames_checked"] += 1
        if self.ref_small and now - self.ref_small[-1][0] > 2 * self.reference_seconds:
            self._reset_reference()  # a long pause: the old background is no longer valid
        result = None
        if self.bg is not None and self.bg.shape == gray.shape:
            result = self._compare_with_background(gray)
        else:
            self.stats["status"] = "preparing the comparison (%d/%d pictures)" % (len(self.ref_small), REFERENCE_MIN)
        step = max(self.check_interval, self.reference_seconds / REFERENCE_SAMPLES)
        if not self.ref_small or now - self.ref_small[-1][0] >= step:
            self.ref_small.append((now, gray))
            self.ref_jpegs.append((now, raw))
            if len(self.ref_small) >= REFERENCE_MIN:
                self.bg = np.median(np.stack([g for _, g in self.ref_small]), axis=0).astype(np.uint8)
        return result

    def _compare_with_background(self, gray):
        shift = float(gray.mean()) - float(self.bg.mean())
        if abs(shift) > 1:
            gray = cv2.convertScaleAbs(gray, alpha=1.0, beta=-shift)
        thresh = cv2.threshold(cv2.absdiff(self.bg, gray), self.sensitivity, 255, cv2.THRESH_BINARY)[1]
        changed = cv2.countNonZero(thresh) * 100.0 / thresh.size
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
