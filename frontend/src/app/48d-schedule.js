/* ============================================================================
   48d · SCHEDULED PRINTS (1.70)
   «Schedule the print» in a file's menu (and on the computer's file panel): the
   print starts by itself at the chosen day and time. The KlippEye service keeps
   the list and starts it (backend/print_schedule.py), so nothing needs to stay
   open. At its time the printer must be ready and free: when it is printing, or
   Klipper is off for more than ten minutes, the print is not started later on its
   own (the bed may not be clear) and the card says it was missed, and why.
   The card «Scheduled prints» on the Files page lists them while there are some.
   ========================================================================== */

const SCHEDULE_POLL_MS = 20000;

const scheduleApi = {
  async list() {
    const json = await fetchJson("/api/schedule");
    if (!json || json.ok === false) throw new Error((json && json.error) || tx("Error"));
    return { entries: Array.isArray(json.entries) ? json.entries : [], now: Number(json.now) || Date.now() / 1000 };
  },
  async add(filename, at) {
    const response = await fetchFresh("/api/schedule", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ filename, at }) });
    const json = await response.json().catch(() => ({}));
    if (!response.ok || !json.ok) throw new Error(json.error || (await responseError(response)));
    return json.entry;
  },
  async remove(id) {
    const response = await fetchFresh("/api/schedule/" + encodeURIComponent(id), { method: "DELETE" });
    if (!response.ok) throw new Error(await responseError(response));
  },
};

/** One store for the page: { loaded, entries, error }, read every few seconds while a part of the page shows it. */
const scheduleStore = (() => {
  const listeners = new Set();
  let state = { loaded: false, entries: [], error: null };
  let users = 0;
  let stop = null;
  const set = (next) => {
    // a print that was waiting and now is missed: said once, on the devices that are open
    if (state.loaded)
      for (const entry of next.entries) {
        const before = state.entries.find((old) => old.id === entry.id);
        if (before && before.status === "waiting" && entry.status === "missed") toast.action(tx("Scheduled print not started: {name}", { name: scheduleFileName(entry) }) + " · " + scheduleReason(entry));
      }
    state = next;
    listeners.forEach((fn) => fn());
  };
  const refresh = async () => {
    try {
      const { entries } = await scheduleApi.list();
      set({ loaded: true, entries, error: null });
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
      if (users === 1) stop = startPolling(refresh, SCHEDULE_POLL_MS);
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

function useSchedule() {
  useEffect(() => scheduleStore.use(), []);
  return useSyncExternalStore(scheduleStore.subscribe, scheduleStore.snapshot);
}

const scheduleFileName = (entry) => String(entry.filename || "").split("/").pop();

function scheduleReason(entry) {
  if (entry.reason === "busy") return tx("the printer was busy with another print");
  if (entry.reason === "not_ready") return tx("Klipper was not ready");
  return entry.detail || tx("Moonraker refused it");
}

/** «Tomorrow 07:00», «Today 23:00», «Tue 10 Nov 07:00». */
function formatScheduleTime(seconds) {
  const date = new Date(seconds * 1000);
  const time = date.toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" });
  const today = new Date();
  const days = Math.round((new Date(date.getFullYear(), date.getMonth(), date.getDate()) - new Date(today.getFullYear(), today.getMonth(), today.getDate())) / 86400000);
  if (days === 0) return tx("Today at {time}", { time });
  if (days === 1) return tx("Tomorrow at {time}", { time });
  return date.toLocaleDateString(LOCALE, { weekday: "short", day: "numeric", month: "short" }) + " · " + time;
}

/** How long until then: «in 2 h 15 min». */
function formatScheduleIn(seconds) {
  const left = Math.max(0, Math.round(seconds - Date.now() / 1000));
  if (left < 60) return tx("in less than a minute");
  return tx("in {time}", { time: formatEstimatedTime(left) });
}

const pad2 = (n) => String(n).padStart(2, "0");
const toDateInput = (date) => date.getFullYear() + "-" + pad2(date.getMonth() + 1) + "-" + pad2(date.getDate());
const toTimeInput = (date) => pad2(date.getHours()) + ":" + pad2(date.getMinutes());

/** The quick choices: in an hour, tonight, tomorrow morning. */
function scheduleQuickChoices() {
  const now = new Date();
  const inHour = new Date(now.getTime() + 3600 * 1000);
  inHour.setSeconds(0, 0);
  const tonight = new Date(now);
  tonight.setHours(23, 0, 0, 0);
  const morning = new Date(now);
  morning.setDate(morning.getDate() + 1);
  morning.setHours(7, 0, 0, 0);
  const choices = [{ id: "hour", label: tx("In an hour"), date: inHour }];
  if (tonight > inHour) choices.push({ id: "tonight", label: tx("Tonight 23:00"), date: tonight });
  choices.push({ id: "morning", label: tx("Tomorrow 07:00"), date: morning });
  return choices;
}

/** «Schedule the print»: a day and a time, a word about the bed, «Schedule». */
function ScheduleDialog({ item, onClose }) {
  useBackHandler(onClose, true);
  const start = scheduleQuickChoices()[0].date;
  const [day, setDay] = useState(toDateInput(start));
  const [time, setTime] = useState(toTimeInput(start));
  const [saving, setSaving] = useState(false);
  const chosen = new Date(day + "T" + (time || "00:00"));
  const at = Math.round(chosen.getTime() / 1000);
  const valid = isFinite(at) && at > Date.now() / 1000;
  const pick = (date) => {
    setDay(toDateInput(date));
    setTime(toTimeInput(date));
  };
  const save = async () => {
    if (!valid || saving) return;
    setSaving(true);
    try {
      await scheduleApi.add(item.file.path, at);
      toast.notice(tx("Scheduled: {name}, {when}", { name: item.fileName, when: formatScheduleTime(at) }));
      onClose();
    } catch (error) {
      toast.action(tx("Cannot schedule it: {reason}", { reason: error.message || error }));
    } finally {
      setSaving(false);
      scheduleStore.refresh();
    }
  };
  return h(
    "div",
    { className: "confirm-overlay", onClick: (e) => e.target === e.currentTarget && onClose() },
    h(
      "div",
      { className: "confirm-card schedule-add", role: "dialog", "aria-label": tx("Schedule the print"), onClick: (e) => e.stopPropagation() },
      h("div", { className: "dialog-head" }, h("div", { className: "dialog-head__icon" }, h(Icons.Clock, { size: 22 })), h("div", null, h("div", { className: "dialog-title" }, tx("Schedule the print")), h("div", { className: "dialog-sub" }, item.fileName))),
      h(
        "div",
        { className: "set-chips schedule-add__quick", role: "group", "aria-label": tx("Quick choices") },
        scheduleQuickChoices().map((choice) => h("button", { key: choice.id, type: "button", className: cx("oui-chip", Math.abs(choice.date.getTime() / 1000 - at) < 30 && "is-selected"), "data-schedule-quick": choice.id, onClick: () => pick(choice.date) }, choice.label)),
      ),
      h(
        "div",
        { className: "schedule-add__fields" },
        h("label", { className: "set-field" }, h("span", { className: "set-field__label" }, tx("Day")), h("input", { type: "date", className: "oui-field set-field__input", value: day, min: toDateInput(new Date()), "data-schedule-day": "1", onChange: (event) => setDay(event.target.value) })),
        h("label", { className: "set-field" }, h("span", { className: "set-field__label" }, txc("clock", "Time")), h("input", { type: "time", className: "oui-field set-field__input", value: time, "data-schedule-time": "1", onChange: (event) => setTime(event.target.value) })),
      ),
      h("div", { className: cx("schedule-add__when", !valid && "is-invalid"), "data-schedule-when": valid ? at : "" }, valid ? formatScheduleTime(at) + " · " + formatScheduleIn(at) : tx("Choose a time still to come")),
      h("div", { className: "dialog-text" }, tx("The KlippEye service starts it by itself, with nothing open. Leave the bed clear: at that time the printer must be ready and free, or the print is not started.")),
      h("div", { className: "oui-btn-row" }, h("button", { className: "oui-btn", onClick: onClose }, tx("Cancel")), h("button", { className: "oui-btn oui-btn--primary schedule-add__confirm", disabled: !valid || saving, onClick: save }, tx("Schedule"))),
    ),
  );
}

function ScheduleRow({ entry, onRemove }) {
  const waiting = entry.status === "waiting";
  const badge = waiting
    ? h("span", { className: "oui-badge oui-badge--info" }, formatScheduleIn(entry.at))
    : entry.status === "started"
      ? h("span", { className: "oui-badge oui-badge--ok" }, tx("Started"))
      : h("span", { className: "oui-badge oui-badge--warn" }, tx("Not started"));
  return h(
    "div",
    { className: cx("schedule-row", "is-" + entry.status), "data-schedule": entry.id, "data-status": entry.status },
    h("span", { className: "schedule-row__icon" }, h(Icons.Clock, { size: 18 })),
    h(
      "span",
      { className: "schedule-row__body" },
      h("span", { className: "schedule-row__name" }, scheduleFileName(entry)),
      h("span", { className: "schedule-row__meta" }, formatScheduleTime(entry.at), entry.status === "missed" && h("span", { className: "schedule-row__why" }, " · " + scheduleReason(entry))),
    ),
    badge,
    h("button", { type: "button", className: "queue-row__btn queue-row__btn--danger", "aria-label": waiting ? tx("Cancel the scheduled print") : tx("Remove from the list"), title: waiting ? tx("Cancel the scheduled print") : tx("Remove from the list"), onClick: () => onRemove(entry) }, h(waiting ? Icons.Trash : Icons.Close, { size: 16 })),
  );
}

/** On the Files page while there are scheduled prints (waiting, or done in the last day). */
function ScheduleCard() {
  const schedule = useSchedule();
  if (!schedule.entries.length) return null;
  const remove = async (entry) => {
    try {
      await scheduleApi.remove(entry.id);
      if (entry.status === "waiting") toast.notice(tx("Scheduled print cancelled: {name}", { name: scheduleFileName(entry) }));
    } catch (error) {
      toast.action(error.message || String(error));
    }
    scheduleStore.refresh();
  };
  const waiting = schedule.entries.filter((entry) => entry.status === "waiting").length;
  return h(
    Card,
    { className: "schedule-card" },
    h(CardHeader, { title: tx("Scheduled prints") }, waiting > 0 && h("span", { className: "oui-badge" }, waiting)),
    h("div", { className: "schedule-list" }, schedule.entries.map((entry) => h(ScheduleRow, { key: entry.id, entry, onRemove: remove }))),
  );
}

/** For the idle print card: the next print that starts by itself, or null. */
function useNextScheduled() {
  const schedule = useSchedule();
  return schedule.entries.find((entry) => entry.status === "waiting") || null;
}
