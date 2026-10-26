/* ============================================================================
   45 · PRINT PROGRESS
   Polls Klipper for the running job and shows file, progress, elapsed and
   remaining time, layer, thumbnail and the PAUSA / CANCELLA STAMPA buttons.
   The card only appears while a job is running or paused.
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

/**
 * Remaining time in seconds, as the average of the available estimates
 * (progress-based, filament-based, slicer estimate); null when none applies.
 */
function estimateRemainingSeconds(printDuration, progress, filamentUsed, meta) {
  const estimates = [];
  const usable = (value) => value > 0 && isFinite(value);
  if (progress > 0.02 && printDuration > 30) {
    const byProgress = (printDuration / progress) * (1 - progress);
    if (usable(byProgress)) estimates.push(byProgress);
  }
  if (meta && meta.filament_total && filamentUsed > 0) {
    const filamentLeft = meta.filament_total - filamentUsed;
    if (filamentLeft > 0) {
      const byFilament = (printDuration / filamentUsed) * filamentLeft;
      if (usable(byFilament)) estimates.push(byFilament);
    }
  }
  if (meta && meta.estimated_time) {
    const bySlicer = meta.estimated_time - printDuration;
    if (bySlicer > 0) estimates.push(bySlicer);
  }
  if (estimates.length > 0) return estimates.reduce((sum, value) => sum + value, 0) / estimates.length;
  if (progress > 0 && printDuration > 0) {
    const fallback = (printDuration / progress) * (1 - progress);
    if (usable(fallback)) return fallback;
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
  "print_stats=state,filename,print_duration,total_duration,filament_used,info&virtual_sdcard=progress,file_position,is_active&display_status=progress,message";

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
    return { stats, sdcard: status.virtual_sdcard || {}, display: status.display_status || {}, meta: stats.filename ? await fetchFileMetadata(stats.filename) : null };
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
};

function usePrintStatus() {
  const [status, setStatus] = useState(IDLE_PRINT_STATUS);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      const data = await fetchPrintObjects();
      if (!data || cancelled) return;
      const { stats, sdcard, display, meta } = data;
      const state = stats.state || "standby";
      const filename = stats.filename || sdcard.file_path || "";
      let progress = sdcard.progress || display.progress || 0;
      if (progress > 1) progress = progress / 100;
      const pct = clamp(Math.round(progress * 100) || 0, 0, 100);
      const printDuration = stats.print_duration || 0;
      const remaining = estimateRemainingSeconds(printDuration, progress, stats.filament_used || 0, meta);
      setStatus((previous) => ({
        loaded: true,
        printing: (state === "printing" || state === "paused" || !!sdcard.is_active) && !!filename,
        state,
        filename: filename ? filename.split("/").pop() : "-",
        pct,
        time: formatDuration(printDuration),
        remaining: remaining ? formatDuration(remaining) : "--:--",
        layer: layerText(stats.info, display.message, meta, progress),
        thumbnail: meta ? largestThumbnailUrl(meta) : previous.thumbnail,
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
const printLockReason = (printStatus) => (printStatus.printing ? "Non disponibile durante una stampa" : !printStatus.loaded ? "Attendo lo stato della stampante" : null);

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
      toast.notice("CANCELLA STAMPA inviato", CANCEL_TOAST_MS);
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

function PrintProgressCard({ status, controls }) {
  const [thumbBroken, setThumbBroken] = useState(false);
  useEffect(() => setThumbBroken(false), [status.thumbnail]);
  const showThumb = !!status.thumbnail && !thumbBroken;

  return h(
    Card,
    { className: "md:col-span-2" },
    h(CardHeader, { title: "Stampa in corso" }, h("span", { className: "oui-badge oui-badge--info print-pct" }, status.pct + "%")),
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
      h(PrintStat, { label: "Tempo", value: status.time }),
      h(PrintStat, { label: "Rimanente", value: status.remaining }),
      h(PrintStat, { label: "Layer", value: status.layer }),
    ),
    h(
      "div",
      { className: "oui-btn-row" },
      h("button", { onClick: controls.togglePause, className: "oui-btn" }, status.state === "paused" ? "Riprendi" : "Pausa"),
      h("button", { onClick: controls.askCancel, className: "oui-btn oui-btn--danger-soft" }, "Cancella stampa"),
    ),
  );
}

function CancelPrintDialog({ open, onConfirm, onCancel }) {
  return h(ConfirmDialog, {
    open,
    tone: "danger",
    icon: h(Icons.CancelCircle),
    title: "Cancella stampa",
    subtitle: "Azione irreversibile",
    message: [
      "La stampa in corso verrà ",
      h("b", { key: "warn" }, "interrotta immediatamente"),
      ". File, progresso e riscaldatori verranno resettati. Confermi?",
    ],
    confirmLabel: "Cancella",
    onConfirm,
    onCancel,
  });
}
