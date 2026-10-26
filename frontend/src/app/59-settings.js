/* ============================================================================
   59 · SETTINGS MENU
   The side menu behind the menu button of the top bar (like Mobileraker's): it slides in from the left and lists the
   groups of settings, each one a page of its own inside the menu.
     Stampante        the name and the logo of the top bar and of the browser tab: KlippEye, VzBot, Voron, RatRig (see 18-printer-brand.js)
     Camera           how the picture is shown (like the webcam page of Mainsail) and flipped
     Indirizzi        the addresses of the Raspberry at home and through ZeroTier, and which one the camera uses
     Z-offset         the step sizes of the Z-offset card
     Notifiche        which notifications the phone gets (done by the service on the Raspberry, see notifier/)
     Monitor IA       automatic pause / cancel, and how sure the AI must be before anything happens
     Soglie monitor   the limits the backend's camera watcher uses (kept by the backend, see 59a-detector-settings.js)
     Aggiornamenti    release installed, update / rollback / restart of KlippEye (see 59b-software-settings.js)
   What is stored and how is app/16-settings.js. Every change counts at once and is saved a moment later.
   ========================================================================== */

const SETTINGS_PAGES = ["printer", "camera", "network", "zoffset", "notifications", "ai", "detector", "software"];
const SETTINGS_TYPING_MS = 800; // a typed value is taken when the typing stops (and when the field is left or the menu closed)
const SWIPE_CLOSE_PX = 70; // a swipe to the left at least this long closes the menu
/** The notification service writes its sign of life this often; one not seen for longer than this is not running. */
const NOTIFIER_ALIVE_S = 360;

const ON_OFF = (value) => (value ? "sì" : "no");

/* ---------------------------------------------------------------------------
   State of the menu
   ------------------------------------------------------------------------- */
function useSettingsMenu() {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(null); // null: the list of groups
  const [question, setQuestion] = useState(null); // "reset" | "autoCancel" while a confirmation is open

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key !== "Escape") return;
      if (question) return setQuestion(null);
      if (page) setPage(null);
      else setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, page, question]);

  return {
    open,
    page,
    question,
    show: () => {
      setPage(null);
      setOpen(true);
      settingsStore.pull(); // another device may have changed something
    },
    close: () => setOpen(false),
    goTo: setPage,
    back: () => setPage(null),
    ask: setQuestion,
  };
}

/* ---------------------------------------------------------------------------
   Controls
   ------------------------------------------------------------------------- */

/** A line with a switch: the whole row is the button. */
function SwitchRow({ title, detail, checked, onChange, danger, disabled }) {
  return h(
    "button",
    {
      type: "button",
      role: "switch",
      "aria-checked": checked,
      disabled,
      className: cx("set-switch", checked && "is-on", danger && "set-switch--danger"),
      onClick: () => onChange(!checked),
    },
    h("span", { className: "set-switch__text" }, h("span", { className: "set-switch__title" }, title), detail && h("span", { className: "set-switch__detail" }, detail)),
    h("span", { className: "oui-switch" }, h("span", { className: "oui-switch__knob" })),
  );
}

/** One choice among several, as rows with a tick. */
function ChoiceRows({ options, value, onChange, label }) {
  return h(
    "div",
    { className: "oui-list", role: "radiogroup", "aria-label": label },
    options.map((option) =>
      h(
        "button",
        { key: option.id, type: "button", role: "radio", "aria-checked": option.id === value, className: cx("set-choice", option.id === value && "is-selected"), onClick: () => onChange(option.id) },
        h("span", { className: "set-switch__text" }, h("span", { className: "set-switch__title" }, option.label), option.detail && h("span", { className: "set-switch__detail" }, option.detail)),
        h("span", { className: "set-choice__tick", "aria-hidden": "true" }, option.id === value && h(Icons.Check, { size: 18 })),
      ),
    ),
  );
}

/** A few short choices side by side. */
function ChipChoice({ options, value, onChange, label }) {
  return h(
    "div",
    { className: "set-chips", role: "group", "aria-label": label },
    options.map((option) => h("button", { key: option.id, type: "button", className: cx("oui-chip", option.id === value && "is-selected"), "aria-pressed": option.id === value, onClick: () => onChange(option.id) }, option.label)),
  );
}

/**
 * A text field that takes what is typed once it is a valid value and the typing has stopped (not at every key: the
 * camera would reload at each step of "192.168.1.17"). `validate(text)` returns the cleaned value or null.
 * A value that is wrong when the field is left goes back to the last good one.
 */
function TextSetting({ label, value, validate, onCommit, hint, error, placeholder, inputMode, id }) {
  const [draft, setDraft] = useState(value);
  const [focused, setFocused] = useState(false);
  const pending = useRef(null); // the value waiting for the typing to stop
  const timer = useRef(0);
  const commitRef = useRef(null);
  commitRef.current = (text) => {
    const clean = validate(text);
    if (clean !== null && clean !== value) onCommit(clean);
  };

  useEffect(() => {
    if (!focused) setDraft(value);
  }, [value, focused]);
  useEffect(
    () => () => {
      if (pending.current !== null) commitRef.current(pending.current); // the menu closed while typing
    },
    [],
  );

  const flush = () => {
    clearTimeout(timer.current);
    if (pending.current !== null) {
      const text = pending.current;
      pending.current = null;
      commitRef.current(text);
    }
  };
  const change = (text) => {
    setDraft(text);
    pending.current = text;
    clearTimeout(timer.current);
    timer.current = setTimeout(flush, SETTINGS_TYPING_MS);
  };
  const invalid = validate(draft) === null;
  return h(
    "label",
    { className: "set-field" },
    h("span", { className: "set-field__label" }, label),
    h("input", {
      id,
      className: cx("oui-field", "set-field__input", invalid && "is-invalid"),
      value: draft,
      placeholder,
      inputMode: inputMode || "text",
      autoCapitalize: "off",
      autoCorrect: "off",
      spellCheck: false,
      "aria-invalid": invalid,
      onChange: (event) => change(event.target.value),
      onFocus: () => setFocused(true),
      onBlur: () => {
        flush();
        setFocused(false);
      },
      onKeyDown: (event) => event.key === "Enter" && event.currentTarget.blur(),
    }),
    invalid && error ? h("span", { className: "set-field__error", role: "alert" }, error) : hint && h("span", { className: "set-field__hint" }, hint),
  );
}

const SettingsGroup = ({ title, children, note }) => h("section", { className: "set-group" }, title && h("div", { className: "set-group__label" }, title), children, note && h("p", { className: "set-group__note" }, note));

/* ---------------------------------------------------------------------------
   Pages
   ------------------------------------------------------------------------- */

/** What the service on the Raspberry says about itself, as one line. */
function ServiceLine({ status }) {
  const now = Date.now() / 1000;
  if (status === undefined) return h("div", { className: "set-status" }, h("span", { className: "set-status__dot" }), "Controllo il servizio sul Raspberry…");
  if (status === null) {
    return h(
      "div",
      { className: "set-status set-status--warn" },
      h("span", { className: "set-status__dot" }),
      h("span", null, "Il servizio delle notifiche non si è ancora fatto vivo. Se lo hai installato, controlla con ", h("code", null, "klippeye status"), " e riavvialo da Impostazioni → Aggiornamenti; se non lo hai ancora configurato, segui la guida (", h("code", null, "docs/GUIDA.md"), "): senza, queste scelte non hanno effetto."),
    );
  }
  const age = Math.max(0, now - (Number(status.seen) || 0));
  const alive = age < NOTIFIER_ALIVE_S;
  const when = age < 90 ? "poco fa" : age < 5400 ? Math.round(age / 60) + " min fa" : Math.round(age / 3600) + " ore fa";
  return h(
    "div",
    { className: cx("set-status", alive ? "set-status--ok" : "set-status--warn") },
    h("span", { className: "set-status__dot" }),
    alive ? "Servizio attivo • versione " + (status.version || "?") + " • visto " + when : "Il servizio non risponde da " + when + ": riavvialo da Impostazioni → Aggiornamenti, oppure controlla con  klippeye status",
  );
}

const ACTION_TEXT = { pause: "messa in pausa", cancel: "interrotta" };
/** "Ultima azione automatica: stampa messa in pausa (14:03)" from the service's report, or "". */
function lastActionText(status) {
  const last = status && status.lastAction;
  if (!isPlainObject(last) || !ACTION_TEXT[last.kind]) return "";
  const when = last.at ? new Date(Number(last.at) * 1000).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
  return "Ultima azione automatica: stampa " + ACTION_TEXT[last.kind] + (last.ok === false ? " (non riuscita)" : "") + (when ? " • " + when : "");
}

/* ---- Printer ---- */
/** How the top bar and the tab will look: the logo (when there is one) and the name. */
function PrinterPreview({ printer }) {
  return h(
    "div",
    { className: "set-brand-preview", "aria-label": "Anteprima della barra in alto" },
    h(PrinterLogo, { id: printer.brand, className: "app-header__logo" }),
    isKlippEyeWordmark(printer) ? h("span", { className: "app-header__name" }, "Klipp", h("span", { className: "app-header__eye" }, "Eye")) : h("span", { className: "app-header__name" }, printerName(printer)),
  );
}

function PrinterPage() {
  const { settings, update } = useSettings();
  const logos = usePrinterLogos();
  const printer = settings.printer;
  const brand = printerBrand(printer.brand);
  useEffect(() => {
    loadLogoFiles(true); // a logo file added to the repository since the page opened
  }, []);
  return h(
    React.Fragment,
    null,
    h(SettingsGroup, { title: "Anteprima", note: "Così appaiono la barra in alto e la scheda del browser (titolo: " + printerName(printer) + ")." }, h(PrinterPreview, { printer })),
    h(
      SettingsGroup,
      { title: "Logo" },
      h(
        "div",
        { className: "oui-list", role: "radiogroup", "aria-label": "Logo" },
        PRINTER_BRANDS.map((item) =>
          h(
            "button",
            { key: item.id, type: "button", role: "radio", "data-brand": item.id, "aria-checked": item.id === printer.brand, className: cx("set-choice", item.id === printer.brand && "is-selected"), onClick: () => update((draft) => (draft.printer.brand = item.id)) },
            h("span", { className: "set-brand__logo" }, logos[item.id] ? h("img", { src: logos[item.id], alt: "" }) : h("span", { className: "set-brand__none", "aria-hidden": "true" }, "—")),
            h("span", { className: "set-switch__text" }, h("span", { className: "set-switch__title" }, item.label), h("span", { className: "set-switch__detail" }, logos[item.id] ? item.detail : "Logo non ancora caricato: si mostra solo il nome (vedi logos/README.md)")),
            h("span", { className: "set-choice__tick", "aria-hidden": "true" }, item.id === printer.brand && h(Icons.Check, { size: 18 })),
          ),
        ),
      ),
    ),
    h(
      SettingsGroup,
      { title: "Nome" },
      h(TextSetting, {
        key: printer.brand,
        label: "Nome della stampante",
        value: printer.name,
        validate: cleanPrinterName,
        placeholder: brand.label,
        error: "Al massimo " + PRINTER_NAME_MAX + " caratteri: lettere, numeri, spazio e . _ - '",
        hint: "Compare nella barra in alto e nella scheda del browser. Lascialo vuoto per usare «" + brand.label + "» (esempio: " + brand.label + ".287).",
        onCommit: (value) => update((draft) => (draft.printer.name = value)),
      }),
    ),
  );
}

/* ---- Camera ---- */
const MAINSAIL_SERVICES = { mjpegstreamer: "mjpeg", "uv4l-mjpeg": "mjpeg", ipstream: "mjpeg", "mjpegstreamer-adaptive": "adaptive", "webrtc-camerastreamer": "webrtc", iframe: "iframe" };

/** The webcams configured in Mainsail (Moonraker keeps them), as [{ name, service, method, address, flipH, flipV, fps }]; `method` is "" when this dashboard cannot show that kind. */
async function loadMainsailWebcams() {
  const json = await fetchJson("/server/webcams/list", { timeout: SETTINGS_DB_TIMEOUT_MS });
  const list = json && json.result && Array.isArray(json.result.webcams) ? json.result.webcams : [];
  return list
    .filter((cam) => isPlainObject(cam) && cam.enabled !== false)
    .map((cam) => {
      const method = MAINSAIL_SERVICES[String(cam.service || "").toLowerCase()] || "";
      const address = cleanCameraAddress(method === "adaptive" ? cam.snapshot_url || cam.stream_url : cam.stream_url);
      return { name: String(cam.name || "Camera"), service: String(cam.service || ""), method: address ? method : "", address, flipH: cam.flip_horizontal === true, flipV: cam.flip_vertical === true, fps: Number(cam.target_fps) || 0 };
    });
}

function MainsailImport({ onPick }) {
  const [state, setState] = useState({ phase: "idle", cams: [], message: "" });
  const load = async () => {
    setState({ phase: "loading", cams: [], message: "" });
    try {
      const cams = await loadMainsailWebcams();
      setState(cams.length ? { phase: "list", cams, message: "" } : { phase: "none", cams: [], message: "Mainsail non ha camere configurate." });
    } catch (error) {
      setState({ phase: "none", cams: [], message: "Non riesco a leggere le camere di Mainsail." });
    }
  };
  return h(
    SettingsGroup,
    { title: "Da Mainsail", note: "Prende metodo e indirizzo dalle camere già impostate nella pagina Webcam di Mainsail." },
    state.phase === "list"
      ? h(
          "div",
          { className: "oui-list" },
          state.cams.map((cam, index) =>
            h(
              "button",
              { key: index, type: "button", className: "set-choice", disabled: !cam.method, onClick: () => onPick(cam) },
              h("span", { className: "set-switch__text" }, h("span", { className: "set-switch__title" }, cam.name), h("span", { className: "set-switch__detail" }, cam.method ? cam.service + " • " + cam.address : cam.service + " • non supportato qui")),
            ),
          ),
        )
      : h("button", { type: "button", className: "oui-btn oui-btn--block", disabled: state.phase === "loading", onClick: load }, h(Icons.Download, { size: 18 }), state.phase === "loading" ? "Leggo…" : "Importa da Mainsail"),
    state.message && h("p", { className: "set-group__note set-group__note--warn", role: "status" }, state.message),
  );
}

function CameraPage() {
  const { settings, update } = useSettings();
  const camera = settings.camera;
  const method = CAMERA_METHODS.find((item) => item.id === camera.method);
  const address = camera.urls[camera.method];
  const isDefault = address === SETTINGS_DEFAULTS.camera.urls[camera.method];
  const pick = (cam) =>
    update((draft) => {
      draft.camera.method = cam.method;
      draft.camera.urls[cam.method] = cam.address;
      draft.camera.flipH = cam.flipH;
      draft.camera.flipV = cam.flipV;
      if (cam.method === "adaptive" && cam.fps) draft.camera.fps = cam.fps;
    });
  return h(
    React.Fragment,
    null,
    h(SettingsGroup, { title: "Metodo" }, h(ChoiceRows, { label: "Metodo", options: CAMERA_METHODS, value: camera.method, onChange: (id) => update((draft) => (draft.camera.method = id)) })),
    h(
      SettingsGroup,
      { title: "Indirizzo" },
      h(TextSetting, {
        key: camera.method,
        label: method.field,
        value: address,
        validate: cleanCameraAddress,
        error: "Scrivi un percorso che inizia con / (come /webcam/webrtc) o un indirizzo completo http://…",
        hint: "Un percorso sulla stampante (/webcam/…) o un indirizzo completo http://…",
        inputMode: "url",
        onCommit: (value) => update((draft) => (draft.camera.urls[camera.method] = value)),
      }),
      !isDefault && h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm set-inline-btn", onClick: () => update((draft) => (draft.camera.urls[camera.method] = SETTINGS_DEFAULTS.camera.urls[camera.method])) }, h(Icons.RotateCcw, { size: 16 }), "Ripristina l'indirizzo predefinito"),
    ),
    camera.method === "adaptive" &&
      h(
        SettingsGroup,
        { title: "Foto al secondo", note: "Più foto al secondo = più fluido, ma più traffico. Con una rete lenta 2–5 bastano." },
        h(
          "div",
          { className: "set-stepper" },
          h("button", { type: "button", className: "oui-btn", "aria-label": "Meno foto", disabled: camera.fps <= CAMERA_FPS_MIN, onClick: () => update((draft) => (draft.camera.fps -= 1)) }, "−"),
          h("div", { className: "set-stepper__value" }, camera.fps, h("span", null, " foto/s")),
          h("button", { type: "button", className: "oui-btn", "aria-label": "Più foto", disabled: camera.fps >= CAMERA_FPS_MAX, onClick: () => update((draft) => (draft.camera.fps += 1)) }, "+"),
        ),
      ),
    h(
      SettingsGroup,
      { title: "Immagine" },
      h(
        "div",
        { className: "oui-list" },
        h(SwitchRow, { title: "Specchia (orizzontale)", detail: "Destra e sinistra scambiate", checked: camera.flipH, onChange: (value) => update((draft) => (draft.camera.flipH = value)) }),
        h(SwitchRow, { title: "Capovolgi (verticale)", detail: "Sopra e sotto scambiati", checked: camera.flipV, onChange: (value) => update((draft) => (draft.camera.flipV = value)) }),
      ),
    ),
    h(MainsailImport, { onPick: pick }),
    h(
      SettingsGroup,
      null,
      h("button", { type: "button", className: "oui-btn oui-btn--block", onClick: requestCameraReload }, h(Icons.Refresh, { size: 18 }), "Ricarica la camera"),
    ),
  );
}

/* ---- Addresses ---- */
const APP_ADDRESSES_NOTES = {
  browser: "L'app Android (versione mk218 o più nuova) si collega a questi stessi indirizzi: ogni modifica vale dal suo prossimo avvio.",
  old: "Questa versione dell'app ha gli indirizzi scritti dentro: con la mk218 (o più nuova) li prende da qui.",
  refused: "L'app non ha accettato questi indirizzi: servono indirizzi di una rete privata (192.168.x.x, 10.x.x.x, 172.16-31.x.x, ZeroTier). Si userà l'ultima coppia accettata.",
  ok: "L'app Android userà questi indirizzi al prossimo avvio.",
  waiting: "L'app Android usa gli indirizzi che il Raspberry ha salvato: li riceve appena sono noti.",
};

/** What the Android app does with the addresses above (app/16-settings.js tells it about them). */
function AppAddressesNote({ state }) {
  const note = APP_ADDRESSES_NOTES[state] || APP_ADDRESSES_NOTES.browser;
  if (state === "ok") return h("div", { className: "set-status set-status--ok" }, h("span", { className: "set-status__dot" }), note);
  return h("p", { className: cx("set-group__note", (state === "old" || state === "refused") && "set-group__note--warn") }, note);
}

function NetworkPage() {
  const { settings, update } = useSettings();
  const { localIp, externalIp, route } = settings.network;
  const using = pickCameraHost(settings);
  const routes = [
    { id: "auto", label: "Automatico", detail: "Quello della rete da cui hai aperto la dashboard" },
    { id: "local", label: "Sempre locale", detail: localIp },
    { id: "external", label: "Sempre esterno", detail: externalIp },
  ];
  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      { title: "Indirizzi del Raspberry", note: "Solo l'indirizzo, senza http:// e senza porta (a meno che la camera non stia su una porta diversa dalla 80)." },
      h(TextSetting, {
        label: "IP locale (rete di casa)",
        value: localIp,
        validate: cleanHost,
        error: "Non è un indirizzo valido (esempio: 192.168.1.17)",
        placeholder: SETTINGS_DEFAULTS.network.localIp,
        inputMode: "decimal",
        onCommit: (value) => update((draft) => (draft.network.localIp = value)),
      }),
      h(TextSetting, {
        label: "IP esterno (ZeroTier, VPN)",
        value: externalIp,
        validate: cleanHost,
        error: "Non è un indirizzo valido (esempio: 172.25.170.177)",
        placeholder: SETTINGS_DEFAULTS.network.externalIp,
        inputMode: "decimal",
        onCommit: (value) => update((draft) => (draft.network.externalIp = value)),
      }),
    ),
    h(SettingsGroup, { title: "Per la camera usa" }, h(ChoiceRows, { label: "Indirizzo della camera", options: routes, value: route, onChange: (id) => update((draft) => (draft.network.route = id)) })),
    h("div", { className: "set-status set-status--ok" }, h("span", { className: "set-status__dot" }), "Ora la camera usa l'indirizzo " + (using.side === "local" ? "locale " : "esterno ") + using.host),
    h(AppAddressesNote, { state: appAddressesState(settings) }),
  );
}

/* ---- Z-offset ---- */
const parseStepText = (text) => {
  const number = Number(String(text).trim().replace(",", "."));
  return text.trim() !== "" && Number.isFinite(number) && number >= Z_STEP_MIN && number <= Z_STEP_MAX ? Math.round(number * 1000) / 1000 : null;
};

function ZOffsetPage() {
  const { settings, update } = useSettings();
  const steps = settings.zOffset.steps;
  const pad = (list) => Array.from({ length: Z_STEP_SLOTS }, (unused, index) => (index < list.length ? String(list[index]) : ""));
  const [slots, setSlots] = useState(() => pad(steps));
  const parsed = slots.filter((text) => text.trim() !== "").map(parseStepText);
  const problem = parsed.length === 0 ? "Scrivi almeno un valore." : parsed.includes(null) ? "Ogni valore va da 0,001 a 1 mm." : new Set(parsed).size !== parsed.length ? "Due valori sono uguali." : "";
  const timer = useRef(0);

  // another device changed the steps: take them (our own change, sorted, must not shuffle the fields while typing)
  const ours = problem ? null : cleanZSteps(parsed).join("|");
  const theirs = steps.join("|");
  useEffect(() => {
    if (ours !== theirs) setSlots(pad(steps));
  }, [theirs]);

  const edit = (index, text) => {
    const next = slots.slice();
    next[index] = text;
    setSlots(next);
    const values = next.filter((item) => item.trim() !== "").map(parseStepText);
    clearTimeout(timer.current);
    if (values.length && !values.includes(null) && new Set(values).size === values.length) timer.current = setTimeout(() => update((draft) => (draft.zOffset.steps = values)), SETTINGS_TYPING_MS);
  };
  useEffect(() => () => clearTimeout(timer.current), []);
  const isDefault = steps.join("|") === SETTINGS_DEFAULTS.zOffset.steps.join("|");
  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      { title: "Passi della card Z-offset", note: "Di quanti millimetri si muove l'ugello a ogni tocco di Alza / Abbassa. Lascia vuoto un campo per averne meno di quattro." },
      h(
        "div",
        { className: "set-grid" },
        slots.map((text, index) =>
          h(
            "label",
            { key: index, className: "set-field" },
            h("span", { className: "set-field__label" }, "Passo " + (index + 1)),
            h("input", {
              className: cx("oui-field", "oui-field--num", "set-field__input", text.trim() !== "" && parseStepText(text) === null && "is-invalid"),
              value: text,
              inputMode: "decimal",
              placeholder: "—",
              autoCapitalize: "off",
              autoCorrect: "off",
              spellCheck: false,
              onChange: (event) => edit(index, event.target.value),
              onBlur: () => {
                clearTimeout(timer.current);
                if (!problem) {
                  update((draft) => (draft.zOffset.steps = parsed));
                  setSlots(pad(cleanZSteps(parsed)));
                } else setSlots(pad(steps));
              },
              onKeyDown: (event) => event.key === "Enter" && event.currentTarget.blur(),
            }),
          ),
        ),
      ),
      problem && h("p", { className: "set-field__error", role: "alert" }, problem),
    ),
    h(
      SettingsGroup,
      { title: "Così appaiono nella card" },
      h("div", { className: "set-preview" }, steps.map((value) => h("span", { key: value, className: "oui-chip" }, value))),
      !isDefault && h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm set-inline-btn", onClick: () => update((draft) => (draft.zOffset.steps = SETTINGS_DEFAULTS.zOffset.steps.slice())) }, h(Icons.RotateCcw, { size: 16 }), "Ripristina 0,01 · 0,025 · 0,05 · 0,1"),
    ),
  );
}

/* ---- Notifications ---- */
function NotificationsPage({ active }) {
  const { settings, update } = useSettings();
  const status = useNotifierStatus(active);
  return h(
    React.Fragment,
    null,
    h(ServiceLine, { status }),
    h(
      SettingsGroup,
      { title: "Quali notifiche ricevere", note: "Valgono per tutti i telefoni con l'app. Il testo è quello della notifica." },
      h(
        "div",
        { className: "oui-list" },
        NOTIFICATION_KINDS.map((kind) =>
          h(SwitchRow, { key: kind.id, title: kind.title, detail: kind.text, checked: settings.notifications[kind.id], onChange: (value) => update((draft) => (draft.notifications[kind.id] = value)) }),
        ),
      ),
    ),
  );
}

/* ---- AI monitor ---- */
const CONFIRMATION_OPTIONS = AI_CONFIRMATIONS.map((value) => ({ id: value, label: value === 1 ? "1 controllo" : value + " di fila" }));
const CONFIDENCE_OPTIONS = AI_CONFIDENCES.map((value) => ({ id: value, label: value === 0 ? "Qualsiasi" : value + "%" }));

function AiPage({ active, menu }) {
  const { settings, update } = useSettings();
  const status = useNotifierStatus(active);
  const ai = settings.ai;
  const last = lastActionText(status);
  return h(
    React.Fragment,
    null,
    h(ServiceLine, { status }),
    h(
      SettingsGroup,
      { title: "Azioni automatiche", note: "Le esegue il Raspberry da solo, anche a telefono spento. L'IA può sbagliare: la cancellazione non si può annullare." },
      h(
        "div",
        { className: "oui-list" },
        h(SwitchRow, { title: "Metti in pausa da solo", detail: "Quando l'IA consiglia PAUSA (o CANCELLA, se la cancellazione automatica è spenta)", checked: ai.autoPause, onChange: (value) => update((draft) => (draft.ai.autoPause = value)) }),
        h(SwitchRow, { title: "Cancella da solo", detail: "Quando l'IA consiglia CANCELLA. La stampa interrotta non si recupera", danger: true, checked: ai.autoCancel, onChange: (value) => (value ? menu.ask("autoCancel") : update((draft) => (draft.ai.autoCancel = false))) }),
      ),
      last && h("p", { className: "set-group__note" }, last),
    ),
    h(
      SettingsGroup,
      { title: "Controlli di fila", note: "Quante analisi consecutive devono segnalare un problema prima di avvisarti o agire. Più alto = meno falsi allarmi, ma più lento." },
      h(ChipChoice, { label: "Controlli di fila", options: CONFIRMATION_OPTIONS, value: ai.confirmations, onChange: (id) => update((draft) => (draft.ai.confirmations = id)) }),
    ),
    h(
      SettingsGroup,
      { title: "Sicurezza minima dell'IA", note: "Un difetto con una percentuale più bassa di questa viene ignorato." },
      h(ChipChoice, { label: "Sicurezza minima", options: CONFIDENCE_OPTIONS, value: ai.minConfidence, onChange: (id) => update((draft) => (draft.ai.minConfidence = id)) }),
    ),
    h(
      SettingsGroup,
      { title: "Sensibilità della camera", note: "Quanto movimento ai bordi fa chiamare l'IA, l'area controllata, le pause: le soglie sono nel backend e si cambiano da qui." },
      h(
        "div",
        { className: "oui-list" },
        h(
          "button",
          { type: "button", className: "set-entry", "data-page": "detector", onClick: () => menu.goTo("detector") },
          h("span", { className: "oui-row__icon oui-row__icon--accent" }, h(Icons.Sliders)),
          h("span", { className: "oui-row__text" }, h("span", { className: "oui-row__name" }, "Soglie del monitor"), h("span", { className: "oui-row__meta set-entry__meta" }, "Soglia di cambiamento, area, pause, modello")),
          h("span", { className: "set-entry__go", "aria-hidden": "true" }, h(Icons.Forward)),
        ),
      ),
    ),
    h(
      SettingsGroup,
      { title: "Difetti da considerare", note: "Quelli spenti non fanno scattare né avvisi né azioni. Il backend decide da solo quando analizzare: qui si sceglie solo cosa farne." },
      h(
        "div",
        { className: "oui-list" },
        AI_DEFECTS.map((defect) => h(SwitchRow, { key: defect.id, title: defect.title, detail: defect.detail, checked: ai.defects[defect.id], onChange: (value) => update((draft) => (draft.ai.defects[defect.id] = value)) })),
      ),
    ),
  );
}

/* ---------------------------------------------------------------------------
   The menu
   ------------------------------------------------------------------------- */
const SYNC_TEXT = {
  loading: "Controllo il Raspberry…",
  saving: "Salvataggio sul Raspberry…",
  shared: "Salvate sul Raspberry: valgono su tutti i dispositivi",
  local: "Solo su questo dispositivo",
};

function SyncLine({ sync }) {
  return h(
    "div",
    { className: cx("set-status", sync.state === "shared" && "set-status--ok", sync.state === "local" && "set-status--warn") },
    h("span", { className: "set-status__dot" }),
    h("span", null, SYNC_TEXT[sync.state], sync.state === "local" && h("span", { className: "set-status__detail" }, " Il Raspberry non ha accettato il salvataggio" + (sync.detail ? " (" + sync.detail + ")" : "") + ": le impostazioni restano in questo browser e le notifiche automatiche non le vedono.")),
  );
}

function settingsSummary(page, settings, brain) {
  const { camera, network, zOffset, notifications, ai } = settings;
  switch (page) {
    case "detector":
      return detectorSummary(brain.version);
    case "access":
      return accessSummary(brain.access);
    case "software":
      return softwareSummary(brain.version, brain.update, appUpdateWaiting(brain.app, readInstalledApp()));
    case "printer":
      return printerBrand(settings.printer.brand).label + (settings.printer.name ? " • " + settings.printer.name : "");
    case "camera":
      return CAMERA_METHODS.find((method) => method.id === camera.method).label + (camera.flipH || camera.flipV ? " • capovolta" : "");
    case "network":
      return network.localIp + " • " + network.externalIp;
    case "zoffset":
      return zOffset.steps.join(" · ") + " mm";
    case "notifications":
      return NOTIFICATION_KINDS.filter((kind) => notifications[kind.id]).length + " su " + NOTIFICATION_KINDS.length + " attive";
    default:
      return "Pausa da sola: " + ON_OFF(ai.autoPause) + " • Cancella da sola: " + ON_OFF(ai.autoCancel);
  }
}

const SETTINGS_ENTRIES = [
  { id: "printer", title: "Stampante", icon: Icons.Cube },
  { id: "camera", title: "Camera", icon: Icons.Camera },
  { id: "network", title: "Indirizzi", icon: Icons.Network },
  { id: "zoffset", title: "Z-offset", icon: Icons.Layers },
  { id: "notifications", title: "Notifiche", icon: Icons.Bell },
  { id: "ai", title: "Monitor IA", icon: Icons.Sparkle },
  { id: "detector", title: "Soglie del monitor", icon: Icons.Sliders },
  { id: "access", title: "Accesso", icon: Icons.Lock },
  { id: "software", title: "Aggiornamenti", icon: Icons.Download },
];
const PAGE_TITLES = Object.fromEntries(SETTINGS_ENTRIES.map((entry) => [entry.id, entry.title]));

function SettingsHome({ menu }) {
  const { settings, sync } = useSettings();
  const brain = { version: useBrainVersion(true), update: useProgramUpdate(true), app: useAppRelease(true), access: useAccessStatus(true)[0] };
  return h(
    React.Fragment,
    null,
    h(
      "div",
      { className: "oui-list" },
      SETTINGS_ENTRIES.map((entry) =>
        h(
          "button",
          { key: entry.id, type: "button", className: "set-entry", "data-page": entry.id, onClick: () => menu.goTo(entry.id) },
          h("span", { className: "oui-row__icon oui-row__icon--accent" }, h(entry.icon)),
          h("span", { className: "oui-row__text" }, h("span", { className: "oui-row__name" }, entry.title), h("span", { className: "oui-row__meta set-entry__meta" }, settingsSummary(entry.id, settings, brain))),
          entry.id === "software" && ((brain.version.state === "ok" && brain.version.info.legacy === true) || (brain.update.phase === "ok" && Number(brain.update.raw.commits_behind_count) > 0) || appUpdateWaiting(brain.app, readInstalledApp())) && h("span", { className: "set-entry__badge" }, "Nuovo"),
          h("span", { className: "set-entry__go", "aria-hidden": "true" }, h(Icons.Forward)),
        ),
      ),
    ),
    h(SyncLine, { sync }),
    h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--block set-reset", onClick: () => menu.ask("reset") }, h(Icons.RotateCcw, { size: 18 }), "Ripristina i valori iniziali"),
  );
}

function SettingsDrawer({ menu, updates, printing, actions }) {
  useBodyScrollLock(true);
  const { settings } = useSettings();
  const { page } = menu;
  const touch = useRef(null);
  const onTouchStart = (event) => {
    const point = event.touches[0];
    touch.current = { x: point.clientX, y: point.clientY };
  };
  const onTouchEnd = (event) => {
    const start = touch.current;
    touch.current = null;
    if (!start) return;
    const point = event.changedTouches[0];
    const dx = point.clientX - start.x;
    if (dx < -SWIPE_CLOSE_PX && Math.abs(dx) > Math.abs(point.clientY - start.y) * 1.5) menu.close();
  };
  let body;
  if (page === "printer") body = h(PrinterPage);
  else if (page === "camera") body = h(CameraPage);
  else if (page === "network") body = h(NetworkPage);
  else if (page === "zoffset") body = h(ZOffsetPage);
  else if (page === "notifications") body = h(NotificationsPage, { active: true });
  else if (page === "ai") body = h(AiPage, { active: true, menu });
  else if (page === "detector") body = h(DetectorPage, { active: true });
  else if (page === "access") body = h(AccessPage, { active: true });
  else if (page === "software") body = h(SoftwarePage, { active: true, menu, updates, printing, actions });
  else body = h(SettingsHome, { menu });
  return h(
    "div",
    { className: "drawer-overlay", onClick: (event) => event.target === event.currentTarget && menu.close() },
    h(
      "aside",
      { className: "drawer", role: "dialog", "aria-modal": "true", "aria-label": "Impostazioni", onTouchStart, onTouchEnd },
      h(
        "div",
        { className: "drawer__head" },
        page
          ? h("button", { type: "button", className: "header-btn drawer__btn", "aria-label": "Indietro", onClick: menu.back }, h(Icons.Back))
          : h(PrinterLogo, { id: settings.printer.brand, className: "drawer__logo" }),
        h("div", { className: "drawer__title" }, page ? PAGE_TITLES[page] : "Impostazioni"),
        h("button", { type: "button", className: "header-btn drawer__btn", "aria-label": "Chiudi", onClick: menu.close }, h(Icons.Close)),
      ),
      h("div", { className: "drawer__body", key: page || "home" }, body),
    ),
  );
}

/** The menu and its two questions (kept outside the menu: a layer inside it would be cut by its blur). */
function SettingsMenuLayer({ menu, updates, printing, actions }) {
  const { update, reset } = useSettings();
  return h(
    React.Fragment,
    null,
    h(Presence, null, menu.open && h(SettingsDrawer, { menu, updates, printing, actions })),
    h(ConfirmDialog, {
      open: menu.question === "reset",
      tone: "danger",
      icon: h(Icons.RotateCcw),
      title: "Ripristinare le impostazioni?",
      subtitle: "Camera, indirizzi, passi Z-offset, notifiche, monitor IA",
      message: "Tutte le impostazioni tornano ai valori iniziali, su tutti i dispositivi. Confermi?",
      confirmLabel: "Ripristina",
      onConfirm: () => {
        menu.ask(null);
        reset();
      },
      onCancel: () => menu.ask(null),
    }),
    h(ConfirmDialog, {
      open: menu.question === "autoCancel",
      tone: "danger",
      icon: h(Icons.Warning),
      title: "Cancellare le stampe da solo?",
      subtitle: "Azione automatica del monitor IA",
      message: "Se l'IA consiglia CANCELLA, il Raspberry interrompe la stampa subito. L'IA può sbagliare e una stampa cancellata non si recupera. Attivarlo?",
      confirmLabel: "Attiva",
      onConfirm: () => {
        menu.ask(null);
        update((draft) => (draft.ai.autoCancel = true));
      },
      onCancel: () => menu.ask(null),
    }),
  );
}
