# KlippEye guide

KlippEye is a dashboard, a backend and an AI print monitor for 3D printers running **Klipper + Moonraker** on a Raspberry Pi
(or any Linux computer next to the printer), with push notifications and an Android app. This guide takes you from the
installation to everyday use. *Una versione in italiano è in [GUIDA.md](GUIDA.md).*

**Contents:** 1. [What you need](#1-what-you-need) · 2. [Install](#2-install) · 3. [First settings](#3-first-settings) ·
4. [Updates](#4-updates) · 5. [AI monitor](#5-ai-monitor) · 6. [Android app and notifications](#6-android-app-and-notifications) ·
7. [Password and security](#7-password-and-security) · 8. [After a power cut](#8-after-a-power-cut) ·
9. [Where things live](#9-where-things-live) · 10. [Troubleshooting](#10-troubleshooting) ·
A. [Building your own Android app](#a-building-your-own-android-app) · B. [Moving from VzBot 1.0.x](#b-moving-from-vzbot-10x)

---

## 1. What you need

* A printer with **Klipper and Moonraker** (installed with KIAUH, MainsailOS, FluiddPi or by hand). Mainsail or Fluidd can stay:
  KlippEye works next to them.
* **Python 3.7+**, **git** and the Python modules `flask`, `flask-cors` and `requests` (the installer tells you how to install
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

* creates the **data folder** `~/printer_data/klippeye` (your settings, AI key, notification keys): updates never touch it;
* installs the services **`klippeye`** (backend and dashboard, port **8085**) and **`klippeye-notifier`** (push notifications,
  only once its keys are there), started at every boot. If the new backend does not answer, it puts everything back as it was;
* adds two terminal commands, `klippeye` and `klippeye-notifiche`;
* connects KlippEye to **Moonraker's update manager** (an `[update_manager klippeye]` entry in `moonraker.conf` and two lines in
  `moonraker.asvc`, with backup copies) and restarts Moonraker, unless the printer is printing.

It can be run again at any time: it repairs without breaking anything. Options: `--no-moonraker` (do not touch Moonraker's
configuration), `--undo` (remove the services, the commands and the Moonraker entry; your folders stay), `--help`.

Open the dashboard: **`http://<address of the Raspberry>:8085`**. Use the address that works for Mainsail, with port 8085.

## 3. First settings

Everything is in the menu **☰ (Settings)**. The settings are saved on the Raspberry and are the same on every device.

* **Printer**: the logo in the top bar (KlippEye, VzBot, Voron, RatRig) and a name of your own, also used as the browser tab
  title. Official brand logos go in the `logos/` folder of the repository (see [logos/README.md](../logos/README.md)).
* **Camera**: the method (WebRTC, MJPEG, MJPEG adaptive or any web page) and its address. **Import from Mainsail** takes them from
  the webcams already set up in Mainsail.
* **Addresses**: the Raspberry's local IP and, if you use a VPN such as ZeroTier, its external IP: the camera and the Android app
  use the right one depending on the network you are on.
* **Z-offset**: the step sizes of the Z-offset card.
* **Notifications**: which push notifications to receive and their language (see 6).
* **AI monitor** and **Monitor thresholds**: see 5.
* **Access**: the optional password (see 7).
* **Updates**: releases, rollback, restart of the services, the Android app.
* **Language**: English or Italian, chosen on each device (*Automatic* follows the device's language).

## 4. Updates

**Settings → Updates → Check for a new release → Update KlippEye.** The backend restarts for a few seconds and the page reloads
by itself. Your settings, the AI key and the notifications stay. The button is off while printing.

The same update is visible in **Mainsail / Fluidd → Update Manager** (entry `klippeye`), which also offers *Rollback* and *Recover*.

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

1. **AI key**: dashboard → **Config → System logs → ⚙️**: choose the service (Groq, free, is recommended) and paste the key.
   The same key is used for the log analysis. It is saved in `~/printer_data/klippeye/ai.json`, readable only by the service.
2. **Settings → AI monitor**: which defects count, how many verdicts in a row, the minimum confidence, and the **automatic
   actions** (pause or cancel by itself, both off by default; the AI can be wrong and a cancelled print cannot be recovered).
3. **Settings → Monitor thresholds**: sensitivity, the watched area on the camera picture, pauses between AI calls, when checking
   starts. **Tip:** draw the watched area on the bed only: belts and parts of the gantry in the foreground move all the time.

The AI writes its observations in the language of the notifications; every alert is kept with its pictures (AI monitor card,
and `~/printer_data/klippeye/alerts/`).

| If… | try… |
|---|---|
| alarms when the print head passes | keep "Ignore passing movements" on; raise "Checks in a row the change must stay for" (3 → 4 or 5) |
| alarms when the light changes | keep "Light change" at 30; fix the camera exposure; diffuse a bright LED |
| the AI reports doubtful problems | raise "Minimum AI confidence" (70 → 80) |
| a real failure goes unnoticed | lower "Movement at the edges" or make the watched area larger |

## 6. Android app and notifications

The Android app is a full-screen window on the dashboard, with push notifications, file downloads and its own updates.

* **Install it**: open the dashboard in the phone's browser → **Settings → Updates → Android app → Download the app**, open the
  downloaded file and allow installing from this source. From then on the app updates itself: **Settings → Updates → Android
  app → Update the app** (Android always asks you to confirm).
* **Addresses**: the app looks for the Raspberry at the addresses of **Settings → Addresses**; when it cannot connect it shows
  an *Addresses* window.

**Push notifications** (print completed, error, pause, filament runout, AI alerts) are sent by the `klippeye-notifier` service
through **Firebase Cloud Messaging**. They need a Firebase project shared by the app and the Raspberry:

* on the Raspberry, `~/printer_data/klippeye/notifier.json` and the Firebase service-account key `service-account.json`;
* in the app, the `google-services.json` of the **same** Firebase project, built in.

The app published in this repository is built for its maintainer's Firebase project. **To receive notifications on your own
printer you currently build your own app** from a fork of the repository (GitHub does the building: see appendix A). A simpler
way that works with the published app is planned.

Minimal `notifier.json` (the `topic` must be the one built into your app, `notification_topic` in
`android/app/src/main/res/values/notifiche.xml`):

```json
{
  "service_account_file": "service-account.json",
  "topic": "your-private-topic"
}
```

Then run `bash ~/klippeye/scripts/install.sh` again (it starts the notifier once the keys are there) and test with
`klippeye notify test`. The language of the notifications is chosen in **Settings → Notifications**; you can also write your
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
channel: dev
managed_services: klippeye
```

On **Update**, Moonraker fetches the changes from GitHub into `~/klippeye` and restarts the `klippeye` service; the notifier
notices its file changed and restarts by itself. The Android app comes the same way: the `apk/` folder of the repository holds
the latest app built by GitHub, and the backend offers it to the phone only if its size and SHA-256 match `apk/version.json`.

## 10. Troubleshooting

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
`update [--force]`, `notify test|check`, `password [set|remove|status|logout-all]`, `access ...`, `undo-install`, `help`.

---

## A. Building your own Android app

Needed only for your own notifications (section 6) or your own changes to the app. GitHub builds the app for free on public
repositories.

1. **Fork** the repository on GitHub and install KlippEye from your fork (`git clone https://github.com/<you>/KlippEye.git`).
2. **Signing key password**: Android updates an app only when it is signed with the same key. GitHub creates the key the first
   time and encrypts it with a password you choose: repository **Settings → Secrets and variables → Actions → New repository
   secret**, name **`KLIPPEYE_CHIAVE_PASSWORD`**, value a long sentence (at least 16 characters, on one line). Keep it safe.
3. **Firebase** (for notifications): create a Firebase project, add an Android app with package name `com.klippeye.app`,
   download its `google-services.json` and put its whole content in a second secret, **`GOOGLE_SERVICES_JSON`**. In the same
   project create a service-account key (*Project settings → Service accounts → Generate new private key*): that file is the
   Raspberry's `service-account.json`. Choose your own private topic in `android/app/src/main/res/values/notifiche.xml` and use
   the same in `notifier.json`.
4. **Settings → Actions → General → Workflow permissions → Read and write permissions** (the workflow saves the app in `apk/`).
5. **Actions → App Android → Run workflow**. After 5–10 minutes the app is in `apk/`; update KlippEye from the dashboard and install
   the app from Settings → Updates → Android app (uninstall first an app signed with another key).
6. **A new app version**: raise the number in `android/VERSION` (three numbers, e.g. `1.2.1`); GitHub builds it by itself.

The workflow explains in plain words what is wrong when it stops (missing secret, short password, a key different from the
published app's…). Technical details: [android/README.md](../android/README.md).

## B. Moving from VzBot 1.0.x

KlippEye was called **VzBot** until release 1.0.x. An existing VzBot install moves to the new name with one button:
update it (it still appears as `vzbot`), then **Settings → Updates → Move to KlippEye**. The dashboard shows the 6 steps: it
copies your data to `~/printer_data/klippeye`, moves the program from `~/vzbot` to `~/klippeye`, installs the new services and
removes the old ones, and puts everything back if a step fails. If it needs the administrator password, run
`bash ~/vzbot/scripts/passa-a-klippeye.sh` from SSH. The old app (`com.vzbot.dashboard`) is offered the new KlippEye app,
which installs next to it: uninstall the old one once the new one works.
