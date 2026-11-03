/* ============================================================================
   44a · BED & GANTRY TOOLS
   The "Calibrate" menu of the Movement card:
     · QUAD_GANTRY_LEVEL / Z_TILT_ADJUST   level the gantry or the bed with the
       probe (1.32: when printer.cfg has [quad_gantry_level] / [z_tilt]);
     · BED_SCREWS_ADJUST   the paper test at each bed screw, step by step
       (1.32: [bed_screws], printers with no probe);
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
  /** A leveling run (QGL, Z tilt): { busy: Klipper runs G-code, applied } of `object`. */
  async leveling(object) {
    const status = await moonraker.queryObjects("idle_timeout=state&" + object + "=applied").catch(() => ({}));
    return { busy: String((status.idle_timeout || {}).state || "") === "Printing", applied: Boolean((status[object] || {}).applied) };
  },
  /** The `bed_screws` object: { is_active, state: "adjust" | "fine", current_screw, accepted_screws }, or null. */
  async bedScrews() {
    const status = await moonraker.queryObjects("bed_screws").catch(() => ({}));
    return status.bed_screws || null;
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
  // A leveling run is over when Klipper, having been busy with it, is idle again (`applied` may already be true from before).
  const levelingDone = (observed, run) => {
    if (observed && observed.busy) run.sawBusy = true;
    return Boolean(observed && !observed.busy && run.sawBusy);
  };
  if (capabilities.quadGantry) {
    tools.push({
      id: "qgl",
      kind: "level",
      group: tx("Leveling"),
      title: "Quad gantry level",
      subtitle: tx("Level the gantry with the probe"),
      short: "QGL",
      icon: h(Icons.Level),
      script: "QUAD_GANTRY_LEVEL",
      observe: () => bedToolsApi.leveling("quad_gantry_level"),
      isDone: levelingDone,
    });
  }
  if (capabilities.zTilt) {
    tools.push({
      id: "z-tilt",
      kind: "level",
      group: tx("Leveling"),
      title: "Z tilt adjust",
      subtitle: tx("Level the bed with the Z motors and the probe"),
      short: "Z tilt",
      icon: h(Icons.Level),
      script: "Z_TILT_ADJUST",
      observe: () => bedToolsApi.leveling("z_tilt"),
      isDone: levelingDone,
    });
  }
  if (capabilities.bedScrews) {
    tools.push({
      id: "bed-screws",
      kind: "bedscrews",
      group: tx("Print bed"),
      title: "Bed screws adjust",
      subtitle: tx("The paper test at each screw, step by step"),
      short: tx("Screws"),
      icon: h(Icons.Screw),
      script: "BED_SCREWS_ADJUST",
      observe: bedToolsApi.bedScrews,
    });
  }
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
    const manual = Boolean(capabilities.twistManual);
    for (const axis of capabilities.twistAxes || TWIST_AXES) {
      tools.push({
        id: "twist-" + axis.toLowerCase(),
        kind: manual ? "twistManual" : "twist",
        group: manual ? "Axis twist compensation" : "Axis twist compensation · Cartographer",
        title: tx("Axis ") + axis,
        subtitle: manual ? tx("Paper test at a few points along ") + axis : tx("Compensate the twist along ") + axis,
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
  const [bedScrews, setBedScrews] = useState(false); // the BED_SCREWS_ADJUST sheet is open
  const [manualProbe, setManualProbe] = useState(null); // { tool, baseline, since } while Klipper's twist calibration asks for the paper test
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
    if (current.tool.kind === "level") toast.action(tx("{tool} completed", { tool: current.tool.title }));
    else if (current.tool.kind === "bedscrews") setBedScrews(true);
    else if (current.tool.kind === "twistManual") setManualProbe({ tool: current.tool, baseline: current.baseline, since: current.since });
    else if (current.tool.kind === "screws") setScrews({ error: Boolean(observed && observed.error), results: (observed && observed.results) || {} });
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
        if (run.tool.isDone ? run.tool.isDone(observed, run) : observed !== null && JSON.stringify(observed) !== run.baseline) complete(run, observed);
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
    if (runRef.current || lockedReason || tool.unavailable || bedScrews || manualProbe) return;
    const current = { tool, since: consoleClock.current, startedAt: Date.now(), baseline: JSON.stringify(await tool.observe().catch(() => null)) };
    runRef.current = current;
    setRun(current);
    setScrews(null);
    toast.action(tx("{tool} started", { tool: tool.title }));
    const sent = await sendLongGcode(tool.script);
    if (!sent.ok) fail(current, sent.message);
    // BED_SCREWS_ADJUST and Klipper's twist calibration answer once the nozzle waits at the first point: the rest is the sheet's
    else if (tool.kind === "bedscrews" || tool.kind === "twistManual") complete(current, null);
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
    bedScrews,
    closeBedScrews: () => setBedScrews(false),
    manualProbe,
    twistSamples: capabilities.twistSamples || 3,
    closeManualProbe: () => setManualProbe(null),
    manualProbeDone: (tool) => {
      setManualProbe(null);
      setTwistDone(tool);
    },
    bedScrewLayout: capabilities.bedScrewLayout || [],
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

/* ---------------------------------------------------------------------------
   BED_SCREWS_ADJUST, step by step (1.32)
   Klipper brings the nozzle above each screw in turn; the person does the paper
   test and answers ADJUSTED (the screw was turned: the round starts again once it
   is over) or ACCEPT (it was right already). It ends when a whole round is
   accepted; ABORT stops it.
   ------------------------------------------------------------------------- */
const BED_SCREWS_POLL_MS = 1000;

function BedScrewsSheet({ controller }) {
  useBodyScrollLock(true);
  const layout = controller.bedScrewLayout;
  const [status, setStatus] = useState(null); // the bed_screws object
  const [busy, setBusy] = useState(""); // the command being sent
  const [finished, setFinished] = useState(false);
  const seenActive = useRef(false);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      const next = await bedToolsApi.bedScrews();
      if (cancelled || !next) return;
      setStatus(next);
      if (next.is_active) seenActive.current = true;
      else if (seenActive.current) setFinished(true);
    };
    poll();
    const timer = setInterval(poll, BED_SCREWS_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const answer = async (command) => {
    if (busy) return;
    setBusy(command);
    const sent = await sendLongGcode(command);
    setBusy("");
    if (!sent.ok) toast.action("Bed screws adjust: " + String(sent.message || tx("unknown error")).replace(/^\s*!!\s*/, "").slice(0, BED_TOOL_ERROR_MAX_CHARS));
    else if (command === "ABORT") controller.closeBedScrews();
  };
  const close = () => (status && status.is_active && !finished ? answer("ABORT") : controller.closeBedScrews());
  useBackHandler(close, true);

  const index = status ? Number(status.current_screw) || 0 : 0;
  const screw = layout[index] || { name: tx("Screw") + " " + (index + 1) };
  const total = layout.length || null;
  const fine = status && status.state === "fine";
  const active = status && status.is_active && !finished;

  return h(
    "div",
    { className: "sheet-overlay sheet-overlay--screws", onClick: (event) => event.target === event.currentTarget && close() },
    h(
      "div",
      { className: "sheet-card sheet-card--column bed-screws", "data-state": finished ? "done" : active ? status.state || "adjust" : "waiting" },
      h(
        "div",
        { className: "sheet-header sheet-header--bar" },
        h("div", null, h("div", { className: "dialog-title" }, tx("Bed screws")), h("div", { className: "dialog-sub" }, "Bed screws adjust")),
        h("button", { className: "dialog-close", onClick: close, "aria-label": tx("Close") }, "✕"),
      ),
      h(
        "div",
        { className: "screws-body" },
        finished
          ? h("div", { className: "oui-tile oui-tile--ok bed-screws__done" }, h(Icons.Check, { size: 20 }), tx("Every screw was accepted: the bed is level."))
          : !active
            ? h("div", { className: "oui-notice" }, tx("Waiting for Klipper…"))
            : h(
                React.Fragment,
                null,
                h(
                  "div",
                  { className: "bed-screws__screw" },
                  h("span", { className: "bed-screws__step" }, total ? tx("Screw {n} of {total}", { n: index + 1, total }) : tx("Screw") + " " + (index + 1), fine ? " · " + tx("fine adjustment") : ""),
                  h("span", { className: "bed-screws__name" }, screw.name),
                  screw.x !== undefined && screw.y !== undefined && h("span", { className: "oui-caption" }, "X " + screw.x + " · Y " + screw.y),
                ),
                h(
                  "ol",
                  { className: "bed-screws__how" },
                  h("li", null, tx("Slide a sheet of paper between the nozzle and the bed.")),
                  h("li", null, tx("Turn the screw until the paper drags a little as it moves.")),
                  h("li", null, tx("Then: «Adjusted» if you turned the screw, «Accept» if it was right already.")),
                ),
                h("div", { className: "oui-caption" }, tx("After a round with an adjusted screw Klipper goes round again; it ends when every screw is accepted.")),
              ),
      ),
      h(
        "div",
        { className: "sheet-footer" },
        finished
          ? h("button", { className: "oui-btn oui-btn--primary", onClick: controller.closeBedScrews }, tx("Done"))
          : h(
              React.Fragment,
              null,
              h("button", { className: "oui-btn", disabled: Boolean(busy) || !active, onClick: () => answer("ABORT") }, tx("Abort")),
              h("button", { className: cx("oui-btn", busy === "ADJUSTED" && "is-busy"), disabled: Boolean(busy) || !active, onClick: () => answer("ADJUSTED") }, tx("Adjusted")),
              h("button", { className: cx("oui-btn oui-btn--primary", busy === "ACCEPT" && "is-busy"), disabled: Boolean(busy) || !active, onClick: () => answer("ACCEPT") }, tx("Accept")),
            ),
      ),
    ),
  );
}

/* ---------------------------------------------------------------------------
   The paper test of Klipper's own twist calibration (1.33.1)
   AXIS_TWIST_COMPENSATION_CALIBRATE probes each point, then leaves the nozzle
   above it in a manual probe session: TESTZ moves the nozzle, ACCEPT takes the
   height, ABORT stops. After the last point the values wait for SAVE_CONFIG.
   ------------------------------------------------------------------------- */
const MANUAL_PROBE_POLL_MS = 800;
const TESTZ_STEPS = [-1, -0.1, -0.05, -0.01, 0.01, 0.05, 0.1, 1];

function ManualProbeSheet({ controller }) {
  useBodyScrollLock(true);
  const { tool, baseline, since } = controller.manualProbe;
  const [probe, setProbe] = useState(null); // the manual_probe object
  const [busy, setBusy] = useState("");
  const [accepted, setAccepted] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      const [status, pending] = await Promise.all([moonraker.queryObjects("manual_probe").catch(() => ({})), bedToolsApi.pendingTwist().catch(() => null)]);
      if (cancelled) return;
      if (pending !== null && JSON.stringify(pending) !== baseline) return controller.manualProbeDone(tool);
      setProbe(status.manual_probe || null);
    };
    poll();
    const timer = setInterval(poll, MANUAL_PROBE_POLL_MS);
    const stopWatching = onConsoleStore((store) => {
      const error = consoleErrorSince(store, since);
      if (error && !cancelled) {
        cancelled = true;
        toast.action(tool.short + ": " + String(error.message).replace(/^\s*!!\s*/, "").slice(0, BED_TOOL_ERROR_MAX_CHARS));
        controller.closeManualProbe();
      }
    });
    return () => {
      cancelled = true;
      clearInterval(timer);
      stopWatching();
    };
  }, []);

  const send = async (command) => {
    if (busy) return;
    setBusy(command);
    const sent = await sendLongGcode(command);
    setBusy("");
    if (!sent.ok) toast.action(tool.short + ": " + String(sent.message || tx("unknown error")).replace(/^\s*!!\s*/, "").slice(0, BED_TOOL_ERROR_MAX_CHARS));
    else if (command === "ACCEPT") {
      setAccepted((n) => n + 1);
      setProbe((current) => current && { ...current, is_active: false }); // Klipper goes on to the next point: wait for it
    }
    else if (command === "ABORT") controller.closeManualProbe();
  };
  const active = Boolean(probe && probe.is_active);
  const close = () => (active ? send("ABORT") : controller.closeManualProbe());
  useBackHandler(close, true);
  const total = controller.twistSamples;
  const z = probe && typeof probe.z_position === "number" ? probe.z_position.toFixed(3) : "–";

  return h(
    "div",
    { className: "sheet-overlay sheet-overlay--screws", onClick: (event) => event.target === event.currentTarget && close() },
    h(
      "div",
      { className: "sheet-card sheet-card--column manual-probe", "data-state": active ? "active" : "waiting" },
      h(
        "div",
        { className: "sheet-header sheet-header--bar" },
        h("div", null, h("div", { className: "dialog-title" }, tx("Axis ") + tool.axis), h("div", { className: "dialog-sub" }, "Axis twist compensation")),
        h("button", { className: "dialog-close", onClick: close, "aria-label": tx("Close") }, "✕"),
      ),
      h(
        "div",
        { className: "screws-body" },
        h(
          "div",
          { className: "bed-screws__screw" },
          h("span", { className: "bed-screws__step" }, tx("Point {n} of {total}", { n: Math.min(accepted + 1, total), total })),
          h("span", { className: "bed-screws__name manual-probe__z" }, active ? "Z " + z : tx("Klipper is measuring with the probe…")),
        ),
        h(
          "ol",
          { className: "bed-screws__how" },
          h("li", null, tx("Slide a sheet of paper between the nozzle and the bed.")),
          h("li", null, tx("Bring the nozzle down (−) or up (+) until the paper drags a little as it moves.")),
          h("li", null, tx("Then «Accept»: Klipper measures the next point, up to the last one.")),
        ),
        h(
          "div",
          { className: "manual-probe__steps" },
          TESTZ_STEPS.map((step) =>
            h(
              "button",
              { key: step, type: "button", className: cx("oui-btn oui-btn--sm manual-probe__step", busy === "TESTZ Z=" + step && "is-busy"), disabled: Boolean(busy) || !active, onClick: () => send("TESTZ Z=" + step) },
              (step > 0 ? "+" : "−") + Math.abs(step),
            ),
          ),
        ),
      ),
      h(
        "div",
        { className: "sheet-footer" },
        h("button", { className: "oui-btn", disabled: Boolean(busy), onClick: close }, active ? tx("Abort") : tx("Close")),
        h("button", { className: cx("oui-btn oui-btn--primary", busy === "ACCEPT" && "is-busy"), disabled: Boolean(busy) || !active, onClick: () => send("ACCEPT") }, tx("Accept")),
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
    h(Presence, null, controller.bedScrews && h(BedScrewsSheet, { controller })),
    h(Presence, null, controller.manualProbe && h(ManualProbeSheet, { controller })),
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
