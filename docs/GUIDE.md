# KlippEye guide

KlippEye is a dashboard, a service and an AI print monitor for 3D printers running **Klipper + Moonraker** on a Raspberry Pi
(or any Linux computer next to the printer), with push notifications and an Android app. This guide takes you from the
installation to everyday use. *Una versione in italiano è in [GUIDA.md](GUIDA.md).*

**Quick start (about 15 minutes):** install with the two lines of [chapter 2](#2-install), open
`http://<address of the Raspberry>:8085` and follow the **guided set-up** that opens by itself ([chapter 3](#3-first-settings)).
Everything else in this guide is there when you need it; every page of the dashboard also has its own **?**.

**Contents:** 1. [What you need](#1-what-you-need) · 2. [Install](#2-install) · 3. [First settings](#3-first-settings) ·
4. [Updates](#4-updates) · 5. [AI monitor](#5-ai-monitor) · 6. [Android app and notifications](#6-android-app-and-notifications) ·
7. [Password and security](#7-password-and-security) · 8. [After a power cut](#8-after-a-power-cut) ·
9. [Where things live](#9-where-things-live) · 10. [Troubleshooting](#10-troubleshooting) ·
A. [Building your own Android app](#a-building-your-own-android-app)

---

## 1. What you need

**Already there:**

* a printer with **Klipper and Moonraker** on a Raspberry Pi (or any Linux computer next to the printer), installed with
  KIAUH, a ready-made image (such as MainsailOS or FluiddPi) or by hand. The printer's other web interfaces can stay: KlippEye
  works next to them;
* **SSH access** to the Raspberry, **once**, for the installation (with your user: it does not have to be `pi`). Everything after
  that happens in the dashboard;
* internet on the Raspberry (to install, for updates, notifications and the AI monitor).

**Optional:** a **camera** with crowsnest (the ready-made images and KIAUH install it already), an **AI service key** for the
AI monitor (Groq is free), a **phone** for notifications (Android with the KlippEye app, or any phone with the ntfy app).

**What KlippEye installs by itself** (with `apt`, asking the password once, only if missing):

| Package | What for |
|---|---|
| `git` | updates and self-repair after a power cut |
| `python3-flask`, `python3-waitress`, `python3-requests` | the KlippEye service and the dashboard |
| `python3-numpy` | the camera calibration (and the AI monitor) |
| `python3-opencv` | the AI monitor: looking at the camera's photos (left out with `--no-ai`) |

It works on every recent Raspberry Pi OS and MainsailOS (Debian 11 "Bullseye", 12 "Bookworm", 13 "Trixie") with Python 3.7 or
newer. Nothing is installed on your computer: a browser is enough.

## 2. Install

Connect to the Raspberry with SSH (`ssh <user>@<address of the Raspberry>`; on MainsailOS the user is usually `pi`) and paste these
lines, one at a time:

```
sudo apt update && sudo apt install -y git
git clone https://github.com/BotuPotto/KlippEye.git ~/klippeye
bash ~/klippeye/scripts/install.sh
```

The first line is only needed when `git` is not there yet (MainsailOS has it: it does no harm). The installer checks what is
missing and installs it by itself: the first time, with OpenCV, it takes a few minutes; after that about a minute. Every step says
`OK`; if something is wrong it says so in plain words (`WARNING` or `ERROR`) and tells you what to do. At the end it shows the
dashboard address and `Moonraker sees KlippEye`.

What the installer does:

* checks **Python, git and the modules** KlippEye needs and **installs the missing ones** (table above). Without `flask`,
  `requests` or `numpy` it stops before touching anything and tells you the command to type;
* creates the **data folder** `~/printer_data/klippeye` (your settings, AI key, notifications): updates never touch it.
  Any user works, not only `pi`: the printer's folders (config, logs, `printer_data` or `printer_1_data` with several
  printers, the old `~/klipper_config`) are asked to Moonraker. To choose the folder by hand:
  `KLIPPEYE_PRINTER_DATA=~/printer_2_data bash ~/klippeye/scripts/install.sh`;
* installs the services **`klippeye`** (the KlippEye service with the dashboard, port **8085**) and **`klippeye-notifier`** (push notifications
  and the automatic pause), started at every boot. If the new service does not answer, it puts everything back as it was;
* adds two terminal commands, `klippeye` and `klippeye-notifiche`;
* connects KlippEye to **Moonraker's update manager** (an `[update_manager klippeye]` entry in `moonraker.conf` and two lines in
  `moonraker.asvc`, with backup copies) and restarts Moonraker, unless the printer is printing.

It can be run again at any time: it repairs without breaking anything. Options:

* `--no-ai`: does not install OpenCV (the AI monitor stays off; add it later by running it again without `--no-ai`);
* `--no-packages`: installs nothing with `apt`, only says what is missing;
* `--no-moonraker`: does not touch Moonraker's configuration;
* `--channel=dev`: every change instead of the tested releases (see 4);
* `--undo`: removes the services, the commands and the Moonraker entry (your folders and the packages stay);
* `--help`.

Open the dashboard: **`http://<address of the Raspberry>:8085`** (the address you open in the browser for the printer, with port 8085). The **guided set-up**
opens (chapter 3).

**The camera and the AI monitor.** The AI monitor and the calibration take one photo at a time from the camera (the *snapshot*).
Usually there is nothing to do: with crowsnest the address is `/webcam/?action=snapshot` and KlippEye works it out by itself. To
check it: **Settings → Camera → Snapshot → Try: take a photo** shows the photo exactly as the Raspberry gets it. With another camera
write there the address of its single photo (the snapshot).

## 3. First settings

**The first time you open the dashboard the guided set-up starts**: nine steps (name and logo, camera, addresses, printer
functions, notifications, AI monitor, password) with a couple of lines of explanation each. Every step can be skipped, and the
last one says what is done and what is left. Repeat it whenever you want from **Settings → Guided set-up**.

Every page has a **?** button in its title bar that opens a short guide (with a drawing where it helps: where to tap the nozzle
in the calibration, what the addresses are for, how the notifications arrive); some groups have their own small **?**.

Everything is in the menu **☰ (Settings)**, in four groups. The settings are saved on the Raspberry and are the same on every
device (except those marked "on this device"). On a phone each page fills the screen; on a computer the settings are one panel
in the middle, with the list on the left.

* **The printer**
  * **Your printers**: the other printers with KlippEye on your network (see below).
  * **Printer functions** (marked *To check* until you confirm it): what the buttons that use your printer's own macros do, see
    below.
  * **Macros**: how the macros are shown (see below).
  * **Motion and Z-offset**: what Z moves, the motion steps and those of the Z-offset card.
* **Camera and AI monitor**
  * **Camera**: the method (WebRTC, MJPEG, MJPEG adaptive or any web page) and its address. **Import from the printer** takes
    them from the cameras already set up on the printer (Moonraker keeps them). Each camera of the printer has its own page;
    there is also **Timelapse** (see below) and the way to the camera calibration of the AI monitor.
  * **AI monitor**: everything of the AI monitor (thresholds, camera calibration, recordings), see 5.
* **Notifications and appearance**
  * **Notifications**: where they arrive (the KlippEye app or the ntfy app), which ones and their language (see 6).
  * **Appearance**: name and logo, colour, look, cards (see below).
  * **Language**: English or Italian, chosen on each device (*Automatic* follows the device's language).
* **System**
  * **Addresses**: only needed if you open KlippEye from outside your home with ZeroTier, Tailscale or another VPN: the
    Raspberry's local IP and its external IP. Empty, the camera uses the address you opened the dashboard at.
  * **Access**: the optional password (see 7).
  * **Updates**: the version, new versions, going back to the previous one, restart of the services, the Android app.

### Printer functions

Every printer parks, wipes the nozzle, loads the filament or switches its light with its own macros (or cannot). **Settings →
Printer functions** says what each button of the dashboard does, and KlippEye fills it in by itself the first time: it looks in
Klipper for the usual names (`PARK`, `CLEAN_NOZZLE`, `LOAD_FILAMENT`/`FILAMENT_LOAD`/`M701`, `UNLOAD_FILAMENT`/`M702`, a pair
like `LIGHTS_ON`/`LIGHTS_OFF`) and for a light output. Check it once and press **All right**. For each function:

* **Automatic**: what KlippEye found (the page says what, or that nothing was found and the button is hidden);
* **Macro**: one of your macros (the field suggests the ones Klipper has);
* **G-code**: a few lines written in the dashboard's editor, which opens over the page;
* **Not used**: the button is not shown;
* **Create a macro for this**: KlippEye proposes one (park at the back, heat and load, heat and unload, wipe on a brush whose
  position you set), it opens in the editor, and when you save it goes into **`klippeye_macros.cfg`**, a file of KlippEye's next
  to `printer.cfg`. The first time, `printer.cfg` gets `[include klippeye_macros.cfg]` at the end (with a backup in the data
  folder). Klipper reads it after a restart: the page offers **Restart Klipper now** (not during a print). A macro that already
  exists in your configuration cannot be created again with the same name.

**The light** can also be switched directly on its output (**Output**: an `[output_pin]`, `[led]`, `[neopixel]`...). Whatever
switches it, the button reads the output itself (and the *klipper-led_effect* effects drawn on it), so it is always right, also
when the light is switched from another program, a screen on the printer, the console or a macro. With macros or G-code you choose where the button
reads the state (or none: it shows what was asked last).

**Lights** (1.37): as many as the printer has. KlippEye finds them by itself — each pair of light macros (`LIGHT_ON` /
`LIGHT_OFF`…), each LED output (`[led]`, `[neopixel]`, `[dotstar]`…) and the pins whose name says light — and lists them
under **Lights**: rename one, change how it is switched (an output, two macros, G-code) and where its state is read,
remove it or add more; from the first change the list is yours (*Find the lights again* goes back to what KlippEye finds).
The round button on the camera switches together the lights marked *Switched by the round button*; the arrow next to it
opens every light — a switch each, the **brightness** (LEDs, PWM pins), the **colour** (RGB LEDs) — and the **scenes**:
*Save as a scene* keeps how the lights are now under a name, a tap brings it back.

**Filament change notification**: the phone gets *Filament run out* when
* a **filament sensor** (`[filament_switch_sensor]`, `[filament_motion_sensor]`) says the filament is gone during a print;
* one of the **macros you choose** runs (`M600` in the G-code, your runout macro...): KlippEye adds to `klippeye_macros.cfg` a
  small wrapper with the same name (`rename_existing`) that writes `KlippEye: filament change` in the console and then runs your
  macro exactly as before. Only macros Klipper really has can be chosen (a wrong one would stop Klipper from starting);
* a **line of the console** you write appears (*Printer paused due to filament runout!* is always recognised).

### Motion

**Settings → Motion**: **what Z moves** (the bed or the toolhead: *Automatic* reads it from Klipper) decides which way the
Z arrows go — with the bed, ↑ brings it up towards the nozzle; with the toolhead, ↑ lifts it. The X/Y pad and the Z
buttons always have 1 and 10 mm steps; 50 and 100 mm can be added (one more ring on the pad, two more Z buttons each).

**Calibrate** (Movement card) also has the **leveling** Klipper offers on your printer: **Z tilt adjust** (`[z_tilt]`),
**Quad gantry level** (`[quad_gantry_level]`) and, on printers with no probe, **Bed screws adjust** (`[bed_screws]`): the
nozzle stops above each screw and a sheet tells you what to do (the paper test); answer *Adjusted* if you turned the screw,
*Accept* if it was right already. Klipper goes round again until a whole round is accepted. **Axis twist compensation**
uses Cartographer's automatic calibration when there is one; otherwise Klipper's own, with the same paper test at a few
points (− / + move the nozzle, *Accept* goes on), then SAVE_CONFIG.

### Height map (bed mesh)

The **Height map / mesh** card (Control page on the phone, Calibration page on a computer): **2D** (seen
from above, the back of the bed at the top, the value of each point; a tap says where a point is) or **3D** (drag to turn,
pinch or wheel to zoom, ↻ to go back); the **probed** points or the **interpolated** mesh Klipper uses; minimum, maximum,
range and number of points. **Calibrate mesh** asks for the profile name (and *Adaptive*: only where the objects of the
print are). **Save as…** saves the mesh in use as a profile, **Clear** stops using it. Under **Profiles**: the ones in
`printer.cfg`, with their range — *Load*, rename, remove. Saving, renaming and removing are kept by SAVE_CONFIG (the
save button at the top).

### Camera in full screen

The ⛶ button of the camera (its card on the phone, the camera panel on a computer) shows it over the whole screen. In
the KlippEye app (1.5.0 or newer) Android's bars disappear and the screen turns to landscape by itself. In a browser
that cannot turn the screen (an iPhone, say) the picture itself is turned so it fills the screen held sideways; the ↻
button switches that off. A tap shows the buttons again; ⤡, Esc or the phone's back leave.

### Notifications: texts and your own

**Settings → Notifications**: under each notification *Change the text* lets you write your own; words in braces are
filled in when it goes out — `{file}`, `{progress}`, `{layer}`, `{total_layers}`, `{elapsed}`, `{remaining}`,
`{message}` (Klipper's reason for an error), `{printer}`… Empty: the usual text. The pause can be announced at once or
after a few seconds (a filament runout that explains it goes out instead). The **error** notification now carries
Klipper's own message (why it shut down, the print's error, the last `!!` line).

**Your notifications** adds more: *Print started*, *Progress reached* (a percent), *Little time left* (minutes), *Layer
reached*, *A line in the console* (words your macro writes with `M118` / `RESPOND`), *Temperature reached* (bed or
nozzle). Each has its text and can be *Important* (it arrives as an alarm). Progress, time and layer go out once a print.

### Console

The console (Control page on the phone, the bar at the bottom on a computer: its arrow opens the whole log) has, in its
title bar: **clear** (empties the view; Klipper keeps its lines, the view shows what comes after), the **options** —
*Autoscroll* (follow the newest line), *Newest on top*, *Show temperatures* (the temperature reports, hidden by default),
kept on this device — and **full screen**. A tap on a command puts it back in the input field.

### Macros

The macro cards (Control page on the phone, Calibration page on a computer) are your shortcuts. **Settings → Macros**
(or the gear of a card) chooses how:
* **All the macros**: one card with every macro of the printer; switch off the ones you never use (the macros whose name
  starts with `_` are never shown);
* **Groups**: cards of your own, each with a **name**, a **colour** (ready ones, or any colour on the wheel of *Custom*), the **macros** you pick in the order you want, and
  **when it shows**: idle, printing, paused (e.g. the filament macros also while paused, the calibrations only when idle).

A macro with parameters has a ⚙ next to its name: it opens a form with the values to send. The choice is in the shared
settings, the same on every phone and computer. The macros chosen in the old *Calibrations* card become a group with that
name. *Endstops and probe* is now a card of its own.

### Tune

The **Tune** card (Control page on the phone, Device page on a computer) changes, also during a print: the **speed** and
**flow** factors (M220 / M221), **pressure advance** and its smooth time, the **machine limits** (velocity, acceleration,
square corner velocity, minimum cruise ratio) and the **firmware retraction** (when `[firmware_retraction]` exists). Use
− / + or type a value; under each one is the value of `printer.cfg`, and the round arrow goes back to it. Nothing is
written to `printer.cfg`: a restart of Klipper brings its values back.

### Print files

The **Print files** card (Files page) has a **search** by name (also by folder) and an **order** to choose: newest or
oldest first, name A→Z / Z→A, shortest or longest print, most filament, largest, last printed (kept on this device).
A long press on a file opens its menu: **Details** shows folder, size, last change, last printed,
slicer, estimated time, layer and first layer height, object height, layers, filament (type, length, weight), nozzle,
first layer temperatures — with *Start print*; then the editor and *Delete*. On a computer the panel next to the list has
a *Details* button too.

### Temperatures

The **Temperatures** card (Home on the phone, under the camera and the print on the computer) lists every heater and
sensor Klipper has — nozzles, bed, `heater_generic`, `temperature_fan`, `temperature_sensor` (names starting with `_`
stay hidden) — with temperature, target and power. The **chart** shows the last 5, 10 or 20 minutes: a line for each, the
target dashed in the same colour; it starts from what Moonraker already recorded and updates every 2 seconds. A finger or
the pointer on the chart reads the time and the values at that moment. Tap a **name** to hide or show its lines, a
**target** to change it (nozzle and bed with the usual dialog, the others with `SET_HEATER_TEMPERATURE` or
`SET_TEMPERATURE_FAN_TARGET`, up to their `max_temp`).

### Devices

The **Devices** card (Control page on the phone, under the fans on a computer) shows up when there is something in it:
Moonraker's `[power]` devices (smart plugs, relays, GPIO), on and off — switching off asks first, since it may be the
printer's power; Klipper's `[output_pin]`s, a switch or, for a PWM pin, a slider; the **filament sensors**, with their
state (filament or not) and the switch that turns them on or off. Names starting with `_` stay hidden.

### Timelapse

With moonraker-timelapse installed, the Files page has a third part, **Timelapse**: the **videos** (preview, date, size;
tap one to watch it full screen, *Download*, delete), the **frames** of the last print not yet a video with **Make the
video**, and the **settings** (also in Settings → Camera → Timelapse): on or off, which camera, a photo every layer or at
intervals, park the head for the photo and where, make the video at the end, frames a second or a video length, repeat
the last frame, quality, preview, keep the frames. **Advanced** shows the others: custom park position and height, speeds,
retraction, wait, camera delay, rotation and mirroring of the video, pixel format, date in the file name, ffmpeg options.

Changes are not sent one by one: **Save and restart Moonraker** writes them in `moonraker.conf`, section `[timelapse]`
(only those that differ from the defaults, or are already there; the rest of the file stays), and restarts Moonraker to
read them. It cannot be saved while printing; *Undo changes* drops them. If `printer.cfg` lacks `[include timelapse.cfg]`
(the `TIMELAPSE_TAKE_FRAME` macro), the page says so. Without moonraker-timelapse the Timelapse part explains how to
install it.

### Spools (Spoolman)

If Moonraker has `[spoolman]`, the **Spool** card (Home on the phone, with the fans on a computer) shows the spool in use
in its colour, with maker, name, material and what is left (weight, length, a bar and the percent). **Change spool**
lists Spoolman's spools, the last used first, with a search: tap one to make it the spool in use, and Moonraker counts
each print's filament on it; **No spool** leaves none. If Spoolman does not answer, the card says so.

### More cameras

Besides the camera of the settings (the one the AI monitor watches), the dashboard uses the other cameras set up on the
printer (Moonraker keeps them): with more than one, the camera card (and the computer's camera panel) has a **menu** to
pick which to watch, and the full screen follows it. Each webcam keeps its own way of being shown and its flips; the
choice stays on this device.

### More printers

Every printer has its own KlippEye. In **Settings → Your printers** add the others with their address on your network
(*Try* checks they answer and reads the name they give themselves); then a tap on the name at the top lists them and
switches between them (in the app, in the same window), and the **Overview** shows them all at once, with their state and
temperatures. The list is the same on every device of this printer.

### G-code viewer

**See the layers** (in a file's menu, *Layers* on the computer's file panel, and on the print card) draws the file from
above, a layer at a time: the slider, ‹ › or the arrow keys pick the layer (with its number and height), the lines take
the colour of the kind the slicer says (outer and inner walls, top / bottom, infill, bridges, support, skirt / brim), the
layer below is grey and the travels show on request; tap a kind in the legend to hide it. Pinch or the wheel zooms, a
drag moves. While that file prints, **Follow the print** shows the nozzle's layer, what is printed and what is not yet,
and the nozzle.

### Folding cards and the order of the pages

The main cards have a **chevron** at the top right that folds them down to their title (it stays so on this device). In
**Settings → Appearance → Cards** there is a small drawing of each page: **drag** a card by its handle (or use the arrows)
to move it, also into the other column; the switch shows or hides it. Phone, tablet and computer each keep their own
layout. The print card always stays in its place; *Usual order, everything shown* goes back to the start.

In **Settings → Appearance → Show the hints** you can hide on this device the small texts that explain how to use a page
(*Tap to change*, *Long-press a file…* and the like).

In **Settings → Appearance → Colour** choose the colour of buttons, switches and highlights: the logo's violet, blue,
teal, green, amber, pink or **your own** from the colour wheel (one too dark or too pale is adjusted to read on the dark
page). It stays on this device.

In **Settings → Appearance → Look** the same page dresses after another phone: **One UI** (the usual), **Liquid
Glass**, **Material 3 Expressive** or **HyperOS 4**, always with the chosen colour.

### Print queue

If `moonraker.conf` has `[job_queue]`, a file's menu (long press; on a computer the *Queue* button of the file panel) has
**Add to the queue**, with how many copies: the prints start one after the other. The dialog says what happens: after the
jobs waiting, when the printer is free, or at once (*Add and print*) when the printer is free and the queue running. While
jobs wait, the **Print queue** card sits at the top of the Files page: the order with thumbnail and estimated time, the
total; move a job up, down or to the front, remove it; **Start the queue** or **Pause the queue**; **Empty**.

### Print history

At the top of the **Files** page a switch goes from *Print files* to **History** (kept on this device). The
**statistics** come from Moonraker's `[history]`: prints, print time, filament used, longest and average print, how many
completed; a bar shows how they ended (completed, cancelled, failed) and a chart the **last 14 days**, print time or
filament a day (tap a bar for its value). *Reset* sets Moonraker's totals back to zero. Below, the **list** of prints with
thumbnail, outcome, date, time and filament, with a search (notes too) and filters. Tap a print for its details, a
**note** (kept on the Raspberry, every device sees it), **Print again** if the file is still there, or **Remove** it from
the history. If Moonraker has no `[history]` in `moonraker.conf`, the page says to add it.

### Configuration files

The **Configuration files** card (Config page) lists folders first, then files. The ⇅ button next to the search box chooses
the **order** (name A→Z or Z→A, last change first or oldest first, largest first) and whether to show the **backup files**
(the `printer-YYYYMMDD_HHMMSS.cfg` written by SAVE_CONFIG, `.bak`, `.bkp`…) and the **hidden files** (names starting with
a dot). The choice stays on this device; a line under the list says how many are left out, and a tap on it shows them.

### The text editor

Configuration and G-code files open in the dashboard's editor, built on **CodeMirror 6**: line numbers,
colours (sections, keys, pins, values, comments, the G-code and Jinja2 of macros), the caret's line marked, brackets
matched. The arrow next to a `[section]` **folds and unfolds** it; the **Sections of the file** button lists them all (tap
one to go there) and folds or unfolds them all at once. The page button opens the **reference** for the section the caret
is in: Klipper's Config Reference for `.cfg` files (`[stepper_x]` leads to `[stepper]`), Moonraker's configuration page
for `moonraker.conf`. The magnifier (or Ctrl+F) opens **Find and replace**: next / previous, all, match case, regexp, by
word, replace, replace all. **Undo / Redo** (Ctrl+Z / Ctrl+Y), **Comment / Uncomment** (Ctrl+/; `#` in configuration
files, `;` in G-code), Ctrl+S to save and *Save and restart* (SAVE_CONFIG) stay.

### During a print

The **print card** (Home) shows the file, the progress, the time, what is left and the layer; under them **when it ends**
(clock time), the **speed** and the **volumetric flow** now. **More details** opens the estimates one by one (by the file,
the filament and the slicer), the total time with pauses, the filament used (m and g), the height, the speed requested
and the speed and flow factors.

**Exclude an object**: when the slicer labels the objects (PrusaSlicer, OrcaSlicer, SuperSlicer "Label objects", Cura
with a plugin) and Klipper has `[exclude_object]`, the card offers **Exclude an object**: a map of the bed with the
objects (the one printing now in blue) and their list; choose one and **Exclude it**. It is not printed any more, the
others go on; it cannot be put back in that print.

## 4. Updates

**Settings → Updates → Check for a new release → Update KlippEye.** The KlippEye service restarts for a few seconds and the page reloads
by itself. Your settings, the AI key and the notifications stay. The button is off while printing.

The update goes through Moonraker's update manager (entry `klippeye`): the printer's other web interfaces see it too.

**Update channel** (same page): **Stable releases** (the default) installs only the releases that passed all the automatic
tests on GitHub, tagged `v1.10.0`, `v1.11.0`…; **Every change** installs every change as soon as it is on GitHub, for
testing new things. Moonraker restarts for a few seconds when you switch.

**New versions by themselves**: once a day (never while printing) the dashboard asks Moonraker whether KlippEye, Klipper,
Moonraker or the other programs have new versions. If so, a number appears on the **System** tab and a message names them;
nothing is installed by itself. **Settings → Updates → Look for new versions by itself** switches it off (for each browser
or phone).

| If… | then |
|---|---|
| the new release does not work as hoped | Settings → Updates → **Go back to the previous release** |
| the page says the program files were changed by hand | Settings → Updates → **Restore the program files** (settings and keys are not touched) |
| the dashboard does not open any more | from SSH: `klippeye status`, `klippeye restart`, `klippeye log`; to put the files back as they are on GitHub: `klippeye update --force` |

## 5. AI monitor

While a print runs, the KlippEye service looks at the camera every few seconds with **OpenCV**, on the Raspberry, without internet. It
compares each picture with a *background* made of the last pictures, ignores light changes and the passing print head, and
counts only changes that **stay**. When something suspicious stays for a few checks, it sends the picture (and how it looked
before) to an **online AI**, which judges whether there is a real problem: spaghetti, a detached part, a layer shift, warping.

Everything is in **Settings → AI monitor**, one page, top to bottom:

1. **Monitor on** and whether the notification service is running.
2. **How it looks at the print**: one line says what the monitor watches now: the **whole bed outside the parts** (with a
   camera calibration) or only the **outer band of a rectangle** (without). From here: **Camera calibration** (below),
   **Monitor thresholds** (the fine numbers: sensitivity, how long a change must stay, pauses, when checking starts; the
   rectangle is there too, used only without a calibration) and **Recordings** (to measure the monitor).
3. **When it sees a problem**: the **minimum AI confidence** (the only one: 70% is the usual value; above 85% a failed print may
   not be stopped), which defects count, how many AI verdicts in a row, and the **automatic actions** (pause or cancel by
   itself, both off by default; the AI can be wrong and a cancelled print cannot be recovered).
4. **The AI service**: the **service** and **model** of the monitor and the **keys** of the AI services. KlippEye works with
   Groq, Google Gemini, OpenAI, Anthropic (Claude), Mistral, OpenRouter, Meta Llama, Together, Fireworks and any other
   OpenAI-compatible server (for example a model on your network: its address, a key only if it asks for one). Groq, Google
   Gemini and Mistral have a free plan: in **Keys of the AI services** tap **Get a key** next to the service, create it there
   and paste it. The model list is read from the service with your key; the monitor needs a model that **sees pictures**
   (listed first; **Default** is one KlippEye knows works). The keys stay in `~/printer_data/klippeye/ai.json`, readable only
   by the service; the page shows only their last 4 characters. Also here: whether the earlier picture is sent too.
   The **log analysis** has its own service and model: the gear next to **Error analysis and suggestions** in the
   System logs card (Config page); the keys are the same.

**During a print.** The **AI** badge in the top bar is grey with no print, green while all is well, amber or red with an alarm; a
tap opens the **AI monitoring panel** (status, score, the last verdict with its picture to enlarge). When the AI sees a problem,
the **print card** shows what it saw and asks: **Real problem**, **False alarm** or **Ignore**. "False alarm" and "Ignore" put the
badge back to green until the next alarm; "Real problem" and "False alarm" are also kept with the alarm and help measure the
monitor (Recordings → Measure now). The alarms of a print are closed when the next one starts.

The AI writes its observations in the language of the notifications; every alert is kept with its pictures (AI monitoring panel,
the alarms in Recordings, and `~/printer_data/klippeye/alerts/`). When the AI proposed to pause or cancel but no defect reached
the minimum confidence, the alarm says so in orange ("Pause proposed, under the threshold").

| If… | try… |
|---|---|
| alarms when the print head passes | calibrate the camera and adjust the toolhead and gantry outlines; raise "Checks in a row the change must stay for" (3 → 4) |
| alarms when the light changes | keep "Light change" at 30; fix the camera exposure; diffuse a bright LED |
| the AI reports doubtful problems | raise "Minimum AI confidence" (70 → 80) |
| a real failure goes unnoticed | calibrate the camera (whole bed watched); check the alarms in Recordings: an orange one means the confidence is too high |

### Calibrating the camera

**Settings → AI monitor → Camera calibration** teaches KlippEye where every point of the printer appears in the camera picture. With it
the AI monitor knows, at every check, where the toolhead and the gantry are and leaves them out (they are the main cause of
false alarms). About fifteen minutes, once; again only if you move the camera.

**Before you start**: clean bed, the light as during prints, the printer idle. The printer moves by itself during the
calibration: keep your hands out.

1. **How does the Z axis move?** The **bed** (VzBot, Voron Trident, RatRig V-Core, most CoreXY) or the **toolhead**
   (Voron 2.4). KlippEye proposes the answer from Klipper's configuration. Printers whose bed moves in Y (Prusa, Ender) are
   not supported yet.
2. **Home** the printer.
3. **Markers** (only when Z moves the bed: for the camera the nozzle alone is always at the same height, so six markers on
   the bed give the second height). Two ways:
   * **Print the markers (recommended)**: **Download the markers (STL)**, six small pyramids already placed for your bed.
     Slice the file with your usual settings (no supports, a colour that stands out on the bed), print it and leave it on
     the bed. Then choose the G-code you printed and **Read the markers from this file**: KlippEye finds where the slicer
     put the pyramids and how tall they came out (the slicer may move them: it does not matter).
   * **Quick blobs**: choose the nozzle and bed temperatures and **Make the 6 blobs**: the printer leaves six small discs
     of filament (with retraction and a Z hop between them). Faster, less precise.
4. **The 12 points.** For each point:
   1. press **Go to point**: the printer moves and a new picture appears;
   2. tap the picture where the point is (see the table below);
   3. a magnified view opens: tap again **exactly** on the point;
   4. **Keep this point**.

   | Points | What happens | What to tap |
   |---|---|---|
   | 1 to 6 | the nozzle stops 3 mm above a marker (Z moves the bed) or at a point of the bed (Z moves the toolhead) | the **lowest point of the nozzle**, the metal tip, **not** the marker under it |
   | 7 to 12, Z moves the bed | the bed goes down and the nozzle goes to the back | the **top tip of the marker** (for a blob: its centre) |
   | 7 to 12, Z moves the toolhead | the nozzle goes to the same points, higher | the **lowest point of the nozzle** |

   The page shows a small drawing of what to tap at each point. Green numbers are done; tap a number to see it or redo it.
   The yellow cross is your tap, the green cross a point already kept.

   **Homing with the markers on the bed.** After printing the markers many printers switch the motors off, so the page
   homes again. KlippEye reads from Klipper where Z is homed and places the pyramids of the STL away from it (the page
   says where); **Home the printer** asks first if a marker could be under the toolhead or the probe there (an older
   print, a `[homing_override]` macro, no `z_hop`). During the calibration the motors stay on (the idle timeout is made
   longer and put back at the end).

   **Faster: the nozzle found by itself.** Once you have tapped the nozzle at one point, KlippEye can find it at the other
   nozzle points: **Find the nozzle by itself at the other N points** goes to each, moves the toolhead aside for a moment
   (to see where it is) and looks for the tip you tapped (about 15 seconds a point; keep your hands out). The points found
   are blue: **Use the N points found** keeps them, and **Calculate** turns red any that does not fit, to tap by hand.
   At a single point, **Go there and find the nozzle by itself** opens the magnified view on what it found. The marker
   points (7 to 12 when Z moves the bed) are always tapped by hand.
5. **Calculate the calibration**: the average error in pixels (good: a few pixels) and, in red, the points to redo (a tap
   on the wrong thing: redo just those and calculate again). The live picture shows the toolhead and the bed drawn over it:
   move the toolhead with the buttons, the drawing must follow it. **Save the calibration**, then remove the markers.

**Toolhead and gantry.** After saving, the page shows the live picture with the **toolhead** (purple) and the **gantry**
(orange: the bar that carries the toolhead from side to side) drawn over it. What is inside those outlines is what the
monitor leaves out, so they must cover the parts, with a little room (much more would hide a problem near the nozzle).
Adjust them by **dragging the dots on the picture** (each side of the toolhead, its top — the height — and the upper and
lower edge of the gantry: the size is shown while you drag) or with **−** and **+** (5 mm a step), moving the toolhead
with the buttons to check a few places. Dots that would sit on top of each other (a small or far toolhead) are left out:
their sizes keep **−** and **+**:

* toolhead: how far it goes **left, right, in front of and behind the nozzle**, **above** the nozzle tip and below it;
* gantry: where the bar **starts behind the nozzle**, how **deep** it is and its **lower and upper edges** above the nozzle
  tip. Switch it off if your printer has no gantry crossing the picture.

The switch **Leave out the toolhead and the gantry** (on by default), on the same page, turns the masks on and off.

**The whole bed, except where the parts are.** With the calibration the monitor also knows where the objects of the print
are, and watches the **whole bed around them** instead of only the edges of the watched area: plastic that appears where no
part should be (spaghetti next to the part, a part torn off and dragged) counts, the part growing does not. The outlines
of the objects come from Klipper's `exclude_object` when the slicer labels the objects (PrusaSlicer/SuperSlicer/OrcaSlicer:
*Label objects*, and `[exclude_object]` in `printer.cfg`: recommended), otherwise from the G-code of the print, read once at
the start. During a print the live picture of this page shows them in green. Switch: **Watch the whole bed, except where the parts
are**, on the same page (on by default). Where the toolhead is right on the part,
the camera cannot see under it: a failure is recognised by what appears around the part.

The calibration is valid **until the camera moves**. Every ten minutes the KlippEye service compares the picture with the one taken
at calibration; if the camera has moved, the page (and its line in the menu) says so and the monitor stops using the
calibration (and the masks) until you calibrate again. The sizes of the toolhead and the gantry are kept.

### Measuring the monitor (recordings)

Instead of guessing whether a change of the thresholds helps, measure it:

1. **Settings → AI monitor → Recordings → Record the prints**. During every print the KlippEye service keeps the pictures the monitor looked at
   (small, about 150 MB for a four-hour print) with layer, position and score, in `~/printer_data/klippeye/recordings/`. The
   oldest prints are deleted when the chosen space is full, and nothing is recorded with less than 1 GB free on the disk.
2. After each print, open it in the same page: look through its pictures and say **It went fine**, or, if it failed, move to
   the first picture where the problem shows and press **It failed from here**. Below, **Alarms of this print** lists its
   alarms, each with the picture the AI saw (tap to enlarge) and its response. You judge whether the AI's response matches the
   real state of the print: **Correct result** if it does, **Wrong result** if not (a pause for a print that was fine, or
   "continue" while something went wrong). An alarm the AI could
   not judge (an error of the AI service) asks **There was a problem** or **No problem**. *See it among the pictures* goes back
   to the print at that moment. Alarms of prints that were not recorded are folded at the bottom of the page.
3. **Measure now** runs the monitor again on the recorded prints ticked under *Prints to use* (all of them unless you untick
   some: a print with another camera or a test can be left out), with the thresholds in use now, and shows the alarms per
   hour, how many were false and whether each failure was caught (and how long it took). From the terminal, to compare other
   thresholds: `klippeye replay --set sensitivity=45 --set persist_checks=4` (options: `scripts/replay.py`). With a camera
   calibration the replay leaves out the toolhead and the gantry like the live monitor (on the prints recorded with
   KlippEye 1.13 or later, which keep the toolhead position); `--set machine_masks=off` compares without them; on prints recorded with 1.16 or later
   (which keep the objects) the whole bed is watched outside the parts, `--set expected_zone=off` compares with the outer band only.

**How precise is it?** In the same page:
* **Precision of the AI**: on the alarms you judged, how often the AI's response matched the real print (pauses that were
  right, problems stopped, false stops, problems missed), and a table of what each **minimum AI confidence** would have given
  on the same alarms; when another value is better the page says so and, with at least 10 judged alarms, offers to use it.
* **Measure and compare the options**: the replay also without the G-code zone, without the masks, less and more sensitive,
  each marked better, worse or the same: what the G-code weighs and whether the thresholds have margin (a few minutes;
  from the terminal `klippeye replay --current --compare`).

The page also shows the **monitor load**: the time of one check and the CPU the KlippEye service used in the last minute.

**"AI error 429"** on an alarm means the AI service refused the request: too many requests or too much data (pictures) for
the limits of its plan, per minute or per day; the alarm shows the service's own words. Since 1.26.1 the KlippEye service waits and asks
once more when the service asks to wait a few seconds. If it keeps happening (a daily limit), raise *Pause between two AI
analyses* (Monitor thresholds), turn off *Also send the earlier picture to the AI* (one picture per request instead of two), choose a model with
higher limits, or use a paid plan of the service.

## 6. Android app and notifications

The Android app is a full-screen window on the dashboard, with push notifications, file downloads and its own updates.

* **Install it**: open the dashboard in the phone's browser → **Settings → Updates → Android app → Download the app**, open the
  downloaded file and allow installing from this source. From then on the app updates itself: **Settings → Updates → Android
  app → Update the app** (Android always asks you to confirm).
* **Addresses**: the first time the app asks for the Raspberry's address (the one you open in the browser for the printer, e.g.
  `192.168.1.20` or `printer.local`) and, if you use ZeroTier or a VPN, the external one. It tries each twice, in turn; when none answers it
  shows *Retry* and *Addresses*. They can also be changed in **Settings → Addresses**.
* **Back button**: closes the guide or the open dialog and goes back to the previous page of the menu or the previous step of
  the guided set-up. Links to websites, stores and the ntfy app open outside the app.

**Push notifications** (print completed, error, pause, filament runout, AI alerts) are sent by the `klippeye-notifier` service,
always on from 1.20.0 (it also does the automatic pause / cancel chosen in the AI monitor). They travel over
[ntfy](https://ntfy.sh), a free service: no account and no key. KlippEye makes a private address (`klippeye-` + 16 letters and
digits) that only your phones know.

**With the KlippEye app (Android, from 1.3.0) nothing else is needed.** The first time it opens the app asks *"Receive the
notifications of the printer on this phone?"*: **Set up** opens the guided procedure (**Settings → Notifications → This phone**):

1. **Allow the notifications** (Android's window).
2. **Make the private address on the Raspberry** (one tap).
3. **Receive on this phone**: the app listens by itself, also when closed and after the phone restarts. A small fixed
   notification *"KlippEye in ascolto"* shows the open connection: hold it to hide it.
4. **Let KlippEye stay awake**: allow KlippEye to run without battery limits, otherwise Android puts it to sleep and the
   notifications arrive late.
5. **Check that it arrives**: KlippEye sends a test and the page confirms by itself when it reaches the phone.

*Do not receive on this phone* turns it off on that phone only. If you change the address from the dashboard, the KlippEye apps
pick it up by themselves the next time they are opened.

**Other phones (iPhone, or if you prefer the ntfy app).** On the same page, from a browser or under *Other phones*: install the
free **ntfy** app (Google Play, F-Droid, App Store), **scan the QR code** with the camera (in the phone's browser just tap *Open in
the ntfy app*, or add server and topic by hand) and **send a test notification**. Several phones can scan the same code.

Whoever knows the address can read the notifications: do not share the code; **New address** makes another one (phones with the
ntfy app must be paired again). With an **ntfy server of your own** write its address (and a token, if it wants one) under *Your
own ntfy server*. Nothing needs restarting: the service reads the change by itself.

If the page says the notification service has not shown up (installations before 1.20.0), run once on the Raspberry the
command the page shows (`bash ~/klippeye/scripts/install.sh`). From the terminal: `klippeye notify test` and
`klippeye notify check`. The language of the notifications is chosen in **Settings → Notifications**; you can also write your
own texts in `notifier.json` (`"messages": {"complete": "Done!"}`).

## 7. Password and security

* **Optional password**: Settings → **Access** → type it twice → **Turn on the password**. This device stays logged in; the
  others (also the app) ask for it once and remember it for 6 months. From there you can change or remove it, and log out the
  other devices. **Forgot it?** On the Raspberry: `klippeye password remove` (or `klippeye password` to set a new one).
* **Guest password** (with the password on): Settings → **Access** → **Guest password**. Who logs in with it sees the printer,
  the camera, the files and the history, but cannot send commands, start or stop prints, or open the configuration, the logs
  or the settings. On the Raspberry: `klippeye password guest-set` / `guest-remove`. Note: KlippEye protects its own address;
  Moonraker's own port (7125) is protected by Moonraker's `[authorization]` section, not by KlippEye.
* **Network checks**, always on: the KlippEye service answers only when called by an IP address, the Raspberry's name or a home-network
  name (`.local`, `.lan`…), and refuses commands coming from pages of other sites. To use a name of your own:
  `klippeye access host-add printer.example.com`. `klippeye access network-checks off` turns the checks off.
* The password does not protect Moonraker (port 7125) or the printer's other web interfaces, and the traffic is plain http on your home network.
  **Never open port 8085 to the internet**: from outside use a VPN (ZeroTier, Tailscale, WireGuard).

## 8. After a power cut

A power cut while the Raspberry writes can leave a program file empty or half written. KlippEye repairs itself, without
internet: before every start of the service `scripts/repair.sh` compares the program files with the copy git keeps in
`~/klippeye/.git` and restores the damaged ones; the KlippEye service checks again when it starts and when the dashboard page is asked
for. Your settings and Klipper's configuration are never touched.

* `klippeye repair log` (or `~/printer_data/klippeye/repair.log`) tells what was restored; `klippeye repair` checks by hand.
* Changing program files by hand? Create `~/printer_data/klippeye/no-repair` first, or the repair puts them back.
* If git's own data is damaged, the log says so: run `klippeye update --force`.

## 9. Where things live

| Where | What |
|---|---|
| `~/klippeye` | the program: a copy of the GitHub repository. Do not change it by hand (Moonraker would refuse to update) |
| `~/printer_data/klippeye` | your things: `monitor.json` (monitor thresholds), `ai.json` (AI key), `access.json` (password hash), `notifier.json` and `service-account.json` (notifications), `alerts/`, backups. Copy this folder to save them |
| services `klippeye`, `klippeye-notifier` | started by systemd at boot; `klippeye` must keep its name: Moonraker restarts it after an update |
| Moonraker's database, namespace `klippeye` | the dashboard settings shared by every device |

**How updates work:** the installer adds this entry to `moonraker.conf`:

```
[update_manager klippeye]
type: git_repo
path: ~/klippeye
origin: https://github.com/BotuPotto/KlippEye.git
primary_branch: main
channel: stable
managed_services: klippeye
```

On **Update**, Moonraker fetches from GitHub the newest release tag (or, on the `dev` channel, the newest commit) into `~/klippeye` and restarts the `klippeye` service; the notifier
notices its file changed and restarts by itself. The Android app comes the same way: the `apk/` folder of the repository holds
the latest app built by GitHub, and the KlippEye service offers it to the phone only if its size and SHA-256 match `apk/version.json`.

## 10. Troubleshooting

**Asking for help?** Attach the diagnostic report: *Settings → Updates → Diagnostics → Download a diagnostic report*, or
`klippeye diagnose --save` on the Raspberry. It contains no keys, passwords or tokens.

| What you see | What to do |
|---|---|
| The dashboard does not answer | `klippeye status`; `klippeye restart`; `klippeye log` shows the last lines of the KlippEye service's log |
| The page says the name is not allowed | open it with the IP address, or allow the name: `klippeye access host-add NAME` |
| Moonraker "does not know KlippEye yet" | `bash ~/klippeye/scripts/install.sh`, then restart Moonraker from the Restart menu |
| The camera stays black | Settings → Camera: check the method and the address (or *Import from the printer*); Settings → Addresses |
| The AI monitor never calls the AI | the AI key (5.1); OpenCV installed (`sudo apt install python3-opencv`); the monitor is on |
| No notifications | `klippeye notify check` lists what is missing; `klippeye notify test` sends a test |
| The app cannot install an update | allow "Install unknown apps" for KlippEye; Samsung's Auto Blocker must be off |

Terminal commands: `klippeye status`, `version`, `log [notifier]`, `restart [backend|notifier|all]`, `repair [log]`,
`update [--force]`, `notify test|check`, `password [set|remove|status|logout-all]`, `access ...`, `diagnose [--save]`,
`undo-install`, `help`.

---

## A. Building your own Android app

Needed only for your own changes to the app (notifications do not need it: section 6). GitHub builds the app for free on
public repositories.

1. **Fork** the repository on GitHub and install KlippEye from your fork (`git clone https://github.com/<you>/KlippEye.git`).
2. **Signing key password**: Android updates an app only when it is signed with the same key. GitHub creates the key the first
   time and encrypts it with a password you choose: repository **Settings → Secrets and variables → Actions → New repository
   secret**, name **`KLIPPEYE_CHIAVE_PASSWORD`**, value a long sentence (at least 16 characters, on one line). Keep it safe.
3. **Settings → Actions → General → Workflow permissions → Read and write permissions** (the workflow saves the app in `apk/`).
4. **Actions → App Android → Run workflow**. After 5–10 minutes the app is in `apk/`; update KlippEye from the dashboard and install
   the app from Settings → Updates → Android app (uninstall first an app signed with another key).
5. **A new app version**: raise the number in `android/VERSION` (three numbers, e.g. `1.2.1`); GitHub builds it by itself.

The workflow explains in plain words what is wrong when it stops (missing secret, short password, a key different from the
published app's…). Technical details: [android/README.md](../android/README.md).
