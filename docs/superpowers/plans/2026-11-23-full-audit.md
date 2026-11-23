# Full audit of KlippEye Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read every line of KlippEye's code, look at every page, and deliver one ranked report of real problems (bugs, safety, load on the Pi, missing tests, look, structure, logic). The fixes come later, one PR per group, chosen by the owner.

**Architecture:** First a map. Then 15 zone readers, each covering a fixed list of files and reading all of them. After that, three passes that cut across zones (boundaries, the Pi under real conditions, the look), and a structure and logic pass. Every finding is checked by a separate verifier before it reaches the report, and dropped if it cannot be shown. The method of `ponytail-audit` applies to every reader: a concrete failing case for each finding, the smallest fix, no taste.

**Tech Stack:** the repository as it is after 1.137.0; Graphify for structure; Playwright and Chromium (`/opt/pw-browsers`) for pictures; `scripts/replay.py` and `ml/evaluate.py` for measurements.

**Spec:** the owner's request of 23 Nov (chat): a complete audit, line by line, of every part and aspect, with visual checks of the interfaces, a proposed reorganisation of the code and suggestions on the logic of functions. Rules: `CLAUDE.md` sections 3–5.

## When it starts

- After the owner's notes 1–3 of 23 Nov are merged: #186 (1.136.0) and the install/uninstall PR (1.137.0), CI green on `main`. Notes 4 (learning on the Pi, other libraries than OpenCV) and 5 (the documentation rewrite) come after the audit: its findings change what they build on, and the guides should describe code that is already fixed.
- Audit `main` at one fixed commit (write its SHA at the top of the report). Work on branch `audit-<date>` for the scratch files only; no code changes during the audit.
- For the logic pass: the old camera's data (`klippeye-misura.zip` in the owner's Downloads, section 6 of `CLAUDE.md`) and, when there are some, the new camera's recordings (only measured on, never trained on).

## Global Constraints

- The audit changes no code. Findings, pictures and notes go in `.superpowers/audit/` (git-ignored); only the final report is committed, at `docs/audits/<date>-full-audit.md`.
- Every finding: what the code does, the problem, the concrete case («this input or situation leads to this wrong result»), the smallest fix, what happens if we skip it. No case, no finding. A `shortcut:` comment that names its limit is a decision, not a finding, unless the real load crosses it.
- Groups: Must fix (bug, safety, data loss, breaks on a real Pi), Should fix (risky code without a test, real slowness, duplication, a function doing several jobs, code that should not exist), Nice to have.
- Expected load: one Raspberry Pi (32-bit, Python 3.11, OpenCV 4.6, maybe 1 GB of RAM) running Klipper too; one to three browsers or phones open at once; prints lasting up to several days; Wi-Fi that drops.
- Never name other printer UIs. Report in plain English (`/humanizer`); the owner gets an Italian summary in chat.
- Nothing may move, pause or restart the owner's printer. Pictures come from the mock server (`tests/ui/mock_server.py`), not from the real Pi.
- Every reader lists each file of its zone with «read in full: yes/no». A «no» is written under «Not checked» in the report.

## Review Focus

- A print of 2–3 days: lists, caches, logs and recordings that only grow (memory and disk on the Pi).
- Moonraker or Klipper restarting in the middle of a print, and Wi-Fi dropping between the phone and the Pi: what the monitor, the notifier and the page do.
- A power cut during any write (settings, labels, calibration, recordings, the update itself).
- Two browsers changing the same thing at once (12 server threads): check-then-write races.
- A new user whose printer is not the owner's (other kinematics, no camera, no bed mesh, a bed slinger, other folders): defaults that silently assume the owner's setup.

Each of these is a named check in Task 3 or Task 4, and each zone reader is told to look for them in its files.

---

### Task 1: Map and zones

**Produces:** `.superpowers/audit/map.md` with the commit SHA, the list of zones below, each with its files and line counts. The check is that every tracked file of code (`*.py`, `*.js`, `*.css`, `*.sh`, `*.kt`, `scripts/klippeye*`, `systemd/*`, `.github/workflows/*`) is in exactly one zone. `git ls-files` minus all zone files gives an empty list, or each leftover file is named with a reason (data, vendor, built page). `klippeye_backend.py` is the one file split between zones: A, C and E name their functions, F reads all the rest, and `map.md` lists the line ranges of each so that every line has one reader.

- [ ] Run Graphify (`list_repositories`, then `graphify_rank_files`, `query_graph skeleton=true`) to confirm the entry points and the most connected files. Record which `commitSha` it answered from.
- [ ] Write the zones:

| Zone | Files |
|---|---|
| A. Monitor loop | `klippeye_backend.py` (`LightDetector`, `LocalAi`, `real_print_check`, `_local_*`, `effective_config`), `monitor_core.py`, `local_model.py`, `purge_marks.py`, `machine_masks.py`, `print_zone.py` |
| B. Learning and memory | `personal_layer.py`, `labelled_prints.py`, `false_alarms.py`, `recorder.py`, `print_review.py`, `ai_precision.py` |
| C. Online AI | `ai_services.py`, `call_ai_analysis`, `build_ai_prompt`, `confirm_stop`, `record_alert` in `klippeye_backend.py` |
| D. Calibration | `camera_calibration.py`, `camera_model.py`, `camera_watch.py`, `camera_markers.py`, `nozzle_finder.py`, `homing_safety.py`, `camera_snapshot.py` |
| E. Access and network | `access.py`, `https_relay.py`, `scripts/web_front.py`, `proxy_moonraker`, the `/webcam` proxy, the access guard and the table of every `/api/*` route with who may call it |
| F. Backend, the rest | settings (`CONFIG_SPEC`, `MonitorConfig`), `printer_macros.py`, `macro_catalog.py`, `printer_lights.py`, `printer_paths.py`, `printers_peek.py`, `config_versions.py`, `print_schedule.py`, `shaper_data.py`, `shaper_fit.py`, `notify_channels.py`, `mqtt_bridge.py`, `mqtt_client.py`, `moonraker_live.py`, `atomic.py`, the rest of `klippeye_backend.py` |
| G. Notifier | `notifier/klippeye_notifier.py` (automatic pause and cancel first) |
| H. Install and updates | `scripts/install.sh`, `repair.sh`, `ripara.sh`, `klippeye`, `klippeye-notifiche`, `diagnose.py`, `benchmark.py`, `systemd/*`, `.github/workflows/release.yml`, the update channel in the backend |
| I. Dashboard core | `frontend/src/app/0*`–`2*`, `frontend/build.py`, `frontend/tools/*`, `frontend/src/css/0*`–`2*` |
| J. Dashboard Home, camera, console, files | `frontend/src/app/3*`–`4*` and their CSS |
| K. Dashboard control, config, system | `frontend/src/app/5*` up to `58*` and their CSS |
| L. Dashboard settings | `frontend/src/app/59*`, `99-main.js` and their CSS |
| M. Android app | `android/` (WebView bridge, downloads, pinning, updates), `.github/workflows/app.yml`, `ci/` |
| N. Model training chain | `ml/*.py`, the notebooks, `models/base/*.json`, `scripts/replay.py` |
| O. Tests and CI | `tests/**` (what each test really pins, flaky waits, tests that pass without the code), `.github/workflows/tests.yml`, `e2e.yml` |

- [ ] Commit nothing; the map stays in `.superpowers/audit/`.

### Task 2: Zone readers (one reader per zone, A to O)

**Consumes:** `map.md`.
**Produces:** `.superpowers/audit/zone-<letter>.md`: up to 20 findings in the format of Global Constraints, then «Files read in full», then «Not checked».

- [ ] For each zone, dispatch one reader with: its file list, the `ponytail-audit` checklist (bug, risk, scale, missing test, speed, lean), the five lines of Review Focus, and the zone's own questions:
  - A: the order of the rules in the loop against section 2 of `CLAUDE.md`; what happens when the picture or Moonraker does not answer.
  - B: files that only grow; retraining that blocks the loop; labels lost on a power cut.
  - C: answers that are not JSON, a 429 in the middle of the chain, a key that leaks into a log, the second look.
  - D: a calibration that is rated «good» but is wrong; numeric edge cases (fisheye near 90°, a point behind the camera).
  - E: every route checked for password and guest role, Host and Origin checks, path traversal in files and logs, the nginx site.
  - G: an automatic pause or cancel that fires twice, or on a stale verdict, or on the wrong print.
  - H: re-runs, power cuts during an update, a user other than `pi`, other folders.
  - I–L: state that is lost on a reconnect, timers and listeners never cleared, `fetch` without error handling, texts not in `tx()`.
  - M: the bridge methods the page can call, files written by downloads, pinning that can be bypassed.
  - N: data leaking between training and the kept-out prints (the 9 prefixes in `CLAUDE.md` section 6), licence filter.
  - O: a test that would still pass if the code it names were deleted (try deleting a line where it is cheap).
- [ ] Readers of zones A, C, E, G, H use the most capable model; the others a standard one. A reader never edits files.
- [ ] After each reader: check its «Files read in full» list against `map.md`; a missing file goes back to the same reader.

### Task 3: Cross-cutting passes

**Produces:** `.superpowers/audit/cross-boundaries.md`, `cross-pi.md`.

- [ ] Boundaries: every `fetch`/`camcalPost` URL in the dashboard has a backend route, and every route has a caller or is in `docs/API.md` (use `graphify_file_neighbors`); field names on both sides match. The notifier reads what the backend writes (`last_analysis`, Moonraker's `klippeye` namespace). Install writes what the backend expects (paths, environment). The «rules written twice» list in `CLAUDE.md` section 1 still agrees on both sides.
- [ ] The Pi under real conditions, run on the mock and the real backend in the container:
  - a 48-hour print simulated with `scripts/replay.py` looped over the old camera's recordings: measure memory every hour, the size of every file under the data folder, the number of threads;
  - Moonraker stopped and started during the replay;
  - the backend killed in the middle of each kind of write (a small script that kills at random points), then started: nothing lost or half-written;
  - two browser sessions changing the same setting at once;
  - a printer config with no camera, no bed mesh, a bed slinger, and a delta, through the mock server.
  Each problem found becomes a finding with the command that shows it.

### Task 4: Visual pass

**Produces:** `.superpowers/audit/shots/` and `visual.md`.

- [ ] A scratch script (in `.superpowers/audit/`, not committed) built on `tests/ui/docs_screenshots.py` and the mock server takes pictures of every page and every menu page:
  - widths 320, 360, 412 (phone), 1280 and 1600 (computer), in the dark and light themes;
  - the states idle, heating, printing, paused, alarm, finished, Pi not answering and no camera;
  - every page in German, Polish and Russian (the longest texts), the other languages on Home and Settings only.
- [ ] A reader with image input looks at every picture against section 5 of `CLAUDE.md` (cut or overflowing text, overlap, sideways scroll, wrong colour meaning, radii, type sizes, buttons under 44 px). Each finding names the picture file.
- [ ] Static checks next to it: hand-written colours outside the tokens, radii and font sizes outside the allowed lists, `text-transform: uppercase`, classes with no rule, contrast. Record the counts; `CLAUDE.md` gives 293 colours and 9 uppercase labels on 17 Nov.
- [ ] Not possible here, and written under «Not checked»: real touch, the Android WebView, the owner's real camera. List the 5–10 pictures the owner should check on his phone.

### Task 5: Structure and logic

**Produces:** `.superpowers/audit/structure.md`, `logic.md`.

- [ ] Structure: duplicated code (a token-based near-copy search over `backend/`, `notifier/`, `frontend/src/app/`), functions or files doing several unrelated jobs (`klippeye_backend.py` at 5,279 lines first), imports that tie modules together without need (Graphify), dead code (grep the whole tree, then build and load the page before calling dashboard code dead, as `CLAUDE.md` warns). Each proposal says which job moves where, what it costs, what it saves, and the test that must pass before and after. Moves are proposed in steps that each keep the behaviour, never as one big rewrite.
- [ ] Logic: for the monitor rules, the online AI chain, the false-alarm memory, the calibration quality and the automatic pause, each suggestion is written as a hypothesis with the measurement that decides it (`scripts/replay.py --set KEY=VALUE` or `ml/evaluate.py` on the old camera's data, then the new camera's data as the independent check). Run the measurements that take under an hour; list the others with their command.

### Task 6: Verify every finding

**Consumes:** all files from Tasks 2–5.
**Produces:** `.superpowers/audit/verified.md`.

- [ ] Merge duplicates across files. For each finding, a verifier who did not write it reproduces the case: a failing test, a command, a picture or a measurement. Not reproduced and not obvious from the code: dropped, with one line saying why. Reproduced: keep the command, so the fix PR can turn it into its test.
- [ ] Re-rank: Must fix, Should fix, Nice to have, numbered across groups.

### Task 7: The report

**Produces:** `docs/audits/<date>-full-audit.md`, committed on `audit-<date>`, PR to `main`; an Italian summary in chat.

- [ ] Sections: «What KlippEye is and the load assumed», then four parts: bugs and safety, look, structure, logic. Each part has its numbered findings with the format of Global Constraints and the command that shows each one. At the end: «Verdict», «Lean: −N lines possible», «Not checked».
- [ ] A proposed order of fix PRs: Must fix first, grouped by zone so one PR touches one area; each with its version bump (patch for fixes, minor when behaviour changes).
- [ ] Update `CLAUDE.md` section 8 with a «Full audit» topic: the report's path, the commit audited, the fix PRs still to do.
- [ ] Ask the owner which groups to fix and in what order. Each fix then follows section 4 of `CLAUDE.md`, starting from the verifier's command as its failing test.
