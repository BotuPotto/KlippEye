/* ============================================================================
   57 · MACROS
   Quick-launch buttons for the Klipper macros (1.33, like Mainsail): every macro
   in one card ("simple", hiding the ones not used) or cards of the person's own
   ("groups": a name, a colour, the macros in their order, and when each card
   shows: standby, printing, paused). The choice is in the shared settings
   (Settings → Macros, 59m-macro-settings.js), the same on every device. A macro
   with parameters gets a ⚙ half-button that opens a form. The endstop and probe
   readings (57a) have their own card.
   ========================================================================== */

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

/** The old "Calibrations" choice (before 1.33), kept by the backend: only read once, to turn it into a group. */
async function loadLegacySelection() {
  const json = await fetchJson("/api/calibration/selected").catch(() => null);
  return json && json.ok && Array.isArray(json.selected) ? json.selected : null;
}

/**
 * Every macro of the printer, shared by the cards and Settings → Macros: read once (and kept on this device for the next
 * opening), again when Klipper restarts and when Settings → Macros opens. Names in upper case.
 */
const macroCatalogStore = (() => {
  const cached = storage.getJson(STORAGE_KEYS.calibrationMacrosCache);
  let view = { macros: Array.isArray(cached) ? cached : [], loaded: false, loading: false };
  let started = false;
  const listeners = new Set();
  const emit = (change) => {
    view = { ...view, ...change };
    listeners.forEach((listener) => listener());
  };
  const refresh = async () => {
    if (view.loading) return;
    emit({ loading: true });
    const catalog = (await loadMacroCatalog().catch(() => null)) || null;
    if (catalog && catalog.length) {
      const macros = catalog.map((macro) => ({ ...macro, name: macro.name.toUpperCase() }));
      storage.set(STORAGE_KEYS.calibrationMacrosCache, JSON.stringify(macros));
      emit({ macros, loaded: true, loading: false });
    } else emit({ loading: false, loaded: Boolean(catalog) });
  };
  return {
    snapshot: () => view,
    refresh,
    subscribe(listener) {
      listeners.add(listener);
      if (!started) {
        started = true;
        setTimeout(refresh, view.macros.length ? MACRO_PRELOAD_DELAY_MS : 0);
        onKlipperReady(() => refresh());
      }
      return () => listeners.delete(listener);
    },
  };
})();

/** { macros, loaded, loading, refresh }. */
function useMacroCatalog() {
  const view = useSyncExternalStore(macroCatalogStore.subscribe, macroCatalogStore.snapshot);
  return { ...view, refresh: macroCatalogStore.refresh };
}

/**
 * 1.33: the macros chosen in the old "Calibrations" card become a group "Calibrations" (groups mode), when the settings have
 * come from the Raspberry (before, they could be the defaults of a device that has not asked yet) and have no groups. The
 * backend's old list is then emptied, so it happens once (and not again after "Restore the initial values").
 */
function useMacroMigration() {
  const { settings, sync, update } = useSettings();
  const done = useRef(false);
  useEffect(() => {
    if (done.current || sync.state !== "shared") return;
    done.current = true;
    loadLegacySelection().then((selected) => {
      const names = cleanMacroNames(selected || []);
      if (!names.length) return;
      update((draft) => {
        if (draft.macros.groups.length) return;
        draft.macros.mode = "groups";
        draft.macros.groups = [{ id: "calib", name: tx("Calibrations"), color: "none", show: { standby: true, printing: true, paused: true }, macros: names }];
      });
      fetch("/api/calibration/selected", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ selected: [] }) }).catch(noop);
    });
  }, [sync.state]);
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
    h("button", { className: "macro-split-gear", onClick: () => onEditParams(macro), "aria-label": tx("Parameters") }, h(Icons.Gear, { size: 18 })),
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
        h("button", { className: "dialog-close", onClick: onClose, "aria-label": tx("Close") }, "✕"),
      ),
      h(
        "div",
        { className: "params-body" },
        h("div", { className: "oui-label mb-3" }, tx("Parameters")),
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
        h(FitButton, { className: "oui-btn", onClick: onClose, text: tx("Cancel") }),
        h(FitButton, { className: "oui-btn oui-btn--primary params-run", onClick: run, text: tx("Run ") + macroLabel(macro.name) }),
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

/** A checklist of every macro. `state`: { macros, selected (names), loading, toggle(name), clear() }; `title` of the sheet. */
function MacroPicker({ state, onClose, title }) {
  const { macros, selected, loading, toggle, clear } = state;
  const [query, setQuery] = useState("");
  // The counter line is worded differently after the list is drawn, after a tick and after "clear all".
  const [lastChange, setLastChange] = useState(null); // null | "toggled" | "cleared"
  useBodyScrollLock(true);
  const needle = query.toLowerCase();
  const visible = macros.filter((macro) => pickerSearchText(macro).includes(needle));
  const found = tx("Found ") + macros.length;
  const stats = loading
    ? tx("Loading macros (all of them)...")
    : lastChange === "cleared"
      ? tx("Selected 0")
      : (lastChange === "toggled" ? found : found + " macro") + tx(" - Selected ") + selected.length;
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
      h("div", { className: "sheet-header sheet-header--bar" }, h("div", { className: "dialog-title" }, title || tx("Choose macros")), h("button", { className: "dialog-close", onClick: onClose, "aria-label": tx("Close") }, "✕")),
      h(
        "div",
        { className: "picker-search" },
        h("input", { className: "oui-field", value: query, placeholder: tx("Search macros..."), onChange: (e) => setQuery(e.target.value) }),
        h("div", { className: "picker-stats" }, stats),
      ),
      h("div", { className: "picker-list oui-list" }, visible.map((macro) => h(MacroPickerRow, { key: macro.name, macro, checked: selected.includes(macro.name), onToggle: () => toggleMacro(macro.name) }))),
      h("div", { className: "sheet-footer sheet-footer--split" }, h("button", { className: "oui-btn", onClick: clearAll }, tx("Deselect all")), h("button", { className: "oui-btn oui-btn--primary", onClick: onClose }, tx("Done"))),
    ),
  );
}

/* ---------------------------------------------------------------------------
   Cards (1.33): like Mainsail's macros
   "simple": one card with every macro of the printer but the hidden ones;
   "groups": a card for each group of the person's, shown while the printer is in
   one of the group's states (standby, printing, paused), in the group's colour.
   ------------------------------------------------------------------------- */
/** "standby" | "printing" | "paused" from print_stats.state. */
const macroPrintState = (state) => (state === "printing" ? "printing" : state === "paused" ? "paused" : "standby");

/** The class and style of a card (or editor) in `color`: one of MACRO_COLORS, or "#rrggbb" from the colour wheel (1.33.1). */
function macroColorProps(color) {
  if (MACRO_HEX_COLOR.test(color)) return { className: "macro-card--custom", style: { "--macro-tint": color, "--macro-soft": "color-mix(in srgb, " + color + " 20%, transparent)" } };
  return { className: "macro-card--" + color, style: undefined };
}

/** The cards to show: [{ id, title, color, names, empty }]. */
function macroCards(macroSettings, catalog, printState) {
  const known = catalog.loaded || catalog.macros.length > 0;
  const exists = (name) => !known || catalog.macros.some((macro) => macro.name === name);
  if (macroSettings.mode === "simple") {
    const names = catalog.macros.map((macro) => macro.name).filter((name) => !macroSettings.hidden.includes(name));
    return [{ id: "all", title: tx("Macros"), color: "none", names, empty: known ? tx("No macros to show - the gear chooses them") : tx("Reading the macros…") }];
  }
  const state = macroPrintState(printState);
  const groups = macroSettings.groups.filter((group) => group.show[state]);
  if (macroSettings.groups.length === 0) return [{ id: "none", title: tx("Macros"), color: "none", names: [], empty: tx("No groups yet - the gear makes one") }];
  return groups.map((group) => ({ id: group.id, title: group.name || tx("Macros"), color: group.color, names: group.macros.filter(exists), empty: tx("No macros in this group - the gear adds them") }));
}

/** The macro cards. `onSettings()` opens Settings → Macros. */
function MacroCards({ printState, onGcode, onSettings }) {
  const { settings } = useSettings();
  const catalog = useMacroCatalog();
  const [editing, setEditing] = useState(null); // macro whose parameters are being filled in
  const run = (script) => {
    onGcode(script);
    toast.action(script);
  };
  const cards = macroCards(settings.macros, catalog, printState);
  return h(
    React.Fragment,
    null,
    cards.map((card) =>
      h(
        Card,
        { key: card.id, cardId: "macro:" + card.id, className: cx("macro-card", macroColorProps(card.color).className), style: macroColorProps(card.color).style, "data-macro-card": card.id },
        h(CardHeader, { title: card.title }, h("button", { className: "icon-btn", title: tx("Manage macros"), "aria-label": tx("Manage macros"), onClick: onSettings }, h(Icons.Gear, { size: 20 }))),
        h(
          "div",
          { className: "macro-grid" },
          card.names.length === 0
            ? h("span", { className: "macro-empty" }, card.empty)
            : card.names.map((name) => {
                const macro = catalog.macros.find((item) => item.name === name) || { name, params: [], has_params: false, description: "" };
                return h(MacroButton, { key: name, macro, onRun: run, onEditParams: setEditing });
              }),
        ),
      ),
    ),
    h(Presence, null, editing && h(ParamDialog, { macro: editing, onRun: run, onClose: () => setEditing(null) })),
  );
}

/** The endstops and the probe (57a), a card of their own since the macros left the "Calibrations" card (1.33). */
function EndstopsCard({ capabilities, lockReason }) {
  return h(Card, { className: "endstops-card" }, h(EndstopsSection, { capabilities, lockReason }));
}
