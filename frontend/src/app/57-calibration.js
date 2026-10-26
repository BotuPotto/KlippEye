/* ============================================================================
   57 · CALIBRATION MACROS
   A card of quick-launch buttons for the Klipper macros the user picked
   (shaper calibration, park, clean nozzle, ...). The choice is kept in
   localStorage and mirrored on the server (/api/calibration/selected), so it is
   the same on every device. A macro with parameters gets a ⚙ half-button that
   opens a form; the ⚙ in the card header opens the macro picker. The endstop and
   probe readings (57a) close the card.
   ========================================================================== */

const CALIBRATION_SYNC_MS = 5000;
const MACRO_PRELOAD_DELAY_MS = 1100;
const MACRO_PREFIX = "gcode_macro ";

/* ---------------------------------------------------------------------------
   Finding the macros
   ------------------------------------------------------------------------- */
const PARAM_DEFAULT_PATTERN = /params\.([A-Za-z0-9_]+)[^\n]*?\|\s*default\s*\(\s*([^),\n]+)/gi;
const PARAM_PATTERN = /params\.([A-Za-z0-9_]+)/gi;

/** The `{params.X|default(...)}` references of a macro's gcode, with their defaults. */
function extractParams(gcode) {
  const defaults = {};
  for (const match of gcode.matchAll(PARAM_DEFAULT_PATTERN)) defaults[match[1].toUpperCase()] = match[2].trim().replace(/^['"]|['"]$/g, "");
  const names = [...new Set([...gcode.matchAll(PARAM_PATTERN)].map((match) => match[1].toUpperCase()))];
  return names.map((name) => ({ name, default: defaults[name] || "", type: "text" }));
}

/** The parameter list in the shape {name, default, type}, whatever the backend sent. */
const normalizeParams = (params) => (params || []).map((param) => (typeof param === "string" ? { name: param, default: "", type: "text" } : param));

/** Macros known to the backend backend (they carry file, description and parameters). */
async function macrosFromBrain() {
  const json = await fetchJson("/api/macros/list").catch(() => null);
  if (!json || !json.ok || !json.macros) return [];
  return json.macros.map((macro) => {
    const params = normalizeParams(macro.params);
    return {
      name: macro.name,
      file: macro.file || "",
      description: macro.description || "",
      params,
      has_params: params.length > 0 || !!macro.has_params,
      source: macro.source || "brain",
    };
  });
}

/** Macros defined in the printer configuration (Klipper's `configfile` object). */
async function macrosFromConfig() {
  const configfile = await moonraker.configfile().catch(() => ({}));
  const config = configfile.config || {};
  return Object.keys(config)
    .filter((key) => key.toLowerCase().startsWith(MACRO_PREFIX))
    .map((key) => ({ name: key.slice(MACRO_PREFIX.length).trim(), settings: config[key] || {} }))
    .filter(({ name }) => !name.startsWith("_"))
    .map(({ name, settings }) => {
      const params = extractParams(settings.gcode || "");
      return { name, file: settings.filename || "", description: settings.description || "", params, has_params: params.length > 0, source: "configfile" };
    });
}

/**
 * Every macro, merged from the backend list and the printer config (the backend wins), sorted by name.
 * (The old dashboard also asked /printer/objects/list but read the wrong field, so that source never
 * contributed anything and has been dropped.)
 */
async function loadMacroCatalog() {
  const [brain, config] = await Promise.all([macrosFromBrain(), macrosFromConfig()]);
  const byName = new Map();
  for (const macro of [...brain, ...config]) if (!byName.has(macro.name)) byName.set(macro.name, macro);
  return [...byName.values()].sort((a, b) => a.name.localeCompare(b.name));
}

const calibrationApi = {
  async loadSelected() {
    const json = await fetchJson("/api/calibration/selected").catch(() => null);
    return json && json.ok && Array.isArray(json.selected) ? json.selected : null;
  },
  async saveSelected(selected) {
    storage.set(STORAGE_KEYS.calibrationSelected, JSON.stringify(selected));
    try {
      await fetch("/api/calibration/selected", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ selected }) });
    } catch (error) {}
  },
};

/* ---------------------------------------------------------------------------
   State
   ------------------------------------------------------------------------- */
function useCalibrationMacros(syncPaused) {
  const [selected, setSelected] = useState(() => storage.getJson(STORAGE_KEYS.calibrationSelected) || []);
  const [macros, setMacros] = useState(() => storage.getJson(STORAGE_KEYS.calibrationMacrosCache) || []);
  const [loading, setLoading] = useState(false);
  const pausedRef = useRef(syncPaused);
  pausedRef.current = syncPaused;

  const refreshMacros = async () => {
    setLoading(true);
    const catalog = await loadMacroCatalog();
    setMacros(catalog);
    storage.set(STORAGE_KEYS.calibrationMacrosCache, JSON.stringify(catalog));
    setLoading(false);
  };

  // The server copy is the reference: it is re-read regularly so a change made on another device shows up here.
  useEffect(() => {
    let cancelled = false;
    const sync = async () => {
      if (pausedRef.current) return;
      const remote = await calibrationApi.loadSelected();
      if (cancelled || !remote || pausedRef.current) return;
      storage.set(STORAGE_KEYS.calibrationSelected, JSON.stringify(remote));
      setSelected((current) => (JSON.stringify(current) === JSON.stringify(remote) ? current : remote));
    };
    const stopPolling = startPolling(sync, CALIBRATION_SYNC_MS);
    const preload = setTimeout(() => (storage.getJson(STORAGE_KEYS.calibrationMacrosCache) || []).length === 0 && refreshMacros(), MACRO_PRELOAD_DELAY_MS);
    return () => {
      cancelled = true;
      stopPolling();
      clearTimeout(preload);
    };
  }, []);

  const select = (next) => {
    setSelected(next);
    calibrationApi.saveSelected(next);
  };

  return {
    selected,
    macros,
    loading,
    refreshMacros,
    toggle: (name) => select(selected.includes(name) ? selected.filter((item) => item !== name) : [...selected, name]),
    clear: () => select([]),
  };
}

/* ---------------------------------------------------------------------------
   Pieces
   ------------------------------------------------------------------------- */
const MACRO_BUTTON_CLASS = cx(PILL_BUTTON_CLASS, "macro-run");
/** "PARK_TEST" → "Park test" (the macro keeps its real name when it is run). */
const macroLabel = (name) => {
  const words = name.replace(/_/g, " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

/** Lets the text of a button wrap onto at most `lines` lines and shrinks its font (from `max` down to `min` px) until it fits, so a long
 *  label ("Esegui Axes shaper calibration") stays inside the button on any screen. Fitted again when the button changes width. */
function useFitLabel(button, label, text, { max = 15, min = 10.5, lines = 2 } = {}) {
  useLayoutEffect(() => {
    const buttonEl = button.current;
    const labelEl = label.current;
    if (!buttonEl || !labelEl) return undefined;
    let lastWidth = -1;
    const fit = () => {
      let size = max;
      buttonEl.style.fontSize = size + "px";
      const fits = () => labelEl.scrollWidth <= labelEl.clientWidth + 1 && labelEl.offsetHeight <= Math.ceil(size * 1.2 * lines) + 1;
      while (size > min && !fits()) {
        size -= 0.5;
        buttonEl.style.fontSize = size + "px";
      }
      lastWidth = buttonEl.clientWidth;
    };
    fit();
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(() => buttonEl.clientWidth !== lastWidth && fit()) : null;
    if (observer) observer.observe(buttonEl);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit).catch(noop);
    return () => {
      if (observer) observer.disconnect();
    };
  }, [text, max, min, lines]);
}

/** A button whose label wraps and shrinks to fit (see useFitLabel). */
function FitButton({ className, onClick, text, ...options }) {
  const button = useRef(null);
  const label = useRef(null);
  useFitLabel(button, label, text, options);
  return h("button", { ref: button, className: cx(className, "fit-btn"), onClick }, h("span", { ref: label, className: "fit-btn__label" }, text));
}

function MacroButton({ macro, onRun, onEditParams }) {
  const label = macroLabel(macro.name);
  if (!macro.has_params || !macro.params || macro.params.length === 0) {
    return h("button", { className: MACRO_BUTTON_CLASS, onClick: () => onRun(macro.name) }, label);
  }
  // One pill, two tap zones: the name runs the macro as it is, the gear asks for parameters first.
  return h(
    "div",
    { className: "macro-split" },
    h("button", { className: "macro-split-run", onClick: () => onRun(macro.name) }, label),
    h("button", { className: "macro-split-gear", onClick: () => onEditParams(macro), "aria-label": "Parametri" }, h(Icons.Gear, { size: 18 })),
  );
}

/** Form for the parameters of one macro; "ESEGUI" sends `NAME KEY=value ...` for the filled-in fields. */
function ParamDialog({ macro, onRun, onClose }) {
  const params = normalizeParams(macro.params);
  const [values, setValues] = useState(() => Object.fromEntries(params.map((param) => [param.name, param.default || ""])));
  const firstInput = useRef(null);
  useBodyScrollLock(true);

  useEffect(() => {
    const closeOnEscape = (event) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", closeOnEscape);
    const focusTimer = setTimeout(() => {
      if (firstInput.current) {
        firstInput.current.focus();
        firstInput.current.select();
      }
    }, 100);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      clearTimeout(focusTimer);
    };
  }, []);

  const run = () => {
    const filled = params.filter((param) => values[param.name].trim());
    onRun([macro.name, ...filled.map((param) => param.name + "=" + values[param.name].trim())].join(" "));
    onClose();
  };

  return h(
    "div",
    { className: "sheet-overlay sheet-overlay--params", onClick: (e) => e.target === e.currentTarget && onClose() },
    h(
      "div",
      { className: "sheet-card sheet-card--column" },
      h(
        "div",
        { className: "sheet-header sheet-header--bar" },
        h("div", null, h("div", { className: "dialog-title" }, macro.name), macro.description && h("div", { className: "dialog-sub" }, macro.description)),
        h("button", { className: "dialog-close", onClick: onClose, "aria-label": "Chiudi" }, "✕"),
      ),
      h(
        "div",
        { className: "params-body" },
        h("div", { className: "oui-label mb-3" }, "Parametri"),
        params.map((param, index) =>
          h(
            "div",
            { key: param.name, className: "param-field" },
            h("div", { className: "param-field-head" }, h("label", { className: "param-name" }, param.name), param.default && h("span", { className: "oui-badge" }, "default: " + param.default)),
            h("input", {
              ref: index === 0 ? firstInput : undefined,
              className: "oui-field oui-mono",
              type: param.type === "text" || !param.type ? "text" : "number",
              placeholder: param.default || param.name,
              value: values[param.name],
              onChange: (e) => setValues({ ...values, [param.name]: e.target.value }),
            }),
          ),
        ),
      ),
      h(
        "div",
        { className: "sheet-footer" },
        h(FitButton, { className: "oui-btn", onClick: onClose, text: "Annulla" }),
        h(FitButton, { className: "oui-btn oui-btn--primary params-run", onClick: run, text: "Esegui " + macroLabel(macro.name) }),
      ),
    ),
  );
}

function MacroPickerRow({ macro, checked, onToggle }) {
  const hasParams = macro.has_params;
  const source = macro.source || "";
  const showSource = source.includes("shaketune") || source.includes("live");
  return h(
    "div",
    { className: "picker-row", onClick: onToggle },
    h("input", { type: "checkbox", className: "oui-check", checked, onChange: onToggle, onClick: (e) => e.stopPropagation() }),
    h(
      "div",
      { className: "picker-row-main" },
      h(
        "div",
        { className: "picker-row-name" },
        macro.name,
        hasParams && h("span", { className: "oui-badge oui-badge--ok" }, macro.params.length + " PARAM"),
        showSource && h("span", { className: "oui-badge oui-badge--warn" }, source),
      ),
      macro.description && macro.description.toLowerCase() !== "dummy" && h("div", { className: "picker-row-description" }, macro.description),
      hasParams && h("div", { className: "picker-row-params" }, macro.params.map((param) => param.name + (param.default ? "=" + param.default : "")).join(", ")),
      h("div", { className: "picker-row-file" }, macro.file || ""),
    ),
  );
}

/** Text a search must find in a row: everything the row shows. */
const pickerSearchText = (macro) =>
  [macro.name, macro.has_params ? macro.params.length + " PARAM" : "", macro.source || "", macro.description || "", (macro.params || []).map((param) => param.name + (param.default ? "=" + param.default : "")).join(", "), macro.file || ""]
    .join(" ")
    .toLowerCase();

function MacroPicker({ state, onClose }) {
  const { macros, selected, loading, toggle, clear } = state;
  const [query, setQuery] = useState("");
  // The counter line is worded differently after the list is drawn, after a tick and after "clear all".
  const [lastChange, setLastChange] = useState(null); // null | "toggled" | "cleared"
  useBodyScrollLock(true);
  const needle = query.toLowerCase();
  const visible = macros.filter((macro) => pickerSearchText(macro).includes(needle));
  const found = "Trovate " + macros.length;
  const stats = loading
    ? "Caricamento macro (Metodo V30 - TUTTE le macro)..."
    : lastChange === "cleared"
      ? "Selezionate 0"
      : (lastChange === "toggled" ? found : found + " macro") + " - Selezionate " + selected.length;
  const toggleMacro = (name) => {
    setLastChange("toggled");
    toggle(name);
  };
  const clearAll = () => {
    setLastChange("cleared");
    clear();
  };
  return h(
    "div",
    { className: "sheet-overlay sheet-overlay--picker", onClick: (e) => e.target === e.currentTarget && onClose() },
    h(
      "div",
      { className: "sheet-card sheet-card--column" },
      h("div", { className: "sheet-header sheet-header--bar" }, h("div", { className: "dialog-title" }, "Seleziona macro"), h("button", { className: "dialog-close", onClick: onClose, "aria-label": "Chiudi" }, "✕")),
      h(
        "div",
        { className: "picker-search" },
        h("input", { className: "oui-field", value: query, placeholder: "Cerca macro...", onChange: (e) => setQuery(e.target.value) }),
        h("div", { className: "picker-stats" }, stats),
      ),
      h("div", { className: "picker-list oui-list" }, visible.map((macro) => h(MacroPickerRow, { key: macro.name, macro, checked: selected.includes(macro.name), onToggle: () => toggleMacro(macro.name) }))),
      h("div", { className: "sheet-footer sheet-footer--split" }, h("button", { className: "oui-btn", onClick: clearAll }, "Deseleziona tutto"), h("button", { className: "oui-btn oui-btn--primary", onClick: onClose }, "Fatto")),
    ),
  );
}

/* ---------------------------------------------------------------------------
   Card
   ------------------------------------------------------------------------- */
/** `onGcode(script)` sends a macro call (and echoes it in the console); `capabilities` and `lockReason` feed the endstop section. */
function CalibrationCard({ onGcode, capabilities, lockReason }) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [editing, setEditing] = useState(null); // macro whose parameters are being filled in
  const state = useCalibrationMacros(pickerOpen);

  const run = (script) => {
    onGcode(script);
    toast.action(script);
  };
  const openPicker = () => {
    setPickerOpen(true);
    state.refreshMacros();
  };

  return h(
    Card,
    null,
    h(
      CardHeader,
      { title: "Calibrazioni" },
      h("button", { className: "icon-btn", title: "Gestisci macro - cache fino ad apertura modal", "aria-label": "Gestisci macro", onClick: openPicker }, h(Icons.Gear, { size: 20 })),
    ),
    h(
      "div",
      { className: "macro-grid" },
      state.selected.length === 0
        ? h("span", { className: "macro-empty" }, "Nessuna macro - tocca l'ingranaggio per sceglierne")
        : state.selected.map((name) => {
            const macro = state.macros.find((item) => item.name === name) || { name, params: [], has_params: false, description: "" };
            return h(MacroButton, { key: name, macro, onRun: run, onEditParams: setEditing });
          }),
    ),
    h(EndstopsSection, { capabilities, lockReason }),
    h(Presence, null, editing && h(ParamDialog, { macro: editing, onRun: run, onClose: () => setEditing(null) })),
    h(Presence, null, pickerOpen && h(MacroPicker, { state, onClose: () => setPickerOpen(false) })),
  );
}
