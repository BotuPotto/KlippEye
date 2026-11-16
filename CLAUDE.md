# KlippEye: notes for Claude

KlippEye is a dashboard and AI print monitor for Klipper printers. It runs on the printer's Raspberry Pi next to Moonraker.
- **Backend:** Flask/waitress in `backend/`.
- **Notifier:** `notifier/`.
- **Dashboard:** one HTML page built from `frontend/src/`.
- **Android app:** `app/`.
- **Local model:** MobileNetV3-Small run with OpenCV DNN on the Pi, trained with the tools in `ml/`.

Expected load: one printer, a few devices on the home network. The Pi is often a 32-bit Raspberry Pi OS with OpenCV 4.6 (Bookworm), so no onnxruntime there.

## Rules (always)

- **No other printer UIs by name.** Never name or reference other printer web interfaces anywhere: code, comments, commits, PRs, docs.
- **Languages:** talk to the owner in **Italian**. Code, comments, commits, PR titles and bodies, and docs are in **English**. The dashboard is translated into 9 languages (`frontend/src/i18n/*.json`): every new user-facing string, backend messages passed through `bt()` included, needs all 9.
- **Universality:** the base model in `models/base/` is trained on public, varied data only. The owner's prints go only to the per-printer personal layer and to measuring.
- **Secrets:** never ask the owner for passwords or API keys. Use an SSH key, or Colab secrets.
- **Git:**
  - Claude branches, commits, pushes and opens PRs. **The owner merges.** Always state the merge order of stacked PRs.
  - No force-push: merge instead.
  - Commit before ending a turn.
  - Commit with `git -c user.name="Claude" -c user.email="noreply@anthropic.com"` and end the message with the attribution lines of the session.
- **CI:** watch it after every push and fix failures. The "Tests" workflow takes about 1 hour (the dashboard browser tests are the slow part).

## How a change is made

1. Branch from `origin/main`, or from the PR it builds on (say so in the PR body).
2. Make the smallest complete change and add one test that fails without it.
3. Bump `VERSION` (patch for fixes, minor for features) and add an entry at the top of `CHANGELOG.md`, in plain English, from the user's point of view.
4. Rebuild the page: `python3 frontend/build.py`. CI checks the committed page is reproducible.
5. Check locally:
   - `ruff check .`
   - `python3 tests/backend/test_backend.py` (about 10 minutes; run it in the background)
   - the specific test file of the area: `test_personal_layer.py`, `test_calibration_auto.py`, `ml/tests/test_tools.py` and so on
   - `python3 frontend/tools/i18n.py check` when strings changed
   - everything at once: `bash tests/run_all.sh --no-ui`
6. Push, open the PR, and watch CI until it is green.

## Where things are

- **Monitor loop:** `LightDetector.loop` and `_local_look` in `backend/klippeye_backend.py`.
- **Motion detection:** `backend/monitor_core.py` (`FrameJudge`).
- **Local model:** `backend/local_model.py`, `backend/personal_layer.py`, `backend/false_alarms.py`.
  - The false-alarm memory is keyed by `memory_version()`: model version plus view.
- **Camera calibration:**
  - `backend/camera_model.py`: the camera's maths.
  - `backend/camera_calibration.py`: the flow.
  - `backend/print_zone.py`: the zones.
  - `backend/machine_masks.py`, `backend/purge_marks.py`: the toolhead masks and the purge marks.
- **AI prompt:** `build_ai_prompt` in `backend/klippeye_backend.py`.
- **ML chain:** `ml/download.py` → `ml/datasets.py` → `ml/train.py` → `ml/evaluate.py`. The Colab notebook is `ml/KlippEye_local_model.ipynb`.

## Topics

Work on **one topic per session**. At the end of a session, update the topic's lines below: status, next step, open PRs. Put nothing else in this file.

### Local model (base model training)
- **Status:**
  - The data chain has `--paste`: public spaghetti pasted on fine pictures, with clean pieces of bed as a counterweight. It is on branch `paste-failures`, with no PR yet.
  - The last Colab run was cut off because the free GPU quota was used up.
- **How to train:**
  - Open the notebook from the `paste-failures` branch on Colab with a GPU.
  - `git clone -b paste-failures`
  - `ROBOFLOW_API_KEY` from the Colab secrets.
  - `cp models/base/bambu-failed.txt ml/data/bambu-timelapses/failed.txt` before `python ml/download.py --bambu --model ''`.
  - `python ml/datasets.py --auto ml/data --hard-cases 0.3 --paste 0.2 --mine models/base --out ml/work`
  - `python ml/train.py --manifest ml/work/manifest.csv --out ml/out/model2 --epochs 15`
- **Next:**
  - Measure the new model against `models/base` with `ml/evaluate.py --box <bed box>` on the owner's recordings (the «monitor» row). Ship it only if better.
  - If `--paste 0.2` gives few pictures, raise it.
  - Distillation only if this is not enough.

### Camera calibration: bed slingers
- **Status:** 1.132.3 refuses bed slingers with the camera on the frame (`bed_moves_in_y`). A camera on the bed works.
- **Plan for real support:**
  1. A new option «the bed moves in Y».
  2. Second set of points: a fixed detail **on the bed** (clip, corner, screw) tapped with the bed at several Y. The maths is `camera_model.fit_offset` with base `(0, -y, 0)`; the unknown offset is where the detail is on the bed. Nozzle points are at `(x, 0, z)`.
  3. After calibration, shift everything on the bed by the current Y: `frame_point`, `print_zone` outlines, the bed box, the part, the local model's bed view. The toolhead masks stay at Y = 0.
  4. A calibration page step, with its 9 translations.
  5. Tests with simulated cameras (as in `test_calibration_auto.py`): all calibrations right.
- It cannot be tried on the owner's printer (a VzBot, Z moves the bed).

### AI monitor: audit leftovers
- **To do:**
  - `build_ai_prompt` says «The camera is fixed, very close and above the bed, in a corner». Make it general: «The camera is fixed; the print head, its cables and parts of the gantry may appear in the picture».
  - `monitor_core.py:342`: `convertScaleAbs` mirrors dark pixels after an exposure shift. Use `cv2.subtract` / `cv2.add`.
- **Known trade-off:** marks outside the parts in the first minutes count as purge and are hidden for the whole print.

### Open PRs (merge in this order)
#166 → #167 → #168, each built on the one before.
