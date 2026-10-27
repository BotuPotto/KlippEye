#!/usr/bin/env bash
# KlippEye - installation on the Raspberry (done ONCE; it can be run again at any time, it is made not to break anything)
#
#   bash ~/klippeye/scripts/install.sh                  install or repair
#   bash ~/klippeye/scripts/install.sh --no-moonraker   do not touch Moonraker's configuration
#   bash ~/klippeye/scripts/install.sh --undo           go back to how it was (old services, no update manager entry)
#   (the Italian options of older releases still work: --senza-moonraker, --annulla, --aiuto)
#
# What it does, in this order:
#   1. checks Python, git and the modules the backend needs
#   2. creates the DATA folder (~/printer_data/klippeye: settings, AI key, notifications) and COPIES into it what you
#      already had (~/vzbot_ai_config.json, ~/vzbot-notifier/..., ~/printer_data/vzbot). The old files stay: nothing is deleted
#   3. installs the services "klippeye" (backend + dashboard) and "klippeye-notifier" (notifications), started at every boot;
#      the services with the old names ("vzbot", "vzbot-notifier") are stopped and removed (a copy is kept);
#      if the new backend does not answer, everything is put back as it was
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
PRINTER_DATA="${KLIPPEYE_PRINTER_DATA:-$HOME/printer_data}"
MOONRAKER_URL="${KLIPPEYE_MOONRAKER_URL:-http://127.0.0.1:7125}"
BRAIN_URL="${KLIPPEYE_BRAIN_URL:-http://127.0.0.1:8085}"
MOONRAKER_SERVICE="${KLIPPEYE_MOONRAKER_SERVICE:-moonraker}"
OLD_NOTIFIER_DIR="${KLIPPEYE_OLD_NOTIFIER_DIR:-$HOME/vzbot-notifier}"   # before KlippEye (VzBot 1.0.x)
if [ -n "${KLIPPEYE_DATA:-}" ]; then DATA="$KLIPPEYE_DATA"
elif [ -d "$PRINTER_DATA" ]; then DATA="$PRINTER_DATA/klippeye"
else DATA="$HOME/klippeye_data"; fi

say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
good() { printf '   OK      %s\n' "$*"; }
note() { printf '           %s\n' "$*"; }
warn() { printf '   WARNING %s\n' "$*"; }
stop() { printf '\n   ERROR   %s\n\n' "$*"; exit 1; }

usage() { sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

MODE=install
WITH_MOONRAKER=1
for arg in "$@"; do
  case "$arg" in
    --undo|--annulla) MODE=undo ;;
    --no-moonraker|--senza-moonraker) WITH_MOONRAKER=0 ;;
    -h|--help|--aiuto) usage; exit 0 ;;
    *) stop "Unknown option: $arg   (try:  bash $0 --help)" ;;
  esac
done

sudo_run() { if [ -n "$SUDO" ]; then $SUDO "$@"; else "$@"; fi; }

RELEASE="$(tr -d '[:space:]' < "$REPO/VERSION" 2>/dev/null || true)"
RELEASE="${RELEASE:-unknown}"
say "KlippEye $RELEASE - installation on the Raspberry"

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
command -v git >/dev/null 2>&1 || warn "git is missing: without it updates do not work. Install it with:  sudo apt install -y git"

MISSING=""
for module in flask flask_cors requests; do
  "$PYTHON" -c "import $module" 2>/dev/null || MISSING="$MISSING $module"
done
if [ -n "$MISSING" ]; then
  warn "The backend is missing these Python modules:$MISSING"
  note "Install them with:   sudo apt install -y python3-flask python3-flask-cors python3-requests"
  note "then run this command again."
  if [ -z "${KLIPPEYE_IGNORE_MISSING:-}" ]; then stop "Without those modules the backend does not start."; fi
else
  good "Backend modules: flask, flask_cors, requests"
fi
if "$PYTHON" -c 'import cv2, numpy' 2>/dev/null; then
  good "OpenCV and numpy (for the AI monitor)"
else
  warn "OpenCV/numpy are missing: the backend starts anyway, but the AI monitor cannot look at the camera."
  note "If you want it:   sudo apt install -y python3-opencv python3-numpy"
fi
[ -f "$REPO/frontend/klippeye_frontend.html" ] || warn "$REPO/frontend/klippeye_frontend.html is missing: the backend starts, but the dashboard page does not open."

WORK="$(mktemp -d "${TMPDIR:-/tmp}/klippeye-install.XXXXXX")" || stop "Cannot create a temporary folder."
trap 'rm -rf "$WORK"' EXIT

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
oldest_backup_of() {  # name_in_the_backup -> path of the oldest backup that has it
  local d
  for d in $(ls -1d "$DATA"/backup/*/ 2>/dev/null | sort); do
    if [ -f "${d}$1" ]; then printf '%s\n' "${d}$1"; return 0; fi
  done
  return 1
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
OLD_UNIT_NAMES="vzbot vzbot-notifier"   # the services before KlippEye
RETIRED=""
retire_old_units() {  # stops and removes the old services (with a copy in the backup); $1 = "all" or "keep-notifier"
  local name f
  for name in $OLD_UNIT_NAMES; do
    f="$UNIT_DIR/$name.service"
    [ -f "$f" ] || continue
    if [ "$name" = "vzbot-notifier" ] && [ "${1:-all}" = "keep-notifier" ]; then
      warn "Leaving the old service $name on: the new notifications are not set up yet."
      continue
    fi
    backup_file "$f" "units/$name.service"
    sudo_run "$SYSTEMCTL" disable --now "$name" >/dev/null 2>&1
    sudo_run rm -f "$f"
    RETIRED="$RETIRED $name"
    good "Old service $name stopped and removed (copy in the backup)"
  done
  [ -n "$RETIRED" ] && sudo_run "$SYSTEMCTL" daemon-reload
}
bring_back_old_units() {  # puts the old services back from the backup copies and starts them; 0 when at least one was put back
  local name old back=1
  for name in $OLD_UNIT_NAMES; do
    [ -f "$UNIT_DIR/$name.service" ] && continue
    old="$(oldest_backup_of "units/$name.service")" || continue
    sudo_run install -m 644 "$old" "$UNIT_DIR/$name.service" && back=0
  done
  [ "$back" = 0 ] && sudo_run "$SYSTEMCTL" daemon-reload
  for name in $OLD_UNIT_NAMES; do
    if [ -f "$UNIT_DIR/$name.service" ]; then
      sudo_run "$SYSTEMCTL" enable "$name" >/dev/null 2>&1
      sudo_run "$SYSTEMCTL" restart "$name" >/dev/null 2>&1
    fi
  done
  return $back
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
notifier_ready() {  # 0 when notifier.json and the Firebase key it points to are there
  [ -f "$DATA/notifier.json" ] || return 1
  "$PYTHON" - "$DATA" <<'PY'
import json, os, sys
d = sys.argv[1]
try:
    conf = json.load(open(os.path.join(d, "notifier.json"), encoding="utf-8"))
    key = conf.get("service_account_file") or "service-account.json"
    if not os.path.isabs(key):
        key = os.path.join(d, key)
    sys.exit(0 if os.path.isfile(key) else 1)
except Exception:
    sys.exit(1)
PY
}

# ====================================================================================================================
#  --undo
# ====================================================================================================================
if [ "$MODE" = "undo" ]; then
  step "Undoing KlippEye $RELEASE: back to the services of before"
  stop_new_units
  good "Services klippeye and klippeye-notifier stopped and removed"
  if bring_back_old_units; then
    good "Services of before (vzbot, vzbot-notifier) put back as they were and started"
  else
    note "There were no services of before to put back (KlippEye was installed from scratch)."
  fi
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
# If VzBot 1.0.x was there before, its data folder (same content) is COPIED here without overwriting anything.
if [ -n "${KLIPPEYE_OLD_DATA:-}" ]; then OLD_DATA="$KLIPPEYE_OLD_DATA"
elif [ -d "$PRINTER_DATA/vzbot" ]; then OLD_DATA="$PRINTER_DATA/vzbot"
else OLD_DATA="$HOME/vzbot_data"; fi
if [ -d "$OLD_DATA" ] && [ "$OLD_DATA" != "$DATA" ] && [ -n "$(ls -A "$OLD_DATA" 2>/dev/null)" ] && [ ! -f "$DATA/.copiato-da-vzbot" ]; then
  if cp -an "$OLD_DATA"/. "$DATA"/ 2>/dev/null; then
    : > "$DATA/.copiato-da-vzbot"
    good "VzBot settings and data copied from $OLD_DATA (the originals stay there)"
  else
    warn "Could not copy the data from $OLD_DATA"
  fi
fi
good "Settings, AI key and notifications stay here. Updates do not touch this folder."

if [ -d "$REPO/.git" ]; then
  # Files uploaded through the GitHub website have no "executable" permission: without this line git would see them as
  # "changed" as soon as they are made executable, and Moonraker's update manager would refuse to update.
  git -C "$REPO" config core.fileMode false 2>/dev/null
fi

AI_OLD="${KLIPPEYE_OLD_AI_CONFIG:-$HOME/vzbot_ai_config.json}"   # before KlippEye (VzBot 1.0.x)
if [ -f "$DATA/ai.json" ]; then
  chmod 600 "$DATA/ai.json"
  good "AI key: already in the data folder"
elif [ -f "$AI_OLD" ]; then
  cp "$AI_OLD" "$DATA/ai.json" && chmod 600 "$DATA/ai.json" && good "AI key copied from $AI_OLD (the original stays there)"
else
  note "AI key: none yet (it is entered from the dashboard)"
fi

if [ -f "$DATA/notifier.json" ]; then
  good "Notifications: configuration already in the data folder"
elif [ -f "$OLD_NOTIFIER_DIR/notifier.json" ]; then
  if "$PYTHON" - "$OLD_NOTIFIER_DIR" "$DATA" <<'PY'
import json, os, shutil, sys, tempfile
old, new = sys.argv[1], sys.argv[2]
conf = json.load(open(os.path.join(old, "notifier.json"), encoding="utf-8"))
key = conf.get("service_account_file") or "service-account.json"
if not os.path.isabs(key):
    key = os.path.join(old, key)
if os.path.isfile(key):
    target = os.path.join(new, "service-account.json")
    shutil.copyfile(key, target)
    os.chmod(target, 0o600)
    conf["service_account_file"] = "service-account.json"
fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=new)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    json.dump(conf, f, indent=2, ensure_ascii=False)
    f.write("\n")
os.chmod(tmp, 0o600)
os.replace(tmp, os.path.join(new, "notifier.json"))
PY
  then good "Notifications: configuration and Firebase key copied from $OLD_NOTIFIER_DIR (the originals stay there)"
  else warn "Could not copy the notification configuration from $OLD_NOTIFIER_DIR"; fi
else
  note "Notifications: not set up (done once with the guide; see docs/GUIDE.md)"
fi

# --- 3. services -------------------------------------------------------------------------------------------------------
step "3/6  Services (started by themselves at every boot)"
for need in "$REPO/systemd/klippeye.service" "$REPO/systemd/klippeye-notifier.service"; do
  [ -f "$need" ] || stop "The template $need is missing"
done
[ -d "$UNIT_DIR" ] || stop "The system services folder ($UNIT_DIR) was not found."

NOTIFIER_ON=0
if notifier_ready; then NOTIFIER_ON=1; fi
# The services of before use the same port and the same data: they are stopped before the new ones start.
if [ "$NOTIFIER_ON" = 1 ]; then retire_old_units all; else retire_old_units keep-notifier; fi
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
    if bring_back_old_units; then
      note "The services were put back as they were: the backend of before should be on again."
    fi
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
else
  note "Notifications: the service starts only after the Firebase key is put in $DATA (guide: docs/GUIDE.md)"
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
      else
        backup_file "$CONF" moonraker.conf
        {
          printf '\n'
          if ! grep -Eq '^\[update_manager[[:space:]]*\][[:space:]]*$' "$CONF"; then
            printf '[update_manager]\n\n'
          fi
          printf '# KlippEye: updates from the dashboard (Settings -> Updates) and from Mainsail/Fluidd. Written by scripts/install.sh.\n'
          printf '[update_manager klippeye]\ntype: git_repo\npath: %s\norigin: %s\nprimary_branch: %s\nchannel: dev\nmanaged_services: klippeye\ninfo_tags:\n  desc=KlippEye: backend, dashboard and notifications\n' "$REPO" "$ORIGIN" "$BRANCH"
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
