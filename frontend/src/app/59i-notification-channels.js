/* ============================================================================
   59i · SETTINGS → NOTIFICATIONS → WHERE THEY ARRIVE (1.20, phase 5c)
   The notifications reach the phone through a "channel" of the notification service (notifier/klippeye_notifier.py):
     · ntfy      the free ntfy app (Android, iPhone) listening to a private random topic made by the backend. Turned on
                 here with one button; the phone is paired by scanning a QR code (ntfy://server/topic), or by hand;
     · Firebase  only for a KlippEye app built for your own Firebase project (guide, appendix A): shown, not set here.
   The settings live in notifier.json on the Raspberry (backend/notify_channels.py); the service reads the change by itself.
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
    h(
      "p",
      { className: "set-group__note", "data-firebase": firebase.on ? "on" : "off" },
      firebase.on ? tx("Firebase: on too (your own build of the KlippEye app).") : firebase.topic_set || firebase.key_found ? tx("Firebase: set up only in part (key or topic missing): see the guide, appendix A.") : tx("Firebase (only for a KlippEye app built for your own Firebase project): not set up. See the guide, appendix A."),
    ),
  );
}
