/* ============================================================================
   45 · PRINT PROGRESS
   Polls Klipper for the running job and shows file, progress, elapsed and
   remaining time, layer, thumbnail and the PAUSA / CANCELLA STAMPA buttons.
   The card only appears while a job is running or paused.
   1.30 (roadmap 6b part 1), like Mainsail: when it ends (clock time), live speed
   and volumetric flow, and under «More details» the estimates one by one (file,
   filament, slicer), filament used, height, speed and flow factors; «Exclude an
   object» (Klipper's exclude_object) with a map of the objects on the bed.
   ========================================================================== */

const CONTROL_LOCK_MS = 1500;
const CANCEL_TOAST_MS = 3000;

/** "mm:ss" under an hour, "Xh Ym" above, "--:--" when unknown. */
function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || isNaN(seconds) || seconds <= 0) return "--:--";
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours > 0) return hours + "h " + minutes + "m";
  return String(minutes).padStart(2, "0") + ":" + String(total % 60).padStart(2, "0");
}

/** The remaining time by each method, in seconds (null when it does not apply): file (progress), filament, slicer. */
/** A time estimate worth showing (positive and finite), else null. */
const usableEstimate = (value) => (value > 0 && isFinite(value) ? value : null);

function remainingEstimates(printDuration, progress, filamentUsed, meta) {
  const usable = usableEstimate;
  const out = { file: null, filament: null, slicer: null };
  if (progress > 0.02 && printDuration > 30) out.file = usable((printDuration / progress) * (1 - progress));
  if (meta && meta.filament_total && filamentUsed > 0 && meta.filament_total > filamentUsed) out.filament = usable((printDuration / filamentUsed) * (meta.filament_total - filamentUsed));
  if (meta && meta.estimated_time) out.slicer = usable(meta.estimated_time - printDuration);
  return out;
}

/**
 * Remaining time in seconds, as the average of the available estimates
 * (progress-based, filament-based, slicer estimate); null when none applies.
 */
function estimateRemainingSeconds(printDuration, progress, filamentUsed, meta) {
  const parts = remainingEstimates(printDuration, progress, filamentUsed, meta);
  const estimates = [parts.file, parts.filament, parts.slicer].filter((value) => value !== null);
  if (estimates.length > 0) return estimates.reduce((sum, value) => sum + value, 0) / estimates.length;
  if (progress > 0 && printDuration > 0) {
    const fallback = (printDuration / progress) * (1 - progress);
    // 1.33.1: this called a helper that only exists inside remainingEstimates: after a finished print (progress 100 %, a
    // duration) every poll stopped here, the status never loaded and the tools waited for it for ever
    if (usableEstimate(fallback)) return fallback;
  }
  return null;
}

/** "12/340", "12/-", "-/340" or "-/-". */
function layerText(printInfo, displayMessage, meta, progress) {
  let current = null;
  let total = null;
  if (printInfo) {
    current = printInfo.current_layer || printInfo.currentLayer || null;
    total = printInfo.total_layer || printInfo.totalLayer || null;
  }
  if (meta && !total) total = meta.layer_count || null;
  if (!current && displayMessage) {
    const match = displayMessage.match(/layer\s*(\d+)\s*\/\s*(\d+)/i);
    if (match) {
      current = parseInt(match[1]);
      if (!total) total = parseInt(match[2]);
    }
  }
  if (!current && total && progress > 0) current = Math.round(total * progress);
  if (current && total) return current + "/" + total;
  if (current) return current + "/-";
  if (total) return "-/" + total;
  return "-/-";
}

/** URL of the largest thumbnail Moonraker extracted from the G-code, or null. */
function largestThumbnailUrl(meta) {
  if (!meta.thumbnails || meta.thumbnails.length === 0) return null;
  const best = meta.thumbnails.slice().sort((a, b) => (b.width || 0) - (a.width || 0))[0];
  if (best.relative_path) return "/server/files/gcodes/" + best.relative_path;
  return best.absolute_path || null;
}

/** The metadata of a file does not change while it is the current one: the last answer is kept until the name changes. */
const printMetadataCache = { filename: "", meta: null };

async function fetchFileMetadata(filename) {
  if (!filename) return null;
  if (printMetadataCache.filename === filename && printMetadataCache.meta) return printMetadataCache.meta;
  try {
    const response = await fetchFresh("/server/files/metadata?filename=" + encodeURIComponent(filename));
    if (!response.ok) return null;
    const meta = (await response.json()).result || null;
    if (meta) {
      printMetadataCache.filename = filename;
      printMetadataCache.meta = meta;
    }
    return meta;
  } catch (e) {
    return null;
  }
}

const PRINT_STATUS_QUERY =
  "print_stats=state,filename,print_duration,total_duration,filament_used,info&virtual_sdcard=progress,file_position,is_active&display_status=progress,message" +
  "&gcode_move=speed_factor,extrude_factor,speed,gcode_position&motion_report=live_velocity,live_extruder_velocity&exclude_object=objects,excluded_objects,current_object";

/** Raw print_stats / virtual_sdcard / display_status / file metadata, or null. */
async function fetchPrintObjects() {
  try {
    const response = await fetchFresh("/printer/objects/query?" + PRINT_STATUS_QUERY);
    if (!response.ok) {
      const fallback = await fetchFresh("/printer/objects/query?print_stats");
      if (!fallback.ok) return null;
      const status = ((await fallback.json()).result || {}).status || {};
      return { stats: status.print_stats || {}, sdcard: {}, display: {}, meta: null };
    }
    const status = ((await response.json()).result || {}).status || {};
    const stats = status.print_stats || {};
    return {
      stats,
      sdcard: status.virtual_sdcard || {},
      display: status.display_status || {},
      move: status.gcode_move || {},
      motion: status.motion_report || {},
      exclude: status.exclude_object || null,
      meta: stats.filename ? await fetchFileMetadata(stats.filename) : null,
    };
  } catch (e) {
    return null;
  }
}

const IDLE_PRINT_STATUS = {
  loaded: false, // true once Klipper has answered at least once
  printing: false,
  state: "-",
  filename: "-",
  pct: 0,
  time: "--:--",
  remaining: "--:--",
  layer: "-/-",
  thumbnail: null,
  eta: null, // the clock time it should end ("14:32", "tomorrow 02:10")
  speed: null, // { live, requested } mm/s
  flow: null, // mm³/s
  factors: { speed: null, flow: null }, // M220 / M221, %
  estimates: { file: null, filament: null, slicer: null }, // remaining, formatted
  totalTime: "--:--",
  slicerTotal: null,
  filament: null, // { used, total } m, { usedG, totalG } g
  height: null, // { now, total } mm
  objects: [], // exclude_object: [{ name, polygon, center, excluded, current }]
  axisLimits: DEFAULT_AXIS_LIMITS,
};

/** "14:32", or "tomorrow 02:10" / "05/11 02:10" when it ends another day. */
function formatEndTime(secondsFromNow, now = Date.now()) {
  if (secondsFromNow === null || !isFinite(secondsFromNow)) return null;
  const end = new Date(now + secondsFromNow * 1000);
  const time = String(end.getHours()).padStart(2, "0") + ":" + String(end.getMinutes()).padStart(2, "0");
  const today = new Date(now);
  const days = Math.round((new Date(end.getFullYear(), end.getMonth(), end.getDate()) - new Date(today.getFullYear(), today.getMonth(), today.getDate())) / 86400000);
  if (days === 0) return time;
  if (days === 1) return tx("tomorrow {time}", { time });
  return String(end.getDate()).padStart(2, "0") + "/" + String(end.getMonth() + 1).padStart(2, "0") + " " + time;
}

/** The objects of exclude_object, each with whether it is excluded or being printed now. */
function excludeObjects(exclude) {
  if (!exclude || !Array.isArray(exclude.objects)) return [];
  const excluded = new Set(exclude.excluded_objects || []);
  return exclude.objects
    .filter((object) => object && object.name)
    .map((object) => ({
      name: object.name,
      polygon: Array.isArray(object.polygon) ? object.polygon : [],
      center: Array.isArray(object.center) ? object.center : null,
      excluded: excluded.has(object.name),
      current: exclude.current_object === object.name,
    }));
}

function usePrintStatus(capabilities) {
  const [status, setStatus] = useState(IDLE_PRINT_STATUS);
  const caps = useRef(capabilities);
  caps.current = capabilities;

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      const data = await fetchPrintObjects();
      if (!data || cancelled) return;
      try {
        applyPrintObjects(data);
      } catch (error) {
        // a value nobody expected must not stop the status for good: what is sure is still known
        console.error("print status", error);
        const state = (data.stats && data.stats.state) || "standby";
        const filename = (data.stats && data.stats.filename) || "";
        setStatus((previous) => ({ ...previous, loaded: true, state, printing: (state === "printing" || state === "paused") && !!filename }));
      }
    };
    const applyPrintObjects = (data) => {
      const { stats, sdcard, display, meta, move = {}, motion = {}, exclude } = data;
      const state = stats.state || "standby";
      const filename = stats.filename || sdcard.file_path || "";
      let progress = sdcard.progress || display.progress || 0;
      if (progress > 1) progress = progress / 100;
      const pct = clamp(Math.round(progress * 100) || 0, 0, 100);
      const printDuration = stats.print_duration || 0;
      const filamentUsed = stats.filament_used || 0;
      const remaining = estimateRemainingSeconds(printDuration, progress, filamentUsed, meta);
      const parts = remainingEstimates(printDuration, progress, filamentUsed, meta);
      const diameter = (caps.current && caps.current.filamentDiameter) || 1.75;
      const number = (value) => (typeof value === "number" && isFinite(value) ? value : null);
      const speedFactor = number(move.speed_factor);
      const liveSpeed = number(motion.live_velocity);
      const liveExtrude = number(motion.live_extruder_velocity);
      const position = Array.isArray(move.gcode_position) ? move.gcode_position : null;
      setStatus((previous) => ({
        loaded: true,
        printing: (state === "printing" || state === "paused" || !!sdcard.is_active) && !!filename,
        state,
        filename: filename ? filename.split("/").pop() : "-",
        filePath: filename || "", // 1.49: the whole path (the G-code viewer opens it)
        pct,
        time: formatDuration(printDuration),
        remaining: remaining ? formatDuration(remaining) : "--:--",
        layer: layerText(stats.info, display.message, meta, progress),
        thumbnail: meta ? largestThumbnailUrl(meta) : previous.thumbnail,
        eta: remaining ? formatEndTime(remaining) : null,
        speed: liveSpeed !== null || number(move.speed) !== null ? { live: liveSpeed, requested: number(move.speed) !== null ? (move.speed / 60) * (speedFactor || 1) : null } : null,
        flow: liveExtrude !== null ? Math.max(0, liveExtrude) * Math.PI * (diameter / 2) ** 2 : null,
        factors: { speed: speedFactor !== null ? Math.round(speedFactor * 100) : null, flow: number(move.extrude_factor) !== null ? Math.round(move.extrude_factor * 100) : null },
        estimates: { file: parts.file ? formatDuration(parts.file) : null, filament: parts.filament ? formatDuration(parts.filament) : null, slicer: parts.slicer ? formatDuration(parts.slicer) : null },
        totalTime: formatDuration(stats.total_duration || 0),
        slicerTotal: meta && meta.estimated_time ? formatDuration(meta.estimated_time) : null,
        filament: filamentUsed || (meta && meta.filament_total)
          ? {
              used: filamentUsed / 1000,
              total: meta && meta.filament_total ? meta.filament_total / 1000 : null,
              totalG: meta && meta.filament_weight_total ? meta.filament_weight_total : null,
              usedG: meta && meta.filament_weight_total && meta.filament_total ? (meta.filament_weight_total * filamentUsed) / meta.filament_total : null,
            }
          : null,
        height: position ? { now: position[2], total: meta && meta.object_height ? meta.object_height : null } : null,
        objects: excludeObjects(exclude),
        axisLimits: (caps.current && caps.current.axisLimits) || DEFAULT_AXIS_LIMITS,
      }));
    };
    const stopPolling = startPolling(poll, POLL_MS.printProgress);
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, []);

  return status;
}

/**
 * Why actions that move the machine or query its sensors must wait, or null when they may go ahead.
 * Until Klipper has answered once the printer might be printing, so that counts as busy too.
 */
const printLockReason = (printStatus) => (printStatus.printing ? tx("Not available during a print") : !printStatus.loaded ? tx("Waiting for the printer status") : null);

/** PAUSA/RIPRENDI and CANCELLA STAMPA (with confirmation); each locks for 1.5 s. */
function usePrintControls(state) {
  const [confirmingCancel, setConfirmingCancel] = useState(false);
  const pauseLocked = useRef(false);
  const cancelLocked = useRef(false);
  const lockFor = (ref) => {
    ref.current = true;
    setTimeout(() => (ref.current = false), CONTROL_LOCK_MS);
  };

  const togglePause = async () => {
    if (pauseLocked.current) return;
    pauseLocked.current = true;
    try {
      await sendGcode(state === "paused" ? "RESUME" : "PAUSE");
    } catch (e) {}
    lockFor(pauseLocked);
  };

  const cancelPrint = async () => {
    setConfirmingCancel(false);
    if (cancelLocked.current) return;
    cancelLocked.current = true;
    try {
      await sendGcode("CANCEL_PRINT");
      toast.notice(tx("CANCEL PRINT sent"), CANCEL_TOAST_MS);
    } catch (e) {}
    lockFor(cancelLocked);
  };

  return { confirmingCancel, askCancel: () => setConfirmingCancel(true), dismissCancel: () => setConfirmingCancel(false), togglePause, cancelPrint };
}

/* ---------------------------------------------------------------------------
   UI
   ------------------------------------------------------------------------- */
function PrintStat({ label, value }) {
  return h("div", { className: "print-stat" }, h("div", { className: "oui-caption" }, label), h("div", { className: "print-stat__value" }, value));
}

const fmt1 = (value) => formatNumber(Math.round(value * 10) / 10);

/** 1.30: the second row of figures: when it ends, the speed now, the volumetric flow now. */
function PrintLiveStats({ status, className }) {
  const speed = status.speed && status.speed.live !== null ? Math.round(status.speed.live) + " mm/s" : "–";
  const flow = status.flow !== null ? fmt1(status.flow) + " mm³/s" : "–";
  return h(
    "div",
    { className: cx("print-live", className), "data-print-live": "1" },
    h(PrintStat, { label: tx("Ends at"), value: status.eta || "--:--" }),
    h(PrintStat, { label: tx("Speed"), value: speed }),
    h(PrintStat, { label: tx("Flow"), value: flow }),
  );
}

/** 1.30: everything else Mainsail shows, folded: the estimates one by one, filament, height, the factors. */
function PrintDetails({ status }) {
  const row = (label, value, key) => value !== null && value !== undefined && h("div", { key: key || label, className: "print-details__row" }, h("span", { className: "print-details__label" }, label), h("span", { className: "print-details__value" }, value));
  const e = status.estimates || {};
  const f = status.filament;
  const height = status.height;
  return h(
    "details",
    { className: "print-details", "data-print-details": "1" },
    h("summary", null, tx("More details")),
    h(
      "div",
      { className: "print-details__list" },
      row(tx("Remaining by the file"), e.file),
      row(tx("Remaining by the filament"), e.filament),
      row(tx("Remaining by the slicer"), e.slicer),
      row(tx("Slicer's estimate (whole print)"), status.slicerTotal),
      row(tx("Total time (with pauses)"), status.totalTime),
      f && row(tx("Filament"), fmt1(f.used) + (f.total ? " / " + fmt1(f.total) : "") + " m" + (f.usedG !== null && f.totalG ? " • " + Math.round(f.usedG) + " / " + Math.round(f.totalG) + " g" : "")),
      height && row(tx("Height"), fmt1(height.now) + (height.total ? " / " + fmt1(height.total) : "") + " mm"),
      status.speed && row(tx("Speed now / requested"), (status.speed.live !== null ? Math.round(status.speed.live) : "–") + " / " + (status.speed.requested !== null ? Math.round(status.speed.requested) : "–") + " mm/s"),
      status.factors.speed !== null && row(tx("Speed factor"), status.factors.speed + "%"),
      status.factors.flow !== null && row(tx("Flow factor"), status.factors.flow + "%"),
    ),
  );
}

/** 1.30: «Exclude an object»: the button, when Klipper knows the objects of the print (exclude_object). */
function ExcludeObjectButton({ status }) {
  const [open, setOpen] = useState(false);
  const objects = status.objects || [];
  if (objects.length < 2) return null;
  const left = objects.filter((o) => !o.excluded).length;
  return h(
    React.Fragment,
    null,
    h("button", { type: "button", className: "oui-btn oui-btn--sm print-exclude-btn", "data-exclude-open": objects.length, onClick: () => setOpen(true) }, tx("Exclude an object ({left} of {count} printing)", { left, count: objects.length })),
    h(Presence, null, open && h(ExcludeObjectDialog, { status, onClose: () => setOpen(false) })),
  );
}

/** The map of the objects on the bed (seen from above, front at the bottom) and their list; one is chosen, then confirmed. */
function ExcludeObjectDialog({ status, onClose }) {
  const [chosen, setChosen] = useState(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  useBodyScrollLock(true);
  useBackHandler(() => {
    if (chosen) setChosen(null);
    else onClose();
    return true;
  });
  const objects = status.objects || [];
  const [x0, x1] = status.axisLimits.X;
  const [y0, y1] = status.axisLimits.Y;
  const width = x1 - x0;
  const height = y1 - y0;
  const point = ([x, y]) => (x - x0) + "," + (y1 - y); // SVG y down: the back of the bed at the top
  const exclude = async () => {
    setBusy(true);
    try {
      await sendGcode("EXCLUDE_OBJECT NAME=" + chosen);
      toast.notice(tx("«{name}» excluded: it is not printed any more", { name: chosen }), CANCEL_TOAST_MS);
      setChosen(null);
      onClose();
    } catch (error) {
      setProblem(tx("Not excluded: ") + (error && error.message ? error.message : ""));
    }
    setBusy(false);
  };
  return h(
    "div",
    { className: "confirm-overlay", onClick: (event) => event.target === event.currentTarget && onClose() },
    h(
      "div",
      { className: "confirm-card exclude-card", role: "dialog", "aria-modal": "true", "aria-label": tx("Exclude an object"), "data-exclude-dialog": "1", onClick: (event) => event.stopPropagation() },
      h("div", { className: "dialog-head" }, h("div", null, h("div", { className: "dialog-title" }, tx("Exclude an object")), h("div", { className: "dialog-sub" }, tx("The object chosen is not printed any more; the others go on.")))),
      h(
        "svg",
        { className: "exclude-map", viewBox: "0 0 " + width + " " + height, role: "img", "aria-label": tx("The objects on the bed") },
        h("rect", { className: "exclude-map__bed", x: 0, y: 0, width, height, rx: Math.max(width, height) * 0.02 }),
        objects.map((object) =>
          object.polygon.length > 2
            ? h("polygon", {
                key: object.name,
                points: object.polygon.map(point).join(" "),
                className: cx("exclude-map__object", object.excluded && "is-excluded", object.current && "is-current", chosen === object.name && "is-chosen"),
                "data-object": object.name,
                onClick: () => !object.excluded && setChosen(object.name),
              })
            : object.center && h("circle", { key: object.name, cx: object.center[0] - x0, cy: y1 - object.center[1], r: Math.max(width, height) * 0.02, className: cx("exclude-map__object", object.excluded && "is-excluded", chosen === object.name && "is-chosen"), onClick: () => !object.excluded && setChosen(object.name) }),
        ),
      ),
      h(
        "div",
        { className: "exclude-list" },
        objects.map((object) =>
          h(
            "button",
            {
              key: object.name,
              type: "button",
              disabled: object.excluded,
              className: cx("exclude-list__row", chosen === object.name && "is-chosen"),
              "data-object-row": object.name,
              onClick: () => setChosen(object.name),
            },
            h("span", { className: "exclude-list__name" }, object.name),
            h("span", { className: cx("oui-badge", object.excluded ? "" : object.current ? "oui-badge--info" : "oui-badge--ok") }, object.excluded ? tx("excluded") : object.current ? tx("printing now") : tx("printing")),
          ),
        ),
      ),
      chosen && h("p", { className: "dialog-text exclude-warn", role: "alert" }, tx("Exclude «{name}»? From now on it is not printed; it cannot be put back in this print.", { name: chosen })),
      problem && h("p", { className: "set-field__error", role: "alert" }, problem),
      h(
        "div",
        { className: "oui-btn-row" },
        h("button", { type: "button", className: "oui-btn", onClick: onClose }, tx("Close")),
        h("button", { type: "button", className: "oui-btn oui-btn--danger", disabled: !chosen || busy, "data-exclude-confirm": "1", onClick: exclude }, chosen ? tx("Exclude it") : tx("Choose an object")),
      ),
    ),
  );
}

function PrintProgressCard({ status, controls, monitor }) {
  const [thumbBroken, setThumbBroken] = useState(false);
  useEffect(() => setThumbBroken(false), [status.thumbnail]);
  const showThumb = !!status.thumbnail && !thumbBroken;

  return h(
    Card,
    { className: "md:col-span-2" },
    h(CardHeader, { title: tx("Printing") }, h("span", { className: "oui-badge oui-badge--info print-pct" }, status.pct + "%")),
    h(
      "div",
      { className: "flex items-center gap-4 mb-4" },
      h(
        "div",
        { className: "print-thumb" },
        h("img", {
          className: cx("w-full h-full", !showThumb && "hidden"),
          src: showThumb ? status.thumbnail : undefined,
          alt: "thumb",
          onError: () => setThumbBroken(true),
        }),
        !showThumb && h(PrintPlaceholder),
      ),
      h(
        "div",
        { className: "flex-1 min-w-0" },
        h("div", { className: "print-file" }, status.filename),
        h("div", { className: "oui-progress" }, h("div", { className: "oui-progress__bar", style: { width: status.pct + "%" } })),
      ),
    ),
    h(
      "div",
      { className: "grid grid-cols-3 mb-4" },
      h(PrintStat, { label: tx("Time"), value: status.time }),
      h(PrintStat, { label: tx("Remaining"), value: status.remaining }),
      h(PrintStat, { label: "Layer", value: status.layer }),
    ),
    h(PrintLiveStats, { status, className: "grid grid-cols-3 mb-4" }),
    h(PrintDetails, { status }),
    h(AiAlarmQuestion, { monitor }),
    h(GcodeViewButton, { status }),
    h(ExcludeObjectButton, { status }),
    h(
      "div",
      { className: "oui-btn-row" },
      h("button", { onClick: controls.togglePause, className: "oui-btn" }, status.state === "paused" ? tx("Resume") : tx("Pause")),
      h("button", { onClick: controls.askCancel, className: "oui-btn oui-btn--danger-soft" }, tx("Cancel print")),
    ),
  );
}

function CancelPrintDialog({ open, onConfirm, onCancel }) {
  return h(ConfirmDialog, {
    open,
    tone: "danger",
    icon: h(Icons.CancelCircle),
    title: tx("Cancel print"),
    subtitle: tx("Cannot be undone"),
    message: [
      tx("The current print will be "),
      h("b", { key: "warn" }, tx("stopped immediately")),
      tx(". File, progress and heaters will be reset. Confirm?"),
    ],
    confirmLabel: txc("action", "Cancel"),
    onConfirm,
    onCancel,
  });
}
