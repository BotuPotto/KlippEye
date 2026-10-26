# Guida di KlippEye — passo per passo

**Hai già VzBot (versione 1.0.x) installato?** Vai alla parte **P** qui sotto: il passaggio al nuovo nome si fa con un tasto della dashboard.
**Prima installazione?** Parti dalla **A**.

Le parti: **P.** il passaggio da VzBot a KlippEye (una volta, solo per chi ha già VzBot), **A.** la preparazione (si fa **una volta sola**),
**B.** gli aggiornamenti (si fanno **ogni volta** che c'è una release nuova, e non servono più né SSH né il terminale), **C.** l'app Android
(anche lei si aggiorna da sola, dopo una preparazione una tantum), **F.** il nome e il logo della stampante e **G.** la riparazione automatica dopo un blackout.

---

## P. Hai già VzBot 1.0.x? Il passaggio a KlippEye (una volta sola)

Il progetto ha cambiato nome: **VzBot → KlippEye**. Cambiano la cartella sul Raspberry (`~/vzbot` → `~/klippeye`), i servizi (`vzbot` → `klippeye`,
`vzbot-notifier` → `klippeye-notifier`), i comandi, i nomi dei file e l'app Android. **Le tue impostazioni, la chiave dell'IA e le notifiche non si perdono**:
vengono *copiate* (gli originali restano dove sono). Tutto si fa dalla dashboard, **senza SSH**; se qualcosa va storto lo script rimette tutto com'era.

**P1. Carica la release 1.1.0 su GitHub** (come in B1: estrai `KlippEye-repo-1.1.0.zip`, su GitHub **Add file → Upload files**, trascina tutto, scrivi
`Release 1.1.0` in *Commit changes* e conferma). Il repository l'hai già rinominato in `KlippEye`: va bene così, GitHub inoltra da solo i vecchi indirizzi.

**P2. Aspetta il ✓ verde della costruzione dell'app** (solo se vuoi anche la nuova app subito, vedi P5): scheda **Actions → App Android**, 5-10 minuti.

**P3. Aggiorna dalla dashboard** (come in B2): ☰ → **Aggiornamenti** → **Controlla se c'è una versione nuova** → **Aggiorna** (la voce si chiama ancora *vzbot*: è normale, il nome
cambia al passo successivo). La pagina si ricarica da sola. Nel menu **Aggiornamenti** compare il badge **Nuovo** e la scritta **Passaggio a KlippEye disponibile**.

**P4. Premi «Passa a KlippEye».** Nella stessa pagina c'è il blocco **Passa a KlippEye**: tocca il tasto, leggi cosa succede e conferma. La dashboard mostra i 6 passi
(controlli → copia dei dati → sposta il programma → installa i servizi nuovi → toglie i vecchi → verifica). Per un minuto circa la pagina dice che il programma
«si sta riavviando con il nuovo nome»: aspetta, **si ricarica da sola**. Il tasto è spento durante una stampa.

* Se la pagina scrive che serve la **password di amministratore**, il tasto non può partire da solo: apri SSH e incolla `bash ~/vzbot/scripts/passa-a-klippeye.sh` (fa le stesse cose).
* Se un passo non riesce, lo script **rimette tutto com'era** (servizi, cartella, `moonraker.conf`) e la pagina lo dice: puoi riprovare o mandarmi il messaggio che vedi.
* Controllo finale (facoltativo, da SSH): `klippeye stato` deve elencare `klippeye` e `klippeye-notifier` accesi.
* I vecchi file (`~/printer_data/vzbot`, le copie dei vecchi servizi in `~/printer_data/klippeye/backup/passaggio-…`) restano: cancellali tu quando sei sicuro che vada tutto bene.

**P5. L'app Android nuova.** L'app ha cambiato nome *interno* (`com.klippeye.app`, prima `com.vzbot.dashboard`): per Android è **un'altra app**, quindi la nuova si installa
*accanto* alla vecchia e poi si toglie la vecchia. Serve un passo su Firebase (le notifiche dell'app nuova):

1. **Usa lo STESSO progetto Firebase del Raspberry** (non crearne uno nuovo): l'ID si legge con `grep project_id ~/printer_data/klippeye/service-account.json` (per esempio `vzbot-f256b`). Se l'app e il Raspberry stanno in progetti diversi le notifiche partono ma non arrivano mai.
   Console Firebase → quel progetto → ingranaggio → *Impostazioni progetto* → *Le tue app* → **Aggiungi app** → Android → **nome del pacchetto** `com.klippeye.app` → *Registra app*
   → scarica `google-services.json`. (L'app vecchia resta registrata: non toccarla finché non l'hai disinstallata.)
2. GitHub → *Settings → Secrets and variables → Actions* → apri il segreto `GOOGLE_SERVICES_JSON` → **Update** → incolla il contenuto del file nuovo.
3. Il segreto della chiave: se in C1 avevi chiamato il segreto `VZBOT_CHIAVE_PASSWORD`, va bene lo stesso (il nuovo nome è `KLIPPEYE_CHIAVE_PASSWORD`: GitHub usa
   quello che trova). La chiave di firma dell'app nuova (`android/chiave/klippeye.p12`) la crea GitHub da solo, con la tua stessa password.
4. Scheda **Actions → App Android → Run workflow** (se non è già partita da sola dopo P1) e aspetta il **✓ verde**; poi dashboard → **Aggiornamenti → Aggiorna KlippEye**.
5. **Sul telefono, nell'app vecchia**: ☰ → **Aggiornamenti → App Android** → compare **Installa la nuova app KlippEye**: scarica e installa (Android chiede conferma). Apri la nuova app,
   controlla che funzioni (e che arrivino le notifiche), e **solo dopo disinstalla la vecchia** (Impostazioni → App → VzBot → Disinstalla). Finché sono installate
   tutte e due, le notifiche arrivano a entrambe.
6. Da quel momento l'app si aggiorna come sempre (parte C).

**P6. (Facoltativo) Pulizia su GitHub.** Dopo il passaggio le cartelle vecchie `brain/` e `dashboard/` e i file `scripts/vzbot*` non servono più: le puoi cancellare dal sito
di GitHub (apri il file → icona cestino → *Commit changes*), poi aggiorna dalla dashboard. Non cancellarle *prima* del passaggio: il vecchio servizio le usa per partire.

---

## A. Preparazione (una volta sola)

### A1. Crea il "contenitore" su GitHub

1. Vai su <https://github.com> e crea un account gratuito (se non ce l'hai).
2. In alto a destra clicca **+** → **New repository**.
3. **Repository name**: scrivi `KlippEye`. Scegli **Public** (pubblico: serve perché il Raspberry lo scarichi senza password).
   Spunta **Add a README file** e clicca **Create repository**.

### A2. Carica i file della release

1. Sul PC, estrai il file `KlippEye-repo-1.1.0.zip`: ottieni le cartelle `backend`, `frontend`, `notifier`, `scripts`, `systemd`, `logos`, `docs`,
   `android`, `ci`, la cartella nascosta `.github` (il nome comincia con un punto: su Windows si vede, su Mac si mostra con
   **Cmd + Maiusc + .**) e i file `VERSION`, `README.md`, `CHANGELOG.md` (e `.gitignore`, che se non lo vedi non è un problema).
2. Nella pagina del repository clicca **Add file** → **Upload files**.
3. **Trascina dentro la pagina le cartelle e i file** (tutto insieme). GitHub mantiene le cartelle.
4. In basso, in **Commit changes**, scrivi `Release 1.1.0` e clicca il bottone verde **Commit changes**.

Controlla che nella pagina principale del repository ci siano le cartelle `backend`, `frontend`, `notifier`, `scripts`,
`systemd`, `logos`, `docs`, `android`, `ci`, `.github` e il file `VERSION`. Se **`.github` manca** (alcuni computer non la trascinano) il programma
funziona lo stesso: serve solo a costruire l'app Android, e si aggiunge dopo (vedi C3).

### A3. Installa sul Raspberry (l'unica volta con il terminale)

1. Collegati al Raspberry via SSH (da Windows: PuTTY o "Terminale"; indirizzo `192.168.1.17`, utente `pi`).
2. Copia e incolla queste due righe, **una alla volta**, sostituendo `TUONOME` con il tuo nome utente di GitHub:

   ```
   git clone https://github.com/TUONOME/KlippEye.git ~/klippeye
   bash ~/klippeye/scripts/install.sh
   ```

3. Aspetta la fine (circa un minuto). Ogni passo dice `OK`; se qualcosa non va, lo scrive in chiaro con `AVVISO` o `ERRORE`
   e dice cosa fare. In fondo vedi `Moonraker vede KlippEye`.

Cosa fa `install.sh`, in breve:

* **non cancella niente**: la chiave dell'IA e le notifiche che avevi già (`~/vzbot_ai_config.json`, `~/vzbot-notifier/`, `~/printer_data/vzbot`) vengono
  **copiate** in `~/printer_data/klippeye`; i file e i servizi vecchi restano dove sono (copie in `~/printer_data/klippeye/backup/`);
* installa i servizi `klippeye` (backend + dashboard) e `klippeye-notifier` (notifiche) e li fa partire a ogni accensione;
* **se il backend nuovo non risponde, rimette il servizio com'era** e te lo dice;
* collega KlippEye all'**update manager di Moonraker** (aggiunge due righe a `moonraker.conf` e a `moonraker.asvc`, con copia di
  sicurezza) e riavvia Moonraker, a meno che stia stampando (allora te lo chiede a fine stampa);
* mette due comandi di soccorso: `klippeye` e `klippeye-notifiche`.

Si può rilanciare quando si vuole: ripara senza rompere niente. `bash ~/klippeye/scripts/install.sh --annulla` torna a com'era prima.

### A4. Controlla

Apri la dashboard (`http://192.168.1.17:8085`), tocca il menu **☰** → **Aggiornamenti**: deve scrivere **Release 1.1.0**.

### A5. Notifiche (solo se le vuoi e non le hai già)

Le notifiche usano `notifier.json` e `service-account.json` (la chiave di Firebase), che stanno in `~/printer_data/klippeye/`.
Se le avevi già installate, `install.sh` le ha spostate da solo. Se no, il servizio `klippeye-notifier` resta spento: metti i due
file in quella cartella e rilancia `bash ~/klippeye/scripts/install.sh`. Poi: `klippeye notifiche prova` manda una notifica di prova.

---

## B. Aggiornare (ogni volta)

> **La release 1.1.0 (cambio di nome in KlippEye, scelta del logo della stampante)** per chi ha già VzBot si fa dalla parte **P**. Per chi è già su KlippEye vale questa parte:
> **B1** (carica i file su GitHub), **aspetta il ✓ verde** nella scheda **Actions** → *App Android* (5-10 minuti: `android/VERSION` è già alzato, **non devi cambiare nessun numero**),
> poi **B2** (*Aggiorna KlippEye*: porta sul Raspberry la dashboard e l'app nuova) e, sul telefono, i passi 4 e 5 di **C7**.

### B1. Carica i file nuovi su GitHub (dal PC)

1. Estrai il pacchetto della release nuova (per esempio `KlippEye-repo-1.1.0.zip`).
2. Su GitHub apri il repository `klippeye` → **Add file** → **Upload files**.
3. Trascina **tutte** le cartelle e i file del pacchetto (anche quelli che non sono cambiati: GitHub vede da sé quali sono diversi).
   Tieni sempre **insieme** il backend, la dashboard e `VERSION`: così sono della stessa release.
4. In **Commit changes** scrivi `Release 1.1.0` (il numero nuovo) e clicca **Commit changes**.

### B2. Premi "Aggiorna" nella dashboard

1. Dashboard → **☰** → **Aggiornamenti**.
2. Tocca **Controlla se c'è una versione nuova**. Compare *Disponibile la release 1.1.0 (ora hai la 1.0.1)* con l'elenco delle modifiche.
3. Tocca **Aggiorna KlippEye** → **Aggiorna**.
4. Aspetta circa **20 secondi**: il backend si riavvia (la pagina per un attimo non risponde, è normale) e **la pagina si ricarica da sola**.
   Le impostazioni e la chiave dell'IA restano.

Durante una stampa il tasto è spento: aggiorna a stampa finita (il backend si riavvia). La stampa in sé non dipende dal backend, ma
il monitor IA si ferma per qualche secondo.

Si può fare lo stesso da **Mainsail/Fluidd** → *Machine* → *Update Manager* → voce **klippeye**.

### B3. Se qualcosa non va

| Cosa vedi | Cosa fare |
|---|---|
| La nuova release non funziona come speravi | Dashboard → Aggiornamenti → **Torna alla versione precedente** |
| La pagina dice che i file sul Raspberry sono "modificati a mano" | Dashboard → Aggiornamenti → **Ripristina i file del programma** (impostazioni e chiavi non si toccano) |
| La dashboard è **bianca** o non si apre dopo un blackout | Di solito **non devi fare niente**: i file rovinati si rimettono a posto da soli a ogni avvio (parte **G**). Se dopo un minuto non è cambiato nulla: Mainsail → *Update Manager* → **klippeye** → *Recover* |
| La dashboard non si apre più | Mainsail → *Update Manager* → **klippeye** → *Rollback* (o *Recover*). Oppure SSH: `klippeye stato`, `klippeye log`, `klippeye aggiorna --forza` |
| Il backend non risponde | SSH: `klippeye riavvia` (oppure Mainsail → *Machine* → servizio `klippeye` → Restart) |
| Moonraker "non conosce ancora KlippEye" | SSH: `bash ~/klippeye/scripts/install.sh`, poi riavvia Moonraker dal menu Riavvia |

Comandi di soccorso (SSH): `klippeye stato`, `klippeye versione`, `klippeye log`, `klippeye riavvia [backend|notifiche|tutto]`,
`klippeye aggiorna [--forza]`, `klippeye notifiche prova`, `klippeye annulla`. `klippeye aiuto` li elenca.

---

## C. L'app Android

L'app KlippEye (la finestra sulla dashboard, con le notifiche) si aggiorna **dalla dashboard**, come il resto. Lo fa così: **GitHub costruisce l'app da solo**
(un suo computer la compila e la firma, in 5-10 minuti), il Raspberry la riceve con il solito «Aggiorna KlippEye» e il telefono la prende dal
Raspberry con un tasto, **Aggiorna l'app**. Android chiede sempre conferma prima di installare: non si può evitare, e va bene così.

L'app ha un numero di versione suo, scritto nel file `android/VERSION` (parte da **1.0.0**). **Per fare un'app nuova si alza quel numero.**

### C1. Scegli la password della chiave (obbligatorio, una volta)

Android aggiorna un'app solo se è firmata sempre con la **stessa chiave**. La chiave la crea GitHub la prima volta e la chiude con una password
che scegli tu.

1. Pensa una **frase lunga** (almeno 16 caratteri, meglio quattro o cinque parole che ricordi) e **scrivila in un posto sicuro** (un gestore di password,
   un foglio). Chi non la conosce non può firmare app che il tuo telefono accetti.
2. Su GitHub apri il repository → **Settings** (la scheda in alto, con l'ingranaggio) → a sinistra **Secrets and variables** → **Actions**
   → **New repository secret**.
3. In **Name** scrivi esattamente `KLIPPEYE_CHIAVE_PASSWORD`. In **Secret** incolla la tua frase (su **una riga sola**). Clicca **Add secret**.

### C2. Le notifiche (facoltativo)

Se vuoi le notifiche sul telefono serve il file `google-services.json` di Firebase (quello dell'app Android `com.klippeye.app`: nella
console Firebase → ingranaggio → *Impostazioni progetto* → *Le tue app* → **google-services.json**). Aprilo con il Blocco note, **seleziona tutto e copia**.
Come in C1, crea un secondo segreto: **Name** `GOOGLE_SERVICES_JSON`, **Secret** il testo copiato. Senza questo segreto l'app si costruisce lo stesso ma senza notifiche.

### C3. Controlla che ci sia il "costruttore"

Nel repository deve esserci il file `.github/workflows/app.yml`. Se non lo vedi (la cartella `.github` non è stata caricata):

1. Nella pagina principale: **Add file** → **Create new file**.
2. Nella casella del nome scrivi `.github/workflows/app.yml` (quando scrivi le barre `/` GitHub crea le cartelle).
3. Apri sul PC il file `app.yml` che sta nella cartella `.github/workflows` del pacchetto (con il Blocco note), **copia tutto** e incollalo nella grande casella di testo.
4. In alto a destra **Commit changes…** → **Commit changes**.

### C4. Fai costruire la prima app

1. Scheda **Actions** (in alto) → a sinistra **App Android** → a destra **Run workflow** → **Run workflow** (verde).
   *(Se GitHub chiede di abilitare i workflow: **I understand my workflows, go ahead and enable them**.)*
   *(Quando hai caricato i file la prima volta GitHub ha già provato a costruire l'app: se ancora non c'era il segreto, ha scritto in giallo «manca il segreto
   KLIPPEYE_CHIAVE_PASSWORD» e non ha fatto niente. È normale: ora che c'è, la costruzione si avvia a mano da qui.)*
2. Aspetta. Il pallino giallo gira per 5-10 minuti (la prima volta anche di più), poi diventa **verde ✓**. Se diventa **rosso ✗** apri il passo con la X: il messaggio
   spiega cosa manca (vedi C8).
3. Cosa ha fatto: ha creato la chiave `android/chiave/klippeye.p12` (cifrata con la tua password), ha compilato e firmato l'app e ha messo nel repository la cartella
   **`apk/`** con `KlippEye.apk` e `versione.json`.

### C5. Porta l'app sul Raspberry

Dashboard → **☰** → **Aggiornamenti** → **Controlla se c'è una versione nuova** → **Aggiorna KlippEye**. Poi, nello stesso menu, il blocco **App Android** dice
*L'app Android 1.0.0 è pronta*.

### C6. Installa l'app sul telefono (la prima volta)

1. **Se sul telefono c'è già un'app KlippEye installata da Android Studio, disinstallala** (Impostazioni → App → KlippEye → Disinstalla): Android non permette di mettere
   sopra un'app firmata con un'altra chiave. Non perdi niente: indirizzi, soglie e chiave dell'IA stanno sul Raspberry.
2. Dal telefono (a casa, o con ZeroTier) apri nel browser `http://192.168.1.17:8085` → **☰** → **Aggiornamenti** → blocco **App Android** → **Scarica l'app**.
3. Apri il file scaricato (notifica «Download completato», o app **File** → *Download*). Android chiede di **consentire l'installazione da questa fonte** (il browser):
   concedi, poi **Installa**.
4. Apri KlippEye. Da ora in poi l'app si aggiorna da sola (C7).

### C7. Un'app nuova (ogni volta)

1. Carica su GitHub i file nuovi della cartella `android/` (come in B1) **e alza il numero in `android/VERSION`**: su GitHub apri il file `android/VERSION` → icona
   **matita** → cambia `1.0.0` in `1.0.1` → **Commit changes**. (Se non alzi il numero GitHub non costruisce niente e lo scrive nel riepilogo.)
2. GitHub parte da solo: scheda **Actions** → *App Android* → attendi il **✓ verde** (5-10 minuti). Mette l'app nuova in `apk/`.
3. Dashboard → **Aggiornamenti** → **Controlla** → **Aggiorna KlippEye** (porta l'app sul Raspberry).
4. **Sul telefono**, nell'app KlippEye: **☰** → **Aggiornamenti** → **App Android** → **Aggiorna l'app**. Compare una barra mentre scarica. Android chiede conferma:
   tocca **Aggiorna**. *(La prima volta chiede prima il permesso «Installa app sconosciute» per KlippEye: attivalo nella pagina che si apre e torna all'app, l'aggiornamento riparte da solo.)*
5. Quando ha finito, **riapri KlippEye dall'icona** (Android chiude l'app durante l'installazione).

### C8. Se qualcosa non va

| Cosa vedi | Cosa fare |
|---|---|
| Actions rosso: *Manca il segreto KLIPPEYE_CHIAVE_PASSWORD* | Rifai C1: il nome del segreto deve essere identico |
| Actions rosso: *password troppo corta* / *ha un «a capo»* | Rifai il segreto con una frase di almeno 16 caratteri su una riga sola |
| Actions rosso: *la password … non apre la chiave* | Hai cambiato la password: rimetti quella di prima. Se l'hai persa: su GitHub cancella il file `android/chiave/klippeye.p12`, poi **Run workflow** spuntando **nuova_chiave**. Le app già installate vanno disinstallate e reinstallate una volta |
| Actions rosso: *firmato con una chiave DIVERSA* | Come sopra: o rimetti la chiave e la password di prima, o accetti il cambio con **nuova_chiave** |
| Actions verde ma «Niente da costruire» | Non hai alzato il numero in `android/VERSION` (C7). Per ricostruire lo stesso numero: **Run workflow** spuntando **forza** |
| Actions rosso al salvataggio (*permission denied*) | Settings → **Actions** → **General** → *Workflow permissions* → **Read and write permissions** → Save, poi rilancia |
| Actions rosso: *android/VERSION deve contenere tre numeri…* | Scrivi la versione come `1.0.1` (tre numeri da 0 a 99 separati da punti) |
| Il blocco dice *non c'è ancora nessuna app* | GitHub non ha ancora costruito l'app (C4) o non hai ancora fatto «Aggiorna KlippEye» (C5) |
| Il blocco dice *non è completa* | Un aggiornamento era a metà: aspetta qualche secondo e tocca **Controlla** |
| Android: *App non installata… in conflitto* | C'è ancora l'app vecchia con un'altra firma: disinstallala (C6, punto 1) |
| L'app dice che non può installare | Attiva «Consenti da questa fonte» per KlippEye; con l'**Auto Blocker** di Samsung attivo non si può: Impostazioni → Sicurezza e privacy → Auto Blocker → spegni, poi riprova |
| Il tasto «Aggiorna l'app» non compare | Si vede solo dentro l'app KlippEye; da un browser c'è «Scarica l'app». Se hai un'app vecchia, installa una volta quella nuova (C6) |

### C9. Cose da sapere

* La chiave sta nel repository (pubblico) ma è **cifrata dalla tua password**: scegli una frase lunga e non scriverla mai nel repository. Anche con la chiave, il tuo telefono installa solo dopo il tuo OK.
* Ogni app nuova aggiunge circa 8 MB al repository (la storia conserva le versioni vecchie): succede solo quando alzi il numero, quindi poche volte.
* Il computer di GitHub è gratuito per i repository pubblici.
* L'APK in `apk/` e la chiave in `android/chiave/` li scrive GitHub: non si modificano a mano.

---

## D. Dove stanno le cose (e perché)

* `~/klippeye` è il **programma**: una copia del repository GitHub. **Non si modifica a mano** (Moonraker rifiuterebbe di aggiornare
  finché ci sono file cambiati: la dashboard allora offre "Ripristina i file del programma").
* `~/printer_data/klippeye` sono **le tue cose**: soglie del monitor (`brain.json`, si cambiano dalla dashboard), chiave dell'IA
  (`ai.json`), notifiche. Gli aggiornamenti non ci mettono mano. Per salvarle basta copiare quella cartella.
* `~/klippeye/android` sono i sorgenti dell'app e `~/klippeye/apk` l'ultimo APK costruito da GitHub: il Raspberry li riceve con l'aggiornamento e li offre al telefono.
* Il repository è **pubblico**: non caricarci mai chiavi o password. (L'unica chiave che c'è, `android/chiave/klippeye.p12`, è cifrata con la password che sta nei segreti di GitHub.)
* Per i nomi dei file e dei servizi vedi la tabella nel [README](../README.md).

## E. Come funziona l'aggiornamento (per chi è curioso)

Moonraker ha un componente, l'*update manager*, che sa tenere aggiornata una cartella git. `install.sh` gli aggiunge
questa voce in `moonraker.conf`:

```
[update_manager klippeye]
type: git_repo
path: ~/klippeye
origin: https://github.com/TUONOME/klippeye.git
primary_branch: main
channel: dev
managed_services: klippeye
```

Quando premi **Aggiorna**, Moonraker confronta `~/klippeye` con GitHub, scarica le differenze e **riavvia il servizio `klippeye`**
(per questo il servizio si deve chiamare così e deve stare in `moonraker.asvc`). Il backend, appena riparte, serve la dashboard nuova.
Moonraker controlla GitHub da solo ogni tanto; il tasto *Controlla* lo fa subito.

**L'app** segue la stessa strada con un passo in più: la modifica di `android/VERSION` fa partire il workflow `.github/workflows/app.yml`, che costruisce l'APK
e lo salva in `apk/` (con un file `versione.json` che ne dice versione, grandezza e impronta). L'aggiornamento di Moonraker porta `apk/` sul Raspberry; il backend lo offre
su `/app/KlippEye.apk` solo se grandezza e impronta del file coincidono con `versione.json`. La dashboard dentro l'app confronta la versione installata con quella offerta e,
al tocco di **Aggiorna l'app**, chiede all'app di scaricare il file (controllando di nuovo l'impronta) e di aprire l'installazione di Android.

## F. Il nome e il logo della stampante

Nella dashboard: **Impostazioni (☰) → Stampante**. Lì scegli il **logo** da mostrare nella barra in alto, nel menu e nella scheda del browser tra **KlippEye** (il predefinito),
**VzBot**, **Voron** e **RatRig**, e puoi scrivere un **nome** tuo (per esempio `VzBot.287`, fino a 24 caratteri): senza nome compare quello della marca. La scelta vale su tutti i
dispositivi (sta nelle impostazioni condivise) e cambia anche il **titolo e l'icona della scheda del browser**; per KlippEye senza nome restano quelli di KlippEye.

I loghi dei costruttori sono marchi loro: KlippEye **non li disegna** e usa solo i file ufficiali. Il logo di VzBot è già dentro la dashboard. Per **Voron** e **RatRig**
(o per sostituire quello di VzBot) metti il file ufficiale nella cartella `logos/` del repository, con questi nomi: `voron.svg` (oppure `.png` o `.webp`), `ratrig.svg`, `vzbot.svg`…
Si carica come ogni altro file (**Add file → Upload files**, vedi B1), poi dalla dashboard **Aggiorna KlippEye**: il logo compare subito, senza ricostruire niente. Le regole
(formati, grandezza massima 2 MB) sono in `logos/README.md`. Finché il file non c'è, per quella marca la barra mostra solo il nome.

## G. Dopo un blackout: la riparazione automatica

Se la corrente salta mentre il Raspberry scrive sulla scheda, un file del programma può restare **vuoto o a metà**. Prima il risultato era la dashboard **bianca**
(oppure il servizio che non partiva) finché non facevi *Recover* da Mainsail. Ora ci pensa KlippEye da solo, **senza internet e senza che tu faccia niente**:

1. **Prima di ogni avvio del servizio** (quindi anche a ogni riaccensione del Raspberry) lo script `scripts/ripara.sh` confronta i file del programma
   (backend, dashboard, notifiche, comandi, servizi, app) con la copia «buona» che git tiene dentro `~/klippeye/.git`, sullo stesso Raspberry.
   Quelli vuoti, troncati, rovinati o spariti vengono rimessi a posto uno per uno; gli altri non si toccano. Se git è rimasto «bloccato» dal blackout, toglie il blocco.
2. **All'avvio del backend** rifà lo stesso controllo (copre anche i Raspberry il cui servizio non ha ancora la riga di cui sopra: se il sistema lo permette senza password,
   il backend la aggiunge da solo come integrazione `klippeye.service.d/ripara.conf`; `install.sh` poi la sostituisce con quella definitiva).
3. **Quando apri la dashboard** e la pagina risulta vuota o tagliata, la rimette a posto al volo prima di mostrartela. Se non ci riesce vedi per qualche secondo una pagina
   «KlippEye sta rimettendo a posto i suoi file» che si ricarica da sola, invece di una pagina bianca.

**Cosa non tocca mai:** le tue impostazioni, la chiave dell'IA, le notifiche, i `.cfg` di Klipper (stanno fuori dal programma) e i file *tuoi* che hai aggiunto dentro la cartella.
**Cosa non può fare:** se è rovinata la memoria di git stessa (`~/klippeye/.git`) o la scheda SD è guasta, lo scrive nel registro e serve il solito *Recover* da Mainsail
(o `klippeye aggiorna --forza` da SSH). Non sostituisce il buon senso: un gruppo di continuità (UPS) o lo spegnimento da Mainsail evitano il problema alla radice.

Per sapere cosa è successo: `klippeye ripara log` (SSH) oppure il file `~/printer_data/klippeye/riparazioni.log`; `klippeye stato` mostra l'ultimo ripristino e
`/api/version` il campo `repair`. Per controllare a mano: `klippeye ripara`.
**Se modifichi i file del programma a mano** (sconsigliato, ma succede) la riparazione li rimetterebbe com'erano: prima crea un file vuoto
`~/printer_data/klippeye/non-riparare` (`touch ~/printer_data/klippeye/non-riparare`), e toglilo quando hai finito.

---

## H. Monitor IA: come ridurre i falsi allarmi

Il monitor guarda la camera ogni circa 3 secondi. Dalla 1.1.0 confronta ogni foto con uno **sfondo** (la mediana delle ultime foto) invece che con la foto precedente, ignora i cambi di luce e
vuole che il cambiamento **resti** per alcuni controlli. Se qualcosa scatta, manda all'IA online la foto di adesso e quella di prima.

Cosa regolare in *Impostazioni → Monitor IA* se hai ancora falsi allarmi:

| Se succede… | Prova a… |
|---|---|
| Allarmi quando passa la testina | lasciare acceso «Ignora i movimenti passeggeri»; alzare «Controlli di fila in cui il cambiamento deve restare» (3 → 4 o 5) |
| Allarmi quando cambia la luce | tenere «Cambio di luce» a 30 (abbassa per essere più severo); fissare l'esposizione della camera e coprire il LED con carta da forno |
| L'IA segnala problemi dubbi | alzare «Fiducia minima dell'IA» (70 → 80); nel pannello Notifiche alzare anche la «confidenza minima» |
| Non si accorge di un guasto vero | abbassare «Movimento ai bordi» o allargare «Area controllata» |

Ogni allarme salva l'immagine in `~/printer_data/klippeye/allarmi/`: l'elenco è nel pannello del monitor e in `/api/print/alerts/history`. Guardarle aiuta a capire cosa ha fatto scattare il monitor.

