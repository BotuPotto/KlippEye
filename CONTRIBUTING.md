# Contributing to KlippEye

Thank you for helping. This page explains how the repository is organised and how a change gets from a pull request to the
printers. To use KlippEye, the [user guide](docs/GUIDE.md) is the place to start.

## How the repository is organised

| Where | What |
|---|---|
| `VERSION` | the release number, one for the backend, the dashboard and the notifier |
| `backend/` | the KlippEye service (`klippeye_backend.py`, port 8085): serves the dashboard, talks to Moonraker and the camera, runs the AI monitor (`monitor_core.py`, `local_model.py`, the camera calibration in `camera_*.py`), the password and network checks (`access.py`) |
| `frontend/` | the dashboard: sources in `frontend/src`, built into the single file `frontend/klippeye_frontend.html` ([frontend/README.md](frontend/README.md)) |
| `notifier/` | the notification service (`klippeye_notifier.py`): ntfy, and Firebase for the maintainer's own app; the automatic pause and cancel |
| `scripts/` | `install.sh` (run once), `repair.sh` (self-repair at every start), the `klippeye` command, `diagnose.py`, `benchmark.py`, `replay.py`, `web_front.py` |
| `systemd/` | the templates of the `klippeye` and `klippeye-notifier` services |
| `android/` | the Android app ([android/README.md](android/README.md)); `android/VERSION` is the app's own version |
| `apk/` | the latest app built by GitHub, with `version.json`. Written by the *Android app* workflow, never by hand |
| `models/base/` | the local model of the AI monitor, with the credits of its training pictures |
| `ml/` | the tools that train and measure that model ([ml/README.md](ml/README.md)); not needed on the Raspberry |
| `ci/` | what the GitHub workflows run: `app_ci.py` (building the app), `release.py` (tagging a release) |
| `docs/` | the guides in English and Italian, the API, and their pictures (`docs/images`, made by `tests/ui/docs_screenshots.py`) |
| `tests/` | the automatic tests ([tests/README.md](tests/README.md)) |
| `logos/` | printer logos ([logos/README.md](logos/README.md)) |

On a printer the program lives in `~/klippeye` and the person's data in `~/printer_data/klippeye`. Updates replace only the
first one. The service must keep the name `klippeye`: Moonraker restarts it after an update.

## Making a change

1. Fork the repository and create a branch with a short English name (`fix-camera-timeout`).
2. If you change the dashboard, edit `frontend/src` and rebuild with `python3 frontend/build.py`. Commit the sources and
   `frontend/klippeye_frontend.html` together: the Raspberry serves the built file, and the tests check that it matches the
   sources.
3. Dashboard texts are written in English inside `tx()` and translated in `frontend/src/i18n/`, one file per language.
   `python3 frontend/tools/i18n.py check` says which translations are missing ([frontend/README.md](frontend/README.md#translations)).
4. Run the linter (`ruff check .`, settings in `pyproject.toml`) and the tests: `bash tests/run_all.sh` (add `--no-ui` to skip
   the browser tests). Add tests for what you change. A change to `scripts/`, `systemd/` or the update path also needs the
   end-to-end test ([tests/e2e/README.md](tests/e2e/README.md)).
5. If a page shown in the guides changed, take the pictures again (see [tests/README.md](tests/README.md#tools)).
6. Open a pull request in English: what changes, why, and how you tested it. The *Tests* workflow runs on every pull request.

English is the language of the code, comments, commands, logs, commit messages and documentation. The Italian guides
(`docs/GUIDA.md`, `docs/FUNZIONI.md`, `ml/LEGGIMI.md`) are translations of the English ones: change both.

## Versions and releases

- `VERSION` holds `MAJOR.MINOR.PATCH` for the backend, the dashboard and the notifier. The dashboard shows it.
- `android/VERSION` is the app's own number, raised only for a new app. A change to `android/` with a higher number makes
  GitHub build, sign and publish the APK into `apk/`.
- A release: raise `VERSION` and add its section to `CHANGELOG.md` in the pull request. Once it is merged and its tests pass
  on `main`, the *Release* workflow (`.github/workflows/release.yml`, rules in `ci/release.py`) tags the commit `vX.Y.Z` and
  publishes a GitHub release with the changelog section. When the release has a new app, the tag waits until GitHub has
  built it.
- Printers on the **stable** channel (the default) install only tagged releases; the **dev** channel installs every commit
  of `main`. Never move or delete a published tag.

## Never commit secrets

The repository is public, because Moonraker downloads it without a password. Keys, passwords and Firebase files live only in
the data folder on each Raspberry. The only exceptions are the app's signing key, `android/chiave/klippeye.p12`, stored here
encrypted (its password is the GitHub secret `KLIPPEYE_CHIAVE_PASSWORD`), and the app's `google-services.json`, which is the
GitHub secret `GOOGLE_SERVICES_JSON`.

## Security problems

Please report them privately, as explained in [SECURITY.md](SECURITY.md), not in a public issue.

## License

By contributing you agree that your contribution is released under the GNU General Public License v3.0 ([LICENSE](LICENSE)).
