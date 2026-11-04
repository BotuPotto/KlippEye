/* ============================================================================
   48a · TUNE CARD (roadmap 6b part 3, release 1.32.0)
   What Mainsail and Fluidd call "Tune" / "Machine limits": the values Klipper
   lets you change while it runs, during a print too:
     · speed and flow factors (M220 / M221);
     · pressure advance and its smooth time (SET_PRESSURE_ADVANCE);
     · the machine limits (SET_VELOCITY_LIMIT): velocity, acceleration,
       square corner velocity, minimum cruise ratio;
     · firmware retraction (SET_RETRACTION), when [firmware_retraction] exists.
   Each value shows what Klipper uses now (polled), changes with − / + or by
   typing, and goes back to the value of printer.cfg with one tap. Nothing is
   written to printer.cfg: a restart of Klipper brings the config values back.
   ========================================================================== */

const TUNE_POLL_MS = 2000;
const TUNE_SEND_DELAY_MS = 500; // taps on − / + within this time are sent once
const TUNE_HOLD_MS = 4000; // after a change the field keeps the value typed until Klipper reports it (or this time passes)
const TUNE_QUERY =
  "gcode_move=speed_factor,extrude_factor&extruder=pressure_advance,smooth_time" +
  "&toolhead=max_velocity,max_accel,square_corner_velocity,minimum_cruise_ratio,max_accel_to_decel&firmware_retraction";

/** The values as Klipper reports them, in the units shown (factors as %). */
function readTuneStatus(status) {
  const num = (value) => (typeof value === "number" && Number.isFinite(value) ? value : null);
  const move = status.gcode_move || {};
  const extruder = status.extruder || {};
  const toolhead = status.toolhead || {};
  const retraction = status.firmware_retraction || null;
  const pct = (value) => (num(value) === null ? null : Math.round(value * 100));
  return {
    speed: pct(move.speed_factor),
    flow: pct(move.extrude_factor),
    pa: num(extruder.pressure_advance),
    smooth: num(extruder.smooth_time),
    velocity: num(toolhead.max_velocity),
    accel: num(toolhead.max_accel),
    scv: num(toolhead.square_corner_velocity),
    mcr: num(toolhead.minimum_cruise_ratio),
    a2d: num(toolhead.max_accel_to_decel), // Klipper before 2024 has this instead of the minimum cruise ratio
    retractLength: retraction && num(retraction.retract_length),
    retractSpeed: retraction && num(retraction.retract_speed),
    unretractExtra: retraction && num(retraction.unretract_extra_length),
    unretractSpeed: retraction && num(retraction.unretract_speed),
  };
}

/**
 * The rows of the card, by group. `send(value)` is the G-code; `fallback` the printer.cfg value (capabilities.tune) the
 * reset button goes back to. A row whose value Klipper does not report is left out.
 */
function tuneRows(capabilities) {
  const config = capabilities.tune || {};
  const velocity = (key) => (value) => "SET_VELOCITY_LIMIT " + key + "=" + value;
  const retract = (key) => (value) => "SET_RETRACTION " + key + "=" + value;
  return [
    {
      id: "print",
      title: tx("Print"),
      rows: [
        { id: "speed", label: tx("Speed"), unit: "%", step: 5, min: 10, max: 500, decimals: 0, fallback: 100, send: (value) => "M220 S" + value },
        { id: "flow", label: tx("Flow"), unit: "%", step: 1, min: 50, max: 200, decimals: 0, fallback: 100, send: (value) => "M221 S" + value },
      ],
    },
    {
      id: "pa",
      title: "Pressure advance",
      rows: [
        { id: "pa", label: "Pressure advance", unit: "", step: 0.005, min: 0, max: 2, decimals: 3, fallback: config.pa, send: (value) => "SET_PRESSURE_ADVANCE ADVANCE=" + value },
        { id: "smooth", label: tx("Smooth time"), unit: "s", step: 0.005, min: 0, max: 0.2, decimals: 3, fallback: config.smooth, send: (value) => "SET_PRESSURE_ADVANCE SMOOTH_TIME=" + value },
      ],
    },
    {
      id: "limits",
      title: tx("Machine limits"),
      rows: [
        { id: "velocity", label: tx("Velocity"), unit: "mm/s", step: 10, min: 1, max: 2000, decimals: 0, fallback: config.velocity, send: velocity("VELOCITY") },
        { id: "accel", label: tx("Acceleration"), unit: "mm/s²", step: 250, min: 1, max: 100000, decimals: 0, fallback: config.accel, send: velocity("ACCEL") },
        { id: "scv", label: tx("Square corner velocity"), unit: "mm/s", step: 1, min: 0, max: 100, decimals: 1, fallback: config.scv, send: velocity("SQUARE_CORNER_VELOCITY") },
        { id: "mcr", label: tx("Minimum cruise ratio"), unit: "", step: 0.05, min: 0, max: 0.99, decimals: 2, fallback: config.mcr, send: velocity("MINIMUM_CRUISE_RATIO") },
        { id: "a2d", label: tx("Accel to decel"), unit: "mm/s²", step: 250, min: 1, max: 100000, decimals: 0, fallback: config.a2d, send: velocity("ACCEL_TO_DECEL") },
      ],
    },
    {
      id: "retraction",
      title: tx("Firmware retraction"),
      rows: [
        { id: "retractLength", label: tx("Retract length"), unit: "mm", step: 0.1, min: 0, max: 20, decimals: 2, fallback: config.retractLength, send: retract("RETRACT_LENGTH") },
        { id: "retractSpeed", label: tx("Retract speed"), unit: "mm/s", step: 5, min: 1, max: 200, decimals: 0, fallback: config.retractSpeed, send: retract("RETRACT_SPEED") },
        { id: "unretractExtra", label: tx("Extra on unretract"), unit: "mm", step: 0.05, min: 0, max: 5, decimals: 2, fallback: config.unretractExtra, send: retract("UNRETRACT_EXTRA_LENGTH") },
        { id: "unretractSpeed", label: tx("Unretract speed"), unit: "mm/s", step: 5, min: 1, max: 200, decimals: 0, fallback: config.unretractSpeed, send: retract("UNRETRACT_SPEED") },
      ],
    },
  ];
}

/** `value` rounded to the row's decimals and kept inside its range. */
function tuneClamp(row, value) {
  const factor = Math.pow(10, row.decimals);
  return clamp(Math.round(value * factor) / factor, row.min, row.max);
}

const tuneText = (row, value) => (value === null || value === undefined ? "–" : Number(value).toFixed(row.decimals));

/** What Klipper uses now, polled while the card is on screen. `null` until it answers. */
function useTuneStatus() {
  const [values, setValues] = useState(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      const status = await moonraker.queryObjects(TUNE_QUERY).catch(() => null);
      if (!cancelled && status) setValues(readTuneStatus(status));
    };
    poll();
    const timer = setInterval(poll, TUNE_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [tick]);
  return { values, refresh: () => setTick((n) => n + 1) };
}

/** One value: label, what printer.cfg says, − / field / +, and the button back to printer.cfg. */
function TuneRow({ row, value, onSend }) {
  const [draft, setDraft] = useState(null); // { value, text, sent } while the person changes it
  const timer = useRef(null);
  const hold = useRef(null);
  useEffect(
    () => () => {
      clearTimeout(timer.current);
      clearTimeout(hold.current);
    },
    [],
  );
  // the value sent stays until Klipper reports it, or a while passes (Klipper refused it: the console says why)
  useEffect(() => {
    if (draft && draft.sent && value === draft.value) setDraft(null);
  }, [value, draft]);

  const shown = draft ? draft.value : value;
  const send = (next) => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      onSend(row.send(next));
      setDraft((current) => current && { ...current, sent: true });
      clearTimeout(hold.current);
      hold.current = setTimeout(() => setDraft((current) => (current && current.sent ? null : current)), TUNE_HOLD_MS);
    }, TUNE_SEND_DELAY_MS);
  };
  const change = (next) => {
    const clean = tuneClamp(row, next);
    setDraft({ value: clean, text: null, sent: false });
    send(clean);
  };
  const step = (direction) => change((shown === null || shown === undefined ? row.fallback || 0 : shown) + direction * row.step);
  const commitText = () => {
    if (!draft || draft.text === null) return;
    const parsed = parseFloat(String(draft.text).replace(",", "."));
    if (!Number.isFinite(parsed)) return setDraft(null);
    change(parsed);
  };
  const fallback = typeof row.fallback === "number" ? tuneClamp(row, row.fallback) : null;
  const changed = fallback !== null && shown !== null && shown !== undefined && Math.abs(shown - fallback) > Math.pow(10, -row.decimals) / 2;

  const text = draft && draft.text !== null ? draft.text : tuneText(row, shown);

  return h(
    "div",
    { className: "tune-row", "data-tune": row.id },
    h(
      "div",
      { className: "tune-row__text" },
      h("span", { className: "tune-row__label" }, row.label),
      fallback !== null && h("span", { className: "tune-row__config" }, tx("printer.cfg: {value}", { value: tuneText(row, fallback) })),
    ),
    h(
      "div",
      { className: "tune-row__controls" },
      h("button", { type: "button", className: "tune-step", "aria-label": row.label + " −", onClick: () => step(-1), disabled: shown !== null && shown <= row.min }, "−"),
      h(
        "label",
        { className: "tune-value" },
        h("input", {
          className: "tune-value__input",
          inputMode: "decimal",
          "aria-label": row.label,
          value: text,
          style: { width: Math.max(3, text.length) + 0.6 + "ch" },
          onChange: (event) => setDraft({ value: shown, text: event.target.value, sent: false }),
          onFocus: (event) => event.target.select(),
          onBlur: commitText,
          onKeyDown: (event) => {
            if (event.key === "Enter") event.target.blur();
            if (event.key === "Escape") {
              setDraft(null);
              event.target.blur();
            }
          },
        }),
        row.unit && h("span", { className: "tune-value__unit" }, row.unit),
      ),
      h("button", { type: "button", className: "tune-step", "aria-label": row.label + " +", onClick: () => step(1), disabled: shown !== null && shown >= row.max }, "+"),
      h(
        "button",
        { type: "button", className: cx("tune-reset", !changed && "is-hidden"), "aria-label": tx("Back to printer.cfg"), title: tx("Back to printer.cfg"), tabIndex: changed ? 0 : -1, onClick: () => changed && change(fallback) },
        h(Icons.Undo, { size: 16 }),
      ),
    ),
  );
}

function TuneCard({ capabilities, onGcode }) {
  const { values, refresh } = useTuneStatus();
  const send = (script) => {
    onGcode(script);
    setTimeout(refresh, 400);
  };
  const groups = tuneRows(capabilities)
    .map((group) => ({ ...group, rows: group.rows.filter((row) => values && values[row.id] !== null && values[row.id] !== undefined) }))
    .filter((group) => group.rows.length);
  // with the minimum cruise ratio (Klipper from 2024) the old accel_to_decel is not shown
  for (const group of groups) if (group.id === "limits" && group.rows.some((row) => row.id === "mcr")) group.rows = group.rows.filter((row) => row.id !== "a2d");

  return h(
    Card,
    { cardId: "tune", className: "tune-card" },
    h(CardHeader, { title: tx("Tune") }),
    !values
      ? h("div", { className: "oui-notice" }, tx("Waiting for Klipper…"))
      : h(
          React.Fragment,
          null,
          groups.map((group) =>
            h(
              "div",
              { key: group.id, className: "tune-group", "data-tune-group": group.id },
              h("div", { className: "oui-label tune-group__title" }, group.title),
              group.rows.map((row) => h(TuneRow, { key: row.id, row, value: values[row.id], onSend: send })),
            ),
          ),
          h("div", { className: "oui-caption tune-note" }, tx("Changes apply at once, during a print too, and last until Klipper restarts: printer.cfg is not changed.")),
        ),
  );
}
