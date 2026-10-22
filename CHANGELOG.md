# Cosa cambia in ogni release

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
