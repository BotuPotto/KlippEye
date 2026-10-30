# KlippEye — app Android

L'app è una finestra a tutto schermo (WebView) sulla dashboard che gira sul Raspberry, con icona e splash KlippEye, notifiche
push, download dei file e **aggiornamento da sola**. Versione attuale: il numero scritto in [`VERSION`](VERSION).

```
android/
  VERSION                 il numero di versione: l'UNICO posto dove si cambia
  build.gradle, settings.gradle, gradle.properties, gradlew, gradle/   progetto Gradle (gradlew = sempre lo stesso Gradle, 8.5)
  app/build.gradle        ricava versionName e versionCode da VERSION; firma se trova la chiave (vedi "Firma")
  app/src/main/java/com/klippeye/app/
      MainActivity.kt     la finestra, il ponte con la dashboard (KlippEyeApp), download, aggiornamento
      Aggiornamento.kt    controlli, scaricamento e verifica dell'APK (solo Java: si prova da sola)
      AggiornamentoAndroid.kt   versione installata, permesso "Installa app sconosciute", installazione
      Indirizzi.kt        gli indirizzi del Raspberry (rete di casa, ZeroTier)
      Notifiche.kt, KlippEyeMessagingService.kt   notifiche push (Firebase)
  app/src/main/res/       icone, splash, colori, temi, file_paths.xml (cartella condivisa con l'installazione)
  chiave/klippeye.p12        la chiave di firma, CIFRATA (la crea GitHub la prima volta; vedi "Firma")
  tools/                  prove (AggiornamentoTest.kt, IndirizziTest.kt) e script per le icone
```

## Nome dell'app

Il nome interno è `com.klippeye.app` e il ponte con la dashboard si chiama `KlippEyeApp` (`KlippEyeApp/5` nell'user agent).
Dalla 1.3.0 l'app non contiene più nessun argomento delle notifiche (vedi «Notifiche push»).

## Versione

`VERSION` contiene tre numeri da 0 a 99 (`1.0.0`, `1.0.1`, `1.2.0`...). Da lì Gradle ricava:

* `versionName` = il testo (`1.0.0`);
* `versionCode` = `maggiore × 10000 + minore × 100 + correzione` (`1.0.0` → 10000, `1.2.3` → 10203): cresce a ogni versione, ed è quello
  che Android confronta per sapere se un APK è più nuovo.

Per fare una versione nuova **basta alzare il numero in `VERSION`**. Con un numero più basso di quello già pubblicato il workflow si ferma e lo dice
(Android non installa mai una versione più vecchia sopra una più nuova). Un formato sbagliato ferma la costruzione con un messaggio.

## Come nasce l'APK

**Da GitHub (il modo normale).** Quando in `android/` cambia qualcosa *e* il numero in `VERSION` è nuovo, il workflow
`.github/workflows/app.yml` compila l'APK sul computer di GitHub, lo firma e lo mette in `apk/KlippEye.apk` con `apk/version.json`
(versione, grandezza, impronta SHA-256, firma). Il Raspberry lo riceve con il normale «Aggiorna KlippEye», il backend lo offre al telefono
(`/api/app/version`, `/app/KlippEye.apk`) e la dashboard dell'app mostra «Aggiorna l'app». Passo per passo: [`docs/GUIDA.md`](../docs/GUIDA.md), parte C.

**Da Android Studio (come prima, per provare).** *File → Open* e scegli questa cartella (`android`); *Build → Build APK(s)*. Senza chiave
l'APK è quello di prova (debug), firmato con la chiave di Android Studio: **non** si può sovrapporre a quello costruito da GitHub (firme diverse):
va disinstallata l'altra app. `app/google-services.json` (da scaricare dalla console Firebase) serve solo per le notifiche; senza, l'app funziona ma all'avvio dice
«Notifiche non attive». Non va caricato su GitHub (è nel `.gitignore`): per l'APK di GitHub si usa il segreto `GOOGLE_SERVICES_JSON`.

## Firma

Android installa un aggiornamento solo se è firmato con la **stessa chiave** dell'app che sostituisce. La chiave dell'app di GitHub è
`chiave/klippeye.p12` (formato PKCS12, alias `klippeye`, RSA 4096, valida 100 anni): la crea il workflow la prima volta e **la cifra con la password** che
sta nel segreto `KLIPPEYE_CHIAVE_PASSWORD` (almeno 16 caratteri). Il file sta nel repository (pubblico) perché serve a ogni costruzione: la
protezione è la password, quindi dev'essere una frase lunga e non va scritta da nessuna parte nel repository.

* Il workflow rifiuta di pubblicare un APK firmato con una chiave **diversa** da quella dell'app già pubblicata (i telefoni non potrebbero
  aggiornarsi): per cambiare chiave davvero si cancella `chiave/klippeye.p12` e si rilancia a mano con «nuova_chiave». Poi le app già
  installate vanno disinstallate e reinstallate una volta.
* Per usare una chiave propria basta mettere il suo `.p12` (alias `klippeye`, stessa password per archivio e chiave) in `chiave/klippeye.p12`.
* `app/build.gradle` firma la versione release solo se trova le variabili `KLIPPEYE_KEYSTORE` (percorso del file) e `KLIPPEYE_KEYSTORE_PASSWORD`.

## L'app si aggiorna da sola

La dashboard dentro l'app (Impostazioni → Aggiornamenti → *App Android*) confronta la versione installata con quella che il backend offre.
Il ponte che l'app mette a disposizione della pagina (`window.KlippEyeApp`, user agent **`KlippEyeApp/5`**):

| Chiamata | Cosa fa |
|---|---|
| `appInfo()` | restituisce `{"version":"1.0.0","code":10000,"canInstall":true}` (`canInstall`: Android ha già dato il permesso «Installa app sconosciute») |
| `updateApp(path, version, sha256, size)` | scarica `/app/KlippEye.apk` dal backend e apre l'installazione di Android. Tutti i valori sono quelli annunciati dal backend, in testo |
| `window.klippeyeAppUpdate({stato, ...})` | la risposta, chiamata dall'app: `scarico` (`fatto`, `totale` in byte), `permesso`, `installazione`, `errore` (`messaggio`) |

Cosa controlla l'app **prima** di installare (`Aggiornamento.kt`, provato da `tools/AggiornamentoTest.kt`):

1. l'indirizzo è quello del backend a cui è collegata (stesso protocollo, indirizzo e porta) e il percorso è esattamente `/app/KlippEye.apk`;
2. la versione è più nuova di quella installata;
3. il file scaricato ha la grandezza e l'impronta SHA-256 annunciate; un file diverso, troncato o più grande del previsto si butta (niente file a metà);
4. un file già scaricato e identico (per esempio mentre si concede il permesso) si riusa.

E poi decide Android: chiede **sempre** conferma, e installa solo se la firma è quella dell'app attuale. Il permesso «Installa app sconosciute»
(`REQUEST_INSTALL_PACKAGES`) si concede una volta: l'app apre la pagina giusta di Android e, tornando, riparte da sola. Con l'Auto Blocker di Samsung attivo il
permesso non si può dare (va spento prima). L'APK scaricato sta in `cache/aggiornamenti/` (la sola cartella condivisa con l'installazione, `res/xml/file_paths.xml`)
e si cancella all'apertura successiva. Dopo l'installazione Android chiude l'app: si riapre dall'icona.

Una dashboard aperta in un'app più vecchia (`KlippEyeApp/3` o `/4`) non ha `updateApp`: il blocco «App Android» offre il download dell'APK nella cartella Download,
da installare a mano, una volta sola.

## Indirizzi del Raspberry

L'app prova in ordine: IP locale, IP esterno (ZeroTier), poi quelli di fabbrica (`192.168.1.17`, `172.25.170.177`); il primo che risponde (1,2 s a testa) vince. Gli indirizzi si
scelgono dal menu Impostazioni → *Indirizzi* della dashboard (che li comunica all'app con `setAddresses`), o dalla finestra «Indirizzi» che l'app mostra quando non riesce
a connettersi. `setAddresses` accetta solo reti private (10.x, 172.16-31.x, 192.168.x, 100.64-127.x, nomi `.local`/`.lan`...): una pagina qualsiasi in un riquadro della dashboard
(la camera «Pagina web») non deve poter dirottare l'app su un sito esterno. La porta è sempre 8085.

## Scelta e salvataggio dei file

* **Carica file**: il selettore di file di Android (`onShowFileChooser`, nessun permesso in più).
* **Download**: `window.KlippEyeApp.saveUrl(indirizzo, nome)` scarica dal Raspberry a cui l'app è collegata (niente altri siti, `blob:` o `data:`) e salva in **Download** (Android 10+ con MediaStore,
  senza permessi; un nome già presente diventa `nome (1).ext`). Prima di Android 10 va in `Android/data/com.klippeye.app/files/Download`.

## Notifiche push

Dalla 1.3.0 l'app non ha **nessun argomento scritto dentro**: chiede al Raspberry a cui è collegata come riceverle
(`GET /api/notifications/app`, dalla dashboard, ponte `KlippEyeApp.notifySetup`) e la persona lo sceglie con la procedura guidata
della dashboard (Impostazioni → Notifiche → Questo telefono). Tutto in `Ascolto.kt`:

* **ntfy** (tutti): `AscoltoNtfy` è un servizio in primo piano (`specialUse`, notifica fissa «KlippEye in ascolto» sul canale
  `ascolto`, il meno visibile) che legge `<server>/<argomento>/json` riga per riga, si ricollega da solo (5 s → 60 s) e recupera i
  messaggi persi con `since=<ultimo id>`. Riparte all'accensione del telefono e dopo un aggiornamento (`RiavvioAscolto`). Il canale
  Android viene dalla priorità ntfy (5 allarmi, 4 avvisi, 3 stampa: la stessa tabella di `KIND_NTFY` nel notifier).
* **Firebase** (solo l'installazione di chi mantiene il progetto): il Raspberry dà l'argomento Firebase **solo se ha la chiave**
  (`service-account.json`); l'app vi si iscrive (anche prima della procedura, come con la 1.2.0) e se ne cancella quando non c'è più.
  L'argomento scritto nelle app fino alla 1.2.0 era pubblico: l'app se ne cancella sempre e il Raspberry lo sostituisce con uno
  segreto (`klippeye-fb-…`) la prima volta che una app 1.3.0 lo chiede.
  Per chi mantiene il progetto: `google-services.json` del progetto Firebase (app Android `com.klippeye.app`) nel segreto
  `GOOGLE_SERVICES_JSON`; la chiave del service account dello stesso progetto è `~/printer_data/klippeye/service-account.json` sul
  proprio Raspberry, con `"topic"` in `notifier.json`. Senza Firebase l'app si costruisce lo stesso e usa ntfy.
* Ponte (app 6): `notifySetup(json)`, `notifyState()`, `askNotificationPermission()`, `askBatteryExemption()`,
  `openNotificationSettings()`; l'app avvisa la pagina con `window.klippeyeNotifyState(stato)`.
* Canali (Impostazioni → App → KlippEye → Notifiche): `allarmi`, `avvisi`, `stampa`, `ascolto`. Con l'app aperta le notifiche
  Firebase le mostra `KlippEyeMessagingService`.

## Icona e splash

Stile One UI 9 con i colori del logo KlippEye: accento viola chiaro `#b79cff`, fondo `#040507` con il viola scuro `#7a5cff` che sfuma verso il nero (come la dashboard), «pillola» di vetro per lo stato.
L'icona adattiva ha per fondo il riquadro viola scuro del logo e, sopra, il logo su un livello separato (anche la versione tematica di Android 13+, a un solo colore); la splash e la notifica usano il logo senza riquadro.
Le immagini si rigenerano con `python3 tools/genera_icone.py` e `python3 tools/genera_icona_notifica.py` (Pillow e numpy; il logo è in `tools/assets/`: `klippeye_g4.svg` è il sorgente, `logo_klippeye.png` a colori e `logo_klippeye_mono.png` a un colore).
Colori in `res/values/colors.xml`, temi in `res/values/` e `res/values-v31/`.

## Prove

Senza telefono né Gradle, da questa cartella (servono `kotlinc` e `android.jar` dell'SDK):

```
kotlinc app/src/main/java/com/klippeye/app/Aggiornamento.kt tools/AggiornamentoTest.kt -d prova
java -cp prova:kotlin-stdlib.jar com.klippeye.app.AggiornamentoTestKt

kotlinc -cp android.jar app/src/main/java/com/klippeye/app/Indirizzi.kt tools/IndirizziTest.kt -d prova2
java -cp prova2:kotlin-stdlib.jar:android.jar com.klippeye.app.IndirizziTestKt
```

`AggiornamentoTest.kt` avvia un piccolo server che fa da backend (anche quando sbaglia: file rovinato, troncato, più grande, 404, 500) e prova controlli e scaricamento.
Il resto del codice (finestra, ponte, installazione) è stato compilato con Kotlin 1.9.10 contro `android.jar` (API 34), ma **non provato su un telefono** e la costruzione con Gradle non
è stata eseguita nell'ambiente di sviluppo: al primo giro conviene guardare il workflow su GitHub e provare l'aggiornamento una volta con il Raspberry acceso.
