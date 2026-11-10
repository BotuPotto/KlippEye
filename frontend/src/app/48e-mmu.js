/* ============================================================================
   48e · MULTI-MATERIAL UNIT (1.85)
   For printers with Happy Hare (Klipper's `mmu` object): the gates with their
   colour, material and state, the tool and gate in use, what the unit is doing,
   and its everyday commands (change tool, select a gate, load, unload, home,
   recover). Without an `mmu` object the card does not show.
   Happy Hare's status: tool / gate (-1 none, -2 bypass), filament ("Loaded",
   "Unloaded", "Unknown"), action ("Idle", "Loading"...), num_gates,
   gate_status (-1 unknown, 0 empty, 1 available, 2 in the buffer),
   gate_color (hex without #, or a name), gate_material, ttg_map (tool → gate).
   1.91: or AFC (the `AFC` object, Box Turtle, Night Owl...): its units and
   lanes (`AFC_stepper <lane>` or `AFC_lane <lane>`) with colour, material,
   tool and state, the lane in the toolhead, what it is doing, its message,
   and its commands (load a lane into the toolhead, eject a lane, unload the
   toolhead, clear an error). AFC's status: current_load (lane in the toolhead
   or null), current_state ("Idle"...), error_state, message {message, type},
   lanes, units ("Box_Turtle Turtle_1"); a lane: unit, map ("T0"), load and
   prep (its sensors), tool_loaded, material, color ("#ff0000"), weight,
   filament_status ("Ready", "Loaded", "Not Ready"...).
   ========================================================================== */

const MMU_POLL_MS = 2000;
const MMU_ABSENT_POLL_MS = 30000;

/** The objects of AFC's lanes ("AFC_stepper lane1", "AFC_lane lane5"), by lane name, in Klipper's list. */
async function afcLaneObjects(lanes) {
  const names = await moonraker.objectsList({ timeout: 4000 }).catch(() => []);
  const found = {};
  names.forEach((name) => {
    const match = /^AFC_(?:stepper|lane) (\S+)$/.exec(name);
    if (match && lanes.includes(match[1])) found[match[1]] = name;
  });
  return found;
}

/** The `mmu` object of Happy Hare, or AFC and its lanes (null when there is none), and the print's state. */
function useMmu() {
  const [state, setState] = useState({ known: false, mmu: null, afc: null, printing: false });
  useEffect(() => {
    let cancelled = false;
    let stop = null;
    let present = null;
    let laneObjects = null; // AFC: lane name → its object, found once
    const load = async () => {
      const status = await moonraker.queryObjects("mmu&AFC&print_stats=state", { timeout: 4000 }).catch(() => null);
      if (cancelled || !status) return;
      const mmu = status.mmu && typeof status.mmu === "object" && Object.keys(status.mmu).length ? status.mmu : null;
      let afc = !mmu && status.AFC && typeof status.AFC === "object" && Object.keys(status.AFC).length ? { ...status.AFC, lane: {} } : null;
      if (afc) {
        const lanes = Array.isArray(afc.lanes) ? afc.lanes : [];
        if (!laneObjects || lanes.some((name) => !laneObjects[name])) laneObjects = await afcLaneObjects(lanes);
        const objects = Object.values(laneObjects);
        if (objects.length) {
          const lanesNow = await moonraker.queryObjects(objects.map(encodeURIComponent).join("&"), { timeout: 4000 }).catch(() => ({}));
          if (cancelled) return;
          lanes.forEach((name) => {
            const one = lanesNow[laneObjects[name]];
            if (one && Object.keys(one).length) afc.lane[name] = one;
          });
        }
      }
      const printState = (status.print_stats || {}).state;
      setState((old) => {
        const next = { known: true, mmu, afc, printing: printState === "printing" || printState === "paused" };
        return JSON.stringify(old) === JSON.stringify(next) ? old : next;
      });
      if (present !== Boolean(mmu || afc)) {
        // a unit polls often, a printer without one only now and then (Klipper may be restarting)
        present = Boolean(mmu || afc);
        if (stop) stop();
        stop = startPolling(load, present ? MMU_POLL_MS : MMU_ABSENT_POLL_MS);
      }
    };
    load();
    return () => {
      cancelled = true;
      if (stop) stop();
    };
  }, []);
  return state;
}

/** A CSS colour from Happy Hare's gate_color ("ff8800", "#ff8800", "red", "" ...), or null. */
function mmuColor(value) {
  const text = String(value || "").trim();
  if (!text) return null;
  if (/^#?[0-9a-f]{6}([0-9a-f]{2})?$/i.test(text)) return "#" + text.replace(/^#/, "").slice(0, 6);
  if (/^[a-z]+$/i.test(text)) return text.toLowerCase();
  return null;
}

/** The gates: [{ gate, color, material, status, tools: [tool numbers mapped to it] }]. */
function mmuGates(mmu) {
  const count = Number(mmu.num_gates) || (mmu.gate_status || []).length || 0;
  const map = mmu.ttg_map || [];
  const gates = [];
  for (let gate = 0; gate < count; gate++) {
    gates.push({
      gate,
      color: mmuColor((mmu.gate_color || [])[gate]),
      material: String((mmu.gate_material || [])[gate] || ""),
      status: (mmu.gate_status || [])[gate],
      tools: map.map((g, tool) => (g === gate ? tool : -1)).filter((tool) => tool >= 0),
    });
  }
  return gates;
}

const mmuGateStatus = (status) =>
  status === 0 ? txc("gate", "Empty") : status === 1 ? tx("Available") : status === 2 ? tx("In the buffer") : tx("Unknown");

const mmuWhere = (value, label) => (value === -2 ? tx("Bypass") : value === -1 || value === undefined || value === null ? "—" : label + value);

function MmuCard({ onGcode }) {
  const { mmu, afc, printing } = useMmu();
  const [chosen, setChosen] = useState(null); // the gate tapped
  if (afc) return h(AfcCard, { afc, printing, onGcode });
  if (!mmu) return null;
  const gates = mmuGates(mmu);
  const action = String(mmu.action || "Idle");
  const busy = action.toLowerCase() !== "idle";
  const locked = printing || busy || mmu.enabled === false;
  const send = (script, message) => {
    if (onGcode) onGcode(script);
    else sendGcode(script).catch((error) => toast.notice(tx("Error: ") + (error.message || error), 5000));
    toast.action(message || script);
  };
  const loaded = String(mmu.filament || "");
  const chosenGate = chosen !== null ? gates.find((one) => one.gate === chosen) : null;
  return h(
    Card,
    { cardId: "mmu", className: "mmu-card" },
    h(CardHeader, { title: tx("Multi-material unit") }, h("span", { className: cx("oui-badge mmu-action", busy && "oui-badge--warn"), "data-mmu-action": action }, busy ? action : tx("Ready"))),
    h(
      "div",
      { className: "mmu-now" },
      h("div", { className: "oui-tile mmu-fact" }, h("div", { className: "oui-caption" }, tx("Tool")), h("div", { className: "mmu-fact__value", "data-mmu-tool": mmu.tool }, mmuWhere(mmu.tool, "T"))),
      h("div", { className: "oui-tile mmu-fact" }, h("div", { className: "oui-caption" }, tx("Gate")), h("div", { className: "mmu-fact__value", "data-mmu-gate": mmu.gate }, mmuWhere(mmu.gate, "#"))),
      h(
        "div",
        { className: "oui-tile mmu-fact" },
        h("div", { className: "oui-caption" }, tx("Filament")),
        h("div", { className: "mmu-fact__value", "data-mmu-filament": loaded }, loaded === "Loaded" ? tx("Loaded") : loaded === "Unloaded" ? tx("Unloaded") : tx("Unknown")),
      ),
    ),
    mmu.enabled === false && h("div", { className: "oui-caption mmu-note" }, tx("The unit is turned off (MMU ENABLE=1 turns it on).")),
    h(
      "div",
      { className: "mmu-gates", role: "list" },
      gates.map((one) =>
        h(
          "button",
          {
            key: one.gate,
            type: "button",
            role: "listitem",
            className: cx("mmu-gate", one.gate === mmu.gate && "is-current", chosen === one.gate && "is-chosen", one.status === 0 && "is-empty"),
            "data-mmu-gate-tile": one.gate,
            onClick: () => setChosen((was) => (was === one.gate ? null : one.gate)),
          },
          h("span", { className: "mmu-gate__swatch", style: { "--mmu-color": one.color || "transparent" } }),
          h("span", { className: "mmu-gate__name" }, "#" + one.gate + (one.tools.length ? " · " + one.tools.map((t) => "T" + t).join(" ") : "")),
          h("span", { className: "mmu-gate__material" }, one.material || "—"),
          h("span", { className: "mmu-gate__status" }, mmuGateStatus(one.status)),
        ),
      ),
    ),
    chosenGate &&
      h(
        "div",
        { className: "mmu-chosen", "data-mmu-chosen": chosenGate.gate },
        chosenGate.tools.map((tool) =>
          h("button", { key: tool, type: "button", className: "oui-btn oui-btn--sm oui-btn--primary", disabled: locked, onClick: () => send("MMU_CHANGE_TOOL TOOL=" + tool, tx("Changing to T{tool}", { tool })) }, tx("Change to T{tool}", { tool })),
        ),
        h("button", { type: "button", className: "oui-btn oui-btn--sm", disabled: locked, onClick: () => send("MMU_SELECT GATE=" + chosenGate.gate) }, tx("Select gate #{gate}", { gate: chosenGate.gate })),
      ),
    h(
      "div",
      { className: "mmu-actions" },
      h("button", { type: "button", className: "oui-btn oui-btn--sm", "data-mmu-cmd": "load", disabled: locked, onClick: () => send("MMU_LOAD") }, tx("Load")),
      h("button", { type: "button", className: "oui-btn oui-btn--sm", "data-mmu-cmd": "unload", disabled: locked, onClick: () => send("MMU_UNLOAD") }, tx("Unload")),
      h("button", { type: "button", className: "oui-btn oui-btn--sm", "data-mmu-cmd": "home", disabled: locked, onClick: () => send("MMU_HOME") }, tx("Home the unit")),
      h("button", { type: "button", className: "oui-btn oui-btn--sm", "data-mmu-cmd": "recover", onClick: () => send("MMU_RECOVER") }, tx("Recover")),
    ),
    h("div", { className: "oui-caption mmu-note" }, printing ? tx("During a print the slicer's tool changes drive the unit; «Recover» realigns it after a problem.") : tx("Tap a gate for its tools.")),
  );
}

/* ---- AFC (1.91) ------------------------------------------------------------------------------------------------ */

/** AFC's units with their lanes, in AFC's order: [{ name, kind, lanes: [{ name, ...status }] }]. */
function afcUnits(afc) {
  const lanes = (afc.lanes || []).map((name) => ({ name, ...(afc.lane[name] || {}) }));
  const units = (afc.units || []).map((text) => {
    const words = String(text).split(" ");
    const name = words.length > 1 ? words.slice(1).join(" ") : words[0];
    return { name, kind: words.length > 1 ? words[0].replace(/_/g, " ") : "", lanes: lanes.filter((lane) => lane.unit === name) };
  });
  const placed = new Set(units.flatMap((unit) => unit.lanes.map((lane) => lane.name)));
  const rest = lanes.filter((lane) => !placed.has(lane.name));
  if (rest.length) units.push({ name: "", kind: "", lanes: rest });
  return units.filter((unit) => unit.lanes.length);
}

/** A lane's state in words, from AFC's filament_status and its sensors. */
function afcLaneState(lane, current) {
  if (lane.name === current || lane.tool_loaded) return { key: "tool", text: tx("In the toolhead") };
  const status = String(lane.filament_status || "").toLowerCase();
  if (status === "ready" || (lane.prep && lane.load)) return { key: "ready", text: tx("Ready") };
  if (lane.prep || lane.load) return { key: "partial", text: tx("Not ready") };
  return { key: "empty", text: txc("lane", "Empty") };
}

function AfcCard({ afc, printing, onGcode }) {
  const [chosen, setChosen] = useState(null); // the lane tapped
  const units = afcUnits(afc);
  const current = afc.current_load || null;
  const currentLane = current ? afc.lane[current] || {} : null;
  const state = String(afc.current_state || "Idle");
  const busy = state.toLowerCase() !== "idle";
  const error = Boolean(afc.error_state);
  const locked = printing || busy;
  const message = afc.message && typeof afc.message === "object" ? afc.message : null;
  const send = (script, text) => {
    if (onGcode) onGcode(script);
    else sendGcode(script).catch((problem) => toast.notice(tx("Error: ") + (problem.message || problem), 5000));
    toast.action(text || script);
  };
  const lane = chosen ? units.flatMap((unit) => unit.lanes).find((one) => one.name === chosen) : null;
  return h(
    Card,
    { cardId: "mmu", className: "mmu-card afc-card" },
    h(
      CardHeader,
      { title: tx("Multi-material unit") },
      h("span", { className: cx("oui-badge mmu-action", (busy || error) && "oui-badge--warn"), "data-afc-state": error ? "error" : state }, error ? tx("Error") : busy ? state : tx("Ready")),
    ),
    h(
      "div",
      { className: "mmu-now" },
      h("div", { className: "oui-tile mmu-fact" }, h("div", { className: "oui-caption" }, tx("Tool")), h("div", { className: "mmu-fact__value", "data-afc-tool": (currentLane && currentLane.map) || "" }, (currentLane && currentLane.map) || "—")),
      h("div", { className: "oui-tile mmu-fact" }, h("div", { className: "oui-caption" }, tx("Lane")), h("div", { className: "mmu-fact__value", "data-afc-current": current || "" }, current || "—")),
      h(
        "div",
        { className: "oui-tile mmu-fact" },
        h("div", { className: "oui-caption" }, tx("Filament")),
        h("div", { className: "mmu-fact__value" }, currentLane ? currentLane.material || tx("Loaded") : afc.bypass_state ? tx("Bypass") : tx("Unloaded")),
      ),
    ),
    message && message.message && h("div", { className: cx("oui-well afc-message", message.type === "error" && "is-error"), "data-afc-message": message.type || "" }, message.message),
    units.map((unit) =>
      h(
        "div",
        { key: unit.name || "lanes", className: "afc-unit", "data-afc-unit": unit.name },
        unit.name && h("div", { className: "afc-unit__name" }, unit.name, unit.kind && h("span", { className: "oui-caption" }, " · " + unit.kind)),
        h(
          "div",
          { className: "mmu-gates", role: "list" },
          unit.lanes.map((one) => {
            const laneState = afcLaneState(one, current);
            return h(
              "button",
              {
                key: one.name,
                type: "button",
                role: "listitem",
                className: cx("mmu-gate", laneState.key === "tool" && "is-current", chosen === one.name && "is-chosen", laneState.key === "empty" && "is-empty"),
                "data-afc-lane": one.name,
                "data-afc-lane-state": laneState.key,
                onClick: () => setChosen((was) => (was === one.name ? null : one.name)),
              },
              h("span", { className: "mmu-gate__swatch", style: { "--mmu-color": mmuColor(one.color) || "transparent" } }),
              h("span", { className: "mmu-gate__name" }, one.name + (one.map ? " · " + one.map : "")),
              h("span", { className: "mmu-gate__material" }, one.material || "—", one.weight ? " · " + Math.round(one.weight) + " g" : ""),
              h("span", { className: "mmu-gate__status" }, laneState.text),
            );
          }),
        ),
      ),
    ),
    lane &&
      h(
        "div",
        { className: "mmu-chosen", "data-afc-chosen": lane.name },
        lane.name !== current &&
          h(
            "button",
            { type: "button", className: "oui-btn oui-btn--sm oui-btn--primary", "data-afc-cmd": "load", disabled: locked, onClick: () => send("CHANGE_TOOL LANE=" + lane.name, tx("Loading {lane} into the toolhead", { lane: lane.name })) },
            tx("Load {lane} into the toolhead", { lane: lane.name }),
          ),
        lane.name !== current &&
          h(
            "button",
            { type: "button", className: "oui-btn oui-btn--sm", "data-afc-cmd": "eject", disabled: locked, onClick: () => send("LANE_UNLOAD LANE=" + lane.name, tx("Ejecting {lane}", { lane: lane.name })) },
            tx("Eject {lane}", { lane: lane.name }),
          ),
        lane.name === current && h("span", { className: "oui-caption" }, tx("This lane is in the toolhead: «Unload the toolhead» brings it back.")),
      ),
    h(
      "div",
      { className: "mmu-actions" },
      h("button", { type: "button", className: "oui-btn oui-btn--sm", "data-afc-cmd": "unload", disabled: locked || !current, onClick: () => send("TOOL_UNLOAD", tx("Unloading the toolhead")) }, tx("Unload the toolhead")),
      error && h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--primary", "data-afc-cmd": "reset", onClick: () => send("RESET_FAILURE", tx("Error cleared")) }, tx("Clear the error")),
      error && printing && h("button", { type: "button", className: "oui-btn oui-btn--sm", "data-afc-cmd": "resume", onClick: () => send("AFC_RESUME", tx("Resuming")) }, tx("Resume the print")),
    ),
    h("div", { className: "oui-caption mmu-note" }, printing ? tx("During a print the slicer's tool changes drive the unit.") : tx("Tap a lane to load or eject it.")),
  );
}
