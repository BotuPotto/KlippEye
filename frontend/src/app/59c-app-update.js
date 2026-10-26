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
  if (phase === "error") return { phase, message: String(event.messaggio || tx("unknown error")).slice(0, 300) };
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
    const timer = setTimeout(() => setProgress({ phase: "error", message: tx("the app did not answer") }), APP_START_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [progress.phase]);
  const start = (offer) => {
    setProgress({ phase: "starting" });
    try {
      // the app of VzBot 1.0.x only accepts the address it knew: the backend serves the same file there too
      nativeBridge().updateApp(isLegacyApp() ? APP_APK_URL_LEGACY : APP_APK_URL, offer.version, offer.sha256, String(offer.size));
    } catch (error) {
      setProgress({ phase: "error", message: tx("the app did not accept the request") });
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
  const retry = h("button", { type: "button", className: "oui-btn oui-btn--block", onClick: onRetry }, h(Icons.RotateCw, { size: 18 }), tx("Retry"));
  switch (progress.phase) {
    case "starting":
      return h(AppStatus, { tone: "update" }, tx("Starting the update…"));
    case "downloading": {
      const percent = progress.total ? Math.round((progress.done / progress.total) * 100) : 0;
      return h(
        React.Fragment,
        null,
        h(AppStatus, { tone: "update" }, tx("Downloading the app {version}… {percent} %", { version: offer.version, percent })),
        h("div", { className: "oui-progress set-progress", role: "progressbar", "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": percent }, h("div", { className: "oui-progress__bar", style: { width: percent + "%" } })),
      );
    }
    case "permission":
      return h(
        React.Fragment,
        null,
        h(AppStatus, { tone: "warn" }, tx("Android must first allow KlippEye to install apps. In the page that opened turn on «Allow from this source», then come back here: the update starts again by itself.")),
        h("p", { className: "set-group__note" }, tx("With Samsung's Auto Blocker on the permission cannot be given: turn it off in Settings → Security and privacy → Auto Blocker, then retry.")),
        retry,
      );
    case "installing":
      return h(
        React.Fragment,
        null,
        h(AppStatus, { tone: "update" }, tx("Confirm the installation in Android's window («Update» button). When it has finished, open KlippEye again from its icon.")),
        retry,
      );
    default:
      return h(React.Fragment, null, h(AppStatus, { tone: "warn" }, tx("Update failed: ") + progress.message + "."), retry);
  }
}

/** The block itself: what is installed, what the Raspberry has, and the way to get from one to the other. */
function AppBlock({ app, installed }) {
  const updater = useAppUpdater();
  if (app.state === "loading") return h(AppStatus, null, tx("Asking the backend whether there is an app…"));
  if (app.state === "old") return h(AppStatus, { tone: "warn" }, tx("The backend on the Raspberry does not know the app yet: update KlippEye (above) and check again."));
  if (app.state === "down") return h(AppStatus, { tone: "warn" }, tx("The backend does not answer: cannot know whether there is an app."));
  const info = app.info;
  if (!info.available) {
    const none = /nessuna app/i.test(String(info.reason));
    return h(
      React.Fragment,
      null,
      installed && h("div", { className: "oui-list set-info-list" }, h(InfoLine, { label: tx("Installed app"), value: installed.version })),
      h(
        AppStatus,
        { tone: none ? undefined : "warn" },
        none
          ? tx("There is no app on the Raspberry yet. GitHub builds it when you upload the android/ folder (guide: docs/GUIDA.md, «The Android app»); then it comes here with «Update KlippEye».")
          : tx("The app on the Raspberry is not complete ({reason}). Update KlippEye and check again.", { reason: info.reason ? tx(String(info.reason)) : tx("unknown reason") }),
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
        h(AppStatus, { tone: "update" }, tx("The new KlippEye app {version} is ready (this is the VzBot app {installed})", { version: info.version, installed: installed.version })),
        h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", onClick: () => updater.start(info) }, h(Icons.Download, { size: 18 }), tx("Install the new KlippEye app")),
        h(
          "p",
          { className: "set-group__note" },
          tx("This is not an update of this app but a new app, with another icon: Android installs it next to this one. Once installed, open KlippEye from its icon and check that it connects, then uninstall this VzBot app (hold its icon → Uninstall). Settings and notifications are on the Raspberry and are not lost. While you have both apps, notifications reach both."),
        ),
      );
    } else if (waiting) {
      body = h(
        React.Fragment,
        null,
        h(AppStatus, { tone: "update" }, tx("App {version} available (you have {installed})", { version: info.version, installed: installed.version })),
        h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", onClick: () => updater.start(info) }, h(Icons.Download, { size: 18 }), tx("Update the app")),
        h("p", { className: "set-group__note" }, (installed.canInstall ? tx("Android asks you to confirm. The app settings stay.") : tx("Android asks you to confirm and, the first time, the permission «Install unknown apps» for KlippEye. The app settings stay."))),
      );
    } else if (installed.code > Number(info.code)) {
      body = h(AppStatus, { tone: "ok" }, tx("The installed app ({installed}) is newer than the one on the Raspberry: update KlippEye first, above.", { installed: installed.version }));
    } else body = h(AppStatus, { tone: "ok" }, tx("The app is up to date"));
  } else if (IN_APP_WEBVIEW) {
    body = h(
      React.Fragment,
      null,
      h(AppStatus, { tone: "warn" }, tx("This is an older version of the app and it cannot update itself. Install the new one once: from then on it updates from here.")),
      h(ApkDownloadButton, { info, label: tx("Download the app {version}", { version: info.version }) }),
      h(
        "p",
        { className: "set-group__note" },
        APP_CAN_SAVE_FILES ? tx("The file goes into the Download folder: open it (from the phone's Files app) to install it. ") : tx("This app cannot download: open {url} in the phone's browser. ", { url: location.origin + APP_APK_URL }),
        tx("If Android says the app conflicts with the one already installed, uninstall the old one first (the settings are on the Raspberry)."),
      ),
    );
  } else {
    body = h(
      React.Fragment,
      null,
      h(AppStatus, { tone: "update" }, tx("The Android app {version} is ready.", { version: info.version })),
      h(ApkDownloadButton, { info, label: tx("Download the app") }),
      h("p", { className: "set-group__note" }, tx("Open this page from the phone, download the file and open it to install it (Android may ask to allow installing from this source).")),
    );
  }
  return h(
    React.Fragment,
    null,
    h("div", { className: "oui-list set-info-list" }, installed && h(InfoLine, { label: tx("Installed app"), value: installed.version, warn: waiting }), h(InfoLine, { label: tx("On the Raspberry"), value: offerLine })),
    body,
  );
}
