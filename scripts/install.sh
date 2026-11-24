#!/usr/bin/env bash
# KlippEye - installation on the Raspberry (done ONCE; it can be run again at any time, it is made not to break anything)
#
#   bash ~/klippeye/scripts/install.sh                  install or repair
#   bash ~/klippeye/scripts/install.sh --no-moonraker   do not touch Moonraker's configuration
#   bash ~/klippeye/scripts/install.sh --uninstall      take KlippEye off this Raspberry, its folders included (asks first;
#                                                       --yes: no question, --keep-data: keep the data folder)
#   bash ~/klippeye/scripts/install.sh --undo           take KlippEye off but leave its folders (services, commands, update manager entry)
#   bash ~/klippeye/scripts/install.sh --channel=dev    updates: every change (dev) instead of the tested releases (stable, default)
#   bash ~/klippeye/scripts/install.sh --no-ai          do not install OpenCV (the AI monitor stays off, less to download)
#   bash ~/klippeye/scripts/install.sh --no-packages    install nothing with apt (only say what is missing)
#   bash ~/klippeye/scripts/install.sh --web            KlippEye is the Raspberry's main page (http://IP, port 80 of nginx)
#   bash ~/klippeye/scripts/install.sh --no-web         KlippEye is a second page (http://IP:8085); port 80 goes back to the page it had
#   (with neither, the installer asks; with no terminal it keeps the current choice, the main page on a first install)
#   (the Italian options of older releases still work: --senza-moonraker, --annulla, --aiuto)
#
# What it does, in this order:
#   1. checks Python, git and the modules KlippEye needs, and installs the missing ones with apt (asking the password once):
#      python3-flask, python3-waitress, python3-requests, python3-numpy (the backend), python3-opencv (the AI monitor),
#      git (updates)
#   2. creates the DATA folder (~/printer_data/klippeye: settings, AI key, notifications)
#   3. installs the services "klippeye" (backend + dashboard) and "klippeye-notifier" (notifications), started at every boot;
#      if the new backend does not answer, they are taken off again
#   4. puts the commands "klippeye" and "klippeye-notifiche" in /usr/local/bin
#   5. connects the program to Moonraker's UPDATE MANAGER (moonraker.conf and moonraker.asvc): that is what makes the
#      "Update" button of the dashboard and Moonraker's update manager work
#   6. asks whether KlippEye is the Raspberry's main page, http://<raspberry> without a port (nginx, scripts/web_front.py):
#      if so, the page that was there moves to port 81 (or the next free one); --no-web or `klippeye web restore` puts it back
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
BACKEND_URL="${KLIPPEYE_BACKEND_URL:-${KLIPPEYE_BRAIN_URL:-http://127.0.0.1:8085}}"   # KLIPPEYE_BRAIN_URL: its name before 1.118
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

usage() { sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

MODE=install
WITH_MOONRAKER=1
WITH_AI=1        # 0: OpenCV is not installed (--no-ai)
WITH_PACKAGES=1  # 0: nothing is installed with apt (--no-packages)
WITH_WEB="${KLIPPEYE_WEB:-1}"  # 1: KlippEye at port 80 (--web), 0: only at port 8085 (--no-web)
WEB_GIVEN=0; [ -n "${KLIPPEYE_WEB:-}" ] && WEB_GIVEN=1   # 1.137.0: with neither option the installer asks (step 6)
CHANNEL=stable   # update channel of a new [update_manager klippeye] entry: tagged releases only
CHANNEL_GIVEN=0
YES=0; KEEP_DATA=0   # 1.137.0: --uninstall --yes / --keep-data
for arg in "$@"; do
  case "$arg" in
    --channel=stable|--channel=dev) CHANNEL="${arg#--channel=}"; CHANNEL_GIVEN=1 ;;
    --undo|--annulla) MODE=undo ;;
    --uninstall) MODE=uninstall ;;
    --yes) YES=1 ;;
    --keep-data) KEEP_DATA=1 ;;
    --no-moonraker|--senza-moonraker) WITH_MOONRAKER=0 ;;
    --no-ai) WITH_AI=0 ;;
    --no-packages) WITH_PACKAGES=0 ;;
    --web) WITH_WEB=1; WEB_GIVEN=1 ;;
    --no-web) WITH_WEB=0; WEB_GIVEN=1 ;;
    -h|--help|--aiuto) usage; exit 0 ;;
    *) stop "Unknown option: $arg   (try:  bash $0 --help)" ;;
  esac
done
if [ "$MODE" != uninstall ] && { [ "$YES" = 1 ] || [ "$KEEP_DATA" = 1 ]; }; then
  stop "--yes and --keep-data go with --uninstall   (try:  bash $0 --help)"
fi

# 1.137.0: --uninstall deletes the program folder, this script's own folder: bash reads a script as it runs, so run a
# copy from the temporary folder. The copy unlinks itself at once (bash keeps reading it through its open file).
# KLIPPEYE_UNINSTALL_FROM counts only in that copy (its name is klippeye-uninstall.*), never in the real script.
if [ "$MODE" = uninstall ]; then
  case "$(basename "${BASH_SOURCE[0]}")" in
    klippeye-uninstall.*) [ -n "${KLIPPEYE_UNINSTALL_FROM:-}" ] || stop "KLIPPEYE_UNINSTALL_FROM is missing." ;;
    *)
      copy="$(mktemp "${TMPDIR:-/tmp}/klippeye-uninstall.XXXXXX")" && cp "${BASH_SOURCE[0]}" "$copy" || stop "Cannot copy myself to a temporary file."
      KLIPPEYE_UNINSTALL_FROM="$REPO" exec bash "$copy" "$@" ;;
  esac
  rm -f "${BASH_SOURCE[0]}"
  REPO="$KLIPPEYE_UNINSTALL_FROM"; HERE="$REPO/scripts"
  cd "$HOME" 2>/dev/null || cd /
fi

FIRST_INSTALL=1; [ -f "$UNIT_DIR/klippeye.service" ] && FIRST_INSTALL=0   # 1.137.0: decides the default of step 6

sudo_run() { if [ -n "$SUDO" ]; then $SUDO "$@"; else "$@"; fi; }

RELEASE="$(tr -d '[:space:]' < "$REPO/VERSION" 2>/dev/null || true)"
RELEASE="${RELEASE:-unknown}"
if [ "$MODE" = install ]; then say "KlippEye $RELEASE - installation on the Raspberry"; else say "KlippEye $RELEASE - taking KlippEye off the Raspberry"; fi
WORK_EARLY="$(mktemp "${TMPDIR:-/tmp}/klippeye-apt.XXXXXX")" || WORK_EARLY=/dev/null
trap 'rm -f "$WORK_EARLY"' EXIT

# --- 1. checks --------------------------------------------------------------------------------------------------------
if [ "$MODE" = install ]; then step "1/7  Checking the Raspberry"; else step "Checking the Raspberry"; fi
if [ "$(id -u)" = "0" ] && [ -z "${KLIPPEYE_ALLOW_ROOT:-}" ]; then
  stop "Do not run me with sudo or as root: I must run as the normal user (usually 'pi').
          Try again like this:   bash $REPO/scripts/install.sh
          (when the administrator password is needed I ask for it at the right moment)"
fi
PYTHON="${KLIPPEYE_PYTHON:-$(command -v python3 || true)}"
[ -n "$PYTHON" ] || stop "Python 3 is not installed. Install it with:  sudo apt install -y python3"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)' || stop "Python 3.7 or newer is needed (here there is $("$PYTHON" --version 2>&1))."
good "$("$PYTHON" --version 2>&1) ($PYTHON)"
# 1.137.0: the checks below are for installing; a broken install must still come off (--undo, --uninstall)
if [ "$MODE" = install ]; then
case "$REPO$DATA" in *" "*) stop "Folder names must not contain spaces ($REPO, $DATA)." ;; esac
[ -f "$REPO/backend/klippeye_backend.py" ] || stop "$REPO/backend/klippeye_backend.py not found: this does not look like the KlippEye folder."
# What KlippEye needs, as Debian / Raspberry Pi OS packages (the same names on Bullseye, Bookworm and Trixie, and on the printer images built on them):
#   the backend: flask, requests, numpy (1.23.0: the camera calibration is numpy-only and part of the backend),
#   waitress (1.74: the web server made to run for months; without it Flask's own server is used)
#   the AI monitor: OpenCV (python3-opencv) - left out with --no-ai
#   updates and self-repair: git
missing_packages() {
  local list=""
  command -v git >/dev/null 2>&1 || list="$list git"
  "$PYTHON" -c 'import flask' 2>/dev/null || list="$list python3-flask"
  "$PYTHON" -c 'import waitress' 2>/dev/null || list="$list python3-waitress"
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
    note "Python is $PYTHON, not the system's: install them in it (pip install flask waitress requests numpy opencv-python-headless)."
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
fi

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
backend_release() {  # max_seconds -> prints the release when the backend answers within that time
  "$PYTHON" - "$BACKEND_URL/api/version" "$1" <<'PY'
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
is_printing() {  # 0 when Moonraker says it is printing (or paused), or when it does not answer in time
  "$PYTHON" - "$MOONRAKER_URL/printer/objects/query?print_stats=state" <<'PY'
import json, sys, urllib.error, urllib.request
try:
    d = json.loads(urllib.request.urlopen(sys.argv[1], timeout=4).read().decode("utf-8", "replace"))
    state = d["result"]["status"]["print_stats"]["state"]
    sys.exit(0 if state in ("printing", "paused") else 1)
except Exception as e:
    # 1.142.0: Moonraker down or Klipper not ready (an error answer): nothing prints. A slow or unreadable answer is
    # unknown, and unknown counts as printing: a busy Pi must not get Moonraker restarted in the middle of a print.
    sys.exit(1 if isinstance(e, urllib.error.HTTPError) or isinstance(getattr(e, "reason", e), ConnectionError) else 0)
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
  # 1.142.0: the data folder of the services (the unit's KLIPPEYE_DATA) goes with the command: it cannot guess another one
  printf '#!/bin/sh\n# written by %s/scripts/install.sh\nKLIPPEYE_DATA="%s" exec bash "%s/scripts/%s" "$@"\n' "$REPO" "$DATA" "$REPO" "$name" > "$tmp"
  if [ -f "$BIN_DIR/$name" ] && cmp -s "$tmp" "$BIN_DIR/$name"; then return 0; fi
  sudo_run install -m 755 "$tmp" "$BIN_DIR/$name" || { warn "Cannot write $BIN_DIR/$name"; return 1; }
}

# ====================================================================================================================
#  --undo
# ====================================================================================================================
if [ "$MODE" = "undo" ] || [ "$MODE" = "uninstall" ]; then
  if [ "$MODE" = undo ]; then step "Undoing KlippEye $RELEASE"; else step "Taking KlippEye $RELEASE off"; fi
  WEB_FAILED=0
  stop_new_units
  good "Services klippeye and klippeye-notifier stopped and removed"
  for name in klippeye klippeye-notifiche; do
    if [ -f "$BIN_DIR/$name" ] && grep -q "$REPO/scripts" "$BIN_DIR/$name" 2>/dev/null; then sudo_run rm -f "$BIN_DIR/$name"; fi
  done
  good "Commands $BIN_DIR/klippeye and klippeye-notifiche removed"
  if [ -f "${KLIPPEYE_NGINX_DIR:-/etc/nginx}/sites-available/klippeye" ] || [ -f "${KLIPPEYE_NGINX_DIR:-/etc/nginx}/conf.d/klippeye.conf" ]; then
    if out="$(sudo_run "$PYTHON" "$REPO/scripts/web_front.py" restore 2>&1)"; then good "The Raspberry's own address: $out"; else warn "$out"; WEB_FAILED=1; fi
  fi
  if [ "$WITH_MOONRAKER" = 1 ]; then
    conf="$PRINTER_DATA/config/moonraker.conf"; asvc="$PRINTER_DATA/moonraker.asvc"
    if [ -f "$conf" ] && grep -Eq '^\[update_manager[[:space:]]+klippeye\]' "$conf"; then
      backup_file "$conf" moonraker.conf
      if "$PYTHON" - "$conf" <<'PY'
import os, re, shutil, sys
p = os.path.realpath(sys.argv[1])
lines = open(p, encoding="utf-8").read().split("\n")
out, skip = [], False
for line in lines:
    if re.match(r"^\[", line):
        skip = bool(re.match(r"^\[update_manager\s+klippeye\]\s*$", line))
    if not skip:
        out.append(line)
text = "\n".join(out).rstrip("\n") + "\n"
text = re.sub(r"\n\n+# KlippEye: (updates from the dashboard|aggiornamenti dalla dashboard)[^\n]*\n*$", "\n", text)
# 1.142.0: a new file next to it, then replace: a full card leaves the old file whole, never an empty one
tmp = p + ".klippeye-tmp"
try:
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    shutil.copymode(p, tmp)
    os.replace(tmp, p)
except OSError:
    if os.path.exists(tmp):
        os.remove(tmp)
    sys.exit(1)
PY
      then good "Entry [update_manager klippeye] removed from moonraker.conf"
      else warn "Cannot write $conf (disk full?): it stays as it was, with the entry."; fi
    fi
    if [ -f "$asvc" ]; then
      backup_file "$asvc" moonraker.asvc
      real_asvc="$(readlink -f "$asvc")"; tmp_asvc="$real_asvc.klippeye-tmp"
      # grep exits 1 when no line is left (fine), 2 or more when it failed; a new file next to it, then replace (1.142.0)
      if cp -p "$real_asvc" "$tmp_asvc" && { grep -vx -e klippeye -e klippeye-notifier "$real_asvc" > "$tmp_asvc"; [ $? -le 1 ]; } && mv -f "$tmp_asvc" "$real_asvc"; then
        good "klippeye and klippeye-notifier removed from moonraker.asvc"
      else
        rm -f "$tmp_asvc"; warn "Cannot write $asvc (disk full?): it stays as it was, with the two names."
      fi
    fi
    if is_printing; then
      warn "Printing: Moonraker is not restarted. Restart it when the print ends (Restart menu of the dashboard) to make the entry disappear."
    else
      sudo_run "$SYSTEMCTL" restart "$MOONRAKER_SERVICE" && good "Moonraker restarted"
    fi
  else
    note "--no-moonraker: the entry [update_manager klippeye] stays in moonraker.conf; remove it by hand if you want."
  fi
  if [ "$MODE" = undo ]; then
    say ""
    say "Done. The program folder ($REPO) and the data folder ($DATA) stayed where they are:"
    say "delete them by hand if you no longer need them, or run:  bash $REPO/scripts/install.sh --uninstall"
    exit 0
  fi
  # 1.137.0: the printer functions' macros (backend/printer_macros.py): klippeye_macros.cfg next to printer.cfg and its
  # include. Klipper is never restarted here; while printing both stay (Klipper reads them only at its next start).
  step "Printer functions (klippeye_macros.cfg)"
  cfg_dir="$PRINTER_DATA/config"; printer_cfg="$cfg_dir/printer.cfg"; macros_cfg="$cfg_dir/klippeye_macros.cfg"
  include_re='^[[:space:]]*\[include[[:space:]]+klippeye_macros\.cfg[[:space:]]*\]'
  if ! [ -f "$macros_cfg" ] && ! { [ -f "$printer_cfg" ] && grep -Eq "$include_re" "$printer_cfg"; }; then
    note "None written by KlippEye."
  elif is_printing; then
    warn "Printing: $macros_cfg and its line [include klippeye_macros.cfg] in printer.cfg stay."
    note "After the print remove that line from printer.cfg, delete klippeye_macros.cfg and restart Klipper."
  else
    removed=1
    if [ -f "$printer_cfg" ] && grep -Eq "$include_re" "$printer_cfg"; then
      backup_file "$printer_cfg" printer.cfg
      if "$PYTHON" - "$printer_cfg" <<'PY'
import os, re, sys
p = os.path.realpath(sys.argv[1])   # a printer.cfg linked into a git folder: change the real file, keep the link
mode = os.stat(p).st_mode & 0o777
text = open(p, encoding="utf-8").read()
text = re.sub(r"\n?# KlippEye \(Settings -> Printer functions\)\n(?=[ \t]*\[include\s+klippeye_macros\.cfg\s*\])", "\n", text)
text = re.sub(r"(?m)^[ \t]*\[include\s+klippeye_macros\.cfg\s*\][ \t]*\n?", "", text)
tmp = p + ".klippeye-tmp"
with open(tmp, "w", encoding="utf-8") as f:
    f.write(text)
os.chmod(tmp, mode)
os.replace(tmp, p)
PY
      then good "Line [include klippeye_macros.cfg] removed from printer.cfg"; else warn "Cannot change $printer_cfg"; removed=0; fi
    fi
    # an include left in another file (not printer.cfg) would stop Klipper at its next start if the file went
    if [ "$removed" = 1 ] && grep -RElq --include='*.cfg' "$include_re" "$cfg_dir" 2>/dev/null; then
      warn "Another file of the configuration still includes klippeye_macros.cfg: the file stays."
      note "Remove that [include klippeye_macros.cfg] line, then delete klippeye_macros.cfg and restart Klipper."
      removed=0
    fi
    if [ "$removed" = 1 ] && [ -f "$macros_cfg" ]; then
      backup_file "$macros_cfg" klippeye_macros.cfg
      rm -f "$macros_cfg" && good "klippeye_macros.cfg deleted"
    fi
    [ "$removed" = 1 ] && note "Klipper is not restarted: restart it when you can, and the macros are gone."
  fi

  # 1.137.0: then the folders, after a yes
  step "Folders"
  if [ "$WEB_FAILED" = 1 ]; then
    warn "Port 80 could not be given back to the previous page, so both folders are kept: the program folder holds the tool for it."
    note "When nginx works again run:  bash $REPO/scripts/install.sh --uninstall"
    exit 1
  fi
  strip_slash() { local p="$1"; while [ "$p" != / ] && [ "${p%/}" != "$p" ]; do p="${p%/}"; done; printf '%s' "$p"; }
  REPO="$(strip_slash "$REPO")"; DATA="$(strip_slash "$DATA")"
  real() { (cd "$1" 2>/dev/null && pwd -P); }
  inside() { case "$1/" in "$2"/*) return 0 ;; *) return 1 ;; esac; }   # real path $1 is $2 or inside it
  may_delete() {  # folder program|data -> 0 when it may be deleted (else it says why)
    local r
    if [ -L "$1" ]; then note "$1 is a link to $(readlink -f "$1"): kept. Delete what it points to by hand if you want."; return 1; fi
    [ -d "$1" ] || { note "No folder at $1"; return 1; }
    r="$(real "$1")"
    if [ -z "$r" ] || [ "$r" = / ] || [ "$r" = "$(real "$HOME")" ] || inside "$(real "$HOME")" "$r"; then warn "$1 is not a folder to delete: kept."; return 1; fi
    if [ "$2" = program ]; then [ -f "$r/backend/klippeye_backend.py" ] && return 0
    else case "$(basename "$r")" in klippeye|klippeye_data) return 0 ;; esac; fi
    warn "$1 does not look like KlippEye's $2 folder: kept."; return 1
  }
  remove_folder() { rm -rf "$1" 2>/dev/null || sudo_run rm -rf "$1"; [ ! -e "$1" ]; }
  DEL_REPO=0; DEL_DATA=0; DATA_GOES=0
  may_delete "$REPO" program && DEL_REPO=1
  RR="$(real "$REPO")"; RD="$(real "$DATA")"
  DATA_IN_REPO=0; [ -n "$RD" ] && [ -n "$RR" ] && inside "$RD" "$RR" && DATA_IN_REPO=1
  if [ "$DATA_IN_REPO" = 1 ]; then
    if [ "$KEEP_DATA" = 1 ]; then
      [ "$DEL_REPO" = 1 ] && note "The data folder $DATA is inside the program folder: the program folder is kept too."
      DEL_REPO=0
    elif [ "$DEL_REPO" = 1 ]; then
      DATA_GOES=1; note "The data folder $DATA is inside the program folder: it goes with it."
    fi
  elif [ "$KEEP_DATA" = 0 ] && may_delete "$DATA" data; then
    DEL_DATA=1; DATA_GOES=1
  fi
  what=""; paths=""
  [ "$DEL_REPO" = 1 ] && { what="the program folder $REPO"; paths="$(printf ' %q' "$REPO")"; }
  [ "$DEL_DATA" = 1 ] && { what="${what:+$what and }the data folder $DATA (settings, recordings, labels)"; paths="$paths$(printf ' %q' "$DATA")"; }
  [ "$DATA_GOES" = 1 ] && [ "$DEL_DATA" = 0 ] && what="$what, with the data folder in it (settings, recordings, labels)"
  [ "$KEEP_DATA" = 1 ] && note "Data folder kept: $DATA"
  if [ -z "$what" ]; then
    say ""; say "Done. No folder to delete."; exit 0
  fi
  answer=no
  if [ "$YES" = 1 ]; then answer=yes
  elif [ -t 0 ]; then read -r -p "   Delete $what? Type yes to delete: " answer || answer=no
  else note "No terminal to ask on and no --yes: folders not deleted."
  fi
  if [ "$answer" != yes ]; then
    note "Kept: $what."
    note "To delete:  rm -rf$paths"
    exit 0
  fi
  if [ "$DATA_GOES" = 1 ] && [ -d "$DATA/backup" ]; then   # the copies of the files KlippEye changed outlive the data folder
    if [ -d "$PRINTER_DATA" ] && ! inside "$(real "$PRINTER_DATA")" "$RD"; then keep_bk="$PRINTER_DATA"; else keep_bk="$HOME"; fi
    keep_bk="$keep_bk/klippeye-backup-$(date +%Y%m%d-%H%M%S)"
    if mv "$DATA/backup" "$keep_bk" 2>/dev/null || sudo_run mv "$DATA/backup" "$keep_bk"; then good "Backup copies of the changed files moved to $keep_bk"
    else warn "Cannot move $DATA/backup: folders kept."; exit 1; fi
  fi
  if [ "$DEL_DATA" = 1 ]; then
    if remove_folder "$DATA"; then good "Data folder deleted: $DATA"; else warn "Cannot delete $DATA"; fi
  fi
  if [ "$DEL_REPO" = 1 ]; then
    if [ ! -e "$REPO" ]; then good "Program folder deleted with the data folder: $REPO"
    elif remove_folder "$REPO"; then good "Program folder deleted: $REPO"
    else warn "Cannot delete $REPO"; fi
  fi
  say ""
  say "Done. KlippEye is off this Raspberry. The system packages it used (python3-flask, python3-opencv...) stay: other programs may need them."
  exit 0
fi

# ====================================================================================================================
#  installation
# ====================================================================================================================

# --- 2. data and settings ----------------------------------------------------------------------------------------------
step "2/7  Data folder: $DATA"
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
step "3/7  Services (started by themselves at every boot)"
for need in "$REPO/systemd/klippeye.service" "$REPO/systemd/klippeye-notifier.service"; do
  [ -f "$need" ] || stop "The template $need is missing"
done
[ -d "$UNIT_DIR" ] || stop "The system services folder ($UNIT_DIR) was not found."

# 1.20.0: the notification service always runs. With no channel set up it sends nothing, but it does the automatic
# pause / cancel of the AI monitor, and it starts sending as soon as ntfy is turned on in the dashboard (no restart needed).
BACKEND_CHANGED=0
if install_unit klippeye; then BACKEND_CHANGED=1; fi
# the self-repair drop-in (klippeye.service.d/repair.conf, ripara.conf before 1.3.0, added by the backend) is no longer needed:
# the line is in the service file itself
if [ -f "$UNIT_DIR/klippeye.service.d/ripara.conf" ] || [ -f "$UNIT_DIR/klippeye.service.d/repair.conf" ]; then
  sudo_run rm -f "$UNIT_DIR/klippeye.service.d/ripara.conf" "$UNIT_DIR/klippeye.service.d/repair.conf"; sudo_run rmdir "$UNIT_DIR/klippeye.service.d" 2>/dev/null; BACKEND_CHANGED=1
fi
NOTIFIER_CHANGED=0
if install_unit klippeye-notifier; then NOTIFIER_CHANGED=1; fi
sudo_run "$SYSTEMCTL" daemon-reload || stop "systemctl daemon-reload failed."
sudo_run "$SYSTEMCTL" enable klippeye klippeye-notifier >/dev/null 2>&1

if [ "$BACKEND_CHANGED" = 1 ] || ! unit_active klippeye; then
  sudo_run "$SYSTEMCTL" restart klippeye || warn "systemctl restart klippeye gave an error"
  printf '   ...     waiting for the backend to answer (up to 40 seconds)\n'
  if NEWREL="$(backend_release 40)"; then
    good "The backend answers: release $NEWREL"
  else
    printf '\n   ERROR   The new backend does not answer at %s.\n' "$BACKEND_URL"
    note "Last lines of its log:"
    (journalctl -u klippeye -n 12 --no-pager 2>/dev/null || sudo_run journalctl -u klippeye -n 12 --no-pager 2>/dev/null) | sed 's/^/           /'
    stop_new_units
    stop "Installation stopped. If port 8085 is taken by another program, stop it and run this again. If a Python module is missing, see above."
  fi
else
  good "Service klippeye already in order"
fi

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

# --- 4. commands -------------------------------------------------------------------------------------------------------
step "4/7  Terminal commands"
if install_command klippeye && install_command klippeye-notifiche; then
  good "Written $BIN_DIR/klippeye and $BIN_DIR/klippeye-notifiche   (try:  klippeye status)"
fi

# --- 5. Moonraker --------------------------------------------------------------------------------------------------------
step "5/7  Updates from the dashboard (Moonraker's update manager)"
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
          "$PYTHON" - "$CONF" "$CHANNEL" <<'PY'
import os, re, shutil, sys
path, channel = os.path.realpath(sys.argv[1]), sys.argv[2]
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
if changed:   # 1.142.0: a new file next to it, then replace: a full card leaves the old file whole
    tmp = path + ".klippeye-tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)
        sys.exit(1)
sys.exit(0 if changed else 3)
PY
          case $? in
            0) good "Update channel set to '$CHANNEL'"; MR_RESTART=1 ;;
            3) good "Update channel already '$CHANNEL'" ;;
            *) warn "Cannot write $CONF (disk full?): the update channel stays as it was." ;;
          esac
        fi
      else
        backup_file "$CONF" moonraker.conf
        {
          printf '\n'
          if ! grep -Eq '^\[update_manager[[:space:]]*\][[:space:]]*$' "$CONF"; then
            printf '[update_manager]\n\n'
          fi
          printf '# KlippEye: updates from the dashboard (Settings -> Updates) and from the update manager of Moonraker. Written by scripts/install.sh.\n'
          printf '[update_manager klippeye]\ntype: git_repo\npath: %s\norigin: %s\nprimary_branch: %s\nchannel: %s\nmanaged_services: klippeye\ninfo_tags:\n  desc=KlippEye: backend, dashboard and notifications\n' "$REPO" "$ORIGIN" "$BRANCH" "$CHANNEL"
        } >> "$CONF"
        good "Entry [update_manager klippeye] added to moonraker.conf"
        MR_RESTART=1
      fi
    fi
    if [ ! -f "$ASVC" ]; then
      warn "$ASVC not found (the list of services Moonraker may restart): without it Moonraker does not restart 'klippeye' after an update."
    else
      ADDED=""
      for s in klippeye klippeye-notifier; do
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
      warn "Printing: Moonraker is not restarted now. When the print ends restart it from the Restart menu of the dashboard"
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

# --- 6. the Raspberry's own address (1.94) ------------------------------------------------------------------------------
step "6/7  KlippEye at the Raspberry's own address (no port)"
WEB_MAIN=0
NGINX_DIR="${KLIPPEYE_NGINX_DIR:-/etc/nginx}"
# 1.137.0: is KlippEye's site in place now (web_front.py status, readable without root)
WEB_NOW=0
"$PYTHON" "$REPO/scripts/web_front.py" status 2>/dev/null | "$PYTHON" -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("main") else 1)' 2>/dev/null && WEB_NOW=1
NGINX_UP=0
[ -d "$NGINX_DIR" ] && sudo_run "$SYSTEMCTL" is-active nginx >/dev/null 2>&1 && NGINX_UP=1
if [ "$WEB_GIVEN" = 0 ]; then
  # no option: a re-run keeps what is in place, a first install makes KlippEye the main page
  if [ "$FIRST_INSTALL" = 1 ]; then WITH_WEB=1; else WITH_WEB="$WEB_NOW"; fi
  if [ "$NGINX_UP" = 1 ] && [ -t 0 ] && [ -t 1 ]; then
    if [ "$WITH_WEB" = 1 ]; then hint="[Y/n]"; else hint="[y/N]"; fi
    while :; do
      answer=""
      read -r -p "   Make KlippEye the Raspberry's main page (http://IP, without :8085)? $hint " answer || answer=""
      case "$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')" in
        "") break ;;
        y|yes|s|si|sì) WITH_WEB=1; break ;;
        n|no) WITH_WEB=0; break ;;
        *) say "   Please answer y or n." ;;
      esac
    done
  fi
fi
if [ "$WITH_WEB" = 0 ]; then
  if [ "$WEB_NOW" = 1 ]; then
    if out="$(sudo_run "$PYTHON" "$REPO/scripts/web_front.py" restore 2>&1)"; then good "Port 80 given back: $out"; else warn "$out"; fi
  fi
  note "KlippEye is a second page: the dashboard is at port 8085."
elif [ "$NGINX_UP" = 0 ]; then
  note "nginx is not running on this Raspberry: the dashboard stays at port 8085."
else
  web_args=()
  if "$PYTHON" -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("enabled") else 1)' "$DATA/https.json" 2>/dev/null && [ -f "$DATA/https/https-cert.pem" ]; then
    web_args=(--https "$DATA/https/https-cert.pem" "$DATA/https/https-key.pem")
  fi
  if out="$(sudo_run "$PYTHON" "$REPO/scripts/web_front.py" main "${web_args[@]}" 2>&1)"; then
    good "$out"; WEB_MAIN=1
    note "To make KlippEye a second page again:  bash $REPO/scripts/install.sh --no-web   (or: klippeye web restore)"
  else
    warn "$out"
    note "The dashboard stays at port 8085."
  fi
fi

# --- 7. end --------------------------------------------------------------------------------------------------------------
step "7/7  Done"
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
say "   KlippEye $RELEASE is installed."
if [ "$WEB_MAIN" = 1 ]; then
  say "   Dashboard:   http://${IP:-<address of the Raspberry>}   (also at port 8085)"
else
  say "   Dashboard:   http://${IP:-<address of the Raspberry>}:8085"
fi
say "   Updates: in the dashboard open Settings -> Updates -> Check -> Update KlippEye."
say "   From the terminal:  klippeye status"
[ -n "$BK" ] && say "   Backup copies of what was changed: $BK"
exit 0
