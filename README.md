# KlippEye

Dashboard, backend (il programma che la serve e controlla la stampa con la camera), notifiche e app Android per una stampante 3D con
Klipper + Moonraker + Raspberry Pi. Questo repository è il **contenitore**: quello che c'è qui è quello che gira sul Raspberry.

> Fino alla 1.0.x il progetto si chiamava **VzBot**. Chi ha già VzBot passa a KlippEye con un tasto della dashboard
> (*Impostazioni → Aggiornamenti → Passa a KlippEye*): guida nella parte **P** di [docs/GUIDA.md](docs/GUIDA.md).

**Come si usa, passo per passo: [docs/GUIDA.md](docs/GUIDA.md).**

## Come funziona l'aggiornamento

```
  tuo PC                      GitHub (questo repository)              Raspberry
  ──────                      ──────────────────────────              ─────────
  carichi i file nuovi  ───►  nuova release (VERSION 1.1.0)  ◄───┐
                                                                 │ Moonraker (update manager) lo controlla
  dashboard ► Impostazioni ► Aggiornamenti ► "Aggiorna KlippEye" ──┘  e scarica solo le differenze in ~/klippeye,
                                                                    poi riavvia il servizio "klippeye".
                                                                    La pagina si ricarica da sola.
```

* Il programma sta in **una cartella sola** (`~/klippeye`), le **tue cose** (soglie del monitor, chiave dell'IA, notifiche) in un'altra
  (`~/printer_data/klippeye`): un aggiornamento tocca solo la prima.
* Dopo un **blackout** i file rovinati si rimettono a posto da soli a ogni avvio ([guida, parte G](docs/GUIDA.md)).
* Se qualcosa va storto: **"Torna alla versione precedente"** nella stessa pagina (o Rollback in Mainsail/Fluidd).
* L'update manager è quello di Moonraker, quindi l'aggiornamento si vede e si lancia anche da Mainsail e Fluidd.

## L'app Android

```
  tuo PC / GitHub                                   Raspberry                           Telefono
  ───────────────                                   ─────────                           ────────
  alzi il numero in android/VERSION
  GitHub compila e firma l'APK (workflow)  ───►  "Aggiorna KlippEye" porta apk/ qui  ───►  dashboard dell'app ► Aggiornamenti
  e lo salva in apk/ (+ versione.json)             il backend lo offre (/app/KlippEye.apk)    ► "Aggiorna l'app" ► conferma di Android
```

L'app ha un numero suo (`android/VERSION`). Il backend offre l'APK solo se grandezza e impronta SHA-256 coincidono con `apk/versione.json`;
l'app le ricontrolla dopo il download, e Android installa solo un APK con la stessa firma e solo dopo la conferma dell'utente.
Preparazione (una volta) e passaggi: [docs/GUIDA.md](docs/GUIDA.md), parte C. Dettagli tecnici: [android/README.md](android/README.md).

## Disposizione dei file

| Dove | Cosa | Chi lo cambia |
|---|---|---|
| `~/klippeye/VERSION` | la release (un numero solo per tutto: `1.1.0`) | tu, a ogni release |
| `~/klippeye/backend/klippeye_backend.py` | il backend: serve la dashboard, ponte verso Moonraker, monitor IA, soglie | l'aggiornamento |
| `~/klippeye/frontend/klippeye_frontend.html` | la dashboard (un file solo) | l'aggiornamento |
| `~/klippeye/logos/` | i loghi ufficiali di Voron, RatRig (e VzBot) per la scelta della stampante ([logos/README.md](logos/README.md)) | tu, una volta |
| `~/klippeye/notifier/klippeye_notifier.py` | il servizio delle notifiche al telefono | l'aggiornamento |
| `~/klippeye/scripts/` | `install.sh` (si lancia una volta), `passa-a-klippeye.sh` (il passaggio da VzBot), `ripara.sh` (la riparazione dopo un blackout, parte da sola), `klippeye` e `klippeye-notifiche` (comandi di soccorso) | l'aggiornamento |
| `~/klippeye/systemd/` | i modelli dei servizi `klippeye` e `klippeye-notifier` | l'aggiornamento |
| `~/klippeye/android/` | i sorgenti dell'app Android (`android/VERSION` = la versione dell'app) | tu, quando fai un'app nuova |
| `~/klippeye/apk/` | `KlippEye.apk` e `versione.json`: l'ultima app costruita da GitHub | GitHub (workflow `.github/workflows/app.yml`) |
| `~/klippeye/ci/app_ci.py` | i passi del workflow che costruisce l'app (provati a parte) | l'aggiornamento |
| `~/klippeye/docs/`, `README.md`, `CHANGELOG.md` | questa documentazione | l'aggiornamento |
| `~/printer_data/klippeye/brain.json` | le soglie del monitor IA (si cambiano dalla dashboard) | la dashboard |
| `~/printer_data/klippeye/ai.json` | la chiave del servizio IA (visibile solo al tuo utente) | la dashboard |
| `~/printer_data/klippeye/notifier.json`, `service-account.json` | impostazioni e chiave delle notifiche | tu, una volta |
| `~/printer_data/klippeye/riparazioni.log`, `ripristino.json` | cosa ha rimesso a posto la riparazione automatica | `ripara.sh` |
| `~/printer_data/klippeye/backup/` | copie di sicurezza fatte dall'installer | l'installer |

I servizi si chiamano **`klippeye`** (backend + dashboard, porta 8085) e **`klippeye-notifier`** (notifiche). Il nome `klippeye` non va cambiato:
è quello che Moonraker riavvia dopo un aggiornamento.

## Numerazione

`MAGGIORE.MINORE.CORREZIONE`, una release sola per backend, dashboard e notifiche (`1.0.0`, `1.0.1`, `1.1.0`...).
Cambia il file `VERSION` a ogni caricamento di file nuovi: è il numero che la dashboard mostra ("Disponibile la release 1.1.0").
Le modifiche di ogni release sono elencate in [CHANGELOG.md](CHANGELOG.md).

L'**app Android** ha una numerazione sua, con lo stesso formato, nel file `android/VERSION`: si alza solo quando si fa un'app nuova.

## Non metterci mai segreti

Il repository è pubblico (Moonraker lo scarica senza password). Chiavi, password e `service-account.json` stanno
**solo** in `~/printer_data/klippeye`, fuori dal repository, e non vanno caricati qui. Fanno eccezione la chiave di firma dell'app,
`android/chiave/klippeye.p12`, che sta qui **cifrata** (la password è un segreto di GitHub), e il file di Firebase per le notifiche dell'app, che sta nei segreti di GitHub.
