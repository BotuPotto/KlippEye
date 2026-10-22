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

## Disposizione dei file

| Dove | Cosa | Chi lo cambia |
|---|---|---|
| `~/vzbot/VERSION` | la release (un numero solo per tutto: `1.0.0`) | tu, a ogni release |
| `~/vzbot/brain/vzbot_brain.py` | il Brain: dashboard, ponte verso Moonraker, monitor IA, soglie | l'aggiornamento |
| `~/vzbot/dashboard/vzbot_dashboard.html` | la dashboard (un file solo) | l'aggiornamento |
| `~/vzbot/notifier/vzbot_notifier.py` | il servizio delle notifiche al telefono | l'aggiornamento |
| `~/vzbot/scripts/` | `install.sh` (si lancia una volta), `vzbot` e `vzbot-notifiche` (comandi di soccorso) | l'aggiornamento |
| `~/vzbot/systemd/` | i modelli dei servizi `vzbot` e `vzbot-notifier` | l'aggiornamento |
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

## Non metterci mai segreti

Il repository è pubblico (Moonraker lo scarica senza password). Chiavi, password e `service-account.json` stanno
**solo** in `~/printer_data/vzbot`, fuori dal repository, e non vanno caricati qui.
