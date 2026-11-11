# KlippEye service API

The KlippEye service (`backend/klippeye_backend.py`) serves the dashboard and answers on the same address
(usually `http://<raspberry>:8085`). This page lists what it answers, for scripts, home automation and other tools.
Everything is JSON unless said otherwise. Moonraker's own API is reached through the same address (see *Moonraker*
below).

## Access

* **No password** (the default): every request is answered, from the home network.
* **With a password** (Settings → Access): log in once with `POST /api/auth/login {"password": "..."}`; the answer sets
  the `klippeye_session` cookie (6 months), to send with every request. Without it: `401` with the header
  `X-KlippEye-Login: 1`.
* **Guests** (1.82): a token from the guest password only reads (printer, camera, G-code files, history); other
  requests answer `403 {"error": "guest"}`.
* **Network checks** (on by default): the service answers only when called by an IP address, the Raspberry's name or a
  home-network name (`.local`, `.lan`…), and refuses commands (POST, DELETE…) coming from pages of other sites
  (`Origin` header). Scripts that send no `Origin` header are not affected. `klippeye access host-add NAME` allows
  another name.
* Refusals have the form `{"ok": false, "error": "<code>", "message": "<words>"}`.

| Method | Path | What |
|---|---|---|
| GET | `/api/auth/status` | `{enabled, logged_in, role, guest_enabled, network_checks, allowed_hosts, min_length}` |
| POST | `/api/auth/login` | `{password}` → sets the cookie; `role` is `admin` or `guest` |
| POST | `/api/auth/logout` | this device goes out |
| POST | `/api/auth/logout_all` | every other device goes out |
| POST | `/api/auth/password` | `{current?, new}` turns the password on or changes it |
| POST | `/api/auth/disable` | `{current}` removes the password |
| POST | `/api/auth/guest` | `{current, new}` sets or changes the guest password |
| POST | `/api/auth/guest/remove` | `{current}` removes it |

## The service

| Method | Path | What |
|---|---|---|
| GET | `/api/health` | the service is up |
| GET | `/api/version` | `{release, server, frontend, git, python, data_dir, started, uptime, repair…}` |
| GET | `/api/diagnose` | the diagnostic report (text, no secrets) |
| GET/POST | `/api/update/channel` | the update channel (`stable` or `dev`) |
| GET | `/api/app/version`, `/app/KlippEye.apk` | the Android app the service can give |
| GET | `/api/logos`, `/logos/<name>` | the printer logos |

## Printer

| Method | Path | What |
|---|---|---|
| GET | `/api/status`, `/api/printer` | a summary of the printer's state (temperatures, print, position) |
| POST | `/api/gcode` | `{script: "G28"}` → Moonraker's `/printer/gcode/script` |
| GET | `/api/macros/list` | the macros with their parameters and defaults |
| POST | `/api/macros/run` | `{macro, params: {NAME: value}}` runs a macro |
| GET | `/api/printer-macros` | the macros KlippEye made (park, wipe, load, unload, lights) |
| GET | `/api/printer-macros/template?function=` | the macro proposed for a function |
| POST | `/api/printer-macros/macro` | `{name, text}` creates, replaces (`text: null` removes) one |
| POST | `/api/printer-macros/wraps` | `{names}` macros that announce a filament change |
| GET | `/api/printers/self` | this printer as another KlippEye shows it: name, logo, state, progress, temperatures |
| GET | `/api/printers/peek?host=` | another printer of the home network, through this service |
| GET | `/api/shaper/files` | the input shaper measurements in `/tmp` (1.80) |
| GET | `/api/shaper/data?name=` | one measurement: frequencies, vibrations, each shaper's response and vibrations left |
| GET/POST | `/api/calibration/selected` | the calibrations chosen in the dashboard |

## Prints

| Method | Path | What |
|---|---|---|
| GET/POST | `/api/schedule` | prints that start at a chosen time: `{entries, now}`; POST `{filename, at}` adds one |
| DELETE | `/api/schedule/<id>` | removes one |
| GET | `/api/print/snapshot` | a picture from the camera (JPEG) |

## Config files

| Method | Path | What |
|---|---|---|
| GET | `/api/config/versions?path=` | earlier versions of a config file, newest first (1.81) |
| POST | `/api/config/versions` | `{path, content}` keeps one (the editor does it before each save) |
| GET | `/api/config/versions/<id>?path=` | `{content}` of one version |
| GET | `/api/logs/list`, `/api/logs/content?file=`, `/api/logs/download?file=` | the log files of the printer |

## AI monitor

| Method | Path | What |
|---|---|---|
| GET | `/api/print/detector/status` | is it watching, the last checks |
| POST | `/api/print/detector/start`, `/stop`, `/config` | start, stop, change it |
| GET | `/api/print/last_analysis` | the last AI analysis |
| POST | `/api/print/last_analysis/answer` | `{answer: "right" \| "false" \| "ignore"}` |
| GET | `/api/print/alerts`, `/api/print/alerts/history` | the alerts, newest first |
| GET | `/api/print/alerts/image/<name>` | the picture of an alert |
| POST | `/api/print/alerts/<id>/label` | `{label: "false" \| "right" \| null}` |
| GET | `/api/print/alerts/precision` | how right the alarms were |
| GET/POST | `/api/print/analyze`, `/api/logs/analyze` | ask the AI about the picture or a log (uses the AI service) |
| GET/POST | `/api/backend/config`, POST `/api/backend/config/reset` | the monitor's thresholds |
| GET/POST | `/api/ai/config`, GET `/api/ai/models?provider=` | the AI services (keys are never returned) |
| GET/POST/DELETE | `/api/recordings…` | the pictures kept of the prints, their labels and the measurement of the monitor |
| GET/POST | `/api/camera/…` | camera calibration, overlay, snapshot, check (used by Settings → Camera) |

## Notifications

| Method | Path | What |
|---|---|---|
| GET | `/api/notifications/channels` | where the notifications go (ntfy, Firebase) |
| POST | `/api/notifications/ntfy` | `{enabled, new_topic, server, token, click}` |
| GET | `/api/notifications/app` | the topics the app listens to |
| POST | `/api/notifications/test` | sends a test through every channel |

## Home Assistant / MQTT (1.100)

| Method | Path | What |
|---|---|---|
| GET | `/api/mqtt` | the settings (never the password: `has_password`), `default_base_topic`, `running` (connected, error, lights) |
| POST | `/api/mqtt` | `{enabled, host, port, tls, username, password, password_clear, base_topic, discovery, discovery_prefix, commands, allow_cancel}`; an empty password keeps the saved one |
| POST | `/api/mqtt/test` | `{host, port, tls, username, password}` → `{ok, error}`: connects once to the broker |

On the broker (`<base>` is `klippeye/<host name>` unless set): `<base>/availability` (`online` / `offline`), `<base>/state`
(everything in one JSON), `<base>/status/<name>` (state, progress, elapsed, remaining, eta, file, layer, total_layers,
nozzle, nozzle_target, bed, bed_target, ai, ai_alarm, ai_summary), `<base>/light/<id>/state`; commands on
`<base>/command` (`pause`, `resume`, `cancel` when allowed) and `<base>/light/<id>/set` (`ON` / `OFF`). Every value is
retained; a value not known now is `None`.

## Moonraker

`/printer/…`, `/server/…`, `/machine/…` and `/webcam/…` on the KlippEye address are passed to Moonraker and to the
camera, with the same access rules as above. Moonraker's own documentation describes them:
<https://moonraker.readthedocs.io/en/latest/web_api/>. For example:

```sh
# the state of the print and the temperatures
curl "http://printer.local:8085/printer/objects/query?print_stats&extruder&heater_bed"
# a command
curl -X POST -H "Content-Type: application/json" -d '{"script": "G28"}' http://printer.local:8085/api/gcode
# with a password: log in once, keep the cookie
curl -c ke.txt -H "Content-Type: application/json" -d '{"password": "..."}' http://printer.local:8085/api/auth/login
curl -b ke.txt http://printer.local:8085/api/status
```

The routes not listed here are used by the dashboard itself and may change between releases.
