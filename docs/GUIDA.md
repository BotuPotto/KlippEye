# Guida di VzBot — passo per passo

Tre parti: **A.** la preparazione (si fa **una volta sola**), **B.** gli aggiornamenti (si fanno **ogni volta** che c'è una
release nuova, e non servono più né SSH né il terminale) ed **C.** l'app Android (anche lei si aggiorna da sola, dopo una preparazione una tantum).

---

## A. Preparazione (una volta sola)

### A1. Crea il "contenitore" su GitHub

1. Vai su <https://github.com> e crea un account gratuito (se non ce l'hai).
2. In alto a destra clicca **+** → **New repository**.
3. **Repository name**: scrivi `vzbot`. Scegli **Public** (pubblico: serve perché il Raspberry lo scarichi senza password).
   Spunta **Add a README file** e clicca **Create repository**.

### A2. Carica i file della release

1. Sul PC, estrai il file `VzBot-repo-1.0.0.zip`: ottieni le cartelle `brain`, `dashboard`, `notifier`, `scripts`, `systemd`, `docs`,
   `android`, `ci`, la cartella nascosta `.github` (il nome comincia con un punto: su Windows si vede, su Mac si mostra con
   **Cmd + Maiusc + .**) e i file `VERSION`, `README.md`, `CHANGELOG.md` (e `.gitignore`, che se non lo vedi non è un problema).
2. Nella pagina del repository clicca **Add file** → **Upload files**.
3. **Trascina dentro la pagina le cartelle e i file** (tutto insieme). GitHub mantiene le cartelle.
4. In basso, in **Commit changes**, scrivi `Release 1.0.0` e clicca il bottone verde **Commit changes**.

Controlla che nella pagina principale del repository ci siano le cartelle `brain`, `dashboard`, `notifier`, `scripts`,
`systemd`, `docs`, `android`, `ci`, `.github` e il file `VERSION`. Se **`.github` manca** (alcuni computer non la trascinano) il programma
funziona lo stesso: serve solo a costruire l'app Android, e si aggiunge dopo (vedi C3).

### A3. Installa sul Raspberry (l'unica volta con il terminale)

1. Collegati al Raspberry via SSH (da Windows: PuTTY o "Terminale"; indirizzo `192.168.1.17`, utente `pi`).
2. Copia e incolla queste due righe, **una alla volta**, sostituendo `TUONOME` con il tuo nome utente di GitHub:

   ```
   git clone https://github.com/TUONOME/vzbot.git ~/vzbot
   bash ~/vzbot/scripts/install.sh
   ```

3. Aspetta la fine (circa un minuto). Ogni passo dice `OK`; se qualcosa non va, lo scrive in chiaro con `AVVISO` o `ERRORE`
   e dice cosa fare. In fondo vedi `Moonraker vede VzBot`.

Cosa fa `install.sh`, in breve:

* **non cancella niente**: la chiave dell'IA e le notifiche che avevi già (`~/vzbot_ai_config.json`, `~/vzbot-notifier/`) vengono
  **copiate** in `~/printer_data/vzbot`; i file e i servizi vecchi restano dove sono (copie in `~/printer_data/vzbot/backup/`);
* installa i servizi `vzbot` (Brain + dashboard) e `vzbot-notifier` (notifiche) e li fa partire a ogni accensione;
* **se il Brain nuovo non risponde, rimette il servizio com'era** e te lo dice;
* collega VzBot all'**update manager di Moonraker** (aggiunge due righe a `moonraker.conf` e a `moonraker.asvc`, con copia di
  sicurezza) e riavvia Moonraker, a meno che stia stampando (allora te lo chiede a fine stampa);
* mette due comandi di soccorso: `vzbot` e `vzbot-notifiche`.

Si può rilanciare quando si vuole: ripara senza rompere niente. `bash ~/vzbot/scripts/install.sh --annulla` torna a com'era prima.

### A4. Controlla

Apri la dashboard (`http://192.168.1.17:8085`), tocca il menu **☰** → **Aggiornamenti**: deve scrivere **Release 1.0.0**.

### A5. Notifiche (solo se le vuoi e non le hai già)

Le notifiche usano `notifier.json` e `service-account.json` (la chiave di Firebase), che stanno in `~/printer_data/vzbot/`.
Se le avevi già installate, `install.sh` le ha spostate da solo. Se no, il servizio `vzbot-notifier` resta spento: metti i due
file in quella cartella e rilancia `bash ~/vzbot/scripts/install.sh`. Poi: `vzbot notifiche prova` manda una notifica di prova.

---

## B. Aggiornare (ogni volta)

### B1. Carica i file nuovi su GitHub (dal PC)

1. Estrai il pacchetto della release nuova (per esempio `VzBot-repo-1.0.1.zip`).
2. Su GitHub apri il repository `vzbot` → **Add file** → **Upload files**.
3. Trascina **tutte** le cartelle e i file del pacchetto (anche quelli che non sono cambiati: GitHub vede da sé quali sono diversi).
   Tieni sempre **insieme** il Brain, la dashboard e `VERSION`: così sono della stessa release.
4. In **Commit changes** scrivi `Release 1.0.1` (il numero nuovo) e clicca **Commit changes**.

### B2. Premi "Aggiorna" nella dashboard

1. Dashboard → **☰** → **Aggiornamenti**.
2. Tocca **Controlla se c'è una versione nuova**. Compare *Disponibile la release 1.0.1 (ora hai la 1.0.0)* con l'elenco delle modifiche.
3. Tocca **Aggiorna VzBot** → **Aggiorna**.
4. Aspetta circa **20 secondi**: il Brain si riavvia (la pagina per un attimo non risponde, è normale) e **la pagina si ricarica da sola**.
   Le impostazioni e la chiave dell'IA restano.

Durante una stampa il tasto è spento: aggiorna a stampa finita (il Brain si riavvia). La stampa in sé non dipende dal Brain, ma
il monitor IA si ferma per qualche secondo.

Si può fare lo stesso da **Mainsail/Fluidd** → *Machine* → *Update Manager* → voce **vzbot**.

### B3. Se qualcosa non va

| Cosa vedi | Cosa fare |
|---|---|
| La nuova release non funziona come speravi | Dashboard → Aggiornamenti → **Torna alla versione precedente** |
| La pagina dice che i file sul Raspberry sono "modificati a mano" | Dashboard → Aggiornamenti → **Ripristina i file del programma** (impostazioni e chiavi non si toccano) |
| La dashboard non si apre più | Mainsail → *Update Manager* → **vzbot** → *Rollback* (o *Recover*). Oppure SSH: `vzbot stato`, `vzbot log`, `vzbot aggiorna --forza` |
| Il Brain non risponde | SSH: `vzbot riavvia` (oppure Mainsail → *Machine* → servizio `vzbot` → Restart) |
| Moonraker "non conosce ancora VzBot" | SSH: `bash ~/vzbot/scripts/install.sh`, poi riavvia Moonraker dal menu Riavvia |

Comandi di soccorso (SSH): `vzbot stato`, `vzbot versione`, `vzbot log`, `vzbot riavvia [brain|notifiche|tutto]`,
`vzbot aggiorna [--forza]`, `vzbot notifiche prova`, `vzbot annulla`. `vzbot aiuto` li elenca.

---

## C. L'app Android

L'app VzBot (la finestra sulla dashboard, con le notifiche) si aggiorna **dalla dashboard**, come il resto. Lo fa così: **GitHub costruisce l'app da solo**
(un suo computer la compila e la firma, in 5-10 minuti), il Raspberry la riceve con il solito «Aggiorna VzBot» e il telefono la prende dal
Raspberry con un tasto, **Aggiorna l'app**. Android chiede sempre conferma prima di installare: non si può evitare, e va bene così.

L'app ha un numero di versione suo, scritto nel file `android/VERSION` (parte da **1.0.0**). **Per fare un'app nuova si alza quel numero.**

### C1. Scegli la password della chiave (obbligatorio, una volta)

Android aggiorna un'app solo se è firmata sempre con la **stessa chiave**. La chiave la crea GitHub la prima volta e la chiude con una password
che scegli tu.

1. Pensa una **frase lunga** (almeno 16 caratteri, meglio quattro o cinque parole che ricordi) e **scrivila in un posto sicuro** (un gestore di password,
   un foglio). Chi non la conosce non può firmare app che il tuo telefono accetti.
2. Su GitHub apri il repository → **Settings** (la scheda in alto, con l'ingranaggio) → a sinistra **Secrets and variables** → **Actions**
   → **New repository secret**.
3. In **Name** scrivi esattamente `VZBOT_CHIAVE_PASSWORD`. In **Secret** incolla la tua frase (su **una riga sola**). Clicca **Add secret**.

### C2. Le notifiche (facoltativo)

Se vuoi le notifiche sul telefono serve il file `google-services.json` di Firebase (quello dell'app Android `com.vzbot.dashboard`: nella
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
   VZBOT_CHIAVE_PASSWORD» e non ha fatto niente. È normale: ora che c'è, la costruzione si avvia a mano da qui.)*
2. Aspetta. Il pallino giallo gira per 5-10 minuti (la prima volta anche di più), poi diventa **verde ✓**. Se diventa **rosso ✗** apri il passo con la X: il messaggio
   spiega cosa manca (vedi C8).
3. Cosa ha fatto: ha creato la chiave `android/chiave/vzbot.p12` (cifrata con la tua password), ha compilato e firmato l'app e ha messo nel repository la cartella
   **`apk/`** con `VzBot.apk` e `versione.json`.

### C5. Porta l'app sul Raspberry

Dashboard → **☰** → **Aggiornamenti** → **Controlla se c'è una versione nuova** → **Aggiorna VzBot**. Poi, nello stesso menu, il blocco **App Android** dice
*L'app Android 1.0.0 è pronta*.

### C6. Installa l'app sul telefono (la prima volta)

1. **Se sul telefono c'è già un'app VzBot installata da Android Studio, disinstallala** (Impostazioni → App → VzBot → Disinstalla): Android non permette di mettere
   sopra un'app firmata con un'altra chiave. Non perdi niente: indirizzi, soglie e chiave dell'IA stanno sul Raspberry.
2. Dal telefono (a casa, o con ZeroTier) apri nel browser `http://192.168.1.17:8085` → **☰** → **Aggiornamenti** → blocco **App Android** → **Scarica l'app**.
3. Apri il file scaricato (notifica «Download completato», o app **File** → *Download*). Android chiede di **consentire l'installazione da questa fonte** (il browser):
   concedi, poi **Installa**.
4. Apri VzBot. Da ora in poi l'app si aggiorna da sola (C7).

### C7. Un'app nuova (ogni volta)

1. Carica su GitHub i file nuovi della cartella `android/` (come in B1) **e alza il numero in `android/VERSION`**: su GitHub apri il file `android/VERSION` → icona
   **matita** → cambia `1.0.0` in `1.0.1` → **Commit changes**. (Se non alzi il numero GitHub non costruisce niente e lo scrive nel riepilogo.)
2. GitHub parte da solo: scheda **Actions** → *App Android* → attendi il **✓ verde** (5-10 minuti). Mette l'app nuova in `apk/`.
3. Dashboard → **Aggiornamenti** → **Controlla** → **Aggiorna VzBot** (porta l'app sul Raspberry).
4. **Sul telefono**, nell'app VzBot: **☰** → **Aggiornamenti** → **App Android** → **Aggiorna l'app**. Compare una barra mentre scarica. Android chiede conferma:
   tocca **Aggiorna**. *(La prima volta chiede prima il permesso «Installa app sconosciute» per VzBot: attivalo nella pagina che si apre e torna all'app, l'aggiornamento riparte da solo.)*
5. Quando ha finito, **riapri VzBot dall'icona** (Android chiude l'app durante l'installazione).

### C8. Se qualcosa non va

| Cosa vedi | Cosa fare |
|---|---|
| Actions rosso: *Manca il segreto VZBOT_CHIAVE_PASSWORD* | Rifai C1: il nome del segreto deve essere identico |
| Actions rosso: *password troppo corta* / *ha un «a capo»* | Rifai il segreto con una frase di almeno 16 caratteri su una riga sola |
| Actions rosso: *la password … non apre la chiave* | Hai cambiato la password: rimetti quella di prima. Se l'hai persa: su GitHub cancella il file `android/chiave/vzbot.p12`, poi **Run workflow** spuntando **nuova_chiave**. Le app già installate vanno disinstallate e reinstallate una volta |
| Actions rosso: *firmato con una chiave DIVERSA* | Come sopra: o rimetti la chiave e la password di prima, o accetti il cambio con **nuova_chiave** |
| Actions verde ma «Niente da costruire» | Non hai alzato il numero in `android/VERSION` (C7). Per ricostruire lo stesso numero: **Run workflow** spuntando **forza** |
| Actions rosso al salvataggio (*permission denied*) | Settings → **Actions** → **General** → *Workflow permissions* → **Read and write permissions** → Save, poi rilancia |
| Actions rosso: *android/VERSION deve contenere tre numeri…* | Scrivi la versione come `1.0.1` (tre numeri da 0 a 99 separati da punti) |
| Il blocco dice *non c'è ancora nessuna app* | GitHub non ha ancora costruito l'app (C4) o non hai ancora fatto «Aggiorna VzBot» (C5) |
| Il blocco dice *non è completa* | Un aggiornamento era a metà: aspetta qualche secondo e tocca **Controlla** |
| Android: *App non installata… in conflitto* | C'è ancora l'app vecchia con un'altra firma: disinstallala (C6, punto 1) |
| L'app dice che non può installare | Attiva «Consenti da questa fonte» per VzBot; con l'**Auto Blocker** di Samsung attivo non si può: Impostazioni → Sicurezza e privacy → Auto Blocker → spegni, poi riprova |
| Il tasto «Aggiorna l'app» non compare | Si vede solo dentro l'app VzBot; da un browser c'è «Scarica l'app». Se hai un'app vecchia, installa una volta quella nuova (C6) |

### C9. Cose da sapere

* La chiave sta nel repository (pubblico) ma è **cifrata dalla tua password**: scegli una frase lunga e non scriverla mai nel repository. Anche con la chiave, il tuo telefono installa solo dopo il tuo OK.
* Ogni app nuova aggiunge circa 8 MB al repository (la storia conserva le versioni vecchie): succede solo quando alzi il numero, quindi poche volte.
* Il computer di GitHub è gratuito per i repository pubblici.
* L'APK in `apk/` e la chiave in `android/chiave/` li scrive GitHub: non si modificano a mano.

---

## D. Dove stanno le cose (e perché)

* `~/vzbot` è il **programma**: una copia del repository GitHub. **Non si modifica a mano** (Moonraker rifiuterebbe di aggiornare
  finché ci sono file cambiati: la dashboard allora offre "Ripristina i file del programma").
* `~/printer_data/vzbot` sono **le tue cose**: soglie del monitor (`brain.json`, si cambiano dalla dashboard), chiave dell'IA
  (`ai.json`), notifiche. Gli aggiornamenti non ci mettono mano. Per salvarle basta copiare quella cartella.
* `~/vzbot/android` sono i sorgenti dell'app e `~/vzbot/apk` l'ultimo APK costruito da GitHub: il Raspberry li riceve con l'aggiornamento e li offre al telefono.
* Il repository è **pubblico**: non caricarci mai chiavi o password. (L'unica chiave che c'è, `android/chiave/vzbot.p12`, è cifrata con la password che sta nei segreti di GitHub.)
* Per i nomi dei file e dei servizi vedi la tabella nel [README](../README.md).

## E. Come funziona l'aggiornamento (per chi è curioso)

Moonraker ha un componente, l'*update manager*, che sa tenere aggiornata una cartella git. `install.sh` gli aggiunge
questa voce in `moonraker.conf`:

```
[update_manager vzbot]
type: git_repo
path: ~/vzbot
origin: https://github.com/TUONOME/vzbot.git
primary_branch: main
channel: dev
managed_services: vzbot
```

Quando premi **Aggiorna**, Moonraker confronta `~/vzbot` con GitHub, scarica le differenze e **riavvia il servizio `vzbot`**
(per questo il servizio si deve chiamare così e deve stare in `moonraker.asvc`). Il Brain, appena riparte, serve la dashboard nuova.
Moonraker controlla GitHub da solo ogni tanto; il tasto *Controlla* lo fa subito.

**L'app** segue la stessa strada con un passo in più: la modifica di `android/VERSION` fa partire il workflow `.github/workflows/app.yml`, che costruisce l'APK
e lo salva in `apk/` (con un file `versione.json` che ne dice versione, grandezza e impronta). L'aggiornamento di Moonraker porta `apk/` sul Raspberry; il Brain lo offre
su `/app/VzBot.apk` solo se grandezza e impronta del file coincidono con `versione.json`. La dashboard dentro l'app confronta la versione installata con quella offerta e,
al tocco di **Aggiorna l'app**, chiede all'app di scaricare il file (controllando di nuovo l'impronta) e di aprire l'installazione di Android.
