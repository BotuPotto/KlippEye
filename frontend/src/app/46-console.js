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
    setEntries((previous) => previous.concat(lines.map((line) => ({ t, msg: line.msg, color: line.color }))));
  };

  return { entries, echo };
}

/** Sends a command typed by the user (or a multi-line script) and echoes it. */
function sendFromConsole(script, echo) {
  echo([...script.split("\n").map((line) => ({ msg: `> ${line}`, color: "log--input" })), { msg: "ok", color: "log--dim" }]);
  fireGcode(script);
}

/* ---------------------------------------------------------------------------
   UI
   ------------------------------------------------------------------------- */
const FOLLOW_TAIL_PX = 80;

function ConsoleLine({ entry, onPick }) {
  if (entry.isCommand) {
    return h(
      "div",
      { className: "log-line log-line--pick", title: "Clicca per copiare nel campo invio", onClick: () => onPick(entry.msg) },
      h("span", { className: "log-time" }, entry.t),
      h("span", { className: cx(entry.color, "log-msg") }, entry.msg),
    );
  }
  return h("div", { className: "log-line" }, h("span", { className: "log-time" }, entry.t), h("span", { className: cx(entry.color, "log-msg") }, entry.msg));
}

/**
 * The scrolling log itself: follows the newest line while the reader is at the bottom, and lets a click on a
 * command line hand it to `onPick`. `className` adds to the well's own (the dock's drawer sets its height).
 */
function ConsoleLog({ entries, onPick, className }) {
  const listRef = useRef(null);
  const following = useRef(true);

  useEffect(() => {
    const list = listRef.current;
    if (list && following.current) list.scrollTop = list.scrollHeight;
  }, [entries]);

  return h(
    "div",
    {
      ref: listRef,
      className: cx("console-well oui-well", className),
      onScroll: (e) => {
        const list = e.currentTarget;
        following.current = list.scrollHeight - list.scrollTop - list.clientHeight < FOLLOW_TAIL_PX;
      },
    },
    entries.filter((entry) => !isTemperatureReport(String(entry.msg || ""))).map((entry, index) => h(ConsoleLine, { key: index, entry, onPick })),
  );
}

function ConsoleCard({ entries }) {
  const [command, setCommand] = useState("");
  const inputRef = useRef(null);

  const send = () => {
    if (!command.trim()) return;
    fireGcode(command);
    setCommand("");
    setTimeout(() => inputRef.current && inputRef.current.focus(), 100);
  };
  const pick = (message) => {
    setCommand(message);
    const input = inputRef.current;
    if (!input) return;
    input.focus();
    setTimeout(() => input.setSelectionRange(input.value.length, input.value.length), 10);
  };

  return h(
    Card,
    null,
    h(CardHeader, { title: "Console" }),
    h(ConsoleLog, { entries, onPick: pick }),
    h(
      "div",
      { className: "flex gap-3 mt-3" },
      h("input", {
        ref: inputRef,
        value: command,
        onChange: (e) => setCommand(e.target.value),
        onKeyDown: (e) => e.key === "Enter" && send(),
        onFocus: (e) => scrollIntoViewSoon(e.target, CONSOLE_INPUT_SCROLL_DELAY_MS),
        placeholder: "Invia codice...",
        className: "oui-field oui-mono console-input",
      }),
      h("button", { onClick: send, className: "oui-btn oui-btn--primary oui-btn--icon console-send", "aria-label": "Invia" }, h(Icons.Send)),
    ),
  );
}
