# Guida di KlippEye

KlippEye è una dashboard, un backend e un monitor IA della stampa per stampanti 3D con **Klipper + Moonraker** su un Raspberry Pi
(o un qualsiasi computer Linux accanto alla stampante), con notifiche push e un'app Android. Questa guida va dall'installazione
all'uso di tutti i giorni. *English version: [GUIDE.md](GUIDE.md) (è quella di riferimento: questa ne è la traduzione).*

**Avvio rapido (circa 15 minuti):** installa con le due righe del [capitolo 2](#2-installazione), apri
`http://<indirizzo del Raspberry>:8085` e segui la **configurazione guidata** che si apre da sola ([capitolo 3](#3-prime-impostazioni)).
Il resto di questa guida c'è quando ti serve; ogni pagina della dashboard ha anche il suo **?**.

**Indice:** 1. [Cosa serve](#1-cosa-serve) · 2. [Installazione](#2-installazione) · 3. [Prime impostazioni](#3-prime-impostazioni) ·
4. [Aggiornamenti](#4-aggiornamenti) · 5. [Monitor IA](#5-monitor-ia) · 6. [App Android e notifiche](#6-app-android-e-notifiche) ·
7. [Password e sicurezza](#7-password-e-sicurezza) · 8. [Dopo un blackout](#8-dopo-un-blackout) ·
9. [Dove stanno le cose](#9-dove-stanno-le-cose) · 10. [Se qualcosa non va](#10-se-qualcosa-non-va) ·
A. [Costruire la propria app Android](#a-costruire-la-propria-app-android)

---

## 1. Cosa serve

**Da avere già:**

* una stampante con **Klipper e Moonraker** su un Raspberry Pi (o un qualsiasi computer Linux accanto alla stampante), installati
  con MainsailOS, FluiddPi, KIAUH o a mano. Mainsail o Fluidd possono restare: KlippEye lavora accanto a loro;
* l'**accesso SSH** al Raspberry, **una volta**, per l'installazione (con il tuo utente: non serve che sia `pi`). Tutto il resto si
  fa dalla dashboard;
* internet sul Raspberry (per installare, per gli aggiornamenti, per le notifiche e per il monitor IA).

**Facoltativi:** una **camera** con crowsnest (come per Mainsail: MainsailOS e KIAUH lo installano già), la **chiave di un
servizio IA** per il monitor IA (Groq è gratis), un **telefono** per le notifiche (Android con l'app KlippEye, o qualsiasi telefono
con l'app ntfy).

**Cosa installa KlippEye da solo** (con `apt`, chiedendo la password una volta, solo se manca):

| Pacchetto | A cosa serve |
|---|---|
| `git` | aggiornamenti e autoriparazione dopo un blackout |
| `python3-flask`, `python3-requests` | il backend e la dashboard |
| `python3-numpy` | la calibrazione della camera (e il monitor IA) |
| `python3-opencv` | il monitor IA: guardare le foto della camera (si salta con `--no-ai`) |

Funziona su Raspberry Pi OS e MainsailOS di ogni versione recente (Debian 11 «Bullseye», 12 «Bookworm», 13 «Trixie») con Python
3.7 o più nuovo. Sul tuo computer non va installato niente: basta un browser.

## 2. Installazione

Collegati al Raspberry con SSH (`ssh <utente>@<indirizzo del Raspberry>`; su MainsailOS l'utente di solito è `pi`) e incolla queste
righe, una alla volta:

```
sudo apt update && sudo apt install -y git
git clone https://github.com/BotuPotto/KlippEye.git ~/klippeye
bash ~/klippeye/scripts/install.sh
```

La prima riga serve solo se `git` non c'è ancora (su MainsailOS c'è già: non fa danni). L'installazione controlla cosa manca e lo
installa da sola: la prima volta, con OpenCV, ci vogliono alcuni minuti; poi circa un minuto. Ogni passo dice `OK`; se qualcosa non va
lo scrive in chiaro (`WARNING` o `ERROR`) e dice cosa fare (i messaggi dell'installazione sono in inglese). Alla fine mostra
l'indirizzo della dashboard e `Moonraker sees KlippEye`.

Cosa fa l'installazione:

* controlla **Python, git e i moduli** che servono e **installa quelli che mancano** (tabella qui sopra). Senza `flask`, `requests`
  o `numpy` si ferma prima di toccare qualunque cosa e dice il comando da scrivere;
* crea la **cartella dei dati** `~/printer_data/klippeye` (impostazioni, chiave dell'IA, notifiche): gli aggiornamenti non la
  toccano mai. Va bene qualunque utente, non solo `pi`: le cartelle della stampante (config, log, `printer_data` o
  `printer_1_data` con più stampanti, la vecchia `~/klipper_config`) vengono chieste a Moonraker. Per scegliere la cartella a mano:
  `KLIPPEYE_PRINTER_DATA=~/printer_2_data bash ~/klippeye/scripts/install.sh`;
* installa i servizi **`klippeye`** (backend e dashboard, porta **8085**) e **`klippeye-notifier`** (notifiche push e
  pausa automatica), che partono a ogni accensione. Se il backend nuovo non risponde rimette tutto com'era;
* aggiunge due comandi da terminale, `klippeye` e `klippeye-notifiche`;
* collega KlippEye all'**update manager di Moonraker** (una voce `[update_manager klippeye]` in `moonraker.conf` e due righe in
  `moonraker.asvc`, con copie di sicurezza) e riavvia Moonraker, a meno che stia stampando.

Si può rilanciare quando si vuole: ripara senza rompere niente. Opzioni:

* `--no-ai`: non installa OpenCV (il monitor IA resta spento; si aggiunge dopo rilanciando senza `--no-ai`);
* `--no-packages`: non installa niente con `apt`, dice solo cosa manca;
* `--no-moonraker`: non tocca la configurazione di Moonraker;
* `--channel=dev`: ogni modifica invece delle release provate (vedi 4);
* `--undo`: toglie servizi, comandi e voce di Moonraker (le cartelle e i pacchetti restano);
* `--help`.

Apri la dashboard: **`http://<indirizzo del Raspberry>:8085`** (lo stesso indirizzo di Mainsail, con la porta 8085). Si apre la
**configurazione guidata** (capitolo 3).

**La camera e il monitor IA.** Il monitor IA e la calibrazione prendono una foto alla volta dalla camera (lo *snapshot*). Di solito
non c'è niente da fare: con crowsnest l'indirizzo è `/webcam/?action=snapshot` e KlippEye lo ricava da solo. Per controllarlo:
**Impostazioni → Camera → Snapshot → Prova: scatta una foto** mostra la foto esattamente come la riceve il Raspberry. Con un'altra
camera scrivi lì lo stesso «URL Snapshot» che usi in Mainsail.

## 3. Prime impostazioni

**La prima volta che apri la dashboard parte la configurazione guidata**: nove passi (nome e logo, camera, indirizzi, funzioni
della stampante, notifiche, monitor IA, password) con due righe di spiegazione ciascuno. Ogni passo si può saltare, e l'ultimo
dice cosa è fatto e cosa resta da fare. Si ripete quando vuoi da **Impostazioni → Configurazione guidata**.

Ogni pagina ha un pulsante **?** nella barra del titolo che apre una breve guida (con un disegno dove serve: dove toccare l'ugello
nella calibrazione, a cosa servono gli indirizzi, come arrivano le notifiche); alcuni gruppi hanno un loro piccolo **?**.

Tutto sta nel menu **☰ (Impostazioni)**, in quattro gruppi. Le impostazioni restano sul Raspberry e valgono su tutti i dispositivi.

* **La stampante**
  * **Nome e logo**: il logo nella barra in alto (KlippEye, VzBot, Voron, RatRig) e un nome tuo, usato anche come titolo della
    scheda del browser. I loghi ufficiali delle marche vanno nella cartella `logos/` del repository (vedi [logos/README.md](../logos/README.md)).
  * **Funzioni della stampante** (segnata *Da controllare* finché non la confermi): cosa fanno i pulsanti che usano le macro della
    tua stampante, vedi sotto.
  * **Z-offset**: i passi della card Z-offset.
* **Camera e monitor IA**
  * **Camera**: il metodo (WebRTC, MJPEG, MJPEG adaptive o una pagina web qualsiasi) e il suo indirizzo. **Importa da Mainsail** li
    prende dalle camere già impostate in Mainsail. In fondo, il collegamento alla calibrazione della camera per il monitor IA.
  * **Monitor IA**: tutto il monitor IA (soglie, calibrazione della camera, registrazioni), vedi 5.
* **Telefono e rete**
  * **Notifiche**: dove arrivano (l'app KlippEye o l'app ntfy), quali ricevere e in che lingua (vedi 6).
  * **Indirizzi**: servono solo se apri KlippEye da fuori casa con ZeroTier, Tailscale o un'altra VPN: l'IP locale del Raspberry e
    quello esterno. Vuoti, la camera usa l'indirizzo da cui hai aperto la dashboard.
* **Sistema**
  * **Accesso**: la password facoltativa (vedi 7).
  * **Aggiornamenti**: release, ritorno alla versione precedente, riavvio dei servizi, app Android.
  * **Lingua**: italiano o inglese, scelta su ogni dispositivo (*Automatico* segue la lingua del dispositivo).

### Funzioni della stampante

Ogni stampante parcheggia, pulisce l'ugello, carica il filamento o accende la luce con le sue macro (oppure non può farlo).
**Impostazioni → Funzioni della stampante** dice cosa fa ogni pulsante della dashboard, e la prima volta KlippEye la compila da
solo: cerca in Klipper i nomi più comuni (`PARK`, `CLEAN_NOZZLE`, `LOAD_FILAMENT`/`FILAMENT_LOAD`/`M701`,
`UNLOAD_FILAMENT`/`M702`, una coppia come `LIGHTS_ON`/`LIGHTS_OFF`) e un'uscita per la luce. Controllala una volta e premi **Va
tutto bene**. Per ogni funzione:

* **Automatico**: quello che KlippEye ha trovato (la pagina dice cosa, oppure che non ha trovato niente e il pulsante non compare);
* **Macro**: una delle tue macro (il campo suggerisce quelle che Klipper ha);
* **G-code**: qualche riga scritta nell'editor della dashboard, che si apre sopra la pagina;
* **Non usata**: il pulsante non compare;
* **Crea una macro per questo**: KlippEye ne propone una (parcheggio in fondo, scalda e carica, scalda e scarica, pulizia su una
  spazzola di cui imposti la posizione), si apre nell'editor e quando salvi finisce in **`klippeye_macros.cfg`**, un file di
  KlippEye accanto a `printer.cfg`. La prima volta `printer.cfg` riceve `[include klippeye_macros.cfg]` in fondo (con una copia di
  sicurezza nella cartella dei dati). Klipper lo legge dopo un riavvio: la pagina propone **Riavvia Klipper adesso** (non durante
  una stampa). Una macro che esiste già nella tua configurazione non si può ricreare con lo stesso nome.

**La luce** si può anche comandare direttamente sulla sua uscita (**Uscita**: un `[output_pin]`, `[led]`, `[neopixel]`...).
Chiunque la cambi, il pulsante legge l'uscita stessa (e gli effetti di *klipper-led_effect* che ci girano sopra), quindi è sempre
giusto, anche quando la luce viene cambiata da Mainsail, KlipperScreen, dalla console o da una macro. Con le macro o il G-code
scegli da dove il pulsante legge lo stato (oppure nessuna: mostra l'ultima richiesta).

**Notifica di cambio filamento**: il telefono riceve *Filamento esaurito* quando
* un **sensore del filamento** (`[filament_switch_sensor]`, `[filament_motion_sensor]`) dice che il filamento è finito durante
  una stampa;
* parte una delle **macro che scegli** (`M600` nel G-code, la tua macro di fine filamento...): KlippEye aggiunge in
  `klippeye_macros.cfg` un piccolo involucro con lo stesso nome (`rename_existing`) che scrive `KlippEye: filament change` nella
  console e poi esegue la tua macro esattamente come prima. Si possono scegliere solo macro che Klipper ha davvero (una sbagliata
  impedirebbe a Klipper di partire);
* compare una **riga della console** che scrivi tu (*Printer paused due to filament runout!* è sempre riconosciuta).

### Movimento

**Impostazioni → Movimento**: **cosa muove Z** (il piatto o la testina: *Automatico* lo legge da Klipper) decide il verso
delle frecce di Z — col piatto, ↑ lo alza verso l'ugello; con la testina, ↑ la alza. Il cerchio X/Y e i tasti Z hanno
sempre i passi da 1 e 10 mm; si possono aggiungere 50 e 100 mm (una corona in più nel cerchio, due tasti Z in più per
ognuno).

**Calibra** (card Movimento) ha anche i **livellamenti** che Klipper offre sulla tua stampante: **Z tilt adjust**
(`[z_tilt]`), **Quad gantry level** (`[quad_gantry_level]`) e, sulle stampanti senza sonda, **Bed screws adjust**
(`[bed_screws]`): l'ugello si ferma sopra ogni vite e una scheda dice cosa fare (la prova del foglio); rispondi *Regolata* se
hai girato la vite, *Va bene* se era già giusta. Klipper rifà il giro finché un giro intero va bene. L'**Axis twist
compensation** usa la calibrazione automatica del Cartographer quando c'è; altrimenti quella di Klipper, con la stessa prova
del foglio in alcuni punti (− / + muovono l'ugello, *Va bene* passa al successivo), poi SAVE_CONFIG.

### Mappa dell'altezza (bed mesh)

La card **Mappa dell'altezza / mesh** (pagina Controllo sul telefono, pagina Calibrazione sul computer), come in Mainsail:
**2D** (vista dall'alto, il retro del piatto in alto, il valore di ogni punto; un tocco dice dov'è un punto) o **3D**
(trascina per girare, pizzica o rotellina per lo zoom, ↻ per tornare); i punti **misurati** o la mesh **interpolata** che
Klipper usa; minimo, massimo, escursione e numero di punti. **Calibra mesh** chiede il nome del profilo (e *Adattiva*:
solo dove ci sono gli oggetti della stampa). **Salva come…** salva come profilo la mesh in uso, **Togli** smette di usarla.
Sotto **Profili**: quelli di `printer.cfg`, con la loro escursione — *Carica*, rinomina, togli. Salvataggi, nomi nuovi e
profili tolti si confermano con SAVE_CONFIG (il pulsante salva in alto).

### Camera a schermo intero

Il pulsante ⛶ della camera (la sua card sul telefono, il riquadro della camera sul computer) la mostra su tutto lo schermo.
Nell'app KlippEye (1.5.0 o più nuova) le barre di Android spariscono e lo schermo si gira in orizzontale da solo. In un
browser che non può girare lo schermo (per esempio un iPhone) è l'immagine a girarsi, così riempie lo schermo tenuto di
lato; il pulsante ↻ lo spegne. Un tocco fa ricomparire i pulsanti; ⤡, Esc o il tasto indietro del telefono escono.

### Console

La console (pagina Controllo sul telefono, la barra in basso sul computer: la sua freccia apre tutto il registro) ha, nella
barra del titolo: **pulisci** (svuota la vista; Klipper tiene le sue righe, la vista mostra quelle che arrivano dopo), le
**opzioni** — *Scorrimento automatico* (segue l'ultima riga), *Più recenti in alto*, *Mostra le temperature* (i messaggi
delle temperature, nascosti di solito), salvate su questo dispositivo — e lo **schermo intero**. Un tocco su un comando lo
rimette nel campo di invio.

### Macro

Le card delle macro (pagina Controllo sul telefono, pagina Calibrazione sul computer) funzionano come in Mainsail.
**Impostazioni → Macro** (o l'ingranaggio di una card) sceglie come:
* **Tutte le macro**: una card con ogni macro della stampante; spegni quelle che non usi mai (le macro il cui nome comincia
  con `_` non vengono mai mostrate);
* **Gruppi**: card tue, ognuna con un **nome**, un **colore** (quelli pronti, o qualsiasi colore sulla ruota di *Personalizzato*), le **macro** che scegli nell'ordine che vuoi, e **quando
  compare**: ferma, in stampa, in pausa (per esempio le macro del filamento anche in pausa, le calibrazioni solo da ferma).

Una macro con parametri ha un ⚙ accanto al nome: apre un modulo con i valori da inviare. La scelta sta nelle impostazioni
condivise, uguale su ogni telefono e computer. Le macro scelte nella vecchia card *Calibrazioni* diventano un gruppo con quel
nome. *Endstop e probe* ora è una card a sé.

### Regolazioni

La card **Regolazioni** (pagina Controllo sul telefono, pagina Dispositivo sul computer) cambia, anche durante una stampa:
i fattori di **velocità** e **flusso** (M220 / M221), il **pressure advance** e il suo smooth time, i **limiti della
macchina** (velocità, accelerazione, velocità negli angoli, minimum cruise ratio) e la **retrazione firmware** (se c'è
`[firmware_retraction]`). Usa − / + o scrivi un valore; sotto ognuno c'è il valore di `printer.cfg`, e la freccia tonda
torna a quello. Niente viene scritto in `printer.cfg`: un riavvio di Klipper riporta i suoi valori.

### Durante la stampa

La **card della stampa** (Home) mostra file, avanzamento, tempo, quanto manca e il layer; sotto, **a che ora finisce**,
la **velocità** e il **flusso volumetrico** del momento. **Più dettagli** apre le stime una per una (secondo il file, il
filamento e lo slicer), il tempo totale con le pause, il filamento usato (m e g), l'altezza, la velocità richiesta e i
fattori di velocità e di flusso.

**Escludi un oggetto**: quando lo slicer etichetta gli oggetti (PrusaSlicer, OrcaSlicer, SuperSlicer «Etichetta oggetti»,
Cura con un plugin) e Klipper ha `[exclude_object]`, la card offre **Escludi un oggetto**: una mappa del piatto con gli
oggetti (quello in stampa adesso in blu) e il loro elenco; scegline uno e **Escludilo**. Non viene più stampato, gli
altri vanno avanti; in quella stampa non si può rimettere.

## 4. Aggiornamenti

**Impostazioni → Aggiornamenti → Controlla se c'è una versione nuova → Aggiorna KlippEye.** Il backend si riavvia per qualche
secondo e la pagina si ricarica da sola. Impostazioni, chiave dell'IA e notifiche restano. Durante una stampa il tasto è spento.

Lo stesso aggiornamento si vede in **Mainsail / Fluidd → Update Manager** (voce `klippeye`), che offre anche *Rollback* e *Recover*.

**Canale degli aggiornamenti** (stessa pagina): **Release stabili** (di serie) installa solo le release che hanno superato tutti
i test automatici su GitHub, con l'etichetta `v1.10.0`, `v1.11.0`…; **Ogni modifica** installa ogni modifica appena arriva su
GitHub, per provare le novità. Quando lo cambi, Moonraker si riavvia per qualche secondo.

| Se… | allora |
|---|---|
| la release nuova non va come speravi | Impostazioni → Aggiornamenti → **Torna alla versione precedente** |
| la pagina dice che i file del programma sono stati modificati a mano | Impostazioni → Aggiornamenti → **Ripristina i file del programma** (impostazioni e chiavi non si toccano) |
| la dashboard non si apre più | Mainsail → Update Manager → `klippeye` → *Rollback* o *Recover*; da SSH: `klippeye status`, `klippeye log`, `klippeye update --force` |

## 5. Monitor IA

Durante una stampa il backend guarda la camera ogni pochi secondi con **OpenCV**, sul Raspberry, senza internet. Confronta ogni
foto con uno *sfondo* fatto dalle ultime foto, ignora i cambi di luce e la testina che passa, e conta solo i cambiamenti che
**restano**. Quando qualcosa di sospetto resta per alcuni controlli, manda la foto (e com'era prima) a un'**IA online**, che giudica
se c'è un problema vero: spaghetti, pezzo staccato, layer shift, warping.

Tutto sta in **Impostazioni → Monitor IA**, una pagina sola, dall'alto in basso:

1. **Monitor attivo** e se il servizio delle notifiche funziona.
2. **Come guarda la stampa**: una riga dice cosa guarda adesso il monitor: **tutto il piatto fuori dai pezzi** (con la camera
   calibrata) oppure solo la **fascia esterna di un rettangolo** (senza). Da qui: **Calibra camera** (sotto), **Soglie del
   monitor** (i numeri fini: sensibilità, quanto deve restare un cambiamento, pause, quando comincia; c'è anche il rettangolo,
   usato solo senza calibrazione) e **Registrazioni** (per misurare il monitor).
3. **Quando vede un problema**: la **fiducia minima dell'IA** (l'unica: 70% è il valore consigliato; sopra l'85% una stampa
   fallita potrebbe non essere fermata), quali difetti contano, quante analisi dell'IA di fila, e le **azioni automatiche**
   (pausa o cancellazione da sole, spente di serie: l'IA può sbagliare e una stampa cancellata non si recupera).
4. **Il servizio IA**: il **servizio** e il **modello** del monitor e le **chiavi** dei servizi IA. KlippEye funziona con
   Groq, Google Gemini, OpenAI, Anthropic (Claude), Mistral, OpenRouter, Meta Llama, Together, Fireworks e qualsiasi altro
   server compatibile con OpenAI (per esempio un modello sulla tua rete: il suo indirizzo, una chiave solo se la chiede).
   Groq, Google Gemini e Mistral hanno un piano gratuito: in **Chiavi dei servizi IA** tocca **Ottieni una chiave** accanto
   al servizio, creala lì e incollala. L'elenco dei modelli viene letto dal servizio con la tua chiave; il monitor ha bisogno
   di un modello che **veda le immagini** (elencati per primi; **Predefinito** è uno che KlippEye sa che funziona). Le chiavi
   restano in `~/printer_data/klippeye/ai.json`, leggibile solo dal servizio; la pagina ne mostra solo gli ultimi 4
   caratteri. Qui c'è anche se mandare la foto di prima. L'**analisi dei log** ha il suo servizio e modello: l'ingranaggio
   accanto ad **Analisi errori e suggerimenti** nella scheda Log di sistema (pagina Config); le chiavi sono le stesse.

**Durante la stampa.** Il badge **AI** nella barra in alto è grigio senza stampa, verde quando va tutto bene, arancione o rosso con
un allarme; toccandolo si apre il **pannello del monitoraggio IA** (stato, punteggio, ultimo giudizio con la foto da ingrandire). Quando
l'IA vede un problema, la **card della stampa** mostra cosa ha visto e chiede: **Problema vero**, **Falso allarme** o **Ignora**.
«Falso allarme» e «Ignora» rimettono il badge verde fino al prossimo allarme; «Problema vero» e «Falso allarme» restano anche
nell'allarme, e servono a misurare il monitor (Registrazioni → Misura adesso). Gli allarmi di una stampa si chiudono quando ne
parte un'altra.

L'IA scrive le sue osservazioni nella lingua delle notifiche; ogni allarme resta con le sue foto (pannello del monitor IA, allarmi in
Registrazioni e `~/printer_data/klippeye/alerts/`). Quando l'IA ha proposto pausa o cancellazione ma nessun difetto arrivava alla
fiducia minima, l'allarme lo dice in arancione («Pausa proposta, sotto la soglia»).

| Se… | prova a… |
|---|---|
| allarmi quando passa la testina | calibrare la camera e regolare i contorni di testina e gantry; alzare «Controlli di fila in cui il cambiamento deve restare» (3 → 4) |
| allarmi quando cambia la luce | tenere «Cambio di luce» a 30; fissare l'esposizione della camera; schermare un LED troppo forte |
| l'IA segnala problemi dubbi | alzare «Fiducia minima dell'IA» (70 → 80) |
| non si accorge di un guasto vero | calibrare la camera (guarda tutto il piatto); controllare gli allarmi in Registrazioni: uno arancione vuol dire fiducia troppo alta |

### Calibrare la camera

**Impostazioni → Monitor IA → Calibra camera** insegna a KlippEye dove ogni punto della stampante compare nell'immagine della camera.
Così il monitor IA sa, a ogni controllo, dove sono la testina e il gantry e li esclude (sono la causa principale dei falsi
allarmi). Circa quindici minuti, una volta; da rifare solo se sposti la camera.

**Prima di iniziare**: piatto pulito, la luce come durante le stampe, stampante ferma. Durante la calibrazione la stampante
si muove da sola: tieni lontane le mani.

1. **Come si muove l'asse Z?** Il **piatto** (VzBot, Voron Trident, RatRig V-Core, quasi tutte le CoreXY) o la **testina**
   (Voron 2.4). KlippEye propone la risposta dalla configurazione di Klipper. Le stampanti con il piatto che si muove in Y
   (Prusa, Ender) non sono ancora supportate.
2. **Homing** della stampante.
3. **Segni** (solo se Z muove il piatto: per la camera l'ugello da solo è sempre alla stessa altezza, quindi sei segni sul
   piatto danno la seconda altezza). Due modi:
   * **Stampa i segni (consigliato)**: **Scarica i segni (STL)**, sei piccole piramidi già posizionate per il tuo piatto.
     Passa il file nello slicer con le tue impostazioni solite (senza supporti, un colore che si distingua dal piatto),
     stampalo e lascialo sul piatto. Poi scegli il G-code che hai stampato e **Leggi i segni da questo file**: KlippEye
     trova dove lo slicer ha messo le piramidi e quanto sono venute alte (se lo slicer le sposta non importa).
   * **Gocce rapide**: scegli le temperature di ugello e piatto e **Fai le 6 gocce**: la stampante lascia sei dischetti di
     filamento (con retrazione e z-hop tra uno e l'altro). Più veloce, meno preciso.
4. **I 12 punti.** Per ogni punto:
   1. premi **Vai al punto**: la stampante si muove e compare un'immagine nuova;
   2. tocca l'immagine dove si trova il punto (vedi la tabella sotto);
   3. si apre una vista ingrandita: tocca di nuovo **esattamente** sul punto;
   4. **Tieni questo punto**.

   | Punti | Cosa succede | Cosa toccare |
   |---|---|---|
   | da 1 a 6 | l'ugello si ferma 3 mm sopra un segno (Z muove il piatto) o in un punto del piatto (Z muove la testina) | il **punto più basso dell'ugello**, la punta di metallo, **non** il segno sotto |
   | da 7 a 12, Z muove il piatto | il piatto scende e l'ugello va in fondo | la **punta in alto del segno** (per una goccia: il centro) |
   | da 7 a 12, Z muove la testina | l'ugello va negli stessi punti, più in alto | il **punto più basso dell'ugello** |

   A ogni punto la pagina mostra un piccolo disegno di cosa toccare. I numeri verdi sono fatti; tocca un numero per vederlo
   o rifarlo. La croce gialla è il tuo tocco, quella verde un punto già tenuto.

   **Homing con i segni sul piatto.** Dopo la stampa dei segni molte stampanti spengono i motori, quindi la pagina rifà
   l'homing. KlippEye legge da Klipper dove fa l'homing di Z e mette le piramidi dell'STL lontane da lì (la pagina dice
   dove); **Fai l'homing** chiede prima se un segno potrebbe stare sotto la testina o la sonda in quel punto (una stampa
   vecchia, una macro `[homing_override]`, niente `z_hop`). Durante la calibrazione i motori restano accesi (il timeout
   di inattività viene allungato e poi rimesso com'era).

   **Più veloce: l'ugello trovato da solo.** Dopo aver toccato l'ugello in un punto, KlippEye può trovarlo negli altri punti
   dell'ugello: **Trova l'ugello da solo negli altri N punti** va in ognuno, sposta per un attimo la testina di lato (per
   vedere dov'è) e cerca la punta che hai toccato (circa 15 secondi a punto; tieni le mani lontane). I punti trovati sono
   blu: **Usa gli N punti trovati** li tiene, e **Calcola** colora in rosso quelli che non tornano, da toccare a mano.
   In un singolo punto, **Vai lì e trova l'ugello da solo** apre la vista ingrandita su quello che ha trovato. I punti dei
   segni (da 7 a 12 quando Z muove il piatto) si toccano sempre a mano.
5. **Calcola la calibrazione**: l'errore medio in pixel (buono: pochi pixel) e, in rosso, i punti da rifare (un tocco sulla
   cosa sbagliata: rifai solo quelli e calcola di nuovo). L'immagine dal vivo mostra la testina e il piatto disegnati sopra:
   muovi la testina con i tasti, il disegno deve seguirla. **Salva la calibrazione**, poi togli i segni.

**Testina e gantry.** Dopo il salvataggio la pagina mostra l'immagine dal vivo con la **testina** (viola) e il **gantry**
(arancione: la barra che porta la testina da un lato all'altro) disegnati sopra. Quello che sta dentro i contorni è ciò che
il monitor esclude, quindi devono coprire le parti, con un po' di margine (molto di più nasconderebbe un problema vicino
all'ugello). Regolali **trascinando i pallini sulla foto** (ogni lato della testina, la sua cima — l'altezza — e i bordi
alto e basso del gantry: la misura si vede mentre trascini) o con **−** e **+** (5 mm alla volta), muovendo la testina con i
tasti per controllare in qualche punto. I pallini che finirebbero uno sopra l'altro (testina piccola o lontana) non
compaiono: le loro misure restano con **−** e **+**:

* testina: quanto sporge **a sinistra, a destra, davanti e dietro l'ugello**, **sopra** la punta dell'ugello e sotto;
* gantry: dove la barra **inizia dietro l'ugello**, quanto è **profonda** e i suoi **bordi basso e alto** sopra la punta
  dell'ugello. Spegnilo se la tua stampante non ha un gantry che attraversa l'immagine.

L'interruttore **Escludi testina e gantry** (acceso di base), nella stessa pagina, accende e spegne le maschere.

**Tutto il piatto, tranne dove sono i pezzi.** Con la calibrazione il monitor sa anche dove sono gli oggetti della stampa e
guarda **tutto il piatto attorno a loro**, non solo i bordi dell'area osservata: conta la plastica che compare dove non
dovrebbe esserci nessun pezzo (spaghetti accanto al pezzo, un pezzo staccato e trascinato), non il pezzo che cresce. I
contorni degli oggetti vengono da `exclude_object` di Klipper quando lo slicer etichetta gli oggetti (PrusaSlicer/SuperSlicer/
OrcaSlicer: *Etichetta oggetti*, e `[exclude_object]` in `printer.cfg`: consigliato), altrimenti dal G-code della stampa,
letto una volta all'inizio. Durante una stampa l'immagine dal vivo di questa pagina li mostra in verde. Interruttore:
**Guarda tutto il piatto, tranne dove sono i pezzi**, nella stessa pagina (acceso di base).
Dove la testina è proprio sopra il pezzo la camera non vede sotto: un guasto si riconosce da ciò che compare attorno al pezzo.

La calibrazione vale **finché la camera non si muove**. Ogni dieci minuti il backend confronta l'immagine con quella presa
alla calibrazione; se la camera si è spostata, la pagina (e la sua riga nel menu) lo dice e il monitor smette di usare la
calibrazione (e le maschere) finché non la rifai. Le misure di testina e gantry restano.

### Misurare il monitor (registrazioni)

Invece di indovinare se una soglia diversa aiuta, misuralo:

1. **Impostazioni → Monitor IA → Registrazioni → Registra le stampe**. Durante ogni stampa il backend conserva le foto guardate dal monitor
   (piccole, circa 150 MB per una stampa di quattro ore) con strato, posizione e punteggio, in `~/printer_data/klippeye/recordings/`.
   Quando lo spazio scelto è pieno si cancellano le stampe più vecchie, e con meno di 1 GB libero sul disco non si registra niente.
2. Dopo ogni stampa, aprila nella stessa pagina: sfoglia le foto e dì **È andata bene** oppure, se è fallita, vai alla prima
   foto in cui si vede il problema e premi **È fallita da qui**. Sotto, **Allarmi di questa stampa** elenca i suoi allarmi,
   ognuno con la foto vista dall'IA (toccala per ingrandirla) e il suo responso. Giudichi se il responso dell'IA corrisponde al
   reale stato della stampa: **Risultato corretto** se corrisponde, **Risultato sbagliato** se no (una pausa per una stampa che andava bene, oppure "continua" mentre qualcosa andava
   storto). Un allarme che l'IA non ha potuto giudicare (un errore del servizio IA) chiede **C'era un problema** o **Nessun
   problema**. *Vedilo tra le foto* torna alla stampa in quel momento. Gli allarmi delle stampe non registrate sono raccolti
   in fondo alla pagina.
3. **Misura adesso** rifà girare il monitor sulle stampe registrate spuntate in *Stampe da usare* (tutte, se non ne togli
   qualcuna: una stampa con un'altra camera o una prova si può escludere), con le soglie in uso adesso, e mostra gli allarmi
   all'ora, quanti erano falsi e se ogni guasto è stato visto (e dopo quanto). Da terminale, per confrontare altre soglie:
   `klippeye replay --set sensitivity=45 --set persist_checks=4` (opzioni: `scripts/replay.py`).
   Con una calibrazione della camera il replay esclude testina e gantry come il monitor dal vivo (sulle stampe registrate
   con KlippEye 1.13 o successivo, che tengono la posizione della testina); `--set machine_masks=off` confronta senza; sulle stampe registrate con la 1.16 o successiva
   (che tengono gli oggetti) si guarda tutto il piatto fuori dai pezzi, `--set expected_zone=off` confronta con la sola fascia esterna.

**Quanto è preciso?** Nella stessa pagina:
* **Precisione dell'IA**: sugli allarmi che hai giudicato, quanto spesso il responso dell'IA corrispondeva alla stampa reale
  (pause giuste, problemi fermati, fermate sbagliate, problemi non visti), e una tabella di cosa avrebbe dato ogni **fiducia
  minima dell'IA** sugli stessi allarmi; se un altro valore è migliore la pagina lo dice e, con almeno 10 allarmi giudicati,
  propone di usarlo.
* **Misura e confronta le opzioni**: il replay anche senza la zona del G-code, senza le maschere, meno e più sensibile, ognuno
  segnato meglio, peggio o uguale: quanto pesa il G-code e se le soglie hanno margine (alcuni minuti; da terminale
  `klippeye replay --current --compare`).

La pagina mostra anche il **carico del monitor**: il tempo di un controllo e la CPU usata dal backend nell'ultimo minuto.

**"AI error 429"** su un allarme vuol dire che il servizio IA ha rifiutato la richiesta: troppe richieste o troppi dati (foto)
per i limiti del suo piano, al minuto o al giorno; l'allarme riporta le parole del servizio. Dalla 1.26.1 il backend aspetta e
riprova una volta quando il servizio chiede di attendere pochi secondi. Se succede spesso (un limite giornaliero), allunga la
*Pausa tra due analisi dell'IA* (Soglie del monitor), spegni *Manda all'IA anche la foto di prima* (una foto per richiesta invece di due), scegli un
modello con limiti più alti o un piano a pagamento del servizio.

## 6. App Android e notifiche

L'app Android è una finestra a tutto schermo sulla dashboard, con notifiche push, download dei file e aggiornamenti da sola.

* **Installarla**: apri la dashboard nel browser del telefono → **Impostazioni → Aggiornamenti → App Android → Scarica l'app**,
  apri il file scaricato e consenti l'installazione da questa fonte. Da lì l'app si aggiorna da sola: **Impostazioni →
  Aggiornamenti → App Android → Aggiorna l'app** (Android chiede sempre conferma).
* **Indirizzi**: al primo avvio l'app chiede l'indirizzo del Raspberry (lo stesso di Mainsail, per esempio `192.168.1.20` o
  `mainsailos.local`) e, se usi ZeroTier o una VPN, quello esterno. Poi li prova due volte ciascuno, alternandoli; se nessuno
  risponde mostra *Riprova* e *Indirizzi*. Si cambiano anche da **Impostazioni → Indirizzi**.
* **Tasto indietro**: chiude la guida o il dialogo aperto e torna alla pagina precedente del menu o al passo precedente della
  configurazione guidata. I collegamenti a siti, store e all'app ntfy si aprono fuori dall'app.

Le **notifiche push** (stampa completata, errore, pausa, filamento finito, allarmi dell'IA) le manda il servizio
`klippeye-notifier`, sempre acceso dal 1.20.0 (fa anche la pausa / l'annullamento automatici scelti nel monitor IA). Le
notifiche viaggiano su [ntfy](https://ntfy.sh), un servizio gratuito: nessun account e nessuna chiave. KlippEye crea un
indirizzo privato (`klippeye-` + 16 lettere e cifre) che conoscono solo i tuoi telefoni.

**Con l'app KlippEye (Android, dalla 1.3.0) non serve altro.** Alla prima apertura l'app chiede *«Vuoi ricevere le notifiche
della stampante su questo telefono?»*: **Imposta** apre la procedura guidata (**Impostazioni → Notifiche → Questo telefono**):

1. **Consenti le notifiche** (la finestra di Android).
2. **Crea l'indirizzo privato sul Raspberry** (un tocco).
3. **Ricevi su questo telefono**: l'app ascolta da sola, anche chiusa e dopo un riavvio del telefono. Una piccola notifica fissa
   *«KlippEye in ascolto»* segnala il collegamento aperto: tienila premuta per nasconderla.
4. **Lascia KlippEye sveglia**: consenti a KlippEye di funzionare senza limiti di batteria, altrimenti Android la addormenta e le
   notifiche arrivano in ritardo.
5. **Controlla che arrivi**: KlippEye manda una prova e la pagina conferma da sola quando arriva sul telefono.

*Non ricevere su questo telefono* la spegne solo su quel telefono. Se cambi indirizzo dalla dashboard, le app KlippEye si
aggiornano da sole la volta dopo che le apri.

**Altri telefoni (iPhone, o chi preferisce l'app ntfy).** Nella stessa pagina, dal browser o sotto *Altri telefoni*:
installa l'app gratuita **ntfy** (Google Play, F-Droid, App Store), **inquadra il codice QR** con la fotocamera (dal browser del
telefono basta toccare *Apri nell'app ntfy*, oppure aggiungi a mano server e argomento) e **invia una notifica di prova**. Più
telefoni possono inquadrare lo stesso codice.

Chi conosce l'indirizzo può leggere le notifiche: non condividere il codice; **Nuovo indirizzo** ne crea un altro (i telefoni con
l'app ntfy vanno abbinati di nuovo). Con un **server ntfy tuo** scrivi il suo indirizzo (e un token, se lo chiede) in *Un server
ntfy tuo*. Non serve riavviare niente: il servizio legge da solo la modifica.

Se la pagina dice che il servizio delle notifiche non si è fatto vivo (installazioni precedenti al 1.20.0), esegui una volta sul
Raspberry il comando che la pagina mostra (`bash ~/klippeye/scripts/install.sh`). Dal terminale: `klippeye notify test` (prova) e
`klippeye notify check` (controllo). La lingua delle notifiche si sceglie in **Impostazioni → Notifiche**; in `notifier.json` puoi
anche scrivere testi tuoi (`"messages": {"complete": "Fatto!"}`).

## 7. Password e sicurezza

* **Password facoltativa**: Impostazioni → **Accesso** → scrivila due volte → **Attiva la password**. Il dispositivo che usi resta
  dentro; gli altri (anche l'app) la chiedono una volta e la ricordano per 6 mesi. Da lì la cambi o la togli, e fai uscire gli altri
  dispositivi. **Dimenticata?** Sul Raspberry: `klippeye password remove` (oppure `klippeye password` per sceglierne una nuova).
* **Controlli di rete**, sempre accesi: il backend risponde solo se lo chiami con un indirizzo IP, il nome del Raspberry o un nome
  della rete di casa (`.local`, `.lan`…), e rifiuta i comandi che arrivano da pagine di altri siti. Per usare un nome tuo:
  `klippeye access host-add stampante.esempio.it`. `klippeye access network-checks off` li spegne.
* La password non protegge Moonraker (porta 7125) né Mainsail/Fluidd, e il traffico resta in chiaro (http) sulla rete di casa.
  **Non aprire mai la porta 8085 su internet**: da fuori usa una VPN (ZeroTier, Tailscale, WireGuard).

## 8. Dopo un blackout

Se la corrente salta mentre il Raspberry scrive, un file del programma può restare vuoto o a metà. KlippEye si ripara da solo,
senza internet: prima di ogni avvio del servizio `scripts/repair.sh` confronta i file del programma con la copia che git tiene in
`~/klippeye/.git` e rimette a posto quelli rovinati; il backend ricontrolla quando parte e quando si chiede la pagina della
dashboard. Le tue impostazioni e la configurazione di Klipper non si toccano mai.

* `klippeye repair log` (o `~/printer_data/klippeye/repair.log`) dice cosa è stato ripristinato; `klippeye repair` controlla a mano.
* Vuoi modificare a mano i file del programma? Prima crea `~/printer_data/klippeye/no-repair`, altrimenti la riparazione li rimette com'erano.
* Se è rovinata la memoria di git stessa, il registro lo dice: usa *Recover* in Mainsail o `klippeye update --force`.

## 9. Dove stanno le cose

| Dove | Cosa |
|---|---|
| `~/klippeye` | il programma: una copia del repository GitHub. Non si modifica a mano (Moonraker rifiuterebbe di aggiornare) |
| `~/printer_data/klippeye` | le tue cose: `monitor.json` (soglie del monitor), `ai.json` (chiave dell'IA), `access.json` (impronta della password), `notifier.json` e `service-account.json` (notifiche), `alerts/`, copie di sicurezza. Per salvarle basta copiare la cartella |
| servizi `klippeye`, `klippeye-notifier` | partono con systemd all'accensione; `klippeye` deve tenere il suo nome: è quello che Moonraker riavvia dopo un aggiornamento |
| database di Moonraker, namespace `klippeye` | le impostazioni della dashboard, uguali su tutti i dispositivi |

**Come funziona l'aggiornamento:** l'installazione aggiunge questa voce a `moonraker.conf`:

```
[update_manager klippeye]
type: git_repo
path: ~/klippeye
origin: https://github.com/BotuPotto/KlippEye.git
primary_branch: main
channel: stable
managed_services: klippeye
```

Con **Aggiorna**, Moonraker scarica da GitHub l'ultima release etichettata (o, sul canale `dev`, l'ultima modifica) in `~/klippeye` e riavvia il servizio `klippeye`; il servizio delle
notifiche si accorge che il suo file è cambiato e riparte da solo. L'app Android arriva per la stessa strada: la cartella `apk/`
del repository contiene l'ultima app costruita da GitHub, e il backend la offre al telefono solo se grandezza e SHA-256
corrispondono ad `apk/version.json`.

## 10. Se qualcosa non va

**Chiedi aiuto?** Allega il rapporto di diagnostica: *Impostazioni → Aggiornamenti → Diagnostica → Scarica il rapporto di
diagnostica*, oppure `klippeye diagnose --save` sul Raspberry. Non contiene chiavi, password o token.

| Cosa vedi | Cosa fare |
|---|---|
| La dashboard non risponde | `klippeye status`; `klippeye restart`; `klippeye log` mostra le ultime righe del registro del backend |
| La pagina dice che il nome non è ammesso | aprila con l'indirizzo IP, oppure ammetti il nome: `klippeye access host-add NOME` |
| Moonraker «non conosce ancora KlippEye» | `bash ~/klippeye/scripts/install.sh`, poi riavvia Moonraker dal menu Riavvia |
| La camera resta nera | Impostazioni → Camera: controlla metodo e indirizzo (o *Importa da Mainsail*); Impostazioni → Indirizzi |
| Il monitor IA non chiama mai l'IA | la chiave dell'IA (5.1); OpenCV installato (`sudo apt install python3-opencv`); il monitor acceso |
| Non arrivano notifiche | `klippeye notify check` elenca cosa manca; `klippeye notify test` manda una prova |
| L'app non riesce a installare un aggiornamento | consenti «Installa app sconosciute» per KlippEye; l'Auto Blocker di Samsung dev'essere spento |

Comandi da terminale: `klippeye status`, `version`, `log [notifier]`, `restart [backend|notifier|all]`, `repair [log]`,
`update [--force]`, `notify test|check`, `password [set|remove|status|logout-all]`, `access ...`, `diagnose [--save]`,
`undo-install`, `help`.
I nomi italiani delle release precedenti (`stato`, `riavvia`, `aggiorna`…) funzionano ancora.

---

## A. Costruire la propria app Android

Serve solo per modificare l'app (le notifiche non ne hanno bisogno: sezione 6). GitHub costruisce l'app gratis per i repository pubblici.

1. Fai un **fork** del repository su GitHub e installa KlippEye dal tuo fork (`git clone https://github.com/<tu>/KlippEye.git`).
2. **Password della chiave di firma**: Android aggiorna un'app solo se è firmata sempre con la stessa chiave. GitHub crea la chiave
   la prima volta e la cifra con una password che scegli tu: nel repository **Settings → Secrets and variables → Actions → New
   repository secret**, nome **`KLIPPEYE_CHIAVE_PASSWORD`**, valore una frase lunga (almeno 16 caratteri, su una riga). Conservala.
3. **Settings → Actions → General → Workflow permissions → Read and write permissions** (il workflow salva l'app in `apk/`).
4. **Actions → App Android → Run workflow**. Dopo 5–10 minuti l'app è in `apk/`; aggiorna KlippEye dalla dashboard e installa l'app da
   Impostazioni → Aggiornamenti → App Android (prima disinstalla un'app firmata con un'altra chiave).
5. **Una versione nuova dell'app**: alza il numero in `android/VERSION` (tre numeri, per esempio `1.2.1`); GitHub la costruisce da solo.

Quando il workflow si ferma spiega a parole cosa non va (segreto mancante, password corta, chiave diversa da quella dell'app
pubblicata…). Dettagli tecnici: [android/README.md](../android/README.md).
