# KlippEye: notes for Claude

Read this first, every session. It holds what KlippEye is, the rules, how work is done here, the design system, the
owner's setup and where each topic stands. A new chat starts from it with no other memory: keep it true and complete.
The longer documents it points to are the source of detail: `docs/FEATURES.md` (every page and setting),
`docs/GUIDE.md` (how a user installs and uses it), `docs/API.md`, `CONTRIBUTING.md`, `frontend/README.md`,
`frontend/NOTES-it.md` (older design notes, Italian), `ml/README.md`, `tests/README.md`, `android/README.md`,
`CHANGELOG.md` (every release, newest first: the history of all the work).

## 1. What KlippEye is

A dashboard and AI print monitor for **Klipper** printers, made to run on the printer's Raspberry Pi next to
**Moonraker**, for **any** Klipper printer (not only the owner's). Free software, GPL-3.0, public repository
`BotuPotto/KlippEye`. One release number (`VERSION`) for the backend, the dashboard and the notifier.

### The parts

| Part | Where | What it does |
|---|---|---|
| Backend | `backend/klippeye_backend.py` (+ modules in `backend/`) | Flask app served by waitress on **port 8085** (`SERVER_THREADS = 12`). Serves the dashboard, proxies Moonraker's API (`proxy_moonraker`), the camera, the AI monitor, settings, access control (`access.py`), recordings, print reviews, MQTT (`mqtt_bridge.py`), HTTPS relay (`https_relay.py`), printer functions/macros (`printer_macros.py`), the AI services (`ai_services.py`). |
| Web front | `scripts/web_front.py` | Optional nginx site that puts KlippEye on **port 80** (`klippeye web main`); `/websocket` and the file uploads go straight to Moonraker; `restore` gives port 80 back. |
| Notifier | `notifier/klippeye_notifier.py` | Separate systemd service, standard library only. Reads Moonraker and the backend; sends notifications (ntfy, and Firebase for the app); the **automatic pause / cancel** on AI verdicts, only when the owner switched them on (N verdicts in a row, defect filters, once per print). Reads the dashboard's settings from Moonraker's database (namespace `klippeye`). |
| Dashboard | `frontend/src/` → `frontend/klippeye_frontend.html` | One self-contained HTML page (React 18 without JSX, `h()` = `React.createElement`), built by `python3 frontend/build.py` (no npm, no network). Phone layout below 1100 px, desktop layout from 1100 px. |
| Android app | `android/` | A full-screen WebView on the dashboard with push notifications, downloads, addresses (home / VPN), HTTPS pinning, in-app updates. Own version in `android/VERSION`; GitHub builds and publishes the APK into `apk/` (never by hand). |
| Install / update | `scripts/install.sh`, `scripts/repair.sh`, `scripts/klippeye`, `systemd/` | Install once as the normal user (never root); `repair.sh` runs at every start and fixes a damaged install; the `klippeye` command (diagnose, benchmark, web, …). Updates come through **Moonraker's update manager** (git): channel **stable** (tagged releases) or **dev** (every commit of `main`). The service must keep the name `klippeye`. |
| Local model | `models/base/` (+ `ml/` to train it) | MobileNetV3-Small, ONNX, run by OpenCV DNN on the Pi. |
| CI | `.github/workflows/` | `tests.yml` (Tests, ~1 h: backend/notifier/app CI/frontend build, local model training chain, Android compile, install & updates on a simulated Raspberry, dashboard in the browser), `release.yml` (tags `vX.Y.Z` after a merge whose tests pass on main), `app.yml` (APK), `e2e.yml`, `bench-models.yml`. |

On a printer: program in `~/klippeye`, the person's data in `~/printer_data/klippeye/` (settings `monitor.json`,
`ai.json` mode 600 with the AI keys, recordings, alerts, `personal/`, `camera.json`, …). Updates replace only the program.

### What the dashboard does (details: `docs/FEATURES.md`)

Pages on the phone: **Home** (camera, print card, heaters, fans, devices), **Control** (movement, Z-offset, leveling,
bed mesh, input shaper, endstops/probe, extruder, tune, spools/Spoolman, multi-material), **Files** (print files, queue,
scheduled prints, history, maintenance, timelapse, G-code viewer, print checks), **Config** (configuration files, editor
with versions, undo/redo, comment toggling), **System** (host, MCU, services, logs with AI analysis, updates, AI
monitor). Top bar: printer name/logo, AI badge, power menu, save config, emergency stop. **Settings** (side menu): your
printers, printer functions (lights, filament change), macros, motion and Z-offset, materials, camera (several cameras,
calibration), AI monitor (services, thresholds, recordings), notifications (channels, rules), appearance (theme dark /
light / as the device, accent colour, cards and page order), language, addresses, access (password, guest link),
Home Assistant / MQTT, updates, guided set-up. A help button (`HelpButton`) next to settings opens the guide's section.

## 2. The AI monitor (the core; read the code before changing it)

The loop is `LightDetector.loop` in `backend/klippeye_backend.py`: while a **real** print runs (`real_print_check`:
warm-up seconds, minimum progress, hotend at temperature), one check every `check_interval` (3 s):

1. **Motion detection** (`backend/monitor_core.py`, `FrameJudge.judge`): background = median of 7 pictures over
   `reference_seconds` (60 s), brightness aligned, «the whole picture changed» (> `global_change`%) ignored up to 10
   checks; only what changed in **all** the last `persist_checks` checks counts (`_persistent`, a point hidden by the
   toolhead does not break the chain). With a calibrated camera and known objects it watches the whole bed **outside**
   the expected zone of the part, and the part already printed (half weight) (`_zone_score`, `print_zone.py`);
   otherwise the outer band of the watched rectangle. `trigger_count` suspicious checks in a row → trigger, then rest
   `cooldown` s. While the local model has a doubt the thresholds are lower (`boost`).
2. **Masks**: the toolhead and the gantry along their path between the two positions read around the snapshot
   (`machine_masks.py`, needs the calibration); the **purge marks** found by comparing the bed before the print with the
   first real check (`purge_marks.py`; at most 12% of the bed, else not trusted).
3. **Local model** (`_local_look`, `local_judge`, `local_model.py`): views = the **bed** (with a calibrated camera,
   `bed_rect` of `_bed_box`, instead of the whole picture), the **part** (closer look), the last **change** (5 min);
   the highest view's score counts. Purge covered by the empty bed. Looks every `local_every` s by itself and at once on
   a new change. Rules: a motion trigger goes online only if the model is at least «in doubt» (`local_filter`); by
   itself two «sure» in a row, or three «in doubt», ask the online AI; **first 5 minutes of a print** (`LOCAL_WARMUP_S`):
   three «sure», «in doubt» alone does not ask. Online AI off: three «sure» propose a pause (`_local_verdict`).
   Levels: `local_doubt` / `local_sure` follow the model's own levels (`model.json` "levels") while the settings are
   at the defaults 35/80 (`effective_config`).
4. **Personal layer** (`personal_layer.py`, optional `personal_learning`): logistic layer on the embeddings, trained on
   the owner's answers to «How did the print go?» and labelled recordings; copies of the examples kept apart
   (`personal/kept/`, at most 4000, deleting recordings loses nothing); trained again when the model or the view
   changes (`personal_stale`, `personal_view` = the bed at height 0); blended with the base score.
5. **False-alarm memory** (`false_alarms.py`): alarms marked «false» (until forgotten) and scenes the online AI called
   fine **from the start** (6 h; a stop not confirmed is never learned). Keyed by `memory_version()` (model version +
   view): refreshed after a new model or a calibration change (`_view_changed`).
6. **Online AI** (`call_ai_analysis`): the chain of services (`ai_services.py`: Groq, Gemini, OpenAI, Anthropic, Mistral,
   OpenRouter, Meta, Together, Fireworks, any OpenAI-compatible «custom»; backups, per-service quotas/429), prompt `build_ai_prompt` (neutral, says what is and is not a problem, «when in
   doubt CONTINUE», never an empty bed from one picture, JSON only), with the picture of a minute before when allowed.
   A PAUSE/CANCEL is looked at **again** 15 s later on a new picture, by another service when there is one
   (`confirm_stop`; the local model sure on the new picture can hold it). An unreadable answer is never a stop.
   `apply_min_confidence` and `distrust_empty_bed` can downgrade. A question while the toolhead hides the part is put
   off (`_put_off_when_hidden`, the rest starts when it goes). Results → `record_alert` (alert history with pictures,
   the person marks right/false) and `last_analysis` (read by the notifier and the dashboard).
7. **Camera calibration** (`camera_calibration.py` flow, `camera_model.py` maths): pairs (machine point → pixel),
   fisheye or pinhole with radial distortion, DLT start + Levenberg–Marquardt. Methods: «detail» (1.128, Z moves the
   bed: nozzle tip + a detail of the toolhead found by itself, offset solved with the camera, nothing printed) and
   «markers». The camera's moves are watched and corrected (`camera_watch`). **Bed slingers with the camera on the frame
   are refused** (`bed_moves_in_y`, 1.132.3).
8. **Recordings** (`recorder.py`): small pictures + score of every check, for measuring (`scripts/replay.py`,
   `ml/evaluate.py`); size limit `record_max_mb`, oldest deleted first.

## 3. Rules (always)

- **No other printer UIs.** Never name, compare with or reference other printer web interfaces or companion apps
  anywhere: code, comments, commits, PRs, docs, chat with the owner. (Real names of services and repositories that
  KlippEye has to talk to, like a plugin's git address or a systemd service name, are data, not references.)
- **Languages**: talk to the owner in **Italian**. Code, comments, commit messages, PR titles and bodies, logs and docs
  are in **English**. The Italian docs (`docs/GUIDA.md`, `docs/FUNZIONI.md`, `ml/LEGGIMI.md`) are translations of the
  English ones: change both. Every user-facing text gets **all 9 dashboard languages** (`frontend/src/i18n/
  {it,de,fr,es,pt,pl,ru,uk,zh}.json`, keyed by the English text): `tx()` in the dashboard, `bt()` for backend messages,
  `CONFIG_SPEC` labels and help texts too. `python3 frontend/tools/i18n.py check` must pass.
- **Skills**:
  - **`/ponytail`** whenever writing code: the smallest complete change; no speculative options, layers or config;
    reuse what the codebase has; one test that fails without the change; a `shortcut:` comment for a known limit.
  - **`/humanizer`** for every text people read: `CHANGELOG.md`, README/LEGGIMI, `docs/`, dashboard strings and help
    texts, settings notes, PR bodies, PR/issue comments. Plain, specific, short sentences; no inflated claims, no
    dashes as connectors, no filler, no bold labels everywhere.
  - **`/ponytail-review`**, **`/ponytail-audit`** when the owner asks for a review or audit: numbered findings in plain
    English, each with a concrete failing case; «Must fix / Should fix / Nice to have».
- **Universality**: KlippEye is for every Klipper printer. The base model in `models/base/` is trained on **public,
  varied data only**, under licences that let the model be shared (`ml/download.py` drops ShareAlike / NonCommercial /
  NoDerivatives / private ones; `models/base/CREDITS.md` lists the sources). The owner's prints go only to the personal
  layer and to measuring. No text, prompt or default may assume the owner's printer or camera.
- **Lightness on the Pi**: the Pi runs Klipper; KlippEye must never slow it. OpenCV uses at most 2 cores, always one
  left free (`opencv_threads`), the service runs at Nice 10; no new dependency that is not in Raspberry Pi OS's apt
  (32-bit included: onnxruntime is not available there).
- **Secrets**: never ask the owner for passwords or API keys. The Roboflow key is in Colab's secrets
  (`ROBOFLOW_API_KEY`); for the Pi use an SSH key. Never commit keys (the repo is public).
- **Safety of actions**: the printer is real. Nothing that moves it, pauses it or restarts it without the owner asking.
- **Git**: Claude branches, commits, pushes and opens PRs. The owner allowed Claude to **merge PRs once CI is fully
  green**, in the right order (a stacked PR after the one it is built on); otherwise say the merge order. No
  force-push (merge instead). Commit before ending a turn, with
  `git -c user.name="Claude" -c user.email="noreply@anthropic.com" commit`, the message ending with the session's
  attribution lines. Open a PR with `gh api repos/BotuPotto/KlippEye/pulls --input pr.json` (title, head, base `main`,
  body ending once with the attribution lines); merge with
  `gh api -X PUT repos/BotuPotto/KlippEye/pulls/<n>/merge -f merge_method=merge`.
- **CI**: watch it after every push and fix failures yourself. «Tests» takes ~1 h («Dashboard in the browser» is the
  slow job). A job cancelled because a newer commit replaced it is not a failure. A random failure: find why, make
  the test deterministic, do not just rerun.
- **Honesty**: before saying something works, run it (tests, a simulation, a measurement); say what was not checked.

## 4. How a change is made

1. Branch from `origin/main`, or from the open PR it builds on (say so at the top of the PR body, with the merge order).
2. Read the code it touches and its callers; make the change (`/ponytail`); add one test that fails without it (check it
   fails first when cheap). Tests are plain scripts with `check(name, condition, details)`; new check names start with
   the release (`"1.132.4: …"`, then `"... "` for the following ones).
3. Bump `VERSION` (patch for fixes, minor for features) and add a section at the top of `CHANGELOG.md` (`/humanizer`,
   from the user's point of view: what changes for them and why).
4. `python3 frontend/build.py` and commit the page with the sources, even when only the version changed (CI checks the
   committed page equals a rebuild).
5. Check locally: `ruff check .`; `python3 tests/backend/test_backend.py` (~10 min, run it in the background); the
   tests of the area (`tests/backend/test_personal_layer.py`, `test_calibration_auto.py`, `test_ai_services.py`,
   `test_bed_and_shift.py`, `ml/tests/test_tools.py`, `ml/tests/smoke_train.py` needs torch); everything but the
   browser: `bash tests/run_all.sh --no-ui`. Changes to `scripts/`, `systemd/` or updates need `tests/e2e/`.
6. If a page shown in the guides changed, retake the pictures (`tests/ui/docs_screenshots.py`).
7. Push, open the PR (what and why, how it was measured, the tests; `/humanizer`), watch CI until green, merge.

### Code conventions

- Python: standard library first; `numpy`/`cv2` passed in or imported guarded (`HAS_CV2`): the backend starts without
  them. Comments and docstrings in plain English say **why**; a behaviour added in a release is marked with it
  (`# 1.130: …`). Optional helpers fail soft (`except Exception: # a help only`), never in the way of the monitor.
  Writes are atomic (`write_json_atomic`, tmp + `os.replace`), private files mode 600.
- `CONFIG_SPEC` in the backend is read as plain data by the tests' mock server (`ast.literal_eval`): literals only.
- Dashboard JS stays within **ES2020** (Android WebView). Texts in `tx()`; same English word, two meanings: `txc()`.
- ruff settings in `pyproject.toml`.

## 5. Design system (the dashboard; follow it for every new piece)

The look is **Samsung One UI 9, dark**, with the KlippEye logo's colours. Everything comes from the tokens in
`frontend/src/css/00-tokens.css` and a few components; the light page (1.108, `05-light.css`, `<html data-mode=
"light">`) redefines the same tokens. The accent colour can be changed in Settings → Appearance (`accentTokens()`
keeps it readable).

- **Meaning of colour** (the same on every page):
  | Meaning | Look |
  |---|---|
  | selection / active state | soft accent (`--oui-accent-soft`, text `--oui-accent-text`) |
  | main action | filled accent pill (`oui-btn--primary`, dark text `--oui-on-accent`) |
  | neutral action | glass pill (`oui-btn`) |
  | danger | red (`oui-btn--danger`, `--oui-danger-soft`, `oui-tile--danger`) |
  | status | `--oui-ok` / `--oui-warn` / `--oui-danger`; heat `--oui-heat`, cool `--oui-cool` |
- **Surfaces**: translucent «glass» (white at low alpha) over a dark backdrop with pools of the logo's dark violet;
  thin outlines (`--oui-stroke`); cards 28 px radius, tiles 22 px, fields 16 px, rows 8 px, buttons are pills.
  Floating bars (top bar, the floating tab bar) carry the only soft shadow; layers (dialogs, sheets, menus) use blur +
  dim and **no** shadow. Wells (`oui-well`: console, camera, code, previews) are inset and dark on both themes.
- **Colours**: accent `#b79cff` (light violet of the logo), backdrop violet `#7a5cff`. **Never write a colour by hand**:
  use `--oui-*` variables (only the editor's syntax colours are exceptions). Text contrast ≥ 4.5:1 (`--oui-text-3`
  was raised for this).
- **Type**: system font; the wordmark only in Outfit («Klipp» text colour, «Eye» accent); monospace only for console,
  logs, code and technical values; numbers `tabular-nums`; no ALL-CAPS labels; text never under 12 px.
- **Components** (use them, do not invent classes): `Card` (with `cardId` it can fold to its header), `CardHeader`,
  `SectionTitle`, `PageTitle`, `ConfirmDialog`, `Presence`, `Collapse`, `HelpButton`, `Icons.*` (stroke SVG icons)
  in `src/app/20-ui-primitives.js` / `22-motion.js`; CSS components in `15-surfaces.css`, `16-controls.css`:
  `oui-card(--flush, __head)`, `oui-tile(--warn/--danger/--ok)`, `oui-list(__row)`, `oui-well`,
  `oui-btn(--primary/--danger/--danger-soft/--accent-soft/--quiet/--sm/--block/--icon)`, `oui-btn-row`,
  `oui-chip(.is-selected)`, `oui-segmented`, `oui-field(--num)`, `oui-badge(--ok/--warn/--danger/--info)`, `oui-dot`,
  `oui-progress(__bar)`, `oui-check`, `oui-switch`. Settings pages use `SettingsGroup` (title, note, help).
- **Inline styles** only for values that come from data (a bar's width, a level's colour); everything else is a class.
  The compiled Tailwind in `vendor/` keeps only classes in use: a new class with no rule does nothing — write it in
  `src/css/` (the browser tests fail on a class with no rule).
- **Motion** (One UI): one curve `--oui-ease` (quick start, soft landing, no bounce), `--oui-ease-in` for exits,
  linear only for fades; durations 100–500 ms (`--oui-dur-press` 100, `-fast` 150, `-base` 250, `-slow` 350,
  `-exit` 150, `-bar` 450). Layers come in rising and growing (`oui-pop`) and leave faster by the reverse path: every
  new dialog/sheet is wrapped in `Presence` (or is a `ConfirmDialog`). Tab change: the marker slides, cards rise one
  after another (35 ms apart). Only opacity and transforms are animated (plus `Collapse` heights). `prefers-reduced-
  motion` makes every duration 1 ms. Nothing animates at rest (`tests/ui/motion_test.py`).
- **Layouts**: phone below **1100 px** (pages + floating tab bar; never scroll sideways; fits 320–360 px wide: five tabs,
  brand, AI badge and three round buttons); desktop from 1100 px (`useIsDesktop()`, `is-wide`, `desk-*` classes in
  `70-desktop.css`): the same cards arranged in columns, fixed-height pages with columns scrolling on their own, files
  and config with a detail panel / in-page editor, a console bar at the bottom. A change to the phone layout must not
  change the desktop one and vice versa.
- **Texts in the page**: short, plain, the user's words (`/humanizer`); explanations go in a setting's note or the help
  button, not on buttons. Every text in `tx()` with its 9 translations.

## 6. The owner's setup (for measuring and testing, never for the base model)

- Printer: a **VzBot** (CoreXY, Z moves the bed), close **fisheye** camera on the frame, calibrated with the «detail»
  method. Raspberry Pi with **32-bit** Raspberry Pi OS Bookworm (`getconf LONG_BIT` = 32; Python 3.11, OpenCV 4.6),
  dashboard `http://raspberrypi.local:8085`. No onnxruntime package exists for it.
- The owner's **Windows PC** can be linked to the session (desktop app). Downloads folder: `C:\Users\coroz\Downloads`.
  The **built-in browser** runs there: it drives Colab and can open the Pi's dashboard (each site needs the owner's
  approval). `klippeye-data.zip` there holds the owner's judged recordings (16 Nov 2026: 14 prints, 9 fine, 5 failed);
  newer ones can be zipped from the dashboard's recordings API (`/api/recordings`, `/api/recordings/<id>`,
  `/api/recordings/<id>/frames/<n>.jpg`) with a small script run in the page.
- Measuring a model on the owner's prints: `python3 ml/evaluate.py --model <folder> --data <unzipped>/klippeye
  --box <x,y,w,h> --json out.json`; read the **«monitor»** row (the monitor's real rule). The bed box is `bed_view` in
  `GET /api/local_model` (about `0.15,0.36,0.70,0.61` on 16 Nov). Current base model **20261116-1408** (threshold 0.86,
  temperature 2.67, levels 75/86): on the bed about 1–1.5 false asks an hour, 3 of 4 measurable failures caught
  (one failed print has no pictures after the failure).

## 7. Colab (training the base model)

- Free GPU (T4) limited per day: when used up the runtime is cut or no GPU is given → wait for the next day.
- In the built-in browser open `https://colab.research.google.com/github/BotuPotto/KlippEye/blob/<branch>/ml/KlippEye_local_model.ipynb`,
  confirm «Esegui comunque». Add **one-line** code cells (Colab auto-indents typed lines): Escape, `b`, type,
  Shift+Enter; cells queue, so all steps can be typed at once. Outputs cut by `tail` show only at the end.
  1. `!git clone -q https://github.com/BotuPotto/KlippEye -b <branch> && pip install -q -r KlippEye/ml/requirements.txt roboflow huggingface_hub && nvidia-smi -L`
  2. `%cd KlippEye`
  3. `import os; from google.colab import userdata; os.environ["ROBOFLOW_API_KEY"]=userdata.get("ROBOFLOW_API_KEY")`
  4. `!mkdir -p ml/data/bambu-timelapses && cp models/base/bambu-failed.txt ml/data/bambu-timelapses/failed.txt && python ml/download.py --bambu --model '' 2>&1 | tail -20`
  5. `!python ml/datasets.py --auto ml/data --hard-cases 0.3 --paste 0.2 --mine models/base --out ml/work 2>&1 | tail -25`
  6. `!python ml/train.py --manifest ml/work/manifest.csv --out ml/out/model2 --epochs 15 --workers 2 2>&1 | grep -v Warning | tail -40`
  7. zip `ml/out/model2` with `ml/data/CREDITS.md` and a contact sheet of 40 pasted pictures (`ml/contact_sheet.py`),
     then `files.download` → it lands in the Downloads folder (maybe first under a `.tmp` name).
- `--model ''`: Bambu timelapses are filtered by hand (`failed.txt`, from `models/base/bambu-failed.txt`).
- The data chain: `download.py` (Roboflow datasets of `ml/sources.json` + Bambu timelapses on Hugging Face, licence
  filter) → `datasets.py` (manifest with weights; `--hard-cases` draws purge lines/blobs/strands/brims on fine pictures;
  `--paste` pastes public spaghetti and clean bed pieces; `--mine` weighs the current model's mistakes) → `train.py`
  (MobileNetV3-Small, temperature scaling baked into the head, threshold for ≤3% false alarms, levels, ONNX tidied for
  OpenCV 4.6) → `evaluate.py`.

## 8. Topics (status; update at the end of each piece of work)

### Local model (base model training)
- `--paste` (public spaghetti on fine pictures + clean bed pieces as counterweight) is on branch `paste-failures`, no
  PR yet. `--paste 0.2` gives ~660 + 660 pictures (20% of ~3,300 whole fine pictures).
- The 16 Nov run was cut by the GPU quota; a retry was scheduled for 17 Nov 09:00 in the old chat.
- **Next**: train (section 7) → measure against `models/base` on the owner's recordings → look at the contact sheet
  (pasted pieces must not look fake) → ship only if better (new `models/base/*`, `CREDITS.md`, measurements in
  `models/base/README.md`, CHANGELOG). Few pasted pictures → raise `--paste`. Distillation only if not enough.

### Camera calibration: bed slingers (remind the owner now and then)
- 1.132.3 refuses bed slingers with the camera on the frame (`bed_moves_in_y`); a camera on the bed works.
- **Plan**: (1) option «the bed moves in Y»; (2) second set of points = a fixed detail **on the bed** (clip, corner,
  screw) tapped with the bed at several Y: `camera_model.fit_offset` with base `(0, -y, 0)` (the unknown offset is where
  the detail is on the bed), nozzle points at `(x, 0, z)`; (3) after calibration shift everything on the bed by the
  current Y (`frame_point`, `print_zone` outlines, bed box, part, the local model's bed view); toolhead masks at Y = 0;
  (4) a calibration page step + 9 translations; (5) tests with simulated cameras like `test_calibration_auto.py`
  (before: 3 of 8 wrong calibrations rated «good»; target: all right). Cannot be tried on the owner's printer.
  A reminder was scheduled for 19 Nov 18:00 in the old chat.

### AI monitor
- Audited 16–17 Nov (releases 1.132.1–1.132.5): personal view at height 0, logs path test, false alarms follow the
  calibration, embedding cache trimmed, bed slingers refused, unconfirmed stops not learned, put-off questions not
  lost, prompt for every camera, exposure shift keeps blacks.
- Known trade-off: marks outside the parts in the first minutes count as purge and are hidden for the whole print.
- Not checked yet: the purge comparison when the bed moves in Z between heating and the start (the 12% cap should
  switch it off; not simulated).

### Open PRs
#168 → #170 (stacked) and #169 (this file), merged in this order once green. Update this line when merged.
