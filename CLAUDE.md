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
| Web front | `scripts/web_front.py` | Optional nginx site that puts KlippEye on **port 80** (`klippeye web main`); `/websocket` and the file uploads go straight to Moonraker after nginx asks KlippEye (`auth_request` to `/api/auth/check`, 1.133.1: password and guests); `restore` gives port 80 back. |
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

### Backend modules (`backend/`)

| Module | What it is |
|---|---|
| `klippeye_backend.py` | the service: settings (`CONFIG_SPEC`, `MonitorConfig`), access guard, Moonraker proxy, all `/api/*` routes, the monitor (`LightDetector`), `LocalAi`, startup |
| `access.py` | optional password, signed tokens, guest role, host and origin checks |
| `ai_services.py` | the online AI services (Groq, Gemini, OpenAI, Anthropic, Mistral, OpenRouter, Meta, Together, Fireworks, custom), keys, chains, model lists |
| `ai_precision.py` | how often the AI's verdict matched the real state of the print |
| `monitor_core.py` | `FrameJudge`: the motion detection (also used by `scripts/replay.py`) |
| `local_model.py` | the local model (OpenCV DNN) |
| `personal_layer.py`, `labelled_prints.py` | the per-printer layer and the prints the person judged |
| `false_alarms.py` | the false-alarm memory |
| `recorder.py`, `print_review.py` | recordings of the monitor; «How did the print go?» |
| `camera_calibration.py`, `camera_model.py`, `camera_watch.py`, `camera_markers.py`, `nozzle_finder.py`, `homing_safety.py` | camera calibration: flow, maths, «has the camera moved», printed markers, finding the nozzle tip, homing with markers on the bed |
| `print_zone.py`, `machine_masks.py`, `purge_marks.py` | watched / expected zones, toolhead and gantry masks, purge marks |
| `camera_snapshot.py` | where the single photo is taken from |
| `moonraker_live.py` | one live connection to Moonraker |
| `printer_macros.py`, `macro_catalog.py`, `printer_lights.py` | the macros KlippEye writes (`klippeye_macros.cfg`), the printer's macros with parameters, the lights |
| `printer_paths.py`, `printers_peek.py` | where the printer keeps its files; other printers |
| `config_versions.py` | earlier versions of the config files |
| `print_schedule.py` | prints that start at a chosen time |
| `shaper_data.py`, `shaper_fit.py` | input shaper results and fitting |
| `notify_channels.py` | the notification channels (ntfy topic, …) |
| `mqtt_bridge.py`, `mqtt_client.py` | Home Assistant / MQTT (standard-library client) |
| `https_relay.py` | the optional HTTPS entrance |
| `atomic.py` | the one safe way to write a file (1.133.1) |

**Rules written twice (change both)**:
- `backend/printer_lights.py` ↔ `frontend/src/app/13-capabilities.js` (`deriveParts`);
- `backend/camera_snapshot.py` ↔ `frontend/src/app/16-settings.js` (the default snapshot);
- `--oui-dur-exit` in `00-tokens.css` ↔ `LAYER_EXIT_MS` in `app/22-motion.js`;
- `CONFIG_SPEC` (backend) ↔ its translations and the settings page (`59a-detector-settings.js`).

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
   changes (`personal_stale`, `personal_view` = the bed at height 0); blended with the base score at weight `BLEND`
   0.25 (1.134.3; it grew to 0.6 before, and at 0.4+ the monitor stopped asking about real failures).
5. **False-alarm memory** (`false_alarms.py`): alarms marked «false» (until forgotten) and scenes the online AI called
   fine **from the start** (10 min since 1.134.3, 6 h before; a stop not confirmed is never learned). Keyed by `memory_version()` (model version +
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
- **Graphify (code graph)**: at the start of a session check whether the Graphify tools are available
  (`list_repositories`). When `BotuPotto/KlippEye` is indexed and queryable, use them for the code's structure before
  grep or reading whole files: `graphify_find` (where a symbol is), `graphify_callers`, `graphify_impact`
  (with `include_risk=true` before a change: what it affects and which tests cover it), `graphify_tests_for`,
  `graphify_file_neighbors` (a file's dependencies and the dashboard pages calling a route), `query_graph`
  (`skeleton=true` to locate cheaply). Each answer carries `commitSha`: equal to `git rev-parse HEAD` → trust it;
  otherwise read the files changed since. Use plain text search for literal strings, config values and translations.
  `recall` / `remember` keep durable notes for the workspace when memory is enabled (empty on 17 Nov 2026); the Free
  plan indexes only README.md among the documents, so this file is not in the graph.
- **Universality**: KlippEye is for every Klipper printer. The base model in `models/base/` is trained on **public,
  varied data**, under licences that let the model be shared (`ml/download.py` drops ShareAlike / NonCommercial /
  NoDerivatives / private ones; `models/base/CREDITS.md` lists the sources). Since 1.135.0 (the owner's choice, 23 Nov:
  he is the only user for now) 10 of the owner's judged prints are in its training too; 9 others stay kept out for
  measuring and must never be trained on. No text, prompt or default may assume the owner's printer or camera.
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
   Cloud sessions: use the personal environment «KlippEye» (17 Nov); its setup script installs OpenCV, Flask, Pillow
   and `playwright==1.63.0` (the version of the Chromium in `/opt/pw-browsers`). Run the browser tests with
   `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers bash tests/ui/run_all.sh`. `settings_test` «a stream that does not
   come» fails in the container on main too (the stream address does not answer the same way there); CI passes it.
6. If a page shown in the guides changed, retake the pictures (`tests/ui/docs_screenshots.py`).
7. Push, open the PR (what and why, how it was measured, the tests; `/humanizer`), watch CI until green, merge.

### Code conventions

- Python: standard library first; `numpy`/`cv2` passed in or imported guarded (`HAS_CV2`): the backend starts without
  them. Comments and docstrings in plain English say **why**; a behaviour added in a release is marked with it
  (`# 1.130: …`). Optional helpers fail soft (`except Exception: # a help only`), never in the way of the monitor.
  Writes are atomic: `atomic.write_text` (`backend/atomic.py`: own temp name, fsync, `os.replace`; `write_json_atomic` uses
  it), private files mode 600. Never a plain `open(path, "w")` on a file that holds settings or labels.
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
  thin outlines (`--oui-stroke`); radii (1.133): cards 28 px, tiles 22 px, fields 16 px, small boxes 12 px, rows 8 px,
  bars and chart marks 3 px, buttons are pills; no other value (the previews of the other looks in Appearance excepted).
  Floating bars (top bar, the floating tab bar) carry the only soft shadow; layers (dialogs, sheets, menus) use blur +
  dim and **no** shadow. Wells (`oui-well`: console, camera, code, previews) are inset and dark on both themes.
- **Colours**: accent `#b79cff` (light violet of the logo), backdrop violet `#7a5cff`. **Never write a colour by hand**:
  use `--oui-*` variables (only the editor's syntax colours are exceptions). Text contrast ≥ 4.5:1 (`--oui-text-3`
  was raised for this).
- **Type**: system font; the wordmark only in Outfit («Klipp» text colour, «Eye» accent); monospace only for console,
  logs, code and technical values; numbers `tabular-nums`; no ALL-CAPS labels; text never under 12 px
  (`a11y_test.py` checks every page and menu page). Sizes (1.133): 12, 13, 14, 15, 17, 20, 24, 28, 34, 48 px only;
  form fields stay 16 px (iOS zooms on a smaller one). Still to do: 9 `text-transform: uppercase` labels in the CSS.
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
- **Motion** (1.134, chosen by the owner after demos: «Mac» feel, the current look): things that arrive or move use
  the spring `--oui-spring` (`linear()` of a spring, response 0.55 s, damping 0.8: a barely visible bounce) over
  `--oui-dur-spring` 550 ms; `--oui-ease` (no bounce) stays for small changes and is the spring's fallback;
  `--oui-ease-in` for exits; linear only for fades; durations 100–550 ms (`--oui-dur-press` 100, `-fast` 150, `-base`
  250, `-slow` 350, `-exit` 150, `-bar` 450, `-spring` 550). Dialogs grow out of the tapped point (`oui-pop` from
  scale 0.6; a MutationObserver in `app/22-motion.js` sets their transform-origin) and shrink back into it; every new
  dialog/sheet is wrapped in `Presence` (or is a `ConfirmDialog`). Tab change: the marker slides, the new page's cards
  come from the side of the tab (`--oui-page-dx`) one after another (35 ms apart). Home's cards slide to new places
  (`useCardMorph`, keyed by `data-slot`). 1.134.1: the side menu, its pages and rows, and `Collapse` use the spring
  too; a folded card animates its height (`Card` + `foldCard` in `app/20-ui-primitives.js`: the height at the
  chevron's tap → the new one, content kept by `is-folding` while it folds, folding at half the spring's time).
  1.134.2: the full-screen camera, console and photo grow from the tap like dialogs (`GROW_FROM_TAP` in
  `app/22-motion.js`); the guide / AI panel (`.help-overlay`, `.help-sheet`) and the guided set-up enter and leave like
  the other layers; the notification invite and the connection strip slide in. Every layer added since must get an
  enter rule and a `[data-presence="leaving"]` rule in `css/22-motion.css` (`motion_test.py` checks a few of them).
  Only opacity and transforms are animated, plus `Collapse` heights and a card's fold.
  `prefers-reduced-motion` makes every duration 1 ms. Nothing animates at rest (`tests/ui/motion_test.py`).
  Rejected by the owner: a view of all pages at once, full redesigns (three demos, 17 Nov), Dock magnification.
- **Home follows the moment** (1.134, phone only): `homeMoment` (alarm / pause / heat / print / idle) and
  `HOME_MOMENTS` in `app/99-main.js` filter the cards; the order and hidden cards stay the person's (Settings →
  Appearance → Cards); an alarm puts the camera first and dims the rest except the print card. The camera can go into
  a small window above the tab bar (`CameraMini`, `cameraMiniStore` in `app/41-camera.js`); on a phone full screen and
  the small window are in the «⋮» menu next to the light (`CameraMoreMenu`, 1.134.1).
- **A WebRTC camera is a clean picture** (1.134.1): a `/webcam…` WebRTC page is loaded from the dashboard's own origin
  (`CameraMedia`) so `cleanCameraPage` can take away its player's controls and play it muted; the backend's `/webcam`
  proxy passes POST (the page's signalling) and `/webcam2…`, and a guest may POST there (`access.guest_may`). A camera
  with an absolute address stays as it is (another origin).
- **Layouts**: phone below **1100 px** (pages + floating tab bar; never scroll sideways; fits 320–360 px wide: five tabs,
  brand, AI badge and three round buttons); desktop from 1100 px (`useIsDesktop()`, `is-wide`, `desk-*` classes in
  `70-desktop.css`): the same cards arranged in columns, fixed-height pages with columns scrolling on their own, files
  and config with a detail panel / in-page editor, a console bar at the bottom. A change to the phone layout must not
  change the desktop one and vice versa.
- **Texts in the page**: short, plain, the user's words (`/humanizer`); explanations go in a setting's note or the help
  button, not on buttons. Every text in `tx()` with its 9 translations.

## 6. The owner's setup (for measuring and testing; part of the base model's training since 1.135.0)

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
  `GET /api/local_model` (about `0.15,0.36,0.70,0.61` on 16 Nov). Current base model **20261118-2036** (1.135.0, threshold 0.90,
  temperature 2.965, levels 80/90; the previous one, 20261116-1408, is in git history). Box `0,0.368,1,0.632`, 9 kept-out
  prints (4 failed, 2.5 h): «monitor» 0 false/h, 1 of 4 (before 10.5/h, 3 of 4); «+ motion» 0/h, 2 of 4 (before
  4.8/h, 2 of 4). Kept-out recording prefixes, never to train on: 20261113-164121, 20261115-011215, 20261116-160817,
  20261116-175000, 20261113-144408, 20261114-001218, 20261114-151534, 20261114-232613, 20261118-160816.

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
- `--paste` (public spaghetti on fine pictures + clean bed pieces as counterweight) comes with #182 (branch
  `paste-failures`) but the shipped model was trained without it (the patches looked fake). `--paste 0.2` gives ~660 + 660 pictures (20% of ~3,300 whole fine pictures).
- **The data is ready** (17 Nov, CPU run): `MyDrive/klippeye-training/prepared.zip` in the owner's Google Drive (7.3 GB,
  `ml/data` + `ml/work`, manifest paths relative; 47,972 pictures: 28,234 failed / 19,738 fine, 658 pasted failures +
  658 clean pieces, 4,403 look-alikes). Do **not** redo steps 4–5 of section 7. On 17 Nov Colab gave a GPU only in the evening, on 18 Nov none.
- Resume with a T4: Escape, ctrl+shift+p, «tipo di runtime», T4, «Salva», run a cell. Allocation can take minutes. If
  «Nessun backend con GPU disponibile» / «Impossibile connettere al backend GPU» appears, press «Annulla» / «Chiudi»,
  never «Connetti» / «Connetti senza GPU» (that is a CPU runtime). Retry every ~3 h (`send_later`). With a GPU, one-line
  cells, never ctrl+F10 (the notebook's own cells follow):
  1. `from google.colab import drive; drive.mount('/content/drive')`: the owner must click «Connetti a Google Drive».
  2. `!git clone -q https://github.com/BotuPotto/KlippEye -b paste-failures && pip install -q -r KlippEye/ml/requirements.txt && nvidia-smi -L`
  3. `%cd /content/KlippEye`
  4. `!unzip -q /content/drive/MyDrive/klippeye-training/prepared.zip && wc -l ml/work/manifest.csv` (47,973 lines)
  5. step 6 of section 7 **without** `| tail -40` (each epoch shows) and with
     `--checkpoint /content/drive/MyDrive/klippeye-training/ckpt.pt` (on `paste-failures`: saved after every epoch,
     resumed when it exists). 17 Nov: the free runtime was cut after 1 h 30 min of training with no one touching the
     page, and the run was lost. During training click inside the notebook every ~20 min (`send_later`); if it is cut
     anyway, reconnect and run the same cells again. Then step 7; copy `model2.zip` to the Drive folder too.
  Close the Colab tab whenever nothing runs (the owner's request: an idle page wastes the free quota).
  Measure with `C:\Users\coroz\Downloads\klippeye-data.zip` (section 6). Afterwards tell the owner he can delete
  `klippeye-training` from Drive.
- **18 Nov: trained on Kaggle, not shipped.** Colab gave no GPU (daily limit) so `ml/KlippEye_kaggle.ipynb` (branch
  `paste-failures`; «Save & Run All» runs in the background up to 12 h, 30 GPU h a week, T4 x2, 55 min for 15 epochs)
  trained from `prepared.zip` (Drive id in the notebook's first cell, typed in Kaggle, never committed). Model
  20261118-1834 on the owner's 14 prints, bed box: «monitor» row 0 false asks in 3.7 h but **2 of 5** failures caught
  (base 20261116-1408: 0.27/h, 3 of 5); at its own threshold 2 of 5 (base 4 of 5). Worse, so `models/base` stays.
  On the larger set `klippeye-misura.zip` (owner's Downloads, split zip, join with `zip -s 0`; 38 labelled prints,
  16 failed, 11.9 h of fine prints) with the calibration's bed box `0,0.368,1,0.632` (the monitor's real view; the
  0.15,… box above is older): the two curves are about the same. Base: 0.95 → 0.42/h, 6 of 16; 0.90 → 3.8/h, 8;
  0.86 → 9.0/h, 9; «monitor» 6.1/h, 7 of 16. New: 0.95 → 0.6/h, 5; 0.80 → 4.7/h, 8; 0.70 → 8.7/h, 11; «monitor»
  1.0/h, 5 of 16. No clear gain, and the pasted pieces are wrong, so not shipped.
  Why: the contact sheet shows the pasted pieces are **round patches** cut around the boxes, often not spaghetti at
  all (black or white discs, pieces of another scene): the model learns «a foreign round patch», which never happens
  on a real printer. Next try: paste only the spaghetti's own pixels (a mask from the colour/edges inside the box, or
  skip boxes whose patch does not look like strands), check the sheet **before** training, then train on Kaggle again.
  Colab's own rule: no second account to get round its limits (FAQ), Kaggle is a separate service and is fine.
- **23 Nov: 20261118-2036 shipped in 1.135.0 as a trial** (Kaggle, no `--paste`, `--klippeye` with 10 of the owner's
  prints, failed Bambu last pictures). Ask the owner after some prints how the monitor behaves; if worse (missed
  failures), restore 20261116-1408 from git (`git show <commit>:models/base/model.onnx`) in a patch release.
- **Next**: train (section 7) → measure against `models/base` on the owner's recordings → look at the contact sheet
  (pasted pieces must not look fake) → ship only if better (new `models/base/*`, `CREDITS.md`, measurements in
  `models/base/README.md`, CHANGELOG). Few pasted pictures → raise `--paste`. Distillation only if not enough.

- Known limit (audit 17 Nov): `ml/train.py` picks the epoch, the temperature and the threshold on the same pictures
  kept aside, and writes its «measured» from them too: optimistic. Only `ml/evaluate.py` on the owner's prints decides.

### Online AI calls and the owner's false alarms (18 Nov)
- The owner's close fisheye: the base model scores fine prints 80–90 on the «bed» view (empty bed at the start already
  66–92; the front of the bed alone 7–29): the view's edges (frame rails, gantry, the calibrated outline wider than the
  plate) fool it. Rejected after measuring on 19 judged recordings: covering the toolhead/gantry (inpaint, grey, black,
  bed colour, history background: false asks 6.1 → 12.2/h), a view cut to the objects' area + 20/40 mm (worse: the
  toolhead fills the crop), a per-print relative threshold (no gain), a heavier model on the phone (same unfamiliar scene).
- **Done in 1.134.3** (the retrained model of 18 Nov was worse and not shipped, so the simulation on `models/base` stood):
  `docs/superpowers/specs/2026-11-18-online-calls-design.md` and `docs/superpowers/plans/2026-11-18-online-calls.md`:
  `BLEND_MAX` 0.6 → 0.25 (personal layer; at 0.4+ the monitor went blind), online «fine» kept 10 min instead of 6 h.
  Simulated: 2.3–3.3 false online calls/h, failures asked about in ~100 s (before 4.7/h, 312 s). Re-run the simulation
  with any new base model (it needs the owner's data, below).
- The simulation needs the owner's data again (the session's scratchpad is gone): on the Pi
  `cd ~/printer_data/klippeye && zip -r -s 25m ~/klippeye-misura.zip camera.json machine_shape.json recordings reviews`,
  uploaded in parts (30 MB limit). Bed box from the calibration then: `0,0.368,1,0.632`. `recordings/*/session.json`
  keeps the objects (`zone`), `frames.jsonl` the toolhead positions (`live`, `live2`) and motion triggers (`trig`).
- Free quotas (Nov 2026, from published pages): Groq qwen3.8-27b 1,000/day but 200k tokens/day (~60–100 calls with
  pictures); Gemini 3.8 Flash 20/day; Flash-Lite 500/day; Gemma 4 31B (same Gemini key) 14,400/day. Advised chain:
  Gemma 4 → Gemini 3.8 Flash → Groq → Claude Haiku 5.5 (paid, Console credit; Pro does not include API calls).

### Camera calibration: bed slingers (remind the owner now and then)
- 1.132.3 refuses bed slingers with the camera on the frame (`bed_moves_in_y`); a camera on the bed works.
- **Plan**: (1) option «the bed moves in Y»; (2) second set of points = a fixed detail **on the bed** (clip, corner,
  screw) tapped with the bed at several Y: `camera_model.fit_offset` with base `(0, -y, 0)` (the unknown offset is where
  the detail is on the bed), nozzle points at `(x, 0, z)`; (3) after calibration shift everything on the bed by the
  current Y (`frame_point`, `print_zone` outlines, bed box, part, the local model's bed view); toolhead masks at Y = 0;
  (4) a calibration page step + 9 translations; (5) tests with simulated cameras like `test_calibration_auto.py`
  (before: 3 of 8 wrong calibrations rated «good»; target: all right). Cannot be tried on the owner's printer.
  A reminder is due on 19 Nov 18:00 (Rome): a new chat schedules it itself (`send_later`), it does not carry over.

### Code audit (17 Nov, 1.133.1)
- Fixed: port-80 auth for Moonraker's WebSocket and uploads, streamed uploads (with a length, never chunked too), one
  safe write (`atomic.py`) everywhere settings or labels are written, the hidden-part threshold, `repair.sh` speed,
  dead code. Read and found sound: access, proxy, monitor loop, second look, notifier auto actions, ai_services,
  camera maths and moves, install.sh, the Android WebView bridge.
- Lesson: a JS name used only through a spread (`...NAME`) looks unused to a naive search; build and load the page
  (or run the browser tests) before calling dashboard code dead.

### AI monitor
- Audited 16–17 Nov (releases 1.132.1–1.132.5): personal view at height 0, logs path test, false alarms follow the
  calibration, embedding cache trimmed, bed slingers refused, unconfirmed stops not learned, put-off questions not
  lost, prompt for every camera, exposure shift keeps blacks.
- Known trade-off: marks outside the parts in the first minutes count as purge and are hidden for the whole print.
- Not checked yet: the purge comparison when the bed moves in Z between heating and the start (the 12% cap should
  switch it off; not simulated).

### Dashboard look
- 17 Nov: analysis and demos (phone and computer) of an optimised look in claude.ai artifacts; the owner likes the
  current style and wants it refined, not replaced. 1.133.0/1.133.1 (#171) did: type scale, radii, «Nozzle» / «Bed» on
  the heater tiles, «See the layers» and «More details» as light buttons under Pause / Cancel (one `MoreDetailsButton`).
- Tests that measure a layer or a panel must wait for its animation to end (`getAnimations()`, finite ones only: the
  progress sweep and the AI badge loop forever): the 550 ms spring made `lights_test` and `editor_test` read half-grown
  boxes in CI (1.134.0).
- CI's headless Chromium has no hyphenation dictionaries: text that fits only by hyphenating (`hyphens: auto`) passes
  locally and fails there. Check narrow tables with DejaVu Sans and `hyphens: none` (the shaper table, 1.133.1).
- Proposed, not done (waits for the owner): AI state and score strip under the camera on Home, the print card's two
  big figures (ends at, remaining), temperatures folded during a print, 44 px hit areas (fold chevrons 36, fan −/+ 36,
  file actions 28, AI badge 48×28), uppercase labels, the remaining hand-written colours (293 outside the tokens).

### Home by moment and motion (17 Nov, 1.134.0)
- The owner keeps the current look; wanted Home to change with the moment (shown only when useful) and macOS-like
  motion. Approved moment table (demo): idle = next in queue, heat for a material, movement, recent files; heating =
  big temperatures, time left, cancel; printing = camera, print card, Z-offset, speed/flow, light; paused = resume,
  filament change, park, temperatures; finished = «how did it go», reprint / next, cool down; alarm = the monitor's
  picture, pause / it's fine.
- 1.134.0 did it with the cards Home already has. Not done yet: new Home cards (next in queue, recent files, filament
  load/unload and park in a pause, speed/flow on Home), the computer's layout (the plan: cards set aside go to the
  side column instead of disappearing), the «finished» moment (Klipper keeps `complete` for hours, so hiding cards
  there would hide them until the next print).

### Open PRs
#182 (release 1.135.0: the new base model, branch `paste-failures`), open 23 Nov: first CI run failed on
`ml/tests/smoke_train.py` (the test's reviewed print had the same start as a recording, so `same_print_once` merged
them), fixed in 31a919c; CI rerunning. Merge it once all green. #181 closed (replaced). Update this line when a PR opens or merges.
