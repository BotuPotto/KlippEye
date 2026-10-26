> **Note:** historical design notes of the dashboard, in Italian. They will be translated; the short English guide is `README.md`.

# KlippEye Dashboard: sorgenti (versione One UI 9)

Il backend Flask serve **un solo file HTML**. Qui sotto ci sono i sorgenti da cui quel file viene
generato. Per modificare la dashboard si cambia un file in `src/` e si rilancia la build.

```
python3 build.py            # scrive klippeye_frontend.html (serve solo Python 3, nessun npm)
python3 build.py out.html   # oppure un percorso a scelta
```

Il file prodotto è autosufficiente: CSS e JS inclusi, **nessuna risorsa esterna** (la versione V37 caricava
i font da Google Fonts, questa usa il font di sistema: su un Samsung è One UI Sans).
Nel repository del progetto la pagina sta in `frontend/klippeye_frontend.html` (la copia `pack_repo.sh` quando prepara la release; prima del cambio di nome era `dashboard/vzbot_dashboard.html`).
La release scritta nella pagina viene dal file `VERSION` (o dalla variabile `KLIPPEYE_RELEASE=x.y.z`).

## Il design: One UI 9, tema scuro

Tutto l'aspetto nasce da pochi valori in `src/css/00-tokens.css` e da pochi componenti riusati ovunque.
Le regole che tengono la pagina armoniosa sono queste quattro, valgono per ogni scheda:

| Significato | Aspetto |
|---|---|
| Selezione / stato attivo | blu tenue (`--oui-accent-soft`, testo `--oui-accent-text`) |
| Azione principale | pillola blu piena (`oui-btn--primary`) |
| Azione neutra | pillola in vetro (`oui-btn`) |
| Pericolo | rosso (`oui-btn--danger`, `--danger-soft`, `oui-tile--danger`) |

Altre scelte, tutte prese dal linguaggio One UI 9: superfici in vetro semitrasparente su uno sfondo scuro con
macchie di colore, angoli molto arrotondati (schede 28 px, riquadri 22 px, campi 16 px, pulsanti a pillola),
bordi sottili, barra delle schede flottante a pillola, titolo grande di pagina sotto la barra in alto,
slider spessi senza bordo, livelli sovrapposti (finestre) con sfocatura + oscuramento e **senza** ombra,
ombra morbida solo sulle barre flottanti. Le etichette sono in minuscolo/maiuscolo normale (niente tutto
maiuscolo), testo minimo 12 px, numeri a larghezza fissa (`tabular-nums`), font a spaziatura fissa solo per
console, log, codice e valori tecnici.

Componenti (`src/css/15-surfaces.css`, `16-controls.css`), da usare al posto di classi nuove:

```
oui-card  oui-card--flush  oui-card__head       scheda e sua intestazione
oui-tile  --warn --danger --ok                   riquadro dentro una scheda (anche <button>)
oui-list  oui-list__row                          elenco raggruppato (angoli esterni grandi, interni piccoli)
oui-well                                         area incassata: console, camera, codice, anteprime
oui-btn   --primary --danger --danger-soft --accent-soft --quiet --sm --block --icon
oui-btn-row                                      i due pulsanti a fondo finestra
oui-chip (.is-selected)  oui-segmented           selezione rapida, interruttore a segmenti
oui-field (--num)        select.oui-field        campi di testo
oui-badge --ok --warn --danger --info            pillole di stato;  oui-dot
oui-progress  oui-progress__bar (--ok/warn/danger)   barre
oui-check  oui-switch                            casella rotonda, interruttore
```

Per un tema chiaro basta ridefinire i valori di `:root` in `00-tokens.css` (superfici, testo, accenti):
nessun colore è scritto a mano negli altri file, tranne i colori della sintassi nell'editor.

## Struttura

```
build.py                    assembla la pagina
VERSION                     la release scritta nella pagina (quella del repository: ../VERSION); si può forzare con KLIPPEYE_RELEASE=x.y.z
src/index.html              scheletro: <head> (titolo della scheda), <div id="root">, segnaposto {{icons}}, {{styles}} e {{script}}
src/icons/                  icona della scheda del browser (3 PNG), incorporata dalla build
src/logos/                  loghi incorporati nella pagina per la scelta della stampante (oggi solo vzbot.png); gli altri loghi ufficiali si mettono in logos/ del repository
src/css/                    stili dell'applicazione (un file per area, in ordine di nome)
src/app/                    codice dell'applicazione (un modulo per area, in ordine di nome)
vendor/react-dom-*.js       React 18.3.1 + ReactDOM, codice di terzi, NON modificato
vendor/tailwind-*.css       Tailwind compilato; la build tiene solo le classi realmente usate
tools/tailwind_purge.py     fa quella riduzione (la chiama build.py)
tools/check_classes.py      elenca i nomi di classe usati nel codice che non hanno nessuna regola CSS
tools/make_favicon.py       disegna le icone di src/icons/ dal logo KlippEye su riquadro viola (tools/assets/logo_klippeye.png); servono Pillow e numpy
tools/make_wordmark_font.py ricava da Outfit il font (1 KB) della scritta KlippEye in alto e lo scrive in src/css/02-wordmark-font.css; serve fontTools
tools/assets/               il logo: klippeye_g4.svg (sorgente), logo_klippeye.png (a colori) e logo_klippeye_mono.png (sagoma a un colore)
```

I file di `src/app/` e `src/css/` condividono la numerazione, così l'area "ventole" è
`42-fans.js` e `42-fans.css`:

| Numero | Area |
|---|---|
| 00-12 | collegamento a React, immagini incorporate, configurazione, utilità, chiamate API |
| 13 | capacità della stampante (`13-capabilities`): cosa sa fare questa macchina, letto da Klipper |
| 14 | app Android (`14-native-app`): cosa sa fare l'app che ospita la pagina e `downloadFile()` |
| 15 | dati in tempo reale (`15-live`): ritorno dallo standby o dal background, `startPolling`, `onResume`; vedi "Tempo reale, standby e background" |
| 16 | impostazioni (`16-settings`): cosa si può cambiare dal menù laterale, dove si conserva (database di Moonraker + copia nel browser), pulizia dei valori, scelta dell'indirizzo della camera; vedi "Menù impostazioni" |
| 17 | il backend (`17-brain`): chi è (`/api/version`), le soglie del monitor IA (`/api/backend/config`), l'attesa del suo ritorno dopo un riavvio (`waitForBrain`); vedi "Soglie del monitor e aggiornamenti" |
| 18 | la stampante (`18-printer-brand`): nome e logo scelti (KlippEye, VzBot, Voron, RatRig), `PrinterLogo`, titolo e icona della scheda del browser; vedi "Nome e logo della stampante" |
| 20-22 | componenti base (Card, SectionTitle, PageTitle, icone, ConfirmDialog, toast), icone dei tipi di file (`20a-file-icons`), menu a tendina (`21-dropdown`), movimento (`22-motion`: `Presence` e `Collapse`) |
| 30-34 | stato di Klipper e riavvii (`30-klipper-state`: il pannello degli errori come in Mainsail), intestazione, menu alimentazione e servizi (`31a-power-menu`), SAVE_CONFIG, barra inferiore, pull-to-refresh |
| 40-49 | pagine Home, Controllo e Files: camera (`41-camera`: WebRTC, MJPEG, MJPEG adaptive, pagina web) e pulsante della luce, ventole, riscaldatori, movimento (`44-movement`; `44a-bed-tools`: menu Calibra; `44b-z-offset`: card Z-offset), avanzamento stampa, console, file, estrusore, menu azioni dei file (`49-file-actions`) |
| 50-58 | pagine Config e Sistema: file di configurazione (`50` dati e API, `50a` operazioni su file e cartelle, `50b` scheda; `50c-text-history`: la cronologia di Annulla/Ripristina dell'editor), editor, visualizzatore immagini, viste AI (`53-ai-views`: verdetto di stampa; `53-ai-markdown`: rapporto dell'analisi log), log, monitor AI, aggiornamenti, calibrazione (`57-calibration`; `57a-endstops`: endstop e probe), bed mesh |
| 59 | menù impostazioni: `59-settings` (il pannello laterale e le sue sette pagine), `59a-detector-settings` (le soglie del monitor), `59b-software-settings` (aggiornamenti KlippEye e passaggio da VzBot), `59c-app-update` (il blocco «App Android» della pagina Aggiornamenti) |
| 70-71 | layout per schermi larghi (PC): `70-desktop-shell` (soglia, schede in alto, barra console), `71-desktop-pages` (le cinque pagine larghe) |
| 99 | `99-main.js`: componente radice e avvio |

Un modulo che nasce accanto a un altro prende la stessa cifra con una lettera (`44a`, `50b`): l'ordine dei
nomi lo carica subito dopo quello principale, e il suo CSS ha lo stesso nome.

I CSS senza un modulo JS con lo stesso numero: `00-tokens` (tutti i valori del design), `10-base` (pagina,
sfondo, scala tipografica, scrollbar), `15-surfaces` e `16-controls` (i componenti `oui-*`), `17-utilities`
(le poche utility di layout che il Tailwind compilato non ha), `20-layout` (barra in alto, barra inferiore,
colonna della pagina), `21-primitives` (spinner), `22-motion` (animazioni e transizioni), `25-pull-refresh`, `30-dialogs` (finestre di dialogo e
notifiche), `35-klipper-state` (pannello di stato di Klipper), `60-system`, `61-screens` (editor e visualizzatore a tutto schermo),
`65-settings` (il menù impostazioni), `62-sheets` (pannelli centrati: aggiornamenti, macro), `62a-power-menu` (il menu alimentazione: deve venire dopo `62-sheets`, che dà ai pannelli la loro altezza di base), `63-macros`, `64-bed-mesh`, `70-desktop` (tutto il layout largo, vedi sotto). `21a-file-icons.css` sono le tessere delle icone dei file. `21-dropdown.css` è il menu a
tendina (`app/21-dropdown.js`), con la freccina `menu-chevron` dei pulsanti che lo aprono.

## Convenzioni

- **Niente colori scritti a mano**: si usano le variabili `--oui-*`. Le schede usano tutte `Card`
  (`20-ui-primitives.js`), i titoli di sezione `SectionTitle`/`CardHeader`, il titolo di pagina `PageTitle`.
- **Stili inline**: restano solo quelli che dipendono da un dato (larghezza di una barra, colore di un
  livello del monitor AI). Tutto il resto è una classe.
- **Classi Tailwind**: la build include solo quelle presenti nel sorgente. Una classe nuova che non
  esiste nel CSS compilato in `vendor/` non fa nulla: va scritta in `src/css/` (`tools/check_classes.py`
  aiuta a trovare i refusi).
- La sintassi JavaScript resta entro ES2020, per la WebView di Android.

## Cosa cambia rispetto alla versione ottimizzata (V37 riorganizzata)

Cambia solo l'aspetto. Funzioni, chiamate al backend, comandi G-code e comportamento sono gli stessi
(verificati con gli stessi scenari automatici su entrambe le versioni). Dettagli visibili:

- Tema scuro One UI 9 al posto dello stile scuro "a righe" della V37; un solo tema (il chiaro si può
  aggiungere dai token).
- Etichette e pulsanti da MAIUSCOLO a testo normale ("Salva", "Analizza automaticamente", "Aggiorna tutto"...).
- Ogni pagina ha un titolo grande (Home, Controllo, Files, Config, Sistema); la pagina Sistema è nella
  stessa colonna delle altre.
- Livelli (z-index): pagina < intestazione (30) < barra delle schede (900) < finestre, conferme e fogli (9999)
  < editor (10000) < visualizzatore (10001) < messaggi (99999). Con una finestra aperta la barra delle schede
  sparisce (`body:has(...)` in `src/css/20-layout.css`), così non resta sospesa sopra la tastiera.
- Barra delle schede flottante a pillola; jog pad con anello a vetro; slider più spessi; riscaldatori con
  icona e sfumatura calda.
- Editor, visualizzatore immagini e finestre di dialogo ridisegnati (barre in vetro, pulsanti a pillola);
  nell'editor la barra dei pulsanti va su due righe sui telefoni.
- Il risultato dell'analisi AI dei log è un rapporto ordinato (vedi sotto), non più testo grezzo.
- La pagina Files mostra fino a 5 colonne sugli schermi larghi.
- Il banner di errore Klipper e il "tira per aggiornare" hanno il nuovo stile.

Restano le differenze volute della versione ottimizzata rispetto alla V37 originale (titolo della scheda
"KlippEye", niente messaggi di debug, nessuna doppia ricarica dei log nei primi secondi, elenco
macro letto una volta sola quando la copia locale manca, un solo riquadro nero dietro la camera).

## Animazioni e transizioni (movimento One UI)

Tutto il movimento segue le linee guida di Samsung per One UI (developer.samsung.com/one-ui/motion) ed è
in un posto solo: i valori sono **token** in `src/css/00-tokens.css`, le animazioni in `src/css/22-motion.css`,
i due componenti di supporto in `src/app/22-motion.js`.

| Token | Valore | Dove |
|---|---|---|
| `--oui-ease` | `cubic-bezier(0.22, 0.25, 0, 1)` (curva base One UI: partenza rapida, arrivo morbido, **nessun rimbalzo**) | tutto ciò che si sposta o cambia dimensione |
| `--oui-ease-in` | `cubic-bezier(0.4, 0, 1, 1)` | ciò che esce |
| `linear` | | solo le dissolvenze (opacità), come da linee guida |
| `--oui-dur-press` | 100 ms | tocco: scala dei pulsanti, anello del jog pad |
| `--oui-dur-fast` | 150 ms | cambi di colore e sfondo |
| `--oui-dur-base` | 250 ms | frecce, interruttori, menu, dissolvenze |
| `--oui-dur-slow` | 350 ms | finestre, fogli, pagine, sezioni che si aprono, marcatore delle schede |
| `--oui-dur-exit` | 150 ms | uscita di finestre e fogli (più breve dell'entrata) |
| `--oui-dur-bar` | 450 ms | barre di avanzamento |

Nessuna durata esce dall'intervallo 100-500 ms di Samsung. Per cambiare il carattere di tutta la dashboard
(più lenta, più scattante) basta cambiare questi valori.

- **Finestre, fogli, editor, visualizzatore, menu**: lo strato sotto si scurisce e sfoca con una dissolvenza; la
  finestra sale e si ingrandisce (`oui-pop`); il menu cresce dal suo pulsante; l'editor e il visualizzatore salgono
  a schermo intero. **All'uscita** fanno il percorso inverso, più veloce. Per questo lo strato resta nel DOM per
  150 ms: lo fa `Presence` (`h(Presence, null, aperto && h(Finestra, ...))`), che mostra un involucro senza
  dimensioni con `data-presence="leaving"` e ignora i tocchi. Una finestra nuova va sempre avvolta in `Presence`
  (o usare `ConfirmDialog`, che lo fa già).
- **Cambio scheda**: il marcatore blu scorre da una scheda all'altra (`bottom-nav__pill` sul telefono,
  `header-tabs__pill` sul PC) e le carte della pagina nuova salgono una dopo l'altra (35 ms di distanza). Vale anche
  per una carta che compare dopo (la carta di stampa).
- **Sezioni che si aprono** (Endstop e probe): `Collapse`, che anima l'altezza con `grid-template-rows`.
- **Sul PC**: la console sale dal basso, il pannello di dettaglio dei file si dissolve a ogni nuovo file.
- **Riduci movimento**: con l'impostazione di sistema attiva (`prefers-reduced-motion`) tutti i tempi diventano
  1 ms: le cose accadono, ma senza spostamenti.
- Si animano solo opacità e trasformazioni (più l'altezza delle sezioni): niente che costringa a ricalcolare la pagina.
- Il test `tests/ui/motion_test.py` controlla entrata, uscita, marcatore, sezioni, "riduci movimento" e che a riposo
  non parta nessuna animazione (nessuna carta che si ricrea a ogni aggiornamento dei dati).

## Pulsante della luce

La luce del case è un **pulsante rotondo con la lampadina** nell'intestazione della card Camera (ambra con bagliore
da accesa); sul PC sta sopra il video in una pillola di vetro. Per gli assistenti vocali è un interruttore
(`role="switch"`, `aria-checked`, `aria-busy` mentre il comando attende Klipper). Il codice è in
`src/app/41-camera.js` (logica e componente) e `src/css/41-camera.css` (aspetto).

**Perché prima sfarfallava** (acceso → spento → acceso). La dashboard legge `VAR_LUCI.stato_luci` ogni 500 ms e al
tocco mostra subito lo stato voluto. Ma una lettura partita *prima* del tocco, se tornava *dopo*, rimetteva lo
stato vecchio; e anche le letture partite dopo il tocco vedono lo stato vecchio finché la macro non ha finito. Con
Klipper lento le due cose si sommavano.

**Come funziona ora** (`createLightEngine`, una piccola macchina a stati fuori da React):

- ogni tocco apre una nuova "generazione": le letture partite prima vengono **scartate e annullate**
  (`AbortController`);
- finché c'è un desiderio in attesa, le letture che **non concordano vengono ignorate**; la prima che concorda lo
  chiude. Il tocco quindi ha effetto subito e l'interruttore **non si muove più da solo**;
- le letture non si sovrappongono mai (una alla volta, la successiva parte a fine della precedente) e, mentre si
  attende, vanno ogni 250 ms invece di 500 (`LIGHT_CONFIRM_POLL_MS`);
- i comandi partono **uno alla volta e solo se servono**: acceso, spento, acceso in un secondo manda un solo
  `luci_on`;
- se Klipper non ha seguito dopo `LIGHT_CONFIRM_MS` (3,5 s dalla risposta al comando) si rilegge una volta e,
  se ancora no, l'interruttore **torna indietro, trema e un avviso dice "La luce non ha risposto"**; se il comando
  stesso fallisce: "Non riesco a comandare la luce". Limite assoluto `LIGHT_GIVE_UP_MS` (12 s) anche senza letture;
- una luce cambiata altrove (macro, altra pagina) viene seguita normalmente.

**Aspetto**: invariato rispetto a prima. Il pulsante mostra sempre ciò che è stato chiesto, anche mentre Klipper
sta ancora eseguendo (nessun indicatore di attesa). L'unica aggiunta visibile è che, se la luce non segue, il
pulsante torna indietro **tremando** (`data-fail`, alternato dispari/pari perché l'animazione possa ripetersi) e
compare l'avviso.

Il test `tests/ui/light_test.py` simula un Klipper lento (`light_read_delay`, `light_exec_delay`, `light_block`,
`light_fail` nel mock) e controlla la **sequenza** degli stati mostrati: deve essere `[spento, acceso]` e basta
(sulla versione precedente era `[spento, acceso, spento, acceso]`). `tests/ui/light_shots.py` fa le foto dei vari stati.

## Tempo reale, standby e background

**Il problema.** Un telefono in standby (o un browser lasciato in background) perde le connessioni verso la
stampante **senza accorgersene e senza errori**: una richiesta fatta su una di quelle connessioni non riceve mai
risposta e non fallisce mai. Un browser tiene al massimo **sei connessioni** verso lo stesso indirizzo: quando le
sei richieste bloccate occupano tutte le connessioni, nessun'altra richiesta della pagina parte più, e la
dashboard resta ferma finché non la si ricarica. Prima nessuna lettura aveva un limite di tempo; sulla Home il
pulsante luce (che un limite lo aveva) toglieva d'impaccio, sulle altre pagine no. Si riproduce con
`tests/ui/live_test.py` (un proxy, `blackhole_proxy.py`, "uccide" le connessioni aperte come fa il telefono): sulla
versione precedente, sulla pagina Files, la dashboard non si riprendeva mai.

**Cosa fa ora** (tutto in `src/app/12-api.js` e `src/app/15-live.js`):

- **Ogni lettura ha un limite di tempo** (`READ_TIMEOUT_MS`, 6 s; una risposta sana arriva in millisecondi):
  `fetchFresh` annulla i GET che non ricevono risposta, e così libera la connessione morta. I comandi (POST,
  upload, analisi AI) non hanno limite.
- **Il ritorno viene riconosciuto**: pagina di nuovo visibile, `pageshow` dalla cache, `resume` del browser, rete
  tornata (`online`) e, per le WebView che non dicono niente, un **controllo dell'orologio** ogni secondo: se tra due
  battiti sono passati più di 4 s, i timer erano congelati. `onResume(callback)` avvisa chi si è iscritto
  (`callback({ away })`, `away` in millisecondi).
- **Al ritorno**: si annullano le letture ancora in attesa (`abortReadsInFlight`); se si è stati via almeno 3 s
  (`LIVE_STALE_AFTER_MS`) si **provano le connessioni** con sei piccole richieste a `/printer/info` (tante quante le
  connessioni del browser): quelle che cadono su una connessione morta scadono in 1,5 s e la portano via; poi tutti
  gli aggiornamenti ripartono subito.
- **`startPolling(poll, ms)`** sostituisce ogni `setInterval` degli aggiornamenti: una lettura alla volta (non si
  sovrappongono), **nessuna lettura mentre la pagina è in background** (meno traffico e batteria), lettura
  immediata al ritorno. Lo usano temperature, ventole, avanzamento stampa, console, file, monitor AI, calibrazione,
  bed mesh e il pulsante della luce.
- **Console**: il WebSocket che ha attraversato uno standby viene chiuso e riaperto (può essere morto senza
  saperlo).
- **Camera**: lo stream WebRTC si ferma con lo standby e la sua pagina non riparte da sola; dopo un'assenza di
  almeno 8 s (`CAMERA_RELOAD_AFTER_AWAY_MS`, `41-camera.js`) l'iframe viene ricaricato (cambia la sua `key`).
- Un "pageIsHidden" conta solo se la pagina è stata vista andare via: una pagina che si apre già nascosta, o una
  WebView che lo dichiara a torto, continua a leggere come ha sempre fatto.

Il test `tests/ui/live_test.py` controlla: ritorno dallo standby con e senza i segnali del browser, su Home e su
Files; niente letture in background e lettura immediata al ritorno; salto dell'orologio (prove di connessione, camera
ricaricata, console riaperta); un'assenza breve non smonta niente; pulsante luce dopo lo standby.

## Stato di Klipper e riavvii (come Mainsail)

Il pannello in cima alla pagina (`src/app/30-klipper-state.js`, stile in `35-klipper-state.css`) fa ciò che fa
quello di Mainsail quando Klipper non è "ready":

- **Legge lo stato** con `GET /printer/info` (`state` e `state_message`): ogni 4 s se va tutto bene, ogni 2 s se
  non va; una riga di shutdown nella console o il tasto di emergenza lo fanno leggere subito.
- **Errore** (`shutdown`, `error`, `startup`): il pannello mostra il messaggio di Klipper così com'è (nel riquadro in
  carattere a larghezza fissa, scorrevole se lungo) e i tasti **Firmware restart**, **Klipper restart**, **Log Klipper**
  e **Log Moonraker**. Colore: arancione per shutdown e startup, rosso per error.
- **Riavvio in corso** (tasti del pannello, menu alimentazione, SAVE_CONFIG): al posto del messaggio c'è l'**anello di
  caricamento**. Se Klipper torna `ready` la pagina si ricarica (così tutto viene riletto); se torna in `shutdown` o
  `error` il pannello **ricompare con il messaggio nuovo**: le risposte che descrivono ancora lo stato di prima del
  riavvio vengono ignorate finché non si è visto Klipper spegnersi (6 s di tolleranza).
- **Klipper non collegato a Moonraker** (`503`): l'anello per 25 s (probabilmente sta ripartendo), poi la spiegazione.
- **Nessuno risponde** (Moonraker o Raspberry giù o occupati): non è un guasto di Klipper, quindi niente pannello, a meno che
  il riavvio non lo abbiamo chiesto noi (i riavvii di Moonraker e del Raspberry tagliano la connessione: è previsto).
- Riavvio di Moonraker e del Raspberry usano lo stesso anello; lo spegnimento del Raspberry mostra "si sta spegnendo".
- **SAVE_CONFIG** mostra l'anello ma non ricarica la pagina (rilegge solo le capacità della stampante).

Il test `tests/ui/klipper_state_test.py` simula tutti i casi con il Moonraker finto (`restart_down`, `restart_result`, ...).

## Menu alimentazione e servizi

Il tasto a forma di interruttore nell'intestazione (`src/app/31a-power-menu.js`) apre un pannello come quello in alto a
destra di Mainsail:

| Sezione | Contenuto | Chiamata |
|---|---|---|
| Klipper | Klipper restart, Firmware restart | `POST /printer/restart`, `POST /printer/firmware_restart` |
| Servizi | tutti i servizi che Moonraker gestisce (`available_services` di `/machine/system_info`, senza `klipper_mcu`), con il loro stato; riavvia (o avvia, se è fermo) e ferma; Moonraker non si può fermare da qui | `POST /machine/services/restart\|start\|stop?service=NOME` |
| Raspberry | Riavvia, Spegni | `POST /machine/reboot`, `POST /machine/shutdown` |

Come in Mainsail chiede conferma **solo mentre si stampa** (un riavvio rovinerebbe la stampa); il riavvio e lo
spegnimento del Raspberry chiedono sempre conferma. Se si riavvia il servizio della camera (`crowsnest`, ...) il
flusso della camera viene ricaricato dopo 7 s. La sezione Klipper sparisce quando Moonraker non ha un Klipper.

## Traffico verso la stampante

La dashboard si aggiorna a ripetizione, e il Raspberry deve anche gestire Klipper, Moonraker e la camera: ogni
richiesta inutile gli ruba un po' di CPU e banda. A riposo, sulla Home, **le richieste erano circa 8 al secondo**;
ora sono **circa 4** (`tests/ui/traffic_probe.py` le conta per indirizzo, `tests/ui/traffic_test.py` lo verifica).
Come si è ottenuto, senza perdere reattività dove serve:

| Cosa | Prima | Ora |
|---|---|---|
| Luce (`POLL_MS.light`) | ogni 0,5 s | ogni 1,5 s; **ogni 0,25 s solo mentre un comando aspetta Klipper** |
| Elenco delle ventole (`/printer/objects/list`) | a ogni lettura (ogni 1,2 s) | ogni 30 s (`FAN_NAMES_REFRESH_MS`); le velocità restano ogni 1,2 s |
| Console (`/server/gcode_store`, 150 righe) | ogni 0,5 s | ogni 3 s **se il WebSocket è agganciato** e consegna le righe da solo (`CONSOLE_SAFETY_POLL_MS`); ogni 0,5 s se non lo è |
| Metadati del file in stampa | a ogni lettura (ogni 2 s, anche a stampa finita) | una volta per nome di file |
| Monitor AI | ogni 2 s | ogni 4 s |
| Selezione calibrazioni (altro dispositivo) | ogni 2 s | ogni 5 s |

Il pannello di stato di Klipper aggiunge **circa 0,25 richieste al secondo** (una ogni 4 s) quando tutto va bene.

Restano invariati: temperature e posizione (1 s), avanzamento stampa (2 s). In background non si legge niente
(`startPolling`, vedi sopra). Il WebSocket "agganciato" è quello che ha risposto alla sottoscrizione
(`server.gcode_store.subscribe`): se la risposta non arriva (WebSocket non inoltrato, per esempio) la console
continua a leggere ogni 0,5 s come prima.

## Layout per schermi larghi (PC)

Da **1100 px di larghezza** in su la dashboard usa un secondo layout, ispirato alla pagina Dispositivo di
Bambu Studio; sotto quella soglia (telefoni, anche in orizzontale) **non cambia nulla**: il telefono ha lo
stesso albero di elementi e gli stessi stili di prima (verificato confrontando le schermate automatiche).

- La scelta è fatta in JavaScript da `useIsDesktop()` (`src/app/70-desktop-shell.js`), che segue il ridimensionamento
  della finestra; `99-main.js` costruisce l'albero largo o quello da telefono. La classe `is-wide` su `<html>`
  serve solo agli stili di `src/css/70-desktop.css`, che sono tutti su classi nuove (`desk-*`, `header-tabs`).
- Le schede della barra in alto sono Dispositivo, Calibrazione, File, Config, Sistema. Gli identificativi sono
  quelli del telefono (home, controllo, files, config, sistema), quindi la scheda ricordata vale per entrambi i layout.
- Le carte sono **le stesse** del telefono (riscaldatori, ventole, movimento, Z-offset, estrusore, mesh,
  calibrazioni, file, config, sistema): cambia solo come sono disposte. Le pagine hanno altezza fissa e ogni
  colonna scorre da sola; la pagina intera non scorre.
- **Dispositivo**: camera a tutta altezza con la luce, fascia del monitoraggio AI (dati veri del rilevatore, un
  clic apre Sistema), avanzamento stampa; a destra riscaldatori, ventole, movimento, estrusore. Durante la stampa
  il Z-offset prende il posto del movimento e l'estrusore si nasconde. Sopra i 1600 px le carte laterali
  passano su due colonne.
- **File**: elenco di tessere a sinistra, pannello di dettaglio a destra (anteprima, dati, Avvia stampa, Scarica,
  Editor, Elimina). **Config**: elenco a sinistra, editor **nella pagina** a destra; "Salva" non chiude il file.
  Con modifiche non salvate, cambiare file o scheda chiede conferma (`editorDirty`, `unlessUnsaved` in `99-main.js`).
- **Sistema**: tre colonne (host, MCU e aggiornamenti | log | monitor AI). Il caricamento dei dati è in `useSystemData`
  (`56-system.js`), condiviso con la pagina da telefono.
- **Console**: barra fissa in basso su ogni pagina con le ultime righe e il campo di invio; la freccia apre l'intera
  console sopra la barra (Esc la chiude).

## Pagina Files: file di stampa

- Su telefono (fino a 600 px) i file sono **3 per riga** con tessere compatte (nome su 3 righe al massimo,
  pulsante "Stampa"); sugli schermi larghi restano fino a 5 colonne con "Avvia stampa".
- **Pressione lunga** (500 ms col dito o col mouse, oppure tasto destro) su un file apre un menu
  (`src/app/49-file-actions.js`, stili in `49-file-actions.css`):
  - **Apri nell'editor**: legge `/server/files/gcodes/<file>` e apre il gcode nell'editor (con colori per
    comandi, parametri e commenti). Fino a 256 KB si può anche modificare e salvare (il file viene ricaricato
    nella root `gcodes`); un file più grande si apre **in sola lettura**, solo l'inizio (circa 192 KB), perché
    l'editor colora ogni riga e si bloccherebbe. Le soglie sono `GCODE_EDIT_MAX_BYTES` e `GCODE_PREVIEW_BYTES`.
  - **Elimina dal Raspberry**: dopo una conferma invia `DELETE /server/files/gcodes/<file>`. Il backend Brain
    inoltra già ogni metodo di `/server/*` a Moonraker, quindi non è stato modificato. Se Moonraker rifiuta
    (per esempio il file è in stampa) compare un messaggio e il file resta nell'elenco.
- Dopo la pressione lunga i clic vengono ignorati per 450 ms sul menu: sollevando il dito il clic non attiva
  una voce per sbaglio.

## Card Movimento: motori e calibrazioni

Sotto i pulsanti di home (`src/app/44-movement.js`, `44a-bed-tools.js`):

- **Motori off** invia `M84` (e lo mostra nella console). Disattivato durante una stampa.
- **Calibra** apre un menu a tendina (`21-dropdown.js`) con quello che la stampante ha davvero, letto da Klipper
  (`13-capabilities.js`: sezioni di `printer.cfg` e comandi registrati):
  - **Screws tilt calculate** (`SCREWS_TILT_CALCULATE`), se esiste `[screws_tilt_adjust]`. Il risultato è un
    foglio con ogni vite: quanto girarla (giri e minuti) e in che verso, letto dall'oggetto `screws_tilt_adjust`.
  - **Axis twist compensation, asse X / asse Y** (`CARTOGRAPHER_AXIS_TWIST_COMPENSATION AXIS=X|Y`), solo con
    Cartographer. Senza la sezione `[axis_twist_compensation]` in `printer.cfg` la voce c'è ma è spenta e lo
    spiega. A fine misura chiede se salvare (`SAVE_CONFIG`) o rimandare.
  - Tutte le voci vogliono gli assi in home e nessuna stampa in corso: altrimenti sono spente e il sottotitolo
    dice perché. Se Klipper non risponde ancora non si nasconde nulla: l'ultima parola resta a Klipper.
- Le due misure durano un minuto o più, mentre il proxy del backend rinuncia a una richiesta dopo 10 s
  (`timeout=10` in `Copy_of_VzBot_Brain.py`, non modificato). Perciò la fine non si legge dalla risposta HTTP:
  si segue lo stato che Klipper riporta (ogni 1,5 s, massimo 10 minuti) e la console, dove una riga `!!` è un errore.

## Card Z-offset

Durante una stampa (non a riposo, non in pausa) la card **Z-offset** prende il posto di Movimento
(`src/app/44b-z-offset.js`): muovere la testa mentre si stampa sarebbe un incidente.

- Passi 0,01 / 0,025 / 0,05 / 0,1 mm, **modificabili dal menù impostazioni** (da uno a quattro valori tra 0,001 e 1 mm; il passo scelto si ricorda su questo dispositivo, e se esce dall'elenco si torna al primo); alza/abbassa invia
  `SET_GCODE_OFFSET Z_ADJUST=±x MOVE=1`; due tocchi ravvicinati diventano un solo comando. **Azzera** (con
  conferma) invia `SET_GCODE_OFFSET Z=0 MOVE=1`.
- A fine stampa (completata o annullata), se è rimasto un offset, la card resta **sopra** Movimento finché non lo
  si applica. **Salva offset** chiede conferma, poi invia `Z_OFFSET_APPLY_PROBE` o `Z_OFFSET_APPLY_ENDSTOP`
  (scelto da `stepper_z.endstop_pin`) e `SAVE_CONFIG`, che scrive il valore in `printer.cfg` e riavvia Klipper.
  Per questo non si può fare mentre si stampa.

## Calibrazioni: endstop e probe

In fondo alla card Calibrazioni, una sezione che si apre e chiude (`src/app/57a-endstops.js`) mostra lo stato di
ogni endstop (`GET /printer/query_endstops/status`) e del probe (`QUERY_PROBE`), come il pannello Endstops di
Mainsail. **Non legge niente da sola**: né quando si apre la pagina Controllo (anche con la sezione lasciata aperta),
né quando si apre la sezione. Gli endstop e il probe si interrogano solo premendo **Aggiorna**; prima dice "Non ancora
letti" e dopo "Aggiornato alle HH:MM". La sezione è spenta durante una stampa, perché interrogare la MCU rallenterebbe
la coda dei movimenti.

## File di configurazione: gestione

Nella card "File di configurazione" (`src/app/50-config-files.js`, `50a-config-file-manager.js`,
`50b-config-files-card.js`). Le chiamate sono le stesse di Mainsail e Fluidd; il backend Brain inoltra già
GET, POST e DELETE di `/server/*`, quindi non è stato modificato.

| Azione | Chiamata a Moonraker |
|---|---|
| Elenco di una cartella (anche vuota) | `GET /server/files/directory?path=config/<cartella>` |
| Nuovo file | upload di un file vuoto, `POST /server/files/upload` (`file`, `root=config`, `path`) |
| Carica file | `POST /server/files/upload`, uno alla volta |
| Nuova cartella | `POST /server/files/directory` `{path}` |
| Rinomina e sposta (file e cartelle) | `POST /server/files/move` `{source, dest}`: il nuovo percorso dice cartella e nome |
| Elimina file | `DELETE /server/files/config/<file>` |
| Elimina cartella | `DELETE /server/files/directory?path=...&force=true` (con tutto il contenuto) |

- **Nuovo** (in alto a destra della card): nuovo file (si apre subito nell'editor), nuova cartella, carica file.
- **Menu di riga**: il pulsante ⋯, la pressione lunga (500 ms) o il tasto destro aprono Apri, Rinomina,
  Sposta in…, Elimina. "Sposta in…" mostra l'albero delle cartelle (una cartella non può finire dentro se
  stessa; se la destinazione ha già lo stesso nome lo dice e non procede).
- **Su computer** una riga si trascina su una cartella, su "/" o su ".." per spostarla, e i file trascinati
  da fuori sulla card vengono caricati nella cartella aperta. Sul telefono le righe non sono trascinabili,
  così il dito scorre la lista.
- **Nomi**: non vuoti, al massimo 100 caratteri, senza `/ \ ? # %` (il proxy del backend non li passa
  nell'indirizzo), senza il punto iniziale (il file resterebbe nascosto), non uguali a un elemento esistente e non
  del tipo dei backup nascosti (`printer-*.cfg`, `crowsnest.conf.*`). Per `printer.cfg` e `moonraker.conf`
  rinominare, spostare o eliminare avvisa che Klipper e Moonraker li leggono all'avvio.
- Un file caricato che ha lo stesso nome di uno esistente chiede conferma prima di sostituirlo.
- **Carica file nell'app Android**: il WebView apre il selettore di file solo se l'app lo implementa
  (`WebChromeClient.onShowFileChooser` in `MainActivity.kt`). L'app dalla versione `mk216.1` lo fa e aggiunge
  `VzBotApp/2` allo user agent; la dashboard riconosce così le app che lo supportano. Con la vecchia app
  (WebView senza selettore) la voce "Carica file" è disattivata e lo dice, perché non si aprirebbe nulla.
  Creare un file e scriverci dentro dall'editor funziona in ogni caso.
- **Scarica**: nel menu di ogni file (non delle cartelle), nel pulsante di download dei log e nel visore immagini.
  Tutti passano da `downloadFile(indirizzo, nome)` (`src/app/14-native-app.js`). In un browser è un link con
  l'attributo `download` (il nome lo decide il server o la pagina, e funziona anche con spazi e accenti: l'indirizzo
  è codificato da `configFileUrl()`). Nell'app Android un WebView non scarica nulla da solo: dalla versione `mk216.3`
  l'app aggiunge `VzBotApp/3` allo user agent ed espone `window.VzBotApp.saveUrl(indirizzo, nome)`, che salva il file
  nella cartella Download del telefono. Con un'app più vecchia la dashboard lo dice ("aggiornala o apri la dashboard
  dal browser") invece di non fare niente. Il numero dopo `VzBotApp/` dice cosa sa fare l'app: 2 = selettore file,
  3 = salvataggio dei file, 4 = indirizzi, 5 = aggiornamento dell'app da sola (vedi «Il blocco App Android»).

## Editor: commentare e decommentare righe

Sotto la barra dell'editor (`src/app/51-config-editor.js`, funzione `commentLines`) ci sono due tasti, **Commenta** e
**Decommenta**; da tastiera **Ctrl+/** fa l'una o l'altra cosa (se tutte le righe non vuote hanno già il segno le
decommenta, altrimenti le commenta). Agiscono sulle **righe toccate dalla selezione** (la riga del cursore se non c'è
selezione); una selezione che finisce all'inizio di una riga non arriva a quella riga.

- **Commenta** mette un `#` davanti a ogni riga non vuota (le righe vuote restano vuote), tutti alla stessa colonna: quella
  della riga meno rientrata. Così un blocco conserva la forma (il corpo di una macro resta rientrato) e una sezione
  intera comincia con `#` in prima colonna. Una riga che ha già un `#` ne riceve un altro: si può commentare due volte e
  poi togliere i due livelli uno alla volta.
- **Decommenta** toglie **un solo** `#` da ogni riga che ne ha uno davanti (dopo gli spazi del rientro); le altre righe non
  cambiano. Non tocca gli spazi: `#    G28` torna `    G28`.
- Nei file G-code il segno è `;` (una riga con `#` lì non è un commento).
- Dopo l'operazione le righe cambiate restano selezionate (si può premere subito l'altro tasto) e la riga di stato dice
  quante sono ("4 righe commentate"), o che non c'era niente da fare.
- È **un solo passo** della cronologia dell'editor (vedi sotto): **Annulla** (o Ctrl+Z) la toglie in un colpo e rimette
  selezionate le stesse righe.
- I tasti non appaiono nei file in sola lettura (G-code grandi). Il test è `tests/ui/editor_comment_test.py`.

## Editor: Annulla e Ripristina

Nella stessa barra, a sinistra di Commenta/Decommenta, ci sono due tasti con le frecce: **Annulla** e **Ripristina**
(spenti quando non c'è niente da annullare o da ripristinare). Da tastiera: **Ctrl+Z** annulla, **Ctrl+Y** (o
**Ctrl+Maiusc+Z**) ripristina; sul Mac lo stesso con Cmd. I tasti non rubano il fuoco al testo: su telefono la tastiera
resta aperta.

La cronologia la tiene l'editor, non il browser (`src/app/50c-text-history.js`, hook `useTextHistory`), per questo il
risultato è uguale su PC, nel browser del telefono e nell'app Android, e i tasti sanno quando sono utilizzabili.
Tutto passa dalla stessa lista, nell'ordine in cui è successo: scrittura, cancellazione, incolla, taglia, Tab,
Commenta/Decommenta.

- **Cosa è un passo.** Le lettere scritte una dopo l'altra (pausa massima 900 ms tra una e l'altra) sono un passo solo, e
  lo stesso vale per una serie di Backspace/Canc consecutivi e per una parola costruita dalla tastiera del telefono
  (composizione). Incolla, taglia, Tab, una selezione sostituita e Commenta/Decommenta sono un passo ciascuno.
  Scrivere dopo un Annulla butta via la lista dei Ripristina (come in ogni editor).
- **Dove finisce il cursore.** Annulla rimette la selezione che c'era prima della modifica, Ripristina quella di dopo; se la
  modifica è fuori dallo schermo l'editor scorre fino a mostrarla (`revealOffset`).
- **Dopo un salvataggio.** La cronologia resta: si può annullare anche dopo aver salvato (il file torna "Modificato"
  perché diverso da quello salvato) e tornando al testo salvato il badge "Modificato" sparisce da solo.
- **L'annulla del browser.** Ctrl+Z viene intercettato; l'annulla "di sistema" (menu Modifica, tastiera di alcuni telefoni)
  è fermato quando il browser lo annuncia (`beforeinput`) oppure, se non lo annuncia, rimesso a posto subito dopo: in tutti i casi fa
  il passo della lista dell'editor e non quello del browser.
- **Memoria.** Un passo contiene solo il pezzo di testo cambiato (non una copia del file); la lista ne tiene **300**, poi
  dimentica i più vecchi. Se il testo non corrisponde più a ciò che la lista si aspetta (non dovrebbe succedere), la lista
  si svuota invece di applicare un passo nel posto sbagliato.
- Non c'è nei file in sola lettura. I test sono `tests/ui/editor_undo_test.py` (tasti, scorciatoie, sequenze miste,
  selezione, scorrimento, tastiera con composizione, limite dei 300 passi) e `tests/ui/history_unit.js` (20.000 casi casuali
  sulle funzioni `diffText` e `joinEdits`).

## Editor: testo colorato e selezione allineati

L'editor è un `<textarea>` trasparente (quello che l'utente tocca, scorre e seleziona) sopra una copia colorata del testo
(`.editor-layer`) e accanto alla colonna dei numeri di riga (`.editor-lines`). Solo il textarea scorre per mano
dell'utente: copia colorata e numeri lo seguono (`syncScroll` in `51-config-editor.js`). Se restano indietro, la
selezione (disegnata dal textarea) cade su una riga diversa da quella del testo colorato e si vede il testo "doppio".

Due cose potevano farli restare indietro, e sono sistemate:

- **Fine del file.** Il textarea può scorrere più in là della copia colorata: ha la riga vuota dopo l'ultimo "a capo" e le sue
  barre di scorrimento gli tolgono spazio. La copia colorata (che è alta quanto il testo) si fermava una riga prima. Ora
  `.editor-layer` e `.editor-lines` hanno 64 px di spazio in più in fondo (e a destra per la copia): possono sempre
  scorrere quanto il textarea, e quello spazio il textarea non lo raggiunge mai.
- **Un evento di scorrimento in ritardo o mancato** (maniglia della selezione trascinata al bordo, tastiera che si apre o si
  chiude e cambia l'altezza della casella). Dopo ogni scorrimento, selezione, tocco, cambio di fuoco o ridimensionamento
  della tastiera (`followScroll`) le copie vengono ricontrollate a ogni fotogramma finché il textarea non sta fermo, e
  per tutto il tempo in cui il textarea ha il fuoco: non possono restare indietro più di un fotogramma. Senza fuoco il
  controllo si ferma e non consuma niente.

Il test è `tests/ui/editor_scroll_test.py` (posizioni a inizio, metà e fine file, a quattro dimensioni di schermo; copie
spostate di proposito senza nessun evento; digitazione in fondo al file; annulla).

## Icone dei file

Un solo posto decide che aspetto ha un file o una cartella: `src/app/20a-file-icons.js` (stile in
`21a-file-icons.css`). È una **tessera arrotondata** (squadrata, mentre i pulsanti d'azione sono tondi, così ciò che
si apre e ciò che si preme non si confondono) con un'icona a linea dello stesso spessore del resto del set.
L'icona dipende **solo dall'estensione** (l'ultima del nome: `moonraker.conf.bkp` è un `.bkp`), mai dal nome:
`printer.cfg`, `macros.cfg` e `moonraker.conf` hanno la stessa icona (e `.moonraker.conf.bkp` vale come `.bkp`).

| Tipo | Icona | Tinta |
|---|---|---|
| Cartella | cartella | giallo |
| `.cfg`, `.conf` | cursori (tre linee con un pomello) | blu |
| `.bkp` | foglio con l'angolo piegato | grigio |
| `.log` (anche ruotati: `moonraker.log.1`) | terminale | grigio |
| `.gcode` | cubo con linea di strato | blu |
| `.json`, `.yaml`, `.toml` | graffe | grigio |
| `.py`, `.sh`, `.js`, `.service` | `</>` | viola |
| `.bak`, `.old`, `.orig`, `.backup`, nomi che finiscono con `~` | orologio all'indietro | grigio |
| immagini | immagine | verde |
| tutto il resto | foglio | grigio |

Si usano nelle righe dei file di configurazione (40 px), nel menu della riga (64 px), nella scelta della cartella
di destinazione e nelle righe dei log. Il **segnaposto delle stampe senza anteprima** (`PrintPlaceholder`: cubo
dentro una tessera blu, al centro della cornice dell'immagine) sostituisce il vecchio simbolo di testo ovunque manchi
la miniatura: tessere della pagina Files, conferma di stampa, menu del file, card della stampa in corso, anteprima
grande della versione per PC. Per un tipo nuovo basta una riga in `FILE_KIND_BY_EXTENSION`. Il test è
`tests/ui/icons_test.py`.

## Come viene mostrata l'analisi AI dei log

La risposta dell'AI è testo Markdown. `src/app/53-ai-markdown.js` lo legge e lo mostra come rapporto (stili in
`src/css/53-ai-markdown.css`); tutto è costruito con elementi React, mai con `innerHTML`:

- **Riepilogo** in alto: numero di errori e avvisi, conclusione, file coinvolti.
- **Sezioni** numerate e richiudibili (`<details>`), con i pulsanti "Comprimi tutto / Espandi tutto".
- **Tabelle** mostrate come una scheda per riga (file, gravità, messaggio, spiegazione), senza scorrimento
  laterale. Il colore viene dalla colonna "Gravità" (Critico / Error → rosso, Warning → ambra), quindi
  "nessun errore critico" non diventa più rosso come con la vecchia ricerca per parole chiave.
- **Elenchi** con pallini e numeri tondi; **comandi** in riquadri con pulsante "Copia" (copiano il testo
  originale); "Testo originale" e "Copia tutto" in fondo.
- Niente esce dallo schermo: nomi di file, token e righe di log lunghi vanno a capo. Il motivo del vecchio
  problema era la griglia della pagina Config, che si allargava fino al testo più lungo: ora ha una colonna
  `minmax(0, 1fr)` e le schede hanno `min-width: 0`.
- Se la risposta non ha la forma attesa (testo semplice) viene mostrata comunque in modo leggibile.

## Menù impostazioni

Il pulsante a tre linee in alto a sinistra (accanto al logo, in tutte le pagine, anche sul PC) apre un pannello laterale come quello di
Mobileraker. Ha sette pagine (`src/app/59-settings.js`, stili `src/css/65-settings.css`); ogni modifica vale subito e viene salvata un attimo dopo.

| Pagina | Cosa si sceglie |
|---|---|
| Camera | il metodo, come nella pagina Webcam di Mainsail: **WebRTC** (la pagina di camera-streamer, come prima), **MJPEG** (flusso continuo in un `<img>`, che si riprova da solo se si interrompe), **MJPEG adaptive** (una foto dopo l'altra, da 1 a 30 al secondo, con due immagini sovrapposte che si scambiano così non sfarfalla; ferma quando la pagina è in background), **Pagina web** (qualsiasi indirizzo in un iframe). Un indirizzo per metodo (un percorso sulla stampante tipo `/webcam/?action=stream` oppure un indirizzo completo `http://…`; `javascript:`, `data:` e simili non entrano), specchia / capovolgi, "Ricarica la camera", e **Importa da Mainsail** (legge `/server/webcams/list`: servizi `mjpegstreamer`, `uv4l-mjpeg`, `ipstream` → MJPEG, `mjpegstreamer-adaptive` → adaptive, `webrtc-camerastreamer` → WebRTC, `iframe` → pagina web; gli altri compaiono spenti con "non supportato qui") |
| Indirizzi | IP locale (rete di casa) e IP esterno (ZeroTier, VPN) del Raspberry, e quale usare per la camera: **Automatico** (quello della rete da cui è aperta la dashboard: stesso indirizzo, poi stessa rete /16, poi `192.168.*` → locale, il resto → esterno), Sempre locale, Sempre esterno (`pickCameraHost`) |
| Z-offset | i passi della card (vedi sopra) |
| Notifiche | quali delle sette notifiche ricevere (con il loro testo esatto) e se il servizio sul Raspberry è vivo |
| Soglie del monitor | le soglie interne del monitor della camera (sensibilità, area, pause), lette dal Brain; vedi la sezione dopo |
| Aggiornamenti | release installata, controllo e installazione degli aggiornamenti, ritorno alla versione precedente, riavvio del Brain e delle notifiche; vedi la sezione dopo |
| Monitor IA | pausa e cancellazione automatiche (spente all'inizio; la cancellazione chiede conferma), quanti controlli di fila (1–3), sicurezza minima (qualsiasi, 50, 70, 85 %), quali difetti contano (spaghetti, piatto vuoto, layer shift, warping) |

**Dove sono conservate.** Un solo documento JSON, nel database di Moonraker (namespace `klippeye`, chiave `settings`; fino alla 1.0.x `vzbot_dashboard`, che si legge ancora la prima volta), raggiunto
tramite il Brain come il resto di Moonraker (`GET/POST /server/database/item`, che il Brain inoltra senza cambiarlo). Così telefono, tablet e PC
vedono le stesse impostazioni e il servizio delle notifiche (`notifier/`) legge lo stesso documento. Una copia sta anche in `localStorage`
(`vz_settings`: `{t, dirty, settings}`): la pagina parte subito con le sue impostazioni e continua a funzionare se il Raspberry non le
accetta (la riga in fondo al menù dice allora "Solo su questo dispositivo" e perché).

- Ogni documento porta `_t`, la data dell'ultima modifica in ms, sempre crescente. All'apertura della pagina, al ritorno in primo piano e ogni volta
  che si apre il menù la dashboard legge quello del Raspberry: se non ha modifiche proprie in attesa lo prende; se le ha e sono più recenti, le invia.
  Il primo documento in assoluto ha `_t = 0`, quindi qualunque scelta fatta altrove vince sui valori iniziali.
- Si legge l'intero namespace (non la singola chiave), così "ancora niente" non è un errore 404 nella console del browser.
- Tutto ciò che arriva (dal Raspberry o dal browser) passa da `sanitizeSettings`: un valore sbagliato o mancante diventa il valore iniziale,
  gli interruttori vogliono un vero `true`/`false` (le azioni automatiche restano spente nel dubbio). Un documento rovinato non rompe la pagina.
- I campi di testo prendono il valore quando si smette di scrivere (0,8 s), con Invio, uscendo dal campo o chiudendo il menù; un valore non valido
  lo dice e, uscendo dal campo, torna l'ultimo buono. Per i passi dello Z-offset uscire dal campo li mette in ordine.
- Chiudono il menù: il pulsante X, un tocco sulla striscia di pagina rimasta visibile, Esc, uno scorrimento verso sinistra (≥ 70 px).
- Le due conferme (ripristina tutto, cancella da solo) stanno fuori dal pannello: un `backdrop-filter` taglia gli elementi `fixed` che contiene.
- **L'app Android** (dalla mk218, user agent `VzBotApp/4`) usa gli stessi indirizzi del menu. La dashboard glieli comunica con
  `window.KlippEyeApp.setAddresses(locale, esterno)` (solo l'indirizzo, senza porta) quando li conosce davvero: dopo aver letto le
  impostazioni dal Raspberry, o quando l'utente li cambia. Mai prima: una pagina che non ha ancora interrogato il Raspberry ha solo
  i valori iniziali, che non devono sovrascrivere quelli dell'app (`known` in `createSettingsStore`, `announce()`). L'app li
  salva e li usa all'avvio successivo; `getAddresses()` dice cosa ha salvato e la pagina Indirizzi lo mostra ("userà questi
  indirizzi", "non ha accettato": l'app rifiuta ciò che non è di una rete privata). Al contrario, la finestra "Indirizzi" che l'app
  mostra quando non riesce a connettersi chiama `window.vzSetAddresses(locale, esterno)` a pagina caricata: aspetta la lettura delle
  impostazioni del Raspberry (`settingsStore.pull()` restituisce una promessa) e poi cambia solo gli indirizzi, così il resto
  resta com'era. Con un'app più vecchia la pagina avvisa che ha gli indirizzi scritti dentro.
- Il codice resta ES2020 (senza `?.` e `??`, per coerenza con il resto).
- Prova: `tests/ui/settings_test.py` (apertura, salvataggio e condivisione, Raspberry che non risponde o non accetta, documenti rovinati, ogni pagina,
  schermi da 320 a 1440 px).

### Servizio delle notifiche 1.1

`notifier/klippeye_notifier.py` (versione 1.1) legge lo stesso documento ogni 10 s (`settings_poll_seconds`): le notifiche spente non partono; i
filtri del monitor IA (controlli di fila, sicurezza minima, difetti) si applicano **sopra** il verdetto del Brain, che decide da solo quando
analizzare e con quali soglie interne (non cambiabili da qui). Le azioni automatiche (`POST /printer/print/pause|cancel`) sono spente
all'inizio, partono una volta per stampa e per tipo, mai se lo stato della stampante non è chiaro; con la cancellazione automatica spenta un
verdetto CANCELLA vale come pausa. Il servizio scrive la chiave `notifier` (`{version, seen, applied, lastAction}`) ogni 2 minuti e a ogni
cambiamento: il menù la legge ogni 8 s mentre una pagina che la usa è aperta, e dice se il servizio è attivo (visto negli ultimi 6 minuti).
Dettagli e comandi in `notifier/README.md`.

## Soglie del monitor e aggiornamenti

Dalla release 1.0 il backend (`backend/klippeye_backend.py`, prima `brain/vzbot_brain.py`) ha tre pagine in più e la dashboard due pagine di menù che le usano.

**Il Brain descrive le proprie impostazioni.** `GET /api/brain/config` risponde `{values, defaults, groups, spec, running, has_cv2, saved}`:
`spec` è la lista delle soglie (chiave, tipo `bool`/`int`/`float`/`text`/`area`, etichetta, aiuto, unità, minimo, massimo, passo, gruppo),
`groups` i titoli dei gruppi. La pagina **Soglie del monitor** (`59a-detector-settings.js`) disegna solo quello che le viene detto:
una soglia aggiunta al Brain compare nel menù senza una dashboard nuova, e un tipo che la dashboard non conosce viene saltato.
`POST /api/brain/config {values: {...}}` salva (il Brain controlla ogni valore: se uno non va risponde 400 con `errors` per chiave e non
cambia niente), `POST /api/brain/config/reset {keys?}` torna ai valori di sempre. Sul disco finisce solo quello che differisce
(`brain.json` nella cartella dei dati). `useBrainConfig` (`17-brain.js`) mostra la modifica subito, la manda 0,6 s dopo (più modifiche
vicine in una richiesta sola) e rilegge la risposta del Brain; un numero fuori dai limiti non parte, uscendo dal campo torna l'ultimo
buono; se il Brain rifiuta o non risponde il valore torna quello di prima e la pagina lo dice.

**La pagina Aggiornamenti** (`59b-software-settings.js`): `GET /api/version` (release, interfaccia, commit, avvio, da quanto è acceso),
la voce `klippeye` (prima del passaggio: `vzbot`) di `/machine/update/status` (update manager di Moonraker, componente `git_repo`) e il file `VERSION` letto da
raw.githubusercontent.com (solo per scrivere "Disponibile la release X": se non c'è internet la pagina dice "N modifiche in arrivo"). Con
"Controlla" chiede a Moonraker `/machine/update/refresh`. "Aggiorna KlippEye", "Torna alla versione precedente" e "Ripristina i file del
programma" usano la finestra di aggiornamento di `56-system.js`; Moonraker riavvia il servizio `klippeye` (`vzbot` prima del passaggio) e **la risposta HTTP viene
tagliata** (la pagina è servita dal Brain che sta per essere ucciso): il TypeError del browser è il risultato atteso, non un errore.
`waitForBrain` aspetta che `/api/version` risponda con un `started` o una release diversi; se il Brain è rimasto acceso 25 s dopo la fine
del lavoro (Moonraker non lo ha riavviato) la dashboard lo riavvia da sé (`/machine/services/restart?service=klippeye`). Poi ricarica la
pagina. Il riavvio dal menù (anche quello della finestra Alimentazione e servizi) segue lo stesso schema (`RESTART_KINDS.brain`).

- Il websocket non c'è dietro il Brain: i comandi dell'update manager vanno su HTTP; dopo un tentativo fallito la dashboard non riprova per 60 s.
- Un repository con file modificati a mano (`is_dirty`) fa rifiutare l'aggiornamento a Moonraker: la pagina lo dice e offre il ripristino
  (`/machine/update/recover`, prima morbido poi `hard`).
- La release della pagina (`DASHBOARD_RELEASE`) la scrive `build.py` dal file `VERSION` (variabile `KLIPPEYE_RELEASE`, poi `vz_oneui/VERSION`,
  poi `../../VERSION`); se differisce da quella del Brain la pagina propone di ricaricarla.
**Il blocco «App Android»** (`59c-app-update.js`, in fondo alla pagina Aggiornamenti): GitHub costruisce e firma l'APK (workflow
`.github/workflows/app.yml` del repository), lo mette in `apk/` insieme a `versione.json`, e arriva sul Raspberry con il normale
«Aggiorna KlippEye». Il backend lo offre: `GET /api/app/version` (`{available, version, code, size, sha256, built}` oppure `{available:false, reason}`;
`available` è vero solo se dimensione e SHA-256 del file vero coincidono con `versione.json`) e `GET /app/KlippEye.apk` (supporta `Range`; `/app/VzBot.apk` è lo stesso file, per la vecchia app).
Il blocco cambia secondo dove è aperta la dashboard:
- **app release 5 o più** (user agent `KlippEyeApp/5`, la vecchia app `VzBotApp/5`): `window.KlippEyeApp.appInfo()` dà `{version, code, canInstall}`; con «Aggiorna l'app» la
  pagina chiama `window.KlippEyeApp.updateApp("/app/KlippEye.apk", versione, sha256, grandezza)` (tutti testo) e l'app risponde chiamando
  `window.vzAppUpdate({stato: "scarico"(fatto, totale) | "permesso" | "installazione" | "errore"(messaggio)})`. L'app controlla da sé che
  l'indirizzo sia quello del backend a cui è collegata e il percorso esattamente `/app/KlippEye.apk` (la vecchia app: `/app/VzBot.apk`), che la versione sia più nuova, e dopo il
  download grandezza e SHA-256. Android chiede sempre conferma e accetta solo un APK con la stessa chiave dell'app installata.
- **app 3 o 4** (`VzBotApp/3`, `/4`): non sa aggiornarsi; il blocco offre il file da salvare in Download (`saveUrl`) da installare a mano una volta.
- **browser**: un normale download.
Il numero di versione dell'app (`android/VERSION`, tre numeri 0–99) diventa `versionCode = maggiore*10000 + minore*100 + correzione`
(1.0.0 → 10000), con la stessa formula in Gradle, nell'app, in `ci/app_ci.py` e nel Brain. Prove: `tests/ui/app_test.py` (tutti i casi del
blocco, con un Brain finto e un'app finta), `app_ci_tests/app_ci_test.py` (le decisioni e i controlli del workflow) e
`android/tools/AggiornamentoTest.kt` (la parte dell'app che scarica e controlla, provata con un server vero).

- Prove: `tests/ui/software_test.py` (soglie, pagina Aggiornamenti, tutti i percorsi dell'aggiornamento con il Brain finto che si riavvia),
  `vzrepo/` con `e2e/e2e_test.py` (installatore e aggiornamenti con un Moonraker vero e systemd finto) e `brain_tests/test_brain.py`.

## Scheda del browser: nome e icona

La scheda si chiama **KlippEye** (`<title>` in `src/index.html`; con un'altra stampante scelta il titolo e l'icona li cambia `usePrinterIdentity`) e mostra il logo KlippEye nello stesso stile
dell'icona dell'app Android: quadrato scuro con il bagliore blu della pagina, logo con i suoi colori (non ridisegnato).

- `build.py` incorpora i tre PNG di `src/icons/` come data URI (nessun file in più, nessuna richiesta a `/favicon.ico`):
  `favicon-32.png` e `favicon-64.png` (angoli arrotondati, il 64 per gli schermi ad alta densità) e
  `apple-touch-icon.png` (180 px, quadrato pieno, usata da iPhone e da Chrome Android per "Aggiungi alla schermata Home").
- Per cambiare disegno o dimensione del logo si modifica `tools/make_favicon.py` (`LOGO_WIDTH`) e si rilancia: riscrive `src/icons/`.
- Per cambiare il nome basta il `<title>`. Il titolo non cambia a runtime e l'app Android (WebView) non lo mostra.
- I browser tengono l'icona delle schede in memoria: dopo l'aggiornamento può servire chiudere la scheda e riaprirla (Ctrl+F5 non sempre basta).
- Prova: `tests/ui/title_icon_test.py`.

## Comportamento dell'originale conservato di proposito

- La finestra "Imposta X / Y / Z" (tocco sulla posizione) parte da 163 / 163 / 5 oppure dall'ultimo valore
  comandato da questa pagina (homing o "vai a posizione"), non dalla posizione letta dalla stampante. Era
  così nella V37. Per farla partire dalla posizione reale basta usare la lettura in `openPositionDialog`
  (`src/app/44-movement.js`).
- Gli avvisi della API key dell'analisi log ("Key troppo corta", errori) e la conferma "Cancellare key?"
  usano i dialoghi nativi del browser (`alert` / `confirm`), come nella V37. L'app Android usa una WebView
  senza `WebChromeClient`: lì questi dialoghi di norma non compaiono e `confirm` risponde "no", quindi in
  app il pulsante "Cancella" della key non fa nulla. Se serve, si possono sostituire con le finestre
  integrate (`ConfirmDialog`, `toast`) in `src/app/54-logs.js`.


## Nome e logo della stampante

`settings.printer = { brand, name }` (in `16-settings.js`, nelle impostazioni condivise): `brand` è `klippeye` (predefinito), `vzbot`, `voron` o `ratrig`; `name` è un testo libero di
al massimo 24 caratteri (`PRINTER_NAME_MAX`, pulito da `cleanPrinterName`). La pagina «Stampante» del menu (`59-settings.js`, `PrinterPage`) li cambia con un'anteprima.
`18-printer-brand.js` decide cosa si vede: nome = `name` oppure il nome della marca; la scritta a due colori «Klipp|Eye» solo per KlippEye senza nome. Il logo di una marca viene, in ordine:
1. da un file della cartella `logos/` del repository (`voron.svg`, `.png` o `.webp`, ecc.), che il backend elenca in `/api/logos` e serve da `/logos/<nome>` (formato e grandezza controllati, vedi `logos/README.md`);
2. dai loghi incorporati dalla build (`src/logos/`, oggi `vzbot.png`; `EMBEDDED_LOGOS` in `01-assets.js`);
3. altrimenti nessuno: la barra mostra solo il nome e la scheda del browser tiene l'icona KlippEye. **Nessun logo di terzi è disegnato nel codice.**

`usePrinterIdentity()` (chiamato da `99-main.js`) scrive `document.title` e ridisegna le icone della scheda (`<link rel="icon">`, `apple-touch-icon`) su un canvas, con lo stesso riquadro viola scuro del logo
KlippEye; se il logo non si può disegnare resta l'icona della pagina. Prova: `tests/ui/printer_test.py`.

## Passaggio da VzBot a KlippEye (pagina Aggiornamenti)

`59b-software-settings.js` riconosce l'installazione vecchia da `/api/version` → `legacy: true` (il backend gira da `~/vzbot`). In quel caso la voce «Aggiornamenti» del menu ha il badge «Nuovo» e la scritta
«Passaggio a KlippEye disponibile», e la pagina ha il blocco `MigrationBlock` (conferma → `POST /api/migrate/start` → segue `/api/migrate/status`, un passo su 6 alla volta; mentre il backend è
fermo dice che «si sta riavviando con il nuovo nome»; a lavoro finito ricarica la pagina). Senza `sudo` senza password il backend risponde `501 no_sudo` e la pagina mostra il comando da
lanciare da terminale. Durante il passaggio Moonraker conosce ancora la voce `vzbot`: `programEntry()` sceglie `klippeye` oppure `vzbot`. Prova: `tests/ui/migrate_test.py`; lo script vero lo prova `e2e/e2e_test.py -k passaggio`.
