/* ============================================================================
   59i · SETTINGS → NOTIFICATIONS → WHERE THEY ARRIVE (1.20, phase 5c)
   The notifications reach the phone through a "channel" of the notification service (notifier/klippeye_notifier.py):
     · ntfy      the free ntfy app (Android, iPhone) listening to a private random topic made by the backend. Turned on
                 here with one button; the phone is paired by scanning a QR code (ntfy://server/topic), or by hand;
     · Firebase  only for a KlippEye app built for your own Firebase project (guide, appendix A): shown, not set here.
   The settings live in notifier.json on the Raspberry (backend/notify_channels.py); the service reads the change by itself.
   1.21 (phase 5d): in the KlippEye app (1.3.0, KlippEyeApp/6) the app receives the notifications by itself: it listens to the
   same ntfy topic (no ntfy app), or, only where Firebase is set up (the maintainer's own installation), it subscribes to the
   Firebase topic its Raspberry gives it. A guided procedure ("This phone") sets it up; the dashboard keeps the app in step
   with the Raspberry every time it is opened (useAppNotifySync).
   ========================================================================== */

const NTFY_APPS = [
  { id: "play", label: "Google Play", href: "https://play.google.com/store/apps/details?id=io.heckel.ntfy" },
  { id: "fdroid", label: "F-Droid", href: "https://f-droid.org/packages/io.heckel.ntfy/" },
  { id: "ios", label: "App Store (iPhone)", href: "https://apps.apple.com/app/ntfy/id1625396347" },
];

/** The channels as the backend sees them, and the calls that change them. */
function useNotifyChannels(active) {
  const channels = useBackendJson("/api/notifications/channels", active, 30000);
  const [busy, setBusy] = useState("");
  const [problem, setProblem] = useState("");
  const call = async (what, path, body) => {
    setBusy(what);
    setProblem("");
    try {
      const response = await fetch(path, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body || {}) });
      const data = await response.json().catch(() => ({}));
      setBusy("");
      if (response.status === 404) {
        setProblem(tx("The backend is older than the dashboard: update KlippEye (Settings → Updates)"));
        return null;
      }
      if (!response.ok || data.ok === false) {
        setProblem(data.error || "HTTP " + response.status);
        return null;
      }
      channels.reload();
      return data;
    } catch (error) {
      setBusy("");
      setProblem(tx("the backend does not answer"));
      return null;
    }
  };
  return { ...channels, busy, problem, ntfy: (body) => call("ntfy", "/api/notifications/ntfy", body), test: () => call("test", "/api/notifications/test") };
}

/** A QR code drawn as SVG (qrcode-generator, vendor/). Black on white whatever the theme: phone cameras need the contrast. */
function QrCode({ text, size = 200 }) {
  const path = useMemo(() => {
    try {
      const code = qrcode(0, "M");
      code.addData(text);
      code.make();
      const count = code.getModuleCount();
      let d = "";
      for (let row = 0; row < count; row += 1) for (let col = 0; col < count; col += 1) if (code.isDark(row, col)) d += "M" + (col + 2) + " " + (row + 2) + "h1v1h-1z";
      return { d, count: count + 4 };
    } catch (error) {
      return null;
    }
  }, [text]);
  if (!path) return null;
  return h(
    "svg",
    { className: "nt-qr", width: size, height: size, viewBox: "0 0 " + path.count + " " + path.count, role: "img", "aria-label": tx("QR code to scan with the phone"), "data-qr": text, shapeRendering: "crispEdges" },
    h("rect", { width: path.count, height: path.count, fill: "#fff" }),
    h("path", { d: path.d, fill: "#000" }),
  );
}

function CopyButton({ text, label }) {
  const [done, setDone] = useState(false);
  return h(
    "button",
    { type: "button", className: "oui-btn oui-btn--sm", onClick: async () => setDone(await copyText(text)) },
    done ? tx("Copied") : label || tx("Copy"),
  );
}

const CHANNEL_LABEL = { ntfy: "ntfy", firebase: "Firebase" };

function TestResults({ results }) {
  if (!results) return null;
  if (!results.results.length) return h("p", { className: "set-field__error", role: "alert", "data-test-result": "none" }, results.error ? tx("The test did not run: {error}", { error: results.error }) : tx("No channel is on: turn ntfy on first."));
  return h(
    "ul",
    { className: "nt-results", "data-test-result": results.results.every((one) => one.ok) ? "ok" : "failed" },
    results.results.map((one) =>
      h("li", { key: one.channel, className: one.ok ? "nt-ok" : "nt-bad" }, one.ok ? tx("{channel}: sent. It should appear on the phone within a few seconds.", { channel: CHANNEL_LABEL[one.channel] || one.channel }) : tx("{channel}: NOT sent ({error})", { channel: CHANNEL_LABEL[one.channel] || one.channel, error: one.error })),
    ),
  );
}

function OwnServer({ ntfy, store }) {
  const [server, setServer] = useState(ntfy.default_server ? "" : ntfy.server);
  const [token, setToken] = useState("");
  return h(
    "details",
    { className: "nt-own" },
    h("summary", null, tx("Your own ntfy server (optional)")),
    h("p", { className: "set-group__note" }, tx("Leave it empty to use ntfy.sh, free and with nothing to set up. With a server of your own, write its address and, if it asks for one, an access token.")),
    h("input", { className: "oui-field oui-mono", value: server, placeholder: "https://ntfy.sh", "data-ntfy-server": "1", onChange: (event) => setServer(event.target.value) }),
    h("input", { className: "oui-field oui-mono", type: "password", value: token, autoComplete: "off", placeholder: ntfy.has_token ? tx("Token saved (write here to change it)") : tx("Access token (only if your server wants one)"), onChange: (event) => setToken(event.target.value) }),
    h(
      "div",
      { className: "oui-btn-row" },
      h("button", { type: "button", className: "oui-btn oui-btn--sm", disabled: Boolean(store.busy), "data-ntfy-save-server": "1", onClick: () => store.ntfy(token ? { server, token } : { server }) }, tx("Save the server")),
      ntfy.has_token && h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--quiet", disabled: Boolean(store.busy), onClick: () => store.ntfy({ token: "" }) }, tx("Remove the token")),
    ),
  );
}

function NtfyPairing({ ntfy, store, onPhone }) {
  const [results, setResults] = useState(null);
  const test = async () => {
    setResults(null);
    const answer = await store.test();
    if (answer) setResults(answer);
  };
  return h(
    React.Fragment,
    null,
    h("div", { className: "set-status set-status--ok", "data-ntfy": "on" }, h("span", { className: "set-status__dot" }), tx("ntfy on: private address made for this printer")),
    h(
      "ol",
      { className: "nt-steps" },
      h(
        "li",
        null,
        h("b", null, tx("Install the free ntfy app on the phone")),
        IN_APP_WEBVIEW
          ? h("p", { className: "set-group__note" }, tx("Look for «ntfy» in Google Play, F-Droid or the App Store."))
          : h("div", { className: "nt-links" }, NTFY_APPS.map((app) => h("a", { key: app.id, className: "oui-btn oui-btn--sm", href: app.href, target: "_blank", rel: "noopener noreferrer" }, app.label))),
      ),
      h(
        "li",
        null,
        h("b", null, onPhone && !IN_APP_WEBVIEW ? tx("Tap «Open in the ntfy app»: it subscribes by itself") : tx("Scan this code with the phone's camera: the ntfy app opens and subscribes")),
        h("div", { className: "nt-pair" }, h(QrCode, { text: ntfy.link }), onPhone && !IN_APP_WEBVIEW && h("a", { className: "oui-btn oui-btn--primary", href: ntfy.link, "data-ntfy-link": "1" }, tx("Open in the ntfy app"))),
        h(
          "p",
          { className: "set-group__note" },
          tx("Or add it by hand in the app (the + button): server"),
          " ",
          h("code", null, ntfy.server),
          ", ",
          tx("topic"),
          " ",
          h("code", { "data-ntfy-topic": ntfy.topic }, ntfy.topic),
          " ",
          h(CopyButton, { text: ntfy.topic, label: tx("Copy the topic") }),
        ),
      ),
      h(
        "li",
        null,
        h("b", null, tx("Check that it arrives")),
        h("div", null, h("button", { type: "button", className: "oui-btn oui-btn--sm", disabled: Boolean(store.busy), "data-ntfy-test": "1", onClick: test }, store.busy === "test" ? tx("Sending…") : tx("Send a test notification"))),
        h(TestResults, { results }),
      ),
    ),
    h("p", { className: "set-group__note" }, tx("Whoever knows this address can read the notifications: do not share the code. If notifications arrive late on Android, open the topic in the ntfy app and turn on «Instant delivery». Several phones can scan the same code.")),
    h(
      "div",
      { className: "oui-btn-row" },
      h("button", { type: "button", className: "oui-btn oui-btn--sm", disabled: Boolean(store.busy), "data-ntfy-new": "1", onClick: () => window.confirm(tx("Make a new address? The phones paired now stop receiving until they scan the new code.")) && store.ntfy({ new_topic: true }) }, tx("New address")),
      h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--quiet", disabled: Boolean(store.busy), "data-ntfy-off": "1", onClick: () => store.ntfy({ enabled: false }) }, tx("Turn ntfy off")),
    ),
    h(OwnServer, { ntfy, store }),
  );
}

/** "Where they arrive": the first group of Settings → Notifications. */
function NotificationChannels({ store }) {
  const onPhone = useMemo(() => /Android|iPhone|iPad/i.test(navigator.userAgent || ""), []);
  if (store.phase === "old") return h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), tx("The backend is older than the dashboard: update KlippEye (Settings → Updates)"));
  if (store.phase !== "ok") return h("div", { className: "set-status" }, h("span", { className: "set-status__dot" }), store.phase === "loading" ? tx("Checking the Raspberry…") : tx("the backend does not answer"));
  const { ntfy, firebase } = store.data;
  return h(
    React.Fragment,
    null,
    ntfy.enabled
      ? h(NtfyPairing, { ntfy, store, onPhone })
      : h(
          React.Fragment,
          null,
          !firebase.on && h("div", { className: "set-status set-status--warn", "data-ntfy": "off" }, h("span", { className: "set-status__dot" }), tx("No channel is on: the notifications do not reach any phone.")),
          h("p", { className: "set-group__note" }, tx("With the free ntfy app (Android and iPhone) the notifications arrive with no account and no key: KlippEye makes a private address that only your phones know.")),
          h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", disabled: Boolean(store.busy), "data-ntfy-on": "1", onClick: () => store.ntfy({ enabled: true, click: window.location.origin + "/" }) }, h(Icons.Bell, { size: 18 }), tx("Turn on notifications with ntfy")),
        ),
    store.problem && h("p", { className: "set-field__error", role: "alert" }, store.problem),
    // Firebase is the maintainer's own channel (the published app's Firebase project): shown only where it is set up
    (firebase.on || firebase.topic_set || firebase.key_found) &&
      h("p", { className: "set-group__note", "data-firebase": firebase.on ? "on" : "partial" }, firebase.on ? tx("Firebase: on too (the KlippEye app receives through it).") : tx("Firebase: set up only in part (key or topic missing).")),
    !IN_APP_WEBVIEW && h("p", { className: "set-group__note", "data-app-hint": "1" }, tx("On Android the KlippEye app can receive the notifications by itself, with no ntfy app: open this page in the app (Settings → Updates → Android app to install it).")),
  );
}

/* ---------------------------------------------------------------------------
   This phone (the KlippEye app, 1.3.0+)
   ------------------------------------------------------------------------- */
const NOTIFY_INVITE_KEY = "ke_notify_invite_closed";
const PROOF_WAIT_MS = 30000;

/** What the app says about the notifications of this phone (Ascolto.stato in the app), or null outside the app. */
function readAppNotifyState() {
  const bridge = nativeBridge();
  if (!APP_CAN_NOTIFY || !bridge || typeof bridge.notifyState !== "function") return null;
  try {
    return JSON.parse(bridge.notifyState());
  } catch (error) {
    return null;
  }
}

/** Gives the app what the Raspberry says (ntfy topic, Firebase topic where it is set up) plus `extra` ({ricevi: true|false}). */
async function syncAppNotifications(extra) {
  const bridge = nativeBridge();
  if (!APP_CAN_NOTIFY || !bridge || typeof bridge.notifySetup !== "function") return null;
  try {
    const response = await fetchFresh("/api/notifications/app", { timeout: BRAIN_READ_TIMEOUT_MS });
    const data = await response.json();
    if (!response.ok || !data.ok) return null;
    return JSON.parse(bridge.notifySetup(JSON.stringify({ ntfy: data.ntfy || null, firebaseTopic: data.firebaseTopic || "", ...(extra || {}) })));
  } catch (error) {
    return null;
  }
}

/** In the app: keep it in step with the Raspberry (a new ntfy address, ntfy turned off...) at start, on return and every 10 minutes. */
function useAppNotifySync() {
  useEffect(() => {
    if (!APP_CAN_NOTIFY) return undefined;
    syncAppNotifications();
    const timer = setInterval(() => syncAppNotifications(), 10 * 60 * 1000);
    const stop = onResume(() => syncAppNotifications());
    return () => {
      clearInterval(timer);
      stop();
    };
  }, []);
}

/** The app calls window.klippeyeNotifyState(state) when something changed (permission given, back from Android's settings). */
const notifyStateListeners = new Set();
window.klippeyeNotifyState = (fresh) => notifyStateListeners.forEach((listener) => listener(fresh && typeof fresh === "object" ? fresh : readAppNotifyState()));

/** The state of this phone, read again every second and a half while `active` (and at once when the app says so). */
function useAppNotifyState(active) {
  const [state, setState] = useState(readAppNotifyState);
  useEffect(() => {
    if (!active || !APP_CAN_NOTIFY) return undefined;
    const read = () => setState(readAppNotifyState());
    notifyStateListeners.add(setState);
    read();
    const timer = setInterval(read, 1500);
    return () => {
      clearInterval(timer);
      notifyStateListeners.delete(setState);
    };
  }, [active]);
  return [state, setState];
}

function PhoneStep({ number, done, current, title, children }) {
  return h(
    "li",
    { className: cx("nt-phone-step", done && "is-done", current && "is-current"), "data-phone-step": number, "data-done": done ? "1" : "0" },
    h("span", { className: "nt-phone-step__mark", "aria-hidden": "true" }, done ? h(Icons.Check, { size: 16 }) : number),
    h("div", { className: "nt-phone-step__body" }, h("b", null, title), (current || done) && children),
  );
}

/** The guided procedure: receive the notifications of the printer on this phone, through the KlippEye app. */
function PhoneNotifications({ store }) {
  const [state, setState] = useAppNotifyState(true);
  const [proof, setProof] = useState(null); // null | "waiting" | "arrived" | "late" | "failed"
  const [proofText, setProofText] = useState("");
  const [busy, setBusy] = useState(false);
  if (!APP_CAN_NOTIFY) {
    return h("div", { className: "set-status set-status--warn", "data-phone": "old-app" }, h("span", { className: "set-status__dot" }), tx("Update the KlippEye app (Settings → Updates → Android app) to receive the notifications in the app itself, without ntfy."));
  }
  if (!state || store.phase !== "ok") return h("div", { className: "set-status" }, h("span", { className: "set-status__dot" }), tx("Checking the Raspberry…"));
  const { ntfy, firebase } = store.data;
  const useFirebase = firebase.on;
  const sync = async (extra) => {
    setBusy(true);
    const fresh = await syncAppNotifications(extra);
    setBusy(false);
    if (fresh) setState(fresh);
  };
  const channelReady = useFirebase || ntfy.enabled;
  const receiving = state.mode !== ""; // Firebase receives also before the choice (as with the app 1.2.0)
  const steps = [
    { id: "permission", done: state.permission },
    ...(useFirebase ? [] : [{ id: "channel", done: channelReady }]),
    { id: "receive", done: receiving },
    ...(useFirebase ? [] : [{ id: "battery", done: state.battery }]),
    { id: "proof", done: proof === "arrived" },
  ];
  const current = (steps.find((step) => !step.done) || {}).id;
  const isDone = (id) => (steps.find((step) => step.id === id) || {}).done;
  const prove = async () => {
    const before = Number(state.lastMessageAt) || 0;
    setProof("waiting");
    setProofText("");
    const answer = await store.test();
    if (!answer) return setProof("failed");
    const failed = (answer.results || []).filter((one) => !one.ok);
    if (!(answer.results || []).length || failed.length === (answer.results || []).length) {
      setProofText(failed.map((one) => one.error).join("; "));
      return setProof("failed");
    }
    const end = Date.now() + PROOF_WAIT_MS;
    while (Date.now() < end) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      const fresh = readAppNotifyState();
      if (fresh && Number(fresh.lastMessageAt) > before) {
        setState(fresh);
        return setProof("arrived");
      }
    }
    setProof("late");
  };
  let number = 0;
  const step = (id, title, ...children) => h(PhoneStep, { key: id, number: (number += 1), done: isDone(id), current: current === id, title }, ...children);
  return h(
    React.Fragment,
    null,
    receiving
      ? h(
          "div",
          { className: "set-status set-status--ok", "data-phone": "on" },
          h("span", { className: "set-status__dot" }),
          state.mode === "firebase" ? tx("This phone receives the notifications (Firebase).") : state.connected ? tx("This phone receives the notifications: connected.") : tx("This phone receives the notifications: connecting…"),
        )
      : h("p", { className: "set-group__note", "data-phone": "off" }, tx("A few steps and the notifications of the printer arrive on this phone, also with the app closed. Nothing else to install.")),
    h(
      "ol",
      { className: "nt-phone" },
      step(
        "permission",
        tx("Allow the notifications"),
        !state.permission && h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--sm", "data-phone-action": "permission", onClick: () => nativeBridge().askNotificationPermission() }, tx("Allow")),
      ),
      !useFirebase &&
        step(
          "channel",
          tx("Make the private address on the Raspberry"),
          ntfy.enabled
            ? h("p", { className: "set-group__note" }, tx("Done: only your phones know it."))
            : h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--sm", disabled: Boolean(store.busy), "data-phone-action": "channel", onClick: async () => (await store.ntfy({ enabled: true, click: window.location.origin + "/" })) && sync() }, tx("Make it")),
        ),
      step(
        "receive",
        tx("Receive on this phone"),
        receiving
          ? null
          : h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--sm", disabled: busy || !channelReady, "data-phone-action": "receive", onClick: () => sync({ ricevi: true }) }, tx("Receive here")),
      ),
      !useFirebase &&
        step(
          "battery",
          tx("Let KlippEye stay awake"),
          h("p", { className: "set-group__note" }, tx("To receive at once KlippEye keeps a connection open, shown by a small fixed notification «KlippEye in ascolto» (hold it to hide it). Android puts still apps to sleep: allow KlippEye to run without battery limits.")),
          !state.battery && h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--sm", "data-phone-action": "battery", onClick: () => nativeBridge().askBatteryExemption() }, tx("Allow")),
        ),
      step(
        "proof",
        tx("Check that it arrives"),
        h("button", { type: "button", className: "oui-btn oui-btn--sm", disabled: proof === "waiting" || !receiving, "data-phone-action": "proof", onClick: prove }, proof === "waiting" ? tx("Waiting for it…") : tx("Send a test notification")),
        proof === "arrived" && h("p", { className: "nt-ok", "data-proof": "arrived" }, tx("Arrived on this phone. All set!")),
        proof === "late" && h("p", { className: "nt-bad", "data-proof": "late" }, tx("Sent, but it has not arrived here within 30 seconds. Check that the phone is online and that the notifications of KlippEye are on in Android.")),
        proof === "failed" && h("p", { className: "nt-bad", "data-proof": "failed" }, tx("The Raspberry could not send it") + (proofText ? " (" + proofText + ")" : store.problem ? " (" + store.problem + ")" : "") + "."),
      ),
    ),
    h(
      "div",
      { className: "oui-btn-row" },
      receiving && h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--quiet", disabled: busy, "data-phone-action": "stop", onClick: () => sync({ ricevi: false }) }, tx("Do not receive on this phone")),
      h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--quiet", onClick: () => nativeBridge().openNotificationSettings() }, tx("Notification settings of Android")),
    ),
  );
}

/** In the app, once: "receive the notifications on this phone?" until the person sets it up or says "not now". */
function NotifyInvite({ onOpen }) {
  const [state] = useAppNotifyState(APP_CAN_NOTIFY);
  const [closed, setClosed] = useState(() => storage.get(NOTIFY_INVITE_KEY) === "1");
  if (!state || closed || state.chosen || state.mode) return null;
  const close = () => {
    storage.set(NOTIFY_INVITE_KEY, "1");
    setClosed(true);
  };
  return h(
    "div",
    { className: "nt-invite", role: "dialog", "aria-label": tx("Notifications"), "data-notify-invite": "1" },
    h("span", { className: "nt-invite__icon" }, h(Icons.Bell, { size: 20 })),
    h("span", { className: "nt-invite__text" }, tx("Receive the notifications of the printer on this phone?")),
    h(
      "span",
      { className: "nt-invite__buttons" },
      h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--quiet", onClick: close }, tx("Not now")),
      h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--primary", onClick: () => (close(), onOpen()) }, tx("Set up")),
    ),
  );
}
