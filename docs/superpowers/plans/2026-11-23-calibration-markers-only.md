# Calibration: markers only, draggable bed corners Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the automatic «detail» camera calibration, leave «markers» (the 6 blobs of filament) as the only method, and let the person drag the four corners of the watched bed on the live picture.

**Architecture:** Task 1 deletes the «detail» method from the backend and its tests; old drafts and saved calibrations with `method: "detail"` are read as invalid and must be redone. Task 2 removes the method step and the detail texts from the dashboard, i18n and docs. Task 3 adds the inverse projection and a route that sets the bed from a dragged corner, plus the dots. Task 4 pins that an adaptive mesh never narrows the bed.

**Tech Stack:** Python (Flask backend, plain-script tests with `check(name, condition, details)`), React without JSX (`h()`), `python3 frontend/build.py`, Playwright UI tests.

**Spec:** `CLAUDE.md` section 8, «Owner's notes of 23 Nov», group 2 (on branch `notes-camera-and-ci`, PR #185). Repo root: the repository checkout (branch `calibration-markers-only`, from `guide-cleanup-1-135-1`).

## Global Constraints

- Code, comments, commits, docs in English; every new `tx()` text gets all 9 languages (`frontend/src/i18n/{it,de,fr,es,pt,pl,ru,uk,zh}.json`, keyed by the English text, `json.dumps(ensure_ascii=False, indent=1, sort_keys=True)` plus a trailing newline); texts removed from the page are removed from the 9 files; `python3 frontend/tools/i18n.py check` must pass.
- Docs are paired: `docs/GUIDE.md` and `docs/GUIDA.md` change together. Texts follow `/humanizer`.
- Never name other printer UIs. Dashboard JS stays ES2020. Never write a colour by hand: use `--oui-*` variables; a new CSS class needs a rule in `frontend/src/css/`.
- Writes of settings files go through `atomic.write_text` / `_write_json`.
- New test check names start with the release: `"1.136.0: …"`.
- Release: `VERSION` 1.136.0, a section at the top of `CHANGELOG.md`, `python3 frontend/build.py` and commit the page.
- `bed slingers with the camera on the frame are refused` stays as it is.
- No change to the monitor's behaviour without calibration (needs measuring first; out of this plan).

## Review Focus

- A draft or saved calibration with `method: "detail"` on disk: loading must not crash; the person is asked to calibrate again.
- A printer where Z moves the bed: `method()` must give `"markers"`, never None, so the flow still starts.
- A dragged corner that crosses the opposite one or makes the bed under `BED_MIN_MM` (20): refused with the existing `ShapeError`, the old bed kept.
- A corner dragged to a pixel above the horizon or behind the camera (no point on the bed plane): refused, nothing saved.
- A bed mesh that covers only the printed part (adaptive): the bed must not shrink to it.

---

### Task 1: Remove the «detail» method from the backend

**Files:**
- Modify: `backend/camera_calibration.py` (`METHODS`, `DETAIL_Z`, `target_list`, `detail_path`, `method`, `set_options`, `reset`, `add_point`, `template_path`/`template_png`, `can_find`, `find_tip`, `find_all`, `fit`, `overlay`, `summary`)
- Modify: `backend/camera_model.py` (remove `fit_offset` if nothing else uses it)
- Modify: `backend/klippeye_backend.py` (`/api/camera/calibration/options`, `/api/camera/calibration/template/<kind>`)
- Test: `tests/backend/test_calibration_auto.py`, `tests/backend/test_backend.py`

**Interfaces:**
- Produces: `METHODS = ("markers",)`; `CameraCalibration.method() -> str` always `"markers"`; no `detail_template`, `saved.offset`, `overlay["detail"]`, `targets[].kind == "detail"` anywhere in the API replies.

- [ ] **Step 1: Write the failing tests.** In `test_calibration_auto.py`: `"1.136.0: Z moves the bed: the method is markers"` (`set_options({"z_moves": "bed"})` then `method() == "markers"`); `"1.136.0: method detail is refused"` (`set_options({"method": "detail"})` raises); `"1.136.0: an old draft with method detail is read as markers, points dropped"` (write a draft JSON with `"method": "detail"` and some points, reload, `method() == "markers"`, no `kind: "detail"` points kept); `"1.136.0: a saved calibration with method detail is not usable"` (`usable()` false). In `test_backend.py`: the API refuses `{"method": "detail"}` with 400 and `GET /api/camera/calibration/template/detail` gives 404.
- [ ] **Step 2: Run them, expect FAIL.** `python3 tests/backend/test_calibration_auto.py`.
- [ ] **Step 3: Implement.** Delete every «detail» path listed under Files; keep the nozzle template. Where a draft or saved calibration is loaded, a stored `method` other than `"markers"` makes the draft drop its points and the saved calibration unusable (find the loader that already validates saved data and reuse it). `fit()` keeps only the nozzle/marker branch.
- [ ] **Step 4: Remove the old detail checks** in the two test files (the `1.128` and the detail ones in `test_calibration_auto.py` lines ~186-254) and run both files, `ruff check .`: all pass.
- [ ] **Step 5: Commit** `1.136.0: remove the detail calibration method (backend)`.

### Task 2: Remove the «detail» method from the dashboard, texts and docs

**Files:**
- Modify: `frontend/src/app/59f-camera-calibration.js` (`MethodStep` and its call at ~884, `detailWay`, `needsMarks`, `firstDetail`, the detail instructions, `[data-detail-help]`, `[data-detail-ref]`, the hint drawing, the `AutoFind` strings, the overlay's detail cross and note)
- Modify: `frontend/src/i18n/*.json` (remove the strings no longer used; `python3 frontend/tools/i18n.py check`)
- Modify: `docs/GUIDE.md` (~278-296), `docs/GUIDA.md` (~288-304)
- Test: `tests/ui/camcal_test.py` (lines ~167-180), `tests/ui/mock_server.py` if it serves detail data
- Modify: `VERSION` (1.136.0), `CHANGELOG.md`, rebuild `frontend/klippeye_frontend.html`

**Interfaces:**
- Consumes: Task 1's API (no `method` choice, no `detail_template`).
- Produces: the calibration flow always shows the markers steps; no method chips.

- [ ] **Step 1: Update `camcal_test.py` first:** replace the four `1.128` checks by `"1.136.0: no method step: the markers flow starts"` and `"1.136.0: no text about a detail of the toolhead on the page"` (page text has no «detail of the toolhead»). Run, expect FAIL.
- [ ] **Step 2: Implement** the removals; the flow for a bed-moves-Z printer is the markers flow (6 blobs).
- [ ] **Step 3: Docs:** rewrite the Camera calibration steps in both guides so only the markers (blobs) way is described; remove «recommended detail method» text.
- [ ] **Step 4: CHANGELOG 1.136.0** (from the user's point of view: the no-print method is gone, why: it was unreliable; whoever used it calibrates again with the markers), VERSION, build.
- [ ] **Step 5: Verify:** `python3 frontend/build.py`, `python3 frontend/tools/i18n.py check`, `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 tests/ui/camcal_test.py` (path as `tests/ui/run_all.sh` calls it) pass.
- [ ] **Step 6: Commit** `1.136.0: remove the detail calibration method (dashboard, texts, guide)`.

### Task 3: Draggable bed corners

**Files:**
- Modify: `backend/camera_model.py` (add `unproject_to_plane`)
- Modify: `backend/camera_calibration.py` (add `set_bed_corner`), `backend/klippeye_backend.py` (route `POST /api/camera/bed_corner`), `backend/camera_calibration.py` `overlay()` (add `overlay["bed_corners"]`: `{"x0y0": [u, v], "x1y0": …, "x1y1": …, "x0y1": …}` fractions of the picture, same frame as `overlay["bed"]`)
- Modify: `frontend/src/app/59f-camera-calibration.js` (a `BedCorners` dots layer like `ShapeHandles`, shown when a calibration is saved), `frontend/src/css/` (rule for the dot class, reuse `cal-handle` look), 9 i18n files for any new text
- Test: `tests/backend/test_bed_and_shift.py`, `tests/ui/camcal_test.py`

**Interfaces:**
- Produces: `camera_model.unproject_to_plane(calibration, u: float, v: float, z: float) -> tuple[float, float] | None` (machine X, Y on the horizontal plane at height `z` mm for the picture point `(u, v)` in 0..1 fractions; None when the ray does not reach the plane in front of the camera); `CameraCalibration.set_bed_corner(corner: str, u: float, v: float) -> list` (corner is one of `"x0y0"`, `"x1y0"`, `"x1y1"`, `"x0y1"`; moves that corner's X and Y edge, keeps the other two, stores through the same path as `set_shape({"bed": …})`, returns the new area; raises `machine_masks.ShapeError` when too small or crossed, `ValueError` when no point); route replies `{"ok": true, "bed": area}` or 400 with the message.
- Dragging a dot sends at most every 400 ms (`SHAPE_SEND_EVERY_MS`) and on release, like `ShapeHandles`; the − and + steps of `BedArea` stay.

- [ ] **Step 1: Failing tests** (names start `"1.136.0: "`): `unproject_to_plane` is the inverse of `project` for a simulated camera (reuse the one in `test_calibration_auto.py`) within 1 mm at bed z; a point above the horizon returns None; `set_bed_corner("x1y1", u, v)` of the projected corner (+10 mm in X) widens X max by 10 mm within 1 mm and leaves the others; crossing the opposite corner raises `ShapeError` and the stored bed is unchanged; the route gives 400 for an unknown corner. UI: four `[data-bed-corner]` dots exist on the live picture of a saved calibration, and dragging one by 20 px posts to `/api/camera/bed_corner`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** the signatures above (least squares not needed: intersect the camera ray with the plane using the model's own unprojection; reuse `_unproject_guess` and the lens model in `camera_model.py`).
- [ ] **Step 4: Texts:** aria-label for the dots «Bed corner» (9 languages), one line in the guide step «Bed area» in both guides saying the corners can be dragged.
- [ ] **Step 5: Run** the two backend files, the UI test, `ruff check .`, build and `i18n.py check`. CHANGELOG 1.136.0 gets a line.
- [ ] **Step 6: Commit** `1.136.0: drag the corners of the watched bed`.

### Task 4: An adaptive mesh never narrows the bed

**Files:**
- Test: `tests/backend/test_bed_and_shift.py`
- Modify (only if the test fails): `backend/camera_calibration.py` `bed_from_mesh`

**Interfaces:**
- Consumes: `bed_from_mesh(settings, travel=None)` reads Klipper's configured `[bed_mesh]` (`mesh_min`/`mesh_max`), not the per-print mesh.

- [ ] **Step 1: Test** `"1.136.0: the bed ignores the mesh of the current print (adaptive)"`: `settings` with `bed_mesh` min/max for the full bed and a live status of a small adaptive mesh in a `printer` stub; `bed_area()` is the configured area plus 10 mm. Run: expected PASS already (the code reads settings only); if it passes keep it as a pin, otherwise fix `bed_from_mesh`.
- [ ] **Step 2: Commit** `1.136.0: pin that adaptive meshes do not narrow the bed`.

### Final

Run `bash tests/run_all.sh --no-ui` and the UI tests of Tasks 2 and 3, push, open the PR (body ends once with the attribution lines).
