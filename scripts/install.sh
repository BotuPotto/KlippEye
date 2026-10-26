#!/usr/bin/env bash
# KlippEye - installazione sul Raspberry (si fa UNA volta; si puo' rilanciare quando si vuole, e' fatta per non rompere niente)
#
#   bash ~/klippeye/scripts/install.sh                  installa o ripara
#   bash ~/klippeye/scripts/install.sh --senza-moonraker   non tocca la configurazione di Moonraker
#   bash ~/klippeye/scripts/install.sh --annulla        torna a come era prima (servizi vecchi, niente voce nell'update manager)
#
# Cosa fa, nell'ordine:
#   1. controlla Python, git e i moduli che servono al backend
#   2. crea la cartella dei DATI (~/printer_data/klippeye: impostazioni, chiave dell'IA, notifiche) e ci COPIA quello che
#      avevi gia' (~/vzbot_ai_config.json, ~/vzbot-notifier/..., ~/printer_data/vzbot). I file vecchi restano dove sono: niente viene cancellato
#   3. installa i servizi "klippeye" (backend + dashboard) e "klippeye-notifier" (notifiche) e li fa partire a ogni accensione;
#      i servizi con i nomi di prima ("vzbot", "vzbot-notifier") vengono fermati e tolti (se ne tiene una copia);
#      se il backend nuovo non risponde rimette tutto com'era
#   4. mette i comandi "klippeye" e "klippeye-notifiche" in /usr/local/bin
#   5. collega il programma all'UPDATE MANAGER di Moonraker (moonraker.conf e moonraker.asvc): e' quello che fa funzionare
#      il tasto "Aggiorna" della dashboard e di Mainsail/Fluidd
#
# Il codice sta in una cartella sola (questa), le tue cose in un'altra: gli aggiornamenti toccano solo la prima.

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
OLD_NOTIFIER_DIR="${KLIPPEYE_OLD_NOTIFIER_DIR:-$HOME/vzbot-notifier}"   # prima di KlippEye (VzBot 1.0.x)
if [ -n "${KLIPPEYE_DATA:-}" ]; then DATA="$KLIPPEYE_DATA"
elif [ -d "$PRINTER_DATA" ]; then DATA="$PRINTER_DATA/klippeye"
else DATA="$HOME/klippeye_data"; fi

say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
good() { printf '   OK      %s\n' "$*"; }
note() { printf '           %s\n' "$*"; }
warn() { printf '   AVVISO  %s\n' "$*"; }
stop() { printf '\n   ERRORE  %s\n\n' "$*"; exit 1; }

usage() { sed -n '2,7p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

MODE=install
WITH_MOONRAKER=1
for arg in "$@"; do
  case "$arg" in
    --annulla) MODE=undo ;;
    --senza-moonraker) WITH_MOONRAKER=0 ;;
    -h|--aiuto|--help) usage; exit 0 ;;
    *) stop "Opzione sconosciuta: $arg   (prova:  bash $0 --aiuto)" ;;
  esac
done

sudo_run() { if [ -n "$SUDO" ]; then $SUDO "$@"; else "$@"; fi; }

RELEASE="$(tr -d '[:space:]' < "$REPO/VERSION" 2>/dev/null || true)"
RELEASE="${RELEASE:-sconosciuta}"
say "KlippEye $RELEASE - installazione sul Raspberry"

# --- 1. controlli -----------------------------------------------------------------------------------------------------
step "1/6  Controllo il Raspberry"
if [ "$(id -u)" = "0" ] && [ -z "${KLIPPEYE_ALLOW_ROOT:-}" ]; then
  stop "Non lanciarmi con sudo e non come utente root: devo girare come l'utente normale (di solito 'pi').
          Riprova cosi':   bash $REPO/scripts/install.sh
          (se serve la password di amministratore te la chiedo io al momento giusto)"
fi
PYTHON="${KLIPPEYE_PYTHON:-$(command -v python3 || true)}"
[ -n "$PYTHON" ] || stop "Python 3 non e' installato. Installalo con:  sudo apt install -y python3"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)' || stop "Serve Python 3.7 o piu' recente (qui c'e' $("$PYTHON" --version 2>&1))."
good "$("$PYTHON" --version 2>&1) ($PYTHON)"
case "$REPO$DATA" in *" "*) stop "Le cartelle non devono avere spazi nel nome ($REPO, $DATA)." ;; esac
[ -f "$REPO/backend/klippeye_backend.py" ] || stop "Non trovo $REPO/backend/klippeye_backend.py: questa non sembra la cartella di KlippEye."
command -v git >/dev/null 2>&1 || warn "git non c'e': senza non funzionano gli aggiornamenti. Installalo con:  sudo apt install -y git"

MISSING=""
for module in flask flask_cors requests; do
  "$PYTHON" -c "import $module" 2>/dev/null || MISSING="$MISSING $module"
done
if [ -n "$MISSING" ]; then
  warn "Al backend mancano questi moduli Python:$MISSING"
  note "Installali con:   sudo apt install -y python3-flask python3-flask-cors python3-requests"
  note "poi rilancia questo comando."
  if [ -z "${KLIPPEYE_IGNORE_MISSING:-}" ]; then stop "Senza quei moduli il backend non parte."; fi
else
  good "Moduli del backend: flask, flask_cors, requests"
fi
if "$PYTHON" -c 'import cv2, numpy' 2>/dev/null; then
  good "OpenCV e numpy (servono al monitor IA)"
else
  warn "OpenCV/numpy non ci sono: il backend parte lo stesso, ma il monitor IA non potra' analizzare la camera."
  note "Se lo vuoi:   sudo apt install -y python3-opencv python3-numpy"
fi
[ -f "$REPO/frontend/klippeye_frontend.html" ] || warn "Manca $REPO/frontend/klippeye_frontend.html: il backend parte, ma la pagina della dashboard non si apre."

WORK="$(mktemp -d "${TMPDIR:-/tmp}/klippeye-install.XXXXXX")" || stop "Non riesco a creare una cartella temporanea."
trap 'rm -rf "$WORK"' EXIT

# --- funzioni comuni ----------------------------------------------------------------------------------------------------
BK=""
bk_dir() {
  if [ -z "$BK" ]; then BK="$DATA/backup/$(date +%Y%m%d-%H%M%S)"; mkdir -p "$BK"; fi
}
backup_file() {  # file_da_salvare nome_nel_backup
  bk_dir
  mkdir -p "$(dirname "$BK/$2")"
  cp -p "$1" "$BK/$2" 2>/dev/null || sudo_run cp -p "$1" "$BK/$2"
}
oldest_backup_of() {  # nome_nel_backup -> percorso del backup piu' vecchio che lo contiene
  local d
  for d in $(ls -1d "$DATA"/backup/*/ 2>/dev/null | sort); do
    if [ -f "${d}$1" ]; then printf '%s\n' "${d}$1"; return 0; fi
  done
  return 1
}
brain_release() {  # secondi_massimi -> stampa la release se il backend risponde entro quel tempo
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
is_printing() {  # 0 se Moonraker dice che sta stampando (o e' in pausa)
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

render_unit() {  # modello destinazione
  sed -e "s|@UTENTE@|$RUN_USER|g" -e "s|@CODICE@|$REPO|g" -e "s|@DATI@|$DATA|g" -e "s|@PYTHON@|$PYTHON|g" "$1" > "$2"
}
install_unit() {  # nome (senza .service): 0 = installato o cambiato, 1 = gia' uguale
  local name="$1" dest="$UNIT_DIR/$1.service" tmp="$WORK/$1.service"
  render_unit "$REPO/systemd/$name.service" "$tmp"
  if [ -f "$dest" ] && cmp -s "$tmp" "$dest"; then return 1; fi
  if [ -f "$dest" ] && ! grep -q 'GESTITO-DA-KLIPPEYE' "$dest"; then backup_file "$dest" "units/$name.service"; fi
  sudo_run install -m 644 "$tmp" "$dest" || stop "Non riesco a scrivere $dest (serve la password di amministratore?)."
  return 0
}
OLD_UNIT_NAMES="vzbot vzbot-notifier"   # i servizi di prima di KlippEye
RETIRED=""
retire_old_units() {  # ferma e toglie i servizi vecchi (con copia nel backup); $1 = "tutti" oppure "senza-notifiche"
  local name f
  for name in $OLD_UNIT_NAMES; do
    f="$UNIT_DIR/$name.service"
    [ -f "$f" ] || continue
    if [ "$name" = "vzbot-notifier" ] && [ "${1:-tutti}" = "senza-notifiche" ]; then
      warn "Lascio acceso il vecchio servizio $name: le notifiche nuove non sono ancora configurate."
      continue
    fi
    backup_file "$f" "units/$name.service"
    sudo_run "$SYSTEMCTL" disable --now "$name" >/dev/null 2>&1
    sudo_run rm -f "$f"
    RETIRED="$RETIRED $name"
    good "Servizio vecchio $name fermato e tolto (copia nel backup)"
  done
  [ -n "$RETIRED" ] && sudo_run "$SYSTEMCTL" daemon-reload
}
bring_back_old_units() {  # rimette i servizi vecchi dalle copie del backup e li accende; 0 se ne ha rimesso almeno uno
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
    if [ -f "$UNIT_DIR/$name.service" ] && grep -q 'GESTITO-DA-KLIPPEYE' "$UNIT_DIR/$name.service"; then
      sudo_run "$SYSTEMCTL" disable --now "$name" >/dev/null 2>&1
      sudo_run rm -f "$UNIT_DIR/$name.service"
    fi
  done
  sudo_run "$SYSTEMCTL" daemon-reload
}

install_command() {  # nome: scrive /usr/local/bin/<nome>, che lancia lo script dentro la cartella del programma
  local name="$1" tmp="$WORK/cmd-$1"
  printf '#!/bin/sh\n# scritto da %s/scripts/install.sh\nexec bash "%s/scripts/%s" "$@"\n' "$REPO" "$REPO" "$name" > "$tmp"
  if [ -f "$BIN_DIR/$name" ] && cmp -s "$tmp" "$BIN_DIR/$name"; then return 0; fi
  sudo_run install -m 755 "$tmp" "$BIN_DIR/$name" || { warn "Non riesco a scrivere $BIN_DIR/$name"; return 1; }
}
notifier_ready() {  # 0 se c'e' notifier.json e la chiave Firebase a cui punta
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
#  --annulla
# ====================================================================================================================
if [ "$MODE" = "undo" ]; then
  step "Annullo KlippEye $RELEASE: torno ai servizi di prima"
  stop_new_units
  good "Servizi klippeye e klippeye-notifier fermati e tolti"
  if bring_back_old_units; then
    good "Servizi di prima (vzbot, vzbot-notifier) rimessi com'erano e riaccesi"
  else
    note "Non c'erano servizi di prima da rimettere (KlippEye e' stato installato da zero)."
  fi
  for name in klippeye klippeye-notifiche; do
    if [ -f "$BIN_DIR/$name" ] && grep -q "$REPO/scripts" "$BIN_DIR/$name" 2>/dev/null; then sudo_run rm -f "$BIN_DIR/$name"; fi
  done
  good "Comandi $BIN_DIR/klippeye e klippeye-notifiche tolti"
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
text = re.sub(r"\n\n+# KlippEye: aggiornamenti dalla dashboard[^\n]*\n*$", "\n", text)
open(p, "w", encoding="utf-8").write(text)
PY
      good "Voce [update_manager klippeye] tolta da moonraker.conf"
    fi
    if [ -f "$asvc" ]; then
      backup_file "$asvc" moonraker.asvc
      grep -vx -e klippeye -e klippeye-notifier "$asvc" > "$WORK/asvc" ; cat "$WORK/asvc" > "$asvc"
      good "klippeye e klippeye-notifier tolti da moonraker.asvc"
    fi
    if is_printing; then
      warn "Sta stampando: non riavvio Moonraker. Riavvialo tu a fine stampa (menu Riavvia della dashboard) per far sparire la voce."
    else
      sudo_run "$SYSTEMCTL" restart "$MOONRAKER_SERVICE" && good "Moonraker riavviato"
    fi
  fi
  say ""
  say "Fatto. La cartella del programma ($REPO) e quella dei dati ($DATA) sono rimaste dove sono:"
  say "se non ti servono piu' le cancelli tu a mano."
  exit 0
fi

# ====================================================================================================================
#  installazione
# ====================================================================================================================

# --- 2. dati e impostazioni --------------------------------------------------------------------------------------------
step "2/6  Cartella dei dati: $DATA"
mkdir -p "$DATA" || stop "Non riesco a creare $DATA"
chmod 700 "$DATA"
# Se prima c'era VzBot 1.0.x, la sua cartella dati (stesso contenuto) viene COPIATA qui senza sovrascrivere nulla.
if [ -n "${KLIPPEYE_OLD_DATA:-}" ]; then OLD_DATA="$KLIPPEYE_OLD_DATA"
elif [ -d "$PRINTER_DATA/vzbot" ]; then OLD_DATA="$PRINTER_DATA/vzbot"
else OLD_DATA="$HOME/vzbot_data"; fi
if [ -d "$OLD_DATA" ] && [ "$OLD_DATA" != "$DATA" ] && [ -n "$(ls -A "$OLD_DATA" 2>/dev/null)" ] && [ ! -f "$DATA/.copiato-da-vzbot" ]; then
  if cp -an "$OLD_DATA"/. "$DATA"/ 2>/dev/null; then
    : > "$DATA/.copiato-da-vzbot"
    good "Impostazioni e dati di VzBot copiati da $OLD_DATA (gli originali restano li')"
  else
    warn "Non sono riuscito a copiare i dati da $OLD_DATA"
  fi
fi
good "Qui restano impostazioni, chiave dell'IA e notifiche. Gli aggiornamenti non la toccano."

if [ -d "$REPO/.git" ]; then
  # I file caricati dal sito di GitHub non hanno il permesso "eseguibile": senza questa riga git li vedrebbe "modificati"
  # appena li rendi eseguibili e l'update manager di Moonraker si rifiuterebbe di aggiornare.
  git -C "$REPO" config core.fileMode false 2>/dev/null
fi

AI_OLD="${KLIPPEYE_OLD_AI_CONFIG:-$HOME/vzbot_ai_config.json}"   # prima di KlippEye (VzBot 1.0.x)
if [ -f "$DATA/ai.json" ]; then
  chmod 600 "$DATA/ai.json"
  good "Chiave dell'IA: gia' nella cartella dati"
elif [ -f "$AI_OLD" ]; then
  cp "$AI_OLD" "$DATA/ai.json" && chmod 600 "$DATA/ai.json" && good "Chiave dell'IA copiata da $AI_OLD (l'originale resta li')"
else
  note "Chiave dell'IA: non ce n'e' ancora una (si inserisce dalla dashboard)"
fi

if [ -f "$DATA/notifier.json" ]; then
  good "Notifiche: configurazione gia' nella cartella dati"
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
  then good "Notifiche: configurazione e chiave Firebase copiate da $OLD_NOTIFIER_DIR (gli originali restano li')"
  else warn "Non sono riuscito a copiare la configurazione delle notifiche da $OLD_NOTIFIER_DIR"; fi
else
  note "Notifiche: non configurate (si fa una volta sola con la guida; vedi docs/GUIDA.md)"
fi

# --- 3. servizi --------------------------------------------------------------------------------------------------------
step "3/6  Servizi (partono da soli a ogni accensione)"
for need in "$REPO/systemd/klippeye.service" "$REPO/systemd/klippeye-notifier.service"; do
  [ -f "$need" ] || stop "Manca il modello $need"
done
[ -d "$UNIT_DIR" ] || stop "Non trovo la cartella dei servizi di sistema ($UNIT_DIR)."

NOTIFIER_ON=0
if notifier_ready; then NOTIFIER_ON=1; fi
# I servizi di prima usano la stessa porta e gli stessi dati: vanno fermati prima di accendere quelli nuovi.
if [ "$NOTIFIER_ON" = 1 ]; then retire_old_units tutti; else retire_old_units senza-notifiche; fi
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
sudo_run "$SYSTEMCTL" daemon-reload || stop "systemctl daemon-reload non e' riuscito."
sudo_run "$SYSTEMCTL" enable klippeye >/dev/null 2>&1
[ "$NOTIFIER_ON" = 1 ] && sudo_run "$SYSTEMCTL" enable klippeye-notifier >/dev/null 2>&1

if [ "$BRAIN_CHANGED" = 1 ] || ! unit_active klippeye; then
  sudo_run "$SYSTEMCTL" restart klippeye || warn "systemctl restart klippeye ha dato errore"
  printf '   ...     aspetto che il backend risponda (fino a 40 secondi)\n'
  if NEWREL="$(brain_release 40)"; then
    good "Il backend risponde: release $NEWREL"
  else
    printf '\n   ERRORE  Il backend nuovo non risponde su %s.\n' "$BRAIN_URL"
    note "Ultime righe del suo registro:"
    (journalctl -u klippeye -n 12 --no-pager 2>/dev/null || sudo_run journalctl -u klippeye -n 12 --no-pager 2>/dev/null) | sed 's/^/           /'
    stop_new_units
    if bring_back_old_units; then
      note "Ho rimesso i servizi com'erano: il backend di prima dovrebbe essere di nuovo acceso."
    fi
    stop "Installazione interrotta. Se la porta 8085 e' occupata da un altro programma, fermalo e rilancia. Se manca un modulo Python, vedi sopra."
  fi
else
  good "Servizio klippeye gia' a posto"
fi

if [ "$NOTIFIER_ON" = 1 ]; then
  if [ "$NOTIFIER_CHANGED" = 1 ] || ! unit_active klippeye-notifier; then
    sudo_run "$SYSTEMCTL" restart klippeye-notifier || warn "systemctl restart klippeye-notifier ha dato errore"
  fi
  good "Servizio klippeye-notifier acceso"
  if "$PYTHON" "$REPO/notifier/klippeye_notifier.py" --config "$DATA/notifier.json" --check >"$WORK/check.out" 2>&1; then
    good "Controllo delle notifiche superato"
  else
    warn "Il controllo delle notifiche segnala qualcosa (vedi sotto). Il backend e la dashboard funzionano lo stesso."
    sed 's/^/           /' "$WORK/check.out" | tail -n 8
  fi
else
  note "Notifiche: il servizio si accende solo dopo aver messo la chiave di Firebase in $DATA (guida: docs/GUIDA.md)"
fi

# --- 4. comandi --------------------------------------------------------------------------------------------------------
step "4/6  Comandi da terminale"
if install_command klippeye && install_command klippeye-notifiche; then
  good "Scritti $BIN_DIR/klippeye e $BIN_DIR/klippeye-notifiche   (prova:  klippeye stato)"
fi

# --- 5. Moonraker --------------------------------------------------------------------------------------------------------
step "5/6  Aggiornamenti dalla dashboard (update manager di Moonraker)"
MR_RESTART=0
if [ "$WITH_MOONRAKER" = 0 ]; then
  note "Saltato (--senza-moonraker)."
else
  CONF="$PRINTER_DATA/config/moonraker.conf"
  ASVC="$PRINTER_DATA/moonraker.asvc"
  ORIGIN=""; BRANCH=""
  if [ -d "$REPO/.git" ]; then
    ORIGIN="$(git -C "$REPO" remote get-url origin 2>/dev/null || true)"
    BRANCH="$(git -C "$REPO" symbolic-ref --short HEAD 2>/dev/null || true)"
  fi
  if [ ! -d "$REPO/.git" ]; then
    warn "$REPO non e' un repository git (l'hai scaricato come zip?). Senza, il tasto Aggiorna non puo' funzionare."
    note "Rifai l'installazione con:   git clone <indirizzo del tuo repository GitHub> ~/klippeye"
  elif [ -z "$ORIGIN" ]; then
    warn "Il repository non ha un 'origin' (un indirizzo GitHub da cui aggiornarsi): salto la configurazione di Moonraker."
  else
    [ -n "$BRANCH" ] || { BRANCH=main; warn "Non riconosco il ramo corrente, uso 'main'."; }
    if [ ! -f "$CONF" ]; then
      warn "Non trovo $CONF: salto la configurazione di Moonraker (se il tuo e' altrove: KLIPPEYE_PRINTER_DATA=... bash $0)."
    else
      if grep -Eq '^\[update_manager[[:space:]]+klippeye\][[:space:]]*$' "$CONF"; then
        good "moonraker.conf ha gia' la voce [update_manager klippeye]"
      else
        backup_file "$CONF" moonraker.conf
        {
          printf '\n'
          if ! grep -Eq '^\[update_manager[[:space:]]*\][[:space:]]*$' "$CONF"; then
            printf '[update_manager]\n\n'
          fi
          printf '# KlippEye: aggiornamenti dalla dashboard (Impostazioni -> Sistema KlippEye) e da Mainsail/Fluidd. Scritto da scripts/install.sh.\n'
          printf '[update_manager klippeye]\ntype: git_repo\npath: %s\norigin: %s\nprimary_branch: %s\nchannel: dev\nmanaged_services: klippeye\ninfo_tags:\n  desc=KlippEye: backend, dashboard e notifiche\n' "$REPO" "$ORIGIN" "$BRANCH"
        } >> "$CONF"
        good "Aggiunta a moonraker.conf la voce [update_manager klippeye]"
        MR_RESTART=1
      fi
    fi
    if [ ! -f "$ASVC" ]; then
      warn "Non trovo $ASVC (l'elenco dei servizi che Moonraker puo' riavviare): senza, Moonraker non riavvia 'klippeye' dopo un aggiornamento."
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
      if [ -n "$ADDED" ]; then good "Aggiunti a moonraker.asvc:$ADDED"; MR_RESTART=1; else good "moonraker.asvc a posto"; fi
    fi
  fi

  if [ "$MR_RESTART" = 1 ]; then
    if is_printing; then
      warn "Sta stampando: non riavvio Moonraker adesso. A fine stampa riavvialo dal menu Riavvia della dashboard (o Mainsail)"
      note "e solo allora il tasto Aggiorna sara' attivo."
    else
      sudo_run "$SYSTEMCTL" restart "$MOONRAKER_SERVICE" || warn "Non sono riuscito a riavviare Moonraker: riavvialo dal menu Riavvia."
      printf '   ...     aspetto Moonraker\n'
      "$PYTHON" - "$MOONRAKER_URL/server/info" <<'PY' || warn "Moonraker non ha ancora risposto: potrebbe volerci un minuto."
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
      good "Moonraker riavviato"
    fi
  fi

  # Moonraker riconosce KlippEye?
  "$PYTHON" - "$MOONRAKER_URL/machine/update/status?refresh=false" <<'PY'
import json, sys, urllib.request
try:
    d = json.loads(urllib.request.urlopen(sys.argv[1], timeout=20).read().decode("utf-8", "replace"))
    info = d["result"]["version_info"].get("klippeye")
except Exception as e:
    print("   AVVISO  Non riesco a chiedere a Moonraker se vede KlippEye (%s)." % e); sys.exit(0)
if not info:
    print("   AVVISO  Moonraker non mostra ancora KlippEye tra i programmi aggiornabili: riavvialo (menu Riavvia) e riguarda tra poco.")
elif info.get("is_valid") is False or info.get("is_dirty"):
    print("   AVVISO  Moonraker vede KlippEye ma lo segna come non aggiornabile: %s" % "; ".join(info.get("warnings") or ["file modificati a mano"]))
else:
    print("   OK      Moonraker vede KlippEye (versione %s): il tasto Aggiorna e' attivo" % info.get("version", "?"))
PY
fi

# --- 6. fine -------------------------------------------------------------------------------------------------------------
step "6/6  Fatto"
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
say "   KlippEye $RELEASE e' installato."
say "   Dashboard:   http://${IP:-<indirizzo del Raspberry>}:8085"
say "   Per aggiornare in futuro: carica i file nuovi su GitHub, poi nella dashboard apri"
say "   Impostazioni -> Sistema KlippEye -> Controlla -> Aggiorna. Dal terminale basta  klippeye stato."
[ -n "$BK" ] && say "   Copie di sicurezza di quello che ho cambiato: $BK"
exit 0
