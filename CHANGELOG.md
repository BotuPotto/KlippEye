# Changelog (Cosa cambia in ogni release)

## 1.6.0

**The AI speaks your language.**

* The AI monitor's request is written in English and asks the AI to write what it sees (observation, notes, summary)
  in the language of the notifications (*Settings → Notifications*). The analyses started from the dashboard (print
  picture, logs) answer in the language of the dashboard on that device.
* The AI's advice is now `CONTINUE` / `PAUSE` / `CANCEL`; the dashboard shows it in its own language (`CONTINUA` /
  `PAUSA` / `CANCELLA` in Italian). Answers and alerts written the Italian way by older releases are still understood,
  also by the notification service (1.4).
* The prompts no longer name a specific printer: they work for any Klipper printer.
* The backend translates its own messages with the dashboard's dictionaries (`bt()`, checked by `frontend/tools/i18n.py check`).

## 1.5.0

**Notifications in your language.**

* The push notifications are in English or Italian: **Settings → Notifications → Language of the notifications**, one
  choice for every phone (the dashboard's own language stays per device). The list of notifications in that page shows
  the texts exactly as the phones will get them.
* Existing installs keep Italian notifications: the first time a dashboard of this release opens, it saves its own
  language as the notifications' language. Until then (or without any dashboard) the notifications are in English, or in
  the language written as `"language": "it"` in `notifier.json`. Texts written in `notifier.json` (`"messages"`) still win.
* The notification service (`klippeye-notifier`, 1.3) writes its log and its `--check` / `--test` answers in English.

## 1.4.0

**The dashboard speaks English and Italian.**

* Every text of the dashboard is now written in English and translated: Italian is the first translation
  (`frontend/src/i18n/it.json`). The page follows the language of the device (an Italian phone gets Italian, any other
  language gets English) and **Settings → Language** lets you choose on each device (*Automatic*, *English*, *Italiano*).
  The choice stays on that device only; changing it reloads the page.
* Dates, times and numbers follow the chosen language too.
* The names and explanations of the AI monitor thresholds come from the backend in English and are shown in the page's
  language; the backend's error messages for the thresholds are in English.
* For translators: texts are marked with `tx("English text")` in `frontend/src/app`; `python3 frontend/tools/i18n.py check`
  (also run by the tests) fails when a text has no translation. A new language is one more `src/i18n/<code>.json` file
  plus one line in `I18N_LANGUAGES` (`src/app/02-i18n.js`).
* Still in Italian, to be translated next: the push notifications, the AI analysis texts and the messages of the move from VzBot.

## 1.3.0

English names on the Raspberry (first step of the move to English; the dashboard text comes next):

* **`klippeye` commands in English**: `status`, `version`, `log [notifier]`, `restart [backend|notifier|all]`, `repair [log]`,
  `update [--force]`, `notify test|check`, `undo-install`, `help`. The Italian names (`stato`, `riavvia`, `aggiorna`, `ripara`,
  `notifiche prova`, `annulla`...) still work. `klippeye-notifiche` accepts `test | check | status | log | restart | uninstall` too.
* **Self-repair** is now `scripts/repair.sh` (`--quiet`, `--enable-at-start`); `scripts/ripara.sh` stays as a wrapper for the services
  installed by older releases. Its files are `repair.log`, `repair.json` and the opt-out `no-repair`.
* **Data folder, English names**: `monitor.json` (AI monitor thresholds, was `brain.json`), `alerts/history.jsonl` and pictures
  `*-now.jpg` / `*-before.jpg` (was `allarmi/storico.jsonl`, `-adesso`, `-prima`), damaged copies `*.damaged-<time>`.
  **Existing files are renamed automatically** at the first start, nothing is lost; old alert entries are read with the new keys
  (`outcome`, `observation`, `with_reference`, `filter`, `original_action`).
* `apk/versione.json` is now `apk/version.json`.
* `install.sh` removes both the old (`ripara.conf`) and the new (`repair.conf`) self-repair drop-in when it rewrites the service.

## Repository changes after 1.2.0

Almost only the repository; on the Raspberry the only change is a minimum space between the printer name and the round
buttons of the top bar (on 360-pixel phones they could touch).

* **License: GNU GPL v3.0** (`LICENSE`), the same as Klipper, Moonraker, Mainsail and Fluidd; third-party components in `THIRD_PARTY_NOTICES.md`.
* **Dashboard sources** are now in the repository (`frontend/src`, `frontend/build.py`): the published `frontend/klippeye_frontend.html`
  is rebuilt from them and the tests check it is identical.
* **Automatic tests** in `tests/` (backend, notifier, app build steps, dashboard in the browser) and a GitHub workflow that runs
  them on every pull request (`.github/workflows/tests.yml`). Run them locally with `bash tests/run_all.sh`.
* `SECURITY.md`, `CONTRIBUTING.md`, issue and pull-request templates; `README.md` in English.
* From now on code, commands, file names, commit messages and documentation are written in English; the existing Italian
  parts will be translated step by step (the dashboard will get English and Italian).

## 1.2.0

* **Password facoltativa** (*Impostazioni → Accesso*): spenta di serie, quindi tutto funziona come prima finché non la attivi. Con la password attiva ogni dispositivo
  (browser o app) la chiede una volta e la ricorda per 6 mesi; senza accesso il backend non apre niente: dashboard, camera, comandi, file, log e il ponte verso Moonraker.
  Dal menu: attivarla, cambiarla, toglierla, far uscire gli altri dispositivi, uscire da questo. Dal Raspberry: `klippeye password` (set), `klippeye password remove`
  (password dimenticata), `klippeye password status`, `klippeye password logout-all`. Non viene mai salvata la password, solo il suo «hash» con sale in
  `~/printer_data/klippeye/access.json` (permessi 600). Dopo 5 tentativi sbagliati dallo stesso indirizzo bisogna aspettare (da 2 secondi a 5 minuti).
* **Controlli di rete, sempre attivi** (anche senza password): il backend risponde solo se lo chiami con un indirizzo IP, il nome del Raspberry o un nome della rete
  di casa (`.local`, `.lan`…), e rifiuta i comandi che arrivano da pagine di altri siti. Niente più CORS «aperto a tutti». Per un nome tuo (es. un dominio):
  `klippeye access host-add NOME`; per tornare al comportamento di prima: `klippeye access network-checks off`.
* **I servizi del Raspberry** (notifiche, comando `klippeye`) si presentano al backend con un gettone interno (`internal.token`, permessi 600): le notifiche
  dell'IA funzionano anche con la password attiva.
* **Permessi dei segreti**: all'avvio il backend riporta a 600 `ai.json`, `service-account.json`, `notifier.json`, `access.json` e alla cartella dati 700
  se qualcuno li ha copiati a mano con permessi larghi (lo scrive nel log).
* La chiave dell'IA nella dashboard si vede solo nelle ultime 4 lettere (prima anche le prime 8).
* **App Android 1.2.0**: i download (log, file, immagini) mandano il cookie di accesso; il cookie resta salvato anche se Android chiude l'app.
* Nomi tecnici nuovi in inglese, in vista della distribuzione: file `access.json` e `internal.token`, pagina `/login`, comandi `klippeye password set|remove|status|logout-all`
  e `klippeye access host-add|host-remove|network-checks|status`. La pagina di accesso e i messaggi di rifiuto sono in inglese, o in italiano se il dispositivo è in italiano.
* `flask_cors` non serve più (resta facoltativo, solo per sviluppo con `KLIPPEYE_CORS`).

## 1.1.1

* **Monitor IA con meno falsi allarmi**: il confronto non usa più solo la foto precedente ma uno sfondo calcolato su più foto (la mediana di 7 foto, coperte per circa un minuto), perciò
  la testina e i passaggi veloci spariscono dallo sfondo; ignora i cambi di luce (se più del 30% dell'immagine cambia di colpo, quel controllo non conta) e normalizza la luminosità;
  un cambiamento conta solo se **resta** per alcuni controlli di fila; all'IA online va anche la foto di riferimento (prima) con un testo neutro; se l'IA non è abbastanza sicura
  (fiducia sotto il 70%) il problema non viene segnalato. Nuovo **storico degli allarmi** con le immagini in `~/printer_data/klippeye/allarmi/`
  (`/api/print/alerts/history`). Tutte le soglie si regolano da *Impostazioni → Monitor IA*; «Ignora i movimenti passeggeri» spento riporta il comportamento di prima.
* Corretto: dopo «spegni e riaccendi» il monitor poteva avere per qualche secondo due cicli di controllo insieme; ora il vecchio ciclo si ferma subito.
* App Android: invariata (1.1.0).

## 1.1.0

* **Riparazione automatica dopo un blackout**: se la corrente salta e un file del programma resta vuoto o a metà (dashboard bianca, servizio che non parte), a ogni avvio
  `scripts/ripara.sh` confronta i file con la copia buona che git ha sul Raspberry (niente internet) e rimette a posto solo quelli rovinati o spariti, toglie anche il blocco di git
  rimasto. Parte prima del servizio (`ExecStartPre`), all'avvio del backend e quando la pagina risulta vuota/troncata (che mostra intanto una pagina d'emergenza 503 che si ricarica
  da sola). Il servizio già installato riceve la riga da solo (integrazione `klippeye.service.d/ripara.conf`) se il sistema lo permette senza password; `install.sh` la rende definitiva.
  Non tocca dati e impostazioni; si spegne con un file vuoto `~/printer_data/klippeye/non-riparare`. Nuovo comando `klippeye ripara [log]`, registro `riparazioni.log`, campo `repair` in `/api/version`.
  Guida: parte G.
**Il progetto si chiama KlippEye** (prima VzBot), in tutto: cartelle, file, servizi, comandi, dashboard e app.

* **Passaggio con un tasto**: chi ha VzBot 1.0.x aggiorna come sempre, poi in *Impostazioni → Aggiornamenti* compare **Passa a KlippEye** (o da terminale:
  `bash ~/vzbot/scripts/passa-a-klippeye.sh`). In 6 passi, con ripristino automatico se qualcosa non va: copia i dati (`~/printer_data/vzbot` → `klippeye`, gli originali
  restano), sposta il programma da `~/vzbot` a `~/klippeye`, installa i servizi `klippeye` e `klippeye-notifier`, aggiorna la voce di Moonraker (`[update_manager klippeye]`
  e `moonraker.asvc`), toglie i servizi e i comandi vecchi (con copia di sicurezza) e controlla che il backend risponda.
* **Nuovi nomi** — cartelle: `backend/` (era `brain/`), `frontend/` (era `dashboard/`), `logos/`; file: `klippeye_backend.py`, `klippeye_frontend.html`, `klippeye_notifier.py`;
  servizi: `klippeye`, `klippeye-notifier`; comandi: `klippeye`, `klippeye-notifiche`; cartella dati `~/printer_data/klippeye`; variabili `KLIPPEYE_*`; segreto GitHub `KLIPPEYE_CHIAVE_PASSWORD`
  (il vecchio `VZBOT_CHIAVE_PASSWORD` vale ancora). In codice e nomi di file i nomi sono in minuscolo (`klippeye`), nei testi `KlippEye`.
  I file vecchi (`brain/vzbot_brain.py`, `notifier/vzbot_notifier.py`, `scripts/vzbot*`) restano come rimandi ai nuovi finché serve il passaggio: dopo si possono cancellare.
* **Stampante: nome e logo** (*Impostazioni → Stampante*): scegli il logo della barra in alto tra **KlippEye** (predefinito), **VzBot**, **Voron** e **RatRig** e, se vuoi, un nome tuo
  (per esempio `VzBot.287`). Cambiano anche il **titolo e l'icona della scheda del browser**. La scelta è nelle impostazioni condivise, uguale su ogni dispositivo.
  I loghi di Voron e RatRig vanno messi (file ufficiali) nella cartella `logos/` del repository: vedi `logos/README.md`.
* **App Android 1.1.0 con nome interno nuovo**: `com.klippeye.app` (era `com.vzbot.dashboard`), ponte `KlippEyeApp`. Si installa accanto alla vecchia, poi si disinstalla quella; la dashboard
  dentro la vecchia app propone *Installa la nuova app KlippEye*. Serve registrare l'app nuova in Firebase e aggiornare il segreto `GOOGLE_SERVICES_JSON` (guida, parte P5).
  L'argomento delle notifiche non cambia. La chiave di firma nuova è `android/chiave/klippeye.p12`.
* Le impostazioni condivise stanno ora in `klippeye` nel database di Moonraker (le vecchie, `vzbot_dashboard`, si leggono ancora la prima volta); le preferenze del browser (`vz_*`) diventano `ke_*` da sole.
* Nelle schermate «Brain» è diventato «backend».
* **Finestra dei parametri delle macro**: il testo dei pulsanti (per esempio «Esegui Axes shaper calibration») va a capo e si rimpicciolisce da solo, in base alla lunghezza e alla larghezza
  del pulsante (cioè dello schermo), invece di essere tagliato; un titolo lungo va a capo e non spinge più fuori la X di chiusura.
* **Console**: il tasto di invio ha l'icona dell'aeroplanino pieno, come quello di WhatsApp (telefono e PC).
* La calibrazione scelta (prima in `printer_data/config/vzbot_calibration_selected.json`, che nessuna macro usa) ora sta nella cartella dati come `calibration_selected.json`; il file vecchio, se c'è, si legge ancora e non si perde niente.

## 1.0.1

Nuovo logo e nuovi colori: **KlippEye**.

* **Logo KlippEye** (la «lente stampata»: strati viola che formano un occhio, con l'ugello sopra e la pupilla al centro) al posto di quello di VzBot:
  nella barra in alto, nel menu delle impostazioni, nell'icona della scheda del browser e nella schermata «aggiungi alla home».
* **Barra in alto**: la scritta *VzBot.287* diventa **KlippEye** (*Klipp* bianco, *Eye* viola). Il font della scritta (Outfit, 1 KB) è dentro la pagina: funziona anche senza internet.
* **Colori della dashboard**: l'accento non è più l'azzurro di One UI ma il **viola chiaro del logo** (`#b79cff`): tasto di homing, tasti di conferma, barre di avanzamento e
  cursori, interruttori e caselle spuntate, evidenziazione dei tasti della barra in basso, schede e file selezionati. I tasti pieni hanno il testo scuro (si leggeva male il bianco sul viola chiaro).
  Lo **sfondo** è il viola scuro del riquadro del logo che sfuma verso il nero. I file di codice (`.py`, `.sh`…) passano dal viola all'azzurro per restare distinguibili dai file di configurazione.
* Sui telefoni larghi 341-374 px (per esempio 360) il logo ora si vede anche nella barra in alto.
* **App Android 1.0.1**: icona con il logo sul riquadro viola scuro (come fondo dell'icona), icona delle notifiche e splash nuove, colore d'accento viola.
  GitHub costruisce l'app da solo perché `android/VERSION` è già alzato; poi, nell'app, **Aggiorna l'app**.
* Restano per ora i nomi «VzBot» (titolo della scheda, servizi, cartelle, nome dell'app): il cambio di nome completo a KlippEye è un lavoro a parte.

## 1.0.0

Prima release "a contenitore": programma e dati separati, aggiornamento dalla dashboard.

* **Aggiornamenti dalla dashboard** (Impostazioni → Aggiornamenti): release installata, controllo di GitHub, "Aggiorna VzBot",
  "Torna alla versione precedente", "Ripristina i file del programma" e riavvio del Brain e delle notifiche. Usa l'update manager
  di Moonraker, quindi funziona anche da Mainsail e Fluidd.
* **Soglie del monitor IA** (Impostazioni → Soglie del monitor): sensibilità, area controllata (con anteprima sulla foto della
  camera), pause, attese e modello dell'IA si cambiano dalla dashboard, valgono subito e restano sul Raspberry. Il Brain descrive
  da sé le proprie impostazioni: una nuova soglia compare nel menu senza aggiornare la dashboard.
* **Disposizione nuova dei file**: programma in `~/vzbot` (un repository git), dati in `~/printer_data/vzbot`, servizi `vzbot` e
  `vzbot-notifier` avviati a ogni accensione, comandi `vzbot` e `vzbot-notifiche`.
* **`scripts/install.sh`**: si lancia una volta, sposta senza cancellare quello che c'era (chiave dell'IA, notifiche), collega
  Moonraker e, se il Brain nuovo non parte, rimette a posto il servizio di prima. `--annulla` torna a com'era.
* Il Brain ha una pagina `/api/version` (release, commit, da quanto è acceso) e `/api/brain/config` (le soglie).
* Il servizio delle notifiche si ricarica da solo quando un aggiornamento ne sostituisce il file.
* **App Android 1.0.0** (la numerazione dell'app riparte da qui: prima era «mk218», `android/VERSION`): il progetto Android sta nel repository (`android/`);
  GitHub costruisce e firma l'APK (`.github/workflows/app.yml`, passi in `ci/app_ci.py`) e lo salva in `apk/`; il Brain lo offre
  (`/api/app/version`, `/app/VzBot.apk`, solo se grandezza e impronta coincidono con `apk/versione.json`); la dashboard ha il blocco **App Android**
  in Impostazioni → Aggiornamenti, e dentro l'app c'è **Aggiorna l'app** (scarica, controlla l'impronta, apre l'installazione di Android).
  Il ponte dell'app (`VzBotApp/5`) ha `appInfo` e `updateApp`. La firma è la stessa a ogni versione (`android/chiave/vzbot.p12`, cifrata con un segreto di GitHub):
  chi ha l'app installata da Android Studio deve disinstallarla una volta, perché la firma è diversa.
