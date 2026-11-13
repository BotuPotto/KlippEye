/* ============================================================================
   59a · AI MONITOR THRESHOLDS
   The page "Soglie del monitor" of the settings menu (app/59-settings.js): the limits the backend's camera watcher uses
   to decide that a print has gone wrong. They live in the backend (app/17-backend.js reads and writes them) and the backend
   describes each one itself: label, help text, unit, minimum and maximum. This page only draws what it is told, so a
   threshold added to the backend later appears here without a new dashboard.
   ========================================================================== */

const NUMBER_TYPING_OK = /^[0-9]*[.,]?[0-9]*$/;
const TEXT_SETTING_CHARS = /^[A-Za-z0-9._:/@+-]*$/;
const AREA_FIELDS = [
  { index: 0, label: tx("From the left"), hint: tx("0 = left edge") },
  { index: 1, label: tx("From the top"), hint: tx("0 = top edge") },
  { index: 2, label: tx("Width"), hint: tx("at least 10") },
  { index: 3, label: tx("Height"), hint: tx("at least 10") },
];
const AREA_PROBLEM = tx("The area must be inside the picture and at least 10% wide and high.");
const sameList = (a, b) => Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((item, index) => item === b[index]);
const formatNumber = decimalText;

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
    h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm", onClick: onRestore }, h(Icons.RotateCcw, { size: 14 }), tx("Restore")),
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
    (invalid || error) && h("p", { className: "set-field__error", role: "alert" }, error || tx("Write a number from {min} to {max}.", { min: formatNumber(spec.min), max: formatNumber(spec.max) })),
    value !== defaultValue && h(DefaultNote, { text: tx("Default: ") + withUnit(spec, defaultValue), onRestore: () => onChange(defaultValue) }),
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
      error: tx("Only letters, digits and . _ : / @ + - (no spaces), at most {max} characters.", { max: spec.maxlen || 80 }),
      hint: spec.help,
      placeholder: "predefinito",
      onCommit: onChange,
    }),
    error && h("p", { className: "set-field__error", role: "alert" }, error),
    value !== defaultValue && h(DefaultNote, { text: tx("Default: ") + (defaultValue || tx("the service's default")), onRestore: () => onChange(defaultValue) }),
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
      !failed && h("img", { className: "set-roi__img", src: "/api/print/snapshot?t=" + stamp, alt: tx("Camera picture"), draggable: false, onError: () => setFailed(true), onLoad: () => setFailed(false) }),
      failed && h("div", { className: "set-roi__empty" }, tx("No picture from the camera (the camera is off or the KlippEye service cannot reach it)")),
      ok && h("div", { className: "set-roi__box", style: { left: area[0] + "%", top: area[1] + "%", width: area[2] + "%", height: area[3] + "%" } }, h("div", { className: "set-roi__inner", style: { top: band + "%", bottom: band + "%", left: band + "%", right: band + "%" } })),
    ),
    h(
      "div",
      { className: "set-roi__legend" },
      h("span", { className: "set-roi__swatch" }),
      tx("Watched area • movement counts only in the band between the edge and the dashed line"),
    ),
    h("button", { type: "button", className: "oui-btn oui-btn--sm set-inline-btn", onClick: () => (setFailed(false), setStamp(Date.now())) }, h(Icons.Refresh, { size: 16 }), tx("Refresh the picture")),
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
    h("div", { className: "set-num__head" }, h("span", { className: "set-num__title" }, spec.label), h("span", { className: "set-num__unit" }, tx("% of the picture"))),
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
    !sameList(value, defaultValue) && h(DefaultNote, { text: tx("Default: ") + defaultValue.join(" · "), onRestore: () => onChange(defaultValue.slice()) }),
  );
}

/**
 * 1.124: limits that depend on another setting: «In doubt from» stays below «Sure from» (the backend refuses the
 * opposite), so the slider of one stops where the other one is.
 */
function boundSpec(spec, values) {
  if (spec.key === "local_doubt" && Number.isFinite(values.local_sure)) return { ...spec, max: Math.max(spec.min, Math.min(spec.max, Math.floor((values.local_sure - 1) / 5) * 5)) };
  if (spec.key === "local_sure" && Number.isFinite(values.local_doubt)) return { ...spec, min: Math.min(spec.max, Math.max(spec.min, values.local_doubt + 1)) };
  return spec;
}

/** The right control for one setting of the backend's list. */
function BackendSettingControl({ spec: given, config }) {
  const spec = boundSpec(given, config.values || {});
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
function BackendNotice({ phase }) {
  if (phase === "loading") return h("div", { className: "set-status" }, h("span", { className: "set-status__dot" }), tx("Reading the thresholds from the KlippEye service…"));
  if (phase === "old") {
    return h(
      "div",
      { className: "set-status set-status--warn" },
      h("span", { className: "set-status__dot" }),
      h("span", null, tx("The KlippEye service on the Raspberry is older than 1.0: it has no thresholds to change. Install KlippEye 1.0 (guide: "), h("code", null, tx("docs/GUIDE.md")), tx(") and the thresholds appear here.")),
    );
  }
  return h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), tx("The KlippEye service does not answer: the thresholds cannot be read or changed now."));
}

/**
 * The names and explanations of the thresholds come from the backend in English: shown in the page's language
 * (frontend/tools/i18n.py check makes sure every one of them is in the dictionaries).
 */
const localizeBackendSchema = (data) => ({
  ...data,
  groups: data.groups.map((group) => ({ ...group, title: tx(group.title), note: group.note && tx(group.note) })),
  spec: data.spec.map((spec) => ({ ...spec, label: tx(spec.label), help: spec.help && tx(spec.help) })),
});

/**
 * 1.124: how watchful the monitor is, in one choice. Each level moves OpenCV and the local model together, so they stay
 * in step; a number changed by hand shows «Custom». Balanced = the default values.
 */
const WATCH_LEVELS = [
  {
    id: "careful",
    label: tx("Few false alarms"),
    note: tx("It speaks up only for clear problems: a bigger change that stays longer, a surer local model. A small defect may be noticed late."),
    values: { sensitivity: 40, score_threshold: 4, trigger_count: 4, persist_checks: 4, local_doubt: 45, local_sure: 85, local_every: 20 },
  },
  {
    id: "balanced",
    label: tx("Balanced"),
    note: tx("The usual values: a good compromise between noticing a problem early and not raising alarms for nothing."),
    values: { sensitivity: 35, score_threshold: 2.5, trigger_count: 3, persist_checks: 3, local_doubt: 35, local_sure: 80, local_every: 15 },
  },
  {
    id: "watchful",
    label: tx("Notices more"),
    note: tx("Smaller changes and lower local-model ratings are enough, and the local model looks more often: problems are noticed sooner, with more false alarms (the online AI, when used, filters many of them)."),
    values: { sensitivity: 28, score_threshold: 1.5, trigger_count: 2, persist_checks: 2, local_doubt: 25, local_sure: 70, local_every: 10 },
  },
];
const WATCH_KEYS = Object.keys(WATCH_LEVELS[1].values);

/** The level the values match, or "custom". */
function watchLevel(values) {
  const level = WATCH_LEVELS.find((item) => WATCH_KEYS.every((key) => Number(values[key]) === item.values[key]));
  return level ? level.id : "custom";
}
const watchLevelName = (values) => {
  const level = WATCH_LEVELS.find((item) => item.id === watchLevel(values));
  return level ? level.label : tx("Custom");
};

/** The fine numbers in the order they act: OpenCV, then the local model, then the pauses and the start. */
const FINE_GROUPS = [
  { id: "opencv", title: tx("OpenCV: what counts as a change"), keys: ["sensitivity", "score_threshold", "trigger_count", "persist_checks", "check_interval"] },
  { id: "background", title: tx("OpenCV: the background and the light"), keys: ["reference_seconds", "global_change"] },
  { id: "local", title: tx("Local model"), keys: ["local_every", "local_doubt", "local_sure"] },
  { id: "tempi", title: tx("Pauses"), keys: ["cooldown", "ai_cooldown"] },
  { id: "avvio", title: tx("When it starts checking"), keys: ["warmup_seconds", "min_progress", "hotend_tolerance"] },
];

const DETECTOR_ELSEWHERE = ["enabled", "ai_min_confidence", "ai_send_reference", "ai_online", "ai_model", "machine_masks", "expected_zone", "inside_parts", "persistent_filter", "local_enabled", "local_filter", "local_alone", "personal_learning"];
/** Used only when the camera is not calibrated (or the whole-bed watching is off): the rectangle and its outer band. */
const FALLBACK_KEYS = ["roi", "border"];

function DetectorPage({ active }) {
  const config = useBackendConfig(active);
  const calibration = useBackendJson("/api/camera/calibration", active, BACKEND_POLL_MS);
  const localModel = useBackendJson("/api/local_model", active, BACKEND_POLL_MS);
  const [askReset, setAskReset] = useState(false);
  const [fine, setFine] = useState(false);
  const data = useMemo(() => (config.data ? localizeBackendSchema(config.data) : null), [config.data]);
  const customNow = config.phase === "ok" && config.values ? watchLevel(config.values) === "custom" : false;
  // numbers changed by hand open the fine adjustments; they stay open when a level or «Restore» puts them back in step
  useEffect(() => {
    if (customNow) setFine(true);
  }, [customNow]);
  if (config.phase !== "ok" || !data) return h(BackendNotice, { phase: config.phase });
  const values = config.values;
  // shown elsewhere (1.19): the switch and the AI on the AI monitor page, the masks on Camera calibration, recording on
  // Recordings; the old detection (filter off) is no longer offered: it ignores the masks and the zone
  const thresholds = data.spec.filter((spec) => spec.group !== "recording" && !DETECTOR_ELSEWHERE.includes(spec.key));
  const byKey = Object.fromEntries(thresholds.map((spec) => [spec.key, spec]));
  const zoneActive = Boolean(calibration.phase === "ok" && calibration.data.saved && calibration.data.usable && values.expected_zone !== false);
  const fallback = thresholds.filter((spec) => FALLBACK_KEYS.includes(spec.key));
  const changed = thresholds.some((spec) => JSON.stringify(values[spec.key]) !== JSON.stringify(data.defaults ? data.defaults[spec.key] : spec.default));
  const watching = data.running && values.enabled !== false;
  const online = values.ai_online !== false;
  const localReady = localModel.phase === "ok" && localModel.data.available && values.local_enabled !== false;
  const level = watchLevel(values);
  const levelInfo = WATCH_LEVELS.find((item) => item.id === level);
  const showFine = fine || level === "custom";
  // a number that does nothing now is not offered: the pause between AI analyses without the online AI, the local
  // model's thresholds without a local model
  const hidden = (key) => (key === "ai_cooldown" && !online) || (FINE_GROUPS[2].keys.includes(key) && !localReady);
  return h(
    React.Fragment,
    null,
    h(
      "div",
      { className: cx("set-status", watching ? "set-status--ok" : "set-status--warn") },
      h("span", { className: "set-status__dot" }),
      watching ? tx("The monitor is on: it watches the camera during prints.") : tx("The monitor is off: it does not watch the camera and does not call the AI."),
    ),
    data.has_cv2 === false && h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), h("span", null, tx("OpenCV is missing on the Raspberry: the monitor cannot compare the pictures. Install it with"), " ", h("code", null, "sudo apt install python3-opencv"), ".")),
    config.problem && h("div", { className: "set-status set-status--warn", role: "alert" }, h("span", { className: "set-status__dot" }), config.problem),
    h(
      SettingsGroup,
      { title: tx("How watchful it is"), help: ["ai", "thresholds"] },
      h(ChipChoice, {
        label: tx("How watchful it is"),
        options: [...WATCH_LEVELS.map((item) => ({ id: item.id, label: item.label })), ...(level === "custom" ? [{ id: "custom", label: tx("Custom") }] : [])],
        value: level,
        onChange: (id) => {
          const chosen = WATCH_LEVELS.find((item) => item.id === id);
          if (chosen) config.set({ ...chosen.values });
        },
      }),
      h("p", { className: "set-group__note", "data-watch-level": level }, levelInfo ? levelInfo.note : tx("Some numbers were changed by hand: they are below, in «Fine adjustments». Choose a level to put them back in step.")),
      h(
        "p",
        { className: "set-group__note" },
        localReady
          ? tx("The two work together: OpenCV notices what appears and stays in the picture and shows the local model where to look closer; when the local model has a doubt, OpenCV raises an alarm sooner.")
          : tx("Without the local model only OpenCV decides when to ask the AI."),
      ),
    ),
    data.saved === false && !changed && h("p", { className: "set-group__note" }, tx("These are the default values: until you change something the KlippEye service writes no file.")),
    (level !== "custom" || fine) &&
      h(
        "button",
        { type: "button", className: "oui-btn oui-btn--quiet oui-btn--block", "aria-expanded": showFine, "data-fine": showFine ? "open" : "closed", onClick: () => setFine(!fine) },
        h(Icons.Sliders, { size: 18 }),
        showFine ? tx("Hide the fine adjustments") : tx("Fine adjustments"),
      ),
    showFine &&
      FINE_GROUPS.map((group) => {
        const specs = group.keys.map((key) => byKey[key]).filter((spec) => spec && !hidden(spec.key));
        if (!specs.length) return null;
        return h(SettingsGroup, { key: group.id, title: group.title }, specs.map((spec) => h(BackendSettingControl, { key: spec.key, spec, config })));
      }),
    showFine && !localReady && h("p", { className: "set-group__note", "data-local-hidden": "" }, tx("The local model's thresholds appear here when a local model is in use (AI monitor → Local model).")),
    showFine &&
      fallback.length > 0 &&
      h(
        SettingsGroup,
        {
          title: tx("Without camera calibration: the watched rectangle"),
          note: zoneActive
            ? tx("Not used now: the camera is calibrated, so the monitor watches the whole bed outside the parts. These are used again only if the calibration is lost or the whole-bed watching is switched off.")
            : tx("Used now: without a camera calibration the monitor watches only the outer band of this rectangle. Calibrate the camera (AI monitor → Camera calibration) to watch the whole bed."),
        },
        h("div", { className: cx("fn-fallback", zoneActive && "is-unused"), "data-fallback": zoneActive ? "unused" : "used" }, fallback.map((spec) => h(BackendSettingControl, { key: spec.key, spec, config }))),
      ),
    h(
      SettingsGroup,
      { note: tx("The thresholds stay on the Raspberry (not on the phone) and apply at once, also during a print; KlippEye updates do not touch them.") },
      askReset
        ? h(
            "div",
            { className: "set-confirm", role: "alertdialog", "aria-label": tx("Restore the thresholds?") },
            h("span", null, tx("All thresholds go back to the default values. Confirm?")),
            h(
              "div",
              { className: "set-confirm__buttons" },
              h("button", { type: "button", className: "oui-btn", onClick: () => setAskReset(false) }, tx("No")),
              h(
                "button",
                {
                  type: "button",
                  className: "oui-btn oui-btn--danger",
                  onClick: () => {
                    setAskReset(false);
                    config.reset(thresholds.map((spec) => spec.key));
                  },
                },
                tx("Yes, restore"),
              ),
            ),
          )
        : h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--block", disabled: !changed, onClick: () => setAskReset(true) }, h(Icons.RotateCcw, { size: 18 }), tx("Restore the default values")),
    ),
  );
}

/** One line for the menu list: what the monitor is doing, from the backend (null while it is not known). */
function detectorSummary(version) {
  if (version.state === "old") return tx("KlippEye service to update");
  if (version.state === "down") return tx("KlippEye service not reachable");
  return tx("How watchful it is, fine adjustments");
}
