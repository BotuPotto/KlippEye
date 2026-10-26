/* ============================================================================
   70 · DESKTOP SHELL
   On a wide screen (a computer, a tablet held sideways) the dashboard uses a
   second layout, closer to the Device page of Bambu Studio: page tabs in the
   top bar instead of the floating bar at the bottom, a camera that fills the
   page, and the console as a bar that is always at hand. A phone keeps the
   layout it always had: nothing below 1100 px wide changes.

   Both layouts show the same cards and use the same state; only the way they
   are arranged differs. This file holds the pieces around the pages (the
   breakpoint, the tabs, the console bar); the five wide pages are in 71.
   ========================================================================== */

/** From this width up the wide layout is used (css/70-desktop.css repeats it only for the extra-wide variant). */
const DESKTOP_MIN_WIDTH_PX = 1100;
const DESKTOP_QUERY = "(min-width: " + DESKTOP_MIN_WIDTH_PX + "px)";

const matchesDesktop = () => typeof window.matchMedia === "function" && window.matchMedia(DESKTOP_QUERY).matches;

/** True while the window is wide enough for the desktop layout; follows a resize or a rotation. */
function useIsDesktop() {
  const [wide, setWide] = useState(matchesDesktop);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const media = window.matchMedia(DESKTOP_QUERY);
    const update = () => setWide(media.matches);
    update();
    if (media.addEventListener) media.addEventListener("change", update);
    else media.addListener(update);
    return () => {
      if (media.removeEventListener) media.removeEventListener("change", update);
      else media.removeListener(update);
    };
  }, []);
  return wide;
}

/**
 * The tabs of the top bar. The ids are the phone's (home, controllo...), so the page that is open, and the one
 * remembered for the next visit, mean the same thing in both layouts: Home + Controllo become Dispositivo,
 * and what Controllo kept apart (calibrations, mesh) is Calibrazione.
 */
const DESKTOP_TABS = [
  { id: "home", label: tx("Device") },
  { id: "controllo", label: tx("Calibration") },
  { id: "files", label: tx("Files") },
  { id: "config", label: "Config" },
  { id: "sistema", label: tx("System") },
];

/** The pill next to the save and emergency buttons: { text, tone } or null until Klipper has answered. */
function printerStatePill(printStatus) {
  if (!printStatus.loaded) return null;
  if (printStatus.state === "printing") return { text: tx("Printing"), tone: "info" };
  if (printStatus.state === "paused") return { text: tx("Paused"), tone: "warn" };
  if (printStatus.state === "error") return { text: tx("Error"), tone: "danger" };
  return { text: tx("Ready"), tone: "ok" };
}

/* ---------------------------------------------------------------------------
   Console bar
   The last few lines and the input field, on every page. The arrow opens the
   whole log in a panel above the bar (Esc or the arrow closes it again).
   ------------------------------------------------------------------------- */
const DOCK_PREVIEW_LINES = 3;

function ConsoleDock({ entries }) {
  const [open, setOpen] = useState(false);
  const [command, setCommand] = useState("");
  const inputRef = useRef(null);
  const recent = entries.filter((entry) => !isTemperatureReport(String(entry.msg || ""))).slice(-DOCK_PREVIEW_LINES);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => event.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const send = () => {
    if (!command.trim()) return;
    fireGcode(command);
    setCommand("");
  };
  const pick = (message) => {
    setCommand(message);
    const input = inputRef.current;
    if (!input) return;
    input.focus();
    setTimeout(() => input.setSelectionRange(input.value.length, input.value.length), 10);
  };

  return h(
    React.Fragment,
    null,
    h(
      Presence,
      null,
      open &&
        h(
          "div",
          { className: "desk-drawer", role: "region", "aria-label": "Console" },
          h("div", { className: "oui-card__head" }, h(SectionTitle, null, "Console"), h("span", { className: "oui-caption" }, tx("Tap a command to put it back in the input field"))),
          h(ConsoleLog, { entries, onPick: pick, className: "desk-drawer__log" }),
        ),
    ),
    h(
      "div",
      { className: "desk-dock" },
      h("button", { className: "desk-dock__title", onClick: () => setOpen(!open), "aria-expanded": open }, h(Icons.Code, { size: 18 }), "Console"),
      h(
        "div",
        { className: "desk-dock__log" },
        recent.map((entry, index) =>
          h("span", { key: index + "|" + entry.t + "|" + entry.msg, className: "desk-dock__line" }, h("span", { className: "log-time" }, entry.t), " ", h("span", { className: cx(entry.color, "desk-dock__msg") }, entry.msg)),
        ),
      ),
      h("input", {
        ref: inputRef,
        value: command,
        onChange: (e) => setCommand(e.target.value),
        onKeyDown: (e) => e.key === "Enter" && send(),
        placeholder: tx("Send code..."),
        "aria-label": tx("Send code"),
        className: "oui-field oui-mono desk-dock__input",
      }),
      h("button", { onClick: send, className: "oui-btn oui-btn--primary oui-btn--icon desk-dock__send", "aria-label": tx("Send") }, h(Icons.Send)),
      h("button", { onClick: () => setOpen(!open), className: cx("oui-btn oui-btn--icon desk-dock__expand", open && "is-open"), "aria-label": open ? tx("Close the console") : tx("Open the whole console") }, h(Icons.Chevron)),
    ),
  );
}
