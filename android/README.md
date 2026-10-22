# VzBot — app Android

L'app è una finestra a tutto schermo (WebView) sulla dashboard che gira sul Raspberry, con icona e splash VzBot, notifiche
push, download dei file e **aggiornamento da sola**. Versione attuale: il numero scritto in [`VERSION`](VERSION).

```
android/
  VERSION                 il numero di versione (1.0.0): l'UNICO posto dove si cambia
  build.gradle, settings.gradle, gradle.properties, gradlew, gradle/   progetto Gradle (gradlew = sempre lo stesso Gradle, 8.5)
  app/build.gradle        ricava versionName e versionCode da VERSION; firma se trova la chiave (vedi "Firma")
  app/src/main/java/com/vzbot/dashboard/
      MainActivity.kt     la finestra, il ponte con la dashboard (VzBotApp), download, aggiornamento
      Aggiornamento.kt    controlli, scaricamento e verifica dell'APK (solo Java: si prova da sola)
      AggiornamentoAndroid.kt   versione installata, permesso "Installa app sconosciute", installazione
      Indirizzi.kt        gli indirizzi del Raspberry (rete di casa, ZeroTier)
      Notifiche.kt, VzBotMessagingService.kt   notifiche push (Firebase)
  app/src/main/res/       icone, splash, colori, temi, file_paths.xml (cartella condivisa con l'installazione)
  chiave/vzbot.p12        la chiave di firma, CIFRATA (la crea GitHub la prima volta; vedi "Firma")
  tools/                  prove (AggiornamentoTest.kt, IndirizziTest.kt) e script per le icone
```

## Versione

`VERSION` contiene tre numeri da 0 a 99 (`1.0.0`, `1.0.1`, `1.2.0`...). Da lì Gradle ricava:

* `versionName` = il testo (`1.0.0`);
* `versionCode` = `maggiore × 10000 + minore × 100 + correzione` (`1.0.0` → 10000, `1.2.3` → 10203): cresce a ogni versione, ed è quello
  che Android confronta per sapere se un APK è più nuovo.

Per fare una versione nuova **basta alzare il numero in `VERSION`**. Con un numero più basso di quello già pubblicato il workflow si ferma e lo dice
(Android non installa mai una versione più vecchia sopra una più nuova). Un formato sbagliato ferma la costruzione con un messaggio.

## Come nasce l'APK

**Da GitHub (il modo normale).** Quando in `android/` cambia qualcosa *e* il numero in `VERSION` è nuovo, il workflow
`.github/workflows/app.yml` compila l'APK sul computer di GitHub, lo firma e lo mette in `apk/VzBot.apk` con `apk/versione.json`
(versione, grandezza, impronta SHA-256, firma). Il Raspberry lo riceve con il normale «Aggiorna VzBot», il Brain lo offre al telefono
(`/api/app/version`, `/app/VzBot.apk`) e la dashboard dell'app mostra «Aggiorna l'app». Passo per passo: [`docs/GUIDA.md`](../docs/GUIDA.md), parte E.

**Da Android Studio (come prima, per provare).** *File → Open* e scegli questa cartella (`android`); *Build → Build APK(s)*. Senza chiave
l'APK è quello di prova (debug), firmato con la chiave di Android Studio: **non** si può sovrapporre a quello costruito da GitHub (firme diverse):
va disinstallata l'altra app. `app/google-services.json` (da scaricare dalla console Firebase) serve solo per le notifiche; senza, l'app funziona ma all'avvio dice
«Notifiche non attive». Non va caricato su GitHub (è nel `.gitignore`): per l'APK di GitHub si usa il segreto `GOOGLE_SERVICES_JSON`.

## Firma

Android installa un aggiornamento solo se è firmato con la **stessa chiave** dell'app che sostituisce. La chiave dell'app di GitHub è
`chiave/vzbot.p12` (formato PKCS12, alias `vzbot`, RSA 4096, valida 100 anni): la crea il workflow la prima volta e **la cifra con la password** che
sta nel segreto `VZBOT_CHIAVE_PASSWORD` (almeno 16 caratteri). Il file sta nel repository (pubblico) perché serve a ogni costruzione: la
protezione è la password, quindi dev'essere una frase lunga e non va scritta da nessuna parte nel repository.

* Il workflow rifiuta di pubblicare un APK firmato con una chiave **diversa** da quella dell'app già pubblicata (i telefoni non potrebbero
  aggiornarsi): per cambiare chiave davvero si cancella `chiave/vzbot.p12` e si rilancia a mano con «nuova_chiave». Poi le app già
  installate vanno disinstallate e reinstallate una volta.
* Per usare una chiave propria basta mettere il suo `.p12` (alias `vzbot`, stessa password per archivio e chiave) in `chiave/vzbot.p12`.
* `app/build.gradle` firma la versione release solo se trova le variabili `VZBOT_KEYSTORE` (percorso del file) e `VZBOT_KEYSTORE_PASSWORD`.

## L'app si aggiorna da sola

La dashboard dentro l'app (Impostazioni → Aggiornamenti → *App Android*) confronta la versione installata con quella che il Brain offre.
Il ponte che l'app mette a disposizione della pagina (`window.VzBotApp`, user agent **`VzBotApp/5`**):

| Chiamata | Cosa fa |
|---|---|
| `appInfo()` | restituisce `{"version":"1.0.0","code":10000,"canInstall":true}` (`canInstall`: Android ha già dato il permesso «Installa app sconosciute») |
| `updateApp(path, version, sha256, size)` | scarica `/app/VzBot.apk` dal Brain e apre l'installazione di Android. Tutti i valori sono quelli annunciati dal Brain, in testo |
| `window.vzAppUpdate({stato, ...})` | la risposta, chiamata dall'app: `scarico` (`fatto`, `totale` in byte), `permesso`, `installazione`, `errore` (`messaggio`) |

Cosa controlla l'app **prima** di installare (`Aggiornamento.kt`, provato da `tools/AggiornamentoTest.kt`):

1. l'indirizzo è quello del Brain a cui è collegata (stesso protocollo, indirizzo e porta) e il percorso è esattamente `/app/VzBot.apk`;
2. la versione è più nuova di quella installata;
3. il file scaricato ha la grandezza e l'impronta SHA-256 annunciate; un file diverso, troncato o più grande del previsto si butta (niente file a metà);
4. un file già scaricato e identico (per esempio mentre si concede il permesso) si riusa.

E poi decide Android: chiede **sempre** conferma, e installa solo se la firma è quella dell'app attuale. Il permesso «Installa app sconosciute»
(`REQUEST_INSTALL_PACKAGES`) si concede una volta: l'app apre la pagina giusta di Android e, tornando, riparte da sola. Con l'Auto Blocker di Samsung attivo il
permesso non si può dare (va spento prima). L'APK scaricato sta in `cache/aggiornamenti/` (la sola cartella condivisa con l'installazione, `res/xml/file_paths.xml`)
e si cancella all'apertura successiva. Dopo l'installazione Android chiude l'app: si riapre dall'icona.

Una dashboard aperta in un'app più vecchia (`VzBotApp/3` o `/4`) non ha `updateApp`: il blocco «App Android» offre il download dell'APK nella cartella Download,
da installare a mano, una volta sola.

## Indirizzi del Raspberry

L'app prova in ordine: IP locale, IP esterno (ZeroTier), poi quelli di fabbrica (`192.168.1.17`, `172.25.170.177`); il primo che risponde (1,2 s a testa) vince. Gli indirizzi si
scelgono dal menu Impostazioni → *Indirizzi* della dashboard (che li comunica all'app con `setAddresses`), o dalla finestra «Indirizzi» che l'app mostra quando non riesce
a connettersi. `setAddresses` accetta solo reti private (10.x, 172.16-31.x, 192.168.x, 100.64-127.x, nomi `.local`/`.lan`...): una pagina qualsiasi in un riquadro della dashboard
(la camera «Pagina web») non deve poter dirottare l'app su un sito esterno. La porta è sempre 8085.

## Scelta e salvataggio dei file

* **Carica file**: il selettore di file di Android (`onShowFileChooser`, nessun permesso in più).
* **Download**: `window.VzBotApp.saveUrl(indirizzo, nome)` scarica dal Raspberry a cui l'app è collegata (niente altri siti, `blob:` o `data:`) e salva in **Download** (Android 10+ con MediaStore,
  senza permessi; un nome già presente diventa `nome (1).ext`). Prima di Android 10 va in `Android/data/com.vzbot.dashboard/files/Download`.

## Notifiche push

Arrivano da Firebase Cloud Messaging anche con app chiusa e schermo spento. Il Raspberry (`notifier/`) manda il messaggio a Firebase, Firebase lo porta al telefono (serve solo internet, non ZeroTier).

* **`app/google-services.json`** (console Firebase, app Android `com.vzbot.dashboard`). Per l'APK di GitHub: segreto `GOOGLE_SERVICES_JSON`. Senza, l'app funziona ma dice «Notifiche non attive».
* **Argomento privato**: `notification_topic` in `res/values/notifiche.xml` dev'essere uguale a `topic` in `~/printer_data/vzbot/notifier.json` (l'installer del Raspberry lo scrive uguale).
* Tre canali (Impostazioni → App → VzBot → Notifiche): `allarmi`, `avvisi`, `stampa`. Si creano a ogni avvio, prima che arrivi il primo messaggio. Con l'app aperta le mostra `VzBotMessagingService`.
* Android 13+: alla prima apertura chiede il permesso. Non arrivano se l'app è «Arrestata forzatamente»: basta riaprirla.

## Icona e splash

Stile One UI 9 (fondo `#040507`, bagliori blu/viola/verde acqua, «pillola» di vetro per lo stato). Icona adattiva con fondo e logo su livelli separati (anche tematica su Android 13+).
Le immagini si rigenerano con `python3 tools/genera_icone.py` (Pillow e numpy; il logo è in `tools/assets/logo_vzbot.png`). Colori in `res/values/colors.xml`, temi in `res/values/` e `res/values-v31/`.

## Prove

Senza telefono né Gradle, da questa cartella (servono `kotlinc` e `android.jar` dell'SDK):

```
kotlinc app/src/main/java/com/vzbot/dashboard/Aggiornamento.kt tools/AggiornamentoTest.kt -d prova
java -cp prova:kotlin-stdlib.jar com.vzbot.dashboard.AggiornamentoTestKt

kotlinc -cp android.jar app/src/main/java/com/vzbot/dashboard/Indirizzi.kt tools/IndirizziTest.kt -d prova2
java -cp prova2:kotlin-stdlib.jar:android.jar com.vzbot.dashboard.IndirizziTestKt
```

`AggiornamentoTest.kt` avvia un piccolo server che fa da Brain (anche quando sbaglia: file rovinato, troncato, più grande, 404, 500) e prova controlli e scaricamento.
Il resto del codice (finestra, ponte, installazione) è stato compilato con Kotlin 1.9.10 contro `android.jar` (API 34), ma **non provato su un telefono** e la costruzione con Gradle non
è stata eseguita nell'ambiente di sviluppo: al primo giro conviene guardare il workflow su GitHub e provare l'aggiornamento una volta con il Raspberry acceso.
