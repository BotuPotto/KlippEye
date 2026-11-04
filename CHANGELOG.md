# Changelog (Cosa cambia in ogni release)

## 1.45.0

**Devices: power, outputs and filament sensors** (roadmap phase 6d, fourth part), like Mainsail's *Power control* and
*Miscellaneous*.

* A **Devices** card (Control page on the phone, under the fans on the computer's device page), shown only when there is
  something in it:
  * **Power**: Moonraker's `[power]` devices (smart plugs, relays, GPIO…) on / off; switching one off asks first (it may
    be the printer's own power); a device locked while printing says so, and Moonraker's refusal is shown.
  * **Outputs**: Klipper's `[output_pin]`s, a switch or, for a PWM pin, a slider (up to its `scale`).
  * **Filament sensors**: filament detected or not, and the switch that turns the sensor on or off
    (`SET_FILAMENT_SENSOR`).
* A name starting with `_` stays hidden, as in Mainsail.

## 1.44.0

**Print queue** (roadmap phase 6d, third part), with Moonraker's `[job_queue]`.

* **Add to the queue** in a file's long-press menu (and *Queue* on the computer's file panel), with how many copies; it
  says what happens: after the jobs already waiting, when the printer is free, or at once (*Add and print*) when the
  printer is free and the queue running.
* The **Print queue** card on the Files page while jobs wait: in order with thumbnail and estimated time, the total;
  move a job up / down or to the front, remove it; **Start the queue** / **Pause the queue**; **Empty** (asks first).
* Nothing of it shows without `[job_queue]` in `moonraker.conf`: the dashboard asks Moonraker which components it has
  (`/server/info`) instead of trying and getting a 404.

## 1.43.0

**Temperatures: every sensor and the chart** (roadmap phase 6d, second part).

* A **Temperatures** card (Home on the phone, under the camera and the print on the computer), like Mainsail's: every
  heater and sensor Klipper has — nozzles, bed, `heater_generic`, `temperature_fan`, `temperature_sensor` (a name starting
  with `_` stays hidden) — with its temperature, target and power.
* The **chart**: each one a line in its own colour, the target dashed in the same colour; 5 / 10 / 20 minutes. It starts
  from what Moonraker kept (`/server/temperature_store`) and goes on with a reading every 2 seconds while the card is on
  screen. The pointer (or a finger) on the chart shows the time and every value at that moment.
* A tap on a **name** hides or shows its lines; a tap on a **target** changes it (the nozzle and the bed with their usual
  dialog, the other heaters with `SET_HEATER_TEMPERATURE`, a temperature fan with `SET_TEMPERATURE_FAN_TARGET`, up to their
  `max_temp`). The hidden lines and the minutes are kept on this device.
* The bars of the history's 14 days are at most 24 px wide.

## 1.42.0

**Print history and statistics** (roadmap phase 6d, first part).

* The **Files** page has a switch at the top: *Print files* | *History* (kept on this device).
* **Statistics** (Moonraker's `[history]`): prints, print time, filament used, longest and average print, how many
  completed; **how the prints ended** (completed / cancelled / failed, one bar with the counts); the **last 14 days**, a bar
  a day for print time or filament (tap a bar for its day and value). *Reset* sets Moonraker's totals back to zero.
* **The list**: every print newest first with its thumbnail, how it ended (Klipper shutdown, error, cancelled…), date,
  print time and filament; search (also in the notes), filters *All / Completed / Cancelled / Failed*.
* **A print**: started, ended, print and total time, slicer estimate, filament used and in the file, slicer, layer and
  object height, whether the file is still there; a **note** (kept in Moonraker's database, every device sees it);
  **Print again**; **Remove** from the history.
* Without `[history]` in `moonraker.conf` the page says what to add.
* Fix: the sheets that set their own size in an earlier stylesheet (file details, lights, folders, bed screws) lost it
  to the defaults: a long one could run off the screen. The defaults now weigh nothing (`:where`).

## 1.41.0

**The text editor on CodeMirror 6, like Mainsail** (roadmap phase 6c, third part).

* The editor of the configuration and G-code files is now **CodeMirror 6** (the engine of Mainsail's editor), bundled in
  the dashboard (`frontend/vendor/codemirror-6.js`, MIT, built by `frontend/tools/codemirror/build.sh`): line numbers,
  colours for Klipper's files (sections, keys, pins, values, comments, G-code and Jinja2 in macros) and for G-code, the
  active line, matching brackets, multiple selections, smooth on long files and on phones.
* **Sections**: the arrow next to a `[section]` folds it; *Sections of the file* lists them (tap one to go there) and folds
  or unfolds them all.
* **Reference**: a button opens Klipper's Config Reference at the section under the caret (`[stepper_x]` → `[stepper]`),
  or Moonraker's configuration page for `moonraker.conf`.
* **Find and replace** (the magnifier or Ctrl+F): next / previous, select all, match case, regexp, whole word, replace,
  replace all — in the dashboard's language.
* Kept from the earlier editor: Undo / Redo (now CodeMirror's history), Comment / Uncomment and Ctrl+/ (`#`, `;` in
  G-code), Ctrl+S, *Save and restart*, the question before closing with unsaved changes.

## 1.40.0

**Print files: search, order and details** (roadmap phase 6c, second part).

* **Search** the print files by name (and folder); the count says how many match.
* **Order** (kept on this device): newest / oldest first, name A→Z / Z→A, shortest / longest print, most filament,
  largest, last printed. Sorting by print time, filament or last print reads every file's metadata (a few at a time).
* **Details** in the long-press menu (and on the computer's file panel), like Mainsail: folder, size, last change, last
  printed, slicer and version, estimated time, layer / first layer / object height, layers, filament type and name, length,
  weight, nozzle, first layer nozzle / bed temperature, chamber; *Start print* from there.

## 1.39.0

**Configuration files: order, backups and hidden files** (roadmap phase 6c, first part).

* The ⇅ button next to the search box: **order** by name A→Z / Z→A, last change first / oldest first, largest first
  (folders always first); show the **backup files** (SAVE_CONFIG's `printer-…cfg`, `.bak`, `.bkp`, `.old`…) and the
  **hidden files** (`.name`), tagged in the list. Kept on this device.
* Under the list, a line says how many backups and hidden files are left out; a tap shows them.

## 1.38.0

**Notifications of your own, and the error with Klipper's message** (roadmap phase 6b, ninth part; notification service 1.7).

* **The error notification says why**: Klipper's own message — the reason of a shutdown (`Timer too close`, `Heater
  extruder not heating at expected rate`…), the error of a print, else the last `!!` line of the console. In English
  "Printer error: …", in Italian "Stampante in errore: …".
* **Your texts**: Settings → Notifications, *Change the text* under each notification; placeholders filled in when it
  goes out: `{file}`, `{progress}`, `{layer}`, `{total_layers}`, `{elapsed}`, `{remaining}`, `{message}`, `{printer}`…
  Empty: the usual text, in the language of the notifications.
* **The pause's delay**: at once, 4 (as before), 10, 30 or 60 seconds.
* **Your notifications**: print started, progress reached (%), little time left (minutes), layer reached, a line in the
  console (words of your macro: `M118`, `RESPOND`), temperature reached (bed or nozzle) — each with its text, *Important*
  (an alarm instead of a notice) and on / off. Progress, time and layer go out once a print.
* The notification service reads them from the shared settings, like the other choices: no restart needed.
* Tests: the notifier's integration test no longer loses its report when it fails in CI.

## 1.37.0

**Every light of the printer** (roadmap phase 6b, eighth part).

* **Found by themselves**: each pair of light macros (`LUCI_ON` / `LUCI_OFF`…, read on the output of the same name), each
  LED output (`[led]`, `[neopixel]`, `[dotstar]`, `[pca9533]`…) and the `[output_pin]`s whose name says light (not a
  beeper or a relay). Universal: no names are fixed.
* **The round button** on the camera (phone, computer, full screen) switches together the lights marked *Switched by the
  round button*: off when any is on, else all on; each light keeps its own reading and retries, as before.
* **The arrow** next to it opens **every light**: a switch each, the **brightness** (LEDs, PWM pins) and the **colour**
  (RGB LEDs, with the colour wheel; white uses the white channel when there is one), and the **scenes**: *Save as a scene*
  keeps how the lights are now under a name, a tap brings it back.
* **Settings → Printer functions** in three parts: **Lights** (the list: name, how it is switched — an output, two macros,
  G-code —, where the state is read, round button yes / no, order, remove, add, *Find the lights again*; the scenes),
  **Buttons** (park, wipe, load, unload) and **Filament**. A light chosen in an earlier release is kept as the only one of
  the list; one left on *Automatic* becomes the lights KlippEye finds.

## 1.36.1

* **The 3D height map looks like Mainsail's**: Mainsail's colours (blue low → yellow → red high) as a smooth gradient
  across the surface instead of one colour a square, the mesh lines faint on it, a box with a grid on the floor and the
  back walls, and the values on its edges (X and Y in mm, Z minimum and maximum). Seen from the front, above; drag to
  turn, pinch or wheel to zoom, ↻ to go back. The 2D grid and the scale use the same colours.

## 1.36.0

**The height map redone, like Mainsail's** (roadmap phase 6b, seventh part).

* **2D and 3D kept**, with the **probed** points or the **interpolated** mesh; **minimum, maximum, range** (in orange above
  0.3 mm) and **points**. The 2D grid shows the value of each point and, with a tap, where it is (X, Y in mm); the 3D view
  has a button to go back to the starting view and is bigger on a phone.
* **Fixed: the map was drawn front to back.** Klipper lists the front row (Y min) first; the 3D view took it for the back
  row, so the map was mirrored. Now the origin (0,0) is the front left point in 3D, and in 2D the back of the bed is at
  the top.
* **Profiles**: the ones Klipper keeps, with their range and the one in use; **load**, **rename** (load, save with the new
  name, remove the old: Klipper has no renaming), **remove** (after a question), **save as** (the mesh in use, under a
  name); **clear** the mesh in use.
* **Calibrate mesh** asks for the profile name and offers **adaptive** (`ADAPTIVE=1`). Calibrate, load and clear wait while
  a print runs; homing (⌂) only shows when the printer is not homed.

## 1.35.0

**The camera in full screen, turned to fit** (roadmap phase 6b, sixth part; Android app 1.5.0).

* A **full screen** button on the camera card (phone) and on the camera panel (computer): the picture over the whole
  screen, with the light button, a tap to show the buttons again (they fade after a few seconds), and ⤡ / Esc / the
  phone's back to leave.
* **Automatic rotation**: the KlippEye app 1.5.0 hides Android's bars and turns the screen to landscape (following the
  sensor between the two sides) while the camera is in full screen, and gives the screen back afterwards. A browser enters
  its own full screen and locks landscape where it can; where the screen stays upright (iPhone, browsers that cannot lock
  it) the picture itself is turned 90° to fill it, and the ↻ button switches that off.

## 1.34.0

**The console, like Mainsail's** (roadmap phase 6b, fifth part). In the title bar of the console (the Control page on the
phone, the panel of the console bar on a computer):

* **Clear**: empties the view (Klipper keeps its lines); then only what comes after is shown, the bar's preview too.
* **Options**, kept on this device: **Autoscroll** on / off (off: new lines arrive and the log stays where it is), **Newest
  on top** or at the bottom, **Show temperatures** (the temperature reports, hidden as before by default).
* **Full screen**: the console over the whole screen, with its tools and its own input field (Esc or the button leaves).

## 1.33.1

* **Fixed: "Waiting for the printer status" for ever.** After a print that ended later than the slicer had estimated
  (the file still loaded, 100 %), the estimate of the remaining time hit a mistake made in 1.30 and the printer status
  never loaded: the *Calibrate* menu and *Endstops and probe* stayed waiting. Now it loads, and a value nobody expected
  can no longer stop it.
* **Axis twist compensation without a Cartographer**: on printers whose probe is not a Cartographer KlippEye uses
  Klipper's own `AXIS_TWIST_COMPENSATION_CALIBRATE` (when `[axis_twist_compensation]` exists; axis Y only with its
  options in the config). At each point a sheet guides the **paper test**: − / + move the nozzle (TESTZ: 1, 0.1, 0.05,
  0.01 mm), *Accept* goes on to the next point, *Abort* stops; at the end the values are offered for SAVE_CONFIG. With a
  Cartographer its automatic calibration is used, as before.
* **Macro groups in any colour**: besides the ready colours, *Custom* opens a **colour wheel** (hue around, strength from
  the centre), a **brightness** bar and the **colour code** (#rrggbb) to type one exactly.

## 1.33.0

**Macros like Mainsail** (roadmap phase 6b, fourth part). The *Calibrations* card is replaced by macro cards set in the new
**Settings → Macros** (also from the gear of each card), kept in the shared settings:

* **All the macros**: one card with every macro of the printer, each can be hidden (search, show all / hide all);
* **Groups**: cards of your own with a name, a colour (it tints the buttons), the macros in the order you choose (↑ ↓ ✕,
  *Add or remove macros*) and the printer states the card shows in (idle, printing, paused); a macro Klipper no longer has
  is left out and flagged in the editor.
* The macros chosen in the old card become the group *Calibrations* (once); a new installation starts with all the macros.
* *Endstops and probe* is a card of its own.

## 1.32.0

**Tune card and leveling tools** (roadmap phase 6b, third part).

* **Tune** (Control page on the phone, Device page on a computer), usable during a print too: **speed** and **flow**
  factors (M220 / M221), **pressure advance** and smooth time (`SET_PRESSURE_ADVANCE`), **machine limits** (velocity,
  acceleration, square corner velocity, minimum cruise ratio, or accel_to_decel on an older Klipper:
  `SET_VELOCITY_LIMIT`) and **firmware retraction** (`SET_RETRACTION`, when `[firmware_retraction]` exists). − / + or a
  typed value; quick taps are sent once; each value shows the one of `printer.cfg` and a button back to it.
* **Calibrate** menu: **Z tilt adjust** and **Quad gantry level** when `printer.cfg` has `[z_tilt]` /
  `[quad_gantry_level]` (the end is read from Klipper, also when it takes longer than the proxy waits; errors in a
  toast), and **Bed screws adjust** (`[bed_screws]`) step by step: which screw, the paper test, *Adjusted* / *Accept* /
  *Abort*, until the bed is level.

## 1.31.0

**Motion: the Z arrows follow your printer, and bigger steps** (roadmap phase 6b, second part).

* **What Z moves**: on a printer whose bed moves in Z (most CoreXY) **↑** brings the bed up towards the nozzle (Z−); where
  the toolhead moves (Voron 2.4, Prusa, Ender) **↑** lifts the toolhead (Z+). *Automatic* reads it from Klipper's
  configuration (`quad_gantry_level`: the toolhead; `z_tilt` or a CoreXY: the bed); **Settings → Motion** chooses by hand.
  The Z column says which part it moves.
* **50 and 100 mm steps**: besides 1 and 10 mm, the X/Y pad (one more ring each) and the Z buttons (an ↑ and a ↓ each)
  can have 50 and 100 mm: at most four steps; with more than two the Z buttons get smaller.
* The pad no longer takes more width than it shows (its scale left room on the right): the Z column fits on a phone.

## 1.30.1

* **Computer: the console bar no longer covers the AI alarm.** On the Device page the column with the camera, the AI strip
  and the print card did not scroll: when the card grew (an AI alarm to answer, *More details*) its bottom went under the
  console bar and the answers could not be pressed. Now the camera takes the room left and the column scrolls.

## 1.30.0

**More in the print card, and «Exclude an object»** (roadmap phase 6b, first part).

* **Like Mainsail**: under time, remaining and layer a second row with **when it ends** (clock time; "tomorrow" when it
  ends another day), the **speed** now and the **volumetric flow** now (the extruder's speed and the filament's diameter
  from `[extruder]`). **More details** (folded) has the remaining time by the file, the filament and the slicer, the
  slicer's whole estimate, the total time with pauses, the filament used of the total (m and g), the height now of the
  object's, the speed now / requested and the speed and flow factors (M220 / M221).
* **Exclude an object**: with Klipper's `[exclude_object]` and a slicer that labels the objects, the card (phone and
  desktop) offers **Exclude an object (N of M printing)**: a map of the bed with the objects (the one printing now in
  blue, the excluded ones grey) and their list; one is chosen on the map or in the list, then confirmed:
  `EXCLUDE_OBJECT NAME=…`. The phone's back first forgets the choice, then closes.

## 1.29.1

**Camera calibration: homing with the markers on the bed** (after the markers are printed many printers switch the motors
off, so the calibration homes again with six 10 mm pyramids on the bed).

* **The STL keeps the pyramids clear of where homing Z touches**: KlippEye reads from Klipper where Z is homed
  (`[safe_z_home] home_xy_position`, a Beacon / Cartographer home position, or where X and Y end their homing) and the
  probe's offsets; when the usual grid would put a pyramid under the toolhead or the probe there, it uses another
  symmetric grid (a slicer that centres the object keeps it in place). The page says where Z is homed.
* **«Home the printer» asks first** when homing could hit a marker: a pyramid under the toolhead or the probe at the
  homing point (take it off), a `[homing_override]` whose place cannot be known, or no `z_hop` with Z not homed (the
  nozzle may be low). *Checked: home* goes on. Blobs (0.6 mm) are no risk; a Z endstop at the top is never a risk.
* **The motors stay on during the calibration**: Klipper's idle timeout is made 1 hour long and put back at the end (save
  or start again), so the printer does not lose its homing halfway.
* Backend: `backend/homing_safety.py`; `/api/camera/calibration` has `homing`; `/home` answers 409 with `risks` unless
  `{"force": true}`.

## 1.29.0

**Camera calibration: the nozzle found by itself, the toolhead resized by dragging** (roadmap phase 6a, last part).

* **The nozzle found by itself**: tap the nozzle by hand at one point; then **Find the nozzle by itself at the other N
  points** goes to each, moves the toolhead to two places aside for a moment (what changed is where the toolhead is) and
  looks for the tip you tapped there (`backend/nozzle_finder.py`: template matching at several sizes inside that region).
  The points found are blue; **Use the N points found** keeps them and **Calculate** shows in red any that does not fit.
  One point at a time: **Go there and find the nozzle by itself** opens the magnified view on the proposal. The marker
  points (bed moving in Z) stay by hand.
* **Dots on the live picture**: each side of the toolhead, its **top (the height)** and the upper and lower edge of the
  gantry have a dot to drag; the size shows while dragging and the outline follows. Dots that would overlap are left out
  (their − and + stay); the gantry's sit on the side away from the toolhead.
* Backend: `/api/camera/calibration/find`, `/find-all` (`{"stop": true}`), `/accept`; the overlay has `handles`
  (`machine_masks.handles`: where each dot is and how far it moves per mm).

## 1.28.0

**How precise the monitor is, what weighs and where there is margin** (roadmap phase 6a, fourth part).

* **Precision of the AI** (Recordings): on the alarms you judged, how often the AI's response matched the real print: the pauses
  that were right, the problems it stopped, the false stops and the problems it missed by saying «continue». Alarms with no
  response of the AI (an error of the service) are counted apart. With fewer than 10 judged alarms it says the numbers are a
  first idea.
* **The minimum AI confidence, tried on your alarms**: a table shows what each value (50–95%) would have given — false stops
  and problems missed — with the one in use marked; when another value is better the page says so and, with enough alarms,
  offers to use it.
* **Measure and compare**: besides *Measure now*, the replay also runs without the G-code zone, without leaving out toolhead
  and gantry, less and more sensitive and with one more check in a row, and marks each one better, worse or the same as the
  settings in use: how much the G-code weighs against the real print, and whether the thresholds have margin. From the
  terminal: `klippeye replay --current --compare`.
* Backend: `GET /api/print/alerts/precision` (`backend/ai_precision.py`), `POST /api/recordings/measure {"compare": true}`.

## 1.27.0

**Any AI service, the model chosen from a list, one for the monitor and one for the logs** (roadmap phase 6a, third part).

* **More services**: Groq, Google Gemini, OpenAI, Anthropic (Claude), Mistral, OpenRouter, Meta Llama, Together, Fireworks and
  any other OpenAI-compatible server (a model on the home network: its address, a key only if it asks). One key per service,
  in one list (**Keys of the AI services**), each with a **Get a key** link to the page where the service gives it; only the
  last 4 characters are ever shown. Groq, Google Gemini and Mistral have a free plan: with Gemini the monitor has another free
  service when Groq answers 429.
* **The model from a list**: the models are read from the service with your key (kept 10 minutes) instead of typed; for the
  monitor the ones that see pictures come first, and a text-only model is flagged. *Another model* still takes a typed name;
  *Default* is a model KlippEye knows works.
* **Separate for the monitor and the logs**: Settings → AI monitor → *The AI service* chooses the monitor's service and model
  (also used by *Analyse the print*); the logs have their own, under the gear now next to **Error analysis and
  suggestions** in the System logs card, which opens the settings right there (also by itself when the key is missing).
  The free-text model of *Monitor thresholds* is replaced (a model chosen there before keeps working until one is chosen here).
* **Backend**: `backend/ai_services.py` (services, `ai.json` version 2 with `keys`, `logs`, `monitor`; the file of before
  is read as before), `GET /api/ai/models?provider=`, `/api/ai/config` takes `{key}`, `{logs}`, `{monitor}`, `{custom_base}`
  (the old `{api_key, provider}` still works). Anthropic gets no JSON mode or temperature (its OpenAI layer refuses them); a
  service that refuses the JSON mode is asked again without it.

## 1.26.2

* **Judging an older alarm no longer says "Not saved: no such alarm"**: the alert history keeps only its last 40 alarms, so
  the answer to an alarm that had already left it was refused. Now it is saved in the recording the alarm belongs to (the
  dashboard says which; without it the backend looks for it).

## 1.26.1

**Recordings: clearer answers, the alarm pictures kept, the AI's 429 explained.**

* **Correct result / Wrong result**: each alarm asks "AI response: «Pause». Does it match the real state of the print?", and
  each answer says the real state (*yes: the print really had a problem*, *no: the print was fine*; for a "continue": *yes: the
  print really was fine*, *no: the print had a problem the AI missed*). *Print OK / KO* was confusing for a "continue". An
  alarm the AI could not judge asks *There was a problem / No problem*.
* **The print first, the alarms one level down**: a recorded print shows its pictures and how it went; *Alarms of this print*
  (with how many are judged) opens the alarms. The *All the recordings* button is gone: the arrow of the menu (and the phone's
  back) goes alarms → print → list of recordings → AI monitor, instead of jumping to AI monitor.
* **Alarm pictures that stay**: the alert history keeps only its last 40 alarms with pictures, so older alarms of a recording
  lost theirs. Now the recording keeps its own copy (`alert-<id>.jpg`); alarms recorded before show the recorded frame of the
  alarm instead.
* **AI error 429** (the AI service refused: too many requests for its plan) is explained in words with the service's message;
  when the service asks to wait a few seconds (up to 30) the backend waits and asks once more, and it no longer resends at once
  with one picture (which got a second 429).

## 1.26.0

**Recordings you can judge at a glance** (roadmap phase 6a, second part).

* **The alarms are judged inside their print**: open a recorded print and its alarms are at the top, each with the picture the
  AI saw (tap to enlarge). The answers say what they mean: **Print OK** (a false alarm, the AI was wrong) and **Print KO** (a
  real problem, the AI was right). *See it among the pictures* jumps to the moment of the alarm in the print's pictures, which
  can be enlarged too. The phone's back goes from a print to the list.
* **The page in a clearer order**: the recorded prints first, then the measurement, then the settings. The alarms of prints that
  were not recorded are folded at the bottom.
* **Choose what to measure**: under *Prints to use* tick the recordings *Measure now* uses (a print with another camera or a
  test can be left out); the choice is remembered on the device. The backend accepts `{"ids": [...]}` and passes them to
  `replay.py --session`.

## 1.25.0

**The alarms of the AI monitor belong to one print, and you answer them** (roadmap phase 6a, first part).

* **The print card asks**: when the AI sees a problem, the card of the print in progress shows what it saw (with the picture)
  and three answers: **Real problem**, **False alarm**, **Ignore**. "False alarm" and "Ignore" put the AI badge back to green
  until the next alarm and the question goes; "Real problem" stays, reminding you to pause or cancel. "Real problem" and "False
  alarm" also label the alarm in the history and the recording, the data *Measure now* uses.
* **One print at a time**: the backend closes the alarm when a print starts and when it ends, so the badge and the verdict never
  carry over to the next print (before, the Config page and the badge stayed amber or red). The dashboard no longer keeps an old
  verdict in the browser.
* **The AI badge opens the panel**: the badge in the top bar is always there (grey with no print) and a tap opens the AI
  monitoring panel, with a button to its settings. The *Automatic AI monitoring* card left the Config page (and the desktop
  System page; the desktop strip opens the panel too).
* **Pictures to enlarge**: the AI monitor's pictures (the alarm in the print card and in the panel) open over the whole screen,
  fit or at their real size; the phone's back closes them.

## 1.24.0

**Sturdier app and menu** (roadmap phase 5f; Android app 1.4.0).

* **The app has no addresses of its own any more**: the first time it asks for the Raspberry's address, with an explanation
  (before, it tried the maintainer's). The external address (ZeroTier, VPN) is optional. Before showing *Retry / Addresses* it
  tries two rounds, local and external in turn, giving each 2.5 s.
* **Links outside the app**: websites, stores and `ntfy://` open in the right Android app instead of replacing the dashboard;
  the store buttons and *Open in the ntfy app* are back in the app's Notifications page. App data is no longer in Android's
  backups.
* **One "back" everywhere**: the arrow of the menu goes back to the page it came from (Camera → Camera calibration → back =
  Camera), and the phone's back button (app 1.4.0) closes the guide or the open dialog, goes to the previous page of the menu or
  the previous step of the guided set-up, and only then leaves.
* **Fewer accidents in the menu**: the swipe that closes it is longer (110 px), must be quick and sideways, and never starts on a
  slider, a field or a picture; a slider touched away from its knob while scrolling keeps its value (the number field is there
  for exact values), and a vertical drag on a slider scrolls the page.
* **System page**: CPU and memory are read again every 5 seconds while it is open.

## 1.23.0

**Installing on any Raspberry, and the camera's snapshot.**

* **The installer installs what is missing** with `apt` (asking the password once): `python3-flask`, `python3-requests`,
  `python3-numpy`, `python3-opencv` (the AI monitor; `--no-ai` leaves it out) and `git`. `--no-packages` only says what is
  missing. Without flask, requests or numpy it stops before touching anything, with the command to type.
* **numpy is really needed**, and the installer said it was optional: since the camera calibration (1.13.0) the backend did not
  start without it. Now the backend starts anyway (the calibration says what to install), and the installer installs it.
* **Debian 11 "Bullseye"** (Raspberry Pi OS before 2023, MainsailOS 1.x): with its Flask 1.1 the downloads (configuration files,
  the Android app, logos, recording pictures) failed; now they work there too.
* **Snapshot address** (Settings → Camera → Snapshot), like Mainsail's "Snapshot URL": the single photo the AI monitor, the
  camera calibration and the recordings take (later also the timelapse). Empty = automatic from the camera's address
  (`/webcam/?action=snapshot`, which every crowsnest streamer answers; `/webcam2/webrtc` → `/webcam2/?action=snapshot`; the
  adaptive method's own address). **Import from Mainsail** takes Mainsail's snapshot too. **Try: take a photo** shows the photo
  exactly as the Raspberry gets it, or why there is none. Before, the backend always asked `/webcam/snapshot`, which mjpg-streamer
  does not have.
* Guides: what is needed and what KlippEye installs by itself, the install lines (also for a Raspberry without git), the options.

## 1.22.0

**Guided and universal** (roadmap phase 5e): a new user sets KlippEye up from the dashboard, step by step, with a guide at hand
on every page.

* **Guided set-up**: the first time the dashboard is opened on a new installation it opens by itself: welcome (and the language
  of the device), name and logo, camera (with a live preview), addresses, printer functions, notifications, AI monitor (key and
  camera calibration), password, and a last step that says what is done, what is to do and what is optional, each leading
  back to its step. Every step can be skipped, the whole guide too; it is repeated from **Settings → Guided set-up**, where it
  restarts from the step it was left at. Installations set up with an earlier release are not asked again.
* **"?" everywhere**: every settings page has a **?** in its title bar that opens a short guide of that page, with a drawing
  where it helps (where to tap the nozzle in the camera calibration, what the addresses are for, what the AI monitor watches, the
  Z-offset gap, how the notifications travel). The groups that need a word more have their own small **?**, which opens the
  guide at their part.
* **The settings menu in four groups**: *The printer* (Name and logo, Printer functions, Z-offset), *Camera and AI monitor*,
  *Phone and network* (Notifications, Addresses), *System* (Access, Updates, Language), with *Guided set-up* on top.
  "Printer" is now "Name and logo" (it was easy to mistake for "Printer functions"). Camera leads to the camera calibration;
  the AI monitor's automatic actions lead to the notifications.
* **No one else's addresses**: a new installation no longer starts with the maintainer's IP addresses. Not set, the camera (and
  the Android app) use the address the dashboard was opened at, which is right in most homes; the addresses are only needed with
  ZeroTier, Tailscale or a VPN.
* Guides: a *Quick start* at the top (install, open, follow the guided set-up: about 15 minutes) and chapter 3 rewritten for the
  new menu. The end-to-end test checks a clean installation by a user other than `pi`.

## 1.21.0

**The KlippEye app receives the notifications by itself** (roadmap phase 5d, Android app 1.3.0). No ntfy app, no account, no
key: open the app, follow the guided procedure, done.

* **Settings → Notifications → This phone** (in the app): five guided steps (allow the notifications, make the private address,
  receive on this phone, let KlippEye stay awake, check that it arrives). The page confirms by itself when the test notification
  reaches the phone. The first time the app opens it asks whether to set them up. *Do not receive on this phone* turns them off
  on that phone only.
* The app listens to the private ntfy topic itself, also when closed and after the phone restarts (a small fixed notification
  "KlippEye in ascolto", which can be hidden), and catches up with the messages missed while offline. The dashboard keeps the app
  in step with the Raspberry (a new address, ntfy turned off) every time it is opened.
* **Firebase is only for the installation where its key is**: the app no longer has a Firebase topic built in (the one of the
  apps up to 1.2.0 was public in the repository, so anyone installing the published app could receive those notifications). The
  app takes the topic from its Raspberry, which gives it only when it has the Firebase key, and replaces the old public topic with
  a secret one the first time. The guides no longer explain Firebase; the maintainer's notes are in `android/README.md`.
* Phones without the KlippEye app (iPhone, or the ntfy app by choice) keep the QR-code procedure, under *Other phones*.
* Every pull request now compiles the Android app (before, only the merge did).

## 1.20.0

**Notifications without a Firebase of your own** (roadmap phase 5c). Until now push notifications needed your own Firebase
project and your own build of the app. Now they work with the free **ntfy** app, set up from the dashboard in a minute.

* **Settings → Notifications → Where they arrive**: *Turn on notifications with ntfy* makes a private random topic for this
  printer; install ntfy (Google Play, F-Droid, App Store), **scan the QR code** (or tap *Open in the ntfy app* on the phone, or
  type server and topic by hand), then **Send a test notification**: the page says, per channel, whether it went out and why not.
  *New address* makes another topic; *Turn ntfy off* keeps it for next time; an **ntfy server of your own** (with an optional
  token) can be used instead of ntfy.sh. Tapping a notification opens the dashboard.
* **Interchangeable channels**: the notification service sends through every channel set up (ntfy, Firebase, or both). A
  channel that fails is retried on its own, without sending again through the one that worked. Changes made in the dashboard
  are picked up without a restart. Firebase keeps working as before.
* **The notification service always runs** (new installations, and every run of `install.sh`): with no channel it sends
  nothing but still does the automatic pause / cancel of the AI monitor. `notifier.json` is no longer needed to start. When the
  service has not shown up, the page shows the command that installs it.
* `klippeye notify check` reports the channels and whether the ntfy server is reached; `klippeye notify test` tests every channel.
* The guide (chapter 6) explains the new way step by step.

## 1.19.0

**The AI monitor, in one place and without contradictions.** A review of everything the AI monitor does, after a real failure
was seen by the AI and still not reported.

* **One menu entry**: *Settings → AI monitor* is the only entry; *Camera calibration*, *Monitor thresholds* and *Recordings*
  are pages inside it (Back returns to it). The page says, top to bottom: monitor on, **how it looks at the print** (the whole bed
  outside the parts, or only the outer band of a rectangle when the camera is not calibrated), **what happens when it sees a
  problem**, and **the AI service** (key, earlier picture, model). The AI key can now be entered, changed and deleted here
  (it was only in the logs page, and deleting it did not work).
* **One confidence threshold**: there were two ("Minimum AI confidence" in the thresholds, used by the backend, and "Minimum AI
  confidence" in the AI monitor, used by the notification service). A value of 100% in the first one turned the AI's "pause"
  on a detached part into "continue". Now there is one, on the AI monitor page, from 30% to 95% (70% usual, a warning above
  85%); the old second one is ignored. A value of 100% saved before is replaced by 70%.
* **A downgraded verdict is no longer green**: when the AI proposed to pause or cancel and the threshold made it "continue", the
  alarm (Recordings) and the AI card say "Pause proposed, under the threshold" in orange, with the highest confidence.
* **The rectangle only when it is used**: the watched area and the outer band are shown in *Monitor thresholds* under
  "Without camera calibration", greyed out with an explanation while the camera is calibrated (the whole bed is watched).
  The switches of the masks and of the whole-bed watching moved to *Camera calibration*. "Ignore passing movements" (the old
  detection, which ignored masks and zone) is no longer offered.
* **The AI is waited for, not skipped**: an alarm that came while the AI was resting between two analyses was written as
  "skipped" and the monitor then rested its own pause on top, so a real failure could wait several minutes for its analysis.
  Now the monitor waits until the AI can look and checks again at once. Old "skipped" alarms are explained in plain words.
* **Checks in a row** says how much later each extra check makes the warning (at least the pause between two analyses).
* Recordings left open by a power cut are closed at the next start (they said "recording" for ever).

## 1.18.1

* **Measure now** no longer stops with an OpenCV error (`!buf.empty() in function 'imdecode_'`) when a recorded picture is
  empty or broken (it happens when the power goes while the picture is being written): such pictures are skipped and counted,
  and the result says how many.

## 1.18.0

**Printer functions (phase 5b of the roadmap).** The buttons that used the macros of one printer (PARK, WIPE, FILAMENT_LOAD,
FILAMENT_UNLOAD, luci_on / luci_off with the VAR_LUCI variable) now work on any printer, and say what they do.

* **Settings → Printer functions**, marked *To check* until confirmed: for park, wipe, load and unload the filament and the light,
  **Automatic** (the usual macro names found in Klipper), **Macro** (chosen from the printer's macros), **G-code** (written in the
  dashboard's editor), **Not used** (no button). The Control page shows only the buttons that do something.
* **Create a macro**: KlippEye proposes one (park, wipe, load, unload, light on / off), it opens in the editor and is saved into
  `klippeye_macros.cfg` (`backend/printer_macros.py`), included at the end of `printer.cfg` (with a backup); the page offers to
  restart Klipper (not while printing). Names that already exist in the configuration are refused.
* **The light switch reads the real output**: an `[output_pin]` value, a `[led]`/`[neopixel]` colour, or a *klipper-led_effect*
  effect running on it. The switch is right whoever changes the light (Mainsail, KlipperScreen, the console, a macro). The light
  can also be switched directly on its output (SET_PIN, SET_LED, STOP_LED_EFFECTS), without macros.
* **Filament change notification on any printer**: from Klipper's filament sensors, from macros announced by a small wrapper in
  `klippeye_macros.cfg` (rename_existing: it writes "KlippEye: filament change" and runs the original), or from a console line
  chosen in the dashboard. Only macros Klipper has can be announced (a wrong one would stop Klipper from starting).
* The dashboard's editor can edit a text that is not a file (a G-code or a macro being prepared).
* API: `/api/printer-macros` (GET; `/template`, `/macro`, `/wraps`).

## 1.17.0

**Any user, any folders (phase 5a of the roadmap: KlippEye for everyone).** The first step to make KlippEye work on any
Klipper printer, not only on the one it was born on.

* **No fixed home folder**: the macro files, Shake&Tune's files and the logs were looked for in `/home/pi/...`. Now the
  folders are asked to Moonraker (`/server/files/roots`, `backend/printer_paths.py`): any user, several printers
  (`printer_1_data`...), the old `~/klipper_config` layout. Without Moonraker, the usual places in the user's home.
* The installer finds the printer's data folder the same way (`KLIPPEYE_PRINTER_DATA=...` still chooses it by hand).
* **Axis travel and maximum temperatures from Klipper**: the "go to position" of the movement card was limited to
  X 350, Y 350, Z 300 and the temperature dialogs to 300 / 120 °C. Now they come from `[stepper_x/y/z]` position_min/max and
  from `[extruder]` / `[heater_bed]` max_temp; the starting position is the centre of the bed.
* The logs page no longer shows a fixed folder or an old `rm` command.
* New test `tests/test_no_fixed_paths.py` (part of `tests/run_all.sh`): it fails if a fixed `/home/<user>` comes back in the
  program, its scripts, the app or the guides.

## 1.16.0

**The whole bed watched, except where the parts are (phase 4c of the roadmap).** The first prints with 1.15 had no false
alarms, but a big failure went unseen: the monitor counted only the outer band of the watched area, and the masks could hide
a failure under the toolhead.

* **Expected zone** (`backend/print_zone.py`): with a usable camera calibration the monitor knows where the objects of the
  print are, from Klipper's `exclude_object` (slicers with "Label objects") or, otherwise, from the G-code of the print
  (read once in the background, line by line: its extrusions grouped on a 5 mm grid, one outline per object). It then
  watches the whole volume above the bed and counts what changes **outside** the objects (with a 6 mm margin, up to the
  height being printed): spaghetti next to the part, a part torn off. The part growing does not count. Without a calibration
  or without objects: the outer band, as before. New switch *False alarms → Watch the whole bed, except where the parts are*
  (on). During a print the calibration page draws the expected zone in green.
* **Masks no longer hide a failure**: a point covered by the toolhead in one of the last checks counts as "not seen", not as
  "unchanged", so the toolhead passing over a failure does not reset its persistence: each point must be seen changed in
  the last 3 checks (persist_checks) in which it was visible, looking back at most twice as far.
* **Fast moves**: the position of the toolhead is now read right before and right after the picture, and its way between
  them is covered by a chain of small boxes (one every 20 mm) instead of one big rectangle: on a fast printer the mask no
  longer covers a large part of the bed. The gantry still covers the band it sweeps.
* The toolhead and gantry sizes can go down to their minimum (0 below the nozzle tip) instead of being refused.
* Recordings keep the objects of the print; `klippeye replay` uses them (`--set expected_zone=off` to compare) and
  *Measure now* says so.

## 1.15.0

**The toolhead and the gantry left out of the AI monitor (phase 4b of the roadmap).** The recordings showed that most false
alarms come from the toolhead and the gantry moving in front of the camera.

* **Machine masks** (`backend/machine_masks.py`): with a good camera calibration, at every check the monitor knows where the
  toolhead and the gantry are (Klipper's live position just before and just after the picture, and the way
  between them) and leaves those parts of the picture out: out of the comparison, out of the background (each background picture
  keeps its own mask; the background is the median of the pictures that saw each point free) and out of the "the whole
  picture changed" check. Never half masks: without a calibration, or when the camera has moved, the monitor works as before.
  New switch *Monitor thresholds → False alarms → Leave out the toolhead and the gantry* (on).
* **Shape of the toolhead and of the gantry**, adjusted on the live picture (*Camera calibration*, after saving): left, right,
  front, back, above and below the nozzle for the toolhead; where the bar starts behind the nozzle, its depth and its lower
  and upper edges for the gantry (a bar across the whole X travel, drawn in ten pieces so that it follows the fisheye
  bending). Kept in `machine_shape.json`, also when the camera is calibrated again. `POST /api/camera/shape`.
* **Clearer calibration**: a small drawing and plain words at every point say what to tap (the lowest point of the nozzle,
  not the marker under it; the top tip of the marker); the steps of a point are explained above the list; the guide has a
  table of what to tap. The toolhead size is no longer asked at the start (the shape is adjusted after saving).
* **Replay with the masks**: `klippeye replay` leaves the toolhead and the gantry out on the recorded pictures that have the
  toolhead position, like the live monitor; `--set machine_masks=off` to compare. *Recordings → Measure now* says whether
  they were used. The recordings keep the position after the picture too (`live2`).

## 1.14.0

**Printed markers for the camera calibration.** The blobs of 1.13.0 were too small and left strings between them.

* **Print the markers (recommended)**: for printers where Z moves the bed, *Camera calibration* offers an STL with six
  small pyramids (16 mm wide, 10 mm tall) placed for your bed (`/api/camera/markers.stl`). You slice it with your own
  settings and print it; then you choose the G-code you printed and KlippEye reads from it where the pyramids are and how
  tall they came out (`backend/camera_markers.py`: the extrusions above the first millimetre, in six groups; skirt, brim
  and purge lines do not count). The tips of the pyramids are the points you tap with the bed lowered.
* **Quick blobs**, reworked: you choose the nozzle and bed temperatures; each blob is a 7 mm disc (a spiral, two layers);
  retraction and a Z hop between them, so no strings.
* The nozzle points of the calibration are taken just above the markers, and the printer never moves across the bed
  lower than the tallest marker.
* API: `POST /api/camera/calibration/markers {file}`, `GET /api/camera/gcode-files`, `GET /api/camera/markers.stl`;
  `POST /api/camera/calibration/marks` takes `{nozzle, bed}`.

## 1.13.0

**Camera calibration (phase 4a of the roadmap).** The first step of a monitor that knows where the toolhead is.

* **Settings → Camera calibration**: the printer goes to 12 points and you tap the nozzle tip (then again in a magnified
  view); KlippEye finds the camera (position, direction, focal length, lens bending: fisheye or ordinary,
  `backend/camera_model.py`) and says the average error in pixels and which points to redo. For printers where Z moves
  the bed (VzBot, Trident, V-Core) the nozzle alone stays at one height for the camera, so the printer first leaves six
  small blobs of filament on the bed and you tap them with the bed lowered.
* **Live check**: the toolhead outline, the nozzle and the bed are drawn over the live picture while you move the toolhead.
* **Has the camera moved?** The picture is compared with the one taken at calibration every ten minutes
  (`backend/camera_watch.py`, image features and RANSAC: the toolhead and the part do not count). If the camera moved, the
  page and the menu say so and the calibration is not used until it is done again (never half masks).
* The recordings now keep the real toolhead position (`motion_report.live_position`) with each picture, for the masks of
  the next release.
* API: `/api/camera/calibration` (options, home, goto, jog, marks, point, forget, fit, save, reset, delete),
  `/api/camera/overlay`, `/api/camera/check`.

## 1.12.0

**Measuring the AI monitor (phase 3 of the roadmap).** Until now nobody knew how many of the monitor's alarms are false:
this release records the prints and counts.

* **Recordings**: *Settings → Recordings → Record the prints* (off by default). During every print the backend keeps the
  pictures the monitor looked at (540x360, about 150 MB for four hours) with time, layer, toolhead position, progress, score
  and alarms, one folder per print in `~/printer_data/klippeye/recordings/`, plus the live alarms, the AI verdicts and the
  thresholds in use. A space limit (2 GB by default) deletes the oldest prints; with less than 1 GB free nothing is recorded.
* **Marking**: each alarm of the monitor can be marked *False alarm* or *Real problem*; each recorded print *It went fine*
  or *It failed from here* (on the picture where the problem starts), in a picture viewer that jumps from alarm to alarm.
* **Replay**: `klippeye replay` (and *Measure now* in the dashboard) runs the monitor again on the recordings and prints a
  table: alarms per hour, how many were false, which failures were caught and after how long. `--current` uses the
  thresholds in use now, `--set key=value` tries others. The AI is never called by the replay.
* **Monitor load**: the time of one check and the backend's CPU over the last minute, in the page, the recording and
  `klippeye diagnose`.
* The judging part of the monitor moved to `backend/monitor_core.py`, shared by the backend and the replay so that they
  always decide the same way (no change in behaviour: the tests that compare it with the original VzBot detector pass).
* `/api/recordings` (list, one recording, its pictures, label, delete, measure) and `/api/print/alerts/<id>/label`.

## 1.11.0

**The VzBot leftovers are gone.** Until release 1.0.x the project was called VzBot; releases 1.1.0 to 1.10.0 carried what
those installs needed to move to KlippEye. That move is done, so this release removes it:

* the folders `brain/` and `dashboard/`, `notifier/vzbot_notifier.py`, the `vzbot` and `vzbot-notifier` services and
  commands, and `scripts/passa-a-klippeye.sh` with the *Move to KlippEye* block of the dashboard (`/api/migrate/...`);
* the old names in the backend (`VZBOT_DATA`, `~/printer_data/vzbot`, `/app/VzBot.apk`, the `vzbot` update manager entry),
  in the dashboard (the `VzBotApp` bridge of the old Android app, the `vzbot_dashboard` settings namespace) and in the
  notifier (notifier 1.5);
* `scripts/install.sh` no longer looks for VzBot services, data or notification files; `--undo` now simply takes KlippEye
  off (services, commands, update manager entry).

* `scripts/install.sh` no longer asks for `flask-cors`: the backend has not needed it since 1.2.0 (found by the new
  end-to-end test).
* **End-to-end test published**: `tests/e2e/` installs and updates KlippEye on a simulated Raspberry with a real Moonraker
  and a local "GitHub" (install, update, rollback, recover, update channel, undo, power cuts, the Android app, the real
  dashboard in Chromium). It runs on GitHub too (*End-to-end* workflow); see [tests/e2e/README.md](tests/e2e/README.md).

An AI key or a calibration choice still in the home folder from before release 1.0 is copied once into the data folder.
The **VzBot** printer logo stays: it is the printer's brand. An install still on VzBot moves with release 1.10.0 first.

## 1.10.0

**Stable releases.**

* **Update channel**: *Settings → Updates → Update channel*. **Stable releases** (the default for new installs) installs only the
  releases tagged on GitHub once all their tests passed; **Every change** (`dev`, what every install used so far) installs
  each change as soon as it is on GitHub. The dashboard changes the `channel:` line of `[update_manager klippeye]` in
  `moonraker.conf` through Moonraker (with a backup copy in the data folder) and restarts Moonraker; refused while printing.
* `scripts/install.sh` writes `channel: stable` for a new entry; `--channel=dev` / `--channel=stable` changes an existing one.
* **Release workflow** (`.github/workflows/release.yml`, `ci/release.py`): when the tests pass on `main` it tags `vX.Y.Z`
  from `VERSION` and publishes a GitHub release with the CHANGELOG section. A release with a new Android app waits for the
  app to be built.
* The dashboard's "Release X available" reads the version of the release tag on the stable channel.

## 1.9.0

* **Diagnostic report**: `klippeye diagnose` (add `--save` to write it to a file) and *Settings → Updates → Diagnostics →
  Download a diagnostic report* collect release, git state, system, services, backend, Moonraker and its update manager,
  dashboard settings, the data folder (names and sizes only), self-repair and the last log lines, in one text to share when
  asking for help. Keys, password and tokens are never read or are hidden.
* **The dashboard opens faster**: the backend sends the page compressed (gzip, about a quarter of the size) with an ETag,
  so an unchanged page is not downloaded again.
* A leftover Italian message of the AI key form is translated.

## 1.8.1

* **English guide**: [docs/GUIDE.md](docs/GUIDE.md), written for anyone installing KlippEye on their own printer (install,
  first settings, updates, AI monitor, Android app and notifications, password, power cuts, troubleshooting, building your
  own app, moving from VzBot). [docs/GUIDA.md](docs/GUIDA.md) is now its Italian translation.
* The dashboard points to the guide of its own language; `logos/README.md` in English.

## 1.8.0

**Installer and terminal commands in English.**

* `scripts/install.sh` speaks English; its options are `--undo`, `--no-moonraker` and `--help` (the Italian
  `--annulla`, `--senza-moonraker` and `--aiuto` still work). `klippeye undo-install` uses `--undo`.
* The service templates in `systemd/` are in English (placeholders `@USER@`, `@CODE@`, `@DATA@`); services written by
  older releases are recognised and rewritten the next time the installer runs.
* The move from VzBot (`scripts/passa-a-klippeye.sh`, kept under its old name) and the old `vzbot` commands speak English.

## 1.7.0

**The backend speaks English** (and Italian where people read it).

* Messages for people (AI key, log analysis, the move from VzBot, the Android app offer, the page shown while the
  dashboard is being repaired) are in English and translated into the language of the dashboard that asked for them.
* The AI monitor's status line is in English and shown translated by the dashboard.
* The backend's log, comments and code descriptions are in English.

## 1.6.0

**The AI speaks your language.**

* The AI monitor's request is written in English and asks the AI to write what it sees (observation, notes, summary)
  in the language of the notifications (*Settings → Notifications*). The analyses started from the dashboard (print
  picture, logs) answer in the language of the dashboard on that device.
* The AI's advice is now `CONTINUE` / `PAUSE` / `CANCEL`; the dashboard shows it in its own language (`CONTINUA` /
  `PAUSA` / `CANCELLA` in Italian). Answers and alerts written the Italian way by older releases are still understood,
  also by the notification service (1.4).
* The prompts no longer name a specific printer: they work for any Klipper printer.
* The backend translates its own messages with the dashboard's dictionaries (`bt()`, checked by `frontend/tools/i18n.py check`).

## 1.5.0

**Notifications in your language.**

* The push notifications are in English or Italian: **Settings → Notifications → Language of the notifications**, one
  choice for every phone (the dashboard's own language stays per device). The list of notifications in that page shows
  the texts exactly as the phones will get them.
* Existing installs keep Italian notifications: the first time a dashboard of this release opens, it saves its own
  language as the notifications' language. Until then (or without any dashboard) the notifications are in English, or in
  the language written as `"language": "it"` in `notifier.json`. Texts written in `notifier.json` (`"messages"`) still win.
* The notification service (`klippeye-notifier`, 1.3) writes its log and its `--check` / `--test` answers in English.

## 1.4.0

**The dashboard speaks English and Italian.**

* Every text of the dashboard is now written in English and translated: Italian is the first translation
  (`frontend/src/i18n/it.json`). The page follows the language of the device (an Italian phone gets Italian, any other
  language gets English) and **Settings → Language** lets you choose on each device (*Automatic*, *English*, *Italiano*).
  The choice stays on that device only; changing it reloads the page.
* Dates, times and numbers follow the chosen language too.
* The names and explanations of the AI monitor thresholds come from the backend in English and are shown in the page's
  language; the backend's error messages for the thresholds are in English.
* For translators: texts are marked with `tx("English text")` in `frontend/src/app`; `python3 frontend/tools/i18n.py check`
  (also run by the tests) fails when a text has no translation. A new language is one more `src/i18n/<code>.json` file
  plus one line in `I18N_LANGUAGES` (`src/app/02-i18n.js`).
* Still in Italian, to be translated next: the push notifications, the AI analysis texts and the messages of the move from VzBot.

## 1.3.0

English names on the Raspberry (first step of the move to English; the dashboard text comes next):

* **`klippeye` commands in English**: `status`, `version`, `log [notifier]`, `restart [backend|notifier|all]`, `repair [log]`,
  `update [--force]`, `notify test|check`, `undo-install`, `help`. The Italian names (`stato`, `riavvia`, `aggiorna`, `ripara`,
  `notifiche prova`, `annulla`...) still work. `klippeye-notifiche` accepts `test | check | status | log | restart | uninstall` too.
* **Self-repair** is now `scripts/repair.sh` (`--quiet`, `--enable-at-start`); `scripts/ripara.sh` stays as a wrapper for the services
  installed by older releases. Its files are `repair.log`, `repair.json` and the opt-out `no-repair`.
* **Data folder, English names**: `monitor.json` (AI monitor thresholds, was `brain.json`), `alerts/history.jsonl` and pictures
  `*-now.jpg` / `*-before.jpg` (was `allarmi/storico.jsonl`, `-adesso`, `-prima`), damaged copies `*.damaged-<time>`.
  **Existing files are renamed automatically** at the first start, nothing is lost; old alert entries are read with the new keys
  (`outcome`, `observation`, `with_reference`, `filter`, `original_action`).
* `apk/versione.json` is now `apk/version.json`.
* `install.sh` removes both the old (`ripara.conf`) and the new (`repair.conf`) self-repair drop-in when it rewrites the service.

## Repository changes after 1.2.0

Almost only the repository; on the Raspberry the only change is a minimum space between the printer name and the round
buttons of the top bar (on 360-pixel phones they could touch).

* **License: GNU GPL v3.0** (`LICENSE`), the same as Klipper, Moonraker, Mainsail and Fluidd; third-party components in `THIRD_PARTY_NOTICES.md`.
* **Dashboard sources** are now in the repository (`frontend/src`, `frontend/build.py`): the published `frontend/klippeye_frontend.html`
  is rebuilt from them and the tests check it is identical.
* **Automatic tests** in `tests/` (backend, notifier, app build steps, dashboard in the browser) and a GitHub workflow that runs
  them on every pull request (`.github/workflows/tests.yml`). Run them locally with `bash tests/run_all.sh`.
* `SECURITY.md`, `CONTRIBUTING.md`, issue and pull-request templates; `README.md` in English.
* From now on code, commands, file names, commit messages and documentation are written in English; the existing Italian
  parts will be translated step by step (the dashboard will get English and Italian).

## 1.2.0

* **Password facoltativa** (*Impostazioni → Accesso*): spenta di serie, quindi tutto funziona come prima finché non la attivi. Con la password attiva ogni dispositivo
  (browser o app) la chiede una volta e la ricorda per 6 mesi; senza accesso il backend non apre niente: dashboard, camera, comandi, file, log e il ponte verso Moonraker.
  Dal menu: attivarla, cambiarla, toglierla, far uscire gli altri dispositivi, uscire da questo. Dal Raspberry: `klippeye password` (set), `klippeye password remove`
  (password dimenticata), `klippeye password status`, `klippeye password logout-all`. Non viene mai salvata la password, solo il suo «hash» con sale in
  `~/printer_data/klippeye/access.json` (permessi 600). Dopo 5 tentativi sbagliati dallo stesso indirizzo bisogna aspettare (da 2 secondi a 5 minuti).
* **Controlli di rete, sempre attivi** (anche senza password): il backend risponde solo se lo chiami con un indirizzo IP, il nome del Raspberry o un nome della rete
  di casa (`.local`, `.lan`…), e rifiuta i comandi che arrivano da pagine di altri siti. Niente più CORS «aperto a tutti». Per un nome tuo (es. un dominio):
  `klippeye access host-add NOME`; per tornare al comportamento di prima: `klippeye access network-checks off`.
* **I servizi del Raspberry** (notifiche, comando `klippeye`) si presentano al backend con un gettone interno (`internal.token`, permessi 600): le notifiche
  dell'IA funzionano anche con la password attiva.
* **Permessi dei segreti**: all'avvio il backend riporta a 600 `ai.json`, `service-account.json`, `notifier.json`, `access.json` e alla cartella dati 700
  se qualcuno li ha copiati a mano con permessi larghi (lo scrive nel log).
* La chiave dell'IA nella dashboard si vede solo nelle ultime 4 lettere (prima anche le prime 8).
* **App Android 1.2.0**: i download (log, file, immagini) mandano il cookie di accesso; il cookie resta salvato anche se Android chiude l'app.
* Nomi tecnici nuovi in inglese, in vista della distribuzione: file `access.json` e `internal.token`, pagina `/login`, comandi `klippeye password set|remove|status|logout-all`
  e `klippeye access host-add|host-remove|network-checks|status`. La pagina di accesso e i messaggi di rifiuto sono in inglese, o in italiano se il dispositivo è in italiano.
* `flask_cors` non serve più (resta facoltativo, solo per sviluppo con `KLIPPEYE_CORS`).

## 1.1.1

* **Monitor IA con meno falsi allarmi**: il confronto non usa più solo la foto precedente ma uno sfondo calcolato su più foto (la mediana di 7 foto, coperte per circa un minuto), perciò
  la testina e i passaggi veloci spariscono dallo sfondo; ignora i cambi di luce (se più del 30% dell'immagine cambia di colpo, quel controllo non conta) e normalizza la luminosità;
  un cambiamento conta solo se **resta** per alcuni controlli di fila; all'IA online va anche la foto di riferimento (prima) con un testo neutro; se l'IA non è abbastanza sicura
  (fiducia sotto il 70%) il problema non viene segnalato. Nuovo **storico degli allarmi** con le immagini in `~/printer_data/klippeye/allarmi/`
  (`/api/print/alerts/history`). Tutte le soglie si regolano da *Impostazioni → Monitor IA*; «Ignora i movimenti passeggeri» spento riporta il comportamento di prima.
* Corretto: dopo «spegni e riaccendi» il monitor poteva avere per qualche secondo due cicli di controllo insieme; ora il vecchio ciclo si ferma subito.
* App Android: invariata (1.1.0).

## 1.1.0

* **Riparazione automatica dopo un blackout**: se la corrente salta e un file del programma resta vuoto o a metà (dashboard bianca, servizio che non parte), a ogni avvio
  `scripts/ripara.sh` confronta i file con la copia buona che git ha sul Raspberry (niente internet) e rimette a posto solo quelli rovinati o spariti, toglie anche il blocco di git
  rimasto. Parte prima del servizio (`ExecStartPre`), all'avvio del backend e quando la pagina risulta vuota/troncata (che mostra intanto una pagina d'emergenza 503 che si ricarica
  da sola). Il servizio già installato riceve la riga da solo (integrazione `klippeye.service.d/ripara.conf`) se il sistema lo permette senza password; `install.sh` la rende definitiva.
  Non tocca dati e impostazioni; si spegne con un file vuoto `~/printer_data/klippeye/non-riparare`. Nuovo comando `klippeye ripara [log]`, registro `riparazioni.log`, campo `repair` in `/api/version`.
  Guida: parte G.
**Il progetto si chiama KlippEye** (prima VzBot), in tutto: cartelle, file, servizi, comandi, dashboard e app.

* **Passaggio con un tasto**: chi ha VzBot 1.0.x aggiorna come sempre, poi in *Impostazioni → Aggiornamenti* compare **Passa a KlippEye** (o da terminale:
  `bash ~/vzbot/scripts/passa-a-klippeye.sh`). In 6 passi, con ripristino automatico se qualcosa non va: copia i dati (`~/printer_data/vzbot` → `klippeye`, gli originali
  restano), sposta il programma da `~/vzbot` a `~/klippeye`, installa i servizi `klippeye` e `klippeye-notifier`, aggiorna la voce di Moonraker (`[update_manager klippeye]`
  e `moonraker.asvc`), toglie i servizi e i comandi vecchi (con copia di sicurezza) e controlla che il backend risponda.
* **Nuovi nomi** — cartelle: `backend/` (era `brain/`), `frontend/` (era `dashboard/`), `logos/`; file: `klippeye_backend.py`, `klippeye_frontend.html`, `klippeye_notifier.py`;
  servizi: `klippeye`, `klippeye-notifier`; comandi: `klippeye`, `klippeye-notifiche`; cartella dati `~/printer_data/klippeye`; variabili `KLIPPEYE_*`; segreto GitHub `KLIPPEYE_CHIAVE_PASSWORD`
  (il vecchio `VZBOT_CHIAVE_PASSWORD` vale ancora). In codice e nomi di file i nomi sono in minuscolo (`klippeye`), nei testi `KlippEye`.
  I file vecchi (`brain/vzbot_brain.py`, `notifier/vzbot_notifier.py`, `scripts/vzbot*`) restano come rimandi ai nuovi finché serve il passaggio: dopo si possono cancellare.
* **Stampante: nome e logo** (*Impostazioni → Stampante*): scegli il logo della barra in alto tra **KlippEye** (predefinito), **VzBot**, **Voron** e **RatRig** e, se vuoi, un nome tuo
  (per esempio `VzBot.287`). Cambiano anche il **titolo e l'icona della scheda del browser**. La scelta è nelle impostazioni condivise, uguale su ogni dispositivo.
  I loghi di Voron e RatRig vanno messi (file ufficiali) nella cartella `logos/` del repository: vedi `logos/README.md`.
* **App Android 1.1.0 con nome interno nuovo**: `com.klippeye.app` (era `com.vzbot.dashboard`), ponte `KlippEyeApp`. Si installa accanto alla vecchia, poi si disinstalla quella; la dashboard
  dentro la vecchia app propone *Installa la nuova app KlippEye*. Serve registrare l'app nuova in Firebase e aggiornare il segreto `GOOGLE_SERVICES_JSON` (guida, parte P5).
  L'argomento delle notifiche non cambia. La chiave di firma nuova è `android/chiave/klippeye.p12`.
* Le impostazioni condivise stanno ora in `klippeye` nel database di Moonraker (le vecchie, `vzbot_dashboard`, si leggono ancora la prima volta); le preferenze del browser (`vz_*`) diventano `ke_*` da sole.
* Nelle schermate «Brain» è diventato «backend».
* **Finestra dei parametri delle macro**: il testo dei pulsanti (per esempio «Esegui Axes shaper calibration») va a capo e si rimpicciolisce da solo, in base alla lunghezza e alla larghezza
  del pulsante (cioè dello schermo), invece di essere tagliato; un titolo lungo va a capo e non spinge più fuori la X di chiusura.
* **Console**: il tasto di invio ha l'icona dell'aeroplanino pieno, come quello di WhatsApp (telefono e PC).
* La calibrazione scelta (prima in `printer_data/config/vzbot_calibration_selected.json`, che nessuna macro usa) ora sta nella cartella dati come `calibration_selected.json`; il file vecchio, se c'è, si legge ancora e non si perde niente.

## 1.0.1

Nuovo logo e nuovi colori: **KlippEye**.

* **Logo KlippEye** (la «lente stampata»: strati viola che formano un occhio, con l'ugello sopra e la pupilla al centro) al posto di quello di VzBot:
  nella barra in alto, nel menu delle impostazioni, nell'icona della scheda del browser e nella schermata «aggiungi alla home».
* **Barra in alto**: la scritta *VzBot.287* diventa **KlippEye** (*Klipp* bianco, *Eye* viola). Il font della scritta (Outfit, 1 KB) è dentro la pagina: funziona anche senza internet.
* **Colori della dashboard**: l'accento non è più l'azzurro di One UI ma il **viola chiaro del logo** (`#b79cff`): tasto di homing, tasti di conferma, barre di avanzamento e
  cursori, interruttori e caselle spuntate, evidenziazione dei tasti della barra in basso, schede e file selezionati. I tasti pieni hanno il testo scuro (si leggeva male il bianco sul viola chiaro).
  Lo **sfondo** è il viola scuro del riquadro del logo che sfuma verso il nero. I file di codice (`.py`, `.sh`…) passano dal viola all'azzurro per restare distinguibili dai file di configurazione.
* Sui telefoni larghi 341-374 px (per esempio 360) il logo ora si vede anche nella barra in alto.
* **App Android 1.0.1**: icona con il logo sul riquadro viola scuro (come fondo dell'icona), icona delle notifiche e splash nuove, colore d'accento viola.
  GitHub costruisce l'app da solo perché `android/VERSION` è già alzato; poi, nell'app, **Aggiorna l'app**.
* Restano per ora i nomi «VzBot» (titolo della scheda, servizi, cartelle, nome dell'app): il cambio di nome completo a KlippEye è un lavoro a parte.

## 1.0.0

Prima release "a contenitore": programma e dati separati, aggiornamento dalla dashboard.

* **Aggiornamenti dalla dashboard** (Impostazioni → Aggiornamenti): release installata, controllo di GitHub, "Aggiorna VzBot",
  "Torna alla versione precedente", "Ripristina i file del programma" e riavvio del Brain e delle notifiche. Usa l'update manager
  di Moonraker, quindi funziona anche da Mainsail e Fluidd.
* **Soglie del monitor IA** (Impostazioni → Soglie del monitor): sensibilità, area controllata (con anteprima sulla foto della
  camera), pause, attese e modello dell'IA si cambiano dalla dashboard, valgono subito e restano sul Raspberry. Il Brain descrive
  da sé le proprie impostazioni: una nuova soglia compare nel menu senza aggiornare la dashboard.
* **Disposizione nuova dei file**: programma in `~/vzbot` (un repository git), dati in `~/printer_data/vzbot`, servizi `vzbot` e
  `vzbot-notifier` avviati a ogni accensione, comandi `vzbot` e `vzbot-notifiche`.
* **`scripts/install.sh`**: si lancia una volta, sposta senza cancellare quello che c'era (chiave dell'IA, notifiche), collega
  Moonraker e, se il Brain nuovo non parte, rimette a posto il servizio di prima. `--annulla` torna a com'era.
* Il Brain ha una pagina `/api/version` (release, commit, da quanto è acceso) e `/api/brain/config` (le soglie).
* Il servizio delle notifiche si ricarica da solo quando un aggiornamento ne sostituisce il file.
* **App Android 1.0.0** (la numerazione dell'app riparte da qui: prima era «mk218», `android/VERSION`): il progetto Android sta nel repository (`android/`);
  GitHub costruisce e firma l'APK (`.github/workflows/app.yml`, passi in `ci/app_ci.py`) e lo salva in `apk/`; il Brain lo offre
  (`/api/app/version`, `/app/VzBot.apk`, solo se grandezza e impronta coincidono con `apk/versione.json`); la dashboard ha il blocco **App Android**
  in Impostazioni → Aggiornamenti, e dentro l'app c'è **Aggiorna l'app** (scarica, controlla l'impronta, apre l'installazione di Android).
  Il ponte dell'app (`VzBotApp/5`) ha `appInfo` e `updateApp`. La firma è la stessa a ogni versione (`android/chiave/vzbot.p12`, cifrata con un segreto di GitHub):
  chi ha l'app installata da Android Studio deve disinstallarla una volta, perché la firma è diversa.
