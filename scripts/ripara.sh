#!/usr/bin/env bash
# KlippEye - autoriparazione dei file del programma dopo uno spegnimento improvviso (blackout, spina staccata).
#
# Se la corrente salta mentre il Raspberry scrive, un file puo' restare vuoto o a meta': il backend allora parte ma la dashboard
# resta bianca (o non parte per niente). Questo script confronta i file del programma con quelli che git ha in memoria (la copia
# "buona" sta nella cartella .git, sul Raspberry stesso, quindi NON serve internet) e rimette a posto solo quelli rovinati o mancanti.
#
# Si lancia da solo: a ogni avvio del servizio (riga ExecStartPre di klippeye.service), all'avvio del backend e quando la pagina della
# dashboard risulta rovinata. A mano:  klippeye ripara
#
# Non tocca: le tue impostazioni, la chiave dell'IA, le notifiche (stanno in ~/printer_data/klippeye, fuori dal programma).
# Per spegnerlo (se lavori sui file a mano) basta creare un file vuoto:  ~/printer_data/klippeye/non-riparare
#
# Scrive cosa ha fatto in <cartella dati>/riparazioni.log e, se ha ripristinato qualcosa, in <cartella dati>/ripristino.json
# (lo legge la dashboard). Esce sempre con 0: non deve mai impedire l'avvio del servizio.

REPO="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
if [ -n "${KLIPPEYE_DATA:-}" ]; then DATA="$KLIPPEYE_DATA"
elif [ -d "$HOME/printer_data/vzbot" ] && [ ! -d "$HOME/printer_data/klippeye" ]; then DATA="$HOME/printer_data/vzbot"
elif [ -d "$HOME/printer_data" ]; then DATA="$HOME/printer_data/klippeye"
else DATA="$HOME/klippeye_data"; fi
LOG="$DATA/riparazioni.log"
MARK="$DATA/ripristino.json"
QUIET=0; ATTIVA=0
for A in "$@"; do case "$A" in --silenzioso) QUIET=1 ;; --attiva-avvio) ATTIVA=1 ;; esac; done

log() {
  local line; line="$(date '+%Y-%m-%d %H:%M:%S') $*"
  [ "$QUIET" = 1 ] || printf '%s\n' "$*"
  mkdir -p "$DATA" 2>/dev/null && printf '%s\n' "$line" >> "$LOG" 2>/dev/null \
    && [ "$(wc -l < "$LOG" 2>/dev/null || echo 0)" -gt 300 ] && { tail -n 150 "$LOG" > "$LOG.tmp" && mv -f "$LOG.tmp" "$LOG"; }
  return 0
}

# --attiva-avvio: fa partire il controllo anche PRIMA del backend (riga ExecStartPre del servizio). Il servizio installato con la 1.0.x
# o con la 1.1.0 non ce l'ha: la aggiungiamo come "integrazione" (cartella klippeye.service.d), una volta, se il sistema lo permette
# senza password. Con scripts/install.sh la riga arriva direttamente nel file del servizio e l'integrazione viene tolta.
attiva_avvio() {
  local unit dir cat tmp sudo_cmd
  unit=klippeye; case "$(basename "$REPO")" in vzbot|VzBot) unit=vzbot ;; esac
  dir="${KLIPPEYE_SYSTEMD_DIR:-/etc/systemd/system}"
  cat="$("${KLIPPEYE_SYSTEMCTL:-systemctl}" cat "$unit" 2>/dev/null)" || return 0   # nessun servizio con questo nome: niente da fare
  case "$cat" in *ripara.sh*) return 0 ;; esac                                      # c'e' gia'
  sudo_cmd="${KLIPPEYE_SUDO-sudo}"; [ -n "$sudo_cmd" ] && sudo_cmd="$sudo_cmd -n"
  tmp="$(mktemp)" || return 0
  printf '[Service]\nExecStartPre=-/bin/bash %s/scripts/ripara.sh --silenzioso\n' "$REPO" > "$tmp"
  if $sudo_cmd mkdir -p "$dir/$unit.service.d" 2>/dev/null && $sudo_cmd install -m 644 "$tmp" "$dir/$unit.service.d/ripara.conf" 2>/dev/null \
     && $sudo_cmd "${KLIPPEYE_SYSTEMCTL:-systemctl}" daemon-reload 2>/dev/null; then
    log "Attivato il controllo dei file a ogni avvio del servizio $unit (vale dal prossimo avvio)."
  elif [ ! -e "$DATA/.avvio-non-attivabile" ]; then
    : > "$DATA/.avvio-non-attivabile" 2>/dev/null
    log "Non riesco ad attivare il controllo prima dell'avvio (serve l'amministratore senza password). Per attivarlo: bash $REPO/scripts/install.sh"
  fi
  rm -f "$tmp"
}

[ -e "$DATA/non-riparare" ] && { [ "$QUIET" = 1 ] || echo "Autoriparazione spenta (file $DATA/non-riparare)."; exit 0; }
[ "$ATTIVA" = 1 ] && { attiva_avvio; exit 0; }
command -v git >/dev/null 2>&1 || exit 0
[ -d "$REPO/.git" ] || exit 0   # copiato a mano senza git: niente da confrontare

# Un aggiornamento (git) sta lavorando proprio ora (o Moonraker sta controllando lo stato del repository, cosa che dura un attimo):
# aspetto fino a 10 secondi che finisca. Un blocco vecchio rimasto da un blackout invece si toglie.
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
    [ "$QUIET" = 1 ] || echo "Git sta lavorando (blocco di ${AGE}s): riprova fra poco."
    exit 0
  fi
  rm -f "$LOCK" && log "Tolto il blocco di git rimasto da uno spegnimento improvviso (vecchio di ${AGE}s)."
fi

if ! git -C "$REPO" rev-parse --verify -q 'HEAD^{commit}' >/dev/null 2>&1; then
  log "ERRORE: la memoria di git in $REPO e' rovinata: non posso confrontare i file. Rimedio: Mainsail -> Machine -> Update Manager -> klippeye -> Recover (hard), oppure da terminale: klippeye aggiorna --forza"
  exit 0
fi

# Confronto: l'impronta di ogni file del programma con quella che git ha per la release installata.
BAD=()
while IFS= read -r -d '' ENTRY; do
  META="${ENTRY%%$'\t'*}"; FILE="${ENTRY#*$'\t'}"
  read -r MODE TYPE SHA <<< "$META"
  [ "$TYPE" = blob ] && [ "$MODE" != 120000 ] || continue
  if [ ! -f "$REPO/$FILE" ]; then BAD+=("$FILE"); continue; fi
  [ "$(git -C "$REPO" hash-object --no-filters -- "$REPO/$FILE" 2>/dev/null)" = "$SHA" ] || BAD+=("$FILE")
done < <(git -C "$REPO" ls-tree -r -z HEAD -- backend frontend notifier scripts systemd brain apk VERSION 2>/dev/null)

if [ "${#BAD[@]}" = 0 ]; then
  [ "$QUIET" = 1 ] || echo "Tutti i file del programma sono integri."
  exit 0
fi

log "File rovinati o mancanti (${#BAD[@]}): ${BAD[*]}"
ERR="$(git -C "$REPO" checkout HEAD -- "${BAD[@]}" 2>&1)" || log "git non riesce a rimetterli a posto: ${ERR:0:300}"
sync 2>/dev/null

DONE=(); FAILED=()
for FILE in "${BAD[@]}"; do
  SHA="$(git -C "$REPO" rev-parse "HEAD:$FILE" 2>/dev/null)"
  if [ -f "$REPO/$FILE" ] && [ "$(git -C "$REPO" hash-object --no-filters -- "$REPO/$FILE" 2>/dev/null)" = "$SHA" ]; then DONE+=("$FILE"); else FAILED+=("$FILE"); fi
done
[ "${#DONE[@]}" = 0 ] || log "Ripristinati (${#DONE[@]}): ${DONE[*]}"
if [ "${#FAILED[@]}" != 0 ]; then
  log "NON riusciti (${#FAILED[@]}): ${FAILED[*]} - rimedio: Mainsail -> Machine -> Update Manager -> klippeye -> Recover (hard), oppure da terminale: klippeye aggiorna --forza"
fi

json_list() { local out="" f; for f in "$@"; do out="${out:+$out,}\"$f\""; done; printf '[%s]' "$out"; }
mkdir -p "$DATA" 2>/dev/null
printf '{"time":%s,"restored":%s,"failed":%s}\n' "$(date +%s)" "$(json_list "${DONE[@]}")" "$(json_list "${FAILED[@]}")" > "$MARK.tmp" 2>/dev/null && mv -f "$MARK.tmp" "$MARK" 2>/dev/null
exit 0
