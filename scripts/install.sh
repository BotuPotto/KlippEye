#!/usr/bin/env bash
# KlippEye - installation on the Raspberry (done ONCE; it can be run again at any time, it is made not to break anything)
#
#   bash ~/klippeye/scripts/install.sh                  install or repair
#   bash ~/klippeye/scripts/install.sh --no-moonraker   do not touch Moonraker's configuration
#   bash ~/klippeye/scripts/install.sh --undo           take KlippEye off (services, commands, update manager entry)
#   bash ~/klippeye/scripts/install.sh --channel=dev    updates: every change (dev) instead of the tested releases (stable, default)
#   bash ~/klippeye/scripts/install.sh --no-ai          do not install OpenCV (the AI monitor stays off, less to download)
#   bash ~/klippeye/scripts/install.sh --no-packages    install nothing with apt (only say what is missing)
#   (the Italian options of older releases still work: --senza-moonraker, --annulla, --aiuto)
#
# What it does, in this order:
#   1. checks Python, git and the modules KlippEye needs, and installs the missing ones with apt (asking the password once):
#      python3-flask, python3-requests, python3-numpy (the backend), python3-opencv (the AI monitor), git (updates)
#   2. creates the DATA folder (~/printer_data/klippeye: settings, AI key, notifications)
#   3. installs the services "klippeye" (backend + dashboard) and "klippeye-notifier" (notifications), started at every boot;
#      if the new backend does not answer, they are taken off again
#   4. puts the commands "klippeye" and "klippeye-notifiche" in /usr/local/bin
#   5. connects the program to Moonraker's UPDATE MANAGER (moonraker.conf and moonraker.asvc): that is what makes the
#      "Update" button of the dashboard and of Mainsail/Fluidd work
#
# The code lives in one folder (this one), your things in another: updates only touch the first one.

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"

RUN_USER="$(id -un)"
SUDO="${KLIPPEYE_SUDO-sudo}"
SYSTEMCTL="${KLIPPEYE_SYSTEMCTL:-systemctl}"
UNIT_DIR="${KLIPPEYE_SYSTEMD_DIR:-/etc/systemd/system}"
BIN_DIR="${KLIPPEYE_BIN_DIR:-/usr/local/bin}"
MOONRAKER_URL="${KLIPPEYE_MOONRAKER_URL:-http://127.0.0.1:7125}"
# The printer's data folder (printer_data, printer_1_data with several printers...): the parent of Moonraker's "config"
# root, asked to Moonraker; ~/printer_data when it does not answer. KLIPPEYE_PRINTER_DATA=... chooses it by hand.
moonraker_printer_data() {
  python3 - "$MOONRAKER_URL" <<'PY' 2>/dev/null
import json, os, sys, urllib.request
try:
    roots = json.load(urllib.request.urlopen(sys.argv[1] + "/server/files/roots", timeout=3)).get("result") or []
    config = [r["path"] for r in roots if r.get("name") == "config"]
    if config:
        print(os.path.dirname(os.path.expanduser(config[0]).rstrip("/")))
except Exception:
    pass
PY
}
if [ -n "${KLIPPEYE_PRINTER_DATA:-}" ]; then PRINTER_DATA="$KLIPPEYE_PRINTER_DATA"
else
  PRINTER_DATA="$(moonraker_printer_data)"
  [ -n "$PRINTER_DATA" ] && [ -d "$PRINTER_DATA" ] || PRINTER_DATA="$HOME/printer_data"
fi
BRAIN_URL="${KLIPPEYE_BRAIN_URL:-http://127.0.0.1:8085}"
MOONRAKER_SERVICE="${KLIPPEYE_MOONRAKER_SERVICE:-moonraker}"
if [ -n "${KLIPPEYE_DATA:-}" ]; then DATA="$KLIPPEYE_DATA"
elif [ -d "$PRINTER_DATA" ]; then DATA="$PRINTER_DATA/klippeye"
else DATA="$HOME/klippeye_data"; fi

say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
good() { printf '   OK      %s\n' "$*"; }
note() { printf '           %s\n' "$*"; }
warn() { printf '   WARNING %s\n' "$*"; }
stop() { printf '\n   ERROR   %s\n\n' "$*"; exit 1; }

usage() { sed -n '2,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

MODE=install
WITH_MOONRAKER=1
WITH_AI=1        # 0: OpenCV is not installed (--no-ai)
WITH_PACKAGES=1  # 0: nothing is installed with apt (--no-packages)
CHANNEL=stable   # update channel of a new [update_manager klippeye] entry: tagged releases only
CHANNEL_GIVEN=0
for arg in "$@"; do
  case "$arg" in
    --channel=stable|--channel=dev) CHANNEL="${arg#--channel=}"; CHANNEL_GIVEN=1 ;;
    --undo|--annulla) MODE=undo ;;
    --no-moonraker|--senza-moonraker) WITH_MOONRAKER=0 ;;
    --no-ai) WITH_AI=0 ;;
    --no-packages) WITH_PACKAGES=0 ;;
    -h|--help|--aiuto) usage; exit 0 ;;
    *) stop "Unknown option: $arg   (try:  bash $0 --help)" ;;
  esac
done

sudo_run() { if [ -n "$SUDO" ]; then $SUDO "$@"; else "$@"; fi; }

RELEASE="$(tr -d '[:space:]' < "$REPO/VERSION" 2>/dev/null || true)"
RELEASE="${RELEASE:-unknown}"
say "KlippEye $RELEASE - installation on the Raspberry"
WORK_EARLY="$(mktemp "${TMPDIR:-/tmp}/klippeye-apt.XXXXXX")" || WORK_EARLY=/dev/null
trap 'rm -f "$WORK_EARLY"' EXIT

# --- 1. checks --------------------------------------------------------------------------------------------------------
step "1/6  Checking the Raspberry"
if [ "$(id -u)" = "0" ] && [ -z "${KLIPPEYE_ALLOW_ROOT:-}" ]; then
  stop "Do not run me with sudo or as root: I must run as the normal user (usually 'pi').
          Try again like this:   bash $REPO/scripts/install.sh
          (when the administrator password is needed I ask for it at the right moment)"
fi
PYTHON="${KLIPPEYE_PYTHON:-$(command -v python3 || true)}"
[ -n "$PYTHON" ] || stop "Python 3 is not installed. Install it with:  sudo apt install -y python3"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)' || stop "Python 3.7 or newer is needed (here there is $("$PYTHON" --version 2>&1))."
good "$("$PYTHON" --version 2>&1) ($PYTHON)"
case "$REPO$DATA" in *" "*) stop "Folder names must not contain spaces ($REPO, $DATA)." ;; esac
[ -f "$REPO/backend/klippeye_backend.py" ] || stop "$REPO/backend/klippeye_backend.py not found: this does not look like the KlippEye folder."
# What KlippEye needs, as Debian / Raspberry Pi OS packages (the same names on MainsailOS, Bullseye, Bookworm, Trixie):
#   the backend: flask, requests, numpy (1.23.0: the camera calibration is numpy-only and part of the backend)
#   the AI monitor: OpenCV (python3-opencv) - left out with --no-ai
#   updates and self-repair: git
missing_packages() {
  local list=""
  command -v git >/dev/null 2>&1 || list="$list git"
  "$PYTHON" -c 'import flask' 2>/dev/null || list="$list python3-flask"
  "$PYTHON" -c 'import requests' 2>/dev/null || list="$list python3-requests"
  "$PYTHON" -c 'import numpy' 2>/dev/null || list="$list python3-numpy"
  if [ "$WITH_AI" = 1 ]; then "$PYTHON" -c 'import cv2' 2>/dev/null || list="$list python3-opencv"; fi
  printf '%s' "${list# }"
}
APT="${KLIPPEYE_APT:-apt-get}"
# apt installs the modules for the system's python3: with another Python (a virtual environment) it would not help
system_python() { [ -n "${KLIPPEYE_APT_ANY_PYTHON:-}" ] || case "$(readlink -f "$PYTHON")" in /usr/bin/*) return 0 ;; *) return 1 ;; esac; }
NEEDED="$(missing_packages)"
if [ -n "$NEEDED" ] && [ "$MODE" = install ]; then
  say "   ...     KlippEye needs: $NEEDED"
  if [ "$WITH_PACKAGES" = 1 ] && command -v "$APT" >/dev/null 2>&1 && system_python; then
    note "Installing them with apt (the administrator password may be asked; it takes a few minutes with OpenCV)."
    if sudo_run env DEBIAN_FRONTEND=noninteractive "$APT" update >"$WORK_EARLY" 2>&1 \
       && sudo_run env DEBIAN_FRONTEND=noninteractive "$APT" install -y $NEEDED >>"$WORK_EARLY" 2>&1; then
      good "Installed: $NEEDED"
    else
      warn "apt could not install everything. Its last lines:"
      tail -n 6 "$WORK_EARLY" | sed 's/^/           /'
    fi
  elif [ "$WITH_PACKAGES" = 1 ] && ! system_python; then
    note "Python is $PYTHON, not the system's: install them in it (pip install flask requests numpy opencv-python-headless)."
  else
    note "Install them with:   sudo apt install -y $NEEDED"
  fi
fi
command -v git >/dev/null 2>&1 && good "git" || warn "git is missing: without it updates and self-repair do not work. Install it with:  sudo apt install -y git"
MISSING=""
for module in flask requests numpy; do   # flask_cors is optional since 1.2.0 (development only)
  "$PYTHON" -c "import $module" 2>/dev/null || MISSING="$MISSING $module"
done
if [ -n "$MISSING" ]; then
  warn "The backend is missing these Python modules:$MISSING"
  note "Install them with:   sudo apt install -y python3-flask python3-requests python3-numpy"
  note "then run this command again."
  if [ -z "${KLIPPEYE_IGNORE_MISSING:-}" ]; then stop "Without those modules the backend does not start."; fi
else
  good "Backend modules: flask $("$PYTHON" -c 'import importlib.metadata as m; print(m.version("flask"))' 2>/dev/null || "$PYTHON" -c 'import flask; print(flask.__version__)' 2>/dev/null), requests, numpy"
fi
if "$PYTHON" -c 'import cv2' 2>/dev/null; then
  good "OpenCV $("$PYTHON" -c 'import cv2; print(cv2.__version__)' 2>/dev/null) (for the AI monitor)"
elif [ "$WITH_AI" = 0 ]; then
  note "OpenCV not installed (--no-ai): the AI monitor stays off. To add it later run this command again without --no-ai."
else
  warn "OpenCV is missing: the backend starts anyway, but the AI monitor cannot look at the camera."
  note "Install it with:   sudo apt install -y python3-opencv"
fi
[ -f "$REPO/frontend/klippeye_frontend.html" ] || warn "$REPO/frontend/klippeye_frontend.html is missing: the backend starts, but the dashboard page does not open."

WORK="$(mktemp -d "${TMPDIR:-/tmp}/klippeye-install.XXXXXX")" || stop "Cannot create a temporary folder."
trap 'rm -rf "$WORK"; rm -f "$WORK_EARLY"' EXIT

# --- shared functions --------------------------------------------------------------------------------------------------
BK=""
bk_dir() {
  if [ -z "$BK" ]; then BK="$DATA/backup/$(date +%Y%m%d-%H%M%S)"; mkdir -p "$BK"; fi
}
backup_file() {  # file_to_save name_in_the_backup
  bk_dir
  mkdir -p "$(dirname "$BK/$2")"
  cp -p "$1" "$BK/$2" 2>/dev/null || sudo_run cp -p "$1" "$BK/$2"
}
brain_release() {  # max_seconds -> prints the release when the backend answers within that time
  "$PYTHON" - "$BRAIN_URL/api/version" "$1" <<'PY'
import json, sys, time, urllib.request
end = time.time() + float(sys.argv[2])
while True:
    try:
        d = json.loads(urllib.request.urlopen(sys.argv[1], timeout=3).read().decode("utf-8", "replace"))
        if isinstance(d, dict) and d.get("release"):
            print(d["release"]); sys.exit(0)
    except Exception:
        pass
    if time.time() >= end:
        sys.exit(1)
    time.sleep(1)
PY
}
is_printing() {  # 0 when Moonraker says it is printing (or paused)
  "$PYTHON" - "$MOONRAKER_URL/printer/objects/query?print_stats=state" <<'PY'
import json, sys, urllib.request
try:
    d = json.loads(urllib.request.urlopen(sys.argv[1], timeout=4).read().decode("utf-8", "replace"))
    state = d["result"]["status"]["print_stats"]["state"]
    sys.exit(0 if state in ("printing", "paused") else 1)
except Exception:
    sys.exit(1)
PY
}
unit_active() { sudo_run "$SYSTEMCTL" is-active "$1" >/dev/null 2>&1; }

render_unit() {  # template destination (@UTENTE@, @CODICE@, @DATI@: the placeholders of the templates before 1.8.0)
  sed -e "s|@USER@|$RUN_USER|g" -e "s|@CODE@|$REPO|g" -e "s|@DATA@|$DATA|g" -e "s|@PYTHON@|$PYTHON|g" \
      -e "s|@UTENTE@|$RUN_USER|g" -e "s|@CODICE@|$REPO|g" -e "s|@DATI@|$DATA|g" "$1" > "$2"
}
# the first line of the service files this script writes ("GESTITO-DA-KLIPPEYE" before 1.8.0)
OURS='MANAGED-BY-KLIPPEYE\|GESTITO-DA-KLIPPEYE'
install_unit() {  # name (without .service): 0 = installed or changed, 1 = already the same
  local name="$1" dest="$UNIT_DIR/$1.service" tmp="$WORK/$1.service"
  render_unit "$REPO/systemd/$name.service" "$tmp"
  if [ -f "$dest" ] && cmp -s "$tmp" "$dest"; then return 1; fi
  if [ -f "$dest" ] && ! grep -q "$OURS" "$dest"; then backup_file "$dest" "units/$name.service"; fi
  sudo_run install -m 644 "$tmp" "$dest" || stop "Cannot write $dest (is the administrator password needed?)."
  return 0
}
stop_new_units() {
  local name
  for name in klippeye klippeye-notifier; do
    if [ -f "$UNIT_DIR/$name.service" ] && grep -q "$OURS" "$UNIT_DIR/$name.service"; then
      sudo_run "$SYSTEMCTL" disable --now "$name" >/dev/null 2>&1
      sudo_run rm -f "$UNIT_DIR/$name.service"
    fi
  done
  sudo_run "$SYSTEMCTL" daemon-reload
}

install_command() {  # name: writes /usr/local/bin/<name>, which runs the script inside the program folder
  local name="$1" tmp="$WORK/cmd-$1"
  printf '#!/bin/sh\n# written by %s/scripts/install.sh\nexec bash "%s/scripts/%s" "$@"\n' "$REPO" "$REPO" "$name" > "$tmp"
  if [ -f "$BIN_DIR/$name" ] && cmp -s "$tmp" "$BIN_DIR/$name"; then return 0; fi
  sudo_run install -m 755 "$tmp" "$BIN_DIR/$name" || { warn "Cannot write $BIN_DIR/$name"; return 1; }
}

# ====================================================================================================================
#  --undo
# ====================================================================================================================
if [ "$MODE" = "undo" ]; then
  step "Undoing KlippEye $RELEASE"
  stop_new_units
  good "Services klippeye and klippeye-notifier stopped and removed"
  for name in klippeye klippeye-notifiche; do
    if [ -f "$BIN_DIR/$name" ] && grep -q "$REPO/scripts" "$BIN_DIR/$name" 2>/dev/null; then sudo_run rm -f "$BIN_DIR/$name"; fi
  done
  good "Commands $BIN_DIR/klippeye and klippeye-notifiche removed"
  if [ "$WITH_MOONRAKER" = 1 ]; then
    conf="$PRINTER_DATA/config/moonraker.conf"; asvc="$PRINTER_DATA/moonraker.asvc"
    if [ -f "$conf" ] && grep -Eq '^\[update_manager[[:space:]]+klippeye\]' "$conf"; then
      backup_file "$conf" moonraker.conf
      "$PYTHON" - "$conf" <<'PY'
import re, sys
p = sys.argv[1]
lines = open(p, encoding="utf-8").read().split("\n")
out, skip = [], False
for line in lines:
    if re.match(r"^\[", line):
        skip = bool(re.match(r"^\[update_manager\s+klippeye\]\s*$", line))
    if not skip:
        out.append(line)
text = "\n".join(out).rstrip("\n") + "\n"
text = re.sub(r"\n\n+# KlippEye: (updates from the dashboard|aggiornamenti dalla dashboard)[^\n]*\n*$", "\n", text)
open(p, "w", encoding="utf-8").write(text)
PY
      good "Entry [update_manager klippeye] removed from moonraker.conf"
    fi
    if [ -f "$asvc" ]; then
      backup_file "$asvc" moonraker.asvc
      grep -vx -e klippeye -e klippeye-notifier "$asvc" > "$WORK/asvc" ; cat "$WORK/asvc" > "$asvc"
      good "klippeye and klippeye-notifier removed from moonraker.asvc"
    fi
    if is_printing; then
      warn "Printing: Moonraker is not restarted. Restart it when the print ends (Restart menu of the dashboard) to make the entry disappear."
    else
      sudo_run "$SYSTEMCTL" restart "$MOONRAKER_SERVICE" && good "Moonraker restarted"
    fi
  fi
  say ""
  say "Done. The program folder ($REPO) and the data folder ($DATA) stayed where they are:"
  say "delete them by hand if you no longer need them."
  exit 0
fi

# ====================================================================================================================
#  installation
# ====================================================================================================================

# --- 2. data and settings ----------------------------------------------------------------------------------------------
step "2/6  Data folder: $DATA"
mkdir -p "$DATA" || stop "Cannot create $DATA"
chmod 700 "$DATA"
good "Settings, AI key and notifications stay here. Updates do not touch this folder."

if [ -d "$REPO/.git" ]; then
  # Files uploaded through the GitHub website have no "executable" permission: without this line git would see them as
  # "changed" as soon as they are made executable, and Moonraker's update manager would refuse to update.
  git -C "$REPO" config core.fileMode false 2>/dev/null
fi

if [ -f "$DATA/ai.json" ]; then
  chmod 600 "$DATA/ai.json"
  good "AI key: already in the data folder"
else
  note "AI key: none yet (it is entered from the dashboard)"
fi

if [ -f "$DATA/notifier.json" ]; then
  good "Notifications: configuration already in the data folder"
else
  note "Notifications: not set up yet (from the dashboard: Settings -> Notifications -> Turn on notifications with ntfy)"
fi

# --- 3. services -------------------------------------------------------------------------------------------------------
step "3/6  Services (started by themselves at every boot)"
for need in "$REPO/systemd/klippeye.service" "$REPO/systemd/klippeye-notifier.service"; do
  [ -f "$need" ] || stop "The template $need is missing"
done
[ -d "$UNIT_DIR" ] || stop "The system services folder ($UNIT_DIR) was not found."

# 1.20.0: the notification service always runs. With no channel set up it sends nothing, but it does the automatic
# pause / cancel of the AI monitor, and it starts sending as soon as ntfy is turned on in the dashboard (no restart needed).
NOTIFIER_ON=1
BRAIN_CHANGED=0
if install_unit klippeye; then BRAIN_CHANGED=1; fi
# the self-repair drop-in (klippeye.service.d/repair.conf, ripara.conf before 1.3.0, added by the backend) is no longer needed:
# the line is in the service file itself
if [ -f "$UNIT_DIR/klippeye.service.d/ripara.conf" ] || [ -f "$UNIT_DIR/klippeye.service.d/repair.conf" ]; then
  sudo_run rm -f "$UNIT_DIR/klippeye.service.d/ripara.conf" "$UNIT_DIR/klippeye.service.d/repair.conf"; sudo_run rmdir "$UNIT_DIR/klippeye.service.d" 2>/dev/null; BRAIN_CHANGED=1
fi
NOTIFIER_CHANGED=0
if [ "$NOTIFIER_ON" = 1 ]; then
  if install_unit klippeye-notifier; then NOTIFIER_CHANGED=1; fi
fi
sudo_run "$SYSTEMCTL" daemon-reload || stop "systemctl daemon-reload failed."
sudo_run "$SYSTEMCTL" enable klippeye >/dev/null 2>&1
[ "$NOTIFIER_ON" = 1 ] && sudo_run "$SYSTEMCTL" enable klippeye-notifier >/dev/null 2>&1

if [ "$BRAIN_CHANGED" = 1 ] || ! unit_active klippeye; then
  sudo_run "$SYSTEMCTL" restart klippeye || warn "systemctl restart klippeye gave an error"
  printf '   ...     waiting for the backend to answer (up to 40 seconds)\n'
  if NEWREL="$(brain_release 40)"; then
    good "The backend answers: release $NEWREL"
  else
    printf '\n   ERROR   The new backend does not answer at %s.\n' "$BRAIN_URL"
    note "Last lines of its log:"
    (journalctl -u klippeye -n 12 --no-pager 2>/dev/null || sudo_run journalctl -u klippeye -n 12 --no-pager 2>/dev/null) | sed 's/^/           /'
    stop_new_units
    stop "Installation stopped. If port 8085 is taken by another program, stop it and run this again. If a Python module is missing, see above."
  fi
else
  good "Service klippeye already in order"
fi

if [ "$NOTIFIER_ON" = 1 ]; then
  if [ "$NOTIFIER_CHANGED" = 1 ] || ! unit_active klippeye-notifier; then
    sudo_run "$SYSTEMCTL" restart klippeye-notifier || warn "systemctl restart klippeye-notifier gave an error"
  fi
  good "Service klippeye-notifier on"
  if "$PYTHON" "$REPO/notifier/klippeye_notifier.py" --config "$DATA/notifier.json" --check >"$WORK/check.out" 2>&1; then
    good "Notification check passed"
  else
    warn "The notification check reports something (see below). The backend and the dashboard work anyway."
    sed 's/^/           /' "$WORK/check.out" | tail -n 8
  fi
fi

# --- 4. commands -------------------------------------------------------------------------------------------------------
step "4/6  Terminal commands"
if install_command klippeye && install_command klippeye-notifiche; then
  good "Written $BIN_DIR/klippeye and $BIN_DIR/klippeye-notifiche   (try:  klippeye status)"
fi

# --- 5. Moonraker --------------------------------------------------------------------------------------------------------
step "5/6  Updates from the dashboard (Moonraker's update manager)"
MR_RESTART=0
if [ "$WITH_MOONRAKER" = 0 ]; then
  note "Skipped (--no-moonraker)."
else
  CONF="$PRINTER_DATA/config/moonraker.conf"
  ASVC="$PRINTER_DATA/moonraker.asvc"
  ORIGIN=""; BRANCH=""
  if [ -d "$REPO/.git" ]; then
    ORIGIN="$(git -C "$REPO" remote get-url origin 2>/dev/null || true)"
    BRANCH="$(git -C "$REPO" symbolic-ref --short HEAD 2>/dev/null || true)"
  fi
  if [ ! -d "$REPO/.git" ]; then
    warn "$REPO is not a git repository (downloaded as a zip?). Without it the Update button cannot work."
    note "Install again with:   git clone https://github.com/BotuPotto/KlippEye.git ~/klippeye"
  elif [ -z "$ORIGIN" ]; then
    warn "The repository has no 'origin' (a GitHub address to update from): Moonraker's configuration is skipped."
  else
    [ -n "$BRANCH" ] || { BRANCH=main; warn "The current branch is not recognised: using 'main'."; }
    if [ ! -f "$CONF" ]; then
      warn "$CONF not found: Moonraker's configuration is skipped (if yours is elsewhere: KLIPPEYE_PRINTER_DATA=... bash $0)."
    else
      if grep -Eq '^\[update_manager[[:space:]]+klippeye\][[:space:]]*$' "$CONF"; then
        good "moonraker.conf already has the entry [update_manager klippeye]"
        if [ "$CHANNEL_GIVEN" = 1 ]; then
          backup_file "$CONF" moonraker.conf
          if "$PYTHON" - "$CONF" "$CHANNEL" <<'PY'
import re, sys
path, channel = sys.argv[1], sys.argv[2]
lines = open(path, encoding="utf-8").read().split("\n")
start = next(i for i, l in enumerate(lines) if re.match(r"^\[update_manager\s+klippeye\]\s*$", l))
end = next((i for i in range(start + 1, len(lines)) if re.match(r"^\s*\[", lines[i])), len(lines))
for i in range(start + 1, end):
    if re.match(r"^\s*channel\s*[:=]", lines[i]):
        changed = lines[i].split(":", 1)[-1].strip() != channel
        lines[i] = "channel: " + channel
        break
else:
    at = next((i + 1 for i in range(start + 1, end) if re.match(r"^\s*type\s*[:=]", lines[i])), start + 1)
    lines.insert(at, "channel: " + channel)
    changed = True
open(path, "w", encoding="utf-8").write("\n".join(lines))
sys.exit(0 if changed else 3)
PY
          then good "Update channel set to '$CHANNEL'"; MR_RESTART=1
          else good "Update channel already '$CHANNEL'"; fi
        fi
      else
        backup_file "$CONF" moonraker.conf
        {
          printf '\n'
          if ! grep -Eq '^\[update_manager[[:space:]]*\][[:space:]]*$' "$CONF"; then
            printf '[update_manager]\n\n'
          fi
          printf '# KlippEye: updates from the dashboard (Settings -> Updates) and from Mainsail/Fluidd. Written by scripts/install.sh.\n'
          printf '[update_manager klippeye]\ntype: git_repo\npath: %s\norigin: %s\nprimary_branch: %s\nchannel: %s\nmanaged_services: klippeye\ninfo_tags:\n  desc=KlippEye: backend, dashboard and notifications\n' "$REPO" "$ORIGIN" "$BRANCH" "$CHANNEL"
        } >> "$CONF"
        good "Entry [update_manager klippeye] added to moonraker.conf"
        MR_RESTART=1
      fi
    fi
    if [ ! -f "$ASVC" ]; then
      warn "$ASVC not found (the list of services Moonraker may restart): without it Moonraker does not restart 'klippeye' after an update."
    else
      WANT="klippeye"; [ "$NOTIFIER_ON" = 1 ] && WANT="klippeye klippeye-notifier"
      ADDED=""
      for s in $WANT; do
        if ! grep -qx "$s" "$ASVC"; then
          if [ -z "$ADDED" ]; then backup_file "$ASVC" moonraker.asvc; fi
          if [ -s "$ASVC" ] && [ "$(tail -c1 "$ASVC" | wc -l)" -eq 0 ]; then printf '\n' >> "$ASVC"; fi
          printf '%s\n' "$s" >> "$ASVC"; ADDED="$ADDED $s"
        fi
      done
      if [ -n "$ADDED" ]; then good "Added to moonraker.asvc:$ADDED"; MR_RESTART=1; else good "moonraker.asvc in order"; fi
    fi
  fi

  if [ "$MR_RESTART" = 1 ]; then
    if is_printing; then
      warn "Printing: Moonraker is not restarted now. When the print ends restart it from the Restart menu of the dashboard (or Mainsail)"
      note "and only then will the Update button work."
    else
      sudo_run "$SYSTEMCTL" restart "$MOONRAKER_SERVICE" || warn "Could not restart Moonraker: restart it from the Restart menu."
      printf '   ...     waiting for Moonraker\n'
      "$PYTHON" - "$MOONRAKER_URL/server/info" <<'PY' || warn "Moonraker has not answered yet: it may take a minute."
import sys, time, urllib.request
end = time.time() + 60
while time.time() < end:
    try:
        urllib.request.urlopen(sys.argv[1], timeout=3).read()
        sys.exit(0)
    except Exception:
        time.sleep(1)
sys.exit(1)
PY
      good "Moonraker restarted"
    fi
  fi

  # does Moonraker see KlippEye?
  "$PYTHON" - "$MOONRAKER_URL/machine/update/status?refresh=false" <<'PY'
import json, sys, urllib.request
try:
    d = json.loads(urllib.request.urlopen(sys.argv[1], timeout=20).read().decode("utf-8", "replace"))
    info = d["result"]["version_info"].get("klippeye")
except Exception as e:
    print("   WARNING Cannot ask Moonraker whether it sees KlippEye (%s)." % e); sys.exit(0)
if not info:
    print("   WARNING Moonraker does not list KlippEye among the programs it updates yet: restart it (Restart menu) and look again shortly.")
elif info.get("is_valid") is False or info.get("is_dirty"):
    print("   WARNING Moonraker sees KlippEye but marks it as not updatable: %s" % "; ".join(info.get("warnings") or ["files changed by hand"]))
else:
    print("   OK      Moonraker sees KlippEye (version %s): the Update button works" % info.get("version", "?"))
PY
fi

# --- 6. end --------------------------------------------------------------------------------------------------------------
step "6/6  Done"
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
say "   KlippEye $RELEASE is installed."
say "   Dashboard:   http://${IP:-<address of the Raspberry>}:8085"
say "   Updates: in the dashboard open Settings -> Updates -> Check -> Update KlippEye."
say "   From the terminal:  klippeye status"
[ -n "$BK" ] && say "   Backup copies of what was changed: $BK"
exit 0
