/* ============================================================================
   59a · AI MONITOR THRESHOLDS
   The page "Soglie del monitor" of the settings menu (app/59-settings.js): the limits the backend's camera watcher uses
   to decide that a print has gone wrong. They live in the backend (app/17-brain.js reads and writes them) and the backend
   describes each one itself: label, help text, unit, minimum and maximum. This page only draws what it is told, so a
   threshold added to the backend later appears here without a new dashboard.
   ========================================================================== */

const NUMBER_TYPING_OK = /^[0-9]*[.,]?[0-9]*$/;
const TEXT_SETTING_CHARS = /^[A-Za-z0-9._:/@+-]*$/;
const AREA_FIELDS = [
  { index: 0, label: "Da sinistra", hint: "0 = bordo sinistro" },
  { index: 1, label: "Dall'alto", hint: "0 = bordo alto" },
  { index: 2, label: "Larghezza", hint: "almeno 10" },
  { index: 3, label: "Altezza", hint: "almeno 10" },
];
const AREA_PROBLEM = "L'area deve stare dentro l'immagine ed essere larga e alta almeno il 10%.";
const sameList = (a, b) => Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((item, index) => item === b[index]);
const formatNumber = (value) => String(value).replace(".", ",");

/** The number in `text` if it is a valid value for `spec` (inside its bounds, whole for an int), otherwise null. */
function parseSpecNumber(spec, text) {
  const clean = String(text).trim().replace(",", ".");
  if (clean === "" || !Number.isFinite(Number(clean))) return null;
  const number = Number(clean);
  if (spec.type === "int" && !Number.isInteger(number)) return null;
  return number >= spec.min && number <= spec.max ? number : null;
}

/** Whether a rectangle [left, top, width, height] (in % of the picture) is one the backend accepts. */
const validArea = (area) => area.every(Number.isFinite) && area[0] >= 0 && area[1] >= 0 && area[2] >= 10 && area[3] >= 10 && area[0] + area[2] <= 100.05 && area[1] + area[3] <= 100.05;

/** "Di serie: 35 %" with a button to go back to it, shown only when the value is not the usual one. */
function DefaultNote({ text, onRestore }) {
  return h(
    "div",
    { className: "set-num__foot" },
    h("span", null, text),
    h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm", onClick: onRestore }, h(Icons.RotateCcw, { size: 14 }), "Ripristina"),
  );
}

/** A number: typed in the box or moved on the slider. A value outside the bounds is not taken; when the box is left the last good one comes back. */
function NumberSetting({ spec, value, defaultValue, error, onChange }) {
  const [draft, setDraft] = useState(formatNumber(value));
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    if (!focused) setDraft(formatNumber(value));
  }, [value, focused]);
  const parsed = parseSpecNumber(spec, draft);
  const invalid = parsed === null;
  const step = spec.step || (spec.type === "int" ? 1 : 0.5);
  const type = (text) => {
    if (!NUMBER_TYPING_OK.test(text)) return;
    setDraft(text);
    const number = parseSpecNumber(spec, text);
    if (number !== null && number !== value) onChange(number);
  };
  const inputId = "set-num-" + spec.key;
  return h(
    "div",
    { className: "oui-tile set-num" },
    h(
      "div",
      { className: "set-num__head" },
      h("label", { className: "set-num__title", htmlFor: inputId }, spec.label),
      h(
        "span",
        { className: "set-num__box" },
        h("input", {
          id: inputId,
          className: cx("oui-field", "oui-field--num", "set-num__input", (invalid || error) && "is-invalid"),
          value: draft,
          inputMode: spec.type === "int" ? "numeric" : "decimal",
          autoCapitalize: "off",
          autoCorrect: "off",
          spellCheck: false,
          "aria-invalid": invalid || Boolean(error),
          onChange: (event) => type(event.target.value),
          onFocus: () => setFocused(true),
          onBlur: () => setFocused(false),
          onKeyDown: (event) => event.key === "Enter" && event.currentTarget.blur(),
        }),
        spec.unit && h("span", { className: "set-num__unit" }, spec.unit),
      ),
    ),
    spec.help && h("p", { className: "set-num__help" }, spec.help),
    h("input", {
      type: "range",
      className: "set-num__range",
      "aria-label": spec.label,
      min: spec.min,
      max: spec.max,
      step,
      value: parsed === null ? value : parsed,
      onChange: (event) => {
        const number = Number(event.target.value);
        setDraft(formatNumber(number));
        onChange(number);
      },
    }),
    h("div", { className: "set-num__bounds" }, h("span", null, withUnit(spec, spec.min)), h("span", null, withUnit(spec, spec.max))),
    (invalid || error) && h("p", { className: "set-field__error", role: "alert" }, error || "Scrivi un numero da " + formatNumber(spec.min) + " a " + formatNumber(spec.max) + "."),
    value !== defaultValue && h(DefaultNote, { text: "Di serie: " + withUnit(spec, defaultValue), onRestore: () => onChange(defaultValue) }),
  );
}

/** A short text (the AI model); wrong characters are refused as they are typed. */
function TextValueSetting({ spec, value, defaultValue, error, onChange }) {
  return h(
    "div",
    { className: "oui-tile set-num" },
    h(TextSetting, {
      label: spec.label,
      value,
      validate: (text) => {
        const clean = text.trim();
        return TEXT_SETTING_CHARS.test(clean) && clean.length <= (spec.maxlen || 80) ? clean : null;
      },
      error: "Solo lettere, numeri e . _ : / @ + - (niente spazi), al massimo " + (spec.maxlen || 80) + " caratteri.",
      hint: spec.help,
      placeholder: "predefinito",
      onCommit: onChange,
    }),
    error && h("p", { className: "set-field__error", role: "alert" }, error),
    value !== defaultValue && h(DefaultNote, { text: "Di serie: " + (defaultValue || "quello predefinito del servizio"), onRestore: () => onChange(defaultValue) }),
  );
}

/** The camera picture with the watched rectangle and its outer band drawn over it, so that the numbers can be judged by eye. */
function RoiPreview({ area, band }) {
  const [stamp, setStamp] = useState(() => Date.now());
  const [failed, setFailed] = useState(false);
  const ok = validArea(area);
  return h(
    "div",
    { className: "set-roi" },
    h(
      "div",
      { className: "set-roi__frame" },
      !failed && h("img", { className: "set-roi__img", src: "/api/print/snapshot?t=" + stamp, alt: "Foto della camera", draggable: false, onError: () => setFailed(true), onLoad: () => setFailed(false) }),
      failed && h("div", { className: "set-roi__empty" }, "Nessuna foto dalla camera (la camera è spenta o il backend non la raggiunge)"),
      ok && h("div", { className: "set-roi__box", style: { left: area[0] + "%", top: area[1] + "%", width: area[2] + "%", height: area[3] + "%" } }, h("div", { className: "set-roi__inner", style: { top: band + "%", bottom: band + "%", left: band + "%", right: band + "%" } })),
    ),
    h(
      "div",
      { className: "set-roi__legend" },
      h("span", { className: "set-roi__swatch" }),
      "Area controllata • il movimento conta solo nella fascia tra il bordo e la linea tratteggiata",
    ),
    h("button", { type: "button", className: "oui-btn oui-btn--sm set-inline-btn", onClick: () => (setFailed(false), setStamp(Date.now())) }, h(Icons.Refresh, { size: 16 }), "Aggiorna la foto"),
  );
}

/** The rectangle: four numbers (they are sent together once all four make sense) and the picture. */
function AreaSetting({ spec, value, defaultValue, error, band, onChange }) {
  const [drafts, setDrafts] = useState(() => value.map(formatNumber));
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    if (!focused) setDrafts(value.map(formatNumber));
  }, [value.join("|"), focused]);
  const numbers = drafts.map((text) => (NUMBER_TYPING_OK.test(text) && text.trim() !== "" ? Number(text.replace(",", ".")) : NaN));
  const good = validArea(numbers);
  const type = (index, text) => {
    if (!NUMBER_TYPING_OK.test(text)) return;
    const next = drafts.slice();
    next[index] = text;
    setDrafts(next);
    const area = next.map((item) => (item.trim() === "" ? NaN : Number(item.replace(",", "."))));
    if (validArea(area) && !sameList(area, value)) onChange(area);
  };
  return h(
    "div",
    { className: "oui-tile set-num" },
    h("div", { className: "set-num__head" }, h("span", { className: "set-num__title" }, spec.label), h("span", { className: "set-num__unit" }, "% dell'immagine")),
    spec.help && h("p", { className: "set-num__help" }, spec.help),
    h(RoiPreview, { area: good ? numbers : value, band }),
    h(
      "div",
      { className: "set-grid" },
      AREA_FIELDS.map((field) =>
        h(
          "label",
          { key: field.index, className: "set-field" },
          h("span", { className: "set-field__label" }, field.label),
          h("input", {
            className: cx("oui-field", "oui-field--num", "set-field__input", !good && "is-invalid"),
            value: drafts[field.index],
            inputMode: "decimal",
            autoCapitalize: "off",
            autoCorrect: "off",
            spellCheck: false,
            "aria-label": field.label + " (" + field.hint + ")",
            onChange: (event) => type(field.index, event.target.value),
            onFocus: () => setFocused(true),
            onBlur: () => setFocused(false),
            onKeyDown: (event) => event.key === "Enter" && event.currentTarget.blur(),
          }),
        ),
      ),
    ),
    (!good || error) && h("p", { className: "set-field__error", role: "alert" }, error || AREA_PROBLEM),
    !sameList(value, defaultValue) && h(DefaultNote, { text: "Di serie: " + defaultValue.join(" · "), onRestore: () => onChange(defaultValue.slice()) }),
  );
}

/** The right control for one setting of the backend's list. */
function BrainSettingControl({ spec, config }) {
  const value = config.values[spec.key];
  const defaultValue = config.data.defaults ? config.data.defaults[spec.key] : spec.default;
  const error = config.errors[spec.key];
  const change = (next) => config.set({ [spec.key]: next });
  if (value === undefined) return null;
  if (spec.type === "bool") return h(SwitchRow, { title: spec.label, detail: spec.help, checked: value === true, onChange: change });
  if (spec.type === "int" || spec.type === "float") return h(NumberSetting, { spec, value, defaultValue, error, onChange: change });
  if (spec.type === "text") return h(TextValueSetting, { spec, value, defaultValue, error, onChange: change });
  if (spec.type === "area" && Array.isArray(value)) return h(AreaSetting, { spec, value, defaultValue, error, band: Number(config.values.border) || 25, onChange: change });
  return null; // a kind of setting this dashboard does not know yet: left out, the rest still works
}

/** Why the thresholds are not there, in words. */
function BrainNotice({ phase }) {
  if (phase === "loading") return h("div", { className: "set-status" }, h("span", { className: "set-status__dot" }), "Leggo le soglie dal backend…");
  if (phase === "old") {
    return h(
      "div",
      { className: "set-status set-status--warn" },
      h("span", { className: "set-status__dot" }),
      h("span", null, "Il backend sul Raspberry è una versione precedente alla 1.0: non ha soglie da modificare. Installa KlippEye 1.0 (guida: ", h("code", null, "docs/GUIDA.md"), ") e le soglie compaiono qui."),
    );
  }
  return h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), "Il backend non risponde: le soglie non si possono leggere né cambiare adesso.");
}

function DetectorPage({ active }) {
  const config = useBrainConfig(active);
  const [askReset, setAskReset] = useState(false);
  if (config.phase !== "ok" || !config.data) return h(BrainNotice, { phase: config.phase });
  const { data } = config;
  const changed = data.spec.some((spec) => JSON.stringify(config.values[spec.key]) !== JSON.stringify(data.defaults ? data.defaults[spec.key] : spec.default));
  const watching = data.running && config.values.enabled !== false;
  return h(
    React.Fragment,
    null,
    h(
      "div",
      { className: cx("set-status", watching ? "set-status--ok" : "set-status--warn") },
      h("span", { className: "set-status__dot" }),
      watching ? "Il monitor è acceso: durante le stampe guarda la camera." : "Il monitor è spento: non guarda la camera e non chiama l'IA.",
    ),
    data.has_cv2 === false && h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), h("span", null, "Sul Raspberry manca OpenCV: il monitor non può confrontare le foto. Installalo con ", h("code", null, "sudo apt install python3-opencv"), ".")),
    config.problem && h("div", { className: "set-status set-status--warn", role: "alert" }, h("span", { className: "set-status__dot" }), config.problem),
    data.saved === false && !changed && h("p", { className: "set-group__note" }, "Sono i valori di sempre: finché non cambi qualcosa il backend non scrive nessun file."),
    data.groups.map((group) => {
      const specs = data.spec.filter((spec) => spec.group === group.id);
      if (!specs.length) return null;
      const switches = specs.filter((spec) => spec.type === "bool");
      const others = specs.filter((spec) => spec.type !== "bool");
      return h(
        SettingsGroup,
        { key: group.id, title: group.title, note: group.note },
        switches.length > 0 && h("div", { className: "oui-list" }, switches.map((spec) => h(BrainSettingControl, { key: spec.key, spec, config }))),
        others.map((spec) => h(BrainSettingControl, { key: spec.key, spec, config })),
      );
    }),
    h(
      SettingsGroup,
      { note: "Le soglie restano sul Raspberry (non sul telefono) e valgono subito, anche durante una stampa; gli aggiornamenti di KlippEye non le toccano." },
      askReset
        ? h(
            "div",
            { className: "set-confirm", role: "alertdialog", "aria-label": "Ripristinare le soglie?" },
            h("span", null, "Tutte le soglie tornano ai valori di sempre. Confermi?"),
            h(
              "div",
              { className: "set-confirm__buttons" },
              h("button", { type: "button", className: "oui-btn", onClick: () => setAskReset(false) }, "No"),
              h(
                "button",
                {
                  type: "button",
                  className: "oui-btn oui-btn--danger",
                  onClick: () => {
                    setAskReset(false);
                    config.reset();
                  },
                },
                "Sì, ripristina",
              ),
            ),
          )
        : h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--block", disabled: !changed, onClick: () => setAskReset(true) }, h(Icons.RotateCcw, { size: 18 }), "Ripristina i valori di sempre"),
    ),
  );
}

/** One line for the menu list: what the monitor is doing, from the backend (null while it is not known). */
function detectorSummary(version) {
  if (version.state === "old") return "Backend da aggiornare";
  if (version.state === "down") return "Backend non raggiungibile";
  return "Sensibilità, area controllata, pause";
}
