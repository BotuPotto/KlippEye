# VzBot

Dashboard, "Brain" (il programma che la serve e controlla la stampa con la camera) e notifiche per la stampante VzBot
(Klipper + Moonraker + Raspberry Pi). Questo repository è il **contenitore**: quello che c'è qui è quello che gira sul Raspberry.

**Come si usa, passo per passo: [docs/GUIDA.md](docs/GUIDA.md).**

## Come funziona l'aggiornamento

```
  tuo PC                      GitHub (questo repository)              Raspberry
  ──────                      ──────────────────────────              ─────────
  carichi i file nuovi  ───►  nuova release (VERSION 1.0.1)  ◄───┐
                                                                 │ Moonraker (update manager) lo controlla
  dashboard ► Impostazioni ► Aggiornamenti ► "Aggiorna VzBot" ───┘  e scarica solo le differenze in ~/vzbot,
                                                                    poi riavvia il servizio "vzbot".
                                                                    La pagina si ricarica da sola.
```

* Il programma sta in **una cartella sola** (`~/vzbot`), le **tue cose** (soglie del monitor, chiave dell'IA, notifiche) in un'altra
  (`~/printer_data/vzbot`): un aggiornamento tocca solo la prima.
* Se qualcosa va storto: **"Torna alla versione precedente"** nella stessa pagina (o Rollback in Mainsail/Fluidd).
* L'update manager è quello di Moonraker, quindi l'aggiornamento si vede e si lancia anche da Mainsail e Fluidd.

## L'app Android

```
  tuo PC / GitHub                                   Raspberry                           Telefono
  ───────────────                                   ─────────                           ────────
  alzi il numero in android/VERSION
  GitHub compila e firma l'APK (workflow)  ───►  "Aggiorna VzBot" porta apk/ qui  ───►  dashboard dell'app ► Aggiornamenti
  e lo salva in apk/ (+ versione.json)             il Brain lo offre (/app/VzBot.apk)    ► "Aggiorna l'app" ► conferma di Android
```

L'app ha un numero suo (`android/VERSION`, parte da 1.0.0). Il Brain offre l'APK solo se grandezza e impronta SHA-256 coincidono con `apk/versione.json`;
l'app le ricontrolla dopo il download, e Android installa solo un APK con la stessa firma e solo dopo la conferma dell'utente.
Preparazione (una volta) e passaggi: [docs/GUIDA.md](docs/GUIDA.md), parte C. Dettagli tecnici: [android/README.md](android/README.md).

## Disposizione dei file

| Dove | Cosa | Chi lo cambia |
|---|---|---|
| `~/vzbot/VERSION` | la release (un numero solo per tutto: `1.0.0`) | tu, a ogni release |
| `~/vzbot/brain/vzbot_brain.py` | il Brain: dashboard, ponte verso Moonraker, monitor IA, soglie | l'aggiornamento |
| `~/vzbot/dashboard/vzbot_dashboard.html` | la dashboard (un file solo) | l'aggiornamento |
| `~/vzbot/notifier/vzbot_notifier.py` | il servizio delle notifiche al telefono | l'aggiornamento |
| `~/vzbot/scripts/` | `install.sh` (si lancia una volta), `vzbot` e `vzbot-notifiche` (comandi di soccorso) | l'aggiornamento |
| `~/vzbot/systemd/` | i modelli dei servizi `vzbot` e `vzbot-notifier` | l'aggiornamento |
| `~/vzbot/android/` | i sorgenti dell'app Android (`android/VERSION` = la versione dell'app) | tu, quando fai un'app nuova |
| `~/vzbot/apk/` | `VzBot.apk` e `versione.json`: l'ultima app costruita da GitHub | GitHub (workflow `.github/workflows/app.yml`) |
| `~/vzbot/ci/app_ci.py` | i passi del workflow che costruisce l'app (provati a parte) | l'aggiornamento |
| `~/vzbot/docs/`, `README.md`, `CHANGELOG.md` | questa documentazione | l'aggiornamento |
| `~/printer_data/vzbot/brain.json` | le soglie del monitor IA (si cambiano dalla dashboard) | la dashboard |
| `~/printer_data/vzbot/ai.json` | la chiave del servizio IA (visibile solo al tuo utente) | la dashboard |
| `~/printer_data/vzbot/notifier.json`, `service-account.json` | impostazioni e chiave delle notifiche | tu, una volta |
| `~/printer_data/vzbot/backup/` | copie di sicurezza fatte dall'installer | l'installer |

I servizi si chiamano **`vzbot`** (Brain + dashboard, porta 8085) e **`vzbot-notifier`** (notifiche). Il nome `vzbot` non va cambiato:
è quello che Moonraker riavvia dopo un aggiornamento.

## Numerazione

`MAGGIORE.MINORE.CORREZIONE`, una release sola per Brain, dashboard e notifiche (`1.0.0`, `1.0.1`, `1.1.0`...).
Cambia il file `VERSION` a ogni caricamento di file nuovi: è il numero che la dashboard mostra ("Disponibile la release 1.0.1").
Le modifiche di ogni release sono elencate in [CHANGELOG.md](CHANGELOG.md).

L'**app Android** ha una numerazione sua, con lo stesso formato, nel file `android/VERSION` (parte da `1.0.0`): si alza solo quando si fa un'app nuova.

## Non metterci mai segreti

Il repository è pubblico (Moonraker lo scarica senza password). Chiavi, password e `service-account.json` stanno
**solo** in `~/printer_data/vzbot`, fuori dal repository, e non vanno caricati qui. Fanno eccezione la chiave di firma dell'app,
`android/chiave/vzbot.p12`, che sta qui **cifrata** (la password è un segreto di GitHub), e il file di Firebase per le notifiche dell'app, che sta nei segreti di GitHub.
