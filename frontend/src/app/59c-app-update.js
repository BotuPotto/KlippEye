/* ============================================================================
   59c · APP ANDROID
   The block "App Android" of the page Aggiornamenti. GitHub builds the app (apk/ of the repository) and Moonraker brings
   it to the Raspberry with the update of KlippEye; the backend offers it: GET /api/app/version says which version it is and
   whether the file is whole, /app/KlippEye.apk is the file. What the block does depends on where the dashboard is open:
     · in the Android app of release 5 or later (user agent KlippEyeApp/5): the app knows its own version
       (window.KlippEyeApp.appInfo()) and installs the update itself (window.KlippEyeApp.updateApp(path, version, sha256, size));
       it reports back by calling window.klippeyeAppUpdate({ stato: "scarico" | "permesso" | "installazione" | "errore", ... });
     · in an older app (KlippEyeApp/3 or 4): it can only save the APK into Download, to be installed by hand, once;
     · in a browser: a plain download (to be opened on the phone).
   Android always asks the user to confirm an installation, and installs only an APK signed with the key of the app it
   replaces: this block cannot do more than ask.
   ========================================================================== */

const APP_APK_URL = "/app/KlippEye.apk";
const APP_APK_URL_LEGACY = "/app/VzBot.apk";
const APP_POLL_MS = 15000;
const APP_START_TIMEOUT_MS = 10000;
const APP_SHA256 = /^[0-9a-f]{64}$/;
const APP_EVENT_PHASES = { scarico: "downloading", permesso: "permission", installazione: "installing", errore: "error" };

/**
 * What the backend offers: { state: "ok", info } (info.available says whether there is an app and, when there is,
 * version, code, size, sha256, built; when there is not, reason) | { state: "old" } (a backend that does not know apps)
 * | { state: "down" }.
 */
async function readAppRelease() {
  try {
    const response = await fetchFresh("/api/app/version", { timeout: BRAIN_READ_TIMEOUT_MS });
    if (response.status === 404) return { state: "old" };
    if (!response.ok) return { state: "down" };
    const info = await response.json();
    if (!isPlainObject(info) || typeof info.available !== "boolean") return { state: "old" };
    if (info.available && !(typeof info.version === "string" && Number(info.code) > 0 && Number(info.size) > 0 && APP_SHA256.test(String(info.sha256)))) return { state: "old" };
    return { state: "ok", info };
  } catch (error) {
    return { state: "down" };
  }
}

/** readAppRelease() read every few seconds while `active`. */
function useAppRelease(active = true) {
  const [app, setApp] = useState({ state: "loading" });
  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    const stop = startPolling(async () => {
      const answer = await readAppRelease();
      if (!cancelled) setApp(answer);
    }, APP_POLL_MS);
    return () => {
      cancelled = true;
      stop();
    };
  }, [active]);
  return app;
}

/** The installed app according to the app itself: { version, code, canInstall }; null in a browser, in an app older than release 5 or if the bridge fails. */
function readInstalledApp() {
  const bridge = nativeBridge();
  if (!APP_CAN_UPDATE || !bridge || typeof bridge.appInfo !== "function") return null;
  try {
    const info = JSON.parse(bridge.appInfo());
    if (!isPlainObject(info) || typeof info.version !== "string" || !Number.isFinite(Number(info.code))) return null;
    return { version: info.version, code: Number(info.code), canInstall: info.canInstall !== false };
  } catch (error) {
    return null;
  }
}

/** A newer app is on the Raspberry than the one installed here (only an app of release 5 can tell). */
const appUpdateWaiting = (app, installed) => Boolean(installed) && app.state === "ok" && app.info.available && installed.code < Number(app.info.code);

/** What the app says about the update it is running (window.vzAppUpdate), as a { phase, ... } of this page; null if it is not understood. */
function appEventToProgress(event) {
  const phase = isPlainObject(event) ? APP_EVENT_PHASES[event.stato] : null;
  if (!phase) return null;
  if (phase === "downloading") {
    const total = Math.max(0, Number(event.totale) || 0);
    return { phase, total, done: Math.min(total, Math.max(0, Number(event.fatto) || 0)) };
  }
  if (phase === "error") return { phase, message: String(event.messaggio || "errore sconosciuto").slice(0, 300) };
  return { phase };
}

/** { progress: { phase: "idle" | "starting" | "downloading" | "permission" | "installing" | "error", ... }, start(offer) } */
function useAppUpdater() {
  const [progress, setProgress] = useState({ phase: "idle" });
  useEffect(() => {
    const listener = (event) => {
      const next = appEventToProgress(event);
      if (next) setProgress(next);
    };
    // klippeyeAppUpdate: called by the KlippEye app; vzAppUpdate: by the app of VzBot 1.0.x
    window.klippeyeAppUpdate = window.vzAppUpdate = listener;
    return () => {
      if (window.vzAppUpdate === listener) window.klippeyeAppUpdate = window.vzAppUpdate = undefined;
    };
  }, []);
  useEffect(() => {
    if (progress.phase !== "starting") return undefined;
    const timer = setTimeout(() => setProgress({ phase: "error", message: "l'app non ha risposto" }), APP_START_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [progress.phase]);
  const start = (offer) => {
    setProgress({ phase: "starting" });
    try {
      // the app of VzBot 1.0.x only accepts the address it knew: the backend serves the same file there too
      nativeBridge().updateApp(isLegacyApp() ? APP_APK_URL_LEGACY : APP_APK_URL, offer.version, offer.sha256, String(offer.size));
    } catch (error) {
      setProgress({ phase: "error", message: "l'app non ha accettato la richiesta" });
    }
  };
  return { progress, start };
}

const AppStatus = ({ tone, children }) =>
  h("div", { className: cx("set-status", tone && "set-status--" + tone), role: tone === "warn" ? "alert" : undefined }, h("span", { className: "set-status__dot" }), h("span", null, children));

const ApkDownloadButton = ({ info, label }) =>
  h("button", { type: "button", className: "oui-btn oui-btn--block", onClick: () => downloadFile(APP_APK_URL, "KlippEye-" + info.version + ".apk") }, h(Icons.Download, { size: 18 }), label);

/** The running update: a bar while the app downloads, then what the person has to do in Android. */
function AppUpdateProgress({ progress, offer, onRetry }) {
  const retry = h("button", { type: "button", className: "oui-btn oui-btn--block", onClick: onRetry }, h(Icons.RotateCw, { size: 18 }), "Riprova");
  switch (progress.phase) {
    case "starting":
      return h(AppStatus, { tone: "update" }, "Avvio l'aggiornamento…");
    case "downloading": {
      const percent = progress.total ? Math.round((progress.done / progress.total) * 100) : 0;
      return h(
        React.Fragment,
        null,
        h(AppStatus, { tone: "update" }, "Scarico l'app " + offer.version + "… " + percent + " %"),
        h("div", { className: "oui-progress set-progress", role: "progressbar", "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": percent }, h("div", { className: "oui-progress__bar", style: { width: percent + "%" } })),
      );
    }
    case "permission":
      return h(
        React.Fragment,
        null,
        h(AppStatus, { tone: "warn" }, "Android deve prima permettere a KlippEye di installare app. Nella pagina che si è aperta attiva «Consenti da questa fonte», poi torna qui: l'aggiornamento riparte da solo."),
        h("p", { className: "set-group__note" }, "Con l'Auto Blocker di Samsung attivo il permesso non si può dare: spegnilo da Impostazioni → Sicurezza e privacy → Auto Blocker, poi riprova."),
        retry,
      );
    case "installing":
      return h(
        React.Fragment,
        null,
        h(AppStatus, { tone: "update" }, "Conferma l'installazione nella finestra di Android (tasto «Aggiorna»). Quando ha finito, riapri KlippEye dall'icona."),
        retry,
      );
    default:
      return h(React.Fragment, null, h(AppStatus, { tone: "warn" }, "Aggiornamento non riuscito: " + progress.message + "."), retry);
  }
}

/** The block itself: what is installed, what the Raspberry has, and the way to get from one to the other. */
function AppBlock({ app, installed }) {
  const updater = useAppUpdater();
  if (app.state === "loading") return h(AppStatus, null, "Chiedo al backend se c'è un'app…");
  if (app.state === "old") return h(AppStatus, { tone: "warn" }, "Il backend sul Raspberry non conosce ancora l'app: aggiorna KlippEye (qui sopra) e ricontrolla.");
  if (app.state === "down") return h(AppStatus, { tone: "warn" }, "Il backend non risponde: non posso sapere se c'è un'app.");
  const info = app.info;
  if (!info.available) {
    const none = /nessuna app/i.test(String(info.reason));
    return h(
      React.Fragment,
      null,
      installed && h("div", { className: "oui-list set-info-list" }, h(InfoLine, { label: "App installata", value: installed.version })),
      h(
        AppStatus,
        { tone: none ? undefined : "warn" },
        none
          ? "Sul Raspberry non c'è ancora nessuna app. GitHub la costruisce quando carichi la cartella android/ (guida: docs/GUIDA.md, «L'app Android»); poi arriva qui con «Aggiorna KlippEye»."
          : "L'app sul Raspberry non è completa (" + String(info.reason || "motivo sconosciuto") + "). Aggiorna KlippEye e ricontrolla.",
      ),
    );
  }

  const waiting = appUpdateWaiting(app, installed);
  const busy = updater.progress.phase !== "idle";
  const offerLine = info.version + " • " + formatBytes(Number(info.size));
  let body;
  if (installed) {
    if (busy) body = h(AppUpdateProgress, { progress: updater.progress, offer: info, onRetry: () => updater.start(info) });
    else if (isLegacyApp()) {
      // the app of VzBot 1.0.x: the new one is another package, so Android installs it beside this one
      body = h(
        React.Fragment,
        null,
        h(AppStatus, { tone: "update" }, "È pronta la nuova app KlippEye " + info.version + " (questa è l'app VzBot " + installed.version + ")"),
        h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", onClick: () => updater.start(info) }, h(Icons.Download, { size: 18 }), "Installa la nuova app KlippEye"),
        h(
          "p",
          { className: "set-group__note" },
          "Non è un aggiornamento di questa app ma un'app nuova, con un'altra icona: Android la installa accanto a questa. Quando l'hai installata apri KlippEye dall'icona e controlla che si colleghi, poi disinstalla questa app VzBot (tieni premuta l'icona → Disinstalla). Impostazioni e notifiche stanno sul Raspberry e non si perdono. Finché hai tutte e due le app, le notifiche arrivano su entrambe.",
        ),
      );
    } else if (waiting) {
      body = h(
        React.Fragment,
        null,
        h(AppStatus, { tone: "update" }, "Disponibile l'app " + info.version + " (hai la " + installed.version + ")"),
        h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", onClick: () => updater.start(info) }, h(Icons.Download, { size: 18 }), "Aggiorna l'app"),
        h("p", { className: "set-group__note" }, "Android ti chiede conferma" + (installed.canInstall ? "" : " e, la prima volta, il permesso «Installa app sconosciute» per KlippEye") + ". Le impostazioni dell'app restano."),
      );
    } else if (installed.code > Number(info.code)) {
      body = h(AppStatus, { tone: "ok" }, "L'app installata (" + installed.version + ") è più nuova di quella sul Raspberry: aggiorna prima KlippEye, qui sopra.");
    } else body = h(AppStatus, { tone: "ok" }, "L'app è aggiornata");
  } else if (IN_APP_WEBVIEW) {
    body = h(
      React.Fragment,
      null,
      h(AppStatus, { tone: "warn" }, "Questa è una versione precedente dell'app e non sa aggiornarsi da sola. Installa quella nuova una volta: da lì in poi si aggiorna da qui."),
      h(ApkDownloadButton, { info, label: "Scarica l'app " + info.version }),
      h(
        "p",
        { className: "set-group__note" },
        APP_CAN_SAVE_FILES ? "Il file va nella cartella Download: aprilo (dall'app File del telefono) per installarlo. " : "Questa app non sa scaricare: apri " + location.origin + APP_APK_URL + " nel browser del telefono. ",
        "Se Android dice che l'app è in conflitto con quella già installata, disinstalla prima quella vecchia (le impostazioni stanno sul Raspberry).",
      ),
    );
  } else {
    body = h(
      React.Fragment,
      null,
      h(AppStatus, { tone: "update" }, "L'app Android " + info.version + " è pronta."),
      h(ApkDownloadButton, { info, label: "Scarica l'app" }),
      h("p", { className: "set-group__note" }, "Apri questa pagina dal telefono, scarica il file e aprilo per installarlo (Android può chiedere di consentire l'installazione da questa fonte)."),
    );
  }
  return h(
    React.Fragment,
    null,
    h("div", { className: "oui-list set-info-list" }, installed && h(InfoLine, { label: "App installata", value: installed.version, warn: waiting }), h(InfoLine, { label: "Sul Raspberry", value: offerLine })),
    body,
  );
}
