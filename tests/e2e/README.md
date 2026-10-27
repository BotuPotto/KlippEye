# End-to-end test

`e2e_test.py` installs and updates KlippEye on a **simulated Raspberry Pi**, the way a person does it, with the real
pieces wherever possible:

* the real `scripts/install.sh`, backend, notifier, dashboard and rescue commands of this repository;
* a **real Moonraker** (cloned from GitHub at a fixed commit by `setup.py`) with its update manager;
* a local bare git repository playing **GitHub**, to which the test pushes releases tagged `vX.Y.Z` (as the release
  workflow does), so Moonraker's *Update*, *Rollback* and *Recover* really run;
* a small **systemd** (`fakebin/systemctl`) that really starts, stops and restarts the programs of the `.service` files,
  with `ExecStartPre`, `Restart=always` and drop-ins; `sudo` and `journalctl` are stand-ins too;
* a fake **Google** (`tests/notifier/fake_google.py`) for the notifications' Firebase sign-in.

Each scenario starts from a fresh world in `tests/e2e/.work/worlds/<scenario>` (a fake home folder with `printer_data/`).
Nothing outside `tests/e2e/.work/` is touched, but the test uses the ports 7125 (Moonraker), 8085 (backend), 7391 and
7455: stop a real KlippEye or Moonraker on the same computer first.

| Scenario | What it checks |
|---|---|
| `install` | a fresh install: services, data folder, Moonraker's update manager entry, commands, `klippeye status` and `diagnose`; running it again changes nothing |
| `update` | *Update* through the backend, *Rollback*, a file changed by hand (refused, then *Recover* soft and hard), a broken release rolled back from Moonraker |
| `undo` | `install.sh --undo` takes KlippEye off, and it installs again |
| `channel` | the stable channel offers only tagged releases; the dashboard switches to `dev`; `--channel=stable` |
| `fails` | a backend that does not start: the installer says so and takes its service off again |
| `no-um` | a `moonraker.conf` without `[update_manager]` |
| `printing` | while printing the installer does not restart Moonraker |
| `ui` | the real dashboard in Chromium: update, go back, recover, restart the backend, AI monitor thresholds |
| `app` | the Android app's way: GitHub builds the APK, Moonraker brings it, the backend offers it, the dashboard and the app's own Kotlin code download it |
| `blackout` | power cuts: damaged program files are restored at start and on page load; git locks; `no-repair` |
| `safety` | the installer refuses to run as root, unknown options, `--help` |

## Running it

Linux with `git`, Python 3.9 or later and the backend's modules (`pip install flask requests cryptography`), then:

```
python3 tests/e2e/setup.py          # once: Moonraker in tests/e2e/.work/
python3 tests/e2e/e2e_test.py       # every scenario (about 10 minutes)
python3 tests/e2e/e2e_test.py -k update    # only the scenarios whose name contains "update"
```

`setup.py` installs Moonraker's requirements with pip into `tests/e2e/.work/venv`. Without access to PyPI, run it with
`KLIPPEYE_E2E_NO_PIP=1`: the pure-Python requirements then come from their GitHub sources and the compiled ones
(dbus-fast, streaming-form-data) from the small stand-ins in `shims/`, which are enough for this test.

`ui` and `app` need Playwright with Chromium (`pip install playwright` and `playwright install chromium`); without it
they are skipped and the summary says so. The Kotlin checks of `app` (`AppDownload.kt` with the app's
`Aggiornamento.kt`) also need `kotlinc` and `java` (`KOTLINC_HOME`, or `kotlinc` on the `PATH`).

Every check prints `PASS` or `FAIL`; the end lists the failed ones and the test exits with 1 if there are any. The output
of the installer and the logs of the fake services stay in `tests/e2e/.work/worlds/<scenario>/` for a look afterwards.
