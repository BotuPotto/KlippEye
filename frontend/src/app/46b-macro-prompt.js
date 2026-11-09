/* ============================================================================
   46b · WINDOWS OPENED BY MACROS (1.71)
   Klipper's macros can open a window with a title, some text and buttons
   (Klipper's "prompt" actions, as Mainsail and Fluidd show them): many macro
   packs ask this way (Happy Hare, RatOS, Klippain, filament changes…).
     RESPOND TYPE=command MSG="action:prompt_begin Filament change"
     RESPOND TYPE=command MSG="action:prompt_text Load the new filament, then:"
     RESPOND TYPE=command MSG="action:prompt_button Purge more|PURGE|primary"
     RESPOND TYPE=command MSG="action:prompt_footer_button Done|RESUME|primary"
     RESPOND TYPE=command MSG="action:prompt_show"
   reach the console as "// action:prompt_…" lines. The window is built from
   the console's lines: it opens on every phone and computer, comes back after
   a reload, and closes when the macro sends "action:prompt_end" (or ✕, which
   sends it). A button sends its command (name|command|colour; without a
   command, the name itself); groups (button_group_start / _end) put buttons on
   one row. The prompt lines themselves are not shown in the console.
   ========================================================================== */

const MACRO_PROMPT_LINE = /^\/\/ action:prompt_([a-z_]+)\s*(.*)$/;
const MACRO_PROMPT_COLORS = { primary: "primary", secondary: "secondary", info: "info", warning: "warning", error: "error" };

/** "// action:prompt_…" → { type, message }; anything else → null. */
function parseMacroPromptLine(message) {
  const match = String(message || "").trim().match(MACRO_PROMPT_LINE);
  if (!match) return null;
  return { type: match[1], message: match[2].trim().replace(/^"(.*)"$/, "$1") };
}

const isMacroPromptLine = (message) => MACRO_PROMPT_LINE.test(String(message || "").trim());

/** A button's "name|command|colour". */
function macroPromptButton(message) {
  const [label, command, color] = message.split("|").map((part) => (part === undefined ? undefined : part.trim()));
  return { label: label || "?", command: command || label || "", color: MACRO_PROMPT_COLORS[(color || "").toLowerCase()] || "" };
}

/**
 * The window to show now, from the console's lines (oldest first), or null: the last «begin» that was «show»n and not
 * «end»ed since. { id (the begin's time), title, items: [{type: "text", text} | {type: "buttons", buttons}], footer }.
 */
function macroPromptFromEntries(entries) {
  let begin = -1;
  for (let index = entries.length - 1; index >= 0; index--) {
    const event = parseMacroPromptLine(entries[index].msg);
    if (!event) continue;
    if (event.type === "end") return null;
    if (event.type === "begin") {
      begin = index;
      break;
    }
  }
  if (begin < 0) return null;
  const events = entries
    .slice(begin)
    .map((entry) => parseMacroPromptLine(entry.msg))
    .filter(Boolean);
  const show = events.findIndex((event) => event.type === "show");
  if (show < 0) return null;
  const items = [];
  const footer = [];
  let group = null;
  for (const event of events.slice(1, show)) {
    if (event.type === "text") items.push({ type: "text", text: event.message });
    else if (event.type === "button_group_start") {
      group = { type: "buttons", buttons: [] };
      items.push(group);
    } else if (event.type === "button_group_end") group = null;
    else if (event.type === "button") {
      if (group) group.buttons.push(macroPromptButton(event.message));
      else items.push({ type: "buttons", buttons: [macroPromptButton(event.message)] });
    } else if (event.type === "footer_button") footer.push(macroPromptButton(event.message));
  }
  const first = entries[begin];
  return { id: String(first.time || 0) + "|" + first.msg, title: events[0].message || tx("Macro"), items: items.filter((item) => item.type === "text" || item.buttons.length), footer };
}

function MacroPromptButton({ button, onSend, footer }) {
  const variant = { primary: "oui-btn--primary", error: "oui-btn--danger" }[button.color] || "";
  return h(
    "button",
    {
      type: "button",
      className: cx("oui-btn macro-prompt__btn", variant, button.color && "is-" + button.color, footer && "macro-prompt__btn--footer"),
      title: button.command,
      "data-prompt-command": button.command,
      onClick: () => onSend(button.command),
    },
    button.label,
  );
}

/** Mounted once by the application, fed the console's lines. */
function MacroPromptDialog({ entries }) {
  const prompt = useMemo(() => macroPromptFromEntries(entries), [entries]);
  const [closed, setClosed] = useState(null); // the window closed here, before Klipper's «end» arrives
  const open = Boolean(prompt) && closed !== prompt.id;
  const close = () => {
    setClosed(prompt.id);
    fireGcode('RESPOND TYPE=command MSG="action:prompt_end"');
  };
  const send = (command) => command && fireGcode(command);
  useBackHandler(() => (open ? (close(), true) : false), open);
  return h(
    Presence,
    null,
    open &&
      h(
        "div",
        { className: "confirm-overlay macro-prompt-overlay" },
        h(
          "div",
          { className: "confirm-card macro-prompt", role: "dialog", "aria-modal": "true", "aria-label": prompt.title },
          h(
            "div",
            { className: "dialog-head" },
            h("div", { className: "dialog-head__icon" }, h(Icons.Info, { size: 22 })),
            h("div", { className: "dialog-head__text" }, h("div", { className: "dialog-title" }, prompt.title), h("div", { className: "dialog-sub" }, tx("Asked by a macro"))),
            h("button", { type: "button", className: "dialog-close", "aria-label": tx("Close"), title: tx("Close"), onClick: close }, h(Icons.Close, { size: 18 })),
          ),
          h(
            "div",
            { className: "macro-prompt__body" },
            prompt.items.map((item, index) =>
              item.type === "text"
                ? h("p", { key: index, className: "macro-prompt__text" }, consoleMessage(item.text))
                : h("div", { key: index, className: "macro-prompt__row" }, item.buttons.map((button, n) => h(MacroPromptButton, { key: n, button, onSend: send }))),
            ),
          ),
          prompt.footer.length > 0 && h("div", { className: "oui-btn-row macro-prompt__footer" }, prompt.footer.map((button, n) => h(MacroPromptButton, { key: n, button, onSend: send, footer: true }))),
        ),
      ),
  );
}
