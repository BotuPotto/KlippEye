# Local model: toolhead covered in its views — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** With a calibrated camera, the local model judges the «bed» and «part» views with the toolhead and gantry covered, so a close camera stops giving false «sure» looks.

**Architecture:** The machine mask the motion detection already builds (`camera_cal.monitor_mask` at `meta["live"]`, `meta["live2"]`) is made at the frame's size, dilated, and filled by `cv2.inpaint` on a reduced picture; `local_judge` gives the covered frame to the «bed»/«part» views and the plain frame to «change». The false-alarm memory's key gains a mark so old embeddings are not matched. `ml/evaluate.py` gets the same cover to measure it on the owner's recordings before release.

**Tech Stack:** Python 3.11, OpenCV 4.6 (`cv2.inpaint`, `cv2.dilate`), numpy; plain-script tests with `check()`.

**Spec:** `docs/superpowers/specs/2026-11-18-local-model-toolhead-mask-design.md`

## Global Constraints

- Calibrated camera only (`camera_cal.usable()` and `camera_cal.saved`, `machine_masks` on); otherwise the views stay as today.
- No new dependency; OpenCV ≤ 2 threads as today; the cover runs once per local look, never per motion check.
- Optional helper fails soft (`except Exception: # a help only`): any error → the uncovered frame.
- Universal: no value tuned to the owner's printer.
- New check names start with `"1.135.0: "`, then `"... "`. VERSION → `1.135.0` (minor: behaviour change).
- Comments in English mark `# 1.135: …`. Talk to the owner in Italian.

## Review Focus

1. Toolhead outside the picture or no live position (`live` None) → mask None → views unchanged, no crash. (Task 2 test.)
2. Mask covers almost all of the «part» crop (first layers: the nozzle is on the part) → the model still gets a picture; inpainting a huge area gives a smooth blur, which must not score high. Measured in Task 4; covered by the stub test only for shape.
3. «change» view must stay uncovered (it already excludes the machine). (Task 2 test.)
4. Purge cover and toolhead cover together: both applied, purge first. (Task 2 test.)
5. Personal layer: trained on uncovered examples, applied to covered views. Shortcut accepted (see Task 2 step 5); the layer's signature is not changed.

---

### Task 1: `machine_masks.cover`

**Files:**
- Modify: `backend/machine_masks.py` (add at the end)
- Test: `tests/backend/test_backend.py` (next to the 1.125 purge checks, ~line 3190)

**Interfaces:**
- Produces: `cover(cv2, np, frame, mask) -> ndarray` — `frame` (BGR, any size) with the points where `mask > 0` (mask any size, uint8) filled from around them; `frame` unchanged; returns `frame` itself when `mask` is None or empty.

- [ ] **Step 1: Write the failing test**

```python
import machine_masks as _mm
_scene = np.full((360, 540, 3), 80, np.uint8)
_scene[100:200, 200:300] = 250                     # a bright «toolhead»
_hole = np.zeros((180, 270), np.uint8); _hole[50:100, 100:150] = 255   # mask at half size
_out = _mm.cover(cv2, np, _scene, _hole)
check("1.135.0: the toolhead is covered by what is around it", abs(int(_out[150, 250, 0]) - 80) < 15 and int(_scene[150, 250, 0]) == 250)
check("... far from it nothing changes", int(_out[20, 20, 0]) == 80 and _out.shape == _scene.shape)
check("... no mask: the same picture", _mm.cover(cv2, np, _scene, None) is _scene)
```

- [ ] **Step 2:** `python3 tests/backend/test_backend.py 2>&1 | grep 1.135` → FAIL (`cover` missing).
- [ ] **Step 3: Implement `cover`.** Resize mask to the frame (INTER_NEAREST), dilate by ~3% of the frame's shorter side (shadow and blur around the box), inpaint (`cv2.INPAINT_TELEA`, radius 3) on the frame reduced to ≤ 320 px wide, resize the inpainted picture back and copy only the masked points into a copy of the frame.
- [ ] **Step 4:** run again → PASS.
- [ ] **Step 5:** commit `"Local model: a helper to cover the machine in a picture (1.135.0)"`.

### Task 2: cover in `local_judge`, memory key

**Files:**
- Modify: `backend/klippeye_backend.py` (`local_views` ~2525, `local_judge` ~2542, `memory_version` ~3203)
- Test: `tests/backend/test_backend.py` (after Task 1's checks)

**Interfaces:**
- Consumes: `machine_masks.cover(cv2, np, frame, mask)`.
- Produces: `LightDetector._without_machine(frame) -> ndarray` (covered frame, or `frame` when no usable calibration / `machine_masks` off / no position / any error). `local_views(frame, now=None, plain=None)`: `plain` = the frame the «change» view is cut from (default `frame`). `memory_version()` ends with `"|th"` when the cover is active.

- [ ] **Step 1: Write the failing tests** (stub `camera_cal.monitor_mask` to return a mask over the toolhead, stub model records the pixel it sees at the toolhead per view, as the 1.125 purge check does):
  - `"1.135.0: the local model sees the bed and the part without the toolhead"` — bed and part views get the inpainted value (≈ background), not 250.
  - `"... the change view keeps the picture as it is"` — change view gets 250.
  - `"... without a toolhead position nothing is covered"` — `meta["live"] = meta["live2"] = None` → all views 250, no exception.
  - `"... the purge is covered too"` — with `_det.purge` from the 1.125 checks, the purge pixel is the empty bed's value.
  - `"... the false-alarm memory knows the toolhead is covered"` — `memory_version().endswith("|th")` with the cover on, not with it off.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement.** `_without_machine`: guard `self.machine_masks and camera_cal.usable() and camera_cal.saved`; mask = `camera_cal.monitor_mask([self.meta.get("live"), self.meta.get("live2")], w // 2, h // 2)`; `machine_masks.cover`. In `local_judge`: `base = self._without_purge(frame) if cover else frame`; `views = self.local_views(self._without_machine(base) if cover else base, now, plain=base)`. `local_views` cuts «change» from `plain`. `memory_version`: append `"|th"` when `detector.machine_masks and camera_cal.usable()`.
- [ ] **Step 4:** run → PASS; also the 1.124/1.125/1.130 local-view checks still pass.
- [ ] **Step 5:** add above `_without_machine`: `# shortcut: the personal layer's examples are not covered (no positions kept with them); cover them when measurements show the layer drifting.`
- [ ] **Step 6:** commit `"Local model: the bed and part views without the toolhead (1.135.0)"`.

### Task 3: measure with the cover (`ml/evaluate.py --cover`)

**Files:**
- Modify: `ml/evaluate.py`
- Test: `ml/tests/test_tools.py`

**Interfaces:**
- Consumes: `machine_masks.cover`; `camera_calibration.CameraCalibration(data_dir, None, None, None, cv2, np).monitor_mask(positions, w, h)`; `labelled_prints.prints_of` pictures `(n, t, path)` — the recording's `frames.jsonl` line holds `live`, `live2`.
- Produces: `--cover` flag: cover the machine (calibration from `--data`) before `--box`. Exit with a message when the calibration is not usable.

- [ ] **Step 1: Failing test** `"1.135.0: evaluate --cover without a calibration says so"` — run `evaluate.py --cover` on the tool tests' tiny data folder → return code 1 and «calibration» in the output.
- [ ] **Step 2:** run `python3 ml/tests/test_tools.py` → FAIL.
- [ ] **Step 3: Implement**: read each picture's `live`/`live2` from the recording's frame lines (extend the picture tuple in `labelled_prints` only if it does not carry the meta: check first), mask at the picture's size, cover, then crop `--box`.
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `"evaluate.py --cover: measure the local model with the machine covered"`.

### Task 4: measure on the owner's prints (gate)

Needs from the owner: `klippeye-data.zip` (PC Downloads) plus newer recordings, and the Pi's calibration file from `~/printer_data/klippeye/` (zip it through the dashboard or SSH key; never ask passwords).

- [ ] **Step 1:** `python3 ml/evaluate.py --model models/base --data <unzipped>/klippeye --box <bed_view> --json before.json` and the same with `--cover --json after.json`.
- [ ] **Step 2:** compare the «monitor» rows. Ship only if false asks on fine prints drop and caught failures do not drop. If they rise, try the flat-colour fill (spec point 2) and measure again; if still no gain, stop and report to the owner.
- [ ] **Step 3:** when the retrained model (`paste-failures`) exists, repeat Step 1 with it; write both in the PR.

### Task 5: release 1.135.0

**Files:** `VERSION`, `CHANGELOG.md`, `docs/FEATURES.md` + `docs/FUNZIONI.md` (local model paragraph), `docs/GUIDE.md` + `docs/GUIDA.md` if they describe the views, `frontend/klippeye_frontend.html` (rebuild), `CLAUDE.md` section 2 point 3 and section 8.

- [ ] **Step 1:** VERSION `1.135.0`; CHANGELOG section (`/humanizer`): with a calibrated camera the local model no longer looks at the toolhead; remembered false alarms are described again once.
- [ ] **Step 2:** docs in English and Italian; `python3 frontend/build.py`; `python3 frontend/tools/i18n.py check`.
- [ ] **Step 3:** `ruff check .`; `bash tests/run_all.sh --no-ui` (backend test in background) → all pass.
- [ ] **Step 4:** commit, push, open the PR with the Task 4 measurements, watch CI, merge when green.
