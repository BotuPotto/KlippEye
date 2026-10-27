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
| `app/` | the steps of the Android build workflow (`ci/app_ci.py`) with fake Android tools; when a release gets its tag (`ci/release.py`, `release_test.py`) | Java (`keytool`), git |
| `ui/` | the dashboard in Chromium: every page, settings, editor, motion, offline/resume, access with the real backend | playwright + Chromium, pillow |
| `e2e/` | install, updates, rollback, recover, update channel, undo, power cuts and the Android app on a simulated Raspberry with a real Moonraker and a local "GitHub" ([e2e/README.md](e2e/README.md)); not part of `run_all.sh` | git, a Moonraker checkout (`e2e/setup.py`), playwright for two scenarios |

The tests also run on GitHub for every pull request (`.github/workflows/tests.yml`).
Many test names are still in Italian: they will be translated together with the rest of the project.
`backend/fixtures/vzbot_brain_original.py` is the original VzBot Brain, kept to check that the detector still gives the same
results with the default values.

The end-to-end test runs on its own (`python3 tests/e2e/setup.py` once, then `python3 tests/e2e/e2e_test.py`) and on GitHub
with the "End-to-end" workflow (`.github/workflows/e2e.yml`).
