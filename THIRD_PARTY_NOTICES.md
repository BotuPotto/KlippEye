# Third-party notices

KlippEye is released under the GNU General Public License v3.0 (see `LICENSE`).
It includes or uses the following third-party works, each under its own license.

## Included in the dashboard (`frontend/klippeye_frontend.html`, built from `frontend/`)

| Work | Version | License | Where |
|---|---|---|---|
| React and ReactDOM | 18.3.1 | MIT, Copyright (c) Meta Platforms, Inc. and affiliates | `frontend/vendor/react-dom-18.3.1.min.js` |
| Tailwind CSS (compiled utilities) | 3.4.18 | MIT, Copyright (c) Tailwind Labs, Inc. | `frontend/vendor/tailwind-3.4.18.compiled.css` |
| Outfit font (SemiBold, reduced subset) | — | SIL Open Font License 1.1, Copyright 2021 The Outfit Project Authors (github.com/Outfitio/Outfit-Fonts) | `frontend/src/css/02-wordmark-font.css` |

## Included in the Android app (`android/`, resolved by Gradle at build time)

| Work | License |
|---|---|
| AndroidX Core KTX, AppCompat | Apache License 2.0 |
| Material Components for Android | Apache License 2.0 |
| kotlinx.coroutines | Apache License 2.0 |
| Firebase Cloud Messaging (Firebase BoM) | Apache License 2.0 |

## Used at run time, not distributed with KlippEye

Python packages installed from the system (Flask, Werkzeug, requests, NumPy, OpenCV) keep their own licenses
(BSD-3-Clause, Apache License 2.0). KlippEye talks to Klipper and Moonraker (GPLv3) only through Moonraker's network API.

## Trademarks

The VzBot, Voron and RatRig names and logos (`logos/`, `frontend/src/logos/`) belong to their owners. They are shown only to
identify the user's printer and are not covered by the GPL. If you redistribute KlippEye, check the owners' terms or remove them.
