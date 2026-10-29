# Guida di KlippEye

KlippEye è una dashboard, un backend e un monitor IA della stampa per stampanti 3D con **Klipper + Moonraker** su un Raspberry Pi
(o un qualsiasi computer Linux accanto alla stampante), con notifiche push e un'app Android. Questa guida va dall'installazione
all'uso di tutti i giorni. *English version: [GUIDE.md](GUIDE.md) (è quella di riferimento: questa ne è la traduzione).*

**Indice:** 1. [Cosa serve](#1-cosa-serve) · 2. [Installazione](#2-installazione) · 3. [Prime impostazioni](#3-prime-impostazioni) ·
4. [Aggiornamenti](#4-aggiornamenti) · 5. [Monitor IA](#5-monitor-ia) · 6. [App Android e notifiche](#6-app-android-e-notifiche) ·
7. [Password e sicurezza](#7-password-e-sicurezza) · 8. [Dopo un blackout](#8-dopo-un-blackout) ·
9. [Dove stanno le cose](#9-dove-stanno-le-cose) · 10. [Se qualcosa non va](#10-se-qualcosa-non-va) ·
A. [Costruire la propria app Android](#a-costruire-la-propria-app-android)

---

## 1. Cosa serve

* Una stampante con **Klipper e Moonraker** (installati con KIAUH, MainsailOS, FluiddPi o a mano). Mainsail o Fluidd possono
  restare: KlippEye lavora accanto a loro.
* **Python 3.7+**, **git** e i moduli Python `flask` e `requests` (l'installazione dice come installare quello che
  manca). **OpenCV** (`python3-opencv`) serve solo al monitor IA.
* L'accesso SSH al Raspberry, **una volta**, per l'installazione. Tutto il resto si fa dalla dashboard.
* Facoltativi: una camera (crowsnest / camera-streamer, come per Mainsail), la chiave di un servizio IA (Groq è gratis, OpenAI a
  pagamento) per il monitor IA, un telefono Android.

## 2. Installazione

Collegati al Raspberry con SSH (`ssh pi@<indirizzo del Raspberry>`, con il tuo utente) e incolla queste due righe, una alla volta:

```
git clone https://github.com/BotuPotto/KlippEye.git ~/klippeye
bash ~/klippeye/scripts/install.sh
```

Ci vuole circa un minuto. Ogni passo dice `OK`; se qualcosa non va lo scrive in chiaro (`WARNING` o `ERROR`) e dice cosa fare
(i messaggi dell'installazione sono in inglese). Alla fine mostra l'indirizzo della dashboard e `Moonraker sees KlippEye`.

Cosa fa l'installazione:

* crea la **cartella dei dati** `~/printer_data/klippeye` (impostazioni, chiave dell'IA, chiavi delle notifiche): gli
  aggiornamenti non la toccano mai. Va bene qualunque utente, non solo `pi`: le cartelle della stampante (config, log,
  `printer_data` o `printer_1_data` con più stampanti, la vecchia `~/klipper_config`) vengono chieste a Moonraker. Per
  scegliere la cartella a mano: `KLIPPEYE_PRINTER_DATA=~/printer_2_data bash ~/klippeye/scripts/install.sh`;
* installa i servizi **`klippeye`** (backend e dashboard, porta **8085**) e **`klippeye-notifier`** (notifiche push, solo quando
  ci sono le sue chiavi), che partono a ogni accensione. Se il backend nuovo non risponde rimette tutto com'era;
* aggiunge due comandi da terminale, `klippeye` e `klippeye-notifiche`;
* collega KlippEye all'**update manager di Moonraker** (una voce `[update_manager klippeye]` in `moonraker.conf` e due righe in
  `moonraker.asvc`, con copie di sicurezza) e riavvia Moonraker, a meno che stia stampando.

Si può rilanciare quando si vuole: ripara senza rompere niente. Opzioni: `--no-moonraker` (non tocca la configurazione di
Moonraker), `--channel=dev` (ogni modifica invece delle release provate, vedi 4), `--undo` (toglie servizi, comandi e voce di
Moonraker; le cartelle restano), `--help`.

Apri la dashboard: **`http://<indirizzo del Raspberry>:8085`** (lo stesso indirizzo di Mainsail, con la porta 8085).

## 3. Prime impostazioni

Tutto sta nel menu **☰ (Impostazioni)**. Le impostazioni restano sul Raspberry e valgono su tutti i dispositivi.

* **Stampante**: il logo nella barra in alto (KlippEye, VzBot, Voron, RatRig) e un nome tuo, usato anche come titolo della scheda
  del browser. I loghi ufficiali delle marche vanno nella cartella `logos/` del repository (vedi [logos/README.md](../logos/README.md)).
* **Funzioni della stampante** (segnata *Da controllare* finché non la confermi): cosa fanno i pulsanti che usano le macro della
  tua stampante, vedi sotto.
* **Camera**: il metodo (WebRTC, MJPEG, MJPEG adaptive o una pagina web qualsiasi) e il suo indirizzo. **Importa da Mainsail** li
  prende dalle camere già impostate in Mainsail.
* **Indirizzi**: l'IP locale del Raspberry e, se usi una VPN come ZeroTier, quello esterno: camera e app Android usano quello giusto
  a seconda della rete in cui sei.
* **Z-offset**: i passi della card Z-offset.
* **Notifiche**: quali notifiche push ricevere e in che lingua (vedi 6).
* **Monitor IA** e **Soglie del monitor**: vedi 5.
* **Accesso**: la password facoltativa (vedi 7).
* **Aggiornamenti**: release, ritorno alla versione precedente, riavvio dei servizi, app Android.
* **Lingua**: italiano o inglese, scelta su ogni dispositivo (*Automatica* segue la lingua del dispositivo).

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

1. **Chiave dell'IA**: dashboard → **Config → Log di sistema → ⚙️**: scegli il servizio (consigliato Groq, gratis) e incolla la
   chiave. È la stessa dell'analisi dei log. Resta in `~/printer_data/klippeye/ai.json`, leggibile solo dal servizio.
2. **Impostazioni → Monitor IA**: quali difetti contano, quanti verdetti di fila, la fiducia minima e le **azioni automatiche**
   (pausa o cancellazione da sole, spente di serie: l'IA può sbagliare e una stampa cancellata non si recupera).
3. **Impostazioni → Soglie del monitor**: sensibilità, area controllata sulla foto della camera, pause tra due chiamate all'IA,
   quando comincia a controllare. **Consiglio:** disegna l'area controllata solo sul piatto: cinghie e parti del portale in primo
   piano si muovono sempre.

L'IA scrive le sue osservazioni nella lingua delle notifiche; ogni allarme resta con le sue foto (card del monitor IA e
`~/printer_data/klippeye/alerts/`).

| Se… | prova a… |
|---|---|
| allarmi quando passa la testina | lasciare acceso «Ignora i movimenti passeggeri»; alzare «Controlli di fila in cui il cambiamento deve restare» (3 → 4 o 5) |
| allarmi quando cambia la luce | tenere «Cambio di luce» a 30; fissare l'esposizione della camera; schermare un LED troppo forte |
| l'IA segnala problemi dubbi | alzare «Fiducia minima dell'IA» (70 → 80) |
| non si accorge di un guasto vero | abbassare «Movimento ai bordi» o allargare l'area controllata |

### Calibrare la camera

**Impostazioni → Calibra camera** insegna a KlippEye dove ogni punto della stampante compare nell'immagine della camera.
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
5. **Calcola la calibrazione**: l'errore medio in pixel (buono: pochi pixel) e, in rosso, i punti da rifare (un tocco sulla
   cosa sbagliata: rifai solo quelli e calcola di nuovo). L'immagine dal vivo mostra la testina e il piatto disegnati sopra:
   muovi la testina con i tasti, il disegno deve seguirla. **Salva la calibrazione**, poi togli i segni.

**Testina e gantry.** Dopo il salvataggio la pagina mostra l'immagine dal vivo con la **testina** (viola) e il **gantry**
(arancione: la barra che porta la testina da un lato all'altro) disegnati sopra. Quello che sta dentro i contorni è ciò che
il monitor esclude, quindi devono coprire le parti, con un po' di margine (molto di più nasconderebbe un problema vicino
all'ugello). Regolali con **−** e **+** (5 mm alla volta), muovendo la testina con i tasti per controllare in qualche punto:

* testina: quanto sporge **a sinistra, a destra, davanti e dietro l'ugello**, **sopra** la punta dell'ugello e sotto;
* gantry: dove la barra **inizia dietro l'ugello**, quanto è **profonda** e i suoi **bordi basso e alto** sopra la punta
  dell'ugello. Spegnilo se la tua stampante non ha un gantry che attraversa l'immagine.

L'interruttore **Impostazioni → Soglie del monitor → Falsi allarmi → Escludi testina e gantry** (acceso di base) accende e
spegne le maschere.

**Tutto il piatto, tranne dove sono i pezzi.** Con la calibrazione il monitor sa anche dove sono gli oggetti della stampa e
guarda **tutto il piatto attorno a loro**, non solo i bordi dell'area osservata: conta la plastica che compare dove non
dovrebbe esserci nessun pezzo (spaghetti accanto al pezzo, un pezzo staccato e trascinato), non il pezzo che cresce. I
contorni degli oggetti vengono da `exclude_object` di Klipper quando lo slicer etichetta gli oggetti (PrusaSlicer/SuperSlicer/
OrcaSlicer: *Etichetta oggetti*, e `[exclude_object]` in `printer.cfg`: consigliato), altrimenti dal G-code della stampa,
letto una volta all'inizio. Durante una stampa l'immagine dal vivo di questa pagina li mostra in verde. Interruttore:
**Impostazioni → Soglie del monitor → Falsi allarmi → Guarda tutto il piatto, tranne dove sono i pezzi** (acceso di base).
Dove la testina è proprio sopra il pezzo la camera non vede sotto: un guasto si riconosce da ciò che compare attorno al pezzo.

La calibrazione vale **finché la camera non si muove**. Ogni dieci minuti il backend confronta l'immagine con quella presa
alla calibrazione; se la camera si è spostata, la pagina (e la sua riga nel menu) lo dice e il monitor smette di usare la
calibrazione (e le maschere) finché non la rifai. Le misure di testina e gantry restano.

### Misurare il monitor (registrazioni)

Invece di indovinare se una soglia diversa aiuta, misuralo:

1. **Impostazioni → Registrazioni → Registra le stampe**. Durante ogni stampa il backend conserva le foto guardate dal monitor
   (piccole, circa 150 MB per una stampa di quattro ore) con strato, posizione e punteggio, in `~/printer_data/klippeye/recordings/`.
   Quando lo spazio scelto è pieno si cancellano le stampe più vecchie, e con meno di 1 GB libero sul disco non si registra niente.
2. Dopo ogni stampa, nella stessa pagina: segna ogni **allarme** come *Falso allarme* o *Problema vero*, e apri la stampa per
   dire **È andata bene** oppure, se è fallita, vai alla prima foto in cui si vede il problema e premi **È fallita da qui**.
3. **Misura adesso** rifà girare il monitor su ogni stampa registrata, con le soglie in uso adesso, e mostra gli allarmi
   all'ora, quanti erano falsi e se ogni guasto è stato visto (e dopo quanto). Da terminale, per confrontare altre soglie:
   `klippeye replay --set sensitivity=45 --set persist_checks=4` (opzioni: `scripts/replay.py`).
   Con una calibrazione della camera il replay esclude testina e gantry come il monitor dal vivo (sulle stampe registrate
   con KlippEye 1.13 o successivo, che tengono la posizione della testina); `--set machine_masks=off` confronta senza; sulle stampe registrate con la 1.16 o successiva
   (che tengono gli oggetti) si guarda tutto il piatto fuori dai pezzi, `--set expected_zone=off` confronta con la sola fascia esterna.

La pagina mostra anche il **carico del monitor**: il tempo di un controllo e la CPU usata dal backend nell'ultimo minuto.

## 6. App Android e notifiche

L'app Android è una finestra a tutto schermo sulla dashboard, con notifiche push, download dei file e aggiornamenti da sola.

* **Installarla**: apri la dashboard nel browser del telefono → **Impostazioni → Aggiornamenti → App Android → Scarica l'app**,
  apri il file scaricato e consenti l'installazione da questa fonte. Da lì l'app si aggiorna da sola: **Impostazioni →
  Aggiornamenti → App Android → Aggiorna l'app** (Android chiede sempre conferma).
* **Indirizzi**: l'app cerca il Raspberry agli indirizzi di **Impostazioni → Indirizzi**; quando non riesce a collegarsi mostra
  una finestra *Indirizzi*.

Le **notifiche push** (stampa completata, errore, pausa, filamento finito, allarmi dell'IA) le manda il servizio
`klippeye-notifier` attraverso **Firebase Cloud Messaging**. Serve un progetto Firebase comune all'app e al Raspberry:

* sul Raspberry, `~/printer_data/klippeye/notifier.json` e la chiave del service account di Firebase `service-account.json`;
* nell'app, il `google-services.json` dello **stesso** progetto Firebase, già dentro l'app.

L'app pubblicata in questo repository è costruita per il progetto Firebase di chi lo mantiene. **Per ricevere le notifiche dalla
tua stampante oggi serve una tua app**, da un fork del repository (la costruisce GitHub: vedi l'appendice A). È prevista una strada
più semplice che funzioni con l'app pubblicata.

`notifier.json` minimo (il `topic` deve essere quello dentro la tua app, `notification_topic` in
`android/app/src/main/res/values/notifiche.xml`):

```json
{
  "service_account_file": "service-account.json",
  "topic": "il-tuo-argomento-privato"
}
```

Poi rilancia `bash ~/klippeye/scripts/install.sh` (accende il servizio delle notifiche quando trova le chiavi) e prova con
`klippeye notify test`. La lingua delle notifiche si sceglie in **Impostazioni → Notifiche**; in `notifier.json` puoi anche
scrivere testi tuoi (`"messages": {"complete": "Fatto!"}`).

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

Serve solo per avere le proprie notifiche (sezione 6) o per modificare l'app. GitHub costruisce l'app gratis per i repository pubblici.

1. Fai un **fork** del repository su GitHub e installa KlippEye dal tuo fork (`git clone https://github.com/<tu>/KlippEye.git`).
2. **Password della chiave di firma**: Android aggiorna un'app solo se è firmata sempre con la stessa chiave. GitHub crea la chiave
   la prima volta e la cifra con una password che scegli tu: nel repository **Settings → Secrets and variables → Actions → New
   repository secret**, nome **`KLIPPEYE_CHIAVE_PASSWORD`**, valore una frase lunga (almeno 16 caratteri, su una riga). Conservala.
3. **Firebase** (per le notifiche): crea un progetto Firebase, aggiungi un'app Android con nome del pacchetto `com.klippeye.app`,
   scarica il suo `google-services.json` e metti tutto il suo contenuto in un secondo segreto, **`GOOGLE_SERVICES_JSON`**. Nello
   stesso progetto crea una chiave del service account (*Impostazioni progetto → Account di servizio → Genera nuova chiave privata*):
   quel file è il `service-account.json` del Raspberry. Scegli un tuo argomento privato in
   `android/app/src/main/res/values/notifiche.xml` e usa lo stesso in `notifier.json`.
4. **Settings → Actions → General → Workflow permissions → Read and write permissions** (il workflow salva l'app in `apk/`).
5. **Actions → App Android → Run workflow**. Dopo 5–10 minuti l'app è in `apk/`; aggiorna KlippEye dalla dashboard e installa l'app da
   Impostazioni → Aggiornamenti → App Android (prima disinstalla un'app firmata con un'altra chiave).
6. **Una versione nuova dell'app**: alza il numero in `android/VERSION` (tre numeri, per esempio `1.2.1`); GitHub la costruisce da solo.

Quando il workflow si ferma spiega a parole cosa non va (segreto mancante, password corta, chiave diversa da quella dell'app
pubblicata…). Dettagli tecnici: [android/README.md](../android/README.md).
