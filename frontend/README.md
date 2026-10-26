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
| `src/css/*.css` | the stylesheet, concatenated in file-name order (`00-tokens.css` holds the design tokens) |
| `src/icons/`, `src/logos/` | tab icon and printer logo, embedded as data URIs |
| `vendor/` | third-party code kept unmodified: ReactDOM 18.3.1, compiled Tailwind 3.4.18 (see `THIRD_PARTY_NOTICES.md`) |
| `tools/` | `tailwind_purge.py` (keeps only the Tailwind classes in use), favicon and wordmark-font generators |

Always commit the rebuilt `klippeye_frontend.html` together with the sources: the Raspberry serves the built file, and
`tests/run_all.sh` checks that rebuilding the sources gives exactly the committed file. Browser tests: `tests/ui/`.
The older, detailed design notes (in Italian, to be translated) are in `NOTES-it.md`.
