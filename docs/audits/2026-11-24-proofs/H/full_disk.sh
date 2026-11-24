#!/usr/bin/env bash
# A full SD card (timelapses, G-code: common) while `install.sh --uninstall` / `--undo` / `--channel=...` runs.
# `ulimit -f 0` stands in for "no space left": a file may be emptied, nothing may be written into it.
R="${KE_ROOT:-$(cd "$(dirname "$0")/../../../.." && pwd)}"; mkdir -p /tmp/zoneH
W=$(mktemp -d /tmp/zoneH/full.XXXX); cd "$W"
printf '[server]\nhost: 0.0.0.0\n\n[update_manager]\n\n# KlippEye: updates from the dashboard\n[update_manager klippeye]\ntype: git_repo\npath: ~/klippeye\n' > moonraker.conf
printf 'klipper_mcu\nwebcamd\ncrowsnest\nklipper\nklippeye\nklippeye-notifier\n' > moonraker.asvc
# the undo/uninstall code of moonraker.conf (install.sh lines 299-312)
body=$(sed -n '/^import re, sys$/,/^PY$/p' "$R/scripts/install.sh" | sed -n '1,/^PY$/p' | sed '$d')
( ulimit -f 0; python3 - "$W/moonraker.conf" <<<"$body" ) 2>&1 | tail -1
echo "moonraker.conf after: $(wc -c < moonraker.conf) bytes"
# the moonraker.asvc code (line 317), with the temporary folder on the same full card
( ulimit -f 0; grep -vx -e klippeye -e klippeye-notifier moonraker.asvc > asvc.tmp ; cat asvc.tmp > moonraker.asvc ) 2>&1 | tail -1
echo "moonraker.asvc after: $(wc -c < moonraker.asvc) bytes (Moonraker may now restart none of klipper, crowsnest, ...)"
