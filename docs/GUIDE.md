# KlippEye guide

KlippEye is a dashboard, a backend and an AI print monitor for 3D printers running **Klipper + Moonraker** on a Raspberry Pi
(or any Linux computer next to the printer), with push notifications and an Android app. This guide takes you from the
installation to everyday use. *Una versione in italiano è in [GUIDA.md](GUIDA.md).*

**Contents:** 1. [What you need](#1-what-you-need) · 2. [Install](#2-install) · 3. [First settings](#3-first-settings) ·
4. [Updates](#4-updates) · 5. [AI monitor](#5-ai-monitor) · 6. [Android app and notifications](#6-android-app-and-notifications) ·
7. [Password and security](#7-password-and-security) · 8. [After a power cut](#8-after-a-power-cut) ·
9. [Where things live](#9-where-things-live) · 10. [Troubleshooting](#10-troubleshooting) ·
A. [Building your own Android app](#a-building-your-own-android-app)

---

## 1. What you need

* A printer with **Klipper and Moonraker** (installed with KIAUH, MainsailOS, FluiddPi or by hand). Mainsail or Fluidd can stay:
  KlippEye works next to them.
* **Python 3.7+**, **git** and the Python modules `flask` and `requests` (the installer tells you how to install
  whatever is missing). **OpenCV** (`python3-opencv`) is only needed by the AI monitor.
* SSH access to the Raspberry, **once**, for the installation. Everything after that happens in the dashboard.
* Optional: a camera (crowsnest / camera-streamer, as for Mainsail), an AI service key (Groq is free, OpenAI is paid) for the
  AI monitor, an Android phone.

## 2. Install

Connect to the Raspberry with SSH (`ssh pi@<address of the Raspberry>`, with your user) and paste these two lines, one at a time:

```
git clone https://github.com/BotuPotto/KlippEye.git ~/klippeye
bash ~/klippeye/scripts/install.sh
```

It takes about a minute. Every step says `OK`; if something is wrong it says so in plain words (`WARNING` or `ERROR`) and tells
you what to do. At the end it shows the dashboard address and `Moonraker sees KlippEye`.

What the installer does:

* creates the **data folder** `~/printer_data/klippeye` (your settings, AI key, notification keys): updates never touch it.
  Any user works, not only `pi`: the printer's folders (config, logs, `printer_data` or `printer_1_data` with several
  printers, the old `~/klipper_config`) are asked to Moonraker. To choose the folder by hand:
  `KLIPPEYE_PRINTER_DATA=~/printer_2_data bash ~/klippeye/scripts/install.sh`;
* installs the services **`klippeye`** (backend and dashboard, port **8085**) and **`klippeye-notifier`** (push notifications,
  only once its keys are there), started at every boot. If the new backend does not answer, it puts everything back as it was;
* adds two terminal commands, `klippeye` and `klippeye-notifiche`;
* connects KlippEye to **Moonraker's update manager** (an `[update_manager klippeye]` entry in `moonraker.conf` and two lines in
  `moonraker.asvc`, with backup copies) and restarts Moonraker, unless the printer is printing.

It can be run again at any time: it repairs without breaking anything. Options: `--no-moonraker` (do not touch Moonraker's
configuration), `--channel=dev` (every change instead of the tested releases, see 4), `--undo` (remove the services, the
commands and the Moonraker entry; your folders stay), `--help`.

Open the dashboard: **`http://<address of the Raspberry>:8085`**. Use the address that works for Mainsail, with port 8085.

## 3. First settings

Everything is in the menu **☰ (Settings)**. The settings are saved on the Raspberry and are the same on every device.

* **Printer**: the logo in the top bar (KlippEye, VzBot, Voron, RatRig) and a name of your own, also used as the browser tab
  title. Official brand logos go in the `logos/` folder of the repository (see [logos/README.md](../logos/README.md)).
* **Printer functions** (marked *To check* until you confirm it): what the buttons that use your printer's own macros do,
  see below.
* **Camera**: the method (WebRTC, MJPEG, MJPEG adaptive or any web page) and its address. **Import from Mainsail** takes them from
  the webcams already set up in Mainsail.
* **Addresses**: the Raspberry's local IP and, if you use a VPN such as ZeroTier, its external IP: the camera and the Android app
  use the right one depending on the network you are on.
* **Z-offset**: the step sizes of the Z-offset card.
* **Notifications**: which push notifications to receive and their language (see 6).
* **AI monitor**: everything of the AI monitor (thresholds, camera calibration, recordings), see 5.
* **Access**: the optional password (see 7).
* **Updates**: releases, rollback, restart of the services, the Android app.
* **Language**: English or Italian, chosen on each device (*Automatic* follows the device's language).

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
when the light is switched from Mainsail, KlipperScreen, the console or a macro. With macros or G-code you choose where the button
reads the state (or none: it shows what was asked last).

**Filament change notification**: the phone gets *Filament run out* when
* a **filament sensor** (`[filament_switch_sensor]`, `[filament_motion_sensor]`) says the filament is gone during a print;
* one of the **macros you choose** runs (`M600` in the G-code, your runout macro...): KlippEye adds to `klippeye_macros.cfg` a
  small wrapper with the same name (`rename_existing`) that writes `KlippEye: filament change` in the console and then runs your
  macro exactly as before. Only macros Klipper really has can be chosen (a wrong one would stop Klipper from starting);
* a **line of the console** you write appears (*Printer paused due to filament runout!* is always recognised).

## 4. Updates

**Settings → Updates → Check for a new release → Update KlippEye.** The backend restarts for a few seconds and the page reloads
by itself. Your settings, the AI key and the notifications stay. The button is off while printing.

The same update is visible in **Mainsail / Fluidd → Update Manager** (entry `klippeye`), which also offers *Rollback* and *Recover*.

**Update channel** (same page): **Stable releases** (the default) installs only the releases that passed all the automatic
tests on GitHub, tagged `v1.10.0`, `v1.11.0`…; **Every change** installs every change as soon as it is on GitHub, for
testing new things. Moonraker restarts for a few seconds when you switch.

| If… | then |
|---|---|
| the new release does not work as hoped | Settings → Updates → **Go back to the previous release** |
| the page says the program files were changed by hand | Settings → Updates → **Restore the program files** (settings and keys are not touched) |
| the dashboard does not open any more | Mainsail → Update Manager → `klippeye` → *Rollback* or *Recover*; from SSH: `klippeye status`, `klippeye log`, `klippeye update --force` |

## 5. AI monitor

While a print runs, the backend looks at the camera every few seconds with **OpenCV**, on the Raspberry, without internet. It
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
4. **The AI service**: the **AI key** (Groq is free; the same key is used for the log analysis, saved in
   `~/printer_data/klippeye/ai.json`, readable only by the service), whether the earlier picture is sent too, the model.

The AI writes its observations in the language of the notifications; every alert is kept with its pictures (AI monitor card,
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
5. **Calculate the calibration**: the average error in pixels (good: a few pixels) and, in red, the points to redo (a tap
   on the wrong thing: redo just those and calculate again). The live picture shows the toolhead and the bed drawn over it:
   move the toolhead with the buttons, the drawing must follow it. **Save the calibration**, then remove the markers.

**Toolhead and gantry.** After saving, the page shows the live picture with the **toolhead** (purple) and the **gantry**
(orange: the bar that carries the toolhead from side to side) drawn over it. What is inside those outlines is what the
monitor leaves out, so they must cover the parts, with a little room (much more would hide a problem near the nozzle).
Adjust them with **−** and **+** (5 mm a step), moving the toolhead with the buttons to check a few places:

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

The calibration is valid **until the camera moves**. Every ten minutes the backend compares the picture with the one taken
at calibration; if the camera has moved, the page (and its line in the menu) says so and the monitor stops using the
calibration (and the masks) until you calibrate again. The sizes of the toolhead and the gantry are kept.

### Measuring the monitor (recordings)

Instead of guessing whether a change of the thresholds helps, measure it:

1. **Settings → AI monitor → Recordings → Record the prints**. During every print the backend keeps the pictures the monitor looked at
   (small, about 150 MB for a four-hour print) with layer, position and score, in `~/printer_data/klippeye/recordings/`. The
   oldest prints are deleted when the chosen space is full, and nothing is recorded with less than 1 GB free on the disk.
2. After each print, in the same page: mark each **alarm** as *False alarm* or *Real problem*, and open the print to say
   **It went fine**, or, if it failed, move to the first picture where the problem shows and press **It failed from here**.
3. **Measure now** runs the monitor again on every recorded print, with the thresholds in use now, and shows the alarms per
   hour, how many were false and whether each failure was caught (and how long it took). From the terminal, to compare other
   thresholds: `klippeye replay --set sensitivity=45 --set persist_checks=4` (options: `scripts/replay.py`). With a camera
   calibration the replay leaves out the toolhead and the gantry like the live monitor (on the prints recorded with
   KlippEye 1.13 or later, which keep the toolhead position); `--set machine_masks=off` compares without them; on prints recorded with 1.16 or later
   (which keep the objects) the whole bed is watched outside the parts, `--set expected_zone=off` compares with the outer band only.

The page also shows the **monitor load**: the time of one check and the CPU the backend used in the last minute.

## 6. Android app and notifications

The Android app is a full-screen window on the dashboard, with push notifications, file downloads and its own updates.

* **Install it**: open the dashboard in the phone's browser → **Settings → Updates → Android app → Download the app**, open the
  downloaded file and allow installing from this source. From then on the app updates itself: **Settings → Updates → Android
  app → Update the app** (Android always asks you to confirm).
* **Addresses**: the app looks for the Raspberry at the addresses of **Settings → Addresses**; when it cannot connect it shows
  an *Addresses* window.

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
* **Network checks**, always on: the backend answers only when called by an IP address, the Raspberry's name or a home-network
  name (`.local`, `.lan`…), and refuses commands coming from pages of other sites. To use a name of your own:
  `klippeye access host-add printer.example.com`. `klippeye access network-checks off` turns the checks off.
* The password does not protect Moonraker (port 7125) or Mainsail/Fluidd, and the traffic is plain http on your home network.
  **Never open port 8085 to the internet**: from outside use a VPN (ZeroTier, Tailscale, WireGuard).

## 8. After a power cut

A power cut while the Raspberry writes can leave a program file empty or half written. KlippEye repairs itself, without
internet: before every start of the service `scripts/repair.sh` compares the program files with the copy git keeps in
`~/klippeye/.git` and restores the damaged ones; the backend checks again when it starts and when the dashboard page is asked
for. Your settings and Klipper's configuration are never touched.

* `klippeye repair log` (or `~/printer_data/klippeye/repair.log`) tells what was restored; `klippeye repair` checks by hand.
* Changing program files by hand? Create `~/printer_data/klippeye/no-repair` first, or the repair puts them back.
* If git's own data is damaged, the log says so: use *Recover* in Mainsail or `klippeye update --force`.

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
the latest app built by GitHub, and the backend offers it to the phone only if its size and SHA-256 match `apk/version.json`.

## 10. Troubleshooting

**Asking for help?** Attach the diagnostic report: *Settings → Updates → Diagnostics → Download a diagnostic report*, or
`klippeye diagnose --save` on the Raspberry. It contains no keys, passwords or tokens.

| What you see | What to do |
|---|---|
| The dashboard does not answer | `klippeye status`; `klippeye restart`; `klippeye log` shows the last lines of the backend's log |
| The page says the name is not allowed | open it with the IP address, or allow the name: `klippeye access host-add NAME` |
| Moonraker "does not know KlippEye yet" | `bash ~/klippeye/scripts/install.sh`, then restart Moonraker from the Restart menu |
| The camera stays black | Settings → Camera: check the method and the address (or *Import from Mainsail*); Settings → Addresses |
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
