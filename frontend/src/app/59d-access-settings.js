/* ============================================================================
   59d · ACCESSO
   The optional password of the dashboard (release 1.2.0). The backend keeps it (backend/access.py, never the password
   itself, only its PBKDF2 hash) and decides who is in with a cookie it signs:
     GET  /api/auth/status      { enabled, logged_in, network_checks, allowed_hosts, min_length }
     POST /api/auth/password    { current?, new }  turns it on or changes it; this device stays in, the others go out
     POST /api/auth/disable     { current }        turns it off
     POST /api/auth/logout      this device goes out
     POST /api/auth/logout_all  every other device goes out
   Without the cookie the backend answers 401 with the header X-KlippEye-Login: 1; the watcher below then opens the
   login page (/login, served by the backend itself). Forgotten password: on the Raspberry, `klippeye password remove`.
   The backend words its refusals in the browser's language (English or Italian); "weak" is worded here.
   ========================================================================== */

const ACCESS_STATUS_URL = "/api/auth/status";

/** Any request answered "log in first" (expired or revoked cookie) brings the page to the login form, once. */
(function watchForLogin() {
  if (typeof window.fetch !== "function") return;
  const original = window.fetch.bind(window);
  let leaving = false;
  window.fetch = (...args) =>
    original(...args).then((response) => {
      if (!leaving && response && response.status === 401 && response.headers && response.headers.get("X-KlippEye-Login") === "1") {
        leaving = true;
        window.location.replace("/login");
      }
      return response;
    });
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
    return { ok: false, message: tx("The backend does not answer") };
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
      h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), status.phase === "old" ? tx("The installed backend has no password yet: update KlippEye (release 1.2.0 or later).") : tx("The backend does not answer: try again shortly.")),
    );
  }

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

/** One line for the settings list. */
const accessSummary = (status) => (status.phase !== "ok" ? tx("Optional password") : status.info.enabled ? tx("Password on") : tx("Password off"));
