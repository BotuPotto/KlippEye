# KlippEye tests

```bash
bash tests/run_all.sh            # everything (about 30–40 minutes, most of it the browser tests)
bash tests/run_all.sh --no-ui    # without the browser tests
bash tests/run_all.sh --quick    # skips the two slow detector runs at the real 3-second rhythm
```

| Folder | What it checks | Needs |
|---|---|---|
| `backend/` | settings, endpoints, access/password, self-repair, AI monitor detector with real OpenCV on synthetic pictures, against a fake Moonraker and camera (`fakes.py`) | flask, requests, numpy, opencv |
| `notifier/` | notification logic (`test_watcher.py`) and the whole service against a fake Moonraker and a fake Google that verifies the RS256 sign-in (`test_integration.py`) | cryptography, playwright (for the stand-in) |
| `app/` | the steps of the Android build workflow (`ci/app_ci.py`) with fake Android tools | Java (`keytool`), git |
| `ui/` | the dashboard in Chromium: every page, settings, editor, motion, offline/resume, access with the real backend | playwright + Chromium, pillow |

The tests also run on GitHub for every pull request (`.github/workflows/tests.yml`).
Many test names are still in Italian: they will be translated together with the rest of the project.
`backend/fixtures/vzbot_brain_original.py` is the original VzBot Brain, kept to check that the detector still gives the same
results with the default values.

Not published yet: the end-to-end simulation of installation, updates, migration and power loss (it needs a real Moonraker
checkout and a Kotlin compiler); it will be added with its setup script.
