#!/usr/bin/env bash
# KlippEye - self-repair of the program files after a sudden power loss.
#
# If power goes away while the Raspberry is writing, a file can be left empty or half written: the backend then starts but the
# dashboard stays blank (or does not start at all). This script compares the program files with the copy git keeps (the "good"
# copy is in the .git folder, on the Raspberry itself, so NO internet is needed) and restores only the damaged or missing ones.
#
# It runs by itself: at every start of the service (ExecStartPre line of klippeye.service), when the backend starts and when the
# dashboard page turns out to be damaged. By hand:  klippeye repair
#
# It does not touch your settings, the AI key or the notifications (they live in ~/printer_data/klippeye, outside the program).
# To turn it off (if you edit the program files by hand) create an empty file:  ~/printer_data/klippeye/no-repair
#
# It writes what it did into <data dir>/repair.log and, when it restored something, into <data dir>/repair.json (read by the
# dashboard). It always exits with 0: it must never stop the service from starting.
# Files of releases before 1.3.0 (riparazioni.log, ripristino.json, non-riparare) are renamed the first time.

REPO="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
if [ -n "${KLIPPEYE_DATA:-}" ]; then DATA="$KLIPPEYE_DATA"
elif [ -d "$HOME/printer_data" ]; then DATA="$HOME/printer_data/klippeye"
else DATA="$HOME/klippeye_data"; fi
LOG="$DATA/repair.log"
MARK="$DATA/repair.json"
QUIET=0; ENABLE=0
for A in "$@"; do case "$A" in --quiet|--silenzioso) QUIET=1 ;; --enable-at-start|--attiva-avvio) ENABLE=1 ;; esac; done

# names before 1.3.0
for PAIR in "riparazioni.log:repair.log" "ripristino.json:repair.json" "non-riparare:no-repair" ".avvio-non-attivabile:.cannot-enable-at-start"; do
  OLD="$DATA/${PAIR%%:*}"; NEW="$DATA/${PAIR#*:}"
  [ -e "$OLD" ] && [ ! -e "$NEW" ] && mv -f "$OLD" "$NEW" 2>/dev/null
done

log() {
  local line; line="$(date '+%Y-%m-%d %H:%M:%S') $*"
  [ "$QUIET" = 1 ] || printf '%s\n' "$*"
  mkdir -p "$DATA" 2>/dev/null && printf '%s\n' "$line" >> "$LOG" 2>/dev/null \
    && [ "$(wc -l < "$LOG" 2>/dev/null || echo 0)" -gt 300 ] && { tail -n 150 "$LOG" > "$LOG.tmp" && mv -f "$LOG.tmp" "$LOG"; }
  return 0
}

# --enable-at-start: run the check also BEFORE the backend (ExecStartPre line of the service). Services installed by 1.0.x or 1.1.0
# do not have it: it is added as a systemd drop-in (folder klippeye.service.d), once, if the system allows it without a password.
# scripts/install.sh puts the line straight into the service file and removes the drop-in.
enable_at_start() {
  local unit dir cat tmp sudo_cmd
  unit=klippeye
  dir="${KLIPPEYE_SYSTEMD_DIR:-/etc/systemd/system}"
  cat="$("${KLIPPEYE_SYSTEMCTL:-systemctl}" cat "$unit" 2>/dev/null)" || return 0   # no service with this name: nothing to do
  case "$cat" in *repair.sh*|*ripara.sh*) return 0 ;; esac                         # already there
  sudo_cmd="${KLIPPEYE_SUDO-sudo}"; [ -n "$sudo_cmd" ] && sudo_cmd="$sudo_cmd -n"
  tmp="$(mktemp)" || return 0
  printf '[Service]\nExecStartPre=-/bin/bash %s/scripts/repair.sh --quiet\n' "$REPO" > "$tmp"
  if $sudo_cmd mkdir -p "$dir/$unit.service.d" 2>/dev/null && $sudo_cmd install -m 644 "$tmp" "$dir/$unit.service.d/repair.conf" 2>/dev/null \
     && $sudo_cmd "${KLIPPEYE_SYSTEMCTL:-systemctl}" daemon-reload 2>/dev/null; then
    log "Enabled the file check at every start of the $unit service (from the next start)."
  elif [ ! -e "$DATA/.cannot-enable-at-start" ]; then
    : > "$DATA/.cannot-enable-at-start" 2>/dev/null
    log "Cannot enable the check before the start (it needs sudo without a password). To enable it: bash $REPO/scripts/install.sh"
  fi
  rm -f "$tmp"
}

[ -e "$DATA/no-repair" ] && { [ "$QUIET" = 1 ] || echo "Self-repair is off (file $DATA/no-repair)."; exit 0; }
[ "$ENABLE" = 1 ] && { enable_at_start; exit 0; }
command -v git >/dev/null 2>&1 || exit 0
[ -d "$REPO/.git" ] || exit 0   # copied by hand without git: nothing to compare with

# An update (git) is working right now (or Moonraker is checking the repository, which takes a moment): wait up to 10 seconds.
# An old lock left by a power loss is removed instead.
LOCK="$REPO/.git/index.lock"
for _ in $(seq 20); do
  [ -e "$LOCK" ] || break
  AGE=$(( $(date +%s) - $(stat -c %Y "$LOCK" 2>/dev/null || echo 0) ))
  { [ "$AGE" -lt 120 ] || pgrep -x git >/dev/null 2>&1; } || break
  sleep 0.5
done
if [ -e "$LOCK" ]; then
  AGE=$(( $(date +%s) - $(stat -c %Y "$LOCK" 2>/dev/null || echo 0) ))
  if [ "$AGE" -lt 120 ] || pgrep -x git >/dev/null 2>&1; then
    [ "$QUIET" = 1 ] || echo "Git is working (lock ${AGE}s old): try again in a moment."
    exit 0
  fi
  rm -f "$LOCK" && log "Removed the git lock left by a sudden power loss (${AGE}s old)."
fi

if ! git -C "$REPO" rev-parse --verify -q 'HEAD^{commit}' >/dev/null 2>&1; then
  log "ERROR: the git data in $REPO is damaged: cannot compare the files. Fix: Mainsail -> Machine -> Update Manager -> klippeye -> Recover (hard), or in a terminal: klippeye update --force"
  exit 0
fi

# Compare the hash of every program file with the one git has for the installed release.
BAD=()
while IFS= read -r -d '' ENTRY; do
  META="${ENTRY%%$'\t'*}"; FILE="${ENTRY#*$'\t'}"
  read -r MODE TYPE SHA <<< "$META"
  [ "$TYPE" = blob ] && [ "$MODE" != 120000 ] || continue
  if [ ! -f "$REPO/$FILE" ]; then BAD+=("$FILE"); continue; fi
  [ "$(git -C "$REPO" hash-object --no-filters -- "$REPO/$FILE" 2>/dev/null)" = "$SHA" ] || BAD+=("$FILE")
done < <(git -C "$REPO" ls-tree -r -z HEAD -- backend frontend notifier scripts systemd brain apk VERSION 2>/dev/null)

if [ "${#BAD[@]}" = 0 ]; then
  [ "$QUIET" = 1 ] || echo "All program files are intact."
  exit 0
fi

log "Damaged or missing files (${#BAD[@]}): ${BAD[*]}"
ERR="$(git -C "$REPO" checkout HEAD -- "${BAD[@]}" 2>&1)" || log "git cannot restore them: ${ERR:0:300}"
sync 2>/dev/null

DONE=(); FAILED=()
for FILE in "${BAD[@]}"; do
  SHA="$(git -C "$REPO" rev-parse "HEAD:$FILE" 2>/dev/null)"
  if [ -f "$REPO/$FILE" ] && [ "$(git -C "$REPO" hash-object --no-filters -- "$REPO/$FILE" 2>/dev/null)" = "$SHA" ]; then DONE+=("$FILE"); else FAILED+=("$FILE"); fi
done
[ "${#DONE[@]}" = 0 ] || log "Restored (${#DONE[@]}): ${DONE[*]}"
if [ "${#FAILED[@]}" != 0 ]; then
  log "NOT restored (${#FAILED[@]}): ${FAILED[*]} - fix: Mainsail -> Machine -> Update Manager -> klippeye -> Recover (hard), or in a terminal: klippeye update --force"
fi

json_list() { local out="" f; for f in "$@"; do out="${out:+$out,}\"$f\""; done; printf '[%s]' "$out"; }
mkdir -p "$DATA" 2>/dev/null
printf '{"time":%s,"restored":%s,"failed":%s}\n' "$(date +%s)" "$(json_list "${DONE[@]}")" "$(json_list "${FAILED[@]}")" > "$MARK.tmp" 2>/dev/null && mv -f "$MARK.tmp" "$MARK" 2>/dev/null
exit 0
