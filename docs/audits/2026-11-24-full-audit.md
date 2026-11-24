# KlippEye full audit, 24 Nov 2026

Code audited: commit `f0552fb671e0100528d58daf72566c65cfb77593` (main after 1.137.0). The audit branch head `ab051af`
differs from it only in `CLAUDE.md`.

About the proof scripts. The audit worked in `.superpowers/audit/`, which git ignores. The scripts that show the Must
and Should findings below are copied into `docs/audits/2026-11-24-proofs/` (only `.py` and `.sh`, no outputs and no
data). Everything else stays outside git: the zone reports, the pictures, the three JavaScript proofs (findings 59, 60,
61), and the measuring scripts of section 6 (`.superpowers/audit/proofs/S/`). In the commands, `$P` means
`docs/audits/2026-11-24-proofs`. Run them from the repository folder. They find the repository from
their own place (or `KE_ROOT` when it is set). Each command is meant to
become the failing test of its fix PR. `D/harness.py`, `D/d2c_param.py`, `X2/common.py`, `X2/fake_pi.py` and
`X2/launch_backend.py` are helpers the other scripts load. The copies differ from the audit's originals only where
they had to run from the new folder: relative paths one level deeper, a sibling file instead of a `/tmp` copy, a
`mkdir` for their scratch folder, and neutral sample data. Each copy was read in full: no keys, passwords or real
addresses (the keys and passwords in them are made up, the hosts are `127.0.0.1` or `example` names).

## 1. What was audited

KlippEye is a dashboard and AI print monitor for any Klipper printer. It runs on the printer's Raspberry Pi next to
Moonraker: a Flask backend on port 8085, an optional nginx front on port 80, a notifier service, one built HTML page,
an Android app and a model training chain.

Scope. Every tracked code file, about 85,200 lines, split into 15 zones. Each line of
`backend/klippeye_backend.py` (5,279 lines) had one reader.

| Zone | What | Lines |
|---|---|---|
| A | monitor loop | 1,997 |
| B | learning and memory | 1,452 |
| C | online AI | 1,347 |
| D | calibration | 2,000 |
| E | access and network | 1,706 |
| F | the rest of the backend | 5,250 |
| G | notifier | 1,733 |
| H | install and updates | 1,904 |
| I | dashboard core | 5,564 |
| J | dashboard Home, camera, console, files | 12,576 |
| K | dashboard control, config, system | 7,504 |
| L | dashboard settings | 10,471 |
| M | Android app | 3,861 |
| N | model training chain | 2,477 |
| O | tests and CI | 25,382 |

How it was done.
- 15 zone readers read their files in full and wrote a finding only when they had a concrete case. They proved most
  cases with a small script.
- Three passes crossed zones. The boundaries pass compared routes, field names and the rules written twice. The Pi pass
  ran the real backend against a fake Moonraker and camera: a long print sped up, Moonraker and the camera killed, 8 to
  10 SIGKILLs during each kind of write, clients saving at once, five kinds of printer. The look pass took 254 pictures of the
  dashboard from the mock server and measured them.
- A structure pass and a logic pass (sections 5 and 6).
- Three verifiers who had not written the findings checked F001 to F109 again. They ran each proof or read the code,
  and moved findings between groups. Their verdicts win over the readers'. The 61 Nice findings (F110 to F170) were not
  verified one by one.

Load assumed: one Raspberry Pi, 32-bit, Python 3.11, OpenCV 4.6, maybe 1 GB of RAM, also running Klipper; one to three
browsers or phones at once; prints of several days; Wi-Fi that drops.

What could not be run here:
- a real Raspberry Pi (the container has 2 x86 cores, 64-bit Python 3.13, OpenCV 5.0);
- nginx (the port-80 findings use the nginx source and an emulation);
- waitress (Flask's own server stood in, so the 12-thread pool was not measured);
- the owner's recordings and camera files (not in the container);
- the Kotlin code (read and mirrored in Python, not built or run);
- touch, the Android WebView and real power cuts (SIGKILL shows what a crashed process leaves, not what an SD card loses
  without fsync).

Totals after the verifiers: 22 Must fix, 65 Should fix, 80 Nice to have (170 candidates, three pairs merged).

## 2. Bugs and safety

Each finding gives the file, what happens, the case, the smallest fix, what we lose by skipping it, the proof and the
verifier's verdict. «REPRODUCED» means the verifier ran the proof and saw the wrong result. «CONFIRMED (code)» means
they read the code and built the case by hand. «PARTLY» means part of the claim holds.

### Must fix

#### 1. With a calibrated camera and no working local model, every check crashes (F001)
`backend/klippeye_backend.py:2542-2558, 2611-2630`
- What happens: `local_judge` returns None only when the failing view is "whole". With a calibration the first view is
  "bed", so an empty score list reaches `max()` and raises. The loop's catch-all swallows it before the online question,
  the recording and the review.
- Case: OpenCV cannot load or run `models/base/model.onnx` and a calibration is saved. Every check logs
  `loop error: max() iterable argument is empty` for the whole print. A real failure never reaches the online AI.
- Fix: `if not scores: return None` before the `max`, and drop the special case for "whole".
- If we skip it: on every such printer the AI monitor is silently dead.
- Proof: `python3 -I $P/A/proof1.py` prints `RAISES: ValueError max() iterable argument is empty`.
- Verifier: REPRODUCED, Must.

#### 2. A snapshot address that streams hangs the monitor and fills the RAM (F002)
`backend/klippeye_backend.py:2426, 2055, 2578` (7 callers in all)
- What happens: the picture is read with `requests.get(url, timeout=4)` and `r.content`. The timeout counts per read,
  not for the whole answer, so an MJPEG stream never returns and `r.content` keeps growing.
- Case: the person types the stream address in Settings, Camera, Snapshot (it is the address most camera pages show).
  The monitor thread is stuck for good and buffers the stream until the Pi swaps.
- Fix: one helper for all 7 callers with `stream=True`, a byte cap, a total deadline of a few seconds, and refusal of
  `multipart/` content.
- If we skip it: one wrong field stops the monitor and can push a Pi that runs Klipper into the OOM killer.
- Proof: `python3 -I $P/A/proof3.py` prints `still waiting after 30 s with timeout=4`.
- Verifier: REPRODUCED, Must.

#### 3. The monitor goes blind without telling anyone (F003)
`backend/klippeye_backend.py:2414-2442`, `backend/monitor_core.py:110`
- What happens: when the camera or Moonraker fails, the loop prints a line and naps. `stats["status"]` keeps its last
  text and the dashboard reads only that and `frames_checked`.
- Case: the camera dies mid-print. The status stays «preparing the comparison (2/5 pictures)» or «scanning» while 0
  checks run. The Pi pass measured 144 s with Moonraker dead and 100 s with the camera hanging, both shown as
  «scanning». With no camera set, a print showed «idle - waiting for a print».
- Fix: set `stats["status"]` in the failure branches («no picture from the camera», «Moonraker does not answer») and
  keep the time of the last real check.
- If we skip it: the person trusts a monitor that is not looking.
- Proof: `python3 -I $P/A/proof2.py` (same status and count before and after 20 s of a dead camera). Longer:
  `python3 $P/X2/run_long.py 24 0.2`, `python3 $P/X2/run_configs.py`.
- Verifier: REPRODUCED, Must.

#### 4. A damaged false-alarm or cache file stops the backend or wipes what it learned (F004 + F040)
`backend/false_alarms.py:50-74`, `backend/personal_layer.py:266-271, 290-294`
- What happens: both modules load their `.npz` with `np.load` and catch only `OSError`, `ValueError` and `KeyError`. A
  zero-length or half-written file raises `EOFError` or `BadZipFile`. `FalseAlarms()` runs at import
  (`klippeye_backend.py:3174`), so the backend cannot start. `_save` replaces the npz without fsync, then writes the
  json; when their lengths differ `_load` keeps nothing. In the personal layer the same error turns into `last_error` at
  every training, and the cache is never rewritten.
- Case: a power cut right after a «false alarm» answer leaves an empty `false_alarms.npz`, and systemd restarts the
  service in a loop. In the Pi pass, one kill in ten during labelling left 26 items and 27 vectors, and the backend came
  back with `false_alarms: {"person": 0}`. The next answer then overwrites both files.
- Fix: catch `Exception` in both loads (start empty); write the npz through `atomic` (temp name, fsync, replace); keep
  the items inside the npz, or at least keep the first `min(len(items), len(vectors))` on a mismatch.
- If we skip it: one power cut can make the dashboard unreachable until someone deletes the file over SSH, or quietly
  forget every false alarm the person marked.
- Proof: `python3 -I $P/B/corrupt_npz.py` (EOFError and BadZipFile out of `FalseAlarms()`, `loaded items: 0`, then the
  personal layer's EOFError). Under load: `python3 $P/X2/run_kill.py 10 false`.
- Verifier: REPRODUCED for both. F040 was moved from Should to Must and merged here, because it is the same loading
  defect and needs the same fix.

#### 5. An exception in an AI look throws away the whole analysis, a first PAUSE included (F005)
`backend/klippeye_backend.py:2846-2873, 3081-3083`
- What happens: `ai_services.answer_text` raises `ValueError` on a 200 answer that is not JSON, and the retry after a
  429 sits outside any `try`. Either one ends `call_ai_analysis`.
- Case: Groq answers PAUSE, and the second look's service returns an HTML error page with status 200. Nothing is
  recorded: `last_analysis` stays empty and no alert is written. The same happens on the first look, where the backup
  would have answered.
- Fix: wrap the body of `_ask_ai` so any exception becomes `{"ok": False, ...}`. The chain then moves on, and a first
  PAUSE whose second look fails is kept.
- If we skip it: a real failure the first look caught is dropped without a trace.
- Proof: `python3 -I $P/C/proof.py 2>/dev/null | grep -A3 "^== 1\|^== 2"`: cases 1a, 1b and 2 end with
  `last_analysis action: None | alerts recorded: 0`.
- Verifier: REPRODUCED, Must.

#### 6. «Find the nozzle» moves the printer during a print (F006)
`backend/camera_calibration.py:509-528, 577-611`
- What happens: `find_tip` calls `_walk()`, which sends G0 moves, before `goto()` checks `_ready_to_move`. The route
  `/api/camera/calibration/find` has no guard of its own.
- Case: a calibration draft is open, a print starts, and the page (or a second browser) asks to find the nozzle. Eight
  G0 moves reach Klipper while `print_stats.state` is `printing`.
- Fix: call `self._ready_to_move(printer)` at the top of `find_tip` (`find_all` goes through it too).
- If we skip it: KlippEye moves a real printer mid-print without the owner asking, which breaks the project's safety
  rule and can crash the toolhead into the part.
- Proof: `python3 -I $P/D/d1_find_moves_during_print.py` prints `G-code sent while print_stats.state == printing: 8`.
- Verifier: REPRODUCED, Must.

#### 7. A calibration rated «good» can be hundreds of pixels wrong away from the taps (F007)
`backend/camera_model.py:158-196`
- What happens: the fit gets 12 points on a grid of 20/50/80 % by 25/75 % of the bed, at two heights, for 11
  parameters. The rating looks only at the residuals on those 12 points, so the lens curve can fold back outside them.
- Case: a simulated fisheye with 1 px of tap noise: 20 of 20 fits rated «good», all 20 have a seen bed point off by
  more than 44 px, and the median worst error over the whole bed is 634 px. The masks and the bed view near the edges
  are then drawn in the wrong place while the page says «good».
- Fix: a weak prior on the distortion (two extra residuals `200·k1` and `200·k2`). With it the median worst error drops
  to 5 px. Add a guard that refuses a fit whose curve folds inside the bed's angles (it catches 12 of 20 wrong fits).
- If we skip it: on any camera, the owner's included, the monitor can watch or hide the wrong parts of the bed.
- Proof: `python3 -I $P/D/d2b_bed_grid.py`; with the fix: `PRIOR_PX=200 python3 -I $P/D/d2f_prior.py`; the fold:
  `python3 -I $P/D/d2e_fold.py`.
- Verifier: REPRODUCED, Must. Synthetic only. Before shipping, try the prior on a fisheye with larger true k1 and k2 (the
  proof uses 0.02 and -0.01) and on the owner's `camera.json` (section 6, Q2).

#### 8. One failed read of access.json turns the password off (F008)
`backend/access.py:91-105`
- What happens: `except (OSError, ValueError): fresh = True`, then the defaults (no password) are saved over the file.
- Case: a tired SD card or a permission glitch makes one read fail. The password is off on disk from then on, and the
  dashboard is open to the network.
- Fix: reset only on `ValueError` (JSON that really is broken). On `OSError` keep the cached settings, or refuse the
  request when there are none, and never write.
- If we skip it: a dashboard that controls a printer can become open with no message.
- Proof: `python3 -I $P/E/probe.py 2>&1 | sed -n '/== 6/,/== 7/p'` prints
  `password on before: True  after one failed read, on disk: False`.
- Verifier: REPRODUCED, Must. The test at `test_backend.py:1275` covers damaged JSON only and still passes after this fix
  (see finding 86).

#### 9. On port 80, a page on another site can upload and start a G-code file when no password is set (F009)
`scripts/web_front.py:103-127`, `backend/klippeye_backend.py:470-476`
- What happens: nginx asks KlippEye through `auth_request`, and an nginx subrequest is always a GET. The guard skips its
  Origin check for GET, and the Sec-Fetch rule lets a cross-site navigation through.
- Case: a page on any site posts a form to `http://raspberrypi.local/server/files/upload`. Sent to 8085 the same POST
  gets 403, but `GET /api/auth/check` with the same headers gets 204, so nginx passes the upload to Moonraker.
- Fix: `proxy_set_header X-Original-Method $request_method;` in `/_klippeye_auth`, and the guard uses that method for
  `/api/auth/check`. A client cannot spoof it because nginx overwrites it.
- If we skip it: KlippEye's main mode (offered at install since 1.137.0) is the one place where another site can drive
  the printer.
- Proof: `python3 -I $P/E/probe.py 2>&1 | sed -n '/== 1/,/== 2/p'` (403 direct, 204 through the check).
- Verifier: REPRODUCED. nginx was not run; its source sets `sr->method = NGX_HTTP_GET` for subrequests. Only without a
  password: the Strict cookie stops it when one is set.

#### 10. On port 80, an unknown /webcamN path makes KlippEye call itself in a loop (F010)
`backend/klippeye_backend.py:1298-1312`, `scripts/web_front.py:146-160`
- What happens: nginx sends any path it has no location for to `location /`, which is KlippEye. `webcam_proxy` sends
  `/webcamN` on to `http://127.0.0.1/webcamN`, which is nginx again.
- Case: one GET of `/webcam9/` from anyone made 2,881 requests inside KlippEye in a few seconds. Under waitress the chain
  stops at the 12 threads and freezes the dashboard for about 15 s per request.
- Fix: add a hop header on the proxied request and answer 502 at once when it comes back.
- If we skip it: one bad camera address, or one request, freezes the dashboard in main mode.
- Proof: `python3 -I -u $P/E/loop.py` (the `-u` matters: the script ends with `os._exit`).
- Verifier: REPRODUCED (emulated with werkzeug in place of nginx and waitress), Must.

#### 11. The filament-change announcer stops Klipper from starting (F011)
`backend/printer_macros.py:117-159`
- What happens: Klipper reads every include into one `RawConfigParser(strict=False)`, so KlippEye's
  `[gcode_macro M600]` merges into the user's own section of the same name.
- Case: the user picks M600, which is almost always a `gcode_macro`. Klipper refuses to start with
  `G-Code macro rename of different types ('M600' vs 'KLIPPEYE_ORIGINAL_M600')`.
- Fix: `set_wraps` refuses names that are `[gcode_macro]` sections in `configfile.settings`, and points to the console
  line option. The feature needs another way to wrap a macro.
- If we skip it: the setting's main example leaves a printer that will not start until someone edits
  `klippeye_macros.cfg` by hand.
- Proof: `python3 -I $P/F/wrap_m600.py`.
- Verifier: REPRODUCED with Klipper's parser emulated; not run in real Klipper.

#### 12. A scheduled print starts hours late after the Pi was off (F012)
`backend/print_schedule.py:216-225`, `backend/klippeye_backend.py:4229-4236`
- What happens: `decide()` limits lateness only when Klipper is not ready, which contradicts the module's own docstring.
- Case: a print is set for 03:00, the power goes off at 02:59 and comes back at 09:00. The print starts at once, 6 hours
  late, maybe with the old print still on the bed. A Pi with no RTC that jumps its clock at NTP sync is another way in.
- Fix: return `("missed", "late")` when `now - at > NOT_READY_GRACE_S`, also when Klipper is ready.
- If we skip it: the printer heats and moves by itself long after anyone expected it.
- Proof: `python3 -I $P/F/schedule_late.py` prints `print started: ['benchy.gcode'] - hours late: 6`.
- Verifier: REPRODUCED, Must.

#### 13. Back-to-back prints from Moonraker's job queue look like one print to the notifier (F013)
`notifier/klippeye_notifier.py:758-781`
- What happens: `_print` resets `auto_done`, `ai_levels` and the fired rules only when the state comes from something
  other than printing or paused, and it never compares the file name. The queue goes from complete to printing within
  one 5 s poll.
- Case: print A paused on a false alarm, the person resumed, A ended and B started. B's first real PAUSE verdict gets no
  action. With 2 confirmations required, one verdict of A and one of B together pause B. «Print completed» for A is
  never sent.
- Fix: treat a changed `info["file"]` while printing as a new print: send «complete» for A and run the same reset.
- If we skip it: queue users lose the automatic pause on real failures, or get one against their chosen confirmations.
- Proof: `python3 -I $P/G/proof_queue3.py` prints `B: actions on its first PAUSE verdict: []`;
  `python3 -I $P/G/proof_queue2.py` prints `['pause']` with 2 required; `python3 -I $P/G/proofs.py` (P1).
- Verifier: REPRODUCED, Must.

#### 14. A full SD card empties moonraker.conf and moonraker.asvc on uninstall, undo or a channel change (F014)
`scripts/install.sh:299-312, 317, 559-576`
- What happens: `open(p, "w").write(...)` and `grep > tmp; cat tmp > asvc` truncate the file before writing, and the
  script has no `set -e`.
- Case: a card full of timelapses. Both files end at 0 bytes, the script prints «removed» and restarts Moonraker anyway.
- Fix: write a temp file next to each one, then `os.replace` / `mv` only when the write succeeded (as the printer.cfg
  code at lines 355-359 already does). Check that grep's temp file was written, since grep exits 1 when no line is left.
- If we skip it: the command meant to take KlippEye off also takes the printer's web access off. The backup made by
  `backup_file` (through sudo, using root's reserved blocks) is the only way back, by hand.
- Proof: `bash $P/H/full_disk.sh` (`ulimit -f 0` stands in for a full card) prints `0 bytes` twice.
- Verifier: REPRODUCED, Must.

#### 15. The klippeye command uses another data folder than the services (F015)
`scripts/klippeye:7-9`, `scripts/repair.sh:19-21`, `scripts/install.sh:57-66, 273-278`
- What happens: the unit sets `KLIPPEYE_DATA`, while the `/usr/local/bin` wrapper passes none and the command guesses.
- Case: a printer folder other than `~/printer_data` (for example `printer_1_data`). The services use
  `.../printer_1_data/klippeye`; `klippeye status` and `klippeye password` use `~/klippeye_data`. A password set from
  the command protects nothing.
- Fix: `install_command` writes `KLIPPEYE_DATA="$DATA"` into the wrapper.
- If we skip it: on these layouts the password command silently does nothing.
- Proof: `bash $P/H/data_mismatch.sh`.
- Verifier: REPRODUCED, Must.

#### 16. Two open dashboards: the last settings save wipes the other's change, the safety switches included (F016 + F023)
`frontend/src/app/16-settings.js:516-548, 619-632, 655-662`, `59h-ai-monitor-settings.js:137-138`
- What happens: all dashboard settings are one document in Moonraker's database. `push()` sends the whole document from
  this page's memory, and `pull()` runs only when the page opens or comes back to the front. «Pause by itself» and
  «Cancel by itself» live in the same document, and the notifier acts on it (`klippeye_notifier.py:503-504`).
- Case: the phone renames the printer; the computer, open since before, changes one material. The stored name is empty
  afterwards. The same way, a stale page can switch «Cancel by itself» back on with no one seeing it.
- Fix: before writing, read the remote copy; when its `_t` is newer, apply only this page's change on top of it.
- If we skip it: settings quietly go back to old values, and a print can be cancelled, or not paused, because an old
  page saved an old copy.
- Proof: `sed 's/^const settingsStore = createSettingsStore();$/& window.__ss = settingsStore;/'
  frontend/klippeye_frontend.html > /tmp/probe.html && cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3
  ../../$P/I/settings_race.py /tmp/probe.html 8792` prints `stored printer.name: '' (expected 'FROM-PHONE')`. For the
  fix PR, test it again with `autoCancel` as the field.
- Verifier: F016 REPRODUCED, F023 CONFIRMED (code); same root and same fix, merged.

#### 17. The emergency stop can fail with no message (F017)
`frontend/src/app/12-api.js:206`, `app/30-klipper-state.js:323-328`
- What happens: the stop sends `POST /printer/emergency_stop` and `M112` through plain `fetch` with no time limit, and
  both errors are swallowed.
- Case: the phone wakes up with dead connections and the person taps stop. Both requests fail and no toast appears.
- Fix: check both answers, and show a danger toast when neither is ok, or neither arrives within a few seconds.
- If we skip it: the one button the person trusts can do nothing while the screen looks like it worked.
- Proof: `cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../$P/I/estop_silent.py
  ../../frontend/klippeye_frontend.html 8793` prints `toasts shown: []`.
- Verifier: PARTLY, Must. A refusal is never reported and there is no timeout. On a fully dead connection the
  «Reconnecting…» strip does appear after `LIVE_QUIET_MS`, so the screen is not blank.

#### 18. Start, Pause, Cancel and Exclude never read Klipper's answer (F018)
`frontend/src/app/99-main.js:6-8, 226-233`, `app/45-print-progress.js:280-301, 392-403`
- What happens: `fetch(...).catch(noop)`.
- Case: a start refused with 400 closes the dialog with no message; a cancel refused with 400 shows «CANCEL_PRINT sent».
- Fix: one helper that checks `response.ok` and shows Moonraker's error text in the existing toast, used in the four
  places.
- If we skip it: a failed cancel looks like it worked, which costs filament or a crash.
- Proof: `cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../$P/J/p1_print_actions_ignore_answer.py`.
- Verifier: REPRODUCED, Must.

#### 19. The config editor can overwrite what Klipper or another browser wrote (F019 + F020)
`frontend/src/app/50-config-files.js:86-95, 117, 259-263`, `51-config-editor.js:604-619`, `51a-config-versions.js:17-21`
- What happens: `configFileCache` serves the editor a copy read earlier, and only the manual reload clears it. Save
  never compares the file's `modified` with the one it opened.
- Case: the person runs a calibration that ends with SAVE_CONFIG, then edits `printer.cfg` in the same session. The
  editor shows the old copy and Save drops the SAVE_CONFIG block. With two tabs, tab B's saved change is gone after tab
  A saves, with no warning, and the kept «earlier version» is A's old text too.
- Fix: the editor always reads fresh on open (keep the cache for the list), remembers `modified`, and asks before
  uploading when the Pi's copy changed.
- If we skip it: with 1 to 3 browsers this is a normal situation, and the loss is silent.
- Proof: `cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../$P/K/stale_cache.py
  ../../frontend/klippeye_frontend.html /tmp/k1 8795` and the same with `$P/K/two_tabs.py /tmp/k2`.
- Verifier: both REPRODUCED; one fix covers both, merged.

#### 20. «Save and restart» restarts Klipper mid-print when the state read fails (F021)
`frontend/src/app/51-config-editor.js:344-350`
- What happens: the print state is read with `.catch(() => ({}))`, so an unknown state counts as «not printing».
- Case: a slow answer or a Wi-Fi drop at that moment. No dialog is shown and `firmware_restart` is sent during a print.
- Fix: when the read fails, ask anyway (or refuse with «cannot tell if a print is running»).
- If we skip it: one dropped request kills a multi-hour print.
- Proof: `cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../$P/K/restart_fail_open.py
  ../../frontend/klippeye_frontend.html /tmp/k3 8795` prints
  `state read fails = True | confirm dialogs shown: [] | restart requests: [.../firmware_restart]`.
- Verifier: REPRODUCED, Must.

#### 21. Renaming a bed mesh profile that is not in use changes the mesh in use (F022)
`frontend/src/app/58-bed-mesh.js:545-549`
- What happens: the rename is LOAD old, SAVE new, REMOVE old. LOAD makes the old profile the active mesh. The mesh page
  has no guard for a running print.
- Case: `default` is in use and the person renames `adaptive` to `fine_bed`. Afterwards `fine_bed` is in use, possibly
  in the middle of a print.
- Fix: refuse while printing, and end with `BED_MESH_PROFILE LOAD=<the one in use>` when it was not the renamed one. An
  unsaved active mesh cannot be put back: say so in a `shortcut:` comment.
- If we skip it: a first layer too high or too low after a harmless-looking rename; at worst a nozzle crash.
- Proof: `cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../$P/K/mesh_rename.py
  ../../frontend/klippeye_frontend.html /tmp/k4 8795` (in use `default` before, `fine_bed` after).
- Verifier: REPRODUCED, Must.

#### 22. Nothing in the code keeps the 9 kept-out prints out of training (F028)
`ml/datasets.py:312-325`, `ml/KlippEye_kaggle.ipynb` cell 3, `ml/KlippEye_local_model.ipynb` cells 6 and 8,
`ml/evaluate.py:167`
- What happens: `from_klippeye` trains on every judged print under the folder. The nine prefixes exist only in
  CLAUDE.md, and `klippeye-misura.zip` holds all nine.
- Case: the next retrain with `--klippeye` on that zip trains on the measuring prints, and the numbers in
  `models/base/README.md` stop meaning anything.
- Fix: a kept-out list file in `ml/` (or `models/base/kept-out.txt`) that `from_klippeye` skips, matching prints by
  start time so the review copy is skipped too (finding 27), and one test that fails when a listed print reaches the
  manifest.
- If we skip it: the owner's rule «never train on these» depends on memory.
- Proof: `grep -n "164121\|kept" ml/datasets.py ml/*.ipynb` finds no exclusion list.
- Verifier: CONFIRMED (code). The verifier proposed Should because nothing breaks on a printer. It stays Must because
  CLAUDE.md section 3 makes it the owner's rule.

### Should fix

#### 23. The «no app published» message never shows (F024)
`frontend/src/app/59c-app-update.js:164`
- What happens: the page tests `/nessuna app/i`, an Italian text, against the backend's English reason.
- Case: a printer with no published app shows the error branch for a normal state.
- Fix: test a reason code (or at least `/no app published/`).
- If we skip it: a false failure on every printer without an app.
- Proof: `python3 -I $P/L/nessuna_app.py` prints `matches: False`.
- Verifier: REPRODUCED; moved from Must (a wrong message, no harm).

#### 24. The Android bridge is open to every frame of every origin (F025)
`android/.../MainActivity.kt:135, 188-197, 488-593`, `frontend/src/app/41-camera.js:602`
- What happens: `addJavascriptInterface` exposes the bridge to all frames, and `DashboardBridge` checks no origin.
- Case: a web-page camera in an iframe can call `notifySetup` with any public server, `setCertificate`,
  `setAddresses`, `saveUrl` and `updateApp`.
- Fix: `WebViewCompat.addWebMessageListener` with an allowed-origin rule, or check the main frame's origin in each call.
- If we skip it: any page in the camera frame controls the app's notifications and addresses.
- Proof: `python3 -I $P/M/bridge_mirror.py` (Python mirror of the Kotlin rules).
- Verifier: CONFIRMED (code), Kotlin not run; moved from Must (it needs a hostile page inside the camera frame).

#### 25. The APK signing key is public and protected only by its password (F026)
`android/chiave/klippeye.p12`, `ci/app_ci.py:30, 150-152`, `CONTRIBUTING.md:60`
- What happens: the p12 is in the public repo; CI only checks that the password has 16 or more characters. The guide
  suggests «a sentence of four or five words», which can be guessable.
- Case: anyone can attack the file offline; a found password signs an update Android accepts.
- Fix: suggest a random passphrase in the guide, or keep the key only as a GitHub secret. The owner is the only user,
  so a new key costs one reinstall.
- If we skip it: the whole update chain rests on one password that can be attacked in private.
- Proof: `openssl pkcs12 -info -in android/chiave/klippeye.p12 -noout -passin pass:x` shows `MAC: sha256, Iteration 10000`.
- Verifier: PARTLY; moved from Must (a documented choice; cracking was not shown, and an attacker still has to deliver
  the APK).

#### 26. HTTPS pinning is bypassed by a downgrade to http (F027)
`android/.../Addresses.kt:40-41`, `MainActivity.kt:255-256, 212-220`
- What happens: `variants()` always lists the http addresses after https, and `find()` takes the first that answers.
- Case: an attacker on the LAN or VPN blocks 443 and serves an http page, which gets the bridge.
- Fix: when a certificate is pinned for the host, try only https, and compare the scheme in `shouldOverrideUrlLoading`.
- If we skip it: the pinning gives a false sense of safety.
- Proof: `python3 -I $P/M/bridge_mirror.py` (`pinned host still tries: [https, http, http:8085]`).
- Verifier: CONFIRMED (code); moved from Must (needs an active attacker on the private network).

#### 27. A print that was recorded and answered is trained twice, in two groups (F029)
`ml/datasets.py:312-325` against `ml/evaluate.py:134-138`
- What happens: the recording and the review of one print get two group keys.
- Case: the group split can put one copy in training and the other in the measuring set, which skews `train.py`'s own
  numbers and the chosen threshold. A kept-out list by id would also miss the review.
- Fix: group by `evaluate.same_print_once`'s match (move it to `labelled_prints.py`).
- If we skip it: slightly too good numbers, and a hole in finding 22's guard.
- Proof: `python3 -I $P/N/same_print_twice.py` prints two groups while evaluate counts the print once.
- Verifier: REPRODUCED; moved from Must.

#### 28. A light switched on during a print triggers the motion detection (F034)
`backend/monitor_core.py:51, 349-357, 306`
- What happens: the «whole picture changed» streak gives up after 10 checks (30 s), before the median background
  follows a new light level (about 34 s).
- Case: a lamp lights half the scene and stays on: score 98.9 and a trigger 33 s later. With a streak of 14 there is
  none.
- Fix: work the streak out from the background's turnover in `apply_config` (13 at the defaults), and update the test.
- If we skip it: one false alarm, and maybe one paid call, every time a light changes.
- Proof: `python3 -I $P/A/proof7.py` (trigger) and `python3 -I $P/A/proof7b.py` (none).
- Verifier: REPRODUCED. «Always» is too strong: it needs a light change the background takes longer than 30 s to follow.

#### 29. The monitor and web requests share one last-vector variable (F036)
`backend/klippeye_backend.py:2557, 3817, 3830, 3898`
- What happens: `local_judge` writes `self.local_vec`; the label routes and `refresh_false_alarms` read it after a
  separate call, from other threads.
- Case: the person marks an alarm «false» while the monitor checks: the live picture's vector is stored as a known
  false alarm, which can later silence a real failure.
- Fix: return the vector from `local_judge` instead of keeping it in an attribute.
- If we skip it: rare, and with no trace when it happens.
- Proof: code at the lines above.
- Verifier: CONFIRMED (code).

#### 30. FalseAlarms.refresh holds the lock while the model runs on every picture (F037)
`backend/false_alarms.py:153-183`
- Case: after a model update, `match()` (called at every local look) waited 3.7 s for 20 alarms; 300 alarms would be
  about a minute with no local looks.
- Fix: compute the new vectors outside the lock and lock only to swap them in.
- If we skip it: the monitor is deaf for up to a minute after every model change.
- Proof: `python3 -I $P/B/refresh_blocks_match.py`.
- Verifier: REPRODUCED.

#### 31. keep_examples redoes hundreds of pictures at every call once fine examples pass the cap (F038)
`backend/personal_layer.py:85-124`
- Case: evicted fine copies are copied again on the next call: 600 pictures decoded and re-encoded on runs 2 and 3 with
  nothing new. Label and delete routes wait for it.
- Fix: stop copying fine pictures beyond the cap, or remember evicted keys.
- If we skip it: minutes of SD-card writes per answer, maybe during a print.
- Proof: `python3 -I $P/B/keep_churn.py`.
- Verifier: REPRODUCED.

#### 32. Past 1,500 failed examples the newest failed prints are never learned (F039)
`backend/personal_layer.py:308-312`
- Case: `failed_ones[:1500]` takes the oldest: with 6 failed prints (4,290 examples) only fail0 to fail2 are used.
- Fix: pick failed examples evenly, like the fine ones.
- If we skip it: the layer stops learning from this printer after about 5 failed prints, and nobody is told.
- Proof: `python3 -I $P/B/newest_failures_dropped.py`.
- Verifier: REPRODUCED.

#### 33. The recorder deletes whole folders under its lock, in the monitor's thread (F041)
`backend/recorder.py:156-188, 315-319, 372-388`
- Case: when the size limit is reached, the 20th `add_frame` walks every folder and runs `rmtree` while holding the
  lock: 0.38 s on a fast disk, seconds on an SD card.
- Fix: size scan once at start in the background; under the lock only rename the folder away, delete it in a thread.
- If we skip it: a pause of the monitor each time the 2,000 MB limit is reached (about every 6.5 days of printing with
  recording on).
- Proof: `python3 -I $P/B/recorder_lock.py`.
- Verifier: REPRODUCED.

#### 34. An unreadable first AI answer ends the analysis; the backup is not asked (F043)
`backend/klippeye_backend.py:2926-2927, 2990-2996`
- Case: Groq answers 200 with prose; `ok: True, parsed: None` counts as an answer, the alert says «AI answer not
  readable» and Gemini is never tried.
- Fix: in `_ask_chain`, treat `parsed is None` like a failure and try the next service.
- If we skip it: one badly written answer silences an alarm a backup could have confirmed.
- Proof: `python3 -I $P/C/proof3.py` (case 5: calls `['groq']` only).
- Verifier: REPRODUCED.

#### 35. normalize_action matches substrings, so the template text or a negation becomes a stop (F044)
`backend/klippeye_backend.py:2092-2102`
- Case: `CONTINUE|PAUSE|CANCEL` (the template echoed back) gives CANCEL; «PAUSE (do not cancel)» gives CANCEL;
  «Continue, no need to pause» gives PAUSE.
- Fix: read the first action word only (`re.match(r"\W*(CANCEL|PAUS|CONTIN)", text)`).
- If we skip it: a model that copies the template proposes the strongest action. The second look softens it.
- Proof: `python3 -c "import sys;sys.path.insert(0,'backend');import klippeye_backend as k;print(k.normalize_action('CONTINUE|PAUSE|CANCEL'),k.normalize_action('PAUSE (do not cancel)'),k.normalize_action('Continue, no need to pause'))"`.
- Verifier: CONFIRMED (code), low end of Should.

#### 36. Two analyses can run at once (F045)
`backend/klippeye_backend.py:2476, 2956-2964, 3003-3007`
- Case: `ai_cooldown` can be 30 s while one analysis with a second look takes 40 s plus up to 30 s. Two alarms 1.2 s
  apart (scaled) gave 4 requests and 2 alerts, and `last_analysis` can go back in time.
- Fix: a lock on the detector taken with `acquire(blocking=False)` at the top of `call_ai_analysis`.
- If we skip it: duplicate paid calls and a verdict that jumps backwards while a stop is being confirmed.
- Proof: `python3 -I $P/C/proof2.py` (case 4).
- Verifier: REPRODUCED.

#### 37. Two clients saving AI keys at once lose most of them (F046)
`backend/klippeye_backend.py:1620-1625`
- Case: 9 clients each save a different service's key at the same moment, 30 rounds: 270 answered «ok», 68 keys on
  disk. The page saves one at a time, so it needs two devices.
- Fix: one module lock around read, apply and `write_json_atomic`.
- If we skip it: «saved» for a key that is not there.
- Proof: `python3 $P/X2/run_race.py 30`.
- Verifier: REPRODUCED.

#### 38. A wrong guess of what Z moves gives a usable calibration and inverted Z arrows (F047)
`backend/camera_calibration.py:121-130, 798`, `frontend/src/app/13-capabilities.js:90-95`, `app/44-movement.js:32, 280-285`
- What happens: `guess_z_moves` / `guessZMoves` say «bed» for CoreXZ (the toolhead moves in Z) and «toolhead» for a
  cartesian cube whose bed moves in Z. The Z buttons flip their sign by this value, and use «bed» while capabilities
  are not loaded.
- Case: with the wrong choice the fit is still rated «fair» (seeds 0 to 2), and on a CoreXZ the «up» arrow lowers the
  nozzle until the person changes Settings, Motion.
- Fix: «toolhead» for `corexz` in both copies; a check like `bed_moves_in_y` for Z; disable the Z jog while the value
  is unknown. Add `guessZMoves` to the «written twice» list in CLAUDE.md.
- If we skip it: a nozzle driven into the bed by a button that looks right.
- Proof: `python3 -I $P/D/d4_guess_kinematics.py` and `python3 -I $P/D/d4b_wrong_choice_fit.py`.
- Verifier: REPRODUCED for the guess and the fit; the inverted arrows were not run.

#### 39. Dragging a bed corner or correcting the camera empties the false-alarm memory until a restart (F048)
`backend/klippeye_backend.py:4709-4717, 3197-3210`
- What happens: `memory_version` includes the bed box and `FalseAlarms.match` needs the same version, but the bed
  corner and correction routes do not call `_view_changed` (only save and forget do).
- Case: after one drag of the 1.136.0 corner dots, no kept false alarm matches any more.
- Fix: call `_view_changed()` in those routes and when the camera watch corrects a move.
- If we skip it: small edits quietly undo what the person taught the monitor.
- Proof: code at the lines above. Test: add an alarm, call `set_bed_corner` through the route, `match` must still find it.
- Verifier: CONFIRMED (code).

#### 40. Through the HTTPS relay a client can set its own X-Forwarded-For (F049)
`backend/https_relay.py:81-98, 160-165`
- What happens: only the first request head is rewritten; with any `Upgrade:` header the connection stays open.
- Case: the second request on the connection reaches the service with `X-Forwarded-For: 10.9.9.9`, which the backend
  trusts from 127.0.0.1. The password throttle is per address, so guessing on 8443 is unlimited.
- Fix: close after one response unless the head is a real WebSocket upgrade (GET with `Upgrade: websocket`).
- If we skip it: unlimited password guessing and made-up addresses in the logs.
- Proof: `python3 -I $P/E/relay.py`.
- Verifier: REPRODUCED.

#### 41. File names with # or ? break, and a delete can hit another file (F050)
`backend/klippeye_backend.py:1137-1141, 1287-1292`
- Case: `part #2.gcode` reaches Moonraker as `part%20`; a DELETE of `part?v=2.gcode` deletes `part`.
- Fix: `urllib.parse.quote(path, safe="/")` when building the Moonraker URL.
- If we skip it: some files cannot be opened or deleted, and once in a while the wrong file is deleted.
- Proof: `python3 -I $P/E/probe.py 2>&1 | sed -n '/== 2/,/== 3/p'`.
- Verifier: REPRODUCED.

#### 42. Wrong passwords sent at the same moment are checked together (F051)
`backend/klippeye_backend.py:495-509`, `backend/access.py:282-307`
- Case: 12 wrong passwords right after the wait ran out: 4 were checked at once, 8 were told to wait. The throttle sets
  the wait only after a failure.
- Fix: a `begin(ip)` that counts the attempt before checking.
- If we skip it: guessing runs a few times faster than the throttle says, and each burst loads the Pi with PBKDF2.
- Proof: `python3 -I $P/E/throttle.py`.
- Verifier: PARTLY (the race is real; the number checked at once is bounded by the thread count, not «all»).

#### 43. With a password on, the camera on port 80 is open to everyone (F052)
`scripts/web_front.py:101, 146-147`
- Case: the copied `/webcam` blocks have no `auth_request`, while 8085 needs the login.
- Fix: `auth_request /_klippeye_auth;` in each camera block; guests keep access through `/api/auth/check`.
- If we skip it: a privacy hole the owner does not expect; the guide does not mention it.
- Proof: `python3 -I $P/E/probe.py 2>&1 | sed -n '/== 4/,/== 5/p'` (`location /webcam/ auth_request: False`).
- Verifier: REPRODUCED. The same camera was open on that nginx before KlippEye.

#### 44. A slicer's connection test passes with the password on, then every upload fails (F054)
`backend/klippeye_backend.py:477, 3383-3384, 1267-1277`
- Case: `GET /api/version` from a slicer answers 200, `POST /api/files/local` answers 401.
- Fix: drop the slicer exception at line 477 so the test fails honestly, and say so in the guide.
- If we skip it: a confusing half-working state.
- Proof: `python3 -I $P/E/probe.py 2>&1 | sed -n '/== 5/,/== 6/p'`.
- Verifier: REPRODUCED.

#### 45. Adding the include turns a symlinked printer.cfg into a plain file (F055)
`backend/printer_macros.py:180-200`, `backend/atomic.py:9-20`
- Case: `printer.cfg` linked into a config repository: `os.replace` replaces the link, and the repository's file never
  gets the include.
- Fix: in `atomic.write_text`, write to `os.path.realpath(path)`.
- If we skip it: the config folder forks quietly, and a later `git pull` of the config drops the include.
- Proof: `python3 -I $P/F/include_symlink.py` prints `printer.cfg still a link: False`.
- Verifier: REPRODUCED.

#### 46. MQTT keeps saying «printing» while Klipper is down (F056)
`backend/mqtt_bridge.py:279-286`, `backend/klippeye_backend.py:5092-5102`
- Case: Moonraker answers but Klipper is down; `tick()` publishes nothing and the retained state stays «printing».
- Fix: publish `state = "offline"` once when the read fails.
- If we skip it: an automation that acts when the print ends or fails never fires after a Klipper crash.
- Proof: `python3 -I $P/F/mqtt_stale.py`.
- Verifier: REPRODUCED.

#### 47. Two printers with the default host name share one MQTT client id (F057)
`backend/mqtt_bridge.py:47-49, 206-207`, `backend/mqtt_client.py:236-254`
- Case: both Pis are `klippeye-raspberrypi`; the broker drops the older connection and they reconnect every 2 s.
- Fix: add a stable per-machine suffix (from `/etc/machine-id`) to the client id.
- If we skip it: MQTT breaks for both printers, and the page shows «connected» most of the time.
- Proof: `python3 -I $P/F/mqtt_stale.py` (same client id twice).
- Verifier: REPRODUCED for the id; the broker loop is standard MQTT behaviour, not run.

#### 48. «Sure from» can end up below «In doubt from» (F059)
`backend/klippeye_backend.py:844-905`
- Case: a hand-edited `monitor.json` with doubt 90 and sure 50 is loaded as it is, while the page refuses the same pair.
- Fix: in `load()`, put both keys back to the defaults when the pair is wrong; hold the lock from merge to save.
- If we skip it: the model is «sure» before it has a doubt, and the ask rules fire on harmless scores.
- Proof: `python3 -I $P/F/monitor_json_pair.py`.
- Verifier: REPRODUCED for the file; the lock window did not open in 30 rounds.

#### 49. After a failed automatic pause, the later successful pause is never announced (F060)
`notifier/klippeye_notifier.py:621-629, 693-706, 779`
- Case: the first pause fails (Moonraker busy), the retry succeeds within the 180 s cooldown, and both «AI paused» and
  «Printer paused» are held back as repeats.
- Fix: let the result of an automatic action skip the cooldown.
- If we skip it: the person may walk to a printer that is already paused, or think it still prints.
- Proof: `python3 -I $P/G/proof_cooldown.py` (`after the successful automatic pause: []`).
- Verifier: REPRODUCED.

#### 50. One unreachable channel delays every later notice on the working one (F061)
`notifier/klippeye_notifier.py:1408-1426, 1456-1476`
- Case: one outbox thread retries a notice for up to 3 h; ntfy gets the second notice only when the first gives up.
- Fix: put a notice that still owes channels back at the end of the queue with its retry time, or one outbox per
  channel.
- If we skip it: with two channels, the working one goes silent when it is needed.
- Proof: `python3 -I $P/G/proofs.py` (P3).
- Verifier: REPRODUCED.

#### 51. «Is it printing?» counts a slow answer as «not printing», so Moonraker is restarted mid-print (F062)
`scripts/install.sh:235-245, 320-324, 341, 609-614`, `backend/klippeye_backend.py:3332-3337, 3354`
- Case: Moonraker says «printing» but answers in 5 s on a busy Pi: `is_printing` exits 1 and the installer (or a
  channel change) restarts Moonraker.
- Fix: an unknown answer counts as printing (install.sh and the route).
- If we skip it: re-running the installer during a long print can end it.
- Proof: `python3 -I $P/H/printing_slow.py`.
- Verifier: REPRODUCED.

#### 52. A git lock left by a power cut looks like a running update while the Pi's clock is behind (F063)
`scripts/repair.sh:70-84`
- Case: after the reboot the lock seems -2,390 s old, repair says «try again in a moment», and the half-written
  dashboard (0 bytes) is not repaired.
- Fix: treat a negative age as stale, or rely on `pgrep -x git` alone.
- If we skip it: after the very power cut repair.sh exists for, the dashboard can stay blank until the Pi gets the time.
- Proof: `bash $P/H/lock_clock.sh`.
- Verifier: REPRODUCED.

#### 53. repair.sh says «All program files are intact» when git's own copy is damaged (F064)
`scripts/repair.sh:93-110`
- Case: an empty tree object after a power cut: `git ls-tree` fails, the error is hidden, the list is empty, and the
  script reports success while the backend file is half written.
- Fix: run `git ls-tree` into a temp file first and report «git data damaged, Recover» when it fails.
- If we skip it: the self-repair reports success and the person is not told to run Recover.
- Proof: `bash $P/H/tree_damaged.sh`.
- Verifier: REPRODUCED.

#### 54. Back and Escape do not close ConfirmDialog (F065)
`frontend/src/app/20-ui-primitives.js:358-386`, `app/15a-back.js:32-42`
- Case: open the save-config dialog and press the phone's back button: `klippeyeBack()` returns true, so the app stays,
  but the dialog stays open. Escape does nothing either.
- Fix: `useBackHandler(onCancel, open)` inside `ConfirmDialog` (and in the hand-made dialogs, structure R11).
- If we skip it: the back button feels broken on every confirmation, on a phone.
- Proof: `cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../$P/I/confirm_back.py
  ../../frontend/klippeye_frontend.html 8792`.
- Verifier: REPRODUCED.

#### 55. The list of Moonraker components is read once per page load (F066)
`frontend/src/app/12-api.js:189-203`
- Case: the dashboard's own timelapse set-up restarts Moonraker with the new component, but the tab stays hidden until
  a manual reload (1 request before the restart, 0 after, even after an `online` event).
- Fix: clear `moonrakerInfoAsk` in `onKlipperReady`.
- If we skip it: «I turned it on and nothing shows».
- Proof: `cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../$P/I/components_cached.py
  ../../frontend/klippeye_frontend.html 8793`.
- Verifier: REPRODUCED.

#### 56. Pins that are not lights are offered as lights (F067)
`frontend/src/app/16a-printer-functions.js:22, 72-75`, `backend/printer_lights.py:17, 114`
- Case: substring match on `case`, `chamber`, `led`: `chamber_heater_relay` and `psu_enabled` become light switches
  that send `SET_PIN ... VALUE=1`, in the dashboard and through MQTT.
- Fix: whole-word match on light words, and no `case`/`chamber` for plain pins. Change both copies.
- If we skip it: a relay or heater pin switched by a tap or by Home Assistant.
- Proof: `python3 -I $P/I/light_words.py`.
- Verifier: REPRODUCED.

#### 57. Quick taps on a jog button collapse into one move (F068)
`frontend/src/app/44-movement.js:21`, `app/12-api.js` (gcodeGuard)
- Case: five taps on Z -1 within half a second send 2 moves, while each tap shows a toast.
- Fix: do not run jog scripts through the duplicate guard, or key it on a tap id.
- If we skip it: a wrong Z by hand; on a printer whose bed moves in Z this can crash the nozzle.
- Proof: `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 $P/J/p2_jog_taps_collapsed.py`.
- Verifier: REPRODUCED.

#### 58. A refused jog leaves the printer in relative mode (F069)
`frontend/src/app/44-movement.js:21`, `app/48-extruder.js`
- Case: `G91`, `G1 ...`, `G90` go as one script; Klipper stops the script at a refused G1 and G90 never runs.
- Fix: send G90 in a follow-up request, or wrap the move in `SAVE_GCODE_STATE` / `RESTORE_GCODE_STATE`.
- If we skip it: the next absolute move from a macro or console goes to the wrong place.
- Proof: code; not run (no printer here).
- Verifier: CONFIRMED (code).

#### 59. The G-code viewer rescans every segment on each render (F070)
`frontend/src/app/49a-gcode-viewer.js:468`
- Case: the «kinds present» filter has no memo: 50.6 ms per render here, 3 to 8 times slower on a phone, on every
  pointer move.
- Fix: compute it once when the model is set (`useMemo`).
- If we skip it: pan stutters on large files.
- Proof: `node .superpowers/audit/proofs/J/p3_gcode_viewer_rescan.js` (kept outside git).
- Verifier: REPRODUCED.

#### 60. «Clear console» compares the phone's clock with the Pi's (F072)
`frontend/src/app/46-console.js:26, 102, 197`, `app/44a-bed-tools.js`
- Case: with the phone's clock off, new lines stay hidden after Clear, or cleared lines come back.
- Fix: clear by line count or sequence number.
- If we skip it: missing console lines when they matter.
- Proof: `node .superpowers/audit/proofs/J/p4_console_clear_clock.js` (kept outside git).
- Verifier: REPRODUCED.

#### 61. The print-metadata cache serves a stale file (F073)
`frontend/src/app/45-print-progress.js:87-104`
- Case: keyed by name only, a re-sliced file under the same name shows 3,600 s instead of 7,200 s, and the old layers
  and thumbnail.
- Fix: key by name plus `modified`.
- If we skip it: a wrong «time left» on every re-sliced print.
- Proof: `node .superpowers/audit/proofs/J/p5_print_metadata_cache_stale.js` (kept outside git).
- Verifier: REPRODUCED.

#### 62. Camera snapshots have no stall watchdog (F074)
`frontend/src/app/41-camera.js:538-589`
- Case: only `onload`/`onerror` schedule the next frame; a half-open request fires neither, so the picture freezes with
  no sign that it is old.
- Fix: a timer per frame (for example three times the interval) that moves on.
- If we skip it: a frozen camera that looks live, during a print.
- Proof: code; reasoned, not run.
- Verifier: CONFIRMED (code), low impact.

#### 63. «Save and restart» says Klipper restarts when Klipper refused SAVE_CONFIG (F077)
`frontend/src/app/51-config-editor.js:353-359`, `app/12-api.js:45`
- Case: SAVE_CONFIG answered 400 («Unable to parse config»), yet the editor shows «Klipper si riavvia ✓» and closes.
- Fix: check `r.ok` after `sendGcode("SAVE_CONFIG")` and throw into the existing error path.
- If we skip it: a broken `printer.cfg` looks applied until the next print.
- Proof: `cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../$P/K/save_config_rejected.py
  ../../frontend/klippeye_frontend.html /tmp/k9 8801`.
- Verifier: REPRODUCED.

#### 64. A confirmation opened while idle does not check the print lock when it is confirmed (F078)
`frontend/src/app/57b-shaper.js:497-503`, `app/58-bed-mesh.js:545-549, 624-627`
- Case: the shaper dialog is opened while idle, a scheduled print starts, the person taps «Measure»: G28 and
  SHAPER_CALIBRATE are sent during the print although the button is now disabled.
- Fix: check `lockReason` again at the top of the confirm callbacks.
- If we skip it: a ruined print; scheduled prints make it likelier.
- Proof: `cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../$P/K/stale_lock.py
  ../../frontend/klippeye_frontend.html /tmp/k4 8794`.
- Verifier: REPRODUCED.

#### 65. In the default «simple» macro mode every macro is one tap, also during a print (F079)
`frontend/src/app/57-calibration.js:321-327, 339-342`, `app/16-settings.js:168`
- Case: one tap on CLEAN_NOZZLE during a print sends it, with no lock and no question.
- Fix: while printing or paused, ask with `ConfirmDialog` first.
- If we skip it: a pocket tap moves the toolhead mid-print.
- Proof: `cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../$P/K/macro_during_print.py
  ../../frontend/klippeye_frontend.html /tmp/k5 8795`.
- Verifier: REPRODUCED.

#### 66. System logs open in the editor as writable config files (F080)
`frontend/src/app/54-logs.js:231-236`, `app/99-main.js:154`, `app/51-config-editor.js:434-457`
- Case: no read-only badge, and Save uploads a 3,000-line `klippy.log` copy into the config folder.
- Fix: `onEditFile(name, content, { readOnly: true })` in `openLog`; the editor already supports it.
- If we skip it: stray log copies in the config folder and an editor that looks like it edits the real log.
- Proof: `cd tests/ui && PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers python3 ../../$P/K/log_editor_writable.py
  ../../frontend/klippeye_frontend.html /tmp/k2 8792`.
- Verifier: REPRODUCED.

#### 67. A macro parameter with a space is sent unquoted (F081)
`frontend/src/app/57-calibration.js:184-188`, `backend/macro_catalog.py:45-50`
- Case: `MSG=hello world` gives «Malformed command» in Klipper; `MSG="hello world"` works.
- Fix: wrap text values that contain a space or a quote in double quotes.
- If we skip it: macros with text parameters fail whenever the value has two words.
- Proof: `python3 -I $P/K/macro_param_space.py`.
- Verifier: REPRODUCED.

#### 68. An update longer than 12 s over the websocket is retried by HTTP and shown as failed (F082)
`frontend/src/app/56-system.js:22, 120-140, 166-182, 504-526`
- Case: the websocket call rejects at 12 s while Moonraker still updates; the HTTP retry gets «update in progress»,
  which `isBusyError` does not match, and the page shows «Failed».
- Fix: on a websocket timeout go straight to `watchUpdate()`.
- If we skip it: «Failed» next to a successful update, and a second tap on Update.
- Proof: code; not run (it assumes Moonraker answers the upgrade call only at the end).
- Verifier: CONFIRMED (code).

#### 69. The signing password is in the environment of the whole Android job (F090)
`.github/workflows/app.yml:35-47, 50-82`
- Case: the job-level `env` exposes the password to setup-java, setup-android and gradle actions pinned by movable tag,
  in a job with `contents: write`.
- Fix: put the secret only on the steps that need it, and pin the third-party actions to commit SHAs.
- If we skip it: one supply-chain incident gives away the key every phone trusts.
- Proof: read the workflow lines above.
- Verifier: CONFIRMED (code).

#### 70. The licence filter fails open (F092)
`ml/download.py:33-48, 117-121`
- Case: «CC BY NC 4.0», «CC BY SA 4.0» and «CC BY ND 4.0» written with spaces are kept, because the code strips the word
  and finds «CC BY 4.0». ODbL, GPL and an empty licence are kept too, only marked «check».
- Fix: keep a dataset only if `licence_is_open` (an allow-list) unless `--any-licence`, and print what was left out.
- If we skip it: a non-shareable dataset can end up in a model published under GPL-3.0.
- Proof: `python3 -I $P/N/licence_filter.py`.
- Verifier: PARTLY (the hyphenated forms Roboflow usually writes are caught).

#### 71. The dashboard cannot use a pca9533 or pca9632 light; the MQTT bridge can (F102)
`frontend/src/app/16-settings.js:247`
- Case: `cleanObjectName` forbids digits in the kind, so these lights are cleaned to `""` and dropped. Of 1,500 random
  printers, 417 differ between the two copies of the light rules, all because of a pca output.
- Fix: `/^[A-Za-z_][A-Za-z0-9_]* [^\n]{1,80}$/`. Keep the script as the test.
- If we skip it: owners of these LEDs have no light button.
- Proof: `python3 -I $P/X1/lights_pair.py` prints `1500 random printers, 417 differ`.
- Verifier: REPRODUCED.

#### 72. A restart during a print splits its recording, and «failed at …» then labels no recording (F103)
`backend/klippeye_backend.py:4006-4015`, `backend/recorder.py:107-119`
- Case: a restart 2 h into a 3 h print leaves recordings A (0 to 2 h) and B (2 to 3 h) and one review. The answer
  «failed at 2.5 h» returns 200, both labels stay empty, and the log says `failed_at must be a moment of the recording`.
- Fix: label every recording of the same file whose span overlaps the review, with `failed_at` only where it falls.
- If we skip it: the failed prints that matter most for learning are never labelled.
- Proof: `python3 -I $P/X2/split_label.py`.
- Verifier: REPRODUCED.

#### 73. A delta gets the default gantry mask, which hides bed it should watch (F104)
`backend/machine_masks.py:22-25`, `backend/camera_calibration.py:1042-1060`
- Case: `DEFAULT_SHAPE` turns the gantry on for every printer. On a simulated delta, the bed left out at one check grows
  from 46.1 % to 67.7 % at y = -60.
- Fix: store `gantry.on = false` when the kinematics is `delta` and the person never saved a shape.
- If we skip it: strands near the nozzle's row are not seen on a delta, for no reason the person can find.
- Proof: `python3 -I $P/X2/delta_gantry.py`.
- Verifier: REPRODUCED; the owner can switch the gantry off in settings.

## 3. Look

The look pass took 254 pictures from the mock server: every tab and Settings page at 360 and 1280 px, other widths and
the light theme, eight states, and German, Polish, Russian (plus Home and the menu in six more languages). Each picture
was measured in the page. The pictures are in `.superpowers/audit/shots/` (outside git); `$P/V/shots.py` and
`$P/V/pidown.py` make them again. The design rules hold well overall. No page scrolls sideways in any of the 252
measured pictures, no HTML text is under 12 px, and the light theme reads correctly.

#### 74. The phone's tab bar shows «Files» and «Config» in English in every language (F105)
`frontend/src/app/33-bottom-nav.js:38-44`, `app/70-desktop-shell.js:47`, `app/99-main.js:84`
- Case: `360-dark-pl-home.png` reads «Home / Sterowanie / Files / Config / System». `pl.json` has «Pliki» for «Files»;
  «Config» has no key in any of the 9 files.
- Fix: wrap the labels in `tx()` (build the array in a function so the language is known), and add «Config» or decide
  it stays a loanword.
- If we skip it: the main navigation looks half translated in 8 languages.
- Verifier: CONFIRMED (code and picture).

#### 75. Touch targets under 44 px on every page (F106)
`frontend/src/css/15-surfaces.css:100` (`.oui-card__fold`), `.fan-step`, `.header-btn`, `.help-btn`, `.file-card__more`
- Case: 252 of 252 pictures have at least one: 36 px fold chevrons, fan steps and header menu button; 40 px emergency
  stop next to save and power; 34 px help buttons; 28 px file menu; a 48 by 28 AI badge.
- Fix: raise the hit area, not the look (`::after` with `inset: -4px`).
- If we skip it: mis-taps with a thumb on a shaking printer, the emergency stop included.
- Verifier: CONFIRMED (measurements in `shots/measure.jsonl`).

#### 76. The brand name is cut to «KlippE…» at 360 and 412 px (F107)
`.app-header__name`
- Case: cut by 3 px in 151 pictures (`360-dark-en-home.png`); at 320 px it fits.
- Fix: take 3 px from the AI badge's margin or the gap between the round buttons.
- If we skip it: the brand is the first thing on every page.
- Verifier: CONFIRMED (picture).

#### 77. Fan names are cut in German, Polish and Russian (F108)
fan rows in `frontend/src/css`
- Case: `360-dark-pl-home.png`: two fans both read «Wentylato…».
- Fix: let the name wrap to two lines in the short rows, as the long rows do.
- If we skip it: in 3 languages two fans have the same visible name.
- Verifier: CONFIRMED (picture).

#### 78. Pi not answering: Home shows no sign for at least 12 s (F109)
connection strip, `frontend/src/app/15-live.js:193`
- Case: `360-state-piDown-12s.png` shows temperatures «0.0° / 0°», the header still says «Ready» on the computer, and no
  banner after 6 and 12 s.
- Fix, if it is real: show the strip before the cards turn to zero.
- If we skip it: the person reads zeros as real temperatures.
- Verifier: PARTLY. The strip exists, but the mock fails only `/printer/*`; the real Pi timing was not checked.

Static counts (Nice to have, details in F134 to F137 and F170):
- 244 hand-written colours in `frontend/src/css` outside `00-tokens.css`, `05-light.css` and `90-looks.css` (biggest:
  `65-settings.css` 48, `41-camera.css` 19, `65b-camera-calibration.css` 19); 102 colour literals in JS (the editor's
  syntax colours are allowed). The count was taken differently from the 17 Nov figure of 293, so no trend can be told.
- Radii outside the scale: 5 real ones, all in `65-settings.css` (the others are previews or the nav pill).
- Font sizes outside the scale: `0.88em` and `0.92em`; `fontSize` 9, 10 and 11 in the guide's SVG figures
  (`59j-help.js`, text people read).
- 9 `text-transform: uppercase` labels, unchanged since 17 Nov; German caps headings wrap in the Settings drawer.
- 23 classes used by the page with no CSS rule; most are test hooks, but `ai-question--warn` looks meant to change the
  alarm card and does nothing.

Pictures the owner should check on his phone:
1. Home at 360 px during a print: is the brand cut, can the thumb hit emergency stop without hitting save.
2. The alarm card: «Real problem / False alarm / Ignore», Pause and Cancel under a thumb, and the amber card over the
   real camera picture.
3. The floating tab bar with gesture navigation: does it cover the last card.
4. The fan sliders and the 36 px -/+ buttons, with a wet or gloved finger.
5. The 36 px fold chevrons on Home and Control.
6. The Settings drawer in German and Polish: long headings on two lines, scrolling inside the drawer in the WebView.
7. The light theme in the Android WebView: status bar colour and the top edge.
8. Pi not answering: switch the Pi's Wi-Fi off with the app open and look at Home after 10 s (finding 78).
9. Files with real G-code thumbnails: names that wrap on three lines.
10. The small camera window above the tab bar and full screen with the real WebRTC page.

## 4. Tests and CI

The base runs: `tests/backend/test_backend.py` passed at f0552fb (712 PASS, 0 FAIL). None of the Must findings has a
test today (F032). By project rule each fix PR adds the failing test from its proof command, so that is not listed as a
separate item.

#### 79. The Colab notebook measures on the prints it just trained on (F030)
`ml/KlippEye_local_model.ipynb` cells 8 and 12
- Case: cell 8 trains with `--klippeye /content/klippeye-data/klippeye` and cell 12 runs `evaluate.py` on that folder.
- Fix: measure only on a second zip that was not trained on, or print a warning that the number is not independent.
- If we skip it: someone builds a model, reads «0 false alarms an hour», and ships it unmeasured.
- Proof: read the two cells.
- Verifier: CONFIRMED (code); moved from Must.

#### 80. A red End-to-end run does not stop a release (F031)
`.github/workflows/release.yml:9-13`, `ci/release.py:62-95`
- Case: `release.yml` waits for Tests and the Android app only; `e2e.yml` (install, update, uninstall, repair) is not
  read. A direct push to main or a failure seen only on main slips through.
- Fix: move the e2e job into `tests.yml` and delete `e2e.yml`.
- If we skip it: a broken installer or updater can reach the stable channel.
- Proof: `grep -n "e2e\|End-to-end" ci/release.py .github/workflows/release.yml` prints nothing.
- Verifier: CONFIRMED (code); moved from Must (PR CI already runs e2e and merges wait for green).

#### 81. Five working browser tests never run in CI (F033)
`tests/ui/run_all.sh:8`
- Case: the hand-written list leaves out `print_review_test`, `temp_presets_test`, `theme_mode_test`, `tidy_test`,
  `visual_test`. The verifier ran two of them: both pass.
- Fix: loop over `*_test.py` with a short SKIP list.
- If we skip it: a change that breaks the light theme or the review card merges green.
- Proof: `python3 -I $P/O/unlisted_ui_tests.py`.
- Verifier: REPRODUCED; moved from Must.

#### 82. The replay measures a different monitor from the live one: no purge marks (F035)
`scripts/replay.py:120-176`, `backend/klippeye_backend.py:2447-2450`, `backend/recorder.py`
- Case: the live loop ORs `self.purge["marks"]` into the ignored area; the recordings do not keep them and the replay
  builds `ignore` from the masks only, so replay alarm counts include changes the live monitor never sees.
- Fix: the recorder keeps the purge mask once per recording, and the replay uses it (structure proposal 1).
- If we skip it: thresholds chosen from replays are tuned against alarms that do not happen live.
- Proof: `grep -n "purge" scripts/replay.py backend/recorder.py` (no hits).
- Verifier: CONFIRMED (code).

#### 83. A dataset interrupted in the middle counts as complete (F096)
`ml/download.py:109-113`
- Case: a non-empty folder counts as «already here», and `klippeye-source.json` is written anyway, so a killed download
  stays partial for good.
- Fix: count a folder as done only when `klippeye-source.json` exists.
- If we skip it: a smaller training set with no trace in the log.
- Proof: read the lines above.
- Verifier: CONFIRMED (code).

#### 84. Tests that cannot fail (F098)
`tests/ui/tools_test.py:76`, `tests/notifier/test_integration.py:96`, `tests/backend/test_backend.py:1003`, and others
- Case: conditions like `... or True`, `ok(..., True)` and `check(..., True)` stay green when the feature is deleted.
- Fix: make the condition real or delete the line.
- If we skip it: green checks that say nothing.
- Proof: read the lines above.
- Verifier: CONFIRMED (code).

#### 85. Skips that pass silently (F099)
`tests/backend/test_backend.py:2636-2660`, `tests/e2e/e2e_test.py:684, 803, 1141-1146`, `tests/notifier/test_watcher.py:212`
- Case: a missing nginx, Playwright, Kotlin or cryptography prints a skip and exits 0, also on GitHub.
- Fix: when `GITHUB_ACTIONS` is set, a skip is a failure.
- If we skip it: a runner image update can drop whole checks without anyone seeing it.
- Proof: read the lines above.
- Verifier: PARTLY (the skips print lines but exit 0; no CI guard).

#### 86. A test pins the damaged access.json case (F100)
`tests/backend/test_backend.py:1275-1277`, `backend/access.py:91-105`
- Case: the test expects the password off after a damaged file. The two verifiers disagree on whether it blocks
  finding 8. Its file is broken JSON (`{rotto`), which stays a reset after the fix, so it should still pass. There is
  no test for the read-error case.
- Fix: with finding 8, add a second test where `open` raises `OSError` once and the password must stay on.
- If we skip it: finding 8 can come back unseen.
- Proof: read the test.
- Verifier: CONFIRMED (code), kept Should.

#### 87. No test says what happens to a scheduled print that is hours late (F101)
`tests/backend/test_print_schedule.py:93-100`
- Case: no case where the first tick comes hours after the time with Klipper ready; the code starts it 6 h late.
- Fix: add the case with finding 12's fix.
- If we skip it: the behaviour can flip either way unseen.
- Proof: `python3 -I $P/O/late_schedule.py`.
- Verifier: CONFIRMED (code).

## 5. Structure

The import graph is clean: `klippeye_backend.py` imports 26 modules, nothing imports it, and there are no cycles. Copied
code is rare: no exact copy of 12 lines anywhere in the backend, notifier, scripts and dashboard. The real costs are
rules written twice (each has already caused a finding) and one 5,279-line file whose 140 globals the tests patch in
place (33 globals, 49 loads of the whole file). Ranked proposals:

1. One monitor rule, one pipeline.
   - Cost: about a day; about 90 new lines, 120 removed.
   - Saving: the measuring tools would then measure the monitor that runs. Today the replay has no purge marks (finding
     82), and `ml/evaluate.py` gives a dropped trigger no rest, so the thresholds and model choices in CLAUDE.md
     section 6 rest on a monitor that is close to the live one, not equal to it.
   - Risk: medium. Replay numbers change, so re-measure once and write the new baseline.
   - Steps: `monitor_core.prepare_check(...)` (masks, zone, purge, judge) called by the loop and by `scripts/replay.py`;
     the recorder keeps the purge mask; a pure `ask_rule(state, score, now, ...)` shared by `_local_look` and
     `ml/evaluate.py`; one test where a recording with purge marks replays like the live check.
2. Move the monitor out of the Flask file.
   - Cost: 2 to 3 days, one step per commit; about 1,600 lines moved.
   - Saving: the monitor can be tested without loading the web app; the backend file drops to about 3,700 lines.
   - Risk: medium-high for step 4 only.
   - Steps (each keeps the behaviour, re-exports the old names, and keeps `CONFIG_SPEC` in the backend file for the mock
     server):
     0. First make `frontend/tools/i18n.py` read `bt()` texts from every `backend/*.py` (today only from
        `klippeye_backend.py`) and check the count stays the same. Then move `_lang`, `bt`, `btn` to `backend/texts.py`.
     1. The pure monitor rules (`normalize_action`, `build_ai_prompt`, `confirm_stop`, `apply_min_confidence`,
        `real_print_check` and the constants, about 280 lines) to `backend/monitor_rules.py`.
     2. Alert history (`record_alert` and helpers, about 110 lines) to `backend/alert_history.py`.
     4. `LightDetector` and `LocalAi` (about 1,060 lines) to `backend/monitor_loop.py`. The 42 names it reads come in
        one `deps` object whose members look the backend global up at call time, so the tests' patches keep working.
        Diff the method bodies before and after.
     5. The learning glue (`label_alert`, `refresh_false_alarms`, `_alarm_vector`) to `backend/learning.py`.
   - Run before and after each step: `ruff check .`, `python3 tests/backend/test_backend.py`,
     `bash tests/run_all.sh --no-ui`, and the tests of the area.
3. Rules written twice, one place each.
   - Cost: half a day each.
   - Saving: about 500 lines deleted in all. The data folder rule (D1, 18 lines, the cause of finding 15); lights served
     by the backend (R3, about 150 lines of JS, the cause of findings 56 and 71); one reader for Moonraker settings and
     objects (R4/R5, about 30); `ACCESS_TEXT` through `bt()` (about 110); the notifier reading the dashboard's i18n
     files instead of its own `MESSAGES` (about 190); `atomic.write_text` in `web_front.py` (R9); the guard calling
     `_role()` (R10). `i18n.py check` then covers every text.
   - Risk: low. The notifier would depend on `frontend/src/i18n/` being present, which it always is in `~/klippeye`.
4. Dashboard shells.
   - Cost: a day.
   - Saving: about 150 lines. One `Dialog` in `20-ui-primitives.js` for the 10 hand-made dialogs (fixes finding 54 in
     one place); `saveConfigFile(path, next, before)` for the editor, shaper and timelapse writes (findings 19, 63);
     `pollingStore(refresh, ms)` for the three polled stores.
   - Risk: medium. Ten dialogs change at once, and `motion_test.py` and the leaving rules must still pass.
5. Route modules.
   - Cost: 2 days.
   - Saving: about 810 lines out of the backend file (MQTT, HTTPS and web front, schedule, recordings, calibration
     routes, each as `register(app, deps)`); one `web_status()` per HTTPS request instead of up to three subprocesses.
   - Risk: medium. Check the access rules that match endpoint names before using blueprints, and keep `web_run` and
     `_mqtt_read_lights` patchable.
6. Dead code.
   - Cost: an hour.
   - Saving: about 40 lines, one orphan route, a dozen payload keys no page reads. The pieces: `load_ai_config`,
     `shaper_pulses`, the `method` parameter left from the «detail» method, unused parameters,
     `/api/camera/calibration/template/<kind>`, `/api/macros/run` (F058). Read `VERSION` in the notifier instead of its
     own «1.7». Keep `bed_view`, which section 6 of CLAUDE.md reads.
   - Risk: low.
7. One way to save settings.
   - Cost: a design change, several days.
   - Saving: the whole class of sync findings (16, and F083 to F085 among the Nice ones).
   - Risk: high. Decide after 1 to 6.

Not worth doing: merging `recorder.py` and `print_review.py`, the small view-preferences and error-wrapper copies,
splitting `ml/download.py` or `scripts/replay.py`.

## 6. Logic

Nothing here ran on the owner's recordings: they are not in the container. Every hypothesis has its measurement. Run it
first on the old camera's data and then on the new camera's recordings, which are never trained on. Keep a change only
if it wins on the old data and does not lose on the new data.

The scripts named below are in `.superpowers/audit/proofs/S/` (outside git). Setup:
`zip -s 0 klippeye-misura.zip --out one.zip && unzip one.zip -d old` (from the owner's Downloads), `OLD=old/klippeye`,
box `0,0.368,1,0.632`. For the new camera, on the Pi: `cd ~/printer_data/klippeye && zip -r -s 25m ~/klippeye-new.zip
camera.json machine_shape.json recordings reviews alerts` (only recordings after the camera change), `NEW=new/klippeye`,
and the box from `GET /api/local_model` → `bed_view`. History: `H=<data>/alerts/history.jsonl`.

Baseline:
```
python3 scripts/replay.py --data $OLD --current --json base_replay.json
python3 ml/evaluate.py --model models/base --data $OLD --box 0,0.368,1,0.632 --json base_eval.json
```

Ranked hypotheses:
1. Q2, a weak prior on the lens distortion (finding 7). On synthetic cameras the worst bed error drops from hundreds of
   pixels to a few, and the RMS on the taps rises from 0.96 to 1.29 px. Decides it:
   `python3 -I refit_owner.py <old>/camera.json 350 350`, then the new camera's `camera.json`. Keep it if the RMS rises
   by less than 1 px, the rating stays, and the corners match what the owner sees in the overlay. If it does not, try
   `PRIOR_PX` 50 and 100 (fourth argument). Q3, refusing a fit that folds inside the bed's angles, catches about 60 % of
   the wrong fits and goes in with it.
2. M2 with G7: a trigger the local filter drops should not start the 90 s rest. First make the tool match the live
   monitor, then try the change: `FILTERED_REST=90 python3 -I evaluate_variant.py --model models/base --data $OLD --box
   0,0.368,1,0.632 --json live_like.json` against `FILTERED_REST=0 ... --json no_rest.json`. Read the «+ motion» row:
   failures caught and median delay should improve, false asks should rise by less than 0.5/h. The gap between the two
   runs is also the error in the old measurements.
3. P1: a verdict of the local model alone pauses the print. With the online AI off, three «sure» looks write
   `action: PAUSE, local_only: true`, and the notifier ignores `local_only`. With «Pause by itself» on, that pauses the
   print with no second look. CLAUDE.md calls it a proposal. Ask the owner; the data:
   `python3 -c "import json;r=[json.loads(l) for l in open('$H')];l=[x for x in r if x.get('trigger')=='local_alone'];print(len(l),[x.get('label') for x in l])"`.
4. C2: a confidence given as 0.9 or as the text «90» turns every stop into CONTINUE (`$P/C/proof3.py` case 6).
   `python3 -c "import json;r=[json.loads(l) for l in open('$H')];d=[x for x in r if x.get('outcome')=='analysed (downgraded)'];print(len(d),[(x.get('service'),x.get('confidence'),x.get('label')) for x in d][:30])"`.
   Any entry with confidence of 1 or less, or labelled «right», settles it: scale values of 1 or less by 100 and accept
   numeric text.
5. C1: an unreadable first answer (finding 34).
   `python3 -c "import json,collections;r=[json.loads(l) for l in open('$H')];print(collections.Counter((x.get('outcome'),x.get('service')) for x in r).most_common())"`.
   Over about 2 % «AI answer not readable» for any service makes it more than a robustness fix.
6. M3: the light-change streak (finding 28): `python3 -I replay_variant.py --streak 13 --data $OLD --current --json
   s13.json` against the baseline. False alarms must not rise and failures caught must not drop. If the recordings have
   no light change, record one print on the new camera and switch the light three times.
7. F2: the person's «false» is stored with a vector recomputed from today's views. Compare it with the vector recorded
   at alarm time (`local["vector"]`); if more than a third of the cosines are below 0.92, store the vector of the
   moment. Needs a small script, not written.
8. F1: `SIM` 0.92 and `MARGIN` 15 were chosen by hand. Leave-one-out over the judged alarms, sweep SIM 0.85 to 0.97 and
   MARGIN 5 to 25, and accept a pair only if no right alarm matches. Needs a small script, easier after structure step 4.
9. F3: how long an online «fine» lasts. `FINE_MEMORY=300`, `600`, `1800` with `evaluate_variant.py`, «+ motion» row; 600
   stays unless another value wins on both counts and holds on `$NEW`.
10. M1: reset the trigger count on a calm check. On synthetic scores it cuts 10 to 25 % of motion triggers at most, with
    the same delay. `python3 -I replay_variant.py --rule decrement ...` against `--rule reset ...`; keep «reset» only
    with 20 % fewer false alarms per hour and the same failures seen. Expected: no change worth a release; fix the
    sentence in CLAUDE.md.
11. M4: the purge comparison when the bed moves in Z between heating and the start. Log `before_pos[2]`, `live[2]` and
    the share of marks at `_purge_find` for the next 5 prints on the new camera; skip the purge when the heights differ
    by more than about 1 mm and the marks follow the plate edge.
12. Also listed, smaller: M5 (warm-up after a restart:
    `journalctl -u klippeye --since -30d | grep -c "Light detector started"` against the prints), C3 (second look when
    Moonraker does not answer), C4 (retries stacked in three places), Q4 (check the camera at once on a whole-picture
    change), F4 (a layer taught on one failed print), P2 (the verdict must belong to the current print; same root as
    finding 13), P3 (an alarm marked false still counts toward «N in a row»).

Measured and rejected: Q1 (rating by leave-one-out error: the taps are all mid-bed, so it cannot see the edge error);
P4 (a verdict skipped by the 5 s poll: verdicts are at least 30 s apart).

Where CLAUDE.md section 2 and the code disagree:

| # | CLAUDE.md says | The code does | Where |
|---|---|---|---|
| G1 | `trigger_count` suspicious checks in a row trigger | a calm check takes one off the count, it does not reset it | `monitor_core.py:173` |
| G2 | (nothing) | the count and the rest carry over to the next print (F110) | `monitor_core.py:268-276` |
| G3 | a motion trigger goes online only if the model is at least in doubt | true, but the dropped trigger still starts the 90 s rest, which silences the local model too | `monitor_core.py:179`, `klippeye_backend.py:2661-2662` |
| G4 | online AI off: three sure looks propose a pause | they write a PAUSE verdict, and with «Pause by itself» on the notifier pauses | `klippeye_backend.py:2643-2716`, `klippeye_notifier.py:861-901` |
| G5 | (nothing) | with the online AI off, motion triggers do nothing at all | `klippeye_backend.py:2642-2649` |
| G6 | a stop is looked at again 15 s later | 40 s (`AI_CONFIRM_DELAY_S`), plus up to 30 s while the toolhead hides the part (F117) | `klippeye_backend.py:1760, 1763` |
| G7 | the section 6 numbers are the monitor's real rule | the tools are close to the live monitor, not equal (G3 missing in `evaluate.py`, 120 s rest instead of 90 s, no purge in the replay) | `ml/evaluate.py:68-90`, `scripts/replay.py:120-176` |

G1, G3, G5 and G6 should be written into section 2 as they are, unless the hypotheses change the code. G2 is a bug
(F110). G4 waits for the owner (P1). G7 is structure proposal 1.

## 7. Nice to have

F110 to F170 were not verified one by one; each comes from a zone reader's or a pass's own case. The first 19 rows were
verified and moved here from Must or Should.

| Id | Title | File |
|---|---|---|
| F032 | No Must finding has a test yet (each fix PR adds its own) | `tests/` |
| F042 | The settings page polls a call that reads every labelled recording | `backend/personal_layer.py:215-223` |
| F053 | web_front.py writes nginx files without fsync | `scripts/web_front.py:66-70, 223-227` |
| F058 | `/api/macros/run` is unused and sends any G-code | `backend/klippeye_backend.py:1339-1353` |
| F071 | The viewer's loader has no size limit without Content-Length | `frontend/src/app/49a-gcode-viewer.js:221-257` |
| F075 | Switching a heater off during a print needs no confirmation | `frontend/src/app/43a-temperatures.js` |
| F076 | File list loads metadata one file at a time | `frontend/src/app/47-files.js:88-134` |
| F083 | MQTT form goes stale and Save overwrites newer values | `frontend/src/app/59r-home-automation.js:23` |
| F084 | AI backups list saved whole from data loaded once | `frontend/src/app/59l-ai-services.js` |
| F085 | Phrases textarea never follows saved data | `frontend/src/app/59g-printer-functions.js:374, 420` |
| F086 | Edits in blur-only fields may be lost on close | `frontend/src/app/59g`, `59n` |
| F087 | AI key typed in a plain text field | `frontend/src/app/59l-ai-services.js:325` |
| F088 | Materials turn bad input into 0 degrees | `frontend/src/app/59s-materials.js:19-20` |
| F089 | `vzbot.p12` is a second public key nothing uses | `android/chiave/vzbot.p12` |
| F091 | A downloaded update is not compared with the app's certificate first | `android/.../AppUpdate.kt:77-152` |
| F093 | train.py numbers are still optimistic (known limit) | `ml/train.py:264-299` |
| F094 | replay.py applies today's calibration to every old recording | `scripts/replay.py:91-106` |
| F095 | evaluate.py and replay.py model only part of the live rules | `ml/evaluate.py`, `scripts/replay.py` |
| F097 | The notebooks drift from CLAUDE.md | `ml/*.ipynb` |
| F110 | Trigger counter and cooldown carry over to the next print | `backend/monitor_core.py:268-276` |
| F111 | Auto-delete takes the oldest recordings whatever their label | `backend/recorder.py:372-388` |
| F112 | Two trainings can start; personal.view is set outside the lock | `backend/klippeye_backend.py:3225-3232` |
| F113 | numpy's BLAS is not limited to the allowed cores | `backend/personal_layer.py:178-191` |
| F114 | Imported examples only grow | `backend/personal_layer.py:400-435` |
| F115 | Two alerts in the same second share an id and picture names | `backend/klippeye_backend.py:1947-1953` |
| F116 | Dead code kept only for tests | `backend/klippeye_backend.py:1544-1551` |
| F117 | CLAUDE.md says the second look comes 15 s later; the code waits 40 s | `CLAUDE.md` section 2 |
| F118 | Printed markers not recognised on beds of 100 mm or less | `backend/camera_markers.py:24, 129-142` |
| F119 | Reference picture written without fsync; a look can race a save | `backend/camera_calibration.py:822-865` |
| F120 | A guest may POST to any path under /webcam | `backend/access.py:262-264` |
| F121 | The guest directory check does not normalise the path | `backend/access.py:271-272` |
| F122 | A comment says a guest never reads the configuration, but configfile is open | `backend/access.py:237-252` |
| F123 | The relay can hold a slot for minutes after a phone drops off Wi-Fi | `backend/https_relay.py:163-189` |
| F124 | Two admins saving access settings at once lose one change | `backend/klippeye_backend.py:587-665` |
| F125 | A power cut can leave an empty earlier version of a config file | `backend/config_versions.py:109-132` |
| F126 | Two ntfy requests can give the phone a topic that is then thrown away | `backend/notify_channels.py:98-143` |
| F127 | Two live connections to Moonraker at start-up | `backend/klippeye_backend.py:1068-1074` |
| F128 | The settings document is read in three places in the notifier | `notifier/klippeye_notifier.py` |
| F129 | A re-install from another folder leaves Moonraker updating the old one | `scripts/install.sh:555-579` |
| F130 | `klippeye update` on the stable channel installs an untested commit | `scripts/klippeye:85-97` |
| F131 | `klippeye benchmark` runs OpenCV on every core at normal priority | `scripts/benchmark.py:228-251` |
| F132 | Two tabs of one browser overwrite each other's layout | `frontend/src/app/19-layout.js` |
| F133 | The action toast does not restart its timer for the same text | `frontend/src/app/20-ui-primitives.js:291-309` |
| F134 | Texts outside tx() shown in English or Italian | `frontend/src/app/16-settings.js`, `17-backend.js`, others |
| F135 | Colours and shadows written by hand outside the tokens | `frontend/src/css` |
| F136 | Uppercase labels remain (9) | `frontend/src/css` |
| F137 | Radii and font sizes outside the scale | `65-settings.css`, `53-ai-markdown.css`, `59j-help.js` |
| F138 | Stale comments, a cut sentence and a build note | `frontend/src/css/02-wordmark-font.css`, others |
| F139 | The CodeMirror vendor build is not reproducible | `frontend/tools/codemirror/build.sh:26-34` |
| F140 | History polls up to 2,000 jobs every 30 s | `frontend/src/app/47b-history.js` |
| F141 | Queue reorder races with a second browser | `frontend/src/app/48b-queue.js` |
| F142 | FanSlider has no pointercancel handler | `frontend/src/app/42-fans.js:267-284` |
| F143 | The System page shows invented or stuck states | `frontend/src/app/56-system.js` |
| F144 | Text typed while the phone editor is closing is lost | `frontend/src/app/51-config-editor.js:618-633` |
| F145 | The log analysis can run twice; a proxy error page is read as JSON | `frontend/src/app/54-logs.js` |
| F146 | Dead CSS and a dialog without Presence in the editor | `frontend/src/css/54-logs.css`, `51-config-editor.js:690` |
| F147 | The setup guide says printer and camera are ok without looking | `frontend/src/app/59k-setup-guide.js:100-101` |
| F148 | «Restart Klipper now» has no confirmation | `frontend/src/app/59g` |
| F149 | SettingsHome polls six endpoints at every refresh | `frontend/src/app/59-settings.js` |
| F150 | Unused aiMonitor prop in DesktopSystemPage | `frontend/src/app/71-desktop-pages.js` |
| F151 | ntfy token can go over cleartext to a public host | `android/.../PushSettings.kt:89, 349` |
| F152 | No tests for the Android security rules | `android/app/src/test` |
| F153 | A CI-made key blocks the release tag once | `ci/release.py:66-69` |
| F154 | Gradle wrapper has no checksum | `android/gradle/wrapper/gradle-wrapper.properties` |
| F155 | A failed print without a moment counts any alarm as caught | `ml/evaluate.py:119-128` |
| F156 | One bad picture ends a whole training run | `ml/train.py:52-77` |
| F157 | `--paste` lets a training picture's background reach the measuring set | `ml/hard_cases.py:132-157` |
| F158 | torch is not pinned | `ml/requirements.txt` |
| F159 | test_backend.py waits 13 minutes of wall clock with fixed windows | `tests/backend/test_backend.py:371-398` |
| F160 | A frozen copy of the first monitor costs 1,680 lines and 44 s | `tests/backend/fixtures/vzbot_brain_original.py` |
| F161 | One `ok()` in 79 test files | `tests/ui`, `tests/notifier` |
| F162 | settings_test «a stream that does not come» depends on port 80 | `tests/ui/settings_test.py:271-274` |
| F163 | A snapshot address of 281 to 293 characters is cleaned differently | `backend/camera_snapshot.py:18` |
| F164 | Payload keys no page reads (one is a lost message) | `backend/klippeye_backend.py` |
| F165 | The MQTT password can be changed but never removed from the dashboard | `frontend/src/app/59r-home-automation.js:39` |
| F166 | The notifier reports version 1.7, not the release | `notifier/klippeye_notifier.py:75` |
| F167 | An orphan route with no caller: calibration template | `backend/klippeye_backend.py` |
| F168 | One log line every 3 s while Moonraker or the camera is down | `backend/klippeye_backend.py:2414-2442` |
| F169 | Temporary files left by a kill are never removed | `backend/atomic.py:13-26` |
| F170 | Classes with no CSS rule; small things seen in pictures | `frontend/src/css` |

## 8. Proposed order of fix PRs

Must first, one area per PR. The ones that can move or restart the printer, or lose the person's data, come first. Each
PR follows CLAUDE.md section 4 and starts from its proof command as the failing test. Version bumps are proposed from
1.137.0 and move on in order.

| # | PR | Closes | Bump |
|---|---|---|---|
| 1 | Dashboard: nothing moves or restarts the printer unseen | 20, 21, 17, 18 (Must); 57, 58, 63, 64, 65 | minor (new confirmations during a print) |
| 2 | Calibration: no moves during a print, right Z guess | 6 (Must); 38 | patch |
| 3 | Scheduled prints: a late print is missed, not started | 12 (Must); 87 | patch |
| 4 | Notifier: queue prints, announced automatic pauses | 13 (Must); 49, 50 | patch |
| 5 | Install and repair scripts: safe writes, the same data folder, no restart on a slow answer | 14, 15 (Must); 51, 52, 53 | patch |
| 6 | Printer macros file: Klipper always starts | 11 (Must); 45 | patch |
| 7 | False-alarm memory and personal layer files | 4 (Must); 29, 30, 31, 32, 33, 72 | patch |
| 8 | Dashboard settings sync between devices | 16 (Must) | patch |
| 9 | Config editor: never overwrite newer text | 19 (Must); 66, 67 | patch |
| 10 | Access and network | 8, 9, 10 (Must); 40, 41, 42, 43, 44, 86 | patch |
| 11 | Monitor loop: no crash, no hang, says when it is blind | 1, 2, 3 (Must); 28, 82 | patch |
| 12 | Online AI chain | 5 (Must); 34, 35, 36, 37 | patch |
| 13 | Training chain: kept-out prints, one group per print, licences | 22 (Must); 27, 70, 79, 83 | patch |
| 14 | Calibration fit: distortion prior and fold guard, after measurement Q2 | 7 (Must); 39, 73 | minor (ratings and masks change) |
| 15 | Android app: bridge origin, https only when pinned, signing key | 24, 25, 26, 69 | `android/VERSION` minor; the key change needs the owner |
| 16 | Backend rest: MQTT and monitor settings | 46, 47, 48 | patch |
| 17 | Dashboard small fixes | 23, 54, 55, 56, 59, 60, 61, 62, 68, 71 | patch |
| 18 | Look: translations, touch areas, cut names, Pi-down sign | 74, 75, 76, 77, 78 | patch |
| 19 | Tests and CI | 80, 81, 84, 85 | patch |

Structure proposals 1 and 6 can go with PRs 11 and 17. The rest of section 5 waits until the fixes are in.

## 9. Verdict

KlippEye is in good shape for its size. The imports are clean and copies are rare. Writes go through one atomic helper,
and the backend came back from every SIGKILL during a write with no file cut. Memory stayed flat over 3.8 hours of checks, and
all five kinds of printer ran with no server error. The weak points are a few, and they are specific.
- Edges where a failure is swallowed: an empty score list, a stream that never ends, an exception in an AI look, an
  answer the page never reads. Findings 1, 2, 5, 17 and 18 are the same mistake in five places.
- Checks that do not hold across time: a guard read before the dialog opens, a cache the editor trusts, a lateness
  limit that only applies when Klipper is down, a print state read that fails open. Findings 6, 12, 19, 20 and 64.
- One shared document saved whole, which loses changes between devices and carries the safety switches (finding 16).
- The measuring tools are close to the live monitor, not equal to it (finding 82, G7), and nothing in the code guards
  the kept-out prints (finding 22).

Lean: about −750 lines possible (from structure.md): rules written twice about −500, dashboard shells about −150, dead
code about −40, the monitor pipeline about −30 net, small copies about −45. Deleting the frozen first monitor in the
tests (F160) would take 1,680 more lines out of `tests/`. Moving the monitor and the routes out of the backend file
moves about 2,400 lines without deleting them.

Not checked:
- A real Raspberry Pi: CPU and timing figures came from 2 x86 cores and do not carry over; memory and file growth
  should.
- nginx and waitress were not run (findings 9, 10 and 43 come from the nginx source and an emulation; the 12-thread
  pool was not measured).
- The owner's recordings and `camera.json`: every logic hypothesis in section 6 still waits for its run.
- The Kotlin code was read and mirrored, not built or run. Touch and the WebView were not tested.
- Power cuts: SIGKILL only, so the fsync findings (4, F053, F119, F125) are from the code.
- The 48 h replay; Klipper restarting while Moonraker stays up; the notifier during a Moonraker outage.
- Dialogs, sheets and every step of the guided set-up were not photographed; contrast was judged by eye.
- Files read only in part: the CSS of zone J, `53-ai-markdown.css` and `63-macros.css`, three Android tool scripts and
  the assets, about 70 UI test files (through greps), `tests/backend/fixtures/vzbot_brain_original.py`,
  `tests/ui/mock_server.py`, `tests/backend/fake_moonraker_ws.py`, and the base64 font.
- The 61 Nice findings from F110 on were not verified one by one.
- The three JavaScript proofs (findings 59, 60, 61) and the section 6 scripts are not in git.
