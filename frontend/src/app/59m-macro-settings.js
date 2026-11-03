/* ============================================================================
   59m · SETTINGS → MACROS (1.33, roadmap 6b part 4)
   How the macro cards (57-calibration.js) look, like Mainsail's macro settings:
     · "All the macros": one card with every macro of the printer; each can be
       hidden from it;
     · "Groups": cards of the person's own, each with a name, a colour, the
       macros in their order, and the printer states it shows in (idle,
       printing, paused).
   Saved in the shared settings: the same on every phone and computer.
   ========================================================================== */

const MACRO_COLOR_OPTIONS = [
  { id: "none", label: tx("Neutral") },
  { id: "accent", label: tx("Violet") },
  { id: "cool", label: tx("Blue") },
  { id: "ok", label: tx("Green") },
  { id: "warn", label: tx("Orange") },
  { id: "danger", label: tx("Red") },
];
const MACRO_STATE_OPTIONS = [
  { id: "standby", label: tx("Idle") },
  { id: "printing", label: tx("Printing") },
  { id: "paused", label: tx("Paused") },
];

/** The line under "Macros" in the menu. */
function macroSettingsSummary(macros) {
  if (macros.mode === "groups") return macros.groups.length === 1 ? tx("1 group") : tx("{count} groups", { count: macros.groups.length });
  return macros.hidden.length ? tx("All the macros • {count} hidden", { count: macros.hidden.length }) : tx("All the macros");
}

/* ---------------------------------------------------------------------------
   The colour (1.33.1): a few ready ones, or any colour on a wheel (hue around,
   strength from the centre out) with a brightness bar and the hex code.
   ------------------------------------------------------------------------- */
const COLOR_COMMIT_MS = 250; // dragging on the wheel saves once it stops for this long

function hsvToHex(hue, sat, val) {
  const f = (n) => {
    const k = (n + hue / 60) % 6;
    return val - val * sat * Math.max(0, Math.min(k, 4 - k, 1));
  };
  return "#" + [f(5), f(3), f(1)].map((c) => Math.round(c * 255).toString(16).padStart(2, "0")).join("");
}

function hexToHsv(hex) {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => c / 255);
  const max = Math.max(r, g, b);
  const d = max - Math.min(r, g, b);
  let hue = 0;
  if (d) hue = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return { h: (hue * 60 + 360) % 360, s: max ? d / max : 0, v: max };
}

/** The wheel: drag (or tap) to pick hue and strength; the bar under it sets the brightness. */
/** `brightness` false: no bar (the lights panel has its own brightness). */
function ColorWheel({ value, onChange, brightness = true }) {
  const [hsv, setHsv] = useState(() => hexToHsv(MACRO_HEX_COLOR.test(value) ? value : "#7c5cff"));
  const [text, setText] = useState(null); // the hex code while it is typed
  const wheel = useRef(null);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    if (MACRO_HEX_COLOR.test(value) && value !== hsvToHex(hsv.h, hsv.s, hsv.v)) setHsv(hexToHsv(value));
  }, [value]);
  const hex = hsvToHex(hsv.h, hsv.s, hsv.v);
  const set = (next) => {
    setHsv(next);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => onChange(hsvToHex(next.h, next.s, next.v)), COLOR_COMMIT_MS);
  };
  const pick = (event) => {
    const box = wheel.current.getBoundingClientRect();
    const dx = event.clientX - (box.left + box.width / 2);
    const dy = event.clientY - (box.top + box.height / 2);
    const radius = box.width / 2;
    set({ ...hsv, h: ((Math.atan2(dy, dx) * 180) / Math.PI + 360) % 360, s: Math.min(1, Math.hypot(dx, dy) / radius) });
  };
  const angle = (hsv.h * Math.PI) / 180;
  return h(
    "div",
    { className: "color-wheel", style: { "--wheel-hex": hex, "--wheel-dim": 1 - hsv.v } },
    h(
      "div",
      {
        ref: wheel,
        className: "color-wheel__disc",
        role: "slider",
        "aria-label": tx("Colour wheel"),
        "aria-valuetext": hex,
        onPointerDown: (event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          pick(event);
        },
        onPointerMove: (event) => event.buttons && pick(event),
      },
      h("span", { className: "color-wheel__dim", "aria-hidden": "true" }),
      h("span", { className: "color-wheel__knob", style: { left: 50 + 50 * hsv.s * Math.cos(angle) + "%", top: 50 + 50 * hsv.s * Math.sin(angle) + "%" } }),
    ),
    h(
      "div",
      { className: "color-wheel__side" },
      h("span", { className: "color-wheel__preview", "aria-hidden": "true" }),
      brightness && h("label", { className: "set-field__label color-wheel__label" }, tx("Brightness")),
      brightness && h("input", { type: "range", className: "color-wheel__bright", min: 15, max: 100, value: Math.round(hsv.v * 100), "aria-label": tx("Brightness"), onChange: (event) => set({ ...hsv, v: Number(event.target.value) / 100 }) }),
      h("input", {
        className: "oui-field oui-mono color-wheel__hex",
        "aria-label": tx("Colour code"),
        value: text !== null ? text : hex,
        maxLength: 7,
        onChange: (event) => {
          const typed = event.target.value.trim().toLowerCase();
          setText(typed);
          const clean = typed.startsWith("#") ? typed : "#" + typed;
          if (MACRO_HEX_COLOR.test(clean)) set(hexToHsv(clean));
        },
        onBlur: () => setText(null),
      }),
    ),
  );
}

/** The ready colours plus "Custom", which opens the wheel. */
function MacroColorChoice({ value, onChange }) {
  const custom = MACRO_HEX_COLOR.test(value);
  const [wheelOpen, setWheelOpen] = useState(custom);
  const chip = (id, label, extra) =>
    h(
      "button",
      { key: id, type: "button", role: "radio", "aria-checked": extra.selected, className: cx("oui-chip macro-color-chip", extra.className, extra.selected && "is-selected"), style: extra.style, onClick: extra.onClick },
      h("span", { className: "macro-color-chip__dot", "aria-hidden": "true" }),
      label,
    );
  return h(
    React.Fragment,
    null,
    h(
      "div",
      { className: "set-chips macro-colors", role: "radiogroup", "aria-label": tx("Colour") },
      MACRO_COLOR_OPTIONS.map((option) =>
        chip(option.id, option.label, {
          className: "macro-card--" + option.id,
          selected: value === option.id,
          onClick: () => {
            setWheelOpen(false);
            onChange(option.id);
          },
        }),
      ),
      chip("custom", tx("Custom"), {
        className: cx("macro-color-chip--custom", custom && "macro-card--custom"),
        style: custom ? macroColorProps(value).style : undefined,
        selected: custom,
        onClick: () => {
          setWheelOpen(true);
          if (!custom) onChange("#7c5cff");
        },
      }),
    ),
    wheelOpen && custom && h(ColorWheel, { value, onChange }),
  );
}

const newGroupId = () => "g" + Date.now().toString(36).slice(-7) + Math.floor(Math.random() * 36).toString(36);

/** A small round button of the group editor. */
const MacroEditButton = ({ label, icon, onClick, disabled, danger }) =>
  h("button", { type: "button", className: cx("macro-edit-btn", danger && "macro-edit-btn--danger"), "aria-label": label, title: label, onClick, disabled }, icon);

/** One group: name, colour, when it shows, its macros in order (↑ ↓ ✕), and the group's own place in the list. */
function MacroGroupEditor({ group, index, count, catalog, onChange, onMove, onDelete }) {
  const [picking, setPicking] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const change = (fn) => onChange((draft) => fn(draft));
  const moveMacro = (from, to) =>
    change((draft) => {
      const [name] = draft.macros.splice(from, 1);
      draft.macros.splice(to, 0, name);
    });
  const describe = (name) => (catalog.macros.find((macro) => macro.name === name) || {}).description || "";
  const missing = (name) => catalog.loaded && !catalog.macros.some((macro) => macro.name === name);
  const pickerState = {
    macros: catalog.macros,
    loading: catalog.loading && catalog.macros.length === 0,
    selected: group.macros,
    toggle: (name) => change((draft) => (draft.macros = draft.macros.includes(name) ? draft.macros.filter((item) => item !== name) : draft.macros.concat(name))),
    clear: () => change((draft) => (draft.macros = [])),
  };

  return h(
    "section",
    { className: cx("set-group macro-group-edit", macroColorProps(group.color).className), style: macroColorProps(group.color).style, "data-group-id": group.id },
    h(
      "div",
      { className: "macro-group-edit__head" },
      h("span", { className: "macro-group-edit__swatch", "aria-hidden": "true" }),
      h("span", { className: "set-group__label macro-group-edit__title" }, group.name || tx("Group without a name")),
      h(MacroEditButton, { label: tx("Move the group up"), icon: h(Icons.ArrowUp, { size: 16 }), disabled: index === 0, onClick: () => onMove(-1) }),
      h(MacroEditButton, { label: tx("Move the group down"), icon: h(Icons.ArrowDown, { size: 16 }), disabled: index === count - 1, onClick: () => onMove(1) }),
      h(MacroEditButton, { label: tx("Delete the group"), icon: h(Icons.Trash, { size: 16 }), danger: true, onClick: () => setDeleting(true) }),
    ),
    h(TextSetting, {
      label: tx("Name"),
      value: group.name,
      placeholder: tx("e.g. Calibrations, Filament"),
      validate: (text) => (text.trim().length <= MACRO_GROUP_NAME_MAX ? text.trim() : null),
      error: tx("At most {count} characters", { count: MACRO_GROUP_NAME_MAX }),
      onCommit: (name) => change((draft) => (draft.name = name)),
    }),
    h("div", { className: "set-field__label macro-group-edit__label" }, tx("Colour")),
    h(MacroColorChoice, { value: group.color, onChange: (color) => change((draft) => (draft.color = color)) }),
    h("div", { className: "set-field__label macro-group-edit__label" }, tx("Show the card while the printer is")),
    h(
      "div",
      { className: "set-chips", role: "group", "aria-label": tx("Show the card while the printer is") },
      MACRO_STATE_OPTIONS.map((option) =>
        h(
          "button",
          { key: option.id, type: "button", "aria-pressed": group.show[option.id], className: cx("oui-chip", group.show[option.id] && "is-selected"), "data-state": option.id, onClick: () => change((draft) => (draft.show[option.id] = !draft.show[option.id])) },
          group.show[option.id] && h(Icons.Check, { size: 14 }),
          option.label,
        ),
      ),
    ),
    h("div", { className: "set-field__label macro-group-edit__label" }, tx("Macros")),
    group.macros.length === 0
      ? h("p", { className: "set-group__note macro-group-edit__empty" }, tx("No macros yet."))
      : h(
          "div",
          { className: "oui-list macro-group-edit__list" },
          group.macros.map((name, position) =>
            h(
              "div",
              { key: name, className: "oui-row macro-group-edit__row", "data-macro": name },
              h(
                "span",
                { className: "oui-row__text" },
                h("span", { className: "oui-row__name" }, name),
                missing(name) ? h("span", { className: "oui-row__meta macro-group-edit__missing" }, tx("Klipper does not have it: not shown")) : describe(name) && h("span", { className: "oui-row__meta" }, describe(name)),
              ),
              h(MacroEditButton, { label: tx("Move up"), icon: h(Icons.ArrowUp, { size: 16 }), disabled: position === 0, onClick: () => moveMacro(position, position - 1) }),
              h(MacroEditButton, { label: tx("Move down"), icon: h(Icons.ArrowDown, { size: 16 }), disabled: position === group.macros.length - 1, onClick: () => moveMacro(position, position + 1) }),
              h(MacroEditButton, { label: tx("Remove"), icon: h(Icons.Close, { size: 16 }), onClick: () => change((draft) => (draft.macros = draft.macros.filter((item) => item !== name))) }),
            ),
          ),
        ),
    h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm set-inline-btn macro-group-edit__add", onClick: () => setPicking(true) }, h(Icons.Plus, { size: 16 }), tx("Add or remove macros")),
    h(Presence, null, picking && h(MacroPicker, { state: pickerState, title: group.name || tx("Macros"), onClose: () => setPicking(false) })),
    h(ConfirmDialog, {
      open: deleting,
      tone: "danger",
      icon: h(Icons.Trash),
      title: tx("Delete the group?"),
      subtitle: group.name,
      message: tx("The card disappears; the macros stay in Klipper."),
      confirmLabel: tx("Delete"),
      onConfirm: () => {
        setDeleting(false);
        onDelete();
      },
      onCancel: () => setDeleting(false),
    }),
  );
}

/** "All the macros": a switch for each macro of the printer (on = in the card). */
function MacroVisibilityList({ macros, catalog, update }) {
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();
  const visible = catalog.macros.filter((macro) => !needle || (macro.name + " " + (macro.description || "")).toLowerCase().includes(needle));
  const setHidden = (names) => update((draft) => (draft.macros.hidden = cleanMacroNames(names)));
  return h(
    SettingsGroup,
    { title: tx("Macros in the card"), note: tx("A hidden macro stays in Klipper: it only leaves the card. Macros whose name starts with _ are never shown.") },
    h("input", { className: "oui-field macro-search", value: query, placeholder: tx("Search macros..."), "aria-label": tx("Search macros..."), onChange: (event) => setQuery(event.target.value) }),
    h(
      "div",
      { className: "macro-visibility__bulk" },
      h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm", onClick: () => setHidden(macros.hidden.filter((name) => !visible.some((macro) => macro.name === name))) }, tx("Show all")),
      h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm", onClick: () => setHidden(macros.hidden.concat(visible.map((macro) => macro.name))) }, tx("Hide all")),
    ),
    catalog.macros.length === 0
      ? h("p", { className: "set-group__note" }, catalog.loading || !catalog.loaded ? tx("Reading the macros…") : tx("Klipper has no macros."))
      : h(
          "div",
          { className: "oui-list macro-visibility" },
          visible.map((macro) =>
            h(SwitchRow, {
              key: macro.name,
              title: macro.name,
              detail: macro.description && macro.description.toLowerCase() !== "dummy" ? macro.description : null,
              checked: !macros.hidden.includes(macro.name),
              onChange: (on) => setHidden(on ? macros.hidden.filter((name) => name !== macro.name) : macros.hidden.concat(macro.name)),
            }),
          ),
        ),
  );
}

function MacrosPage() {
  const { settings, update } = useSettings();
  const catalog = useMacroCatalog();
  const macros = settings.macros;
  useEffect(() => {
    catalog.refresh(); // a macro just added to printer.cfg shows up here
  }, []);

  const updateGroup = (index) => (fn) => update((draft) => fn(draft.macros.groups[index]));
  const moveGroup = (index) => (direction) =>
    update((draft) => {
      const [group] = draft.macros.groups.splice(index, 1);
      draft.macros.groups.splice(index + direction, 0, group);
    });
  const deleteGroup = (index) => () => update((draft) => draft.macros.groups.splice(index, 1));
  const addGroup = () =>
    update((draft) => {
      draft.macros.groups.push({ id: newGroupId(), name: tx("New group"), color: "none", show: { standby: true, printing: true, paused: true }, macros: [] });
    });

  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      { title: tx("How the macros are shown"), help: ["macros", "mode"] },
      h(ChoiceRows, {
        label: tx("How the macros are shown"),
        value: macros.mode,
        onChange: (id) => update((draft) => (draft.macros.mode = id)),
        options: [
          { id: "simple", label: tx("All the macros"), detail: tx("One card with every macro of the printer; hide the ones you do not use") },
          { id: "groups", label: tx("Groups"), detail: tx("Cards of your own (Calibrations, Filament...), each with its macros, its colour and when it shows") },
        ],
      }),
    ),
    macros.mode === "simple"
      ? h(MacroVisibilityList, { macros, catalog, update })
      : h(
          React.Fragment,
          null,
          macros.groups.map((group, index) =>
            h(MacroGroupEditor, { key: group.id, group, index, count: macros.groups.length, catalog, onChange: updateGroup(index), onMove: moveGroup(index), onDelete: deleteGroup(index) }),
          ),
          macros.groups.length < MACRO_GROUPS_MAX && h("button", { type: "button", className: "oui-btn oui-btn--block macro-group-new", onClick: addGroup }, h(Icons.Plus, { size: 18 }), tx("New group")),
        ),
  );
}
