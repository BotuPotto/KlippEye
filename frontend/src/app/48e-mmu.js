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
   ========================================================================== */

const MMU_POLL_MS = 2000;
const MMU_ABSENT_POLL_MS = 30000;

/** The `mmu` object (null when there is none) and the print's state. */
function useMmu() {
  const [state, setState] = useState({ known: false, mmu: null, printing: false });
  useEffect(() => {
    let cancelled = false;
    let stop = null;
    let present = null;
    const load = async () => {
      const status = await moonraker.queryObjects("mmu&print_stats=state", { timeout: 4000 }).catch(() => null);
      if (cancelled || !status) return;
      const mmu = status.mmu && typeof status.mmu === "object" && Object.keys(status.mmu).length ? status.mmu : null;
      const printState = (status.print_stats || {}).state;
      setState((old) => {
        const next = { known: true, mmu, printing: printState === "printing" || printState === "paused" };
        return JSON.stringify(old) === JSON.stringify(next) ? old : next;
      });
      if (present !== Boolean(mmu)) {
        // a unit polls often, a printer without one only now and then (Klipper may be restarting)
        present = Boolean(mmu);
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
  const { mmu, printing } = useMmu();
  const [chosen, setChosen] = useState(null); // the gate tapped
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
