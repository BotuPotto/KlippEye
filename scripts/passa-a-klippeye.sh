#!/usr/bin/env bash
# KlippEye - move from VzBot 1.0.x to KlippEye (done ONCE; it can be run again: it skips what is already done)
# (the file keeps its Italian name: installs of the VzBot days look for it under this name)
#
#   bash ~/vzbot/scripts/passa-a-klippeye.sh
#
# Usually it is not run by hand: the dashboard has the button "Move to KlippEye" (Settings -> Updates), which does the
# same and shows the steps. This command is for when the button cannot start it (e.g. sudo needs a password).
#
# What it does (6 steps):
#   1. checks that the printer is not printing and that it can be done
#   2. COPIES your data (~/printer_data/vzbot -> ~/printer_data/klippeye): the originals stay where they are
#   3. stops the services "vzbot" and "vzbot-notifier" and MOVES the program from ~/vzbot to ~/klippeye
#   4. installs the services "klippeye" and "klippeye-notifier" and connects them to Moonraker's update manager (scripts/install.sh)
#   5. removes the old services, the old commands and Moonraker's old entry (with a backup copy)
#   6. checks that KlippEye answers
# If something goes wrong before the end, everything is put back as it was and written in the log.
#
# State of the steps for the dashboard: a JSON file in /tmp/klippeye-migrazione.json

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OLD_REPO="$(cd "$HERE/.." && pwd)"
cd "$HOME" 2>/dev/null || cd /

SUDO="${KLIPPEYE_SUDO-sudo}"
SYSTEMCTL="${KLIPPEYE_SYSTEMCTL:-systemctl}"
UNIT_DIR="${KLIPPEYE_SYSTEMD_DIR:-/etc/systemd/system}"
BIN_DIR="${KLIPPEYE_BIN_DIR:-/usr/local/bin}"
PRINTER_DATA="${KLIPPEYE_PRINTER_DATA:-$HOME/printer_data}"
MOONRAKER_URL="${KLIPPEYE_MOONRAKER_URL:-http://127.0.0.1:7125}"
BACKEND_URL="${KLIPPEYE_BRAIN_URL:-http://127.0.0.1:8085}"
NEW_REPO="${KLIPPEYE_NEW_REPO:-$HOME/klippeye}"
STATUS="${KLIPPEYE_MIGRATION_STATUS:-${TMPDIR:-/tmp}/klippeye-migrazione.json}"
STEPS=6
FROM_BACKEND=0
for arg in "$@"; do
  case "$arg" in
    --from-backend|--dal-backend) FROM_BACKEND=1 ;;
    -h|--help|--aiuto) sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$arg"; exit 1 ;;
  esac
done

if [ -n "${KLIPPEYE_OLD_DATA:-}" ]; then OLD_DATA="$KLIPPEYE_OLD_DATA"
elif [ -d "$PRINTER_DATA/vzbot" ]; then OLD_DATA="$PRINTER_DATA/vzbot"
elif [ -d "$HOME/vzbot_data" ]; then OLD_DATA="$HOME/vzbot_data"
else OLD_DATA="$PRINTER_DATA/vzbot"; fi
if [ -n "${KLIPPEYE_DATA:-}" ]; then NEW_DATA="$KLIPPEYE_DATA"
elif [ -d "$PRINTER_DATA" ]; then NEW_DATA="$PRINTER_DATA/klippeye"
else NEW_DATA="$HOME/klippeye_data"; fi

PYTHON="${KLIPPEYE_PYTHON:-$(command -v python3 || true)}"
sudo_run() { if [ -n "$SUDO" ]; then $SUDO "$@"; else "$@"; fi; }
say()  { printf '%s\n' "$*"; }
good() { printf '   OK      %s\n' "$*"; }
note() { printf '           %s\n' "$*"; }
warn() { printf '   WARNING %s\n' "$*"; }

json_text() {  # text -> JSON string
  "$PYTHON" -c 'import json,sys; sys.stdout.write(json.dumps(sys.argv[1], ensure_ascii=False))' "$1"
}
report() {  # state step message
  local tmp="$STATUS.$$"
  printf '{"state":"%s","step":%s,"steps":%s,"message":%s,"time":%s}\n' "$1" "$2" "$STEPS" "$(json_text "$3")" "$(date +%s)" > "$tmp" 2>/dev/null \
    && mv -f "$tmp" "$STATUS" 2>/dev/null
}
CURRENT=0
step() { CURRENT="$1"; shift; printf '\n== %s/%s  %s\n' "$CURRENT" "$STEPS" "$*"; report running "$CURRENT" "$*"; }

# --- rollback ----------------------------------------------------------------------------------------------------------
MOVED=0; OLD_STOPPED=0; CONF_BACKUP=""; ASVC_BACKUP=""; BK=""
rollback() {
  say ""
  say "   Putting everything back as it was..."
  if [ "$MOVED" = 1 ] && [ -d "$NEW_REPO" ] && [ ! -d "$OLD_REPO" ]; then
    mv "$NEW_REPO" "$OLD_REPO" && good "Program put back in $OLD_REPO"
  fi
  [ -n "$CONF_BACKUP" ] && [ -f "$CONF_BACKUP" ] && cp -p "$CONF_BACKUP" "$PRINTER_DATA/config/moonraker.conf"
  [ -n "$ASVC_BACKUP" ] && [ -f "$ASVC_BACKUP" ] && cp -p "$ASVC_BACKUP" "$PRINTER_DATA/moonraker.asvc"
  for n in klippeye klippeye-notifier; do
    if [ -f "$UNIT_DIR/$n.service" ] && grep -q 'MANAGED-BY-KLIPPEYE\|GESTITO-DA-KLIPPEYE' "$UNIT_DIR/$n.service"; then
      sudo_run "$SYSTEMCTL" disable --now "$n" >/dev/null 2>&1
      sudo_run rm -f "$UNIT_DIR/$n.service"
    fi
  done
  for n in vzbot vzbot-notifier; do   # the old service files, if install.sh had already removed them
    if [ ! -f "$UNIT_DIR/$n.service" ] && [ -n "$BK" ] && [ -f "$BK/units/$n.service" ]; then sudo_run install -m 644 "$BK/units/$n.service" "$UNIT_DIR/$n.service"; fi
  done
  sudo_run "$SYSTEMCTL" daemon-reload >/dev/null 2>&1
  if [ "$OLD_STOPPED" = 1 ]; then
    sudo_run "$SYSTEMCTL" enable vzbot >/dev/null 2>&1
    sudo_run "$SYSTEMCTL" restart vzbot >/dev/null 2>&1 && good "Service vzbot on again"
    if [ -f "$UNIT_DIR/vzbot-notifier.service" ]; then
      sudo_run "$SYSTEMCTL" enable vzbot-notifier >/dev/null 2>&1
      sudo_run "$SYSTEMCTL" restart vzbot-notifier >/dev/null 2>&1
    fi
  fi
}
fail() {
  printf '\n   ERROR   %s\n' "$*"
  rollback
  report error "$CURRENT" "$*"
  exit 1
}

say "KlippEye - move from VzBot"

# --- 1. checks ---------------------------------------------------------------------------------------------------------
step 1 "Checking that it can be done"
[ -n "$PYTHON" ] || fail "Python 3 is missing."
if [ "$(id -u)" = "0" ] && [ -z "${KLIPPEYE_ALLOW_ROOT:-}" ]; then
  fail "Do not run me with sudo: I must run as the normal user (usually 'pi')."
fi
case "$(basename "$OLD_REPO")" in
  vzbot|VzBot) ;;
  *) if [ -z "${KLIPPEYE_FORCE:-}" ]; then
       if [ -d "$NEW_REPO" ] && [ "$OLD_REPO" = "$NEW_REPO" ]; then
         good "Already on KlippEye ($OLD_REPO): nothing to do."
         report done "$STEPS" "Already on KlippEye: nothing to do."
         exit 0
       fi
       fail "This folder ($OLD_REPO) is not called vzbot: there is nothing known to move."
     fi ;;
esac
[ -f "$OLD_REPO/scripts/install.sh" ] || fail "$OLD_REPO/scripts/install.sh is missing: update the program from the dashboard first."
[ -f "$OLD_REPO/backend/klippeye_backend.py" ] || fail "$OLD_REPO/backend/klippeye_backend.py is missing: update the program from the dashboard first (Settings -> Updates)."
if [ -e "$NEW_REPO" ]; then
  fail "$NEW_REPO already exists and will not be overwritten. Move or delete it and try again."
fi
case "$OLD_REPO$NEW_REPO$OLD_DATA$NEW_DATA" in *" "*) fail "Folder names must not contain spaces." ;; esac

PRINTING="$("$PYTHON" - "$MOONRAKER_URL/printer/objects/query?print_stats=state" <<'PY'
import json, sys, urllib.request
try:
    d = json.loads(urllib.request.urlopen(sys.argv[1], timeout=4).read().decode("utf-8", "replace"))
    print("yes" if d["result"]["status"]["print_stats"]["state"] in ("printing", "paused") else "no")
except Exception:
    print("no")
PY
)"
[ "$PRINTING" = "no" ] || fail "Printing (or paused): try again when the print ends. Nothing was touched."
if [ -n "$SUDO" ]; then
  $SUDO -n true 2>/dev/null || fail "The administrator password is needed and it cannot be asked for here. Run the command from the terminal:   bash $OLD_REPO/scripts/passa-a-klippeye.sh"
fi
good "It can be done: program in $OLD_REPO -> $NEW_REPO"

# --- 2. data ------------------------------------------------------------------------------------------------------------
step 2 "Copying your settings"
mkdir -p "$NEW_DATA" || fail "Cannot create $NEW_DATA"
chmod 700 "$NEW_DATA"
if [ -d "$OLD_DATA" ] && [ "$OLD_DATA" != "$NEW_DATA" ] && [ -n "$(ls -A "$OLD_DATA" 2>/dev/null)" ]; then
  cp -an "$OLD_DATA"/. "$NEW_DATA"/ || fail "Could not copy the data from $OLD_DATA"
  : > "$NEW_DATA/.copiato-da-vzbot"
  good "Data copied from $OLD_DATA to $NEW_DATA (the originals stay there)"
else
  note "No earlier data to copy"
fi
BK="$NEW_DATA/backup/passaggio-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BK/units"

# --- 3. stop the old services and move the program -----------------------------------------------------------------------
step 3 "Stopping VzBot and moving the program"
HAD_NOTIFIER=0
[ -f "$UNIT_DIR/vzbot-notifier.service" ] && HAD_NOTIFIER=1
for n in vzbot vzbot-notifier; do   # copy of the old services: needed to go back if something goes wrong
  [ -f "$UNIT_DIR/$n.service" ] && cp -p "$UNIT_DIR/$n.service" "$BK/units/$n.service"
done
OLD_STOPPED=1
if [ "$HAD_NOTIFIER" = 1 ]; then sudo_run "$SYSTEMCTL" stop vzbot-notifier >/dev/null 2>&1; fi
# "vzbot" stopping here does not stop this script: it runs as a separate systemd job when the backend started it.
sudo_run "$SYSTEMCTL" stop vzbot >/dev/null 2>&1
good "Old services stopped"
CONF="$PRINTER_DATA/config/moonraker.conf"; ASVC="$PRINTER_DATA/moonraker.asvc"
if [ -f "$CONF" ]; then CONF_BACKUP="$BK/moonraker.conf"; cp -p "$CONF" "$CONF_BACKUP"; fi
if [ -f "$ASVC" ]; then ASVC_BACKUP="$BK/moonraker.asvc"; cp -p "$ASVC" "$ASVC_BACKUP"; fi
mv "$OLD_REPO" "$NEW_REPO" || fail "Cannot move $OLD_REPO to $NEW_REPO"
MOVED=1
good "Program moved to $NEW_REPO"
if [ -d "$NEW_REPO/.git" ]; then
  ORIGIN="$(git -C "$NEW_REPO" remote get-url origin 2>/dev/null || true)"
  FIXED="$(printf '%s' "$ORIGIN" | sed -E 's#/[Vv]z[Bb]ot(\.git)?$#/KlippEye\1#')"
  if [ -n "$ORIGIN" ] && [ "$FIXED" != "$ORIGIN" ]; then
    git -C "$NEW_REPO" remote set-url origin "$FIXED" && good "GitHub address updated: $FIXED"
  fi
fi

# --- 4. install KlippEye ------------------------------------------------------------------------------------------------
step 4 "Installing the KlippEye services"
# First Moonraker's old entry goes (it points to a folder that is no longer there): install.sh then writes a new one.
if [ -f "$CONF" ]; then
  "$PYTHON" - "$CONF" <<'PY' || fail "Cannot change moonraker.conf"
import re, sys
p = sys.argv[1]
lines = open(p, encoding="utf-8").read().split("\n")
out, skip = [], False
for line in lines:
    if re.match(r"^\[", line):
        skip = bool(re.match(r"^\[update_manager\s+vzbot\]\s*$", line))
    if not skip:
        out.append(line)
text = "\n".join(out).rstrip("\n") + "\n"
text = re.sub(r"\n+# VzBot: aggiornamenti dalla dashboard[^\n]*\n", "\n", text)
open(p, "w", encoding="utf-8").write(text)
PY
fi
if [ -f "$ASVC" ]; then
  grep -vx -e vzbot -e vzbot-notifier "$ASVC" > "$BK/asvc.nuovo"; cat "$BK/asvc.nuovo" > "$ASVC"
fi
INSTALL_ENV=(KLIPPEYE_DATA="$NEW_DATA" KLIPPEYE_OLD_DATA="$OLD_DATA")
env "${INSTALL_ENV[@]}" bash "$NEW_REPO/scripts/install.sh" > "$BK/install.log" 2>&1
RC=$?
if [ "$RC" != 0 ]; then
  tail -n 12 "$BK/install.log" | sed 's/^/           /'
  fail "The KlippEye installation failed (details in $BK/install.log)."
fi
good "KlippEye services installed and on"

# --- 5. clean up ----------------------------------------------------------------------------------------------------------
step 5 "Removing the old services and commands"
for n in vzbot vzbot-notifier; do
  if [ -f "$UNIT_DIR/$n.service" ]; then
    sudo_run "$SYSTEMCTL" disable --now "$n" >/dev/null 2>&1
    sudo_run rm -f "$UNIT_DIR/$n.service"
  fi
done
sudo_run "$SYSTEMCTL" daemon-reload
for n in vzbot vzbot-notifiche; do
  if [ -f "$BIN_DIR/$n" ]; then sudo_run rm -f "$BIN_DIR/$n"; fi
done
good "Old services and commands removed (copy in $BK)"
OLD_STOPPED=0  # no going back from here: everything is in place

# --- 6. check ------------------------------------------------------------------------------------------------------------
step 6 "Checking that KlippEye answers"
NEWREL="$("$PYTHON" - "$BACKEND_URL/api/version" <<'PY'
import json, sys, time, urllib.request
end = time.time() + 45
while time.time() < end:
    try:
        d = json.loads(urllib.request.urlopen(sys.argv[1], timeout=3).read().decode("utf-8", "replace"))
        if isinstance(d, dict) and d.get("release"):
            print(d["release"]); sys.exit(0)
    except Exception:
        time.sleep(1)
sys.exit(1)
PY
)" || { warn "KlippEye does not answer yet (it may take a minute). Check with:  klippeye status"; NEWREL=""; }
if [ -n "$NEWREL" ]; then good "KlippEye $NEWREL answers"; fi
report done "$STEPS" "Done: you are now on KlippEye ${NEWREL}. Reload the page."
say ""
say "Done. Reload the dashboard (if the browser does not refresh, clear its cache)."
say "The old files ($OLD_DATA) stayed where they were: delete them once you are sure everything works."
exit 0
