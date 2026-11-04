/* ============================================================================
   47b · PRINT HISTORY AND STATISTICS (1.42, roadmap 6d part 1)
   What Moonraker's [history] keeps of every print, as Mainsail shows it:
     · the statistics: prints, print time, filament, longest and average print,
       how many finished; how they ended (a bar), and the last 14 days (print
       time or filament a day);
     · the list: searched, filtered by how they ended; a tap opens a job with
       its figures, your note (kept in Moonraker's database, shared by every
       device), Print again and Remove from the history.
   The Files page switches between the print files and this (kept per device).
   ========================================================================== */

const HISTORY_PAGE = 200; // jobs asked for at a time
const HISTORY_MAX_JOBS = 2000; // the statistics of the page are worked out from at most this many (the newest)
const HISTORY_POLL_MS = 30000;
const HISTORY_SHOWN_STEP = 30; // rows shown at first, and added by "Show more"
const HISTORY_DAYS = 14;
const HISTORY_NOTES_KEY = "history_notes"; // { job_id: text } in the dashboard's namespace of Moonraker's database
const HISTORY_NOTE_MAX = 500;

/* ---------------------------------------------------------------------------
   Moonraker's history API
   ------------------------------------------------------------------------- */
/** A clear message for a history that cannot be read: Moonraker answers 404 when [history] is not in moonraker.conf. */
async function historyError(response) {
  if (response.status === 404) return tx("Moonraker keeps no print history: add [history] to moonraker.conf and restart Moonraker.");
  return responseError(response);
}

const historyApi = {
  /** Every job, newest first (at most HISTORY_MAX_JOBS). */
  async jobs() {
    let all = [];
    for (let start = 0; start < HISTORY_MAX_JOBS; start += HISTORY_PAGE) {
      const response = await fetchFresh("/server/history/list?limit=" + HISTORY_PAGE + "&start=" + start + "&order=desc");
      if (!response.ok) throw new Error(await historyError(response));
      const result = (await response.json()).result || {};
      const jobs = Array.isArray(result.jobs) ? result.jobs : [];
      all = all.concat(jobs);
      if (jobs.length < HISTORY_PAGE || all.length >= (result.count || 0)) break;
    }
    return all;
  },
  /** Moonraker's own totals (they count every job ever, also the ones removed from the list). */
  async totals() {
    const response = await fetchFresh("/server/history/totals");
    if (!response.ok) throw new Error(await historyError(response));
    return ((await response.json()).result || {}).job_totals || {};
  },
  async remove(uid) {
    const response = await fetchFresh("/server/history/job?uid=" + encodeURIComponent(uid), { method: "DELETE" });
    if (!response.ok) throw new Error(await responseError(response));
  },
  async resetTotals() {
    const response = await fetchFresh("/server/history/reset_totals", { method: "POST" });
    if (!response.ok) throw new Error(await responseError(response));
  },
};

/** The jobs and totals, read again every HISTORY_POLL_MS while `active`, and the notes. */
function useHistory(active) {
  const [state, setState] = useState({ jobs: [], totals: null, loading: true, error: null });
  const [notes, setNotes] = useState({});
  const refreshRef = useRef(null);
  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    const refresh = async () => {
      try {
        const [jobs, totals] = await Promise.all([historyApi.jobs(), historyApi.totals()]);
        if (!cancelled) setState({ jobs, totals, loading: false, error: null });
      } catch (error) {
        if (!cancelled) setState((previous) => ({ ...previous, loading: false, error: error.message || tx("Error") }));
      }
      try {
        const stored = await readSettingsDb(HISTORY_NOTES_KEY);
        if (!cancelled && stored.ok) setNotes(isPlainObject(stored.value) ? stored.value : {});
      } catch (error) {}
    };
    refreshRef.current = refresh;
    const stop = startPolling(refresh, HISTORY_POLL_MS);
    return () => {
      cancelled = true;
      stop();
    };
  }, [active]);
  return {
    ...state,
    notes,
    reload: () => refreshRef.current && refreshRef.current(),
    /** Takes a job off the list at once (after Moonraker removed it). */
    forget: (uid) => setState((previous) => ({ ...previous, jobs: previous.jobs.filter((job) => job.job_id !== uid) })),
    /** Saves the note of a job (empty: removed); the notes of the others as they are now on the Raspberry. */
    async saveNote(uid, text) {
      const stored = await readSettingsDb(HISTORY_NOTES_KEY);
      const next = Object.assign({}, stored.ok && isPlainObject(stored.value) ? stored.value : notes);
      if (text) next[uid] = text.slice(0, HISTORY_NOTE_MAX);
      else delete next[uid];
      const written = await writeSettingsDb(HISTORY_NOTES_KEY, next);
      if (!written.ok) throw new Error(written.detail);
      setNotes(next);
    },
  };
}

/* ---------------------------------------------------------------------------
   Figures
   ------------------------------------------------------------------------- */
/** How a job ended: its words and its tone (ok, muted, danger, accent: the colours of the badges and of the bar). */
function historyStatus(status) {
  switch (status) {
    case "completed":
      return { label: tx("Completed"), tone: "ok" };
    case "cancelled":
      return { label: tx("Cancelled"), tone: "muted" };
    case "in_progress":
      return { label: tx("Printing"), tone: "accent" };
    case "error":
      return { label: tx("Error"), tone: "danger" };
    case "klippy_shutdown":
      return { label: tx("Klipper shut down"), tone: "danger" };
    case "klippy_disconnect":
      return { label: tx("Klipper disconnected"), tone: "danger" };
    case "server_exit":
      return { label: tx("Moonraker stopped"), tone: "danger" };
    case "interrupted":
      return { label: tx("Interrupted"), tone: "danger" };
    default:
      return { label: status || "?", tone: "muted" };
  }
}
const HISTORY_TONE_BADGE = { ok: "oui-badge--ok", danger: "oui-badge--danger", accent: "oui-badge--info", muted: "" };

/** The filters of the list: the tone of the jobs each one keeps (null: all of them). */
const historyFilters = () => [
  { id: "all", label: txc("prints", "All"), tone: null },
  { id: "completed", label: txc("prints", "Completed"), tone: "ok" },
  { id: "cancelled", label: txc("prints", "Cancelled"), tone: "muted" },
  { id: "failed", label: txc("prints", "Failed"), tone: "danger" },
];

const jobName = (job) => String(job.filename || "").split("/").pop() || "?";

/** "4.2 m", "1.35 km" from millimetres; "--" for nothing. */
function formatFilamentLength(millimetres) {
  if (!(millimetres > 0)) return "--";
  const metres = millimetres / 1000;
  if (metres >= 1000) return (metres / 1000).toFixed(2) + " km";
  return (metres >= 100 ? Math.round(metres) : metres.toFixed(metres >= 10 ? 1 : 2)) + " m";
}

/** "3h 12m", "1d 4h" for long totals (formatDuration stops at hours). */
function formatLongDuration(seconds) {
  if (!(seconds > 0)) return "--";
  const days = Math.floor(seconds / 86400);
  if (days === 0) return formatDuration(seconds);
  return days + tx("d") + " " + Math.floor((seconds % 86400) / 3600) + "h";
}

/** "12/03/2026, 14:05" */
function formatJobDate(unixSeconds) {
  if (!(unixSeconds > 0)) return "--";
  try {
    return new Date(unixSeconds * 1000).toLocaleString(LOCALE, { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch (e) {
    return "--";
  }
}

/** The thumbnail of a job: Moonraker keeps the path of each one relative to the folder of the G-code file. */
function jobThumbnail(job) {
  const meta = job.metadata || {};
  if (!job.exists || !Array.isArray(meta.thumbnails) || meta.thumbnails.length === 0) return null;
  const best = meta.thumbnails.slice().sort((a, b) => (b.width || 0) - (a.width || 0))[0];
  if (!best.relative_path) return null;
  const folder = String(job.filename || "").includes("/") ? job.filename.split("/").slice(0, -1).join("/") + "/" : "";
  return "/server/files/gcodes/" + encodeRemotePath(folder + best.relative_path);
}

/**
 * The statistics of the page. The totals are Moonraker's (every print ever); how the prints ended, the average and the
 * days come from the jobs in the list.
 */
function historyStats(jobs, totals) {
  const finished = jobs.filter((job) => job.status !== "in_progress");
  const counts = {};
  for (const job of finished) {
    const tone = historyStatus(job.status).tone;
    counts[tone] = (counts[tone] || 0) + 1;
  }
  const printed = finished.filter((job) => job.print_duration > 0);
  const t = totals || {};
  const totalPrint = t.total_print_time > 0 ? t.total_print_time : printed.reduce((sum, job) => sum + job.print_duration, 0);
  const totalJobs = t.total_jobs > 0 ? t.total_jobs : jobs.length;
  return {
    jobs: totalJobs,
    printTime: totalPrint,
    filament: t.total_filament_used > 0 ? t.total_filament_used : jobs.reduce((sum, job) => sum + (job.filament_used || 0), 0),
    longest: t.longest_print > 0 ? t.longest_print : printed.reduce((most, job) => Math.max(most, job.print_duration), 0),
    average: printed.length ? printed.reduce((sum, job) => sum + job.print_duration, 0) / printed.length : 0,
    counts,
    finished: finished.length,
    successRate: finished.length ? Math.round(((counts.ok || 0) / finished.length) * 100) : null,
  };
}

/** The last `days` days, oldest first: { day (Date at midnight), time (s of printing), filament (mm), jobs }. */
function historyDays(jobs, days = HISTORY_DAYS, now = Date.now()) {
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  const out = [];
  for (let i = days - 1; i >= 0; i--) {
    const day = new Date(today);
    day.setDate(today.getDate() - i);
    out.push({ day, time: 0, filament: 0, jobs: 0 });
  }
  const first = out[0].day.getTime();
  for (const job of jobs) {
    const start = (job.start_time || 0) * 1000;
    if (start < first) continue;
    const day = new Date(start);
    day.setHours(0, 0, 0, 0);
    const slot = out.find((one) => one.day.getTime() === day.getTime());
    if (!slot) continue;
    slot.time += job.print_duration || 0;
    slot.filament += job.filament_used || 0;
    slot.jobs++;
  }
  return out;
}

/* ---------------------------------------------------------------------------
   The page's switch: print files | history (kept on this device)
   ------------------------------------------------------------------------- */
const FILES_SECTION_KEY = "ke_files_section";
const filesSectionStore = (() => {
  const listeners = new Set();
  let current = "files";
  try {
    if (localStorage.getItem(FILES_SECTION_KEY) === "history") current = "history";
  } catch (e) {}
  return {
    subscribe: (fn) => (listeners.add(fn), () => listeners.delete(fn)),
    snapshot: () => current,
    set(value) {
      current = value === "history" ? "history" : "files";
      try {
        localStorage.setItem(FILES_SECTION_KEY, current);
      } catch (e) {}
      listeners.forEach((fn) => fn());
    },
  };
})();
const useFilesSection = () => useSyncExternalStore(filesSectionStore.subscribe, filesSectionStore.snapshot);

function FilesSectionSwitch({ section }) {
  const option = (id, label) => h("button", { type: "button", className: cx(section === id && "is-selected"), "aria-pressed": section === id, "data-files-section": id, onClick: () => filesSectionStore.set(id) }, label);
  return h("div", { className: "oui-segmented files-section-switch", role: "group", "aria-label": tx("Files") }, option("files", tx("Print files")), option("history", tx("History")));
}

/* ---------------------------------------------------------------------------
   Statistics
   ------------------------------------------------------------------------- */
function HistoryStatTile({ label, value, id }) {
  return h("div", { className: "history-stat", "data-stat": id }, h("div", { className: "history-stat__value" }, value), h("div", { className: "history-stat__label" }, label));
}

/** How the prints ended: one bar in parts (2 px apart), each part with its words and count under it. */
function HistoryOutcomeBar({ stats }) {
  const parts = [
    { tone: "ok", label: txc("prints", "Completed") },
    { tone: "muted", label: txc("prints", "Cancelled") },
    { tone: "danger", label: txc("prints", "Failed") },
  ].map((part) => ({ ...part, count: stats.counts[part.tone] || 0 }));
  if (!stats.finished) return null;
  return h(
    "div",
    { className: "history-outcome" },
    h(
      "div",
      { className: "history-outcome__bar", role: "img", "aria-label": parts.map((part) => part.label + " " + part.count).join(", ") },
      parts.filter((part) => part.count > 0).map((part) => h("span", { key: part.tone, className: "history-outcome__part is-" + part.tone, style: { flexGrow: part.count }, title: part.label + ": " + part.count })),
    ),
    h(
      "div",
      { className: "history-outcome__legend" },
      parts.map((part) => h("span", { key: part.tone, className: "history-outcome__key", "data-outcome": part.tone }, h("span", { className: "history-outcome__dot is-" + part.tone }), part.label, h("b", null, part.count))),
    ),
  );
}

/** The last 14 days, a bar a day: print time or filament (one measure at a time). A tap (or the pointer) on a bar says its day and value. */
function HistoryDaysChart({ jobs }) {
  const [measure, setMeasure] = useState("time");
  const [picked, setPicked] = useState(null);
  const days = useMemo(() => historyDays(jobs), [jobs]);
  const valueOf = (day) => (measure === "time" ? day.time : day.filament);
  const format = (value) => (measure === "time" ? (value > 0 ? formatDuration(value) : "0") : value > 0 ? formatFilamentLength(value) : "0");
  const most = Math.max(...days.map(valueOf), 0);
  const dayLabel = (day) => day.toLocaleDateString(LOCALE, { day: "numeric", month: "short" });
  const shown = picked !== null ? days[picked] : null;
  return h(
    "div",
    { className: "history-days" },
    h(
      "div",
      { className: "history-days__head" },
      h("span", { className: "oui-label" }, tx("Last {count} days", { count: HISTORY_DAYS })),
      h(
        "div",
        { className: "oui-segmented oui-segmented--sm", role: "group", "aria-label": tx("Show") },
        h("button", { type: "button", className: cx(measure === "time" && "is-selected"), "aria-pressed": measure === "time", "data-measure": "time", onClick: () => setMeasure("time") }, tx("Print time")),
        h("button", { type: "button", className: cx(measure === "filament" && "is-selected"), "aria-pressed": measure === "filament", "data-measure": "filament", onClick: () => setMeasure("filament") }, tx("Filament")),
      ),
    ),
    h("div", { className: "history-days__readout", "aria-live": "polite" }, shown ? h(React.Fragment, null, h("b", null, format(valueOf(shown))), " · ", dayLabel(shown.day), " · ", shown.jobs === 1 ? tx("1 print") : tx("{count} prints", { count: shown.jobs })) : most > 0 ? h(React.Fragment, null, tx("Most in a day:"), " ", h("b", null, format(most))) : tx("No prints in these days")),
    h(
      "div",
      { className: "history-days__plot", onMouseLeave: () => setPicked(null) },
      days.map((day, index) =>
        h(
          "button",
          {
            key: index,
            type: "button",
            className: cx("history-days__slot", picked === index && "is-picked"),
            "aria-label": dayLabel(day.day) + ": " + format(valueOf(day)),
            "data-day": index,
            onMouseEnter: () => setPicked(index),
            onFocus: () => setPicked(index),
            onClick: () => setPicked(index),
          },
          h("span", { className: "history-days__bar", style: { height: most > 0 ? Math.max(valueOf(day) > 0 ? 4 : 0, (valueOf(day) / most) * 100) + "%" : 0 } }),
        ),
      ),
    ),
    h("div", { className: "history-days__axis" }, h("span", null, dayLabel(days[0].day)), h("span", null, tx("Today"))),
  );
}

function HistoryStatsCard({ history, onReset }) {
  const stats = historyStats(history.jobs, history.totals);
  return h(
    Card,
    { className: "history-stats-card" },
    h(CardHeader, { title: tx("Statistics") }, h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--quiet history-reset", onClick: onReset, disabled: history.loading || !!history.error }, tx("Reset"))),
    history.error
      ? h("div", { className: "oui-tile oui-tile--danger history-error" }, h("div", { className: "oui-notice" }, history.error), h("button", { className: "oui-btn oui-btn--sm", onClick: history.reload }, tx("Retry")))
      : history.loading
        ? h("div", { className: "oui-caption" }, tx("Loading..."))
        : h(
            React.Fragment,
            null,
            h(
              "div",
              { className: "history-stats" },
              h(HistoryStatTile, { id: "jobs", label: tx("Prints"), value: String(stats.jobs) }),
              h(HistoryStatTile, { id: "time", label: tx("Print time"), value: formatLongDuration(stats.printTime) }),
              h(HistoryStatTile, { id: "filament", label: tx("Filament used"), value: formatFilamentLength(stats.filament) }),
              h(HistoryStatTile, { id: "longest", label: tx("Longest print"), value: formatLongDuration(stats.longest) }),
              h(HistoryStatTile, { id: "average", label: tx("Average print"), value: stats.average > 0 ? formatDuration(stats.average) : "--" }),
              h(HistoryStatTile, { id: "success", label: txc("prints", "Completed"), value: stats.successRate === null ? "--" : stats.successRate + "%" }),
            ),
            h(HistoryOutcomeBar, { stats }),
            h(HistoryDaysChart, { jobs: history.jobs }),
          ),
  );
}

/* ---------------------------------------------------------------------------
   The list
   ------------------------------------------------------------------------- */
function HistoryRow({ job, note, onOpen, selected }) {
  const status = historyStatus(job.status);
  const thumbnail = jobThumbnail(job);
  return h(
    "button",
    { type: "button", className: cx("history-row", selected && "is-selected"), "data-job": job.job_id, onClick: () => onOpen(job) },
    h("span", { className: "history-row__thumb oui-well" }, thumbnail ? h("img", { src: thumbnail, className: "file-thumb", draggable: false, loading: "lazy", alt: "" }) : h(Icons.Doc, { size: 20 })),
    h(
      "span",
      { className: "history-row__body" },
      h("span", { className: "history-row__name" }, jobName(job)),
      h(
        "span",
        { className: "history-row__meta" },
        h("span", { className: cx("oui-badge history-row__status", HISTORY_TONE_BADGE[status.tone]), "data-status": job.status }, status.label),
        h("span", null, formatFileDate(job.start_time)),
        h("span", { className: "history-row__fact" }, h(Icons.Clock, { size: 13 }), formatDuration(job.print_duration)),
        job.filament_used > 0 && h("span", { className: "history-row__fact" }, h(Icons.Spool, { size: 13 }), formatFilamentLength(job.filament_used)),
      ),
      note && h("span", { className: "history-row__note" }, h(Icons.Pencil, { size: 12 }), note),
    ),
  );
}

function HistoryListCard({ history, onOpen, selectedId }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [shown, setShown] = useState(HISTORY_SHOWN_STEP);
  const filters = historyFilters();
  const tone = (filters.find((one) => one.id === filter) || filters[0]).tone;
  const needle = query.trim().toLowerCase();
  const jobs = history.jobs.filter((job) => (!tone || historyStatus(job.status).tone === tone) && (!needle || String(job.filename || "").toLowerCase().includes(needle) || (history.notes[job.job_id] || "").toLowerCase().includes(needle)));
  useEffect(() => setShown(HISTORY_SHOWN_STEP), [query, filter]);
  let body;
  if (history.loading) body = h("div", { className: "oui-caption files-notice" }, tx("Loading..."));
  else if (history.error) body = null;
  else if (history.jobs.length === 0) body = h("div", { className: "oui-caption files-notice" }, tx("No prints yet: each print you start appears here."));
  else if (jobs.length === 0) body = h("div", { className: "oui-caption files-notice" }, tx("No print matches"));
  else
    body = h(
      React.Fragment,
      null,
      h(
        "div",
        { className: "history-list" },
        jobs.slice(0, shown).map((job) => h(HistoryRow, { key: job.job_id, job, note: history.notes[job.job_id], onOpen, selected: selectedId === job.job_id })),
      ),
      jobs.length > shown && h("button", { type: "button", className: "oui-btn oui-btn--block history-more", onClick: () => setShown(shown + HISTORY_SHOWN_STEP) }, tx("Show more ({count} left)", { count: jobs.length - shown })),
    );
  return h(
    Card,
    { className: "history-list-card" },
    h(CardHeader, { title: tx("Print history") }, h("span", { className: "oui-badge" }, history.loading ? "..." : (jobs.length !== history.jobs.length ? jobs.length + " / " : "") + history.jobs.length)),
    h(
      "div",
      { className: "files-search" },
      h(Icons.Search, { size: 16 }),
      h("input", { type: "search", className: "oui-field files-search__input history-search", value: query, placeholder: tx("Search prints..."), "aria-label": tx("Search prints..."), onChange: (event) => setQuery(event.target.value) }),
    ),
    h(
      "div",
      { className: "set-chips history-filters", role: "group", "aria-label": tx("How they ended") },
      filters.map((one) => h("button", { key: one.id, type: "button", className: cx("oui-chip", filter === one.id && "is-selected"), "aria-pressed": filter === one.id, "data-filter": one.id, onClick: () => setFilter(one.id) }, one.label)),
    ),
    body,
  );
}

/* ---------------------------------------------------------------------------
   A job
   ------------------------------------------------------------------------- */
function historyJobRows(job) {
  const meta = job.metadata || {};
  const folder = String(job.filename || "").includes("/") ? "/" + job.filename.split("/").slice(0, -1).join("/") : null;
  return [
    [tx("Status"), historyStatus(job.status).label],
    [tx("Folder"), folder],
    [tx("Started"), formatJobDate(job.start_time)],
    [tx("Ended"), job.end_time ? formatJobDate(job.end_time) : null],
    [tx("Print time"), formatDuration(job.print_duration)],
    [tx("Total time"), job.total_duration > 0 ? formatDuration(job.total_duration) : null],
    [tx("Estimated time"), metaNumber(meta.estimated_time) !== null ? formatDuration(meta.estimated_time) : null],
    [tx("Filament used"), job.filament_used > 0 ? formatFilamentLength(job.filament_used) : null],
    [tx("Filament in the file"), metaNumber(meta.filament_total) !== null ? formatFilamentLength(meta.filament_total) : null],
    [tx("Filament weight"), metaNumber(meta.filament_weight_total) !== null ? Math.round(meta.filament_weight_total * 10) / 10 + " g" : null],
    [tx("Filament"), [meta.filament_type, meta.filament_name].filter(Boolean).join(" · ") || null],
    [tx("Slicer"), [meta.slicer, meta.slicer_version].filter(Boolean).join(" ") || null],
    [tx("Layer height"), mm(meta.layer_height, 3)],
    [tx("Object height"), mm(meta.object_height, 1)],
    [tx("File"), job.exists ? tx("Still on the printer") : tx("Deleted")],
  ].filter(([, value]) => value);
}

function HistoryNote({ value, onSave }) {
  const [text, setText] = useState(value || "");
  const [state, setState] = useState("");
  useEffect(() => setText(value || ""), [value]);
  const commit = async () => {
    const clean = text.trim();
    if (clean === (value || "")) return;
    setState(tx("Saving..."));
    try {
      await onSave(clean);
      setState(tx("Saved ✓"));
    } catch (error) {
      setState(tx("Error: ") + (error.message || error));
    }
  };
  return h(
    "label",
    { className: "set-field history-note" },
    h("span", { className: "set-field__label" }, tx("Note")),
    h("textarea", { className: "oui-field set-field__input history-note__input", rows: 2, maxLength: HISTORY_NOTE_MAX, value: text, placeholder: tx("e.g. new spool, warping in a corner…"), onChange: (event) => setText(event.target.value), onBlur: commit }),
    h("span", { className: "set-field__hint" }, state || tx("Kept on the Raspberry: every device sees it.")),
  );
}

function HistoryJobSheet({ job, history, onClose, onPrint }) {
  useBodyScrollLock(true);
  useBackHandler(onClose, true);
  const [confirming, setConfirming] = useState(false);
  const thumbnail = jobThumbnail(job);
  const remove = async () => {
    setConfirming(false);
    try {
      await historyApi.remove(job.job_id);
      history.forget(job.job_id);
      onClose();
      toast.notice(tx("Removed from the history"));
    } catch (error) {
      toast.action(tx("Error: ") + (error.message || error));
    }
  };
  return h(
    "div",
    { className: "sheet-overlay sheet-overlay--details", onClick: (e) => e.target === e.currentTarget && onClose() },
    h(
      "div",
      { className: "sheet-card sheet-card--column file-details history-job", role: "dialog", "aria-label": jobName(job) },
      h("div", { className: "sheet-header sheet-header--bar" }, h("div", { className: "dialog-title file-details__title" }, jobName(job)), h("button", { className: "dialog-close", onClick: onClose, "aria-label": tx("Close") }, "✕")),
      h(
        "div",
        { className: "file-details__body" },
        h("div", { className: "file-details__thumb oui-well" }, thumbnail ? h("img", { src: thumbnail, className: "file-thumb", draggable: false }) : h(PrintPlaceholder)),
        h(
          "dl",
          { className: "file-details__list" },
          historyJobRows(job).map(([label, value]) => h(React.Fragment, { key: label }, h("dt", null, label), h("dd", { "data-detail": label }, value))),
        ),
        h(HistoryNote, { value: history.notes[job.job_id], onSave: (text) => history.saveNote(job.job_id, text) }),
      ),
      h(
        "div",
        { className: "sheet-footer" },
        h("button", { className: "oui-btn oui-btn--danger-soft history-remove", onClick: () => setConfirming(true), disabled: job.status === "in_progress" }, h(Icons.Trash, { size: 16 }), tx("Remove")),
        job.exists &&
          onPrint &&
          h(
            "button",
            {
              className: "oui-btn oui-btn--primary history-reprint",
              onClick: () => {
                onClose();
                onPrint({ path: job.filename, fileName: jobName(job), thumbnail });
              },
            },
            h(Icons.Play, { size: 16 }),
            tx("Print again"),
          ),
      ),
    ),
    h(ConfirmDialog, {
      open: confirming,
      tone: "danger",
      zIndex: 10002,
      icon: h(Icons.Trash),
      title: tx("Remove from the history?"),
      subtitle: jobName(job),
      message: tx("Only this entry of the list goes: the G-code file stays, and so do the totals of the statistics."),
      confirmLabel: tx("Remove"),
      onConfirm: remove,
      onCancel: () => setConfirming(false),
    }),
  );
}

/* ---------------------------------------------------------------------------
   The page
   ------------------------------------------------------------------------- */
/** The history part of the Files page: on a phone the cards one under the other, on a computer side by side. */
function HistoryPage({ desktop, onPrint }) {
  const history = useHistory(true);
  const [openId, setOpenId] = useState(null);
  const [confirmingReset, setConfirmingReset] = useState(false);
  const open = history.jobs.find((job) => job.job_id === openId) || null;
  const resetTotals = async () => {
    setConfirmingReset(false);
    try {
      await historyApi.resetTotals();
      history.reload();
      toast.notice(tx("Statistics reset"));
    } catch (error) {
      toast.action(tx("Error: ") + (error.message || error));
    }
  };
  const stats = h(HistoryStatsCard, { history, onReset: () => setConfirmingReset(true) });
  const list = h(HistoryListCard, { history, onOpen: (job) => setOpenId(job.job_id), selectedId: openId });
  return h(
    React.Fragment,
    null,
    desktop ? h("div", { className: "desk-split desk-split--history" }, h("div", { className: "desk-col" }, stats), h("div", { className: "desk-col" }, list)) : h("div", { className: "history-page" }, stats, list),
    h(Presence, null, open && h(HistoryJobSheet, { job: open, history, onClose: () => setOpenId(null), onPrint })),
    h(ConfirmDialog, {
      open: confirmingReset,
      tone: "danger",
      icon: h(Icons.Refresh),
      title: tx("Reset the statistics?"),
      subtitle: tx("Statistics"),
      message: tx("Moonraker's totals (prints, print time, filament, longest print) start again from zero. The list of prints stays."),
      confirmLabel: tx("Reset"),
      onConfirm: resetTotals,
      onCancel: () => setConfirmingReset(false),
    }),
  );
}

/** The Files page: the switch, then the print files or the history. */
function FilesPage({ desktop, files }) {
  const section = useFilesSection();
  return h(React.Fragment, null, h("div", { className: "files-section-bar" }, h(FilesSectionSwitch, { section })), section === "history" ? h(HistoryPage, { desktop, onPrint: files.onPrint }) : files.content);
}
