# KlippEye dashboard (frontend)

The dashboard is one self-contained HTML file, `klippeye_frontend.html`, served as is by the backend (port 8085).
It is built from the sources in this folder with Python 3 only (no npm, no network):

```bash
python3 frontend/build.py          # writes frontend/klippeye_frontend.html with the release from ../VERSION
```

| Path | Content |
|---|---|
| `src/index.html` | page skeleton with the `{{icons}}`, `{{styles}}` and `{{script}}` placeholders |
| `src/app/*.js` | the application (React 18 without JSX, `h()` = `React.createElement`), concatenated in file-name order; `99-main.js` starts it |
| `src/i18n/<lang>.json` | translations: English text → translated text (`it.json` = Italian), embedded at build time |
| `src/css/*.css` | the stylesheet, concatenated in file-name order (`00-tokens.css` holds the design tokens) |
| `src/icons/`, `src/logos/` | tab icon and printer logo, embedded as data URIs |
| `vendor/` | third-party code kept unmodified: ReactDOM 18.3.1, compiled Tailwind 3.4.18 (see `THIRD_PARTY_NOTICES.md`) |
| `tools/` | `i18n.py` (translation checks and helpers, below), `tailwind_purge.py` (keeps only the Tailwind classes in use), favicon and wordmark-font generators |

## Translations

Texts are written in English in the code and marked for translation:

```js
tx("Restart the backend")                        // a text
tx("Uploaded {count} files", { count })          // placeholders in braces, filled in after translating
txc("verb", "Print")                             // the same English word with two meanings: key "verb|Print"
```

The page uses the language chosen in *Settings → Language* (kept in `localStorage`, key `ke_lang`), otherwise the device's
language, otherwise English. `LOCALE` (in `src/app/02-i18n.js`) is the matching locale for dates and numbers.

* `python3 frontend/tools/i18n.py check` fails when a text has no Italian translation (the tests run it); `check -v` also
  lists string literals outside `tx()` that might be visible text.
* The names and explanations of the monitor thresholds come from the backend (`CONFIG_SPEC` in `backend/klippeye_backend.py`),
  in English; `check` requires their translations too.
* A new language: add `src/i18n/<code>.json` with the same keys as `it.json` and one entry in `I18N_LANGUAGES`.

Always commit the rebuilt `klippeye_frontend.html` together with the sources: the Raspberry serves the built file, and
`tests/run_all.sh` checks that rebuilding the sources gives exactly the committed file. Browser tests: `tests/ui/`.
The older, detailed design notes (in Italian, to be translated) are in `NOTES-it.md`.
