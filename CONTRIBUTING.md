# Contributing to KlippEye

Thank you for helping! KlippEye is a dashboard, a notifier and an Android app for Klipper printers.

## Layout

| Folder | What it is |
|---|---|
| `backend/` | Flask backend (port 8085): serves the dashboard, bridges Moonraker and the camera, runs the AI monitor |
| `frontend/` | the dashboard: sources in `frontend/src`, built into the single file `frontend/klippeye_frontend.html` |
| `notifier/` | push notifications to the phone (Firebase Cloud Messaging) |
| `android/` | the Android app (a WebView around the dashboard + notifications) |
| `scripts/`, `systemd/` | installer, `klippeye` command, self-repair, service files |
| `tests/` | automatic tests, see `tests/README.md` |

## Making a change

1. Fork the repository and create a branch with a short English name (`fix-camera-timeout`).
2. If you change the dashboard, edit `frontend/src` and rebuild: `python3 frontend/build.py`. Commit both the sources and
   `frontend/klippeye_frontend.html` (the Raspberry serves the built file; the tests check it matches the sources).
3. Run the tests: `bash tests/run_all.sh` (add `--no-ui` to skip the browser tests). Add tests for what you change.
   A change to `scripts/`, `systemd/` or the update path: also run the end-to-end test ([tests/e2e/README.md](tests/e2e/README.md)).
4. Open a pull request in English: what changes, why, how you tested it. The *Tests* workflow runs on every pull request.

## Conventions

* English for code, comments, file names, commands, logs, commit messages and documentation. Dashboard text is written in
  English inside `tx()` and translated in `frontend/src/i18n/` (see [frontend/README.md](frontend/README.md#translations));
  some older parts (notifications, AI texts, guide) are still in Italian.
* Versions: `MAJOR.MINOR.PATCH` in `VERSION` (backend, dashboard, notifier) and `android/VERSION` (the app). A change to `android/`
  with a higher `android/VERSION` makes GitHub build and publish the APK.
* Releases: raise `VERSION` and add its section to `CHANGELOG.md` in the pull request. Once it is merged and the tests pass,
  GitHub tags it `vX.Y.Z` by itself (`.github/workflows/release.yml`): that is what the printers on the stable channel install.
  Never move or delete a published tag.
* Never commit secrets: no API keys, no `google-services.json`, no Firebase service-account keys, no keystore passwords.

## License

By contributing you agree that your contribution is released under the GNU General Public License v3.0 (`LICENSE`).
