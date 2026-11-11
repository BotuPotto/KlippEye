/* ============================================================================
   59n · YOUR NOTIFICATIONS (1.38, roadmap 6b part 9)
   Settings → Notifications, the parts read by the notification service
   (notifier/klippeye_notifier.py 1.7):
     · the text of every notification, with placeholders ({file}, {progress},
       {message}…) filled in when it goes out; empty: the service's own text;
     · how long a pause waits before it is announced (a filament runout that
       explains it goes out instead);
     · notifications of your own: print started, progress reached, little time
       left, a layer reached, a line in the console, a temperature reached —
       each with its value, its text, and "important" (the alarm sound).
   ========================================================================== */

// 1.101: each placeholder whole on its line ({total_layers} was broken in two on a phone)
const placeholderCodes = () => NOTIFY_PLACEHOLDERS.map((name, index) => h(React.Fragment, { key: name }, index ? " " : null, h("code", null, "{" + name + "}")));

/** A text of a notification: empty shows (and sends) the service's own one, in the language of the notifications. */
function NotifyTextField({ value, fallback, onCommit, testId }) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  return h(
    "label",
    { className: "set-field notify-text" },
    h("span", { className: "set-field__label" }, tx("Text")),
    h("textarea", {
      className: "oui-field set-field__input notify-text__input",
      rows: 2,
      value: text,
      maxLength: NOTIFY_TEXT_MAX,
      placeholder: fallback,
      "data-notify-text": testId,
      onChange: (event) => setText(event.target.value),
      onBlur: () => text !== value && onCommit(text.trim()),
    }),
    h("span", { className: "set-field__hint" }, value ? tx("Empty: the usual text.") : tx("Empty: the usual text (the one in grey).")),
  );
}

/** One notification of the list: on / off, and its text (and, for the pause, its delay) behind a tap. */
function NotifyKindRow({ kind, settings, update }) {
  const [open, setOpen] = useState(false);
  const own = settings.notify.texts[kind.id] || "";
  const usual = txIn(settings.language, kind.text);
  const delay = settings.notify.pauseDelay;
  return h(
    "div",
    { className: cx("notify-kind", open && "is-open"), "data-notify-kind": kind.id },
    h(SwitchRow, { title: kind.title, detail: own || usual, checked: settings.notifications[kind.id], onChange: (value) => update((draft) => (draft.notifications[kind.id] = value)) }),
    h(
      "button",
      { type: "button", className: "notify-kind__edit", "aria-expanded": open, "aria-label": tx("Change the text of «{name}»", { name: kind.title }), onClick: () => setOpen(!open) },
      h(Icons.Pencil, { size: 15 }),
      own ? tx("Your text") : tx("Change the text"),
    ),
    open &&
      h(
        "div",
        { className: "notify-kind__body" },
        h(NotifyTextField, { value: own, fallback: usual, testId: kind.id, onCommit: (text) => update((draft) => (text ? (draft.notify.texts[kind.id] = text) : delete draft.notify.texts[kind.id])) }),
        kind.id === "error" && h("p", { className: "set-group__note" }, tx("{message} is Klipper's own reason (the shutdown's, the print's error, the last «!!» line). The usual text already adds it when Klipper says one.")),
        kind.id === "paused" &&
          h(
            React.Fragment,
            null,
            h("div", { className: "set-field__label" }, tx("Wait before announcing it")),
            h(ChipChoice, {
              label: tx("Wait before announcing it"),
              value: delay === null ? 4 : delay,
              options: NOTIFY_PAUSE_DELAYS.map((seconds) => ({ id: seconds, label: seconds === 0 ? tx("At once") : seconds + " s" })),
              onChange: (seconds) => update((draft) => (draft.notify.pauseDelay = seconds)),
            }),
            h("p", { className: "set-group__note" }, tx("If a filament runout explains the pause meanwhile, that is the notification that goes out.")),
          ),
      ),
  );
}

const ruleKind = (id) => NOTIFY_RULE_KINDS.find((kind) => kind.id === id);

/** One notification of your own: when, the text, important or not, on or off. */
function NotifyRuleEditor({ rule, index, settings, update }) {
  const kind = ruleKind(rule.kind);
  const change = (fn) => update((draft) => fn(draft.notify.rules[index]));
  let when = null;
  if (kind.unit) {
    when = h(TextSetting, {
      label: rule.kind === "progress" ? tx("At (percent)") : rule.kind === "remaining" ? tx("When this many minutes are left") : tx("At layer"),
      value: String(rule.value),
      inputMode: "numeric",
      validate: (text) => {
        const number = Number(String(text).replace(",", "."));
        return Number.isFinite(number) && number >= kind.min && number <= kind.max ? Math.round(number) : null;
      },
      error: tx("From {min} to {max}", { min: kind.min, max: kind.max }),
      onCommit: (value) => change((draft) => (draft.value = value)),
    });
  } else if (rule.kind === "line") {
    when = h(TextSetting, {
      label: tx("When the console shows"),
      value: rule.value || "",
      placeholder: tx("e.g. COLOR CHANGE (from M118 in your macro)"),
      validate: (text) => (text.trim().length <= 120 ? text.trim() : null),
      onCommit: (value) => change((draft) => (draft.value = value)),
    });
  } else if (rule.kind === "temp") {
    when = h(ChipChoice, {
      label: tx("Which heater"),
      value: rule.value,
      options: [
        { id: "heater_bed", label: tx("Bed") },
        { id: "extruder", label: tx("Nozzle") },
      ],
      onChange: (value) => change((draft) => (draft.value = value)),
    });
  }
  return h(
    "section",
    { className: cx("set-group notify-rule", !rule.on && "is-off"), "data-rule": rule.id, "data-rule-kind": rule.kind },
    h(
      "div",
      { className: "macro-group-edit__head" },
      h("span", { className: "notify-rule__icon", "aria-hidden": "true" }, h(Icons.Bell, { size: 15 })),
      h("span", { className: "set-group__label macro-group-edit__title" }, kind.title),
      h(MacroEditButton, { label: tx("Remove") + " " + kind.title, icon: h(Icons.Trash, { size: 16 }), danger: true, onClick: () => update((draft) => draft.notify.rules.splice(index, 1)) }),
    ),
    when,
    rule.kind === "line" && !rule.value && h("p", { className: "set-group__note notify-rule__warn" }, tx("Write the words to look for: until then it never goes out.")),
    h(NotifyTextField, { value: rule.text, fallback: txIn(settings.language, kind.defaultText), testId: "rule-" + rule.id, onCommit: (text) => change((draft) => (draft.text = text)) }),
    h(
      "div",
      { className: "oui-list" },
      h(SwitchRow, { title: tx("Important"), detail: tx("Arrives as an alarm (like an error), not as a notice."), checked: rule.high, onChange: (high) => change((draft) => (draft.high = high)) }),
      h(SwitchRow, { title: tx("On"), checked: rule.on, onChange: (on) => change((draft) => (draft.on = on)) }),
    ),
  );
}

function NotifyRules({ settings, update }) {
  const rules = settings.notify.rules;
  const add = (kind) =>
    update((draft) => {
      if (draft.notify.rules.length >= NOTIFY_RULES_MAX) return;
      draft.notify.rules.push({ id: "r" + Date.now().toString(36), kind: kind.id, value: kind.initial === undefined ? null : kind.initial, text: "", on: true, high: false });
    });
  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      { title: tx("Your notifications"), help: ["notifications", "own"], note: tx("Progress, time left and layer go out once a print; a line or a temperature each time it happens.") },
      rules.length === 0 && h("p", { className: "set-group__note" }, tx("None yet: add one below.")),
      h(
        "div",
        { className: "set-chips notify-add", role: "group", "aria-label": tx("Add a notification") },
        NOTIFY_RULE_KINDS.map((kind) => h("button", { key: kind.id, type: "button", className: "oui-chip", "data-add-rule": kind.id, disabled: rules.length >= NOTIFY_RULES_MAX, onClick: () => add(kind) }, h(Icons.Plus, { size: 14 }), kind.title)),
      ),
    ),
    rules.map((rule, index) => h(NotifyRuleEditor, { key: rule.id, rule, index, settings, update })),
    h("p", { className: "set-group__note notify-placeholders" }, tx("In the texts:"), " ", placeholderCodes(), " — ", tx("filled in when the notification goes out (file name, percent, layer, elapsed and remaining time, Klipper's message, the console line, heater and temperature, the printer's name).")),
  );
}
