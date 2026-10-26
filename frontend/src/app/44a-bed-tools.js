/* ============================================================================
   44a · BED & GANTRY TOOLS
   The "Calibrate" menu of the Movement card:
     · SCREWS_TILT_CALCULATE   how much to turn each bed screw (result sheet);
     · CARTOGRAPHER_AXIS_TWIST_COMPENSATION AXIS=X|Y   measures the twist of an
       axis with the probe, then offers SAVE_CONFIG.
   Both run for a minute or more and the backend's proxy gives up on a request
   after 10 s, so completion is not read from the HTTP answer: the run is
   followed by polling what Klipper reports (the tool's own result) and by
   watching the console for a "!!" error line.
   ========================================================================== */

const BED_TOOL_POLL_MS = 1500;
const BED_TOOL_TIMEOUT_MS = 10 * 60 * 1000; // a run that reports nothing for this long is given up
const TWIST_AXES = ["X", "Y"];
const BED_TOOL_ERROR_MAX_CHARS = 140;

/* ---------------------------------------------------------------------------
   What Klipper reports about each tool
   ------------------------------------------------------------------------- */
const bedToolsApi = {
  /** The `screws_tilt_adjust` object: { error, results: { screw1: { z, sign, adjust, is_base } } }, or null. */
  async screwsStatus() {
    const status = await moonraker.queryObjects("screws_tilt_adjust").catch(() => ({}));
    return status.screws_tilt_adjust || null;
  },
  /** The axis twist values waiting for the next SAVE_CONFIG, or null. */
  async pendingTwist() {
    const configfile = await moonraker.configfile("save_config_pending_items").catch(() => ({}));
    return (configfile.save_config_pending_items || {}).axis_twist_compensation || null;
  },
};

/**
 * The tools this printer offers. A tool is finished when Klipper answers the request, or (a request
 * longer than the proxy allows) when `observe()` answers something other than it did before the
 * run: new screw results, new pending twist values.
 */
function buildBedTools(capabilities) {
  const tools = [];
  if (capabilities.screwsTilt) {
    tools.push({
      id: "screws",
      kind: "screws",
      group: tx("Print bed"),
      title: "Screws tilt calculate",
      subtitle: tx("How much to turn each bed screw"),
      short: tx("Screws"),
      icon: h(Icons.Screw),
      script: "SCREWS_TILT_CALCULATE",
      observe: bedToolsApi.screwsStatus,
    });
  }
  if (capabilities.twistCommand || capabilities.twistNeedsConfig) {
    for (const axis of TWIST_AXES) {
      tools.push({
        id: "twist-" + axis.toLowerCase(),
        kind: "twist",
        group: "Axis twist compensation · Cartographer",
        title: tx("Axis ") + axis,
        subtitle: tx("Compensate the twist along ") + axis,
        short: "Twist " + axis,
        axis,
        icon: h(Icons.Wave),
        script: (capabilities.twistCommand || "") + " AXIS=" + axis,
        observe: bedToolsApi.pendingTwist,
        unavailable: capabilities.twistCommand ? null : tx("Add [axis_twist_compensation] to printer.cfg"),
      });
    }
  }
  return tools;
}

/** "!! message" lines the console got after `since` (a gcode-store time). Klipper's clock, never the phone's. */
const consoleErrorSince = (store, since) => store.find((item) => (item.time || 0) > since && item.type !== "command" && /^\s*!!/.test(item.message || ""));

/* ---------------------------------------------------------------------------
   State
   ------------------------------------------------------------------------- */

/**
 * `homedAxes` comes from the printer status poll, `lockReason` from printLockReason() (a print runs,
 * or the printer has not answered yet), `onSaveConfig` is useSaveConfig().confirm.
 * Returns what the Movement card needs (tools, locked/why, running) and what the dialogs show.
 */
function useBedTools({ capabilities, homedAxes, lockReason, onSaveConfig }) {
  const [run, setRun] = useState(null); // { tool, since, startedAt, baseline } while a tool runs
  const [screws, setScrews] = useState(null); // { error, results } to show in the sheet
  const [twistDone, setTwistDone] = useState(null); // the twist tool whose values wait for SAVE_CONFIG
  const runRef = useRef(null);
  const consoleClock = useRef(0); // newest gcode-store time seen so far
  runRef.current = run;

  const tools = buildBedTools(capabilities);
  const homed = ["x", "y", "z"].every((axis) => (homedAxes || "").includes(axis));
  const lockedReason = lockReason || (!homed ? tx("Home the printer first") : null);

  const end = (current) => {
    if (runRef.current !== current) return false; // already ended (or replaced)
    runRef.current = null;
    setRun(null);
    return true;
  };
  const fail = (current, message) => {
    if (!end(current)) return;
    const text = (message || tx("unknown error")).replace(/^\s*!!\s*/, "").slice(0, BED_TOOL_ERROR_MAX_CHARS);
    toast.action(current.tool.short + ": " + text);
  };
  const complete = (current, observed) => {
    if (!end(current)) return;
    if (current.tool.kind === "screws") setScrews({ error: Boolean(observed && observed.error), results: (observed && observed.results) || {} });
    else setTwistDone(current.tool);
  };

  // The newest console time, kept even while idle so a run knows which lines are its own.
  useEffect(
    () =>
      onConsoleStore((store) => {
        for (const item of store) consoleClock.current = Math.max(consoleClock.current, item.time || 0);
      }),
    [],
  );

  // While a tool runs: look for its result, for an error line, and give up after a while.
  useEffect(() => {
    if (!run) return;
    let busy = false;
    const check = async () => {
      if (busy) return;
      busy = true;
      try {
        if (Date.now() - run.startedAt > BED_TOOL_TIMEOUT_MS) return fail(run, tx("no answer from Klipper"));
        const observed = await run.tool.observe().catch(() => null);
        if (observed !== null && JSON.stringify(observed) !== run.baseline) complete(run, observed);
      } finally {
        busy = false;
      }
    };
    const timer = setInterval(check, BED_TOOL_POLL_MS);
    const stopWatching = onConsoleStore((store) => {
      const error = consoleErrorSince(store, run.since);
      if (error) fail(run, error.message);
    });
    return () => {
      clearInterval(timer);
      stopWatching();
    };
  }, [run]);

  const start = async (tool) => {
    if (runRef.current || lockedReason || tool.unavailable) return;
    const current = { tool, since: consoleClock.current, startedAt: Date.now(), baseline: JSON.stringify(await tool.observe().catch(() => null)) };
    runRef.current = current;
    setRun(current);
    setScrews(null);
    toast.action(tool.title + " avviato");
    const sent = await sendLongGcode(tool.script);
    if (!sent.ok) fail(current, sent.message);
    // Answered before the proxy's 10 s: the script is over, whatever its result looks like next to the old one.
    else if (sent.finished) complete(current, await tool.observe().catch(() => null));
  };

  return {
    tools,
    run,
    lockedReason,
    start,
    // dialogs
    screws,
    closeScrews: () => setScrews(null),
    retryScrews: () => {
      setScrews(null);
      const tool = tools.find((item) => item.kind === "screws");
      if (tool) start(tool);
    },
    twistDone,
    dismissTwist: () => setTwistDone(null),
    saveTwist: () => {
      setTwistDone(null);
      onSaveConfig();
    },
    screwLayout: capabilities.screwLayout,
  };
}

/* ---------------------------------------------------------------------------
   Movement card: the "Calibrate" button and its menu
   ------------------------------------------------------------------------- */
function BedToolsMenuButton({ bedTools }) {
  const menu = useDropdown();
  const { tools, run, lockedReason } = bedTools;
  const choose = (tool) => () => {
    menu.close();
    bedTools.start(tool);
  };

  const groups = [];
  for (const tool of tools) {
    const last = groups[groups.length - 1];
    if (last && last.title === tool.group) last.tools.push(tool);
    else groups.push({ title: tool.group, tools: [tool] });
  }

  return h(
    React.Fragment,
    null,
    h(
      "button",
      { ref: menu.anchorRef, className: cx("oui-btn oui-btn--accent-soft", Boolean(run) && "is-busy"), disabled: Boolean(run), "aria-haspopup": "menu", "aria-expanded": menu.open, onClick: menu.toggle },
      run ? h(Icons.Refresh, { size: 18 }) : h(Icons.Level),
      run ? run.tool.short + "…" : tx("Calibrate"),
      !run && h("span", { className: cx("menu-chevron", menu.open && "is-open") }, h(Icons.Chevron, { size: 16 })),
    ),
    h(
      DropdownMenu,
      { menu },
      groups.map((group) =>
        h(
          React.Fragment,
          { key: group.title },
          h(MenuLabel, null, group.title),
          group.tools.map((tool) =>
            h(MenuItem, { key: tool.id, icon: tool.icon, title: tool.title, subtitle: tool.unavailable || lockedReason || tool.subtitle, disabled: Boolean(tool.unavailable || lockedReason), onClick: choose(tool) }),
          ),
        ),
      ),
    ),
  );
}

/* ---------------------------------------------------------------------------
   Result sheet of SCREWS_TILT_CALCULATE
   ------------------------------------------------------------------------- */
const screwNumber = (id) => parseInt(String(id).replace(/\D/g, ""), 10) || 0;

/** One screw: where it is and what to do with it. `adjust` is Klipper's "turns:minutes" text, e.g. "01:15". */
function ScrewRow({ id, result, layout }) {
  const place = layout.find((screw) => screw.id === id) || { name: id };
  const coordinates = place.x !== undefined && place.y !== undefined ? "X " + place.x + " · Y " + place.y : "";
  const adjust = result.adjust || "00:00";
  const done = !result.is_base && /^0+:0+$/.test(adjust);
  let badge;
  if (result.is_base) badge = h("span", { className: "oui-badge oui-badge--info" }, tx("Reference"));
  else if (done) badge = h("span", { className: "oui-badge oui-badge--ok" }, "OK");
  else badge = h("span", { className: "oui-badge oui-badge--warn" }, result.sign === "CCW" ? h(Icons.RotateCcw, { size: 14 }) : h(Icons.RotateCw, { size: 14 }), (result.sign || "") + " " + adjust);

  return h(
    "div",
    { className: "oui-row" },
    h("span", { className: cx("oui-row__icon", result.is_base && "oui-row__icon--accent") }, h(Icons.Screw, { size: 20 })),
    h("span", { className: "oui-row__text" }, h("span", { className: "oui-row__name screw-row__name" }, place.name), coordinates && h("span", { className: "oui-row__meta" }, coordinates)),
    badge,
  );
}

function ScrewsSheet({ controller }) {
  useBodyScrollLock(true);
  const { screws, screwLayout } = controller;
  const ids = Object.keys(screws.results).sort((a, b) => screwNumber(a) - screwNumber(b));
  return h(
    "div",
    { className: "sheet-overlay sheet-overlay--screws", onClick: (event) => event.target === event.currentTarget && controller.closeScrews() },
    h(
      "div",
      { className: "sheet-card sheet-card--column" },
      h(
        "div",
        { className: "sheet-header sheet-header--bar" },
        h("div", null, h("div", { className: "dialog-title" }, tx("Bed screws")), h("div", { className: "dialog-sub" }, "Screws tilt calculate")),
        h("button", { className: "dialog-close", onClick: controller.closeScrews, "aria-label": tx("Close") }, "✕"),
      ),
      h(
        "div",
        { className: "screws-body" },
        screws.error && h("div", { className: "oui-tile oui-tile--danger screws-alert" }, tx("One or more screws exceed the maximum allowed deviation: adjust them and measure again.")),
        ids.length === 0
          ? h("div", { className: "oui-notice" }, tx("Klipper returned no results."))
          : h("div", { className: "oui-list" }, ids.map((id) => h(ScrewRow, { key: id, id, result: screws.results[id], layout: screwLayout }))),
        h("div", { className: "oui-caption screws-legend" }, tx("CW = clockwise, CCW = counter-clockwise. 01:15 means one turn and 15 minutes (like the hands of a clock).")),
      ),
      h(
        "div",
        { className: "sheet-footer" },
        h("button", { className: "oui-btn", onClick: controller.retryScrews }, tx("Retry")),
        h("button", { className: "oui-btn oui-btn--primary", onClick: controller.closeScrews }, tx("Done")),
      ),
    ),
  );
}

/** The result sheet and the "save the twist values?" question. */
function BedToolsDialogs({ controller }) {
  const { twistDone } = controller;
  return h(
    React.Fragment,
    null,
    h(Presence, null, controller.screws && h(ScrewsSheet, { controller })),
    h(ConfirmDialog, {
      open: Boolean(twistDone),
      tone: "neutral",
      icon: h(Icons.Wave),
      title: tx("Compensation calculated"),
      subtitle: twistDone ? tx("Axis twist · axis ") + twistDone.axis : "",
      message: [tx("The values are active but not written to printer.cfg yet. "), h("code", { key: "cmd" }, "SAVE_CONFIG"), tx(" saves them and restarts Klipper. Save now?")],
      confirmLabel: tx("Save"),
      cancelLabel: tx("Later"),
      onConfirm: controller.saveTwist,
      onCancel: controller.dismissTwist,
    }),
  );
}
