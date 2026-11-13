# KlippEye — Android app

The app is a full-screen window (WebView) on the dashboard that runs on the Raspberry, with the KlippEye icon and splash,
push notifications, file downloads and **updates by itself**. Current version: the number in [`VERSION`](VERSION).

```
android/
  VERSION                 the version number: the ONLY place where it changes
  build.gradle, settings.gradle, gradle.properties, gradlew, gradle/   the Gradle project (gradlew = always the same Gradle, 8.5)
  app/build.gradle        versionName and versionCode come from VERSION; signs when it finds the key (see "Signing")
  app/src/main/java/com/klippeye/app/
      MainActivity.kt     the window, the bridge with the dashboard (KlippEyeApp), downloads, the update
      Addresses.kt        the Raspberry's addresses (home network, ZeroTier/VPN)
      Printers.kt         the other printers opened in the app
      Certificates.kt     the Raspberry's own HTTPS certificate (pinning)
      AppUpdate.kt        checks, download and verification of the update's APK (plain Java)
      AppInstaller.kt     installed version, "Install unknown apps" permission, Android's installer
      PushSettings.kt     how the notifications reach this phone (Firebase or ntfy, with NtfyListenerService)
      Notifications.kt, KlippEyeMessagingService.kt   channels and the notifications shown
  app/src/main/res/       icons, splash, colours, themes, texts (values*/strings.xml), file_paths.xml
  app/src/test/           tests of the parts that need no phone (JUnit)
  chiave/klippeye.p12     the signing key, ENCRYPTED (GitHub makes it the first time; see "Signing")
  tools/                  scripts for the icons and for the texts
```

## Name

The internal name is `com.klippeye.app` and the bridge with the dashboard is `KlippEyeApp` (`KlippEyeApp/9` in the user agent).

## Languages

The app's own screens (splash, the "Addresses" window, messages, the names of the notification channels) are in the
dashboard's ten languages and follow the phone's language; English is the default. The texts are written in
`tools/strings_source.py`, which writes `app/src/main/res/values*/strings.xml`:

```
python3 tools/strings_source.py
```

## Version

`VERSION` holds three numbers from 0 to 99 (`1.0.0`, `1.0.1`, `1.2.0`...). Gradle derives from it:

* `versionName` = the text (`1.0.0`);
* `versionCode` = `major × 10000 + minor × 100 + patch` (`1.0.0` → 10000, `1.2.3` → 10203): it grows with every version, and it is what
  Android compares to know whether an APK is newer.

For a new version **raise the number in `VERSION`**. With a number lower than the published one the workflow stops and says so
(Android never installs an older version over a newer one). A wrong format stops the build with a message.

## How the APK is made

**On GitHub (the normal way).** When something changes in `android/` *and* the number in `VERSION` is new, the workflow
`.github/workflows/app.yml` builds the APK on GitHub's computer, signs it and puts it in `apk/KlippEye.apk` with `apk/version.json`
(version, size, SHA-256 fingerprint, signature). The Raspberry receives it with the normal «Update KlippEye», the backend offers it to
the phone (`/api/app/version`, `/app/KlippEye.apk`) and the dashboard in the app shows «Update the app». Step by step:
[`docs/GUIDE.md`](../docs/GUIDE.md), appendix A.

**With Android Studio (to try a change).** *File → Open* and choose this folder (`android`); *Build → Build APK(s)*. Without the key the
APK is a debug one, signed with Android Studio's key: it **cannot** be installed over the one built by GitHub (different signatures),
so that one must be uninstalled first. `app/google-services.json` (from the Firebase console) is needed only for Firebase notifications;
it must not be committed (it is in `.gitignore`): GitHub's APK uses the secret `GOOGLE_SERVICES_JSON`.

## Signing

Android installs an update only when it is signed with the **same key** as the app it replaces. The key of GitHub's app is
`chiave/klippeye.p12` (PKCS12, alias `klippeye`, RSA 4096, valid 100 years): the workflow makes it the first time and **encrypts it with the
password** in the secret `KLIPPEYE_CHIAVE_PASSWORD` (at least 16 characters). The file is in the (public) repository because every build
needs it: the password is what protects it, so it must be a long sentence and must never be written in the repository. The folder and the
secret keep their first names: renaming them would break the repositories that already build the app.

* The workflow refuses to publish an APK signed with a key **different** from the published app's (the phones could not update): to
  really change key, delete `chiave/klippeye.p12` and start the workflow by hand with «new_key». The installed apps must then be
  uninstalled and installed again, once.
* To use your own key, put its `.p12` (alias `klippeye`, the same password for the store and the key) in `chiave/klippeye.p12`.
* `app/build.gradle` signs the release build only when it finds the variables `KLIPPEYE_KEYSTORE` (the file's path) and `KLIPPEYE_KEYSTORE_PASSWORD`.

## The app updates itself

The dashboard in the app (Settings → Updates → *Android app*) compares the installed version with the one the backend offers.
The bridge the app gives the page (`window.KlippEyeApp`):

| Call | What it does |
|---|---|
| `appInfo()` | answers `{"version":"1.0.0","code":10000,"canInstall":true}` (`canInstall`: Android already allows «Install unknown apps») |
| `updateApp(path, version, sha256, size)` | downloads `/app/KlippEye.apk` from the backend and opens Android's installer; all values are the backend's, as text |
| `window.klippeyeAppUpdate({stato, ...})` | the answer, called by the app: `scarico` (downloading, `fatto` and `totale` in bytes), `permesso` (waiting for the permission), `installazione` (installer open), `errore` (`messaggio`, in the phone's language) |

The names of the bridge (calls, fields, values) are shared with every dashboard version, old and new: they never change.

What the app checks **before** installing (`AppUpdate.kt`, tested by `AppUpdateTest`):

1. the address is the backend it is connected to (same protocol, address and port) and the path is exactly `/app/KlippEye.apk`;
2. the version is newer than the installed one;
3. the downloaded file has the announced size and SHA-256 fingerprint; a different, cut or bigger file is thrown away (nothing half-written);
4. a file already downloaded and identical (while the permission was being granted, say) is used again.

Then Android decides: it **always** asks to confirm, and installs only when the signature is the current app's. The «Install unknown apps»
permission (`REQUEST_INSTALL_PACKAGES`) is granted once: the app opens the right Android page and, back from it, goes on by itself.
With Samsung's Auto Blocker on the permission cannot be granted (switch it off first). The downloaded APK is in `cache/updates/` (the only
folder shared with the installer, `res/xml/file_paths.xml`) and is deleted at the next start. After the installation Android closes the
app: open it again from its icon.

A dashboard opened in an older app (`KlippEyeApp/3` or `/4`) has no `updateApp`: the «Android app» block offers the APK in the Download
folder, to install by hand, once.

## The Raspberry's addresses

There are no built-in addresses: at the first start the app asks for the Raspberry's local IP (the same address used to open the printer's
web page in the browser) and, optionally, the external one (ZeroTier, VPN). Then it tries two rounds, local and external in turn (2.5 s
per attempt); the first that answers wins, otherwise it shows «Try again» and «Addresses». The addresses can also be chosen in the
dashboard's Settings menu, which passes them to the app with `setAddresses`. `setAddresses` accepts only private networks (10.x,
172.16-31.x, 192.168.x, 100.64-127.x, `.local`/`.lan` names...): a page shown in a frame of the dashboard (the «Web page» camera) must
not be able to send the app to an outside site.

For each address the app looks for KlippEye in this order: `https://address/` (only when it knows the Raspberry's certificate),
`http://address/` (without a port: KlippEye 1.94 with nginx) and `http://address:8085/`, which is always there. An address counts only
when `api/auth/status` answers as KlippEye (a JSON with `enabled`): another page may be at the address without a port. The other
printers without a written port are looked for the same way.

## HTTPS (`Certificates.kt`)

KlippEye's HTTPS certificate (1.93) is made by the Raspberry and no authority signs it. The dashboard, as soon as it opens in the app,
passes the certificate's SHA-256 fingerprint with `setCertificate` ("" when HTTPS is off); the app remembers it for that address and from
then on opens the dashboard over https accepting **only** that certificate: in the WebView (`onReceivedSslError`), for downloaded files and
for the app's update. Another certificate is refused and the app falls back to http.

## Links and the back key

* Only the Raspberry's pages stay in the window: a link to another site, to a store, to `ntfy://` or `intent://` opens in the right
  Android app (`shouldOverrideUrlLoading`, for the main page only: a camera in a frame stays inside).
* The phone's back key asks the dashboard first (`window.klippeyeBack()`): it closes the open guide or dialog, goes back to the previous
  page of the menu or step of the guided set-up; only when there is nothing to close does it go back in the WebView or leave the app.
* `allowBackup="false"`: the app's data (addresses, login cookie) do not end up in Google's backups. The WebView does not open the
  phone's own files as pages (`allowFileAccess` off).

## Choosing and saving files

* **Upload file**: Android's file picker (`onShowFileChooser`, no extra permission).
* **Download**: `window.KlippEyeApp.saveUrl(address, name)` downloads from the Raspberry the app is connected to (no other sites, `blob:`
  or `data:`) and saves in **Download** (Android 10+ through MediaStore, no permission; a name already taken becomes `name (1).ext`).
  Before Android 10 it goes into `Android/data/com.klippeye.app/files/Download`.

## Push notifications

The app has **no topic written inside**: it asks the Raspberry it is connected to how to receive them (`GET /api/notifications/app`,
from the dashboard, bridge `KlippEyeApp.notifySetup`) and the person chooses with the dashboard's guided set-up (Settings →
Notifications → This phone). All in `PushSettings.kt`:

* **ntfy** (everyone): `NtfyListenerService` is a foreground service (`specialUse`, the ongoing notification «KlippEye is listening» on
  the `ascolto` channel, the least visible) that reads `<server>/<topics>/json` line by line, reconnects by itself (5 s → 60 s) and gets
  the missed messages with `since=<last id>`. It starts again with the phone and after an update (`BootReceiver`). The Android channel
  comes from the ntfy priority (5 alarms, 4 warnings, 3 print: the same table as `KIND_NTFY` in the notifier).
* **Firebase** (only the installation of whoever maintains the project): the Raspberry gives the Firebase topic **only when it has the
  key** (`service-account.json`); the app subscribes to it and leaves it when it is gone. The topic written in the apps up to 1.2.0 was
  public: the app always leaves it, and the Raspberry replaces it with a secret one (`klippeye-fb-…`).
  For the maintainer: `google-services.json` of the Firebase project (Android app `com.klippeye.app`) in the secret
  `GOOGLE_SERVICES_JSON`; the service account key of the same project is `~/printer_data/klippeye/service-account.json` on their own
  Raspberry, with `"topic"` in `notifier.json`. Without Firebase the app is built anyway and uses ntfy.
* Bridge: `notifySetup(json)`, `notifyState()`, `askNotificationPermission()`, `askBatteryExemption()`, `openNotificationSettings()`;
  the app tells the page with `window.klippeyeNotifyState(state)`.
* Channels (Settings → Apps → KlippEye → Notifications): `allarmi`, `avvisi`, `stampa`, `ascolto`. Their ids are those of the
  notifier and Android keeps the person's settings under them, so they never change; their names follow the phone's language.
  With the app open, Firebase notifications are shown by `KlippEyeMessagingService`.

The preferences the app stores keep the names of its first versions (`ip_locale`, `ricevi`, `argomento`...), so an update keeps
the addresses and the choices of the phone.

## Icon and splash

The KlippEye logo's colours: light violet accent `#b79cff`, background `#040507` with the dark violet `#7a5cff` fading to black (as in
the dashboard), a glass «pill» for the status. The adaptive icon has the logo's dark violet tile as background and the logo on its own
layer above (also the themed version of Android 13+, in one colour); the splash and the notification use the logo without the tile.
The pictures are made again with `python3 tools/make_icons.py` and `python3 tools/make_notification_icon.py` (Pillow and numpy; the logo
is in `tools/assets/`: `klippeye_g4.svg` and `klippeye_g4_mono.svg` are the sources, `logo_klippeye.png` in colour and
`logo_klippeye_mono.png` in one colour). Colours in `res/values/colors.xml`, themes in `res/values/` and `res/values-v31/`.

## Tests

```
./gradlew testDebugUnitTest
```

`AppUpdateTest` starts a small server that stands in for the backend (also when it goes wrong: damaged, cut or bigger file, 404, 500) and
tests the checks and the download; `AddressesTest` the addresses, the other printers, the certificate fingerprints and how the
notifications arrive. GitHub runs them, and builds the app, on every pull request (the *Tests* workflow).
