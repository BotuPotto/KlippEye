#!/usr/bin/env bash
# KlippEye - passaggio da VzBot 1.0.x a KlippEye (si fa UNA volta; si puo' rilanciare: salta quello che e' gia' fatto)
#
#   bash ~/vzbot/scripts/passa-a-klippeye.sh
#
# Di solito non serve lanciarlo a mano: nella dashboard c'e' il pulsante "Passa a KlippEye" (Impostazioni -> Sistema) che
# fa le stesse cose e mostra i passi. Questo comando serve se il pulsante non puo' partire (per esempio manca sudo senza password).
#
# Cosa fa (6 passi):
#   1. controlla che non stia stampando e che si possa fare
#   2. COPIA i tuoi dati (~/printer_data/vzbot -> ~/printer_data/klippeye): gli originali restano dove sono
#   3. ferma i servizi "vzbot" e "vzbot-notifier" e SPOSTA il programma da ~/vzbot a ~/klippeye
#   4. installa i servizi "klippeye" e "klippeye-notifier" e li collega all'update manager di Moonraker (scripts/install.sh)
#   5. toglie i vecchi servizi, i vecchi comandi e la vecchia voce di Moonraker (con copia di sicurezza)
#   6. controlla che KlippEye risponda
# Se qualcosa va storto prima della fine, rimette tutto com'era e lo scrive nel registro.
#
# Stato dei passi per la dashboard: file JSON in /tmp/klippeye-migrazione.json

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
    --dal-backend) FROM_BACKEND=1 ;;
    -h|--aiuto|--help) sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) printf 'Opzione sconosciuta: %s\n' "$arg"; exit 1 ;;
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
warn() { printf '   AVVISO  %s\n' "$*"; }

json_text() {  # testo -> stringa JSON
  "$PYTHON" -c 'import json,sys; sys.stdout.write(json.dumps(sys.argv[1], ensure_ascii=False))' "$1"
}
report() {  # stato passo messaggio
  local tmp="$STATUS.$$"
  printf '{"state":"%s","step":%s,"steps":%s,"message":%s,"time":%s}\n' "$1" "$2" "$STEPS" "$(json_text "$3")" "$(date +%s)" > "$tmp" 2>/dev/null \
    && mv -f "$tmp" "$STATUS" 2>/dev/null
}
CURRENT=0
step() { CURRENT="$1"; shift; printf '\n== %s/%s  %s\n' "$CURRENT" "$STEPS" "$*"; report running "$CURRENT" "$*"; }

# --- annullamento -------------------------------------------------------------------------------------------------------
MOVED=0; OLD_STOPPED=0; CONF_BACKUP=""; ASVC_BACKUP=""; BK=""
rollback() {
  say ""
  say "   Rimetto tutto com'era..."
  if [ "$MOVED" = 1 ] && [ -d "$NEW_REPO" ] && [ ! -d "$OLD_REPO" ]; then
    mv "$NEW_REPO" "$OLD_REPO" && good "Programma rimesso in $OLD_REPO"
  fi
  [ -n "$CONF_BACKUP" ] && [ -f "$CONF_BACKUP" ] && cp -p "$CONF_BACKUP" "$PRINTER_DATA/config/moonraker.conf"
  [ -n "$ASVC_BACKUP" ] && [ -f "$ASVC_BACKUP" ] && cp -p "$ASVC_BACKUP" "$PRINTER_DATA/moonraker.asvc"
  for n in klippeye klippeye-notifier; do
    if [ -f "$UNIT_DIR/$n.service" ] && grep -q 'GESTITO-DA-KLIPPEYE' "$UNIT_DIR/$n.service"; then
      sudo_run "$SYSTEMCTL" disable --now "$n" >/dev/null 2>&1
      sudo_run rm -f "$UNIT_DIR/$n.service"
    fi
  done
  for n in vzbot vzbot-notifier; do   # i file dei servizi vecchi, se install.sh li aveva gia' tolti
    if [ ! -f "$UNIT_DIR/$n.service" ] && [ -n "$BK" ] && [ -f "$BK/units/$n.service" ]; then sudo_run install -m 644 "$BK/units/$n.service" "$UNIT_DIR/$n.service"; fi
  done
  sudo_run "$SYSTEMCTL" daemon-reload >/dev/null 2>&1
  if [ "$OLD_STOPPED" = 1 ]; then
    sudo_run "$SYSTEMCTL" enable vzbot >/dev/null 2>&1
    sudo_run "$SYSTEMCTL" restart vzbot >/dev/null 2>&1 && good "Servizio vzbot riacceso"
    if [ -f "$UNIT_DIR/vzbot-notifier.service" ]; then
      sudo_run "$SYSTEMCTL" enable vzbot-notifier >/dev/null 2>&1
      sudo_run "$SYSTEMCTL" restart vzbot-notifier >/dev/null 2>&1
    fi
  fi
}
fail() {
  printf '\n   ERRORE  %s\n' "$*"
  rollback
  report error "$CURRENT" "$*"
  exit 1
}

say "KlippEye - passaggio da VzBot"

# --- 1. controlli -------------------------------------------------------------------------------------------------------
step 1 "Controllo che si possa fare"
[ -n "$PYTHON" ] || fail "Python 3 non c'e'."
if [ "$(id -u)" = "0" ] && [ -z "${KLIPPEYE_ALLOW_ROOT:-}" ]; then
  fail "Non lanciarmi con sudo: devo girare come l'utente normale (di solito 'pi')."
fi
case "$(basename "$OLD_REPO")" in
  vzbot|VzBot) ;;
  *) if [ -z "${KLIPPEYE_FORCE:-}" ]; then
       if [ -d "$NEW_REPO" ] && [ "$OLD_REPO" = "$NEW_REPO" ]; then
         good "Sei gia' su KlippEye ($OLD_REPO): niente da fare."
         report done "$STEPS" "Sei gia' su KlippEye: niente da fare."
         exit 0
       fi
       fail "Questa cartella ($OLD_REPO) non si chiama vzbot: non so cosa spostare."
     fi ;;
esac
[ -f "$OLD_REPO/scripts/install.sh" ] || fail "Manca $OLD_REPO/scripts/install.sh: aggiorna prima il programma dalla dashboard."
[ -f "$OLD_REPO/backend/klippeye_backend.py" ] || fail "Manca $OLD_REPO/backend/klippeye_backend.py: aggiorna prima il programma dalla dashboard (Impostazioni -> Sistema -> Aggiorna)."
if [ -e "$NEW_REPO" ]; then
  fail "Esiste gia' $NEW_REPO: non voglio sovrascriverlo. Spostalo o cancellalo e riprova."
fi
case "$OLD_REPO$NEW_REPO$OLD_DATA$NEW_DATA" in *" "*) fail "Le cartelle non devono avere spazi nel nome." ;; esac

PRINTING="$("$PYTHON" - "$MOONRAKER_URL/printer/objects/query?print_stats=state" <<'PY'
import json, sys, urllib.request
try:
    d = json.loads(urllib.request.urlopen(sys.argv[1], timeout=4).read().decode("utf-8", "replace"))
    print("yes" if d["result"]["status"]["print_stats"]["state"] in ("printing", "paused") else "no")
except Exception:
    print("no")
PY
)"
[ "$PRINTING" = "no" ] || fail "Sta stampando (o e' in pausa): riprova a fine stampa. Non ho toccato niente."
if [ -n "$SUDO" ]; then
  $SUDO -n true 2>/dev/null || fail "Serve la password di amministratore e qui non posso chiederla. Lancia il comando dal terminale:   bash $OLD_REPO/scripts/passa-a-klippeye.sh"
fi
good "Si puo' fare: programma in $OLD_REPO -> $NEW_REPO"

# --- 2. dati ------------------------------------------------------------------------------------------------------------
step 2 "Copio le tue impostazioni"
mkdir -p "$NEW_DATA" || fail "Non riesco a creare $NEW_DATA"
chmod 700 "$NEW_DATA"
if [ -d "$OLD_DATA" ] && [ "$OLD_DATA" != "$NEW_DATA" ] && [ -n "$(ls -A "$OLD_DATA" 2>/dev/null)" ]; then
  cp -an "$OLD_DATA"/. "$NEW_DATA"/ || fail "Non sono riuscito a copiare i dati da $OLD_DATA"
  : > "$NEW_DATA/.copiato-da-vzbot"
  good "Dati copiati da $OLD_DATA in $NEW_DATA (gli originali restano li')"
else
  note "Nessun dato precedente da copiare"
fi
BK="$NEW_DATA/backup/passaggio-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BK/units"

# --- 3. ferma i servizi vecchi e sposta il programma ---------------------------------------------------------------------
step 3 "Fermo VzBot e sposto il programma"
HAD_NOTIFIER=0
[ -f "$UNIT_DIR/vzbot-notifier.service" ] && HAD_NOTIFIER=1
for n in vzbot vzbot-notifier; do   # copia dei servizi vecchi: servono per tornare indietro se qualcosa va storto
  [ -f "$UNIT_DIR/$n.service" ] && cp -p "$UNIT_DIR/$n.service" "$BK/units/$n.service"
done
OLD_STOPPED=1
if [ "$HAD_NOTIFIER" = 1 ]; then sudo_run "$SYSTEMCTL" stop vzbot-notifier >/dev/null 2>&1; fi
# Non fermo "vzbot" qui se lo script e' stato lanciato proprio da lui: lo fa systemd quando il lavoro e' separato.
sudo_run "$SYSTEMCTL" stop vzbot >/dev/null 2>&1
good "Servizi vecchi fermati"
CONF="$PRINTER_DATA/config/moonraker.conf"; ASVC="$PRINTER_DATA/moonraker.asvc"
if [ -f "$CONF" ]; then CONF_BACKUP="$BK/moonraker.conf"; cp -p "$CONF" "$CONF_BACKUP"; fi
if [ -f "$ASVC" ]; then ASVC_BACKUP="$BK/moonraker.asvc"; cp -p "$ASVC" "$ASVC_BACKUP"; fi
mv "$OLD_REPO" "$NEW_REPO" || fail "Non riesco a spostare $OLD_REPO in $NEW_REPO"
MOVED=1
good "Programma spostato in $NEW_REPO"
if [ -d "$NEW_REPO/.git" ]; then
  ORIGIN="$(git -C "$NEW_REPO" remote get-url origin 2>/dev/null || true)"
  FIXED="$(printf '%s' "$ORIGIN" | sed -E 's#/[Vv]z[Bb]ot(\.git)?$#/KlippEye\1#')"
  if [ -n "$ORIGIN" ] && [ "$FIXED" != "$ORIGIN" ]; then
    git -C "$NEW_REPO" remote set-url origin "$FIXED" && good "Indirizzo GitHub aggiornato: $FIXED"
  fi
fi

# --- 4. installa KlippEye -------------------------------------------------------------------------------------------------
step 4 "Installo i servizi KlippEye"
# Prima tolgo da Moonraker la voce vecchia (punta a una cartella che non c'e' piu'): ci pensa poi install.sh a metterne una nuova.
if [ -f "$CONF" ]; then
  "$PYTHON" - "$CONF" <<'PY' || fail "Non riesco a modificare moonraker.conf"
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
  fail "L'installazione di KlippEye non e' riuscita (dettagli in $BK/install.log)."
fi
good "Servizi KlippEye installati e accesi"

# --- 5. pulizia -----------------------------------------------------------------------------------------------------------
step 5 "Tolgo i vecchi servizi e comandi"
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
good "Servizi e comandi vecchi tolti (copia in $BK)"
OLD_STOPPED=0  # da qui non si torna indietro: e' tutto a posto

# --- 6. verifica ----------------------------------------------------------------------------------------------------------
step 6 "Controllo che KlippEye risponda"
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
)" || { warn "KlippEye non risponde ancora (potrebbe volerci un minuto). Controlla con:  klippeye stato"; NEWREL=""; }
if [ -n "$NEWREL" ]; then good "KlippEye $NEWREL risponde"; fi
report done "$STEPS" "Fatto: ora sei su KlippEye ${NEWREL}. Ricarica la pagina."
say ""
say "Fatto. Ricarica la dashboard (se il browser non si aggiorna, svuota la cache)."
say "I vecchi file ($OLD_DATA) sono rimasti dove stavano: puoi cancellarli quando sei sicuro che vada tutto bene."
exit 0
