/* ============================================================================
   59d · ACCESSO
   The optional password of the dashboard (release 1.2.0). The backend keeps it (backend/access.py, never the password
   itself, only its PBKDF2 hash) and decides who is in with a cookie it signs:
     GET  /api/auth/status      { enabled, logged_in, network_checks, allowed_hosts, min_length }
     POST /api/auth/password    { current?, new }  turns it on or changes it; this device stays in, the others go out
     POST /api/auth/disable     { current }        turns it off
     POST /api/auth/logout      this device goes out
     POST /api/auth/logout_all  every other device goes out
     POST /api/auth/guest       { current, new }   1.82: the guest password (look only); /api/auth/guest/remove { current }
   Without the cookie the backend answers 401 with the header X-KlippEye-Login: 1; the watcher below then opens the
   login page (/login, served by the backend itself). Forgotten password: on the Raspberry, `klippeye password remove`.
   The backend words its refusals in the browser's language (English or Italian); "weak" is worded here.
   ========================================================================== */

const ACCESS_STATUS_URL = "/api/auth/status";

/**
 * 1.82: who is using the dashboard: "admin" (the main password, or no password), "guest" (the guest password: looks,
 * never commands) or null while not known. Read once when the page opens.
 */
const accessRoleStore = (() => {
  let role = null;
  const listeners = new Set();
  const set = (value) => {
    role = value;
    document.documentElement.classList.toggle("is-guest", role === "guest");
    listeners.forEach((listener) => listener(role));
  };
  return {
    get: () => role,
    set,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
})();

function useAccessRole() {
  const [role, setRole] = useState(accessRoleStore.get());
  useEffect(() => accessRoleStore.subscribe(setRole), []);
  return role;
}

const GUEST_ALLOWED_POSTS = ["/api/auth/logout", "/api/auth/login"];
let guestToastAt = 0;

/** A guest's command never leaves the page: it is answered here (403) and a note says why, once every few seconds. */
function guestRefusal(input, init) {
  if (accessRoleStore.get() !== "guest") return null;
  const method = String((init && init.method) || (input && input.method) || "GET").toUpperCase();
  if (method === "GET" || method === "HEAD") return null;
  const url = new URL(typeof input === "string" ? input : input.url, window.location.href);
  if (url.origin !== window.location.origin || GUEST_ALLOWED_POSTS.includes(url.pathname)) return null;
  if (Date.now() - guestToastAt > 4000 && typeof toast !== "undefined") {
    guestToastAt = Date.now();
    toast.notice(tx("Guests can only look: log in with the main password to command the printer."), 5000);
  }
  return new Response(JSON.stringify({ ok: false, error: "guest", message: tx("Guests can only look: log in with the main password to command the printer.") }), { status: 403, headers: { "Content-Type": "application/json" } });
}

/** Any request answered "log in first" (expired or revoked cookie) brings the page to the login form, once. */
(function watchForLogin() {
  if (typeof window.fetch !== "function") return;
  const original = window.fetch.bind(window);
  let leaving = false;
  window.fetch = (...args) => {
    const refused = guestRefusal(args[0], args[1]);
    return (refused ? Promise.resolve(refused) : original(...args)).then((response) => {
      if (!leaving && response && response.status === 401 && response.headers && response.headers.get("X-KlippEye-Login") === "1") {
        leaving = true;
        window.location.replace("/login");
      }
      return response;
    });
  };
  // who is using the page (1.82)
  original(ACCESS_STATUS_URL, { cache: "no-store" })
    .then((response) => (response.ok ? response.json() : null))
    .then((info) => accessRoleStore.set(info && info.role ? info.role : "admin"))
    .catch(() => accessRoleStore.set("admin"));
})();

/** { phase: "loading" | "ok" | "old" | "down", info } — "old": a backend before 1.2.0, with no password at all. */
function useAccessStatus(active = true) {
  const [state, setState] = useState({ phase: "loading", info: null });
  const reload = React.useCallback(async () => {
    try {
      const response = await fetchFresh(ACCESS_STATUS_URL, { timeout: BRAIN_READ_TIMEOUT_MS });
      if (response.status === 404) return setState({ phase: "old", info: null });
      const info = await response.json();
      setState(isPlainObject(info) && typeof info.enabled === "boolean" ? { phase: "ok", info } : { phase: "old", info: null });
    } catch (error) {
      setState((old) => (old.phase === "ok" ? old : { phase: "down", info: null }));
    }
  }, []);
  useEffect(() => {
    if (active) reload();
  }, [active, reload]);
  return [state, reload];
}

/** POST a JSON body; resolves { ok, message }. */
async function accessPost(url, body) {
  try {
    const response = await fetch(url, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body || {}) });
    const json = await response.json().catch(() => ({}));
    const weak = json && json.error === "weak";
    return { ok: response.ok && json.ok !== false, message: weak ? tx("The password must have 6 to 256 characters") : (json && json.message) || (response.ok ? "" : tx("Error {status}", { status: response.status })) };
  } catch (error) {
    return { ok: false, message: tx("The KlippEye service does not answer") };
  }
}

function PasswordField({ label, value, onChange, autoComplete, id }) {
  return h(
    "label",
    { className: "set-field" },
    h("span", { className: "set-field__label" }, label),
    h("input", {
      id,
      type: "password",
      className: "oui-field set-field__input",
      value,
      autoComplete,
      autoCapitalize: "off",
      autoCorrect: "off",
      spellCheck: false,
      onChange: (event) => onChange(event.target.value),
    }),
  );
}

function AccessMessage({ result }) {
  if (!result) return null;
  return h("div", { className: cx("set-status", result.ok ? "set-status--ok" : "set-status--warn"), role: result.ok ? "status" : "alert" }, h("span", { className: "set-status__dot" }), result.message);
}

/** Two fields (new + repeat) checked here before the backend sees them. */
function newPasswordProblem(first, second, min) {
  if (first.length < min) return tx("The password must have at least {min} characters", { min });
  if (first !== second) return tx("The two passwords do not match");
  return "";
}

function AccessPage({ active }) {
  const [status, reload] = useAccessStatus(active);
  const [current, setCurrent] = useState("");
  const [first, setFirst] = useState("");
  const [second, setSecond] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const info = status.info || {};
  const min = Number(info.min_length) || 6;

  const run = async (url, body, okMessage, after) => {
    setBusy(true);
    setResult(null);
    const outcome = await accessPost(url, body);
    setBusy(false);
    setResult({ ok: outcome.ok, message: outcome.ok ? okMessage : outcome.message });
    if (outcome.ok) {
      setCurrent("");
      setFirst("");
      setSecond("");
      if (after) after();
      reload();
    }
  };
  const setPassword = () => {
    const problem = newPasswordProblem(first, second, min);
    if (problem) return setResult({ ok: false, message: problem });
    run("/api/auth/password", info.enabled ? { current, new: first } : { new: first }, info.enabled ? tx("Password changed. The other devices will have to log in again.") : tx("Password turned on. This device stays logged in; the others will have to log in."));
  };

  if (status.phase === "loading") return h("div", { className: "set-status" }, h("span", { className: "set-status__dot" }), tx("Reading the access settings…"));
  if (status.phase !== "ok") {
    return h(
      SettingsGroup,
      { title: "Password" },
      h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), status.phase === "old" ? tx("The installed KlippEye service has no password yet: update KlippEye (release 1.2.0 or later).") : tx("The KlippEye service does not answer: try again shortly.")),
    );
  }

  if (info.role === "guest")
    return h(
      SettingsGroup,
      { title: tx("Guest"), note: tx("Logged in with the guest password: you can look at the printer, the camera, the files and the history, not command it or read its configuration.") },
      h("div", { className: "set-status set-status--warn", "data-guest-status": "1" }, h("span", { className: "set-status__dot" }), tx("Guest: look only")),
      h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", onClick: () => accessPost("/api/auth/logout", {}).then(() => window.location.replace("/login")) }, tx("Log in with the main password")),
    );

  const hostsNote = (info.allowed_hosts || []).length ? tx("Extra names allowed: ") + info.allowed_hosts.join(", ") + "." : tx("Besides IP addresses only home network names work (.local, .lan…). For a name of your own: klippeye access host-add NAME");

  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      {
        title: "Password",
        note: info.enabled
          ? tx("Forgot the password? On the Raspberry: klippeye password remove")
          : tx("Optional. Without a password anyone who reaches the dashboard from your network (or the VPN) can control the printer. With a password every device asks for it once, then remembers it for 6 months."),
      },
      h("div", { className: cx("set-status", info.enabled ? "set-status--ok" : "set-status--warn") }, h("span", { className: "set-status__dot" }), info.enabled ? tx("Password on") : tx("Password off")),
      info.enabled && h(PasswordField, { label: tx("Current password"), value: current, onChange: setCurrent, autoComplete: "current-password", id: "access-current" }),
      h(PasswordField, { label: info.enabled ? tx("New password") : tx("Password (at least {min} characters)", { min }), value: first, onChange: setFirst, autoComplete: "new-password", id: "access-new" }),
      h(PasswordField, { label: tx("Repeat the password"), value: second, onChange: setSecond, autoComplete: "new-password", id: "access-repeat" }),
      h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", disabled: busy || !first, onClick: setPassword }, info.enabled ? tx("Change the password") : tx("Turn on the password")),
      h(AccessMessage, { result }),
    ),
    info.enabled && h(GuestPasswordGroup, { info, min, onChanged: reload }),
    info.enabled &&
      h(
        SettingsGroup,
        { title: tx("Devices") },
        h("button", { type: "button", className: "oui-btn oui-btn--accent-soft oui-btn--block", disabled: busy, onClick: () => run("/api/auth/logout_all", {}, tx("Done: the other devices will have to log in again.")) }, tx("Log out all the other devices")),
        h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--block", disabled: busy, onClick: () => run("/api/auth/logout", {}, tx("Logged out."), () => window.location.replace("/login")) }, tx("Log out of this device")),
      ),
    info.enabled &&
      h(
        SettingsGroup,
        { title: tx("Remove the password"), note: tx("It needs the current password (field at the top). The dashboard will open again without logging in.") },
        h("button", { type: "button", className: "oui-btn oui-btn--danger-soft oui-btn--block", disabled: busy || !current, onClick: () => run("/api/auth/disable", { current }, tx("Password removed.")) }, tx("Remove the password")),
      ),
    h(HttpsGroup, null),
    h(
      SettingsGroup,
      { title: tx("Network"), note: hostsNote },
      h(
        "div",
        { className: cx("set-status", info.network_checks ? "set-status--ok" : "set-status--warn") },
        h("span", { className: "set-status__dot" }),
        info.network_checks ? tx("Commands accepted only from the dashboard and the app, not from other sites") : tx("Network checks off (klippeye access network-checks on to turn them on again)"),
      ),
    ),
  );
}

/** 1.82: the guest password: who logs in with it looks at the printer, never commands it. Set with the main password. */
function GuestPasswordGroup({ info, min, onChanged }) {
  const [current, setCurrent] = useState("");
  const [first, setFirst] = useState("");
  const [second, setSecond] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const run = async (url, body, okMessage) => {
    setBusy(true);
    setResult(null);
    const outcome = await accessPost(url, body);
    setBusy(false);
    setResult({ ok: outcome.ok, message: outcome.ok ? okMessage : outcome.message });
    if (outcome.ok) {
      setCurrent("");
      setFirst("");
      setSecond("");
      onChanged();
    }
  };
  const set = () => {
    const problem = newPasswordProblem(first, second, min);
    if (problem) return setResult({ ok: false, message: problem });
    run("/api/auth/guest", { current, new: first }, info.guest_enabled ? tx("Guest password changed: guests will have to log in again.") : tx("Guest password on: who logs in with it can look, not command."));
  };
  return h(
    "div",
    { "data-guest-group": "1" },
    h(
      SettingsGroup,
      {
        title: tx("Guest password"),
        note: tx("A second password, for who should only look: the printer's state, the camera, the files and the history. Guests cannot send commands, start or stop prints, or read the configuration and the settings."),
      },
      h("div", { className: cx("set-status", info.guest_enabled ? "set-status--ok" : "set-status--warn") }, h("span", { className: "set-status__dot" }), info.guest_enabled ? tx("Guest password on") : tx("Guest password off")),
      h(PasswordField, { label: tx("Main password"), value: current, onChange: setCurrent, autoComplete: "current-password", id: "guest-current" }),
      h(PasswordField, { label: info.guest_enabled ? tx("New guest password") : tx("Guest password (at least {min} characters)", { min }), value: first, onChange: setFirst, autoComplete: "new-password", id: "guest-new" }),
      h(PasswordField, { label: tx("Repeat the password"), value: second, onChange: setSecond, autoComplete: "new-password", id: "guest-repeat" }),
      h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", "data-guest-set": "1", disabled: busy || !first || !current, onClick: set }, info.guest_enabled ? tx("Change the guest password") : tx("Turn on the guest password")),
      info.guest_enabled && h("button", { type: "button", className: "oui-btn oui-btn--danger-soft oui-btn--block", "data-guest-remove": "1", disabled: busy || !current, onClick: () => run("/api/auth/guest/remove", { current }, tx("Guest password removed: guests are logged out.")) }, tx("Remove the guest password")),
      h(AccessMessage, { result }),
    ),
  );
}

/** One line for the settings list. */
const accessSummary = (status) => (status.phase !== "ok" ? tx("Optional password") : status.info.enabled ? tx("Password on") : tx("Password off"));

/* ---- HTTPS (1.93) ---------------------------------------------------------------------------------------------- */

/** An encrypted entrance next to the usual one (backend/https_relay.py): on, off, its port, its certificate. */
function HttpsGroup() {
  const [info, setInfo] = useState(null);
  const [port, setPort] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const load = React.useCallback(async () => {
    try {
      const response = await fetchFresh("/api/https", { timeout: BRAIN_READ_TIMEOUT_MS });
      if (!response.ok) return setInfo((old) => old || { missing: true });
      const json = await response.json();
      setInfo(json);
      setPort((old) => old || String(json.port));
    } catch (error) {
      setInfo((old) => old || { missing: true });
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  if (!info || info.missing) return null;
  const send = async (body, okMessage) => {
    setBusy(true);
    setResult(null);
    try {
      const response = await fetch("/api/https", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) });
      const json = await response.json().catch(() => ({}));
      if (!response.ok || json.ok === false) setResult({ ok: false, message: json.error || tx("Error {status}", { status: response.status }) });
      else {
        setInfo(json);
        setPort(String(json.port));
        setResult(json.error ? { ok: false, message: tx("HTTPS could not start: {error}", { error: json.error }) } : { ok: true, message: okMessage });
        // switched off from the encrypted page: this page goes away with it, back to the usual address
        if (info.secure && json.enabled === false) window.location.replace("http://" + window.location.hostname + ":" + KLIPPEYE_PORT + "/");
      }
    } catch (error) {
      setResult({ ok: false, message: tx("The KlippEye service does not answer") });
    }
    setBusy(false);
  };
  const addresses = (info.addresses && info.addresses.length ? info.addresses : [window.location.hostname]).map((host) => "https://" + host + ":" + info.port);
  const portChanged = port.trim() !== String(info.port);
  return h(
    SettingsGroup,
    {
      title: "HTTPS",
      note: tx(
        "An encrypted entrance next to the usual one. Its certificate is made on the Raspberry and no authority signed it: the first time the browser warns that it does not know it. Compare the fingerprint below with the one the browser shows, then go on. The Android app keeps using the usual address.",
      ),
    },
    h(
      "div",
      { className: cx("set-status", info.running ? "set-status--ok" : "set-status--warn"), "data-https-status": info.running ? "on" : "off" },
      h("span", { className: "set-status__dot" }),
      info.running ? tx("On") + (info.secure ? " · " + tx("this page came encrypted") : "") : info.enabled ? tx("On, but not running") : tx("Off"),
    ),
    h("div", { className: "oui-list" }, h(SwitchRow, { title: tx("Encrypted entrance (HTTPS)"), detail: info.running ? addresses.join(" · ") : tx("Port {port}", { port: info.port }), checked: info.enabled, disabled: busy, onChange: (value) => send({ enabled: value }, value ? tx("HTTPS on.") : tx("HTTPS off.")) })),
    info.running &&
      h(
        "div",
        { className: "https-links", "data-https-links": "1" },
        addresses.map((address) => h("a", { key: address, className: "oui-btn oui-btn--quiet oui-btn--sm", href: address + "/", target: "_blank", rel: "noopener" }, address)),
      ),
    h(
      "label",
      { className: "set-field" },
      h("span", { className: "set-field__label" }, tx("Port")),
      h(
        "div",
        { className: "https-port" },
        h("input", { className: "oui-field set-field__input", inputMode: "numeric", value: port, "data-https-port": "1", onChange: (event) => setPort(event.target.value.replace(/[^0-9]/g, "").slice(0, 5)) }),
        portChanged && h("button", { type: "button", className: "oui-btn oui-btn--sm", disabled: busy || !port, onClick: () => send({ port: Number(port) }, tx("Port changed.")) }, tx("Apply")),
      ),
    ),
    info.fingerprint &&
      h("div", { className: "https-fingerprint" }, h("div", { className: "oui-caption" }, tx("Certificate fingerprint (SHA-256)")), h("code", { "data-https-fingerprint": "1" }, info.fingerprint)),
    info.fingerprint &&
      h(
        "button",
        { type: "button", className: "oui-btn oui-btn--quiet oui-btn--block", disabled: busy, "data-https-renew": "1", onClick: () => send({ renew: true }, tx("New certificate made: the browsers will warn once more.")) },
        tx("Make a new certificate (after the Raspberry got a new address)"),
      ),
    info.error && !result && h("div", { className: "set-status set-status--warn", role: "alert" }, h("span", { className: "set-status__dot" }), tx("HTTPS could not start: {error}", { error: info.error })),
    h(AccessMessage, { result }),
  );
}
