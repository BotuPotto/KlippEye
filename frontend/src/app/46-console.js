/* ============================================================================
   46 · CONSOLE
   Live G-code console. Entries come from Moonraker's gcode store (polled) and,
   when the websocket is available, from its live notifications. Everything that
   arrives is also handed to the fault banner so it can notice a shutdown.
   ========================================================================== */

const CONSOLE_STORE_COUNT = 150;
const CONSOLE_MAX_ENTRIES = 200;
const WEBSOCKET_RETRY_MS = 3000;
/** While the websocket is subscribed and delivers every new line, the stored lines are only read this often (otherwise every POLL_MS.consoleStore). */
const CONSOLE_SAFETY_POLL_MS = 3000;

/** Style modifier (css/46-console.css) for a console line, by what the line says. */
function consoleColor(message, isCommand) {
  if (isCommand) return "log--command";
  const lower = message.toLowerCase();
  if (lower.includes("unknown") || lower.includes("error") || lower.includes("!!")) return "log--error";
  if (lower.includes("warning")) return "log--warn";
  if (lower.includes("homed") || lower.includes("ok") || lower.includes("ready")) return "log--ok";
  return "log--info";
}

/** gcode-store item (or a plain string from a websocket notification) → console entry. */
function toConsoleEntry(item) {
  const record = typeof item === "string" ? { message: item, type: "response", time: Date.now() / 1000 } : item;
  const message = record.message || "";
  const isCommand = record.type === "command";
  return { t: formatUnixTime(record.time), msg: message, color: consoleColor(message, isCommand), isCommand, time: record.time || 0 };
}

/** Temperature reports ("ok B:60 /60 T0:200 /200", M105 answers...) are noise. */
function isTemperatureReport(message) {
  if (/B:\s*\d+\.?\d*\s*\/\s*\d+\.?\d*/i.test(message) && /T0?:\s*\d+\.?\d*/i.test(message)) return true;
  if (/T0?:\s*\d+\.?\d*\s*\/\s*\d+\.?\d*/i.test(message) && /B:\s*\d+/i.test(message)) return true;
  if (/^ok\s+B:/i.test(message) || /^ok\s+T/i.test(message)) return true;
  return /B:\d+\.?\d*\s*\/\s*\d+\.?\d*\s*@:\s*\d+/i.test(message);
}

/**
 * Other features watch the same G-code store (a calibration looking for its "!!" error line, say)
 * without a second poll: `onConsoleStore(listener)` receives every batch and returns the unsubscribe.
 */
const consoleStoreListeners = new Set();
const onConsoleStore = (listener) => {
  consoleStoreListeners.add(listener);
  return () => consoleStoreListeners.delete(listener);
};

/**
 * Console entries plus `echo(lines)` to append local lines ({ msg, color }).
 * `onStore(items)` receives every batch of raw store items.
 */
function useConsoleFeed(onStore) {
  const [entries, setEntries] = useState([]);
  const onStoreRef = useRef(onStore);
  const echoPending = useRef(false); // local lines are replaced by the server's own record on the next poll
  onStoreRef.current = onStore;

  useEffect(() => {
    let socket = null;
    let retryTimer = null;
    let lastSignature = "";
    let closed = false;
    let socketLive = false; // subscribed: new lines arrive by themselves
    let lastRead = 0;

    const poll = async () => {
      if (socketLive && !echoPending.current && Date.now() - lastRead < CONSOLE_SAFETY_POLL_MS) return;
      lastRead = Date.now();
      try {
        const json = await fetchJson("/server/gcode_store?count=" + CONSOLE_STORE_COUNT);
        const store = (json.result && json.result.gcode_store) || [];
        if (store.length === 0) return;
        store.sort((a, b) => (a.time || 0) - (b.time || 0));
        const last = store[store.length - 1];
        const signature = store.length + "|" + last.time + "|" + last.message;
        if (signature !== lastSignature || echoPending.current) {
          lastSignature = signature;
          echoPending.current = false;
          setEntries(store.map(toConsoleEntry));
        }
        onStoreRef.current(store);
        consoleStoreListeners.forEach((listener) => listener(store));
      } catch (e) {}
    };

    const connect = () => {
      try {
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        socket = new WebSocket(protocol + "//" + location.host + "/websocket");
        socket.onopen = () =>
          socket.send(JSON.stringify({ jsonrpc: "2.0", method: "server.gcode_store.subscribe", params: { count: CONSOLE_STORE_COUNT }, id: 1 }));
        socket.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.id === 1 && data.result) socketLive = true; // the answer to our subscription
            if (data.method !== "notify_gcode_response") return;
            const items = data.params || [];
            if (items.length === 0) return;
            setEntries((previous) => previous.concat(items.map(toConsoleEntry)).slice(-CONSOLE_MAX_ENTRIES));
            const records = items.map((item) => (typeof item === "string" ? { message: item, time: Date.now() / 1000 } : item));
            onStoreRef.current(records);
            consoleStoreListeners.forEach((listener) => listener(records));
          } catch (e) {}
        };
        socket.onclose = () => {
          socketLive = false;
          if (!closed) retryTimer = setTimeout(connect, WEBSOCKET_RETRY_MS);
        };
        socket.onerror = () => {
          socketLive = false;
          try {
            socket.close();
          } catch (e) {}
        };
      } catch (e) {
        retryTimer = setTimeout(connect, WEBSOCKET_RETRY_MS);
      }
    };

    /** A socket that sat through a sleep may be dead without knowing it: replace it. */
    const reconnect = () => {
      socketLive = false;
      clearTimeout(retryTimer);
      if (socket) {
        socket.onclose = null;
        try {
          socket.close();
        } catch (e) {}
      }
      connect();
    };

    const stopPolling = startPolling(poll, POLL_MS.consoleStore);
    connect();
    const stopListening = onResume((info) => wasAwayLong(info) && !closed && reconnect());

    return () => {
      closed = true;
      stopPolling();
      stopListening();
      clearTimeout(retryTimer);
      if (socket) {
        try {
          socket.close();
        } catch (e) {}
      }
    };
  }, []);

  const echo = (lines) => {
    echoPending.current = true;
    const t = localTimeString();
    setEntries((previous) => previous.concat(lines.map((line) => ({ t, msg: line.msg, color: line.color, seq: ++consoleEchoSeq }))));
  };

  return { entries, echo };
}

/** Sends a command typed by the user (or a multi-line script) and echoes it. */
function sendFromConsole(script, echo) {
  echo([...script.split("\n").map((line) => ({ msg: `> ${line}`, color: "log--input" })), { msg: "ok", color: "log--dim" }]);
  fireGcode(script);
}

/* ---------------------------------------------------------------------------
   How the console is shown (1.34): kept on this device
     autoscroll   follow the newest line (off: the log stays where it is);
     newestOnTop  the newest line first;
     showTemps    the temperature reports too (hidden by default: noise);
   and "clear", which empties the view (Klipper keeps its lines; the view shows
   only what comes after).
   ------------------------------------------------------------------------- */
const CONSOLE_PREFS_KEY = "ke_console_prefs";
let consoleEchoSeq = 0; // the lines KlippEye adds itself (echo) have no Klipper time: they are told apart by this

const consoleViewStore = (() => {
  const saved = storage.getJson(CONSOLE_PREFS_KEY) || {};
  let view = { autoscroll: saved.autoscroll !== false, newestOnTop: saved.newestOnTop === true, showTemps: saved.showTemps === true, clearedAt: 0, clearedSeq: 0 };
  const listeners = new Set();
  const emit = () => listeners.forEach((listener) => listener());
  return {
    snapshot: () => view,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    set(change) {
      view = { ...view, ...change };
      storage.set(CONSOLE_PREFS_KEY, JSON.stringify({ autoscroll: view.autoscroll, newestOnTop: view.newestOnTop, showTemps: view.showTemps }));
      emit();
    },
    clear(entries) {
      const newest = entries.reduce((max, entry) => Math.max(max, entry.time || 0), view.clearedAt);
      view = { ...view, clearedAt: newest, clearedSeq: consoleEchoSeq };
      emit();
    },
  };
})();

function useConsoleView() {
  return useSyncExternalStore(consoleViewStore.subscribe, consoleViewStore.snapshot);
}

/**
 * 1.69: moonraker-timelapse sends its settings to its macros (_SET_TIMELAPSE_SETUP ENABLE=… VERBOSE=… PARK_ENABLE=…)
 * each time Moonraker or Klipper starts: a long line nobody typed, after every «Save» of the timelapse settings. Not
 * shown (Klipper still gets it).
 */
const isAddonSetupLine = (message) => /^_SET_TIMELAPSE_SETUP\b/i.test(message);

/** The lines to show, in the order to show them. */
function visibleConsoleEntries(entries, view, order = true) {
  const shown = entries.filter((entry) => !isAddonSetupLine(String(entry.msg || "")) && !isMacroPromptLine(entry.msg) && (view.showTemps || !isTemperatureReport(String(entry.msg || ""))) && (entry.time ? entry.time > view.clearedAt : (entry.seq || 0) > view.clearedSeq));
  return order && view.newestOnTop ? shown.reverse() : shown;
}

/** Clear, the options (autoscroll, newest on top, temperatures) and full screen: the buttons of a console's title bar. */
function ConsoleTools({ entries, fullscreen, onFullscreen }) {
  const view = useConsoleView();
  const menu = useDropdown();
  const option = (key, title, subtitle) =>
    h(
      "button",
      { key, type: "button", className: "oui-menu__item console-option", role: "menuitemcheckbox", "aria-checked": view[key], "data-option": key, onClick: () => consoleViewStore.set({ [key]: !view[key] }) },
      h("span", { className: "oui-menu__icon" }, view[key] ? h(Icons.Check, { size: 18 }) : null),
      h("span", { className: "oui-menu__text" }, h("span", { className: "oui-menu__title" }, title), h("span", { className: "oui-menu__sub" }, subtitle)),
    );
  return h(
    "div",
    { className: "console-tools" },
    h("button", { type: "button", className: "icon-btn", title: tx("Clear the console"), "aria-label": tx("Clear the console"), onClick: () => consoleViewStore.clear(entries) }, h(Icons.Trash, { size: 18 })),
    h("button", { type: "button", ref: menu.anchorRef, className: cx("icon-btn", menu.open && "is-active"), title: tx("Console options"), "aria-label": tx("Console options"), "aria-haspopup": "menu", "aria-expanded": menu.open, onClick: menu.toggle }, h(Icons.Sliders, { size: 18 })),
    h(
      DropdownMenu,
      { menu },
      option("autoscroll", tx("Autoscroll"), tx("Follow the newest line")),
      option("newestOnTop", tx("Newest on top"), tx("The latest line first")),
      option("showTemps", tx("Show temperatures"), tx("The temperature reports too")),
    ),
    onFullscreen &&
      h(
        "button",
        { type: "button", className: "icon-btn", title: fullscreen ? tx("Leave full screen") : tx("Full screen"), "aria-label": fullscreen ? tx("Leave full screen") : tx("Full screen"), onClick: onFullscreen },
        h(fullscreen ? Icons.Shrink : Icons.Expand, { size: 18 }),
      ),
  );
}

/* ---------------------------------------------------------------------------
   UI
   ------------------------------------------------------------------------- */
const FOLLOW_TAIL_PX = 80;

/* ---------------------------------------------------------------------------
   What a line says (1.69): the "!! " and "// " marks Klipper puts in front are
   dropped (the colour already says it), and the little HTML that Klipper, its modules and many macros write
   is drawn instead of printed: <a class="command">SAVE_CONFIG</a> becomes a link that puts SAVE_CONFIG in the
   input field, <b>, <i>, <br>, a coloured <span>… Everything else (scripts, images, frames, events) is left out:
   only the tags and attributes listed here get through.
   ------------------------------------------------------------------------- */
const CONSOLE_TAGS = new Set(["a", "b", "strong", "i", "em", "u", "s", "small", "code", "span", "div", "p", "pre", "br", "ul", "ol", "li", "font"]);
const CONSOLE_DROPPED_TAGS = new Set(["script", "style", "iframe", "object", "embed", "template", "noscript", "svg", "math", "img", "video", "audio"]);
const CONSOLE_SAFE_COLOR = /^(#[0-9a-f]{3,8}|[a-z]{3,20}|rgba?\([\d\s.,%]+\)|hsla?\([\d\s.,%deg]+\))$/i;

/** The text to show: the marks Klipper puts in front of its answers dropped. */
function consoleDisplayText(message) {
  return String(message || "")
    .replace(/^!! /, "")
    .replace(/\n!! /g, "\n")
    .replace(/^\/\/ /, "")
    .replace(/\n\/\/ /g, "\n")
    .replace(/^echo:/, "")
    .trim();
}

function consoleColorStyle(element) {
  const raw = element.getAttribute("color") || ((element.getAttribute("style") || "").match(/(?:^|;)\s*color\s*:\s*([^;]+)/i) || [])[1] || "";
  const color = raw.trim();
  return color && CONSOLE_SAFE_COLOR.test(color) ? { color } : undefined;
}

/** HTML nodes → React elements, through the list of allowed tags. */
function consoleNodes(nodes, onPick, path) {
  const out = [];
  Array.from(nodes).forEach((node, index) => {
    const key = path + "." + index;
    if (node.nodeType === 3) {
      out.push(node.nodeValue);
      return;
    }
    if (node.nodeType !== 1) return;
    const tag = node.nodeName.toLowerCase();
    if (CONSOLE_DROPPED_TAGS.has(tag)) return;
    if (!CONSOLE_TAGS.has(tag)) {
      out.push(...consoleNodes(node.childNodes, onPick, key)); // an unknown tag: its text only
      return;
    }
    if (tag === "br") {
      out.push(h("br", { key }));
      return;
    }
    const children = consoleNodes(node.childNodes, onPick, key);
    const style = consoleColorStyle(node);
    if (tag === "a") {
      const classes = (node.getAttribute("class") || "").split(/\s+/);
      const href = node.getAttribute("href") || "";
      if (classes.includes("command")) {
        const command = (node.textContent || "").trim();
        out.push(
          h(
            "a",
            {
              key,
              role: "button",
              tabIndex: 0,
              className: "log-cmd",
              style,
              title: tx("Click to copy into the input field"),
              onClick: (event) => {
                event.stopPropagation();
                if (onPick) onPick(command);
              },
              onKeyDown: (event) => event.key === "Enter" && onPick && onPick(command),
            },
            children,
          ),
        );
      } else if (/^https?:\/\//i.test(href)) {
        out.push(h("a", { key, href, target: "_blank", rel: "noopener noreferrer", className: "log-link", style }, children));
      } else out.push(h("span", { key, style }, children));
      return;
    }
    out.push(h(tag === "font" ? "span" : tag, { key, style, className: tag === "code" ? "log-code" : undefined }, children));
  });
  return out;
}

/** What a console line shows: plain text, or the HTML in it drawn safely. */
function consoleMessage(message, onPick) {
  const text = consoleDisplayText(message);
  if (!/[<&]/.test(text) || typeof DOMParser === "undefined") return text;
  try {
    const doc = new DOMParser().parseFromString("<body>" + text.replace(/\r\n|\r|\n/g, "<br>") + "</body>", "text/html");
    return consoleNodes(doc.body.childNodes, onPick, "m");
  } catch (e) {
    return text;
  }
}

function ConsoleLine({ entry, onPick, lineKey }) {
  if (entry.isCommand) {
    return h(
      "div",
      { className: "log-line log-line--pick", "data-line": lineKey, title: tx("Click to copy into the input field"), onClick: () => onPick(entry.msg) },
      h("span", { className: "log-time" }, entry.t),
      h("span", { className: cx(entry.color, "log-msg") }, entry.msg),
    );
  }
  return h("div", { className: "log-line", "data-line": lineKey }, h("span", { className: "log-time" }, entry.t), h("span", { className: cx(entry.color, "log-msg") }, consoleMessage(entry.msg, onPick)));
}

/** A key that stays the same for a line when the list is read again or the oldest lines drop off. */
function consoleLineKeys(shown) {
  const seen = new Map();
  return shown.map((entry) => {
    const base = (entry.time ? "t" + entry.time : "s" + (entry.seq || 0)) + "|" + entry.msg;
    const count = (seen.get(base) || 0) + 1;
    seen.set(base, count);
    return base + "|" + count;
  });
}

/**
 * The scrolling log itself: follows the newest line (at the bottom, or at the top with "newest on top") while the reader
 * is there and autoscroll is on, and lets a click on a command line hand it to `onPick`. `className` adds to the well's
 * own (the dock's drawer and the full screen set its height).
 */
function ConsoleLog({ entries, onPick, className }) {
  const view = useConsoleView();
  const listRef = useRef(null);
  const following = useRef(true);
  const shown = visibleConsoleEntries(entries, view);
  const keys = consoleLineKeys(shown);

  // Not following (autoscroll off, or the reader scrolled away): the line at the top of the view stays where it is,
  // even when new lines come in above it or the oldest ones drop off the list (before 1.69 the text slid by).
  const anchor = useRef(null);
  const list = listRef.current;
  if (list && !(view.autoscroll && following.current)) {
    const top = list.getBoundingClientRect().top;
    const first = Array.from(list.children).find((line) => line.getBoundingClientRect().bottom > top + 1);
    anchor.current = first && first.dataset.line ? { key: first.dataset.line, offset: first.getBoundingClientRect().top - top } : null;
  } else anchor.current = null;

  useEffect(() => {
    following.current = true; // the order changed: start from the newest line
  }, [view.newestOnTop]);
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) return;
    if (view.autoscroll && following.current) {
      list.scrollTop = view.newestOnTop ? 0 : list.scrollHeight;
      return;
    }
    const held = anchor.current;
    if (!held) return;
    const line = Array.from(list.children).find((child) => child.dataset.line === held.key);
    if (line) list.scrollTop += line.getBoundingClientRect().top - list.getBoundingClientRect().top - held.offset;
  }, [entries, view]);

  return h(
    "div",
    {
      ref: listRef,
      className: cx("console-well oui-well", className),
      "data-order": view.newestOnTop ? "newest-first" : "newest-last",
      onScroll: (e) => {
        const list = e.currentTarget;
        following.current = view.newestOnTop ? list.scrollTop < FOLLOW_TAIL_PX : list.scrollHeight - list.scrollTop - list.clientHeight < FOLLOW_TAIL_PX;
      },
    },
    shown.length === 0 && h("div", { className: "log-line log-empty" }, h("span", { className: "log--dim" }, view.clearedAt || view.clearedSeq ? tx("Nothing new since the console was cleared.") : tx("No lines yet."))),
    shown.map((entry, index) => h(ConsoleLine, { key: keys[index], lineKey: keys[index], entry, onPick })),
  );
}

/* ---------------------------------------------------------------------------
   The input field (1.72), the same on the console card, over the whole screen and in the computer's bar:
     ↑ / ↓      the commands sent before (the last 100, kept on this device; the line being typed comes back);
     Tab        completes the command's name from Klipper's commands and macros (/printer/gcode/help): one match is
                written out, several are listed above the field with what they do (a tap writes one);
     Escape     closes that list.
   On a touch screen, with no Tab key, the matches are listed while the name is typed (from its second letter).
   ------------------------------------------------------------------------- */
const CONSOLE_HISTORY_KEY = "klippeye.console.history";
const CONSOLE_HISTORY_MAX = 100;
const CONSOLE_SUGGESTIONS_MAX = 8;
const CONSOLE_TOUCH = () => typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;

function readConsoleHistory() {
  try {
    const list = JSON.parse(localStorage.getItem(CONSOLE_HISTORY_KEY) || "[]");
    return Array.isArray(list) ? list.filter((item) => typeof item === "string") : [];
  } catch (e) {
    return [];
  }
}
function rememberConsoleCommand(command) {
  const list = readConsoleHistory().filter((item) => item !== command);
  list.push(command);
  try {
    localStorage.setItem(CONSOLE_HISTORY_KEY, JSON.stringify(list.slice(-CONSOLE_HISTORY_MAX)));
  } catch (e) {}
}

/** Klipper's commands { NAME: help }, asked once per page (and again after a failure). */
let consoleCommandsPromise = null;
function consoleCommands() {
  if (!consoleCommandsPromise)
    consoleCommandsPromise = moonraker.gcodeCommands().catch(() => {
      consoleCommandsPromise = null;
      return {};
    });
  return consoleCommandsPromise;
}

/** The longest start that all the names share. */
function commonPrefix(names) {
  if (!names.length) return "";
  let prefix = names[0];
  for (const name of names) while (!name.startsWith(prefix)) prefix = prefix.slice(0, -1);
  return prefix;
}

/** Everything an input field of the console needs: { command, setCommand, send, inputProps, suggestions, choose, closeSuggestions }. */
function useConsoleInput(inputRef, afterSend) {
  const [command, setCommand] = useState("");
  const [suggestions, setSuggestions] = useState([]); // [{ name, help }] after a Tab with several matches
  const browse = useRef({ index: -1, draft: "" }); // where ↑ / ↓ are in the history
  const caretToEnd = () =>
    setTimeout(() => {
      const input = inputRef.current;
      if (input) input.setSelectionRange(input.value.length, input.value.length);
    }, 0);
  const send = () => {
    const script = command.trim();
    if (!script) return;
    fireGcode(script);
    rememberConsoleCommand(script);
    browse.current = { index: -1, draft: "" };
    setSuggestions([]);
    setCommand("");
    if (afterSend) afterSend();
  };
  // on a touch screen (no Tab key) the matches are listed while the name is typed, from the second letter
  const suggestWhileTyping = async (value) => {
    const typed = value.trim().toUpperCase();
    if (typed.length < 2 || /\s/.test(value)) return setSuggestions([]);
    const commands = await consoleCommands();
    const names = Object.keys(commands)
      .map((name) => name.toUpperCase())
      .filter((name) => name.startsWith(typed) && name !== typed)
      .sort();
    if (inputRef.current && inputRef.current.value.trim().toUpperCase() !== typed) return; // typed on meanwhile
    setSuggestions(names.slice(0, CONSOLE_SUGGESTIONS_MAX).map((name) => ({ name, help: commands[name] || "" })));
  };
  const complete = async () => {
    const value = command;
    if (/\s/.test(value.trim()) || !value.trim()) return; // only the command's name is completed
    const typed = value.trim().toUpperCase();
    const commands = await consoleCommands();
    const names = Object.keys(commands)
      .map((name) => name.toUpperCase())
      .filter((name) => name.startsWith(typed))
      .sort();
    if (!names.length) return setSuggestions([]);
    if (names.length === 1) {
      setCommand(names[0] + " ");
      setSuggestions([]);
    } else {
      setCommand(commonPrefix(names));
      const helpOf = (name) => commands[name] || commands[name.toLowerCase()] || Object.entries(commands).find(([key]) => key.toUpperCase() === name)?.[1] || "";
      setSuggestions(names.slice(0, CONSOLE_SUGGESTIONS_MAX).map((name) => ({ name, help: helpOf(name) })).concat(names.length > CONSOLE_SUGGESTIONS_MAX ? [{ name: "", help: tx("…and {count} more: type more letters", { count: names.length - CONSOLE_SUGGESTIONS_MAX }) }] : []));
    }
    caretToEnd();
  };
  const step = (direction) => {
    const history = readConsoleHistory();
    if (!history.length) return;
    const state = browse.current;
    if (state.index === -1) {
      if (direction > 0) return;
      state.draft = command;
      state.index = history.length;
    }
    const next = Math.min(history.length, Math.max(0, state.index + direction));
    state.index = next;
    if (next === history.length) {
      state.index = -1;
      setCommand(state.draft);
    } else setCommand(history[next]);
    caretToEnd();
  };
  const onKeyDown = (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      send();
    } else if (event.key === "Tab" && !event.shiftKey && command.trim()) {
      event.preventDefault();
      complete();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      step(-1);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      step(1);
    } else if (event.key === "Escape" && suggestions.length) {
      event.preventDefault();
      event.stopPropagation();
      setSuggestions([]);
    }
  };
  const choose = (name) => {
    if (!name) return;
    setCommand(name + " ");
    setSuggestions([]);
    const input = inputRef.current;
    if (input) input.focus();
    caretToEnd();
  };
  return {
    command,
    setCommand: (value) => {
      browse.current.index = -1;
      setCommand(value);
    },
    send,
    suggestions,
    choose,
    inputProps: {
      ref: inputRef,
      value: command,
      onChange: (event) => {
        browse.current.index = -1;
        setCommand(event.target.value);
        if (CONSOLE_TOUCH()) suggestWhileTyping(event.target.value);
        else setSuggestions([]);
      },
      onKeyDown,
      autoCapitalize: "characters",
      autoCorrect: "off",
      autoComplete: "off",
      spellCheck: false,
      enterKeyHint: "send",
    },
  };
}

/** The names Tab found, above the input field. */
function ConsoleSuggestions({ input }) {
  if (!input.suggestions.length) return null;
  return h(
    "div",
    { className: "console-suggest", role: "listbox", "aria-label": tx("Matching commands") },
    input.suggestions.map((item, index) =>
      item.name
        ? h(
            "button",
            { key: item.name, type: "button", role: "option", className: "console-suggest__item", "data-suggest": item.name, onMouseDown: (event) => event.preventDefault(), onClick: () => input.choose(item.name) },
            h("span", { className: "console-suggest__name" }, item.name),
            item.help && h("span", { className: "console-suggest__help" }, item.help),
          )
        : h("div", { key: "more" + index, className: "console-suggest__more" }, item.help),
    ),
  );
}

/** The console over the whole screen: the log, the tools and the input field (1.34). */
function ConsoleFullscreen({ entries, onClose }) {
  useBodyScrollLock(true);
  useBackHandler(onClose, true);
  const inputRef = useRef(null);
  const input = useConsoleInput(inputRef);
  useEffect(() => {
    // Escape with the options menu open closes the menu only
    // in the capture phase, before the menu's own handler takes the menu away: Escape with the options open closes the menu only
    const onKey = (event) => event.key === "Escape" && !document.querySelector(".oui-menu") && onClose();
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);
  const pick = (message) => {
    input.setCommand(message);
    if (inputRef.current) inputRef.current.focus();
  };
  return h(
    "div",
    { className: "console-full", role: "dialog", "aria-label": "Console" },
    h("div", { className: "console-full__head" }, h("div", { className: "console-full__title" }, h(Icons.Code, { size: 20 }), "Console"), h(ConsoleTools, { entries, fullscreen: true, onFullscreen: onClose })),
    h(ConsoleLog, { entries, onPick: pick, className: "console-full__log" }),
    h(
      "div",
      { className: "console-full__input console-input-wrap" },
      h(ConsoleSuggestions, { input }),
      h("input", { ...input.inputProps, placeholder: tx("Send code..."), "aria-label": tx("Send code"), className: "oui-field oui-mono console-input" }),
      h("button", { onClick: input.send, className: "oui-btn oui-btn--primary oui-btn--icon console-send", "aria-label": tx("Send") }, h(Icons.Send)),
    ),
  );
}

function ConsoleCard({ entries }) {
  const [fullscreen, setFullscreen] = useState(false);
  const inputRef = useRef(null);
  const input = useConsoleInput(inputRef, () => setTimeout(() => inputRef.current && inputRef.current.focus(), 100));
  const pick = (message) => {
    input.setCommand(message);
    const field = inputRef.current;
    if (!field) return;
    field.focus();
    setTimeout(() => field.setSelectionRange(field.value.length, field.value.length), 10);
  };

  return h(
    Card,
    { cardId: "console" },
    h(CardHeader, { title: "Console" }, h(ConsoleTools, { entries, fullscreen: false, onFullscreen: () => setFullscreen(true) })),
    h(ConsoleLog, { entries, onPick: pick }),
    h(Presence, null, fullscreen && h(ConsoleFullscreen, { entries, onClose: () => setFullscreen(false) })),
    h(
      "div",
      { className: "flex gap-3 mt-3 console-input-wrap" },
      h(ConsoleSuggestions, { input }),
      h("input", {
        ...input.inputProps,
        onFocus: (e) => scrollIntoViewSoon(e.target, CONSOLE_INPUT_SCROLL_DELAY_MS),
        placeholder: tx("Send code..."),
        "aria-label": tx("Send code"),
        className: "oui-field oui-mono console-input",
      }),
      h("button", { onClick: input.send, className: "oui-btn oui-btn--primary oui-btn--icon console-send", "aria-label": tx("Send") }, h(Icons.Send)),
    ),
  );
}
