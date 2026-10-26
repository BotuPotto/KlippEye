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
    return { ok: response.ok && json.ok !== false, message: weak ? "La password deve avere da 6 a 256 caratteri" : (json && json.message) || (response.ok ? "" : "Errore " + response.status) };
  } catch (error) {
    return { ok: false, message: "Il backend non risponde" };
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
  if (first.length < min) return "La password deve avere almeno " + min + " caratteri";
  if (first !== second) return "Le due password non coincidono";
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
    run("/api/auth/password", info.enabled ? { current, new: first } : { new: first }, info.enabled ? "Password cambiata. Gli altri dispositivi dovranno rifare l'accesso." : "Password attivata. Questo dispositivo resta dentro; gli altri dovranno fare l'accesso.");
  };

  if (status.phase === "loading") return h("div", { className: "set-status" }, h("span", { className: "set-status__dot" }), "Leggo le impostazioni di accesso…");
  if (status.phase !== "ok") {
    return h(
      SettingsGroup,
      { title: "Password" },
      h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), status.phase === "old" ? "Il backend installato non ha ancora la password: aggiorna KlippEye (release 1.2.0 o successiva)." : "Il backend non risponde: riprova tra poco."),
    );
  }

  const hostsNote = (info.allowed_hosts || []).length ? "Nomi in più ammessi: " + info.allowed_hosts.join(", ") + "." : "Oltre agli indirizzi IP valgono solo i nomi della rete di casa (.local, .lan…). Per un nome tuo: klippeye access host-add NOME";

  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      {
        title: "Password",
        note: info.enabled
          ? "Password dimenticata? Sul Raspberry: klippeye password remove"
          : "Facoltativa. Senza password chiunque raggiunga la dashboard dalla tua rete (o dalla VPN) può comandare la stampante. Con la password ogni dispositivo la chiede una volta, poi la ricorda per 6 mesi.",
      },
      h("div", { className: cx("set-status", info.enabled ? "set-status--ok" : "set-status--warn") }, h("span", { className: "set-status__dot" }), info.enabled ? "Password attiva" : "Password non attiva"),
      info.enabled && h(PasswordField, { label: "Password attuale", value: current, onChange: setCurrent, autoComplete: "current-password", id: "access-current" }),
      h(PasswordField, { label: info.enabled ? "Nuova password" : "Password (almeno " + min + " caratteri)", value: first, onChange: setFirst, autoComplete: "new-password", id: "access-new" }),
      h(PasswordField, { label: "Ripeti la password", value: second, onChange: setSecond, autoComplete: "new-password", id: "access-repeat" }),
      h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", disabled: busy || !first, onClick: setPassword }, info.enabled ? "Cambia la password" : "Attiva la password"),
      h(AccessMessage, { result }),
    ),
    info.enabled &&
      h(
        SettingsGroup,
        { title: "Dispositivi" },
        h("button", { type: "button", className: "oui-btn oui-btn--accent-soft oui-btn--block", disabled: busy, onClick: () => run("/api/auth/logout_all", {}, "Fatto: gli altri dispositivi dovranno rifare l'accesso.") }, "Fai uscire tutti gli altri dispositivi"),
        h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--block", disabled: busy, onClick: () => run("/api/auth/logout", {}, "Uscito.", () => window.location.replace("/login")) }, "Esci da questo dispositivo"),
      ),
    info.enabled &&
      h(
        SettingsGroup,
        { title: "Togli la password", note: "Serve la password attuale (campo in alto). La dashboard tornerà ad aprirsi senza accesso." },
        h("button", { type: "button", className: "oui-btn oui-btn--danger-soft oui-btn--block", disabled: busy || !current, onClick: () => run("/api/auth/disable", { current }, "Password tolta.") }, "Togli la password"),
      ),
    h(
      SettingsGroup,
      { title: "Rete", note: hostsNote },
      h(
        "div",
        { className: cx("set-status", info.network_checks ? "set-status--ok" : "set-status--warn") },
        h("span", { className: "set-status__dot" }),
        info.network_checks ? "Comandi accettati solo dalla dashboard e dall'app, non da altri siti" : "Controlli di rete spenti (klippeye access network-checks on per riaccenderli)",
      ),
    ),
  );
}

/** One line for the settings list. */
const accessSummary = (status) => (status.phase !== "ok" ? "Password facoltativa" : status.info.enabled ? "Password attiva" : "Password non attiva");
