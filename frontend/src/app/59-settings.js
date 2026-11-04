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
     Calibra camera   where the printer appears in the camera picture, for the monitor (see 59f-camera-calibration.js)
     Registrazioni    the recorded prints, the alarms to mark and the measurement of the monitor (see 59e-recordings.js)
     Aggiornamenti    release installed, update / rollback / restart of KlippEye (see 59b-software-settings.js)
   What is stored and how is app/16-settings.js. Every change counts at once and is saved a moment later.
   ========================================================================== */

const SETTINGS_TYPING_MS = 800; // a typed value is taken when the typing stops (and when the field is left or the menu closed)
// a swipe to the left closes the menu: at least this long, mostly sideways, quick, and never started on a control
// (1.24: it was too easy to close it while moving a slider or scrolling)
const SWIPE_CLOSE_PX = 110;
const SWIPE_CLOSE_MAX_MS = 600;
const SWIPE_IGNORE = "input, textarea, select, .set-num, .cal-frame, .cal-loupe, .set-snapshot, .rec-viewer, [data-no-swipe]";
/** The notification service writes its sign of life this often; one not seen for longer than this is not running. */
const NOTIFIER_ALIVE_S = 360;

const ON_OFF = (value) => (value ? tx("yes") : tx("no"));

/* ---------------------------------------------------------------------------
   State of the menu
   ------------------------------------------------------------------------- */
function useSettingsMenu() {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(null); // null: the list of groups
  const [question, setQuestion] = useState(null); // "reset" | "autoCancel" while a confirmation is open
  // the pages that led here (1.24): "back" returns to the page it came from (Camera -> Camera calibration -> back = Camera),
  // not to the parent or to the start
  const history = useRef([]);

  const goTo = (next) => {
    if (next !== page) history.current.push(page);
    setPage(next);
  };
  const back = () => setPage(history.current.length ? history.current.pop() : PAGE_PARENT[page] || (page && page.startsWith("webcam:") ? "camera" : null));
  const close = () => {
    history.current = [];
    setOpen(false);
  };

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key !== "Escape" || document.querySelector(".help-overlay")) return;
      goBack(); // 1.26.1: the same "back" as the phone's (a page may have a level of its own, e.g. one recording)
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, page, question]);

  // the phone's back button (KlippEye app): the confirmation, then the page before, then the menu itself
  useBackHandler(() => {
    if (question) setQuestion(null);
    else if (page) back();
    else close();
    return true;
  }, open);

  return {
    open,
    page,
    question,
    show: () => {
      history.current = [];
      setPage(null);
      setOpen(true);
      settingsStore.pull(); // another device may have changed something
    },
    close,
    /** The guided set-up (59k) takes the place of the menu. */
    startSetup: () => {
      close();
      openSetupGuide();
    },
    /** Opens the menu straight on one page (the invitation to set up the notifications of this phone). */
    openPage: (id) => {
      history.current = [];
      setPage(id);
      setOpen(true);
    },
    goTo,
    back,
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

/** A group of a settings page; `help` ([page, section]) puts a small "?" next to its title that opens the guide there (59j). */
const SettingsGroup = ({ title, children, note, help }) =>
  h(
    "section",
    { className: "set-group" },
    title && h("div", { className: cx("set-group__label", help && "set-group__label--help") }, h("span", null, title), help && h(HelpButton, { page: help[0], section: help[1], className: "help-btn--small" })),
    children,
    note && h("p", { className: "set-group__note" }, note),
  );

/* ---------------------------------------------------------------------------
   Pages
   ------------------------------------------------------------------------- */

/** What the service on the Raspberry says about itself, as one line. */
function ServiceLine({ status, installCommand }) {
  const now = Date.now() / 1000;
  if (status === undefined) return h("div", { className: "set-status" }, h("span", { className: "set-status__dot" }), tx("Checking the service on the Raspberry…"));
  if (status === null) {
    return h(
      "div",
      { className: "set-status set-status--warn" },
      h("span", { className: "set-status__dot" }),
      h(
        "span",
        { "data-service": "missing" },
        tx("The notification service has not shown up yet. Run once on the Raspberry"),
        " ",
        h("code", null, installCommand || "bash ~/klippeye/scripts/install.sh"),
        " ",
        tx("(it installs it), then check with"),
        " ",
        h("code", null, "klippeye status"),
        ". ",
        tx("Without it these choices have no effect."),
      ),
    );
  }
  const age = Math.max(0, now - (Number(status.seen) || 0));
  const alive = age < NOTIFIER_ALIVE_S;
  const when = age < 90 ? tx("just now") : age < 5400 ? tx("{count} min ago", { count: Math.round(age / 60) }) : tx("{count} h ago", { count: Math.round(age / 3600) });
  return h(
    "div",
    { className: cx("set-status", alive ? "set-status--ok" : "set-status--warn") },
    h("span", { className: "set-status__dot" }),
    alive ? tx("Service running • version {version} • seen {when}", { version: status.version || "?", when }) : tx("The service does not answer (last seen {when}): restart it from Settings → Updates, or check with  klippeye status", { when }),
  );
}

const ACTION_TEXT = { pause: tx("Last automatic action: print paused"), cancel: tx("Last automatic action: print cancelled") };
/** "Ultima azione automatica: stampa messa in pausa (14:03)" from the service's report, or "". */
function lastActionText(status) {
  const last = status && status.lastAction;
  if (!isPlainObject(last) || !ACTION_TEXT[last.kind]) return "";
  const when = last.at ? new Date(Number(last.at) * 1000).toLocaleString(LOCALE, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
  return ACTION_TEXT[last.kind] + (last.ok === false ? tx(" (failed)") : "") + (when ? " • " + when : "");
}

/* ---- Printer ---- */
/** How the top bar and the tab will look: the logo (when there is one) and the name. */
function PrinterPreview({ printer }) {
  return h(
    "div",
    { className: "set-brand-preview", "aria-label": tx("Preview of the top bar") },
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
    h(SettingsGroup, { title: tx("Preview"), note: tx("This is how the top bar and the browser tab look (title: {title}).", { title: printerName(printer) }) }, h(PrinterPreview, { printer })),
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
            h("span", { className: "set-switch__text" }, h("span", { className: "set-switch__title" }, item.label), h("span", { className: "set-switch__detail" }, logos[item.id] ? item.detail : tx("Logo not uploaded yet: only the name is shown (see logos/README.md)"))),
            h("span", { className: "set-choice__tick", "aria-hidden": "true" }, item.id === printer.brand && h(Icons.Check, { size: 18 })),
          ),
        ),
      ),
    ),
    h(
      SettingsGroup,
      { title: tx("Name") },
      h(TextSetting, {
        key: printer.brand,
        label: tx("Printer name"),
        value: printer.name,
        validate: cleanPrinterName,
        placeholder: brand.label,
        error: tx("At most {max} characters: letters, digits, space and . _ - '", { max: PRINTER_NAME_MAX }),
        hint: tx("Shown in the top bar and in the browser tab. Leave it empty to use «{brand}» (example: {brand}.287).", { brand: brand.label }),
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
      return { name: String(cam.name || "Camera"), service: String(cam.service || ""), method: address ? method : "", address, snapshot: cleanCameraAddress(cam.snapshot_url) || "", flipH: cam.flip_horizontal === true, flipV: cam.flip_vertical === true, rotation: [90, 180, 270].includes(Number(cam.rotation)) ? Number(cam.rotation) : 0, fps: Number(cam.target_fps) || 0 };
    });
}

function MainsailImport({ onPick }) {
  const [state, setState] = useState({ phase: "idle", cams: [], message: "" });
  const load = async () => {
    setState({ phase: "loading", cams: [], message: "" });
    try {
      const cams = await loadMainsailWebcams();
      setState(cams.length ? { phase: "list", cams, message: "" } : { phase: "none", cams: [], message: tx("Mainsail has no cameras set up.") });
    } catch (error) {
      setState({ phase: "none", cams: [], message: tx("Cannot read Mainsail's cameras.") });
    }
  };
  return h(
    SettingsGroup,
    { title: tx("From Mainsail"), note: tx("Takes method and address from the cameras already set up in Mainsail's Webcam page.") },
    state.phase === "list"
      ? h(
          "div",
          { className: "oui-list" },
          state.cams.map((cam, index) =>
            h(
              "button",
              { key: index, type: "button", className: "set-choice", disabled: !cam.method, onClick: () => onPick(cam) },
              h("span", { className: "set-switch__text" }, h("span", { className: "set-switch__title" }, cam.name), h("span", { className: "set-switch__detail" }, cam.method ? cam.service + " • " + cam.address : cam.service + tx(" • not supported here"))),
            ),
          ),
        )
      : h("button", { type: "button", className: "oui-btn oui-btn--block", disabled: state.phase === "loading", onClick: load }, h(Icons.Download, { size: 18 }), state.phase === "loading" ? tx("Reading…") : tx("Import from Mainsail")),
    state.message && h("p", { className: "set-group__note set-group__note--warn", role: "status" }, state.message),
  );
}

/**
 * The camera's single photo (1.23): the AI monitor, the camera calibration and the recordings take it (later the timelapse
 * too). Automatic from the camera's address, or chosen like in Mainsail; "Try" shows the photo exactly as the Raspberry gets it.
 */
function SnapshotSetting({ camera, update }) {
  const automatic = defaultSnapshot(camera);
  const [trial, setTrial] = useState(null); // null | { phase: "loading" | "ok" | "error", src, text }
  const tryIt = async () => {
    const address = snapshotAddress(camera);
    setTrial({ phase: "loading" });
    try {
      const response = await fetchFresh("/api/camera/snapshot?url=" + encodeURIComponent(address), { timeout: 12000 });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        return setTrial({ phase: "error", text: data.error || "HTTP " + response.status });
      }
      const blob = await response.blob();
      setTrial({ phase: "ok", src: URL.createObjectURL(blob), text: response.headers.get("X-Snapshot-Url") || address });
    } catch (error) {
      setTrial({ phase: "error", text: tx("the KlippEye service does not answer") });
    }
  };
  useEffect(() => () => trial && trial.src && URL.revokeObjectURL(trial.src), [trial]);
  return h(
    SettingsGroup,
    { title: tx("Snapshot (single photo)"), help: ["camera", "snapshot"], note: tx("The photo the AI monitor and the camera calibration take (later also the timelapse). Empty: automatic, from the address above.") },
    h(TextSetting, {
      key: camera.method + "|" + (camera.urls[camera.method] || ""),
      label: tx("Snapshot address"),
      value: camera.snapshot,
      validate: (text) => (typeof text === "string" && text.trim() === "" ? "" : cleanCameraAddress(text)),
      error: tx("Write a path that starts with / (like /webcam/?action=snapshot) or a full address http://…"),
      placeholder: automatic,
      inputMode: "url",
      onCommit: (value) => update((draft) => (draft.camera.snapshot = value)),
    }),
    h("p", { className: "set-group__note", "data-snapshot-now": snapshotAddress(camera) }, camera.snapshot ? tx("In use: {address} (chosen)", { address: camera.snapshot }) : tx("In use: {address} (automatic)", { address: automatic })),
    h(
      "div",
      { className: "oui-btn-row" },
      h("button", { type: "button", className: "oui-btn oui-btn--sm", "data-snapshot-try": "1", disabled: trial && trial.phase === "loading", onClick: tryIt }, h(Icons.Camera, { size: 16 }), trial && trial.phase === "loading" ? tx("Taking the photo…") : tx("Try: take a photo")),
      camera.snapshot && h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--quiet", onClick: () => update((draft) => (draft.camera.snapshot = "")) }, h(Icons.RotateCcw, { size: 16 }), tx("Back to automatic")),
    ),
    trial && trial.phase === "ok" && h("img", { className: "set-snapshot", src: trial.src, alt: tx("The photo taken by the Raspberry"), "data-snapshot-ok": "1" }),
    trial && trial.phase === "ok" && h("div", { className: "set-status set-status--ok" }, h("span", { className: "set-status__dot" }), tx("The Raspberry gets the photo: the AI monitor will see this.")),
    trial && trial.phase === "error" && h("p", { className: "set-field__error", role: "alert", "data-snapshot-error": "1" }, tx("No photo: {error}", { error: trial.text })),
  );
}

/** The main camera (1.59: a page of Settings → Camera, which lists every camera; see 59p-cameras-settings.js). */
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
      draft.camera.snapshot = cam.snapshot; // Mainsail's own snapshot address ("" = automatic)
      draft.camera.flipH = cam.flipH;
      draft.camera.flipV = cam.flipV;
      if (cam.method === "adaptive" && cam.fps) draft.camera.fps = cam.fps;
    });
  return h(
    React.Fragment,
    null,
    h(SettingsGroup, { title: tx("Method"), help: ["camera", "method"] }, h(ChoiceRows, { label: tx("Method"), options: CAMERA_METHODS, value: camera.method, onChange: (id) => update((draft) => (draft.camera.method = id)) })),
    h(
      SettingsGroup,
      { title: tx("Address") },
      h(TextSetting, {
        key: camera.method,
        label: method.field,
        value: address,
        validate: cleanCameraAddress,
        error: tx("Write a path that starts with / (like /webcam/webrtc) or a full address http://…"),
        hint: tx("A path on the printer (/webcam/…) or a full address http://…"),
        inputMode: "url",
        onCommit: (value) => update((draft) => (draft.camera.urls[camera.method] = value)),
      }),
      !isDefault && h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm set-inline-btn", onClick: () => update((draft) => (draft.camera.urls[camera.method] = SETTINGS_DEFAULTS.camera.urls[camera.method])) }, h(Icons.RotateCcw, { size: 16 }), tx("Restore the default address")),
    ),
    camera.method === "adaptive" &&
      h(
        SettingsGroup,
        { title: tx("Frames per second"), note: tx("More frames per second = smoother, but more traffic. On a slow network 2–5 are enough.") },
        h(
          "div",
          { className: "set-stepper" },
          h("button", { type: "button", className: "oui-btn", "aria-label": tx("Fewer frames"), disabled: camera.fps <= CAMERA_FPS_MIN, onClick: () => update((draft) => (draft.camera.fps -= 1)) }, "−"),
          h("div", { className: "set-stepper__value" }, camera.fps, h("span", null, " foto/s")),
          h("button", { type: "button", className: "oui-btn", "aria-label": tx("More frames"), disabled: camera.fps >= CAMERA_FPS_MAX, onClick: () => update((draft) => (draft.camera.fps += 1)) }, "+"),
        ),
      ),
    h(
      SettingsGroup,
      { title: tx("Image") },
      h(
        "div",
        { className: "oui-list" },
        h(SwitchRow, { title: tx("Mirror (horizontal)"), detail: tx("Left and right swapped"), checked: camera.flipH, onChange: (value) => update((draft) => (draft.camera.flipH = value)) }),
        h(SwitchRow, { title: tx("Flip (vertical)"), detail: tx("Top and bottom swapped"), checked: camera.flipV, onChange: (value) => update((draft) => (draft.camera.flipV = value)) }),
      ),
    ),
    h(SnapshotSetting, { camera, update }),
    h(MainsailImport, { onPick: pick }),
  );
}

/* ---- Addresses ---- */
const cleanHostOrEmpty = (value) => (typeof value === "string" && value.trim() === "" ? "" : cleanHost(value));

const APP_ADDRESSES_NOTES = {
  browser: tx("The Android app (version mk218 or newer) connects to these same addresses: every change applies from its next start."),
  old: tx("This version of the app has the addresses built in: from mk218 (or newer) it takes them from here."),
  refused: tx("The app did not accept these addresses: they must be private network addresses (192.168.x.x, 10.x.x.x, 172.16-31.x.x, ZeroTier). The last accepted pair will be used."),
  ok: tx("The Android app will use these addresses at its next start."),
  waiting: tx("The Android app uses the addresses saved on the Raspberry: it gets them as soon as they are known."),
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
    { id: "auto", label: tx("Automatic"), detail: tx("The one of the network you opened the dashboard from") },
    { id: "local", label: tx("Always local"), detail: localIp || tx("not set: this address") },
    { id: "external", label: tx("Always external"), detail: externalIp || tx("not set: this address") },
  ];
  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      { title: tx("Addresses of the Raspberry"), help: ["network", "what"], note: tx("Only the address, without http:// and without port (unless the camera is on a port other than 80). Empty: the address you opened the dashboard at.") },
      h(TextSetting, {
        label: tx("Local IP (home network)"),
        value: localIp,
        validate: cleanHostOrEmpty,
        error: tx("Not a valid address (example: 192.168.1.17)"),
        placeholder: tx("example: 192.168.1.17"),
        inputMode: "decimal",
        onCommit: (value) => update((draft) => (draft.network.localIp = value)),
      }),
      h(TextSetting, {
        label: tx("External IP (ZeroTier, VPN)"),
        value: externalIp,
        validate: cleanHostOrEmpty,
        error: tx("Not a valid address (example: 172.25.170.177)"),
        placeholder: tx("only with ZeroTier, Tailscale or a VPN"),
        inputMode: "decimal",
        onCommit: (value) => update((draft) => (draft.network.externalIp = value)),
      }),
    ),
    h(SettingsGroup, { title: tx("For the camera use") }, h(ChoiceRows, { label: tx("Camera address"), options: routes, value: route, onChange: (id) => update((draft) => (draft.network.route = id)) })),
    h("div", { className: "set-status set-status--ok" }, h("span", { className: "set-status__dot" }), using.side === "same" ? tx("The camera now uses the address of this page: {host}", { host: using.host }) : using.side === "local" ? tx("The camera now uses the local address {host}", { host: using.host }) : tx("The camera now uses the external address {host}", { host: using.host })),
    h(AppAddressesNote, { state: appAddressesState(settings) }),
  );
}

/* ---- Z-offset ---- */
const parseStepText = (text) => {
  const number = Number(String(text).trim().replace(",", "."));
  return text.trim() !== "" && Number.isFinite(number) && number >= Z_STEP_MIN && number <= Z_STEP_MAX ? Math.round(number * 1000) / 1000 : null;
};

/** One line for the menu: what Z moves and the steps. */
function motionSummary(motion) {
  const z = motion.zMoves === "bed" ? tx("Z moves the bed") : motion.zMoves === "toolhead" ? tx("Z moves the toolhead") : tx("Z: automatic");
  return z + " • XY " + MOTION_BASE_STEPS.concat(motion.xyExtra).join("·") + " • Z " + MOTION_BASE_STEPS.concat(motion.zExtra).join("·") + " mm";
}

/** 1.31: the Motion card: which way the Z arrows go, and the steps of the pad and of the Z buttons. */
function MotionPage() {
  const { settings, update } = useSettings();
  const capabilities = usePrinterCapabilities();
  const motion = settings.motion;
  const guess = capabilities.zMoves;
  const guessText = guess === "toolhead" ? tx("the toolhead") : guess === "bed" ? tx("the bed") : tx("not known yet");
  const steps = (key, title, note) =>
    h(
      SettingsGroup,
      { title, note },
      h(
        "div",
        { className: "oui-list" },
        MOTION_BASE_STEPS.map((step) => h(SwitchRow, { key: step, title: "± " + step + " mm", detail: tx("always there"), checked: true, disabled: true, onChange: noop })),
        MOTION_EXTRA_STEPS.map((step) =>
          h(SwitchRow, {
            key: step,
            title: "± " + step + " mm",
            checked: motion[key].includes(step),
            onChange: (on) => update((draft) => (draft.motion[key] = cleanExtraSteps(on ? draft.motion[key].concat(step) : draft.motion[key].filter((s) => s !== step)))),
          }),
        ),
      ),
    );
  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      { title: tx("What Z moves"), help: ["motion", "z"], note: tx("The Z arrows show where the part that moves goes. Bed: ↑ brings the bed up, towards the nozzle (Z−). Toolhead: ↑ lifts the toolhead (Z+).") },
      h(ChoiceRows, {
        label: tx("What Z moves"),
        value: motion.zMoves,
        onChange: (id) => update((draft) => (draft.motion.zMoves = id)),
        options: [
          { id: "auto", label: tx("Automatic"), detail: tx("From Klipper's configuration: {part}.", { part: guessText }) },
          { id: "bed", label: tx("The bed"), detail: tx("VzBot, Voron Trident, RatRig V-Core, most CoreXY") },
          { id: "toolhead", label: tx("The toolhead"), detail: tx("Voron 2.4, Prusa, Ender and other i3-style printers") },
        ],
      }),
    ),
    steps("xyExtra", tx("Steps of the X / Y pad"), tx("One ring of the pad for each step, the smallest inside: at most four.")),
    steps("zExtra", tx("Steps of the Z buttons"), tx("An ↑ and a ↓ button for each step.")),
  );
}

function ZOffsetPage() {
  const { settings, update } = useSettings();
  const steps = settings.zOffset.steps;
  const pad = (list) => Array.from({ length: Z_STEP_SLOTS }, (unused, index) => (index < list.length ? String(list[index]) : ""));
  const [slots, setSlots] = useState(() => pad(steps));
  const parsed = slots.filter((text) => text.trim() !== "").map(parseStepText);
  const problem = parsed.length === 0 ? tx("Write at least one value.") : parsed.includes(null) ? tx("Every value goes from 0.001 to 1 mm.") : new Set(parsed).size !== parsed.length ? tx("Two values are the same.") : "";
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
      { title: tx("Steps of the Z-offset card"), help: ["zoffset", "what"], note: tx("How many millimetres the nozzle moves at each tap of Raise / Lower. Leave a field empty to have fewer than four.") },
      h(
        "div",
        { className: "set-grid" },
        slots.map((text, index) =>
          h(
            "label",
            { key: index, className: "set-field" },
            h("span", { className: "set-field__label" }, tx("Step ") + (index + 1)),
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
      { title: tx("How they look in the card") },
      h("div", { className: "set-preview" }, steps.map((value) => h("span", { key: value, className: "oui-chip" }, value))),
      !isDefault && h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm set-inline-btn", onClick: () => update((draft) => (draft.zOffset.steps = SETTINGS_DEFAULTS.zOffset.steps.slice())) }, h(Icons.RotateCcw, { size: 16 }), tx("Restore 0.01 · 0.025 · 0.05 · 0.1")),
    ),
  );
}

/* ---- Language ---- */
/** Kept on this device only (each person may want their own); choosing reloads the page in that language. */
function LanguagePage() {
  const choice = savedLanguageChoice();
  const deviceName = I18N_LANGUAGES.find((language) => language.code === deviceLanguage()).name;
  const options = [{ id: "auto", label: tx("Automatic"), detail: tx("The language of this device: {language}", { language: deviceName }) }].concat(I18N_LANGUAGES.map((language) => ({ id: language.code, label: language.name })));
  return h(
    SettingsGroup,
    { title: tx("Language"), note: tx("Only on this device. The page reloads in the chosen language.") },
    h(ChoiceRows, { label: tx("Language"), options, value: choice, onChange: (id) => id !== choice && setLanguageChoice(id) }),
  );
}

/** "Italiano", or "Automatic (English)". */
function languageSummary() {
  const current = I18N_LANGUAGES.find((language) => language.code === LANG).name;
  return savedLanguageChoice() === "auto" ? tx("Automatic ({language})", { language: current }) : current;
}

/* ---- Notifications ---- */
function NotificationsPage({ active }) {
  const { settings, update } = useSettings();
  const status = useNotifierStatus(active);
  const channels = useNotifyChannels(active);
  return h(
    React.Fragment,
    null,
    h(ServiceLine, { status, installCommand: channels.data && channels.data.install_command }),
    IN_APP_WEBVIEW && h(SettingsGroup, { title: tx("This phone"), help: ["notifications", "app"] }, h(PhoneNotifications, { store: channels })),
    h(SettingsGroup, { title: IN_APP_WEBVIEW ? tx("Other phones (ntfy app, iPhone)") : tx("Where they arrive"), help: ["notifications", IN_APP_WEBVIEW ? "ntfy" : "how"] }, h(NotificationChannels, { store: channels })),
    h(
      SettingsGroup,
      { title: tx("Which notifications to receive"), help: ["notifications", "which"], note: tx("They apply to every phone with the app. Under each one, its text: change it if you like (1.38).") },
      h("div", { className: "oui-list" }, NOTIFICATION_KINDS.map((kind) => h(NotifyKindRow, { key: kind.id, kind, settings, update }))),
    ),
    h(NotifyRules, { settings, update }),
    h(
      SettingsGroup,
      { title: tx("Language of the notifications"), note: tx("The same for every phone, whatever language the dashboard shows.") },
      h(ChoiceRows, { label: tx("Language of the notifications"), options: I18N_LANGUAGES.map((language) => ({ id: language.code, label: language.name })), value: settings.language, onChange: (id) => update((draft) => (draft.language = id)) }),
    ),
  );
}

/* ---- AI monitor ---- */
const CONFIRMATION_OPTIONS = AI_CONFIRMATIONS.map((value) => ({ id: value, label: value === 1 ? tx("1 check") : tx("{count} in a row", { count: value }) }));

/* ---------------------------------------------------------------------------
   The menu
   ------------------------------------------------------------------------- */
const SYNC_TEXT = {
  loading: tx("Checking the Raspberry…"),
  saving: tx("Saving on the Raspberry…"),
  shared: tx("Saved on the Raspberry: they apply to every device"),
  local: tx("Only on this device"),
};

function SyncLine({ sync }) {
  return h(
    "div",
    { className: cx("set-status", sync.state === "shared" && "set-status--ok", sync.state === "local" && "set-status--warn") },
    h("span", { className: "set-status__dot" }),
    h("span", null, SYNC_TEXT[sync.state], sync.state === "local" && h("span", { className: "set-status__detail" }, " " + tx("The Raspberry did not accept the save") + (sync.detail ? " (" + sync.detail + ")" : "") + tx(": the settings stay in this browser and the automatic notifications do not see them."))),
  );
}

function settingsSummary(page, settings, brain) {
  const { camera, network, zOffset, notifications, ai } = settings;
  switch (page) {
    case "detector":
      return detectorSummary(brain.version);
    case "recordings":
      return recordingsSummary(brain.recordings);
    case "camcal":
      return cameraCalibrationSummary(brain.camcal);
    case "access":
      return accessSummary(brain.access);
    case "software":
      return softwareSummary(brain.version, brain.update, appUpdateWaiting(brain.app, readInstalledApp()));
    case "printer":
      return printerBrand(settings.printer.brand).label + (settings.printer.name ? " • " + settings.printer.name : "");
    case "camera":
      return CAMERA_METHODS.find((method) => method.id === camera.method).label + (camera.flipH || camera.flipV ? tx(" • flipped") : "");
    case "network":
      return network.localIp || network.externalIp ? [network.localIp, network.externalIp].filter(Boolean).join(" • ") : tx("Automatic (the address of this page)");
    case "zoffset":
      return zOffset.steps.join(" · ") + " mm";
    case "motion":
      return motionSummary(settings.motion);
    case "macros":
      return macroSettingsSummary(settings.macros);
    case "language":
      return languageSummary();
    case "functions":
      return printerFunctionsSummary(settings);
    case "appearance":
      return appearanceSummary();
    case "notifications":
      return tx("{count} of {total} on", { count: NOTIFICATION_KINDS.filter((kind) => notifications[kind.id]).length, total: NOTIFICATION_KINDS.length });
    default:
      return aiMonitorSummary(settings, brain);
  }
}

/**
 * The menu, in groups (1.22): what a page is about decides where it is, the most used first. 1.54: the pages of the
 * dashboard that are not on the bottom bar ("Go to"), and "This device" for what is kept on this device only.
 */
const SETTINGS_GROUPS = [
  { id: "printer", title: tx("The printer") },
  { id: "pages", title: tx("Go to") },
  { id: "watch", title: tx("Camera and AI monitor") },
  { id: "phone", title: tx("This device") },
  { id: "system", title: tx("System") },
];
/** Set by the app (99-main.js): goes to a page of the dashboard, and to a part of the Files page. */
const appNavigation = { go: noop };
const SETTINGS_ENTRIES = [
  { id: "printer", group: "printer", title: tx("Name and logo"), icon: Icons.Cube },
  { id: "functions", group: "printer", title: tx("Printer functions"), icon: Icons.Bulb },
  { id: "macros", group: "printer", title: tx("Macros"), icon: Icons.Play },
  { id: "motion", group: "printer", title: tx("Motion"), icon: Icons.Move },
  { id: "zoffset", group: "printer", title: "Z-offset", icon: Icons.Layers },
  { id: "camera", group: "watch", title: "Camera", icon: Icons.Camera },
  { id: "ai", group: "watch", title: tx("AI monitor"), icon: Icons.Sparkle },
  { id: "go-history", group: "pages", title: tx("Print history"), icon: Icons.Clock, link: ["files", "history"], detail: tx("Statistics and every print") },
  { id: "go-timelapse", group: "pages", title: "Timelapse", icon: Icons.Camera, link: ["files", "timelapse"], detail: tx("Videos and their settings") },
  { id: "appearance", group: "phone", title: tx("Appearance"), icon: Icons.Sliders },
  { id: "notifications", group: "phone", title: tx("Notifications"), icon: Icons.Bell },
  { id: "language", group: "phone", title: tx("Language"), icon: Icons.Language },
  { id: "network", group: "phone", title: tx("Addresses"), icon: Icons.Network },
  { id: "access", group: "system", title: tx("Access"), icon: Icons.Lock },
  { id: "software", group: "system", title: tx("Updates"), icon: Icons.Download },
];
/** The pages inside "AI monitor" (1.19: one entry for everything the monitor does, see 59h-ai-monitor-settings.js). */
const AI_SUBPAGES = [
  { id: "camcal", title: tx("Camera calibration"), icon: Icons.Probe },
  { id: "detector", title: tx("Monitor thresholds"), icon: Icons.Sliders },
  { id: "recordings", title: tx("Recordings"), icon: Icons.Image },
];
/** 1.59: the pages inside "Camera" (and one page for each webcam of Moonraker, "webcam:<uid>"). */
const CAMERA_SUBPAGES = [
  { id: "camera-main", title: tx("Main camera"), icon: Icons.Camera },
  { id: "camera-timelapse", title: "Timelapse", icon: Icons.Play },
];
const PAGE_PARENT = Object.fromEntries([...AI_SUBPAGES.map((entry) => [entry.id, "ai"]), ...CAMERA_SUBPAGES.map((entry) => [entry.id, "camera"])]);
const PAGE_TITLES = Object.fromEntries([...SETTINGS_ENTRIES, ...AI_SUBPAGES, ...CAMERA_SUBPAGES].map((entry) => [entry.id, entry.title]));

/** One row of the menu: icon, name, what it is set to now, and a badge when something waits. */
function SettingsEntry({ entry, settings, brain, menu }) {
  if (entry.link)
    return h(
      "button",
      {
        type: "button",
        className: "set-entry set-entry--link",
        "data-page": entry.id,
        onClick: () => {
          menu.close();
          appNavigation.go(entry.link[0], entry.link[1]);
        },
      },
      h("span", { className: "oui-row__icon oui-row__icon--accent" }, h(entry.icon)),
      h("span", { className: "oui-row__text" }, h("span", { className: "oui-row__name" }, entry.title), h("span", { className: "oui-row__meta set-entry__meta" }, entry.detail)),
      h("span", { className: "set-entry__go", "aria-hidden": "true" }, h(Icons.Forward)),
    );
  return h(
    "button",
    { type: "button", className: "set-entry", "data-page": entry.id, onClick: () => menu.goTo(entry.id) },
    h("span", { className: "oui-row__icon oui-row__icon--accent" }, h(entry.icon)),
    h(
      "span",
      { className: "oui-row__text" },
      h("span", { className: "oui-row__name" }, entry.title),
      entry.id === "functions" && !settings.functions.reviewed
        ? h("span", null, h("span", { className: "set-entry__badge set-entry__badge--inline" }, tx("To check"))) // under the name: the long title keeps its room on a narrow phone
        : h("span", { className: "oui-row__meta set-entry__meta" }, settingsSummary(entry.id, settings, brain)),
    ),
    entry.id === "software" && ((brain.update.phase === "ok" && Number(brain.update.raw.commits_behind_count) > 0) || appUpdateWaiting(brain.app, readInstalledApp())) && h("span", { className: "set-entry__badge" }, tx("New")),
    h("span", { className: "set-entry__go", "aria-hidden": "true" }, h(Icons.Forward)),
  );
}

function SettingsHome({ menu }) {
  const { settings, sync } = useSettings();
  const [components, setComponents] = useState(null);
  useEffect(() => {
    let cancelled = false;
    moonrakerComponents().then((found) => !cancelled && setComponents(found));
    return () => {
      cancelled = true;
    };
  }, []);
  const shown = (entry) => !entry.component || (components && components.has(entry.component));
  const brain = { version: useBrainVersion(true), update: useProgramUpdate(true), app: useAppRelease(true), access: useAccessStatus(true)[0], recordings: useBackendJson("/api/recordings", true, BRAIN_POLL_MS), camcal: useBackendJson("/api/camera/calibration", true, BRAIN_POLL_MS) };
  return h(
    React.Fragment,
    null,
    h(
      "button",
      { type: "button", className: "set-entry set-entry--guide", "data-page": "setup", onClick: menu.startSetup },
      h("span", { className: "oui-row__icon oui-row__icon--accent" }, h(Icons.Sparkle)),
      h("span", { className: "oui-row__text" }, h("span", { className: "oui-row__name" }, tx("Guided set-up")), h("span", { className: "oui-row__meta set-entry__meta" }, settings.setup.done ? tx("Everything KlippEye needs, step by step: repeat it whenever you want") : tx("Not done yet: everything KlippEye needs, step by step"))),
      !settings.setup.done && h("span", { className: "set-entry__badge" }, tx("Start")),
      h("span", { className: "set-entry__go", "aria-hidden": "true" }, h(Icons.Forward)),
    ),
    SETTINGS_GROUPS.map((group) =>
      h(
        "section",
        { key: group.id, className: "set-group set-group--menu", "data-group": group.id },
        h("div", { className: "set-group__label" }, group.title),
        h(
          "div",
          { className: "oui-list" },
          SETTINGS_ENTRIES.filter((entry) => entry.group === group.id && shown(entry)).map((entry) => h(SettingsEntry, { key: entry.id, entry, settings, brain, menu })),
        ),
      ),
    ),
    h(SyncLine, { sync }),
    h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--block set-reset", onClick: () => menu.ask("reset") }, h(Icons.RotateCcw, { size: 18 }), tx("Restore the initial values")),
  );
}

function SettingsDrawer({ menu, updates, printing, actions }) {
  useBodyScrollLock(true);
  const { settings } = useSettings();
  const { page } = menu;
  const touch = useRef(null);
  const onTouchStart = (event) => {
    const point = event.touches[0];
    const onControl = event.target && event.target.closest && event.target.closest(SWIPE_IGNORE);
    touch.current = event.touches.length === 1 && !onControl ? { x: point.clientX, y: point.clientY, t: Date.now() } : null;
  };
  const onTouchEnd = (event) => {
    const start = touch.current;
    touch.current = null;
    if (!start) return;
    const point = event.changedTouches[0];
    const dx = point.clientX - start.x;
    if (dx < -SWIPE_CLOSE_PX && Math.abs(dx) > Math.abs(point.clientY - start.y) * 2 && Date.now() - start.t < SWIPE_CLOSE_MAX_MS) menu.close();
  };
  let body;
  if (page === "printer") body = h(PrinterPage);
  else if (page === "camera") body = h(CamerasPage, { menu });
  else if (page === "camera-main") body = h(CameraPage);
  else if (page === "camera-timelapse") body = h(CameraTimelapsePage);
  else if (page && page.startsWith(WEBCAM_PAGE_PREFIX)) body = h(WebcamPage, { key: page, uid: page.slice(WEBCAM_PAGE_PREFIX.length), menu });
  else if (page === "network") body = h(NetworkPage);
  else if (page === "zoffset") body = h(ZOffsetPage);
  else if (page === "motion") body = h(MotionPage);
  else if (page === "macros") body = h(MacrosPage);
  else if (page === "notifications") body = h(NotificationsPage, { active: true });
  else if (page === "ai") body = h(AiPage, { active: true, menu });
  else if (page === "detector") body = h(DetectorPage, { active: true });
  else if (page === "recordings") body = h(RecordingsPage, { active: true });
  else if (page === "camcal") body = h(CameraCalibrationPage, { active: true });
  else if (page === "access") body = h(AccessPage, { active: true });
  else if (page === "language") body = h(LanguagePage);
  else if (page === "appearance") body = h(AppearancePage);
  else if (page === "functions") body = h(PrinterFunctionsPage, { printing });
  else if (page === "software") body = h(SoftwarePage, { active: true, menu, updates, printing, actions });
  else body = h(SettingsHome, { menu });
  return h(
    "div",
    { className: "drawer-overlay", onClick: (event) => event.target === event.currentTarget && menu.close() },
    h(
      "aside",
      { className: "drawer", role: "dialog", "aria-modal": "true", "aria-label": tx("Settings"), onTouchStart, onTouchEnd },
      h(
        "div",
        { className: "drawer__head" },
        page
          ? h("button", { type: "button", className: "header-btn drawer__btn", "aria-label": tx("Back"), onClick: () => goBack() }, h(Icons.Back))
          : h(PrinterLogo, { id: settings.printer.brand, className: "drawer__logo" }),
        h("div", { className: "drawer__title" }, page ? PAGE_TITLES[page] || webcamPageTitle(page) : tx("Settings")),
        h(HelpButton, { page: page || "home", className: "drawer__help" }),
        h("button", { type: "button", className: "header-btn drawer__btn", "aria-label": tx("Close"), onClick: menu.close }, h(Icons.Close)),
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
      title: tx("Restore the settings?"),
      subtitle: tx("Camera, addresses, Z-offset steps, notifications, AI monitor"),
      message: tx("All settings go back to the initial values, on every device. Confirm?"),
      confirmLabel: tx("Restore"),
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
      title: tx("Cancel prints by itself?"),
      subtitle: tx("Automatic action of the AI monitor"),
      message: tx("If the AI suggests CANCEL, the Raspberry stops the print right away. The AI can be wrong and a cancelled print cannot be recovered. Turn it on?"),
      confirmLabel: tx("Turn on"),
      onConfirm: () => {
        menu.ask(null);
        update((draft) => (draft.ai.autoCancel = true));
      },
      onCancel: () => menu.ask(null),
    }),
  );
}
