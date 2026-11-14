# Changelog (Cosa cambia in ogni release)

## 1.128.0

**Calibrating the camera without printing anything.** When Z moves the bed, the calibration needed six markers printed
on the bed (or six blobs), because the nozzle tip is always at the same height and a second height was missing. Now the
recommended way gives that height with **a detail of the toolhead**: a screw head, a corner of the cover, anything small
and sharp higher than the nozzle. At each of six places you tap the nozzle tip and that detail, and KlippEye works out
by itself how much higher the detail is. The page explains how to choose it. The markers and the blobs stay as the
other way.

**Finding the points by itself no longer takes reflections.** It searched the whole moving toolhead for something that
looked like the nozzle, and often chose a reflection or a piece of the background. Now it starts from a place already
tapped and moves a few mm at a time, following the tip (and the detail) in the picture and looking only next to where
they should be. The picture it looks for is updated on the way, as what is behind the nozzle changes. A point lost on
the way is left to tap by hand instead of being guessed. With a detail of the toolhead, tap the tip and the detail at
the first place, then **Find the other 10 points by themselves**.

## 1.127.0

**The AI monitor watches the bed, not the whole travel.** Until now the watched area went from the toolhead's minimum
to its maximum travel, which on many printers goes beyond the plate: a purge bucket, a brush, the frame. Changes there
counted as possible failures. The bed is now worked out from Klipper's bed mesh (its area, a little wider), and the
calibration page has a **Bed area** with its four edges to adjust with − and +; the dashed outline on the live picture
follows. Without a mesh the travel is used as before.

**A camera that moved a little is corrected by itself.** Before, any move of more than a few pixels switched the
calibration off until it was done again. A small move (up to about 5% of the picture) is now checked again a minute
later and, when three looks in a row agree, corrected from what stays still in the picture: the frame and the bed's
edges, never the nozzle. The calibration itself is not changed; the page says by how much it was corrected, and **Do not
trust it** undoes it. A bigger move asks to calibrate again, as before.

**The same margin on every side of the parts.** The 6 mm around each part was made by pushing its corners away from
the centre: a long thin part got almost no margin along its long sides, and its edge (elephant foot, brim) could count
as a change. The margin is now the same all around.

## 1.126.0

**The dashboard no longer gets stuck after a while.** On a page left open, or coming back to it, it could stop
updating until the page was reloaded by hand, on every device.

* An answer whose connection fell asleep halfway (the start arrived, the rest never did) kept its read waiting for
  ever. The status, temperatures and the rest then stopped updating, also with the page in front of you. Reads now give
  up when nothing more arrives for a few seconds. A long download that keeps arriving, such as a G-code in the viewer,
  is never cut.
* A refresh that takes far too long is dropped, and the next one starts.
* A watchdog notices when no answer at all has arrived for 15 seconds. It shows «Reconnecting…» at the top and gets the
  connection back by itself. If nothing comes within a minute and the printer answers again, it reloads the page on the
  same tab.
* Away for more than 10 minutes, the page is reloaded as soon as you come back: quicker than bringing old data back to
  life.
* Never with unsaved changes in the configuration editor, never twice in a row, and never while the printer does not
  answer: then it says «The printer does not answer: trying again…» and tries again, further and further apart.

## 1.125.0

**The local model learns from its false alarms, live.**

* Mark an alarm as *False alarm* and the local model remembers that scene: a picture like it, rated not much higher, no
  longer counts as a doubt or as sure. No alarm, no pause, no online question for it. A worse picture of the same scene,
  or another scene, still counts.
* When the online AI finds nothing where the local model had a doubt, the scene is remembered for a few hours: no more
  questions every minute for the same thing, and no more spent credits.
* What it learned is kept apart from the recordings and the alarm list (deleting them forgets nothing), with a small copy
  of each picture you marked, so it is described again when a new local model arrives. *Real problem* on the same alarm
  forgets the scene; **Local model → Forget the false alarms it learned** forgets them all.
* The AI monitoring panel says when the local model recognises a scene it learned, and so does *Try the local model now*.

**The purge is hidden.** With a calibrated camera, KlippEye compares the bed when the print starts with the bed when the
real print starts. What appeared outside the parts (a purge line, also an adaptive one next to the print area, a blob) is
covered with the empty bed before the local model looks, and OpenCV ignores it, also if it is pulled off by hand. A change
of the light is not taken for a purge.

**What the personal layer learns from is kept apart.** A small copy of every picture that becomes an example (an answer
to «How did the print go?», a labelled recording) is kept with its label, also while learning is off: deleting
recordings, or the oldest answers going, no longer takes examples away. At most 4000 copies: every failed one, the oldest
fine ones go first.

**Several recordings deleted at once.** *Choose several to delete* under *Recorded prints* puts a tick on each print
(*Tick all*, *Untick all*), then *Delete (n)* asks once. The print being recorded cannot be chosen.

## 1.124.0

**OpenCV and the local model now help each other.**

* When OpenCV sees a change, the local model looks at once, closer at that spot, and keeps looking there for five
  minutes: a part that came off and lies still is no longer forgotten once it stops moving.
* With a calibrated camera the local model also looks closer at the printed part, not only at the whole picture, where
  a small defect was too small for it to see.
* When the local model has a doubt, OpenCV raises an alarm sooner for a minute: 60% of the usual change is enough, and
  one suspicious check fewer.

**The AI monitoring panel shows both scores.** The local model's tile was missing, and OpenCV's score alone looked broken:
it goes back to 0% once a change stops changing. Now each tile has the last score and the highest of the print, and
**Try the local model now** rates the camera's picture there and then, to see whether it recognises a defect.

**Monitor thresholds, simpler.** The page starts with *How watchful it is*: Few false alarms, Balanced or Notices more,
which moves OpenCV and the local model together. The single numbers are under *Fine adjustments*, grouped by what they
do; a number that does nothing with your setup is hidden (the local model's without a local model, the pause between AI
analyses without the online AI). *In doubt from* can no longer be set above *Sure from*. Some names and explanations were
corrected: *Changed area for a suspicious check* replaces *Movement at the edges*, which was wrong with a calibrated
camera.

**Backup services and second opinion, checked.**

* When the second opinion's answer cannot be read, the next service is asked, instead of letting the first verdict
  stand unconfirmed.
* A second opinion that sees nothing no longer lets a failure go when the local model is sure of it on the same new
  picture.
* The second look tells the AI the local model's opinion of the new picture, not of the first one.
* A print that ends during the 40 seconds of the second look is not «stopped»: the alarm says it ended first.

## 1.123.0

**The configuration editor keeps its height when Klipper is in error or starting.** On a computer, the Klipper panel
used to take a large part of the Config page and left the editor only a few lines. With a file open it is now a single
line with the state, the first line of Klipper's message and the restart and log buttons; «Whole message» shows the
rest. Close the file and the full panel comes back.

## 1.122.0

**«How did the print go?»: a big picture to choose from.** When you tell from when a problem can be seen, the picture is
now as wide as the card, with the slider and the ‹ › buttons right under it, and a label on the picture with its number,
time, progress and layer. A tap opens it over the whole screen, to zoom on a small defect.

The pictures of a print are kept three times as wide (960 pixels) until you answer; once answered, or when the next print
starts, they are made small again, so the space they take on the Raspberry does not grow.

**Fewer calls to the online AI.** With a calibrated camera KlippEye now knows when the print head is in front of the part.
A question is then put off until the head moves away (within 90 seconds), the second look of a stop waits for it too, and
an «empty bed» seen through the head never counts.

## 1.121.0

**Far fewer false «empty bed» alarms.** The AI used to judge «empty bed» without knowing what to look for, and from a
single picture a part that came off and a part the camera cannot see look the same. Now:

* the AI is told how many objects are printed, how big the biggest one is, how high the print is and, with a calibrated
  camera, where the part should be in the picture;
* «empty bed» counts only when the part is clearly visible in the earlier picture and gone in the new one: with a single
  picture it is never trusted;
* it needs the AI to be at least 85% sure (the other defects keep your threshold), the print to be at least 2 mm high and
  the part at least 2 cm across;
* when one of these is missing, «empty bed» does not count; if a pause or a cancel rested on it alone, the print goes on
  and the AI's panel says why. Spaghetti, layer shifts and warping are judged as before.

## 1.120.0

**New guides, written from scratch for whoever uses the printer.** The [user guide](https://github.com/BotuPotto/KlippEye/blob/main/docs/GUIDE.md) goes from installing to
everyday use, with what to do when something goes wrong and the questions people ask; the dashboard has its own reference,
[page by page](https://github.com/BotuPotto/KlippEye/blob/main/docs/FEATURES.md). Both are in Italian too ([GUIDA](https://github.com/BotuPotto/KlippEye/blob/main/docs/GUIDA.md), [FUNZIONI](https://github.com/BotuPotto/KlippEye/blob/main/docs/FUNZIONI.md)), with
pictures of the dashboard. The README, the contributing and security pages and the other READMEs were rewritten as well.

**GitHub releases again.** The releases stopped at 1.94.0 because a release number with three digits in the middle
(1.100.0 and later) was not recognised. They are tagged again, and this one gets its own release page.

* Numbers in English (and the other languages that use a point) are written with a point: «6.3 mm³/s», not «6,3».
* «KlippEye found 1 lights» is now «KlippEye found one light».
* The guided set-up says that the online AI is optional: without a key the local model judges alone.

## 1.119.0

**The AI monitor can do without the online AI.** Settings → AI monitor → The AI service → «Who judges the pictures»:
«Local model only» sends no picture to the internet. The local model judges alone: when it is sure for three looks in a
row it proposes a pause, and «Pause by itself» does it. Without a local model the page says that nothing can judge. The
keys of the online services stay saved for when you switch back; the analysis of the logs is not affected.

**The settings, page by page, in every language and look.** A new check (tests/ui/settings_audit.py) opens every page
of the settings in the ten languages, the eight looks, dark and light, and looks for what reads badly. What it found:

* the grey of the small texts was too pale in dark mode (and more in Liquid Glass): now readable on every box;
* the green of the badges in light mode was too pale on its own background;
* in light mode (Soft, HyperOS, Studio, Liquid Glass) the boxes were almost the colour of the panel: a thin edge now;
* «All right» on Printer functions sat inside the last line of the text: now under it;
* the «add» buttons (a light, a material, a backup service) all look the same, as on Camera;
* the six values of «Minimum AI confidence» stay on one row on a phone;
* the names of the cards on Appearance go on two lines before being cut (German, Polish...);
* the logos on Appearance: their names start at the same place;
* Appearance, Your printers and Materials have their «?» guide, as every other page.

## 1.118.0

**A full review of the code, part 4: every module read line by line.** Nothing new to learn; a few fixes and a lot of
tidying.

* **Notifications**: the error of Firebase and one line of the service's log were still in Italian; the code that reads
  the AI's verdict from its text is written once.
* **Self-repair** (after a power cut) now also checks the files of the local AI model, and no longer a folder that has not
  existed for a long time.
* **Diagnostic report**: the hiding of keys and passwords is simpler and also hides the keys of one more AI service.
* The old internal name of the KlippEye service ("brain") is gone from the code: it is called the backend everywhere. The
  command `klippeye` also reads `KLIPPEYE_BACKEND_URL` (the old `KLIPPEYE_BRAIN_URL` still works).
* `klippeye update` says what it really does: it installs the newest version of the branch, while the dashboard follows
  the update channel.
* Comments and documentation no longer name other printer interfaces.

## 1.117.0

**Android app 1.8.0: in your language.** Update it from Settings → Updates → Android app once KlippEye is updated.

* The app's own screens (the splash, the «Addresses» window, its messages, the names of the notification channels) follow
  the phone's language, in the same ten languages as the dashboard; they were in Italian only. The errors of the app's own
  update shown in the dashboard follow it too.
* Safer: the app's window no longer opens the phone's own files as pages, and it no longer carries two fixed home
  addresses that were left in its network settings.
* The back key uses Android's current method (ready for the «predictive back» gesture of the newest phones).
* Under the hood: the app's code is in English like the rest of the project, and its tests run on GitHub with every pull
  request. The addresses, the printers and the notification choices stored on the phone are kept.

## 1.116.0

**A full review of the code, part 1: the backend.** Nothing new to learn: the oldest parts of the backend were rewritten
in the style of the rest, with a few real fixes found on the way.

* **AI monitor**: an answer of the online AI that cannot be read (cut off, not in the expected shape) no longer counts
  as «pause the print»: it is written in the history and the print goes on. The picture sent to the AI is the very one
  the alarm was raised on (it was taken again a moment later), and the pictures waiting for the AI are kept in KlippEye's
  own data folder instead of the shared temporary folder.
* **Macros**: one list, made by the backend (new module `macro_catalog.py`): Klipper's configuration first, then the
  files of the configuration folder. A parameter's default is no longer given to another parameter of the same line;
  dated copies of the configuration and the `.git` folder are not read.
* **Printer and camera addresses passed on by the backend**: the connection to the printer is always closed when the
  page goes away, and the cookie and the internal key of KlippEye are not passed on.
* **Logs**: the routes share one check of the file name; the text given to the AI is built in one place.
* Tidier code: imports at the top, old section names and unused code removed, one module (`labelled_prints.py`) for
  reading the labelled prints (it was written three times), a tool that only gave false alarms deleted, an old copy of
  the app (6 MB) that nothing used removed from the repository.
* The Python code is now checked by a linter (`ruff`, settings in `pyproject.toml`) on every pull request.

## 1.115.0

**Clearer on the light page, and the movement wheel redrawn.**

* The **movement wheel** (Home → Movement) has real gaps between its four parts instead of black lines: the page shows
  through them, light or dark, in every look. The steps (+1, −10…) are written in those gaps, a little bigger, in the
  page's own text colour.
* Light page: the green, orange and red of the badges («Connected», «Up to date», the AI button of the logs…) are deeper,
  and the small grey notes darker, so they read on the white cards; the «Copy» buttons of the commands stay readable on
  their dark box; the options that cannot be changed («always there») are less faded.

## 1.114.0

**KlippEye's own local model is here.** The AI monitor now comes with a small model (`models/base/`, about 6 MB) that
runs on the Raspberry, without internet, and looks for a failing print: it judges the alarms of the motion detection,
so the online AI is asked only when a picture looks doubtful, and every 15 seconds it also looks by itself, so a failure
the motion detection misses is still caught.

* Trained on 38,247 photos from 19 public collections of 3D print failures (spaghetti, detachment, layer shifts, blobs…),
  each credited with its licence in `models/base/CREDITS.md`. On photos it never saw: about 95 failures out of 100
  caught, and 95 alarms out of 100 right.
* Public photos are not your camera and your light: «Learn from this printer's prints» (Settings → AI monitor) adapts
  it to your printer, from the prints you judge.
* A model you trained yourself (data folder → `model/`) is still used instead of this one.

## 1.113.0

**Tidier pages, your own materials, and the ZeroTier guide.**

* The **system logs** moved from Config to the **System** page (as on a computer): Config keeps only the configuration files.
* Control → Tune: **Machine limits** and **Firmware retraction** start folded, one tap opens them (the device remembers);
  folded, a dot says when one of their values differs from printer.cfg.
* **Settings → Materials**: the materials of the temperature window are the printer's own, to change, add or remove
  (and back to the usual ones); **Edit** in the window opens the page. With **Spoolman**, the spool in use comes first,
  with its filament's temperatures.
* **Settings → Addresses → From outside home with ZeroTier: the guide**: six steps with the commands to copy, from the
  free account to the address to write in KlippEye; they follow the guide of Pi My Life Up, credited with its link.

## 1.112.0

**Materials in the temperature window.** Tap the nozzle or the bed: the usual **materials**, PLA, PETG, ABS, ASA and
TPU, set the nozzle and the bed together with one tap; **Off** switches off the heater the window was opened for.

## 1.111.0

**The guided set-up, brought up to date** with what KlippEye learned since it was made.

* Welcome: besides the language, the **theme** (dark, light, as the device).
* AI monitor: **Google Gemini** suggested for the free key (its free plan allows many more checks a day), the **backup
  services** mentioned, and a new group **Learning from your prints**: «Ask how each print went» and «Learn from this
  printer's prints».
* A new optional step, **Home Assistant**, only for who uses it; the optional steps (addresses, Home Assistant, password)
  now come last. The summary at the end shows Home Assistant as done when it is connected.
* Translations: the new texts of the last releases in Portuguese (Brazil), like the rest; «Look» was translated as the verb in
  five languages.
* GUIDE / GUIDA: the new groups of the menu and its search, the theme, the new looks, the guided set-up.

## 1.110.0

**The settings menu, easier to find your way in.**

* Clearer groups: *The printer*; *Camera, monitor and notifications* (the notifications now sit with what watches the
  print); *Appearance and language*; *Network and system*.
* A **search** at the top of the menu: it finds any page, also the ones inside another (Monitor thresholds,
  Recordings, Camera calibration, Timelapse), by its name, by what it is set to, or by words a person would use
  («dark», «password», «spaghetti»…), with or without accents.
* The menu's help («What is where») describes the new groups.

## 1.109.0

**Four more looks and a few small animations.**

* Settings → Appearance → Look, after popular apps and sites (not only phones), each dark and light:
  * **Studio**: flat and sharp, thin lines, small corners (the tools of software teams);
  * **Soft**: big soft cards with shadows, gradient buttons (the dashboards of web services);
  * **Fluent**: smoky glass and square corners (Windows 11);
  * **Aurora**: a slowly moving glow of your colour behind glass cards.
* Animations, light on the phone (transform and opacity only; off with the system's «reduce motion»):
  * a soft light runs along the bar of a print going on;
  * the AI badge's dot breathes while the monitor watches;
  * the menu's lines come in one after the other;
  * a switch's knob lands with a small bounce.

## 1.108.0

**Dark, light or as the device.** Settings → Appearance → **Theme**: *Dark* (the usual), *Light*, or *As the device*,
which follows the phone's or computer's dark mode, also when it changes by itself in the evening. Kept on this device.

* The light page: white cards over a pale grey, dark text, deeper status colours and a deeper accent (white text on it);
  the top bar, the side menu, the windows and the browser's bar follow.
* Every look (One UI, Liquid Glass, Material 3 Expressive, HyperOS 4) has its light version.
* The code editor, the G-code viewer, the AI's code blocks and the camera stay dark.
* The bed mesh's lines and figures take the page's colour.

## 1.107.1

**Visual fixes.**

* Control → Console: the list of matching commands (Tab) no longer squeezes its lines into each other when a command's
  help takes two lines; the same rule now holds for every list that scrolls inside a window.
* Files: on a phone the names of the files wrap after `_`, `.` and `-` instead of in the middle of a word.

## 1.107.0

**The local model learns from each printer** (the fifth step of the new AI monitor), optional and off at first.

* Settings → AI monitor → Local model → **Learn from this printer's prints**: the answers to «How did the print go?»
  (the pictures before the moment of the failure as fine, those from a minute after it as failed) and the labelled
  recordings train a small personal layer on the base model's description of each picture — on the Raspberry, a few
  seconds after each answer (the first time, with many recordings, a minute or two). Its rating is blended with the base model's, more as the examples grow (from 5 failed and
  20 fine pictures).
* What it learned is shown (how many examples, how often it was right on those kept aside); **Learn now** trains it at once.
* **Export the examples** / **Import examples**: the small pictures and their labels in one zip, to carry what one printer
  learned to another; the imported ones can be removed. Nothing is ever sent elsewhere.
* A new base model: the descriptions are computed again from the pictures kept, by themselves.
* `POST /api/local_model/personal`, `GET /api/local_model/personal/export`, `POST /api/local_model/personal/import`;
  `GET /api/local_model` has `personal`.

## 1.106.0

**The local model in the monitor** (the fourth step of the new AI monitor): the motion detection, the local model and the
online AI work together.

* When a local model is installed (KlippEye's own in `models/base/`, or yours in the data folder's `model/`), it rates
  every alarm of the motion detection and also looks by itself every 15 seconds:
  * an alarm of the motion detection goes to the online AI only if the local model has at least a doubt (35%), with its
    rating in the AI's question; the others are kept from it (fewer calls, fewer false alarms);
  * two «sure» looks in a row (80%) ask the online AI even without any alarm of the motion detection — the failures the
    motion detection misses; three «in doubt» in a row ask it too;
  * optional: when no online AI can answer (no key, the limits used up), three sure looks propose a pause by the local
    model alone.
* Settings → AI monitor → **Local model**: which model is in use, its last look and what it did, its switches;
  its thresholds in Monitor thresholds → Local model. Without a model nothing changes.
* The recordings keep the local model's rating of each picture, to measure it afterwards.
* `GET /api/local_model` (and `POST {"reload": true}` after copying a model).

## 1.105.0

**The local model's tools** (the third step of the new AI monitor): what is needed to make, on a computer or on Google
Colab, the small model that will judge the pictures on the Raspberry itself, and to measure it on your own prints first.

* `ml/download.py` + `ml/sources.json`: downloads every listed public dataset of Roboflow Universe (about twenty) with
  a free key, and writes their licences in `ml/data/CREDITS.md`. `ml/KlippEye_local_model.ipynb`: the whole chain on
  Google Colab, cell by cell.
* `ml/datasets.py`: lists the training pictures from public datasets in YOLO format or class folders (the classes read
  by their names: failures, normal prints, quality defects left out) (a failure's box is also cut out),
  folders sorted by hand, and KlippEye's own data (labelled recordings, answers to «How did the print go?»), keeping the
  pictures of one print together when some are set aside for measuring.
* `ml/train.py`: MobileNetV3-Small from its ImageNet weights, a score (failed / fine) and the embedding for each printer's
  personal layer; exported to ONNX, checked against OpenCV, with the threshold that keeps 9 alarms out of 10 right.
* `ml/evaluate.py`: on the labelled prints, false alarms per hour and failures caught (and how late) for several thresholds.
* `backend/local_model.py`: runs the model with OpenCV's DNN module (nothing new to install on the Raspberry).
* Guides: `ml/LEGGIMI.md`, `ml/README.md`. Tests: `ml/tests/test_tools.py` (in `tests/run_all.sh`) and a new CI job that
  runs the whole chain on synthetic pictures.

## 1.104.0

**Backup AI services for the monitor, a second opinion, and how to get a free key.**

* Settings → AI monitor → The AI service → **Backup services** (up to three): when the monitor's service cannot answer
  (its limit of the day used up, down, a key refused), the same alarm is asked of the next one, in order. A service whose
  limit is used up is left alone until the time it gave; the others go on answering.
* **Second opinion from another service** (on when there is a backup): before a pause or a cancel, the second look is
  asked of a different service, so two different AIs must agree to stop a print.
* The alarm says which service answered (and whether it was a backup); when none could, the alarm lists what each said.
* Under Groq, Google Gemini, OpenRouter and Mistral: **How to get a free key**, step by step, with what their free plan
  means (limits, what may be used to train their models).

## 1.103.0

**«How did the print go?»** (the first step of the new AI monitor: OpenCV, a local model and the online AI working
together).

* When a print ends (finished, cancelled or stopped by an error), a card at the top of the home page asks how it went:
  **Went fine**, or **There was a problem**: then a choice of problems, each a tile with a small drawing, in two groups,
  *the print failed* (spaghetti, part detached, layer shift, blob on the nozzle, clog, warping) and *defects of quality*
  (stringing, under- and over-extrusion, elephant foot, ringing, drooping overhangs, supports, rough surface, something
  else), and, with a slider over the print's pictures, from when it can be seen.
  **Skip** passes this print; **Don't ask again** switches the question off (Settings → Recordings → «Ask how each print
  went» switches it back on).
* The answer judges the print's alarms not judged yet: a print that went fine makes them false alarms; a failed one with
  its moment makes the alarms from then on real problems. The recording of the same print, if any, gets the same label.
* Every print keeps a few small pictures of its own (one a minute at most, 48 at most, in `klippeye/reviews/`), also with
  the recordings off: with the answers, they are the examples the local model will learn from. A print shorter than two
  minutes is not asked about, nor one ended more than two days ago.
* Backend: `backend/print_review.py`, `GET /api/print/review`, `GET /api/print/review/<id>/<n>.jpg`,
  `POST /api/print/review/<id>`; the setting `print_review`.

## 1.102.0

**The AI monitor stops less often by mistake** (from the alarms judged on a real printer: 5 wrong stops out of 6, all at
95% confidence, so no minimum confidence could tell them apart).

* **A second look before a stop**: when the AI proposes to pause or cancel, KlippEye takes a new picture 40 seconds later
  and asks again. The stop holds only if the AI sees a problem that time too: a real failure stays (spaghetti grows, a
  part stays off the bed), a reflection, a shadow or the head passing over do not. The notifications and the automatic
  pause wait for the second look; if the AI service cannot answer it, the first verdict stands, so a real failure is
  never let go for that. The alarm keeps both answers.
* **«Empty bed» on a flat print**: below 2 mm of height (a first layer, a calibration print, a flat part) the camera can
  hardly see the print, and the AI took it for an empty bed. Below that height «empty bed» alone no longer stops the
  print; the other defects still do.
* **The start of the print**: with the slicer's progress (M73) the monitor waits for its 2%, not for 1% of the file:
  on short prints the start G-code (heating, mesh, purge) is more than that, and the monitor used to start while the
  head was still moving over the empty bed.
* **The AI service's daily limit**: when the service says its limit is used up (Groq's free plan: about 40 analyses a
  day), KlippEye leaves it alone until the time it gives, instead of asking at every alarm: one print had filled the
  alarm list with 17 «AI error 429», pushing the judged alarms out of it.
## 1.101.1

**Finishing touches to the visual pass.**

* Editor's ⋯ menu: every row has its icon (fold, unfold, go to the section). Comment and Uncomment first give up
  their icons, then their words, always both the same way.
* Connected devices: rows with the same padding as the other lists, the address to copy in a box of its own.
* Input shaper: the «in use» tag stays a whole pill under the name.
* Uncomment no longer squeezes its icon to a dot.

## 1.101.0

**A visual pass over the whole dashboard, from 320 px phones to the computer.**

* Editor: Earlier versions, the configuration reference, folding and the list of sections are now together in one ⋯
  menu, so Comment and Uncomment keep their room; on the narrowest phones (or a long language) they become icons.
  The file name stands centred beside ✕.
* Phones of 320 px: the name in the top bar stays whole, the big temperatures, the fan readings, the temperature table
  (the power column steps aside), the movement pad, the print card's figures, the bed-mesh profiles, the input shaper
  (its table uses the card's whole width with every word whole; only on 320 px it may scroll sideways), the files in two columns, the config search on its own line,
  the MCU versions and the tab bar's names all stay inside the screen.
* Adjustments: on a narrow card a setting's name goes above its buttons; every row's buttons stand in the same column.
* Long languages: Motors off and Calibrate each take their own line when they do not fit side by side; a long word of a
  field name is split at a syllable; a long settings page name goes on two lines.
* Computer: a card that is not shown leaves no extra gap in the side column.
* Notifications: each placeholder stays whole on its line. Home Assistant / MQTT: the topics as a tidy list.
* Extruder: a single macro button takes the whole width.
* Home Assistant / MQTT: switching it off right after a reconnection could leave some entities in Home Assistant
  (the removal ran while the entities were being published again); now the removal waits for that round.

## 1.100.1

**Code review, first pass.**

* The logs (System logs, their AI analysis) are read from their end: a klippy.log of hundreds of MB, on a printer that
  runs for weeks, is no longer loaded whole into the Raspberry's memory to keep its last lines.
* `/api/gcode` reads the command in one clear order ({script}, {gcode}, plain text, ?script=) and refuses an empty one.

## 1.100.0

**Home Assistant and MQTT.**

* Settings › Home Assistant / MQTT: the KlippEye service publishes the printer on an MQTT broker (the Mosquitto add-on of
  Home Assistant, or any other), with nothing to install on the Raspberry. With Home Assistant's discovery the printer
  appears there by itself: state, progress, time left and end time, file, layer, temperatures, the AI monitor and its
  alarm, Pause and Resume buttons, and the lights of Printer functions (switched as the dashboard switches them).
  Cancel print only when allowed. The entities are named in the language of the notifications.
* Plain topics for Node-RED, openHAB, ioBroker and the others: everything in one JSON, each value on its own topic,
  `pause` / `resume` / `cancel` on the command topic, `ON` / `OFF` for each light.
* «Test the connection» says whether the broker answers and the user and password are right; the password stays on the
  Raspberry and is never shown again. KlippEye leaves «offline» as its last will, and connects again by itself.

## 1.99.0

**Ukrainian.**

* The dashboard, the login page, the notifications and the AI monitor's texts are now also in Ukrainian (Settings →
  Language → Українська, or «Automatic» on a Ukrainian device).
* Tests: the history page's test no longer fails when it starts just before midnight (Rome time).

## 1.98.0

**Russian.**

* The dashboard, the login page, the notifications and the AI monitor's texts are now also in Russian (Settings →
  Language → Русский, or «Automatic» on a Russian device).
* Print history: a long state badge wraps in a narrow card instead of leaving it.

## 1.97.0

**Simplified Chinese.**

* The dashboard, the login page, the notifications and the AI monitor's texts are now also in Simplified Chinese
  (Settings → Language → 简体中文, or «Automatic» on a Chinese device).

## 1.96.0

**Polish.**

* The dashboard, the login page, the notifications and the AI monitor's texts are now also in Polish (Settings →
  Language → Polski, or «Automatic» on a Polish device).
* Bed mesh card: the «Probed / Interpolated» switch shrinks and wraps its words in a narrow card instead of leaving it.

## 1.95.0

**Portuguese (Brazil).**

* The dashboard, the login page, the notifications and the AI monitor's texts are now also in Brazilian Portuguese
  (Settings → Language → Português (Brasil), or «Automatic» on a Portuguese device).

## 1.94.0

**KlippEye at the Raspberry's own address, without a port.**

* KlippEye now opens at http://<raspberry>, the address with no port (port 80 of the Raspberry's web server, nginx),
  also from a slicer's printer page. The page that was there moves to the next free port (81, or the next one) and
  keeps working; a copy of its configuration is kept, and nginx checks everything before using it.
* New installations do it by themselves; on an existing one: Settings › Access › Address › «Open KlippEye at …», or
  `klippeye web main` on the Raspberry. «Give the address back to the previous page» (or `klippeye web restore`)
  undoes it. `install.sh --no-web` leaves the address as it is.
* With HTTPS on, nginx serves it at https://<raspberry>, also without a port.
* Through the address without a port, Moonraker's WebSocket and the uploads of files go straight to Moonraker; slicers
  that send to "OctoPrint" (OrcaSlicer, PrusaSlicer...) keep working, also at port 8085.
* Port 8085 keeps working, for the services on the Raspberry and the Android app before 1.7.0.
* **Android app 1.7.0**: it looks for KlippEye at the address without a port first (and only uses it when KlippEye answers
  there), then at port 8085. With HTTPS on, the dashboard gives the app the certificate's fingerprint: the app then opens
  the dashboard with https and accepts that certificate only, also for downloaded files and its own updates. The other
  printers without a written port are looked for the same way.

## 1.93.0

**HTTPS.**

* Settings › Access › HTTPS: an encrypted entrance next to the usual one, at https://<raspberry>:8443 (the port can be
  changed). Off until you switch it on; on and off at once, no restart.
* Its certificate is made on the Raspberry for its names and addresses (no authority signs it): the first time the
  browser warns that it does not know it. The page shows the certificate's fingerprint to compare with the browser's,
  and makes a new one after the Raspberry gets a new address.
* Behind it the service knows who is on the other side and that the connection was encrypted (the login cookie is then
  sent only encrypted); the camera comes through the service on the encrypted page. The Android app keeps using the
  usual address.

## 1.92.0

**One live connection to Moonraker.**

* The KlippEye service now keeps one live connection (WebSocket) to Moonraker: Moonraker sends it the changes of the
  printer's state as they happen (temperatures, fans, position, the print...). The questions of the dashboards (on
  every phone and computer that has one open) and of the AI monitor are answered from that copy, at once, without
  asking Moonraker and Klipper each time: less work for the Raspberry, quicker answers.
* When the connection is not there (Moonraker restarting, Klipper not ready yet) everything asks Moonraker directly, as
  before, and the connection comes back by itself. `KLIPPEYE_LIVE=0` in the service's environment switches it off.
* `/api/health` says whether it is live and how many questions it answered.

## 1.91.0

**AFC in the multi-material card.**

* Printers with AFC (Box Turtle, Night Owl and the other AFC units) now have the multi-material card too: the lane in
  the toolhead with its tool and material, each unit with its lanes (colour, tool, material, weight, state), AFC's
  message, and its commands: load a lane into the toolhead, eject a lane, unload the toolhead, clear an error (and
  resume the print after one). The commands wait while the unit is busy or printing.

## 1.90.0

**Input shaper: Klipper's own fitting, two recommendations, the measured damping.**

* KlippEye now runs Klipper's own input shaper fitting (ported from Klipper, identical results) on the file
  SHAPER_CALIBRATE leaves: when Klipper's messages about a measurement are gone from the console and klippy.log, the
  card still shows exactly what SHAPER_CALIBRATE found.
* «Recommended filters», as in Klipper's result: «for low vibrations» is the shaper Klipper recommends; «for
  performance» is the one allowing the highest acceleration among those leaving less than 5 % of the vibrations, when
  it allows more than Klipper's choice. When they are the same, a single «best shaper». The chart draws what both
  leave.
* The analysis now follows the usual input shaper chart: the shapers are fitted with the damping ratio measured on
  the curve, the printer's square corner velocity and the allowed smoothing (shown above the chart). A switch shows
  SHAPER_CALIBRATE's own result instead (its damping ratio, 0.1: the same as the console).
* The chart draws X+Y+Z, X, Y and Z, what the two recommended shapers leave, each shaper's response, the relax region
  (below 5 % of the highest vibration: noise, not a peak) and the warning region (5 to 12 %: small peaks); the peaks
  above it, the ones that show in prints, have their number in red. The scale is fixed on the highest value.
* The damping ratio is measured as it should be (half-power bandwidth at peak/√2); the peaks are found on a smoothed
  curve, and those above the warning band are marked in red; the bands are drawn as filled areas.
* The shapers' impulses now follow current Klipper (EI, 2HUMP_EI and 3HUMP_EI depend on the damping ratio), so
  smoothing and max acceleration match its figures.

## 1.89.1

**Input shaper: Klipper's own figures.**

* The card now shows what SHAPER_CALIBRATE said in the console for that measurement: each shaper's vibrations,
  smoothing and suggested max acceleration, and the shaper Klipper recommends (read from Moonraker, or from
  klippy.log after a Moonraker restart). When those messages are gone, the figures are worked out from the file the
  way Klipper does, and the card says so.
* The «low vibrations» recommendation is gone: the card shows Klipper's choice, already selected for «Save», and what
  the chosen shaper leaves.
* With a high peak the chart could spill over the rest of the card: its scale now always reaches above the highest
  value and the lines stay inside it.
* The shaper table fits narrow phones.

## 1.89.0

**Input shaper: a clearer chart, the shapers' figures, saving in printer.cfg.**

* The chart is now an axis frequency profile: the vibrations of all axes together and of X, Y and Z, what is left with
  the shaper recommended for performance and the one for low vibrations, the two bands (below the green line the
  vibrations do not matter, above the orange one they show in the prints), the peaks numbered, each shaper's response
  dotted. The title gives the resonance frequency (ω0) and the estimated damping ratio (ζ); the legend hides and shows
  each line.
* Under it: the recommended shapers (performance, low vibrations), the estimated damping ratio and a table with each
  shaper's frequency, vibrations, smoothing and highest acceleration, computed as Klipper does with the printer's
  square corner velocity and damping ratio.
* «Measure X» and «Measure Y» each have a menu with the measurement's settings (start and end frequency, sweep speed,
  acceleration per Hz, max smoothing): empty ones use Klipper's (shown in grey). They are kept on the device.
* «Try» is now «Save»: the chosen shaper and its frequency are written in [input_shaper] where Klipper reads it
  (Klipper's own block at the end of printer.cfg, printer.cfg itself or the included file that has the section; a new
  section otherwise), keeping a copy of the file first, and applied at once.
* The snowflake icon of the temperature card is now symmetric.

## 1.88.0

**French.**

* The dashboard, the login page, the notifications and the AI monitor's texts are now also in French (Settings →
  Language → Français, or «Automatic» on a French device).

## 1.87.0

**German.**

* The dashboard, the login page, the notifications and the AI monitor's texts are now also in German (Settings →
  Language → Deutsch, or «Automatic» on a German device).

## 1.86.0

**Spanish.**

* The dashboard, the login page, the notifications and the AI monitor's texts are now also in Spanish: Settings →
  Language (or «Automatic», which follows the device). The notifications' language is chosen in Notifications.
* `frontend/tools/i18n.py check` now also checks every other language file: the same texts as Italian, with the same
  {placeholders}.

## 1.85.1

**Accessibility checks.**

* A new automatic test visits every page, the pages of the menu and the print's confirmation, on a phone and on a
  computer, and checks that every button, link, switch and field has a name a screen reader can say, every picture an
  alternative text, and no id is used twice.
* The file previews and the print's picture are now marked as decoration (the file name is next to them); the image
  viewer names the picture with its file.

## 1.85.0

**Multi-material units (Happy Hare).**

* On printers with Happy Hare, a «Multi-material unit» card on the Home page (in the side column on the computer): the
  tool, gate and filament in use, what the unit is doing, and the gates with their colour, material, state and tools.
* Tap a gate to change to its tool or select it; «Load», «Unload», «Home the unit», «Recover». The commands wait
  while the unit is busy or a print runs (except «Recover»). Without a unit the card does not show.

## 1.84.0

**`klippeye benchmark`.**

* On the Raspberry, `klippeye benchmark [--seconds 30] [--json]` measures how much processor and memory KlippEye,
  Moonraker, Klipper and the camera use, the Raspberry's load, free memory, temperature and power or heat warnings,
  and how long the AI monitor takes to check one picture here; then it says in plain words whether there is room.
  It only reads.

## 1.83.0

**Checks before a print.**

* The «Confirm print» dialog reads the file and the printer and says what would spoil the print: taller than the
  printer's Z, sliced for another nozzle, layers too thick for the nozzle, temperatures over the printer's limits,
  Klipper not ready, settings still waiting for SAVE_CONFIG. Nothing is blocked; when all is well one line says so.

## 1.82.0

**A password for guests: look, don't touch.**

* With the password on, Settings → Access → «Guest password» sets a second password. Who logs in with it sees the
  printer, the camera, the files to print and the history; the top bar shows «Guest» instead of the power, save and
  emergency stop buttons.
* The KlippEye service refuses a guest's commands (anything but reading) and the configuration files, the logs and the
  settings (they hold keys); the page answers a guest's command itself and says why.
* Changing or removing the guest password logs the guests out; removing the main password removes it too.
* On the Raspberry: `klippeye password guest-set` / `klippeye password guest-remove`.

## 1.81.0

**Earlier versions of the config files.**

* Before the editor writes a file of the config folder over, the KlippEye service keeps the text it had (the last 30
  of each file, in its data folder).
* The clock button of the editor lists them, and for printer.cfg also Klipper's own backups (printer-….cfg, written by
  SAVE_CONFIG): choose one to see what putting it back changes (the lines that go and those that come back), then «Put
  back in the editor». Nothing is written until Save; Undo takes it back.

## 1.80.0

**Input shaper graphs.**

* A new «Input shaper» card (Control on the phone, Calibration on the computer) draws what Klipper's resonance
  measurement found: how much the axis shakes at each frequency, with its peak, and how much each shaper lets through,
  with the vibrations it leaves. The shaper printer.cfg sets is marked, and the one that leaves the fewest vibrations.
* «Measure X» / «Measure Y» run SHAPER_CALIBRATE (after homing, if needed, and a confirmation); «Try …» sets the shaper
  chosen in the list until Klipper restarts.
* The service reads the files Klipper leaves in /tmp (`GET /api/shaper/files`, `GET /api/shaper/data?name=`).

## 1.79.0

**Read a file again.**

* «Read the file again» in a file's menu: Moonraker reads its times, filament and pictures again, for a file it read
  wrong or before the slicer's settings changed.

## 1.78.0

**Hidden lines in the console.**

* Console options → «Hidden lines»: lines with a piece of text you choose are not shown (any case), or, between
  slashes, those matching a regular expression (`/^Homed/`). Klipper still gets and keeps them.
* Kept on this device; the menu says how many rules there are, and each one can be removed.

## 1.77.0

**The spool, before a print starts.**

* With Spoolman, the print's confirmation shows the spool in use (colour, name, material, what is left) and «Change»
  to pick another one before starting.
* It warns when the file needs more filament than is left on the spool, or was sliced for another material.

## 1.76.0

**Devices connected to the Raspberry.**

* A **Connected devices** card on the System page: the serial ports (the boards, with the address to write after
  `serial:` in printer.cfg), the USB devices, the cameras and, on a CAN network, the boards not set up yet (their
  `canbus_uuid`). A tap on an address copies it.
* Read when the page opens and with «Look again» (Moonraker 0.8 or newer).

## 1.75.0

**Temperature chart: the clock slides with the lines; a button to turn every heater off.**

* The times under the chart now sit on round minutes (every 1, 2 or 4 minutes, as many as fit) and slide to the left
  with the lines, each with a faint vertical line; before they stood still under a moving chart.
* A snowflake next to the minutes turns every heater off at once (Klipper's `TURN_OFF_HEATERS`). While a print runs it
  asks first.

## 1.74.0

**A production web server for the KlippEye service.**

* The service now runs on **waitress** (`python3-waitress`), a web server made to run for months: a fixed number of
  threads, requests that time out. Until now it used Flask's own server, meant for development.
* The installer adds `python3-waitress` with the other packages. An installation from before 1.74 keeps working on
  Flask's server: Settings → Software says so and gives the command
  (`sudo apt install -y python3-waitress && klippeye restart`); `klippeye diagnose` shows which server runs.

## 1.73.0

**Maintenance reminders.**

* Files → History has a **Maintenance** card: «Add» a reminder (what to do, every N printing hours, N metres of
  filament and/or N days, a note). It counts from Moonraker's own totals (every print ever) since the last time it was
  done: a bar, «Soon» from 90 %, «To do» when it is time.
* «Done» starts it again from now; a tap on the reminder changes or removes it.
* When one is due, a message says so once a day on each device.
* Kept in Moonraker's database: every phone and computer sees the same reminders. If Moonraker's totals are reset,
  a reminder counts what was printed since then.

## 1.72.1

**No other interface named.**

* The texts, the comments of the code, the scripts' messages, the app's first-start help, this changelog and the
  security notes no longer name other web interfaces: the update steps point to Moonraker's update manager or to the
  `klippeye` commands. The ready-made Raspberry images are still named where the installation needs them, and file
  names that exist on the printer (log files, configuration files) are kept as they are.

## 1.72.0

**The console's input field: history and completion.**

* ↑ / ↓ go through the commands sent before (the last 100, kept on this device); going past the newest brings back
  the line being typed.
* Tab completes a command's name from Klipper's commands and macros: one match is written out; several are listed
  above the field with what each one does, and a tap writes one. Escape closes the list.
* On a touch screen, with no Tab key, the matching commands are listed while the name is typed (from its second
  letter).
* The same on the console card, over the whole screen and in the computer's console bar.

## 1.71.0

**Windows opened by macros.**

* Klipper's macros can open a window with a title, some text and buttons (`RESPOND TYPE=command
  MSG="action:prompt_begin …"`, `prompt_text`, `prompt_button`, `prompt_button_group_start/_end`,
  `prompt_footer_button`, `prompt_show`, `prompt_end`): many macro packs ask this way
  (Happy Hare, RatOS, Klippain, filament changes). KlippEye now shows them.
* A button sends its command (`name|command|colour`; colours primary, secondary, info, warning, error); the window
  stays until the macro ends it. ✕ closes it and sends `action:prompt_end`.
* The window opens on every phone and computer, on any page, and again after a reload.
* The `// action:prompt_…` lines are no longer shown in the console.

## 1.70.2

**Visual review** (phone 360 and 390 px, tablet, computers 1024 to 1920 px; idle and printing; every page).

* Temperature chart: on a narrow chart every other clock time, so they no longer run into each other.
* Files: «File di stampa» on one line on a small phone.
* Computer, file panel: the buttons go on two lines instead of squeezing into each other («Dettagli» and «Programma»
  touched).
* Computer, print card: the six figures fit at 1280 px («6,3 mm³/s» was cut to «6,3 mm…»).
* Computer, camera: with more than one camera the name is no longer shown twice (the label and the camera menu).
* Tablet and phone, print card: a gap between «Vedi i layer» and Pausa / Annulla stampa.
* A new automatic check (tests/ui/visual_test.py) keeps these fixed, and looks at every page at six sizes, idle and
  printing, for anything off the screen or scrolling sideways.

## 1.70.1

**The AI monitor looks at the parts too.**

* Until now, with the whole bed watched (camera calibrated), the parts were a blind spot: their outline, from the bed up
  to the nozzle, was left out entirely, so a string or spaghetti that stayed in front of a part was never seen.
* Now only the layers being printed (the last 2 mm and the slice above, with its margin) are left out. What is already
  printed does not change any more, and the background is the picture of the last minute: a change that stays there
  counts. Its edges are left out (a bed that moves in Z shifts them), and it is measured against the part's own area,
  not the whole bed (halved), so a thin string is not lost in a big picture.
* While the toolhead hides the part a check says nothing about it (it no longer lowers an alarm that is building up).
* A switch, on by default: Settings → Camera calibration → «Watch the parts too, below the layer being printed».
* Very thin strings far from the camera may still not be seen: they are thinner than what the camera resolves.

## 1.70.0

**Scheduled prints.**

* «Schedule the print» in a file's menu (and «Schedule» on the computer's file panel): a day and a time, or a quick
  choice (in an hour, tonight at 23:00, tomorrow at 07:00). The KlippEye service starts the print at that time by
  itself: no browser or app needs to stay open.
* At its time the printer must be ready and free. If another print is on, or Klipper is off for more than ten minutes,
  the print is not started later on its own (the bed may not be clear): it is marked «Not started», with the reason.
* The «Scheduled prints» card on the Files page lists them: when, in how long, started or not and why; cancel one, or
  take a finished one off the list (they go by themselves after a day). On a computer the idle print card says which
  one starts next.
* Kept in schedule.json, in KlippEye's data folder.

## 1.69.2

**A calibration waiting for an answer stays on screen.**

* Bed screws adjust and every paper test (Klipper's manual probe: axis twist, PROBE_CALIBRATE, Z_ENDSTOP_CALIBRATE, a
  macro…): while Klipper waits for «Accept» or «Abort», its sheet opens by itself on every phone and computer, on any
  page, and again after a reload. Before, a reload closed it and it did not come back.
* While Klipper waits, a tap beside the sheet or the back button no longer closes it (the ✕ still aborts). An answer
  given on one device moves the others on; when it ends, it closes everywhere.
* A paper test started elsewhere (the console, a macro) gets its own sheet: «Nozzle height», with the steps, «Accept»
  and «Abort».

## 1.69.1

**Timelapse settings read from moonraker.conf.**

* The settings card (Files → Timelapse, and Settings → Camera → Timelapse) now shows what moonraker.conf says in its
  [timelapse] section, each time it opens; what the section does not say shows moonraker-timelapse's default. Before, it
  showed what the add-on kept in its own database, which could differ from the file (a change made from another
  interface, say).
* «Save» still writes the section and restarts Moonraker; nothing is sent to the add-on or to Klipper.
* The add-on itself, when Moonraker or Klipper starts, sends its settings to its macros with a long
  `_SET_TIMELAPSE_SETUP …` line: the console no longer shows it (Klipper still gets it).
* The repeated last frame defaults to 5, as in the add-on (it said 0). «Wait for the photo» is gone: the add-on has no
  such setting, and writing it in moonraker.conf would only give a warning.

## 1.69.0

**Console with formatted messages, the temperature chart with the clock, the light menus fixed.**

* Console: the HTML that Klipper and many macros write in their messages is drawn: `<a class="command">
  SAVE_CONFIG</a>` is a link that puts the command in the input field, bold, italics, line breaks and colours are shown.
  Only a short list of harmless tags gets through (no scripts, images or frames). The «!! » and «// » in front of
  Klipper's answers are no longer printed (the colour says it).
* Console: with «Autoscroll» off the text no longer slides by. The console keeps the last 200 lines: each new line pushed
  the oldest one out and the whole text moved up, as if it scrolled by itself. Now the line at the top of the view stays
  where it is.
* Temperature chart: time runs left to right again (now on the right), and the marks under it are clock times (14:05,
  14:07…) instead of «-2′, -4′».
* Lights: on a computer the panel of the lights (the arrow next to the light button) opened squeezed inside the camera's
  corner; it opens in the middle of the page again.
* Printer functions: the macro of a light (and of park, load…) is chosen from Klipper's macros with the arrow next to the
  field. Before, the browser's suggestion list showed only the name already written, and the app never showed it.
* README: the license line no longer names other interfaces.

## 1.68.1

**The guide follows the reviewed texts** (docs/GUIDE.md, docs/GUIDA.md). Nothing changes in the dashboard.

* The same words as the dashboard (in Italian: telecamera, Annulla stampa, Rimuovi, probe, inattiva, versione…; in both:
  the KlippEye service instead of «the backend») and no other web interface named: the commands to run on the Raspberry
  instead of another interface's update manager, «Import from the printer». The ready-made Raspberry images are still
  named where the installation needs them.
* Brought up to date: the settings menu as it is now, the cards dragged per kind of device, the timelapse with «Advanced»
  and «Save and restart Moonraker», more printers, the daily look for new versions.

## 1.68.0

**Texts reviewed** (roadmap phase 7): about 300 texts changed after a comparison with the Italian translations of the other
3D printing programs, and the choices made together on 9 November.

* Italian: **«Annulla stampa»** instead of «Cancella stampa» (in Italian «cancellare» means to delete); **«Elimina»** for
  files, **«Rimuovi»** for lists (no more «Cancella» / «Togli»); **«telecamera»** instead of «camera» (the print
  chamber stays «camera di stampa»); **«inattiva»** for an idle printer; **probe** and **endstop**, **target**,
  **homing**, **pressure advance** and the other Klipper names as they are; «piatto», «retrazione», «spurgo»,
  «predefinito», «versione», «pulsante», «chiave».
* Waiting messages without «I» («Lettura…», «In attesa…»), errors as «Impossibile…», the notifications with «tu»
  («Filamento esaurito: cambia la bobina!»), a space before the units and the decimal comma.
* The texts no longer name other programs: «Import from the printer» for the webcams Moonraker keeps, and when the
  KlippEye service does not answer the page gives the command to run on the Raspberry.
* What was still in English in Italian: the extruder's Retract / Extrude / Wipe / Load / Unload, the fans' names, the
  restart buttons, the emergency stop, the rollback of the updates, the monitor's figures.
* In the «Annulla stampa» dialog the buttons are «Annulla stampa» and «Indietro».
* In Italian the AI is «IA» in the texts; the badge at the top always says «AI».
* Fixed: SAVE_CONFIG restarts Klipper, not the firmware of the boards; two texts said the timelapse would use the
  snapshot «later»; a technical leftover in the macros' loading message; two missing accents.

## 1.67.0

**New versions looked for by itself; a larger camera on a computer; «Print again»; pictures over the whole screen.**

* **New versions**: once a day (never while printing) the dashboard asks Moonraker to look for new versions. When KlippEye,
  Klipper, Moonraker or the others have one, a number appears on the «System» tab and a message names them (once for
  each new set; the operating system's packages are left out). Nothing is installed by itself. Settings → Updates →
  «Look for new versions by itself» switches it off for that browser or phone.
* **Computer, Device page**: the camera is as large as its shape needs at the column's full width (it stretched to the
  column's height and the picture sat small between two grey bands), keeping the print card in view under it; the print
  card is compact (the six figures on one line, the buttons on one line, «More details» among them).
* **Computer**: the «AI monitoring» strip under the camera is gone (the AI badge at the top says the same and opens the
  same panel). When nothing prints, the card of the last print has **«Print again»** (it asks first, like a file).
* **A picture of the AI monitor** (an alarm, a recording) opens over the whole screen, black and edge to edge, as the
  camera's full screen; turned on an upright phone; a tap shows or hides the buttons.
* **Lights**: when on, the whole button lights up, its arrow too.
* **Bed mesh**: the pill with the profile's name shows the whole name (it was cut to «def»).
* **Temperature chart**: «now» is on the left and the lines flow to the right.
* **Timelapse settings**: more of them, the specific ones behind **«Advanced»** (parking: custom position, Z lift,
  speeds, retraction, wait; the photo: snapshot address, camera delay, wait for the photo, console messages; the
  video: frame rate limits, rotation, mirroring, pixel format, date in the name, ffmpeg options). Changes are no longer
  sent one by one: **«Save and restart Moonraker»** writes them in moonraker.conf, section [timelapse] (what differs
  from moonraker-timelapse's defaults, or is already there; the rest of the file untouched), then restarts Moonraker to
  read them. Refused while printing; «Undo changes» drops them. The camera choice is saved the same way.

## 1.66.0

**Computer: the history and the timelapse scroll, nothing under the console bar.**

* On a computer the **history** and the **timelapse** grew taller than the window: they went under the console bar (you
  could read them through it) and could not be scrolled. Their columns now keep to the window and scroll by themselves,
  like the other pages.
* The console bar blurs what is behind it.
* Timelapse settings: a line says where they are kept (moonraker-timelapse, which gives them to Klipper at every start;
  timelapse.cfg is its own file and stays as it is).

## 1.65.0

**Settings in full pages (phone) and one panel (computer); the cards' layout dragged, one per kind of device.**

* On a **phone** a page of the settings fills the screen (the side menu is the list of pages).
* On a **computer** the settings are one panel in the middle of the screen: the list on the left (the
  page open marked), the page on the right.
* **Settings → Appearance → Cards**: a small drawing of the page. A card is **dragged by its handle** (finger or mouse)
  to its new place, also into the other column; the arrows do the same, the switch shows or hides it.
* **One layout per kind of device**: phone, tablet and computer each keep their own (the one of this screen is chosen
  at first and marked «this one»). On a computer the Device page has a main and a side column (the print card always
  stays), the Calibration page a left and a right one; any card can go in either. The order of 1.50 becomes the
  phone's and the tablet's.

## 1.64.0

**Computer: every card scrolls, the console no longer hides the page.**

* The **3D bed mesh** took the mouse wheel for its zoom, so with the pointer on it the page could not be scrolled: the
  wheel now scrolls; **Ctrl (⌘) + wheel** or a trackpad's pinch zoom the view.
* The **whole console** (the arrow on the console bar) takes its place above the bar, and the page's columns get
  shorter, instead of floating over the cards and hiding them.

## 1.63.0

**Fixes: the printers' menu, the G-code viewer, the timelapse check, «Save and restart»** (requests of 4 November, evening).

* **Menus** (the printers' one in the top bar, and every other) are drawn over the whole page: a tap outside closes
  them (in the top bar it did not), and their glass blurs the page under them again (it looked almost transparent).
* **G-code viewer**: files in vase mode (or with a spiral lift) were cut into thousands of "layers", one per move. The
  layers are now the slicer's own (;LAYER_CHANGE of OrcaSlicer, PrusaSlicer, SuperSlicer; ;LAYER: of Cura); without
  them a layer needs the height to rise by more than 0.02 mm.
* **Timelapse → «Installed: check again»** restarts Moonraker first (it finds moonraker-timelapse only when it starts;
  a print going on does not stop), then asks again: found, the page opens on the timelapse; not found, it says to check
  the [timelapse] section.
* **«Save and restart»** in the editor restarts what the file belongs to: moonraker.conf → Moonraker, crowsnest.conf →
  crowsnest, KlipperScreen.conf, sonar.conf, the Telegram bot, Obico…; the other .cfg files → Klipper (FIRMWARE_RESTART,
  or SAVE_CONFIG when Klipper holds changes to save; asked first while a print runs). Files of nothing get no button.
* The side menu's **«Go to»** group is gone (history and timelapse are on the Files page).

## 1.62.0

**More printers in the Android app (app 1.6.0)** (requests of 4 November, second part).

* In the KlippEye app, choosing another printer (the menu on the name at the top, or the overview) opens it **inside
  the app**, and the app remembers it the next time it opens. If it does not answer, the app says so and goes back to
  the main printer (the one of the app's addresses).
* The **notifications arrive from every printer** opened in the app, not only from the one on the screen: each printer
  gives the app its ntfy topic, and the app listens to all of them (one connection per ntfy server).
* The dashboard of another printer does not change the app's addresses (they stay the main printer's).
* With an older app, another printer opens in the browser and the page says to update the app.

## 1.61.0

**More printers: the list, the switcher in the top bar, the overview** (requests of 4 November, first part).

* **Settings → Your printers**: the other printers with KlippEye on your network, by their address (192.168.1.50,
  voron.local…; the port 8085 is added by itself). «Try» asks the address first and shows the name the printer gives
  itself and its state; the order can be changed. The list is shared by every device of this printer.
* A tap on the **logo and name in the top bar** lists the printers: this one, then the others with their state
  (printing and how far, ready, not reachable, protected by a password…), the **overview** and «Manage the printers».
* The **overview** shows every printer at once: logo, name, state, progress, file and temperatures.
* Choosing another printer opens its KlippEye (in the browser, its address). Arriving there from a printer that is not
  in its list, the page offers to add it, so the lists fill in by themselves. Inside the Android app, the app will keep
  it inside with its next update (the second part).
* The state of the other printers comes through this printer's KlippEye service (`/api/printers/peek`, which asks the
  other one's `/api/printers/self`), and only addresses of the home network (private, ZeroTier / Tailscale) are asked.
* Settings: a save that did not get through (the page woke up and cancelled it, or the network dropped it) is tried
  again by itself instead of staying only on this device.

## 1.60.0

**Side menu: fewer, fuller pages, grouped by what they are about** (requests of 4 November).

* **The printer**: Printer functions, Macros, **Motion and Z-offset** (the Z-offset card's steps are now at the bottom
  of the Motion page).
* **Camera and AI monitor**: Camera (every camera, the timelapse), AI monitor.
* **Notifications and appearance**: Notifications, **Appearance** (now with the printer's name and logo, for every
  device, then the colour, the look, the hints and the cards of this device), Language.
* **Go to**: print history, timelapse.
* **System**: Addresses, Access, Updates.
* 13 lines instead of 15; the old pages (Name and logo, Z-offset) still open from the guided set-up and the help.

## 1.59.0

**Settings → Camera: every camera, one page each; the timelapse settings there too** (requests of 4 November).

* **Camera** lists every camera: the **main camera** (KlippEye's own, the one the AI monitor watches) on its page as
  before, and the **cameras of the printer** that Moonraker keeps, the same ones every interface of the printer shows.
* Each camera of the printer has **its own page**: name, on / off, kind (WebRTC, MJPEG,
  MJPEG adaptive, web page), the video and snapshot addresses, frames a second, mirror, flip and rotation. Every change
  is saved to Moonraker at once (the printer's other interfaces see it too). **Add a camera** makes a new one and opens its page; **Remove**
  deletes it. A camera written in moonraker.conf can only be read there, and says so.
* The camera card shows a camera's rotation too.
* **Camera → Timelapse**: the settings of moonraker-timelapse, with **which camera** takes the photos; without it, how
  to install it. The camera calibration of the AI monitor and «Reload the camera» stay on the Camera page.

## 1.58.0

**One long light button; notifications that are on stay out of the way; editable G-code** (requests of 4 November).

* The light button and its arrow are **one long button**, split 70 / 30: the light on the left, the arrow that opens
  every light on the right (on the camera card, the computer's camera and the full screen).
* **Notifications**: once ntfy is on, the page says so and offers the test; pairing a phone (the app, the QR code) and
  the other choices (new address, own server, turn off) are folded. In the app, a phone already set up when the page
  opens has its steps folded, with the test at hand. With Firebase on, turning ntfy on for other phones is folded too.
* **Editor**: selected text keeps its colours (on some phones it turned black on the dark editor and could not be
  read); the selection is a little stronger.
* **G-code files open editable up to 32 MB** (before: 256 KB, so almost every print opened read-only). A long file is
  copied out of the editor once typing pauses, not at every key; only a file over 32 MB opens read-only.

## 1.57.0

**Folding: the same chevron in the same place; Printer functions as a short list** (requests of 4 November).

* The chevron that folds a card is at the same place on every card: top right, on the title's line, also when the
  card's own buttons go to a second line (Temperatures, bed mesh on a phone).
* **Endstops and probe** is a foldable card like the others (its own fold, with a different arrow, is gone). It is open
  unless it had been left folded.
* Every fold-out section («More details» on the print card, the AI keys, your own ntfy server…) has a chevron at its
  right end that turns when it opens.
* **Settings → Printer functions**: every light, every button (park, wipe, load, unload) and the filament change
  notification is a row with its icon, its name and what it does now in a few words («Automatic · CLEAN_NOZZLE»,
  «Macro · LUCI_ON / LUCI_OFF · round button»); a tap opens its settings under it. A light's move and remove buttons
  are at the bottom of its settings.
* The printer's macros to choose for the filament notification are folded under a line that says which ones are chosen.

## 1.56.0

**Files: a menu button on every file; Timelapse always there** (requests of 4 November).

* Every file tile has a **⋯** button in the corner of its preview: it opens the same menu as the long press (details,
  queue, layers, editor, delete). The long press stays.
* The **Timelapse** part of the Files page (and its line in the side menu) is there also when Moonraker does not have
  moonraker-timelapse: it says what the add-on is and how to install it, step by step, with the commands and the
  configuration lines to copy; once it is installed the videos and settings appear as before.

## 1.55.3

**Narrow phones: nothing out of its card** (roadmap phase 8).

* A card's title bar with more buttons than a narrow phone can hold (the Spool card's *Change spool* and fold, the
  configuration files' *New* and reload…) puts them on a second line instead of pushing them out of the card.
* Timelapse: on the narrowest phones the preview is smaller and the delete button stays inside the row.
* A new test checks every page, with every optional card on, at 320 and 390 px.

## 1.55.2

**Code: leftovers removed** (roadmap phase 8, first pass). Nothing changes on screen.

* Seven definitions nobody uses any more: `escapeHtml` (the old editor's colours), `cameraUrl` (the cameras of 1.48),
  `SETTINGS_PAGES`, `AI_CONFIDENCES`, `LIGHT_MODES`, `AI_VERDICT_MAX_AGE_MS`, `SERVICES_REFRESH_MS`.

## 1.55.1

**Texts: the same words for the same things** (roadmap phase 7, text review).

* Italian: **layer** everywhere (as on the print card and in the slicers), no more "strato" in the recordings, the
  Z-offset steps and the AI monitor's alarms; **IA**, not "AI", in the logs analysis and the monitor's details; the
  dashboard's panels are **card** also in the help texts (no more "scheda", which stays for the browser's tab and the
  printer's boards).

## 1.55.0

**Texts: "the KlippEye service", not "the backend"** (roadmap phase 7, first part of the text review).

* The dashboard no longer talks about "the backend" (a developer's word): the program on the Raspberry is **the KlippEye
  service** everywhere (updates, restart, access, AI monitor, recordings, calibration, notifications, the app), in English
  and Italian; the AI monitor's own descriptions (written by the service) too.
* A leftover developer message of the logs card ("Check the backend: /api/logs/list") now says the logs cannot be read and
  to try again.

## 1.54.0

**The side menu, reorganised** (roadmap phase 6e, fifth and last part).

* A new group **Go to** with the pages that are not on the bottom bar: **Print history** and, when Moonraker has it,
  **Timelapse**: a tap closes the menu and opens the Files page on that part.
* **Phone and network** becomes **This device**: Appearance, Notifications, Language (moved from System: it is per
  device) and Addresses.

## 1.53.0

**Looks** (roadmap phase 6e, fourth part): the same page and palette, dressed after another phone.

* **Settings → Appearance → Look**: **One UI** (the usual glass on the logo's glow), **Liquid Glass** (clearer glass, a
  light edge on top, deeper blur, rounder corners), **Material 3 Expressive** (solid surfaces tinted by the chosen
  colour, no outlines, bolder titles, softer squares for secondary buttons), **HyperOS 4** (black page, flat grey cards).
  Each choice has a small preview; kept on this device; the colour of 1.52 goes with every look.
* Fix: on a phone the camera card's title bar (camera menu, light, full screen, fold) ran out of the card: the camera
  menu keeps only its icon there, and on the narrowest phones the buttons go under the title.

## 1.52.0

**Your colour, and a RatRig logo you can see** (roadmap phase 6e, third part).

* **Settings → Appearance → Colour**: the accent of buttons, switches and highlights — the logo's violet (default),
  blue, teal, green, amber, pink, or **your own** from the colour wheel. A colour too dark or too pale for the dark page
  is made lighter or deeper; the glow of the background follows it. Kept on this device.
* Every hard-coded violet of the stylesheet now follows the chosen colour (`--oui-accent-rgb`).
* The RatRig logo of `logos/` is green: the dark grey one could not be seen on the dark bar.

## 1.51.0

**Hints on or off** (roadmap phase 6e, second part).

* **Settings → Appearance → Show the hints**: the small texts that explain how to use a page (*Tap to change* under the
  heaters, *Tap X/Y/Z to move to a position*, *Long-press a file…*, the temperature chart's and the bed mesh's, the
  computer's console drawer) can be hidden on this device. The notes that say what something does stay.

## 1.50.0

**Cards that fold, and the order of the pages** (roadmap phase 6e, first part).

* Every main card (camera, heaters, temperatures, spool, movement, Z-offset, console, extruder, devices, the macro cards,
  tuning, bed mesh, the computer's fans) has a **chevron** in its title bar that folds it down to the title; it stays so on
  this device.
* **Settings → Appearance** (new): the order of the cards of **Home** and **Control** (arrows) and which of them show
  (a switch), kept on this device; how many cards are folded, with *Open them all*; *Usual order, everything shown*. The
  print card always stays on top.

## 1.49.0

**G-code viewer** (roadmap phase 6d, eighth and last part): a file seen layer by layer from above, in 2D.

* **See the layers** in a file's long-press menu, *Layers* on the computer's file panel, and **See the layers** on the
  print card.
* The file is read in pieces with a progress bar; every move is parsed (absolute / relative moves and extrusion, `G92`,
  arcs `G2` / `G3`), and the slicer's `;TYPE:` comments say what each line is.
* The layer is chosen with the slider, ‹ › or the arrow keys, with its number and height; its lines are coloured by kind
  (outer and inner wall, top / bottom, infill, bridge, support, skirt / brim), the layer under it in grey, the travels on
  request; a tap on a kind in the legend hides it. Pinch or the wheel zooms, a drag moves, a double click resets.
* While that file prints, **Follow the print** shows the layer at the nozzle, what is printed of it and what is still to
  print (faint), and the nozzle itself; moving the slider stops following.

## 1.48.0

**More cameras** (roadmap phase 6d, seventh part).

* Besides the camera of the settings (the one the AI monitor watches), the webcams set up on the printer
  (Moonraker keeps them) that the dashboard can show: with more than one, a **camera menu** on the camera card (and on
  the computer's camera panel) picks which one to watch, and the full screen follows it. Each webcam keeps its own way of
  being shown (WebRTC, MJPEG, MJPEG adaptive, web page) and its flips.
* The same camera twice, and the kinds the dashboard cannot show, are left out. The choice is kept on this device.

## 1.47.0

**Filament spools with Spoolman** (roadmap phase 6d, sixth part), through Moonraker's `[spoolman]`.

* A **Spool** card (Home on the phone, with the fans on the computer), only when Moonraker has the component: the spool in
  use drawn in its colour, with maker, name, material, diameter, place, and what is left (weight, length, a bar and the
  percent).
* **Change spool**: Spoolman's spools, the last used first, with a search; a tap makes one the active spool (Moonraker
  then counts each print's filament on it); **No spool** leaves none in use.
* Spoolman unreachable: the card says to check it is running and the address in `[spoolman]`.

## 1.46.0

**Timelapse** (roadmap phase 6d, fifth part), with moonraker-timelapse.

* The Files page gets a third part, **Timelapse**, when Moonraker has the component:
  * the **videos**, newest first, with their preview picture, date and size: a tap plays one full screen, *Download*,
    delete (asks first; the preview goes with it);
  * the **frames** of the last print not yet a video, with **Make the video**; the new video appears when ready;
  * the **settings**: on / off, a photo every layer or every few seconds (hyperlapse), park the head for the photo and
    where, make the video at the end of the print, frames a second or a video length to aim at, repeat the last frame,
    quality (CRF), preview picture, keep the frames. A setting fixed in `moonraker.conf` is shown locked.
* Without the `TIMELAPSE_TAKE_FRAME` macro (`[include timelapse.cfg]`) the page says that no photo is taken.

## 1.45.0

**Devices: power, outputs and filament sensors** (roadmap phase 6d, fourth part).

* A **Devices** card (Control page on the phone, under the fans on the computer's device page), shown only when there is
  something in it:
  * **Power**: Moonraker's `[power]` devices (smart plugs, relays, GPIO…) on / off; switching one off asks first (it may
    be the printer's own power); a device locked while printing says so, and Moonraker's refusal is shown.
  * **Outputs**: Klipper's `[output_pin]`s, a switch or, for a PWM pin, a slider (up to its `scale`).
  * **Filament sensors**: filament detected or not, and the switch that turns the sensor on or off
    (`SET_FILAMENT_SENSOR`).
* A name starting with `_` stays hidden.

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

* A **Temperatures** card (Home on the phone, under the camera and the print on the computer): every
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

**The text editor on CodeMirror 6** (roadmap phase 6c, third part).

* The editor of the configuration and G-code files is now **CodeMirror 6**, bundled in
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
* **Details** in the long-press menu (and on the computer's file panel): folder, size, last change, last
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

* **The 3D height map's new colours**: blue low → yellow → red high, as a smooth gradient
  across the surface instead of one colour a square, the mesh lines faint on it, a box with a grid on the floor and the
  back walls, and the values on its edges (X and Y in mm, Z minimum and maximum). Seen from the front, above; drag to
  turn, pinch or wheel to zoom, ↻ to go back. The 2D grid and the scale use the same colours.

## 1.36.0

**The height map redone** (roadmap phase 6b, seventh part).

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

**The console's options** (roadmap phase 6b, fifth part). In the title bar of the console (the Control page on the
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

**Macro cards** (roadmap phase 6b, fourth part). The *Calibrations* card is replaced by macro cards set in the new
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

* Under time, remaining and layer a second row with **when it ends** (clock time; "tomorrow" when it
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
* **Debian 11 "Bullseye"** (Raspberry Pi OS before 2023 and the images built on it): with its Flask 1.1 the downloads (configuration files,
  the Android app, logos, recording pictures) failed; now they work there too.
* **Snapshot address** (Settings → Camera → Snapshot), the single photo the AI monitor, the
  camera calibration and the recordings take (later also the timelapse). Empty = automatic from the camera's address
  (`/webcam/?action=snapshot`, which every crowsnest streamer answers; `/webcam2/webrtc` → `/webcam2/?action=snapshot`; the
  adaptive method's own address). **Import from the printer** takes the webcam's snapshot address too. **Try: take a photo** shows the photo
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
  effect running on it. The switch is right whoever changes the light (another interface, a screen on the printer, the console, a macro). The light
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

* **License: GNU GPL v3.0** (`LICENSE`), the same as Klipper and Moonraker; third-party components in `THIRD_PARTY_NOTICES.md`.
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
  di Moonraker, quindi funziona anche dalle altre interfacce della stampante.
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
