# Guida di VzBot — passo per passo

Due parti: **A.** la preparazione (si fa **una volta sola**) e **B.** gli aggiornamenti (si fanno **ogni volta** che c'è una
release nuova, e non servono più né SSH né il terminale).

---

## A. Preparazione (una volta sola)

### A1. Crea il "contenitore" su GitHub

1. Vai su <https://github.com> e crea un account gratuito (se non ce l'hai).
2. In alto a destra clicca **+** → **New repository**.
3. **Repository name**: scrivi `vzbot`. Scegli **Public** (pubblico: serve perché il Raspberry lo scarichi senza password).
   Spunta **Add a README file** e clicca **Create repository**.

### A2. Carica i file della release

1. Sul PC, estrai il file `VzBot-repo-1.0.0.zip`: ottieni le cartelle `brain`, `dashboard`, `notifier`, `scripts`, `systemd`, `docs`
   e i file `VERSION`, `README.md`, `CHANGELOG.md` (e `.gitignore`, che se non lo vedi non è un problema).
2. Nella pagina del repository clicca **Add file** → **Upload files**.
3. **Trascina dentro la pagina le cartelle e i file** (tutto insieme). GitHub mantiene le cartelle.
4. In basso, in **Commit changes**, scrivi `Release 1.0.0` e clicca il bottone verde **Commit changes**.

Controlla che nella pagina principale del repository ci siano le cartelle `brain`, `dashboard`, `notifier`, `scripts`,
`systemd`, `docs` e il file `VERSION`.

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

## C. Dove stanno le cose (e perché)

* `~/vzbot` è il **programma**: una copia del repository GitHub. **Non si modifica a mano** (Moonraker rifiuterebbe di aggiornare
  finché ci sono file cambiati: la dashboard allora offre "Ripristina i file del programma").
* `~/printer_data/vzbot` sono **le tue cose**: soglie del monitor (`brain.json`, si cambiano dalla dashboard), chiave dell'IA
  (`ai.json`), notifiche. Gli aggiornamenti non ci mettono mano. Per salvarle basta copiare quella cartella.
* Il repository è **pubblico**: non caricarci mai chiavi o password.
* Per i nomi dei file e dei servizi vedi la tabella nel [README](../README.md).

## D. Come funziona l'aggiornamento (per chi è curioso)

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
