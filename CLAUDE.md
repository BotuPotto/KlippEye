# KlippEye: notes for Claude

Read this first, every session. It holds the rules, how work is done here, the owner's setup and where each topic
stands. A new chat starts from it: keep it true.

## What KlippEye is

A dashboard and AI print monitor for Klipper printers. It runs on the printer's Raspberry Pi next to Moonraker and
is updated through Moonraker's update manager (git).

- **Backend:** `backend/klippeye_backend.py`, Flask served by waitress, port 8085.
  - The web front on port 80 is nginx, written by `scripts/web_front.py`: uploads and `/websocket` go straight to Moonraker.
- **Notifier:** `notifier/klippeye_notifier.py`, a separate systemd service. It sends phone notifications, and pauses or cancels by itself only when the owner switched that on.
- **Dashboard:** one HTML page, `frontend/klippeye_frontend.html`, built from `frontend/src/` by `python3 frontend/build.py`.
  - The built page is committed, and CI checks it is reproducible.
  - It is translated into 9 languages: `frontend/src/i18n/{it,de,fr,es,pt,pl,ru,uk,zh}.json`, keyed by the English text. Backend messages go through `bt()`.
- **Android app:** `app/`.
- **Install and updates:** `scripts/install.sh`, `scripts/repair.sh`, and the `klippeye` command.

Expected load: one printer and a few phones or computers on the home network. One monitor loop checks the camera every
3 s. Data lives in `~/printer_data/klippeye/`.

## The AI monitor, in one page

- **Motion detection:** `backend/monitor_core.py`, `FrameJudge`. The background is the median of 7 pictures over a minute; it counts only what stays changed over several checks, outside the expected zone of the part (or on the part already printed). The toolhead and the gantry are masked (`machine_masks.py`), and so are the purge marks (`purge_marks.py`).
- **Local model:** MobileNetV3-Small exported to ONNX and run with OpenCV DNN (`backend/local_model.py`), shipped in `models/base/` (`model.onnx`, `model.json` with the threshold, the temperature and the levels, `CREDITS.md`).
  - **Views:** with a calibrated camera it judges the **bed** (not the whole picture), a closer look at the part, and the last change; the highest score counts.
  - **Rules:** two «sure» looks in a row, or three «in doubt», ask the online AI by itself. In the first 5 minutes of a print it takes three «sure» looks, and «in doubt» alone does not ask (1.132).
  - **Levels:** «In doubt from» and «Sure from» follow the model's own levels while the settings are at their defaults, 35 and 80 (`effective_config`).
- **Personal layer** (`personal_layer.py`): a logistic layer on the model's embeddings, trained on the owner's rated prints and labelled recordings.
  - Copies of the examples are kept apart (`personal/kept/`), so deleting recordings loses nothing.
  - It is trained again when the model or the view changes (`personal_stale()`).
- **False-alarm memory** (`false_alarms.py`): the alarms marked «false», and for 6 hours the scenes the online AI called fine.
  - It is keyed by `memory_version()`: the model version plus the view. It is described again after a new model or a calibration change.
- **Online AI:** `call_ai_analysis` asks the chain of services (`ai_services.py`) with `build_ai_prompt`.
  - A PAUSE or CANCEL is looked at again 15 s later on a new picture, by another service when there is one (`confirm_stop`). An answer that cannot be read is never a stop.
  - When the toolhead hides the part, the question is put off.
- **Camera calibration:** `camera_calibration.py` is the flow, `camera_model.py` the maths (fisheye or pinhole, least squares).
  - The «detail» method (1.128): the nozzle tip plus a detail of the toolhead, found by itself. Nothing is printed.
  - `print_zone.py` gives the watched and expected zones.
  - Bed slingers with a frame camera are refused (1.132.3).

## Rules (always)

- **No other printer UIs by name.** Never name or reference other printer web interfaces anywhere: code, comments, commits, PRs, docs, chat.
- **Languages.** Talk to the owner in **Italian**. Code, comments, commits, PR titles and bodies, and docs are in **English**. Every new user-facing string, `bt()` messages included, gets all 9 translations; `python3 frontend/tools/i18n.py check` must pass.
- **Skills.**
  - **`/ponytail` when writing code:** the smallest complete change, no speculative options, one test that fails without the change, and a `shortcut:` comment for any known limit.
  - **`/humanizer` for every text people read:** `CHANGELOG.md`, `README.md`/`LEGGIMI.md`, `docs/`, dashboard strings and their help texts, PR bodies, PR and issue comments. Plain, specific sentences: no inflated claims, no dashes, no filler.
  - **`/ponytail-review` or `/ponytail-audit`** when the owner asks for a review or an audit: findings in plain English, numbered, each with a concrete case.
- **Universality.** KlippEye is for every Klipper printer, not only the owner's.
  - The base model in `models/base/` is trained on **public, varied data only**, with licences that allow sharing the model (`ml/download.py` filters them).
  - The owner's prints go only to the personal layer and to measuring.
  - No text or rule may assume the owner's printer or camera.
- **Secrets.** Never ask the owner for passwords or API keys. The Roboflow key is in Colab's secrets (`ROBOFLOW_API_KEY`). For the Pi, use an SSH key, never a password.
- **Git.**
  - Claude branches, commits, pushes and opens PRs.
  - **Merging:** the owner allowed Claude to merge PRs **once CI is fully green**, in the right order (a stacked PR after the one it is built on). Otherwise say the merge order.
  - No force-push: merge instead.
  - Commit before ending a turn.
  - Commit with `git -c user.name="Claude" -c user.email="noreply@anthropic.com" commit` and end the message with the session's attribution lines.
  - Open a PR with `gh api repos/BotuPotto/KlippEye/pulls --input pr.json`, where pr.json holds title, head, base `main`, and body. End the body with the session's attribution lines, once.
- **CI.** Watch it after every push and fix failures yourself. The «Tests» workflow takes about 1 hour (the «Dashboard in the browser» job is the slow part). A job cancelled because a newer commit replaced it is not a failure.
- **Before saying something works,** run it: tests, a simulation, or a measurement. Say what was not checked.

## How a change is made

1. Branch from `origin/main`, or from the open PR it builds on (say so at the top of the PR body, with the merge order).
2. Make the change and add one test that fails without it (check it fails first when cheap).
3. Bump `VERSION` (patch for a fix, minor for a feature) and add an entry at the top of `CHANGELOG.md`, from the user's point of view.
4. `python3 frontend/build.py`. Commit the page even if only the version changed.
5. Check locally:
   - `ruff check .`
   - `python3 tests/backend/test_backend.py` (about 10 minutes: run it in the background)
   - the tests of the area: `tests/backend/test_personal_layer.py`, `test_calibration_auto.py`, `test_ai_services.py`, `ml/tests/test_tools.py` and so on
   - everything but the browser: `bash tests/run_all.sh --no-ui`
6. Push, open the PR (what and why, how it was measured, the tests), and watch CI until it is green.

## The owner's setup (for measuring, never for the base model)

- **Printer:** a VzBot (CoreXY, Z moves the bed) with a close fisheye camera on the frame. The camera is calibrated with the «detail» method.
- **Pi:** 32-bit Raspberry Pi OS (Bookworm, `getconf LONG_BIT` = 32, Python 3.11, OpenCV 4.6). There is no onnxruntime package for it.
  - Dashboard: `http://raspberrypi.local:8085`.
  - Recordings: `/api/recordings`, `/api/recordings/<id>`, `/api/recordings/<id>/frames/<n>.jpg`.
- **The owner's PC** (Windows) can be linked to a session. Its Downloads folder is `C:\Users\coroz\Downloads` and the built-in browser runs there; Colab is driven from it.
  - `klippeye-data.zip` there holds the owner's judged recordings (16 Nov 2026: 14 prints, 9 fine, 5 failed).
  - To get newer ones, build the zip in the browser from the dashboard's recordings API.
- **Measuring a model on the owner's prints:** `python3 ml/evaluate.py --model <folder> --data <unzipped>/klippeye --box <x,y,w,h> --json out.json`. Read the «monitor» row: it is the monitor's real rule.
  - The bed box is `bed_view` in `GET /api/local_model`; on 16 Nov it was about `0.15,0.36,0.70,0.61`.
  - The current base model (20261116-1408, threshold 0.86, levels 75/86) on the bed: about 1 to 1.5 false asks an hour, and 3 of 4 measurable failures caught.

## Colab (training the base model)

- Free GPU: a T4, limited per day. When it is used up, the runtime is cut, or no GPU is given: wait for the next day.
- Open `https://colab.research.google.com/github/BotuPotto/KlippEye/blob/<branch>/ml/KlippEye_local_model.ipynb` in the built-in browser and confirm «Esegui comunque».
- Add **one-line** code cells: Colab auto-indents typed lines. Press Escape, then `b`, type, then Shift+Enter. Cells queue up, so all the steps can be typed at once.
- Steps:
  1. `!git clone -q https://github.com/BotuPotto/KlippEye -b <branch> && pip install -q -r KlippEye/ml/requirements.txt roboflow huggingface_hub && nvidia-smi -L`
  2. `%cd KlippEye`
  3. `import os; from google.colab import userdata; os.environ["ROBOFLOW_API_KEY"]=userdata.get("ROBOFLOW_API_KEY")`
  4. `!mkdir -p ml/data/bambu-timelapses && cp models/base/bambu-failed.txt ml/data/bambu-timelapses/failed.txt && python ml/download.py --bambu --model '' 2>&1 | tail -20`
  5. `!python ml/datasets.py --auto ml/data --hard-cases 0.3 --paste 0.2 --mine models/base --out ml/work 2>&1 | tail -25`
  6. `!python ml/train.py --manifest ml/work/manifest.csv --out ml/out/model2 --epochs 15 --workers 2 2>&1 | grep -v Warning | tail -40`
  7. Zip `ml/out/model2`, with `ml/data/CREDITS.md` and a contact sheet of 40 pasted pictures (`ml/contact_sheet.py`), then `files.download`. It lands in the Downloads folder, maybe under a `.tmp` name first.
- **Why `--model ''`:** Bambu timelapses are filtered by hand with `failed.txt`; the model-based filter would drop them all.
- **The output is cut by `tail`,** so watch the cell status, not the text.

## Topics

At the end of each piece of work, update the topic's lines below: status, next step, open PRs. Keep only what the
next chat needs.

### Local model (base model training)
- **Status:**
  - `--paste` (public spaghetti pasted on fine pictures, with clean pieces of bed as a counterweight) is on branch `paste-failures`, with no PR yet.
  - `--paste 0.2` gives about 660 + 660 pictures: it is 20% of the about 3,300 whole fine pictures.
  - The 16 Nov run was cut by the GPU quota. A retry was scheduled for 17 Nov 09:00 in the old chat.
- **Next:**
  - Train (Colab above), then measure against `models/base` on the owner's recordings, then look at the contact sheet: pasted pieces must not look fake.
  - Ship in a PR only if better: the new `models/base/*`, `CREDITS.md`, measurements in `models/base/README.md`, and a CHANGELOG entry.
  - If few pasted pictures, raise `--paste`. Distillation only if this is not enough.

### Camera calibration: bed slingers (remind the owner now and then)
- **Status:** 1.132.3 refuses bed slingers with the camera on the frame (`bed_moves_in_y`). A camera on the bed works as before.
- **Plan for real support:**
  1. A new option «the bed moves in Y».
  2. Second set of points: a fixed detail **on the bed** (clip, corner, screw) tapped with the bed at several Y.
     - Maths: `camera_model.fit_offset` with base `(0, -y, 0)`; the unknown offset is where the detail is on the bed.
     - Nozzle points are at `(x, 0, z)`.
  3. After calibration, shift everything on the bed by the current Y: `frame_point`, `print_zone` outlines, the bed box, the part, the local model's bed view. The toolhead masks stay at Y = 0.
  4. A calibration page step, with its 9 translations.
  5. Tests with simulated cameras, like `test_calibration_auto.py`: before, 3 of 8 wrong calibrations were rated «good»; the target is all right.
- It cannot be tried on the owner's printer. A reminder was scheduled for 19 Nov 18:00 in the old chat.

### AI monitor
- **Done:** the audits of 16–17 Nov (1.132.1 to 1.132.5).
- **Known trade-off:** marks outside the parts in the first minutes count as purge and are hidden for the whole print.
- **Not checked yet:** the purge comparison when the bed moves in Z between heating and the start. The 12% cap should switch it off; it was not simulated.

### Open PRs (merge in this order, each once CI is green)
#167 → #168 → #170 (stacked), and #169 (this file) at any time. Update this line when they are merged.
