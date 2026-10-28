# KlippEye

A dashboard, a backend (the program that serves it and watches the print through the camera), push notifications and an
Android app for 3D printers running **Klipper + Moonraker** on a Raspberry Pi. This repository is what runs on the
Raspberry: Moonraker's update manager installs and updates it from here.

> Until release 1.0.x the project was called **VzBot**. The move of those installs to KlippEye was part of releases 1.1.0 to
> 1.10.0 (tag `v1.10.0`): an install still on VzBot moves with that release first.

**Step-by-step guide: [docs/GUIDE.md](docs/GUIDE.md)** (in Italian: [docs/GUIDA.md](docs/GUIDA.md)).
Security: [SECURITY.md](SECURITY.md) · Contributing: [CONTRIBUTING.md](CONTRIBUTING.md) · Changes: [CHANGELOG.md](CHANGELOG.md)

## Features

* Full printer control from phone or desktop: temperatures, fans, motion, Z-offset, files, console and macros, config
  editor, bed mesh, calibrations, endstops, service and host restarts, software updates.
* AI print monitor: a local OpenCV filter on the Raspberry; an online AI (Groq or OpenAI, with your own key) only judges
  the pictures that look suspicious. Alerts are kept with their images.
* Push notifications to the Android app (Firebase Cloud Messaging), in English or Italian, with optional automatic pause/cancel.
* Self-repair after a power loss: damaged program files are restored from git at every start.
* English and Italian dashboard (it follows the device's language; *Settings → Language* to choose).
* Optional password, network checks (host name and origin of requests) and restricted permissions of the secrets.

## How updates work

```
  pull request                GitHub (this repository)                Raspberry
  ────────────                ────────────────────────                ─────────
  merged, tests pass    ───►  release tagged v1.10.0          ◄───┐
                                                                  │ Moonraker (update manager) checks it
  dashboard ► Settings ► Updates ► "Update KlippEye" ─────────────┘  and fetches only the differences into ~/klippeye,
                                                                     then restarts the "klippeye" service.
                                                                     The page reloads by itself.
```

* The program lives in **one folder** (`~/klippeye`), **your data** (monitor thresholds, AI key, notifications, password)
  in another (`~/printer_data/klippeye`): an update only touches the first one.
* After a **power loss** damaged files are restored automatically at every start (guide, part G).
* If something goes wrong: **"Go back to the previous version"** on the same page (or Rollback in Mainsail/Fluidd).
* It is Moonraker's update manager, so updates are also visible and can be started from Mainsail and Fluidd.

## The Android app

```
  your PC / GitHub                                  Raspberry                              Phone
  ────────────────                                  ─────────                              ─────
  raise the number in android/VERSION
  GitHub builds and signs the APK (workflow)  ───►  "Update KlippEye" brings apk/ here ───►  app dashboard ► Updates
  and saves it in apk/ (+ version.json)            the backend offers it (/app/KlippEye.apk)  ► "Update the app" ► Android asks
```

The app has its own version (`android/VERSION`). The backend offers the APK only if its size and SHA-256 match
`apk/version.json`; the app checks them again after downloading, and Android installs only an APK signed with the same
key, after the user confirms. Setup (once) and steps: guide, part C. Technical details: [android/README.md](android/README.md).

## Repository layout

| Where | What | Changed by |
|---|---|---|
| `VERSION` | the release (one number for backend, dashboard and notifier) | each release |
| `backend/` | the backend (`klippeye_backend.py`): serves the dashboard, bridges Moonraker, AI monitor (its judging in `monitor_core.py`, the recordings of the prints in `recorder.py`, the camera calibration in `camera_calibration.py`, `camera_model.py`, `camera_watch.py`), password and network checks (`access.py`) | updates |
| `frontend/` | the dashboard: sources in `frontend/src`, built into `frontend/klippeye_frontend.html` ([frontend/README.md](frontend/README.md)) | updates |
| `notifier/klippeye_notifier.py` | the push-notification service | updates |
| `scripts/` | `install.sh` (run once), `repair.sh` (self-repair, runs by itself), `diagnose.py` (report for bug reports), `replay.py` (measures the AI monitor on the recorded prints), `klippeye` and `klippeye-notifiche` (rescue commands) | updates |
| `systemd/` | templates of the `klippeye` and `klippeye-notifier` services | updates |
| `android/` | the Android app sources (`android/VERSION` = app version) | new app releases |
| `apk/` | `KlippEye.apk` and `version.json`: the latest app built by GitHub | GitHub (`.github/workflows/app.yml`) |
| `ci/app_ci.py` | the steps of the app build workflow | updates |
| `tests/` | automatic tests ([tests/README.md](tests/README.md)), run on GitHub for every pull request | contributors |
| `logos/` | official printer logos for the printer picker ([logos/README.md](logos/README.md)) | once |
| `~/printer_data/klippeye/monitor.json` | AI monitor thresholds (changed from the dashboard) | the dashboard |
| `~/printer_data/klippeye/ai.json` | the AI service key (mode 600) | the dashboard |
| `~/printer_data/klippeye/access.json`, `internal.token` | optional password (hash only) and token of the local services (mode 600) | the dashboard / `klippeye password` |
| `~/printer_data/klippeye/notifier.json`, `service-account.json` | notification settings and key | you, once |

The services are **`klippeye`** (backend + dashboard, port 8085) and **`klippeye-notifier`** (notifications). Do not rename
`klippeye`: it is the service Moonraker restarts after an update.

## Versions

`MAJOR.MINOR.PATCH`, one release for backend, dashboard and notifier, in `VERSION`; the dashboard shows it ("Release 1.2.0
available"). Every release is described in [CHANGELOG.md](CHANGELOG.md). The **Android app** has its own number in
`android/VERSION`, raised only for a new app.

When a pull request that raises `VERSION` is merged and its tests pass on `main`, the *Release* workflow
(`.github/workflows/release.yml`, rules in `ci/release.py`) tags the commit `vX.Y.Z` and publishes a GitHub release with
its CHANGELOG section. Printers on the **stable** update channel (the default) install only these tagged releases; the
**dev** channel installs every commit of `main`. A release with a new Android app is tagged after GitHub has built the app.

## Never commit secrets

This repository is public (Moonraker downloads it without a password). Keys, passwords and `service-account.json` live
**only** in `~/printer_data/klippeye`, outside the repository. The only exceptions are the app signing key,
`android/chiave/klippeye.p12`, stored here **encrypted** (its password is a GitHub secret), and the app's Firebase file,
which is a GitHub secret.

## License

KlippEye is free software, released under the [GNU General Public License v3.0](LICENSE), like Klipper, Moonraker,
Mainsail and Fluidd. Third-party components and their licenses: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
