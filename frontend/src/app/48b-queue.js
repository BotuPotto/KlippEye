/* ============================================================================
   48b · PRINT QUEUE (1.44, roadmap 6d part 3)
   Moonraker's [job_queue]: files waiting to be printed one after the other.
     · "Add to the queue" in a file's menu (and on the computer's file panel),
       with how many copies;
     · the Queue card on the Files page while something waits: the jobs in
       order with their estimated time, move one up / down or to the front,
       remove one or all; start the queue (the next job prints now) or pause it
       (the jobs wait, the print going on finishes).
   Without [job_queue] in moonraker.conf none of this shows.
   ========================================================================== */

const QUEUE_POLL_MS = 4000;
const QUEUE_COPIES_MAX = 50;

const jobQueueApi = {
  async status() {
    const response = await fetchFresh("/server/job_queue/status");
    if (response.status === 404) return null; // no [job_queue]
    if (!response.ok) throw new Error(await responseError(response));
    return (await response.json()).result || {};
  },
  async post(path, body) {
    const response = await fetchFresh(path, { method: "POST", headers: JSON_HEADERS, body: body ? JSON.stringify(body) : undefined });
    if (!response.ok) throw new Error(await responseError(response));
    return ((await response.json()).result || {});
  },
  /** Adds `count` copies of `path` at the end. */
  add: (path, count = 1) => jobQueueApi.post("/server/job_queue/job", { filenames: Array(Math.max(1, count)).fill(path), reset: false }),
  /** The whole queue in this order (Moonraker has no "move": the list is set again). */
  replace: (filenames) => jobQueueApi.post("/server/job_queue/job", { filenames, reset: true }),
  async remove(ids) {
    const response = await fetchFresh("/server/job_queue/job?job_ids=" + ids.map(encodeURIComponent).join(","), { method: "DELETE" });
    if (!response.ok) throw new Error(await responseError(response));
  },
  async clear() {
    const response = await fetchFresh("/server/job_queue/job?all=true", { method: "DELETE" });
    if (!response.ok) throw new Error(await responseError(response));
  },
  start: () => jobQueueApi.post("/server/job_queue/start"),
  pause: () => jobQueueApi.post("/server/job_queue/pause"),
  jump: (id) => jobQueueApi.post("/server/job_queue/jump?job_id=" + encodeURIComponent(id)),
};

/** One store for the page: { available (null: not asked yet), jobs, state }, read while a part of the page needs it. */
const jobQueueStore = (() => {
  const listeners = new Set();
  let state = { available: null, jobs: [], state: "", error: null };
  let users = 0;
  let stop = null;
  const set = (next) => {
    state = next;
    listeners.forEach((fn) => fn());
  };
  const refresh = async () => {
    try {
      if (!(await moonrakerComponents()).has("job_queue")) return set({ available: false, jobs: [], state: "", error: null });
      const result = await jobQueueApi.status();
      if (result === null) set({ available: false, jobs: [], state: "", error: null });
      else set({ available: true, jobs: Array.isArray(result.queued_jobs) ? result.queued_jobs : [], state: result.queue_state || "", error: null });
    } catch (error) {
      set({ ...state, error: error.message || tx("Error") });
    }
  };
  return {
    subscribe: (fn) => (listeners.add(fn), () => listeners.delete(fn)),
    snapshot: () => state,
    refresh,
    use() {
      users++;
      if (users === 1) stop = startPolling(refresh, QUEUE_POLL_MS);
      return () => {
        users--;
        if (users === 0 && stop) {
          stop();
          stop = null;
        }
      };
    },
  };
})();

function useJobQueue() {
  useEffect(() => jobQueueStore.use(), []);
  return useSyncExternalStore(jobQueueStore.subscribe, jobQueueStore.snapshot);
}

/** Runs a queue action, then reads the queue again; a failure is a toast. */
async function queueAction(run, done) {
  try {
    await run();
    if (done) toast.notice(done);
  } catch (error) {
    toast.action(tx("Queue: ") + (error.message || error));
  }
  jobQueueStore.refresh();
}

/* ---------------------------------------------------------------------------
   Adding a file
   ------------------------------------------------------------------------- */
function QueueAddDialog({ item, onClose }) {
  useBackHandler(onClose, true);
  const queue = useSyncExternalStore(jobQueueStore.subscribe, jobQueueStore.snapshot);
  const [count, setCount] = useState(1);
  const [idle, setIdle] = useState(null); // the printer is free: with the queue ready, the first job starts at once
  useEffect(() => {
    let cancelled = false;
    moonraker
      .queryObjects("print_stats=state")
      .then((status) => !cancelled && setIdle(!["printing", "paused"].includes((status.print_stats || {}).state)))
      .catch(noop);
    return () => {
      cancelled = true;
    };
  }, []);
  const startsNow = idle && queue.state === "ready" && queue.jobs.length === 0;
  const add = () => {
    onClose();
    queueAction(() => jobQueueApi.add(item.file.path, count), count === 1 ? tx("Added to the queue") : tx("{count} copies added to the queue", { count }));
  };
  const clampCount = (value) => Math.max(1, Math.min(QUEUE_COPIES_MAX, value));
  return h(
    "div",
    { className: "confirm-overlay", onClick: (e) => e.target === e.currentTarget && onClose() },
    h(
      "div",
      { className: "confirm-card queue-add", role: "dialog", "aria-label": tx("Add to the queue"), onClick: (e) => e.stopPropagation() },
      h("div", { className: "dialog-head" }, h("div", { className: "dialog-head__icon" }, h(Icons.Queue, { size: 22 })), h("div", null, h("div", { className: "dialog-title" }, tx("Add to the queue")), h("div", { className: "dialog-sub" }, item.fileName))),
      h(
        "div",
        { className: "queue-add__count" },
        h("span", { className: "oui-label" }, tx("Copies")),
        h(
          "div",
          { className: "queue-add__stepper" },
          h("button", { type: "button", className: "oui-btn oui-btn--icon", "aria-label": tx("One less"), disabled: count <= 1, onClick: () => setCount(clampCount(count - 1)) }, "−"),
          h("input", { className: "oui-field queue-add__input", type: "number", inputMode: "numeric", min: 1, max: QUEUE_COPIES_MAX, value: count, "aria-label": tx("Copies"), onChange: (event) => setCount(clampCount(Math.round(Number(event.target.value) || 1))) }),
          h("button", { type: "button", className: "oui-btn oui-btn--icon", "aria-label": tx("One more"), disabled: count >= QUEUE_COPIES_MAX, onClick: () => setCount(clampCount(count + 1)) }, "+"),
        ),
      ),
      h(
        "div",
        { className: "dialog-text" },
        startsNow
          ? tx("The printer is free and the queue is running: the first copy starts printing at once.")
          : queue.jobs.length > 0
            ? tx("It goes after the {count} already waiting.", { count: queue.jobs.length })
            : queue.state === "paused"
              ? tx("The queue is paused: start it from the Queue card.")
              : tx("It prints when the printer is free."),
      ),
      h("div", { className: "oui-btn-row" }, h("button", { className: "oui-btn", onClick: onClose }, tx("Cancel")), h("button", { className: "oui-btn oui-btn--primary queue-add__confirm", onClick: add }, startsNow ? tx("Add and print") : tx("Add"))),
    ),
  );
}

/* ---------------------------------------------------------------------------
   The Queue card
   ------------------------------------------------------------------------- */
/** The metadata of the queued files (time, thumbnail), read once each. */
function useQueuedMeta(paths) {
  const [meta, setMeta] = useState({});
  const asked = useRef({});
  useEffect(() => {
    for (const path of paths) {
      if (asked.current[path]) continue;
      asked.current[path] = true;
      fetchFileMetadata(path).then((result) => result && setMeta((previous) => ({ ...previous, [path]: result })));
    }
  }, [paths.join("\n")]);
  return meta;
}

function QueueRow({ job, index, total, meta, onMove, onFront, onRemove }) {
  const name = String(job.filename || "").split("/").pop();
  const thumbnail = meta ? largestThumbnailUrl(meta) : null;
  return h(
    "div",
    { className: "queue-row", "data-queue-job": job.job_id },
    h("span", { className: "queue-row__pos" }, index + 1),
    h("span", { className: "queue-row__thumb oui-well" }, thumbnail ? h("img", { src: thumbnail, className: "file-thumb", alt: "", draggable: false }) : h(Icons.Doc, { size: 18 })),
    h(
      "span",
      { className: "queue-row__body" },
      h("span", { className: "queue-row__name" }, name),
      h("span", { className: "queue-row__meta" }, meta && meta.estimated_time ? formatEstimatedTime(meta.estimated_time) : "--"),
    ),
    h(
      "span",
      { className: "queue-row__actions" },
      h("button", { type: "button", className: "queue-row__btn", "aria-label": tx("Up"), title: tx("Up"), disabled: index === 0, onClick: () => onMove(index, -1) }, h(Icons.ArrowUp, { size: 16 })),
      h("button", { type: "button", className: "queue-row__btn", "aria-label": tx("Down"), title: tx("Down"), disabled: index === total - 1, onClick: () => onMove(index, 1) }, h(Icons.ArrowDown, { size: 16 })),
      index > 0 && h("button", { type: "button", className: "queue-row__btn", "aria-label": tx("First"), title: tx("Print it next"), onClick: () => onFront(job) }, h(Icons.Rocket, { size: 16 })),
      h("button", { type: "button", className: "queue-row__btn queue-row__btn--danger", "aria-label": tx("Remove from the queue"), title: tx("Remove from the queue"), onClick: () => onRemove(job) }, h(Icons.Trash, { size: 16 })),
    ),
  );
}

/** Shown on the Files page while jobs wait (nothing without [job_queue], nothing with an empty queue). */
function QueueCard() {
  const queue = useJobQueue();
  const [confirmingClear, setConfirmingClear] = useState(false);
  const meta = useQueuedMeta(queue.jobs.map((job) => job.filename));
  if (!queue.available || queue.jobs.length === 0) return null;
  const paused = queue.state === "paused";
  const total = queue.jobs.reduce((sum, job) => sum + ((meta[job.filename] || {}).estimated_time || 0), 0);
  const move = (index, step) => {
    const names = queue.jobs.map((job) => job.filename);
    const [moved] = names.splice(index, 1);
    names.splice(index + step, 0, moved);
    queueAction(() => jobQueueApi.replace(names));
  };
  return h(
    React.Fragment,
    null,
    h(
      Card,
      { className: "queue-card" },
      h(CardHeader, { title: tx("Print queue") }, h("span", { className: "oui-badge" }, queue.jobs.length)),
      h(
        "div",
        { className: cx("queue-state", paused ? "is-paused" : "is-ready") },
        h("span", { className: "queue-state__dot" }),
        h("span", { className: "queue-state__text" }, paused ? tx("Paused: the jobs wait") : queue.state === "loading" || queue.state === "starting" ? tx("Starting the next print…") : tx("Running: the next one starts when the printer is free")),
        total > 0 && h("span", { className: "queue-state__total" }, tx("about {time}", { time: formatEstimatedTime(total) })),
      ),
      h(
        "div",
        { className: "queue-list" },
        queue.jobs.map((job, index) =>
          h(QueueRow, {
            key: job.job_id,
            job,
            index,
            total: queue.jobs.length,
            meta: meta[job.filename],
            onMove: move,
            onFront: (one) => queueAction(() => jobQueueApi.jump(one.job_id)),
            onRemove: (one) => queueAction(() => jobQueueApi.remove([one.job_id]), tx("Removed from the queue")),
          }),
        ),
      ),
      h(
        "div",
        { className: "queue-actions" },
        paused
          ? h("button", { type: "button", className: "oui-btn oui-btn--primary queue-start", onClick: () => queueAction(() => jobQueueApi.start(), tx("Queue started")) }, h(Icons.Play, { size: 16 }), tx("Start the queue"))
          : h("button", { type: "button", className: "oui-btn queue-pause", onClick: () => queueAction(() => jobQueueApi.pause(), tx("Queue paused")) }, h(Icons.Pause, { size: 16 }), tx("Pause the queue")),
        h("button", { type: "button", className: "oui-btn oui-btn--danger-soft queue-clear", onClick: () => setConfirmingClear(true) }, h(Icons.Trash, { size: 16 }), tx("Empty")),
      ),
    ),
    h(ConfirmDialog, {
      open: confirmingClear,
      tone: "danger",
      icon: h(Icons.Trash),
      title: tx("Empty the queue?"),
      subtitle: queue.jobs.length === 1 ? tx("1 job") : tx("{count} jobs", { count: queue.jobs.length }),
      message: tx("The jobs leave the queue; the files stay, and so does a print going on."),
      confirmLabel: tx("Empty"),
      onConfirm: () => {
        setConfirmingClear(false);
        queueAction(() => jobQueueApi.clear(), tx("Queue emptied"));
      },
      onCancel: () => setConfirmingClear(false),
    }),
  );
}
