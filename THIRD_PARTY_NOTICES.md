# Third-party notices

KlippEye is released under the GNU General Public License v3.0 (see `LICENSE`).
It includes or uses the following third-party works, each under its own license.

## Included in the dashboard (`frontend/klippeye_frontend.html`, built from `frontend/`)

| Work | Version | License | Where |
|---|---|---|---|
| React and ReactDOM | 18.3.1 | MIT, Copyright (c) Meta Platforms, Inc. and affiliates | `frontend/vendor/react-dom-18.3.1.min.js` |
| Tailwind CSS (compiled utilities) | 3.4.18 | MIT, Copyright (c) Tailwind Labs, Inc. | `frontend/vendor/tailwind-3.4.18.compiled.css` |
| qrcode-generator | 2.0.4 | MIT, Copyright (c) 2009 Kazuhiko Arase | `frontend/vendor/qrcode-generator-2.0.4.js` |
| CodeMirror 6 (state, view, language, commands, search, autocomplete) | 6.x (see `frontend/tools/codemirror/build.sh`) | MIT, Copyright (C) 2018-2021 by Marijn Haverbeke and others | `frontend/vendor/codemirror-6.js` |
| Lezer (common, highlight, lr) | 1.x | MIT, Copyright (C) 2018 by Marijn Haverbeke and others | `frontend/vendor/codemirror-6.js` |
| style-mod, w3c-keyname, crelt, find-cluster-break | 4.1.2, 2.2.8, 1.0.6, 1.0.2 | MIT, Copyright (C) Marijn Haverbeke | `frontend/vendor/codemirror-6.js` |
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
