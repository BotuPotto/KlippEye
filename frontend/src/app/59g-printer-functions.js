/* ============================================================================
   59g · PRINTER FUNCTIONS
   Settings → Printer functions, in three parts (1.37): the lights (as many as the printer has: each with its name, how
   it is switched, where its state is read, whether the round button switches it; the scenes), the buttons (park, wipe,
   filament load / unload) and what tells the notifications that the filament ran out. For each button:
     · Automatic   what KlippEye found in Klipper (the usual macro names);
     · Macro       a macro of the printer, chosen from the list or typed;
     · G-code      a few lines written here (in the editor);
     · Off         the button is not shown;
   and "Create a macro": KlippEye proposes one, it opens in the editor, and when saved it goes into klippeye_macros.cfg
   (backend/printer_macros.py), included by printer.cfg; Klipper reads it after a restart (never during a print).
   Until the person has looked at this page once, the menu says "To check".
   ========================================================================== */

const FUNCTION_TITLES = {
  park: tx("Park the toolhead"),
  wipe: tx("Wipe the nozzle"),
  load: tx("Load the filament"),
  unload: tx("Unload the filament"),
};
const ACTION_MODE_LABELS = { auto: tx("Automatic"), macro: tx("Macro"), gcode: "G-code", off: tx("Not used") };
const LIGHT_HOW_LABELS = { object: tx("Output"), macro: tx("Macro"), gcode: "G-code" };

/** GET/POST to /api/printer-macros...; resolves { ok, data, message }. */
async function macrosApi(path, body) {
  try {
    const response = await fetch("/api/printer-macros" + path, body === undefined ? { cache: "no-store" } : { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) });
    let data = null;
    try {
      data = await response.json();
    } catch (error) {}
    return { ok: response.ok && Boolean(data && data.ok), data, message: (data && data.error) || "HTTP " + response.status };
  } catch (error) {
    return { ok: false, data: null, message: tx("the KlippEye service does not answer") };
  }
}

/** The one-line description of what a function does now. */
function functionNow(resolved) {
  if (resolved.mode === "off") return resolved.chosen ? tx("Off: the button is not shown.") : tx("Nothing found on your printer: the button is not shown.");
  if (resolved.mode === "gcode") return tx("Runs your G-code ({lines} lines).", { lines: resolved.command.split("\n").length });
  return resolved.chosen ? tx("Runs the macro {name}.", { name: resolved.command }) : tx("Found on your printer: the macro {name}.", { name: resolved.command });
}

/** What one light does now, in a line (`light`: resolveLightItem, or undefined when it cannot be switched). */
function lightNow(light, item) {
  if (!light) {
    if (item.mode === "object") return item.object ? tx("Klipper has no {object}: this light cannot be switched.", { object: item.object }) : tx("Choose the output of this light.");
    return tx("Write both commands, on and off.");
  }
  const how = light.mode === "object" ? tx("switched directly on {object}", { object: light.object.object }) : light.mode === "macro" ? tx("switched by the macros {on} / {off}", { on: light.on, off: light.off }) : tx("switched by your G-code");
  const state = light.object
    ? tx("the button shows the state of {object}", { object: light.object.object }) + (light.object.effects.length ? " " + tx("and of its {count} effects", { count: light.object.effects.length }) : "")
    : tx("the button cannot read the light: it shows what was asked last");
  const extra = light.dim || light.color ? " " + (light.color ? tx("Brightness and colour can be set.") : tx("Brightness can be set.")) : "";
  return how + "; " + state + "." + extra;
}

/** A text field with the printer's macros as suggestions. */
function MacroField({ label, value, macros, onCommit, testId }) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const listId = "macros-" + testId;
  return h(
    "label",
    { className: "set-field" },
    h("span", { className: "set-field__label" }, label),
    h("input", {
      className: "oui-field set-field__input",
      value: text,
      list: listId,
      autoCapitalize: "characters",
      spellCheck: false,
      "data-macro": testId,
      placeholder: tx("Name of the macro"),
      onChange: (event) => setText(event.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "")),
      onBlur: () => onCommit(text),
    }),
    h("datalist", { id: listId }, macros.map((name) => h("option", { key: name, value: name }))),
    text && macros.length > 0 && !macros.includes(text) && h("span", { className: "set-field__hint set-field__hint--warn" }, tx("Klipper does not know this macro (yet).")),
  );
}

/** The editor over the page for a G-code or a macro (the dashboard's own editor, 51-config-editor.js). */
function useFunctionEditor() {
  const [session, setSession] = useState(null);
  const open = (title, content, onSave) => setSession({ path: title, content, token: Date.now(), onSave });
  const editor = session && h(TextEditor, { session, onClose: () => setSession(null) });
  return { open, editor };
}

function ActionFunction({ id, settings, resolved, macros, update, editor, createMacro }) {
  const one = settings.functions[id];
  const set = (changes) => update((draft) => Object.assign(draft.functions[id], changes));
  const modes = ACTION_MODES.map((mode) => ({ id: mode, label: ACTION_MODE_LABELS[mode] }));
  return h(
    SettingsGroup,
    { title: FUNCTION_TITLES[id] },
    h("div", { "data-function-group": id }, h(ChipChoice, { options: modes, value: one.mode, label: FUNCTION_TITLES[id], onChange: (mode) => set({ mode }) })),
    h("p", { className: "set-group__note fn-now", "data-now": id }, functionNow(resolved[id])),
    one.mode === "macro" && h(MacroField, { label: tx("Macro"), value: one.macro, macros, testId: id, onCommit: (macro) => set({ macro }) }),
    one.mode === "gcode" &&
      h(
        "button",
        { type: "button", className: "oui-btn oui-btn--block", "data-edit-gcode": id, onClick: () => editor.open(FUNCTION_TITLES[id] + " · G-code", one.gcode || "; " + tx("write here the G-code of this button") + "\n", async (text) => set({ gcode: text })) },
        h(Icons.Code, { size: 16 }),
        one.gcode ? tx("Edit the G-code") : tx("Write the G-code"),
      ),
    h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm set-inline-btn", "data-create": id, onClick: () => createMacro(id, (name) => set({ mode: "macro", macro: name })) }, h(Icons.Plus, { size: 16 }), tx("Create a macro for this (KlippEye proposes one)")),
  );
}

/** One light of the list: its name, how it is switched, where its state is read, whether the round button switches it. */
function LightItemEditor({ item, index, count, light, capabilities, change, move, remove, editor }) {
  const outputs = capabilities.lights || [];
  const [deleting, setDeleting] = useState(false);
  const set = (changes) => change((draft) => Object.assign(draft, changes));
  const title = item.name || tx("Light");
  const objectSelect = (label, value, onChange, withNone) =>
    h(
      "label",
      { className: "set-field" },
      h("span", { className: "set-field__label" }, label),
      h(
        "select",
        { className: "oui-field set-field__input", value, "data-light-select": withNone ? "state" : "object", onChange: (event) => onChange(event.target.value) },
        withNone && h("option", { value: "auto" }, tx("Found by KlippEye")),
        withNone && h("option", { value: "" }, tx("None: show what was asked last")),
        !withNone && h("option", { value: "" }, tx("Choose…")),
        outputs.map((output) => h("option", { key: output.object, value: output.object }, output.object + (output.effects.length ? " (" + tx("{count} effects", { count: output.effects.length }) + ")" : ""))),
      ),
    );
  return h(
    "section",
    { className: "set-group fn-light", "data-light-item": item.id },
    h(
      "div",
      { className: "macro-group-edit__head" },
      h("span", { className: "fn-light__icon", "aria-hidden": "true" }, h(Icons.Bulb, { size: 16 })),
      h("span", { className: "set-group__label macro-group-edit__title" }, title),
      h(MacroEditButton, { label: tx("Move up"), icon: h(Icons.ArrowUp, { size: 16 }), disabled: index === 0, onClick: () => move(-1) }),
      h(MacroEditButton, { label: tx("Move down"), icon: h(Icons.ArrowDown, { size: 16 }), disabled: index === count - 1, onClick: () => move(1) }),
      h(MacroEditButton, { label: tx("Remove") + " " + title, icon: h(Icons.Trash, { size: 16 }), danger: true, onClick: () => setDeleting(true) }),
    ),
    h(TextSetting, { label: tx("Name"), value: item.name, placeholder: tx("e.g. Case light, LED strip"), validate: (text) => (text.trim().length <= LIGHT_NAME_MAX ? text.trim() : null), onCommit: (name) => set({ name }) }),
    h("div", { "data-function-group": "light-" + item.id }, h(ChipChoice, { options: LIGHT_HOWS.map((how) => ({ id: how, label: LIGHT_HOW_LABELS[how] })), value: item.mode, label: tx("How it is switched"), onChange: (mode) => set({ mode }) })),
    h("p", { className: "set-group__note fn-now", "data-now": "light-" + item.id }, lightNow(light, item)),
    item.mode === "object" && objectSelect(tx("The output of the light"), item.object, (object) => set({ object }), false),
    item.mode === "macro" &&
      h(
        React.Fragment,
        null,
        h(MacroField, { label: tx("Macro that switches it on"), value: item.onMacro, macros: capabilities.macros || [], testId: "light-on-" + item.id, onCommit: (onMacro) => set({ onMacro }) }),
        h(MacroField, { label: tx("Macro that switches it off"), value: item.offMacro, macros: capabilities.macros || [], testId: "light-off-" + item.id, onCommit: (offMacro) => set({ offMacro }) }),
      ),
    item.mode === "gcode" &&
      h(
        "div",
        { className: "fn-buttons" },
        h("button", { type: "button", className: "oui-btn", "data-edit-gcode": "light-on-" + item.id, onClick: () => editor.open(title + " · " + tx("G-code: on"), item.onGcode || "; " + tx("write here the G-code that switches the light on") + "\n", async (text) => set({ onGcode: text })) }, h(Icons.Code, { size: 16 }), tx("G-code: on")),
        h("button", { type: "button", className: "oui-btn", "data-edit-gcode": "light-off-" + item.id, onClick: () => editor.open(title + " · " + tx("G-code: off"), item.offGcode || "; " + tx("write here the G-code that switches the light off") + "\n", async (text) => set({ offGcode: text })) }, h(Icons.Code, { size: 16 }), tx("G-code: off")),
      ),
    item.mode !== "object" && objectSelect(tx("Where the button reads whether the light is on"), item.stateFrom, (stateFrom) => set({ stateFrom }), true),
    h("div", { className: "oui-list" }, h(SwitchRow, { title: tx("Switched by the round button"), detail: tx("The light button on the camera switches together every light that has this on."), checked: item.main, onChange: (main) => set({ main }) })),
    h(ConfirmDialog, {
      open: deleting,
      tone: "danger",
      icon: h(Icons.Trash),
      title: tx("Remove this light?"),
      subtitle: title,
      message: tx("It leaves KlippEye's list; nothing changes in Klipper."),
      confirmLabel: tx("Remove"),
      onConfirm: () => {
        setDeleting(false);
        remove();
      },
      onCancel: () => setDeleting(false),
    }),
  );
}

/** The lights: what KlippEye found or the person's list, each one's editor, adding one, finding them again, the scenes. */
function LightsSettings({ settings, resolved, capabilities, update, editor, createMacro }) {
  const lights = settings.functions.lights;
  const items = resolved.lightItems;
  const [refinding, setRefinding] = useState(false);
  /** Every change keeps the list (the first one takes what KlippEye found as it is now). */
  const edit = (fn) =>
    update((draft) => {
      const list = draft.functions.lights;
      if (!list.configured) {
        list.items = items.map((item) => ({ ...item }));
        list.configured = true;
      }
      fn(list);
    });
  const add = (extra) =>
    edit((list) => {
      if (list.items.length >= LIGHTS_MAX) return;
      list.items.push(cleanLightItem({ id: "l" + Date.now().toString(36), name: tx("Light") + " " + (list.items.length + 1), mode: "object", main: true, ...extra }, list.items.length));
    });
  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      { title: tx("Lights"), help: ["functions", "lights"] },
      h(
        "p",
        { className: "set-group__note", "data-lights-state": lights.configured ? "configured" : "found" },
        lights.configured
          ? tx("Your list of lights ({count}). The round button on the camera switches the ones marked; its arrow opens them all, with brightness, colour and scenes.", { count: items.length })
          : items.length
            ? tx("KlippEye found {count} lights on your printer (pairs of light macros, LED outputs, pins named as lights). Change anything and the list stays as you leave it.", { count: items.length })
            : tx("KlippEye found no light on your printer: add one, or create the two macros."),
      ),
      lights.configured && h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm set-inline-btn", "data-refind": "1", onClick: () => setRefinding(true) }, h(Icons.Refresh, { size: 16 }), tx("Find the lights again")),
    ),
    items.map((item, index) =>
      h(LightItemEditor, {
        key: item.id,
        item,
        index,
        count: items.length,
        light: resolved.lights.find((one) => one.id === item.id),
        capabilities,
        editor,
        change: (fn) => edit((list) => fn(list.items[index])),
        move: (direction) =>
          edit((list) => {
            const [moved] = list.items.splice(index, 1);
            list.items.splice(index + direction, 0, moved);
          }),
        remove: () => edit((list) => list.items.splice(index, 1)),
      }),
    ),
    h(
      "div",
      { className: "fn-light-add" },
      items.length < LIGHTS_MAX && h("button", { type: "button", className: "oui-btn", "data-add-light": "1", onClick: () => add({}) }, h(Icons.Plus, { size: 16 }), tx("Add a light")),
      h(
        "button",
        { type: "button", className: "oui-btn oui-btn--quiet", "data-create": "light", onClick: () => createMacro("light_on", (on) => createMacro("light_off", (off) => add({ name: tx("Light"), mode: "macro", onMacro: on, offMacro: off, stateFrom: "auto" }))) },
        h(Icons.Plus, { size: 16 }),
        tx("Create the two macros (KlippEye proposes them)"),
      ),
    ),
    lights.scenes.length > 0 &&
      h(
        SettingsGroup,
        { title: tx("Scenes"), note: tx("Saved from the lights panel (the arrow next to the light button). A tap there brings them back.") },
        h(
          "div",
          { className: "oui-list" },
          lights.scenes.map((scene, index) =>
            h(
              "div",
              { key: scene.id, className: "oui-row", "data-scene-row": scene.id },
              h("span", { className: "oui-row__text" }, h("span", { className: "oui-row__name" }, scene.name), h("span", { className: "oui-row__meta" }, tx("{count} lights", { count: Object.keys(scene.set).length }))),
              h(MacroEditButton, { label: tx("Remove") + " " + scene.name, icon: h(Icons.Trash, { size: 16 }), danger: true, onClick: () => update((draft) => draft.functions.lights.scenes.splice(index, 1)) }),
            ),
          ),
        ),
      ),
    h(ConfirmDialog, {
      open: refinding,
      tone: "neutral",
      icon: h(Icons.Refresh),
      title: tx("Find the lights again?"),
      message: tx("Your list is replaced by what KlippEye finds on the printer now (the scenes stay)."),
      confirmLabel: tx("Find again"),
      onConfirm: () => {
        setRefinding(false);
        update((draft) => {
          draft.functions.lights.configured = false;
          draft.functions.lights.items = [];
        });
      },
      onCancel: () => setRefinding(false),
    }),
  );
}

function FilamentFunction({ settings, capabilities, update, wraps, onWraps, busy }) {
  const filament = settings.functions.filament;
  const set = (changes) => update((draft) => Object.assign(draft.functions.filament, changes));
  const sensors = capabilities.sensors || [];
  const macros = (capabilities.macros || []).filter((name) => !name.startsWith(KLIPPEYE_ORIGINAL));
  const [chosen, setChosen] = useState(wraps);
  useEffect(() => setChosen(wraps), [wraps.join(",")]);
  const [phrases, setPhrases] = useState(filament.phrases.join("\n"));
  const changed = chosen.join(",") !== wraps.join(",");
  const toggle = (name) => setChosen(chosen.includes(name) ? chosen.filter((n) => n !== name) : [...chosen, name]);
  return h(
    SettingsGroup,
    { title: tx("Filament change notification") },
    h("p", { className: "set-group__note" }, tx("When one of these happens during a print, the phone gets «Filament run out, change the spool!».")),
    h(
      "div",
      { className: "oui-list" },
      h(SwitchRow, {
        title: tx("The filament sensor says the filament is gone"),
        detail: sensors.length ? sensors.join(", ") : tx("No filament sensor in your configuration"),
        checked: filament.sensor && sensors.length > 0,
        disabled: sensors.length === 0,
        onChange: (sensor) => set({ sensor }),
      }),
    ),
    h("div", { className: "set-field__label fn-subtitle" }, tx("A macro of yours runs (M600, your runout macro...)")),
    macros.length
      ? h(
          "div",
          { className: "set-chips fn-wraps", role: "group", "aria-label": tx("Macros that announce a filament change") },
          [...new Set([...macros, ...chosen])].map((name) => h("button", { key: name, type: "button", "data-wrap": name, className: cx("oui-chip", chosen.includes(name) && "is-selected"), "aria-pressed": chosen.includes(name), onClick: () => toggle(name) }, name)),
        )
      : h("p", { className: "set-group__note" }, tx("Klipper has not said its macros yet.")),
    h("p", { className: "set-group__note" }, tx("KlippEye adds to klippeye_macros.cfg a small wrapper with the same name: it writes «KlippEye: filament change» in the console and then runs your macro exactly as before. Your macro is not changed. Klipper must restart to read it.")),
    changed && h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", "data-apply-wraps": "1", disabled: busy, onClick: () => onWraps(chosen) }, tx("Apply ({count} macros)", { count: chosen.length })),
    h(
      "label",
      { className: "set-field" },
      h("span", { className: "set-field__label" }, tx("A line in the console (one per line)")),
      h("textarea", {
        className: "oui-field set-field__input fn-phrases",
        rows: 2,
        value: phrases,
        "data-phrases": "1",
        placeholder: "Printer paused due to filament runout!",
        onChange: (event) => setPhrases(event.target.value),
        onBlur: () => set({ phrases: phrases.split("\n").map((line) => line.trim()).filter(Boolean) }),
      }),
      h("span", { className: "set-field__hint" }, tx("«Printer paused due to filament runout!» is always recognised.")),
    ),
  );
}

const KLIPPEYE_ORIGINAL = "KLIPPEYE_ORIGINAL_";

function PrinterFunctionsPage({ printing }) {
  const { settings, update } = useSettings();
  const capabilities = usePrinterCapabilities();
  const resolved = usePrinterFunctions();
  const editor = useFunctionEditor();
  const [store, setStore] = useState({ macros: {}, wraps: [] });
  const [problem, setProblem] = useState("");
  const [restart, setRestart] = useState(false);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    const reply = await macrosApi("");
    if (reply.ok) setStore(reply.data);
  };
  useEffect(() => {
    load();
  }, []);
  const after = (reply) => {
    setBusy(false);
    if (!reply.ok) {
      setProblem(reply.message);
      throw new Error(reply.message);
    }
    setProblem("");
    setStore(reply.data);
    setRestart(true);
  };
  /** Proposes a macro (template from the backend), opens it in the editor; saving puts it in klippeye_macros.cfg. */
  const createMacro = async (kind, onCreated) => {
    const reply = await macrosApi("/template?kind=" + encodeURIComponent(kind));
    if (!reply.ok) return setProblem(reply.message);
    const { name, text } = reply.data;
    editor.open(name + " · klippeye_macros.cfg", (store.macros || {})[name] || text, async (edited) => {
      setBusy(true);
      after(await macrosApi("/macro", { name, text: edited }));
      setTimeout(() => onCreated(name), 400); // after the editor has closed (the light opens the second macro next)
    });
  };
  const onWraps = async (names) => {
    setBusy(true);
    try {
      after(await macrosApi("/wraps", { names }));
      update((draft) => (draft.functions.filament.macros = names));
    } catch (error) {}
  };
  const restartKlipper = async () => {
    setRestart(false);
    await moonraker.firmwareRestart();
    toast.action(tx("Klipper restarts: the new macros are read"));
  };
  const reviewed = settings.functions.reviewed;
  return h(
    React.Fragment,
    null,
    !reviewed &&
      h(
        "div",
        { className: "set-status set-status--warn fn-review", role: "status" },
        h("span", { className: "set-status__dot" }),
        h(
          "span",
          null,
          tx("Every printer does these things with its own macros. KlippEye looked at yours: check each function below, change what is not right, then confirm."),
          " ",
          h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--primary", "data-reviewed": "1", onClick: () => update((draft) => (draft.functions.reviewed = true)) }, tx("All right")),
        ),
      ),
    problem && h("div", { className: "set-status set-status--warn", role: "alert", "data-problem": "1" }, h("span", { className: "set-status__dot" }), problem),
    restart &&
      h(
        "div",
        { className: "set-status fn-restart", role: "status" },
        h("span", { className: "set-status__dot" }),
        h(
          "span",
          null,
          printing ? tx("Saved in klippeye_macros.cfg. Klipper reads it at its next restart: after the print.") : tx("Saved in klippeye_macros.cfg. Klipper reads it at its next restart."),
          " ",
          !printing && h("button", { type: "button", className: "oui-btn oui-btn--sm", "data-restart": "1", onClick: restartKlipper }, tx("Restart Klipper now")),
        ),
      ),
    h("h3", { className: "fn-section", "data-section": "lights" }, h(Icons.Bulb, { size: 18 }), tx("Lights")),
    h(LightsSettings, { settings, resolved, capabilities, update, editor, createMacro }),
    h("h3", { className: "fn-section", "data-section": "buttons" }, h(Icons.Play, { size: 18 }), tx("Buttons")),
    ACTION_FUNCTIONS.map((id) => h(ActionFunction, { key: id, id, settings, resolved, macros: capabilities.macros || [], update, editor, createMacro })),
    h("h3", { className: "fn-section", "data-section": "filament" }, h(Icons.Spool, { size: 18 }), tx("Filament")),
    h(FilamentFunction, { settings, capabilities, update, wraps: store.wraps || [], onWraps, busy }),
    editor.editor,
  );
}

/** One line for the menu list. */
function printerFunctionsSummary(settings) {
  if (!settings.functions.reviewed) return ""; // the badge "To check" says it
  const functions = settings.functions;
  const off = ACTION_FUNCTIONS.filter((id) => functions[id].mode === "off").length;
  const lights = functions.lights.configured ? functions.lights.items.length : null;
  const lightText = lights === null ? "" : lights === 1 ? tx("1 light") : tx("{count} lights", { count: lights });
  return [lightText, off ? tx("{count} off", { count: off }) : tx("All on")].filter(Boolean).join(" • ");
}
