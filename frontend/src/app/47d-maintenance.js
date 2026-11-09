/* ============================================================================
   47d · MAINTENANCE REMINDERS (1.73)
   «Grease the rails every 200 printing hours», «check the belts every 3 months»,
   «change the nozzle every 2 km of filament»: each reminder has its intervals
   (printing hours, metres of filament, days: one or more) and counts from the
   last time it was done, with Moonraker's own totals (/server/history/totals:
   every print ever, also those removed from the list).
   The reminders are kept in Moonraker's database (the dashboard's namespace),
   so every phone and computer sees the same ones. They are on the Files page,
   under «History»; when one is due, a message says so once a day on each device.
   «Done» starts it again from now.
   ========================================================================== */

const MAINTENANCE_KEY = "maintenance"; // [{ id, name, note, every: { hours, metres, days }, last: { at, printTime, filament } }]
const MAINTENANCE_SOON = 0.9; // from this share of the interval it says «soon»
const MAINTENANCE_WATCH_MS = 30 * 60 * 1000;
const MAINTENANCE_ANNOUNCED_KEY = "klippeye.maintenance.announced"; // the day the message was last shown on this device
const MAINTENANCE_NAME_MAX = 60;
const MAINTENANCE_NOTE_MAX = 300;

function cleanMaintenanceItem(item) {
  if (!isPlainObject(item) || !item.id) return null;
  const every = isPlainObject(item.every) ? item.every : {};
  const last = isPlainObject(item.last) ? item.last : {};
  const positive = (value) => (Number(value) > 0 ? Number(value) : 0);
  return {
    id: String(item.id),
    name: String(item.name || "").slice(0, MAINTENANCE_NAME_MAX) || "?",
    note: String(item.note || "").slice(0, MAINTENANCE_NOTE_MAX),
    every: { hours: positive(every.hours), metres: positive(every.metres), days: positive(every.days) },
    last: { at: positive(last.at), printTime: positive(last.printTime), filament: positive(last.filament) },
  };
}

/** The reminders as Moonraker keeps them now. */
async function readMaintenance() {
  const stored = await readSettingsDb(MAINTENANCE_KEY);
  if (!stored.ok) throw new Error(stored.detail);
  return (Array.isArray(stored.value) ? stored.value : []).map(cleanMaintenanceItem).filter(Boolean);
}

/** Changes the list as it is now on the Raspberry (another device may have changed it) and saves it. */
async function changeMaintenance(change) {
  const next = change(await readMaintenance());
  const written = await writeSettingsDb(MAINTENANCE_KEY, next);
  if (!written.ok) throw new Error(written.detail);
  return next;
}

/** Where the counters are now: { at, printTime (s), filament (mm) }. */
function maintenanceNow(totals) {
  return { at: Math.round(Date.now() / 1000), printTime: Number((totals || {}).total_print_time) || 0, filament: Number((totals || {}).total_filament_used) || 0 };
}

/**
 * How far a reminder has gone: { parts: [{ kind, used, limit, share }], share (the largest), state: ok | soon | due }.
 * Counters lower than when it was done mean Moonraker's totals were reset: what was counted since then is used.
 */
function maintenanceProgress(item, totals) {
  const now = maintenanceNow(totals);
  const since = (current, then) => (current >= then ? current - then : current);
  const parts = [];
  if (item.every.hours) parts.push({ kind: "hours", used: since(now.printTime, item.last.printTime) / 3600, limit: item.every.hours });
  if (item.every.metres) parts.push({ kind: "metres", used: since(now.filament, item.last.filament) / 1000, limit: item.every.metres });
  if (item.every.days) parts.push({ kind: "days", used: Math.max(0, now.at - item.last.at) / 86400, limit: item.every.days });
  parts.forEach((part) => (part.share = part.limit ? part.used / part.limit : 0));
  const share = parts.reduce((max, part) => Math.max(max, part.share), 0);
  return { parts, share, state: share >= 1 ? "due" : share >= MAINTENANCE_SOON ? "soon" : "ok" };
}

function maintenancePartText(part) {
  const round = (value) => (value >= 100 ? Math.round(value) : Math.round(value * 10) / 10).toLocaleString(LOCALE);
  if (part.kind === "hours") return tx("{used} of {limit} printing hours", { used: round(part.used), limit: round(part.limit) });
  if (part.kind === "metres") return tx("{used} of {limit} m of filament", { used: round(part.used), limit: round(part.limit) });
  return tx("{used} of {limit} days", { used: Math.floor(part.used), limit: round(part.limit) });
}

/** The reminders and the totals: { loaded, items, totals, error, reload, save(item), remove(id), done(id) }. */
function useMaintenance(active = true) {
  const [state, setState] = useState({ loaded: false, items: [], totals: null, error: null });
  const reload = async () => {
    try {
      const [items, totals] = await Promise.all([readMaintenance(), historyApi.totals().catch(() => null)]);
      setState({ loaded: true, items, totals, error: null });
    } catch (error) {
      setState((previous) => ({ ...previous, loaded: true, error: error.message || tx("Error") }));
    }
  };
  useEffect(() => {
    if (!active) return undefined;
    return startPolling(reload, HISTORY_POLL_MS);
  }, [active]);
  const apply = async (change) => {
    const items = await changeMaintenance(change);
    setState((previous) => ({ ...previous, items }));
  };
  return {
    ...state,
    reload,
    save: (item) => apply((items) => (items.some((one) => one.id === item.id) ? items.map((one) => (one.id === item.id ? item : one)) : items.concat(item))),
    remove: (id) => apply((items) => items.filter((one) => one.id !== id)),
    done: async (id) => {
      const totals = await historyApi.totals();
      setState((previous) => ({ ...previous, totals }));
      await apply((items) => items.map((one) => (one.id === id ? { ...one, last: maintenanceNow(totals) } : one)));
    },
  };
}

/** Mounted once by the application: a message when a reminder is due, once a day on this device. */
function useMaintenanceWatch() {
  useEffect(() => {
    const look = async () => {
      const today = new Date().toDateString();
      let announced = "";
      try {
        announced = localStorage.getItem(MAINTENANCE_ANNOUNCED_KEY) || "";
      } catch (e) {}
      if (announced === today) return;
      try {
        const [items, totals] = await Promise.all([readMaintenance(), historyApi.totals()]);
        const due = items.filter((item) => maintenanceProgress(item, totals).state === "due");
        if (!due.length) return;
        try {
          localStorage.setItem(MAINTENANCE_ANNOUNCED_KEY, today);
        } catch (e) {}
        toast.notice(tx("Maintenance due: {names}. See Files → History.", { names: due.map((item) => item.name).join(", ") }), 8000);
      } catch (error) {}
    };
    return startPolling(look, MAINTENANCE_WATCH_MS);
  }, []);
}

/** Add or change a reminder. */
function MaintenanceDialog({ item, onSave, onRemove, onClose }) {
  useBackHandler(onClose, true);
  const [name, setName] = useState(item ? item.name : "");
  const [note, setNote] = useState(item ? item.note : "");
  const [every, setEvery] = useState(() => ({ hours: item && item.every.hours ? String(item.every.hours) : "", metres: item && item.every.metres ? String(item.every.metres) : "", days: item && item.every.days ? String(item.every.days) : "" }));
  const [busy, setBusy] = useState(false);
  const numbers = { hours: Number(every.hours) || 0, metres: Number(every.metres) || 0, days: Number(every.days) || 0 };
  const valid = name.trim() && (numbers.hours > 0 || numbers.metres > 0 || numbers.days > 0) && Object.values(numbers).every((n) => n >= 0);
  const save = async () => {
    if (!valid || busy) return;
    setBusy(true);
    try {
      const totals = item ? null : await historyApi.totals().catch(() => null);
      await onSave({
        id: item ? item.id : Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
        name: name.trim().slice(0, MAINTENANCE_NAME_MAX),
        note: note.trim().slice(0, MAINTENANCE_NOTE_MAX),
        every: numbers,
        last: item ? item.last : maintenanceNow(totals),
      });
      onClose();
    } catch (error) {
      toast.action(tx("Error: ") + (error.message || error));
      setBusy(false);
    }
  };
  const field = (key, label, unit) =>
    h(
      "label",
      { className: "set-field maintenance-every" },
      h("span", { className: "set-field__label" }, label),
      h("input", { type: "number", inputMode: "decimal", min: 0, step: "any", className: "oui-field set-field__input", "data-every": key, "aria-label": label + " (" + unit + ")", value: every[key], placeholder: unit, onChange: (event) => setEvery({ ...every, [key]: event.target.value }) }),
    );
  return h(
    "div",
    { className: "confirm-overlay", onClick: (event) => event.target === event.currentTarget && onClose() },
    h(
      "div",
      { className: "confirm-card maintenance-dialog", role: "dialog", "aria-label": item ? tx("Change the reminder") : tx("New reminder") },
      h("div", { className: "dialog-head" }, h("div", { className: "dialog-head__icon" }, h(Icons.Screw, { size: 22 })), h("div", null, h("div", { className: "dialog-title" }, item ? tx("Change the reminder") : tx("New reminder")), h("div", { className: "dialog-sub" }, tx("Maintenance")))),
      h("label", { className: "set-field" }, h("span", { className: "set-field__label" }, tx("What to do")), h("input", { className: "oui-field set-field__input", "data-maintenance-name": "1", value: name, maxLength: MAINTENANCE_NAME_MAX, placeholder: tx("e.g. Grease the rails"), onChange: (event) => setName(event.target.value) })),
      h("div", { className: "maintenance-dialog__every-title" }, tx("Every (one or more)")),
      h("div", { className: "maintenance-dialog__every" }, field("hours", tx("Printing hours"), "h"), field("metres", tx("Filament"), "m"), field("days", tx("Days"), tx("days"))),
      h("label", { className: "set-field" }, h("span", { className: "set-field__label" }, tx("Note")), h("textarea", { className: "oui-field set-field__input", rows: 2, maxLength: MAINTENANCE_NOTE_MAX, value: note, placeholder: tx("e.g. which grease, where the manual is…"), onChange: (event) => setNote(event.target.value) })),
      !item && h("div", { className: "dialog-text" }, tx("It starts counting now.")),
      h(
        "div",
        { className: "oui-btn-row" },
        item && h("button", { type: "button", className: "oui-btn oui-btn--danger", onClick: async () => (await onRemove(item.id), onClose()) }, tx("Remove")),
        h("button", { type: "button", className: "oui-btn", onClick: onClose }, tx("Cancel")),
        h("button", { type: "button", className: "oui-btn oui-btn--primary maintenance-dialog__save", disabled: !valid || busy, onClick: save }, tx("Save")),
      ),
    ),
  );
}

function MaintenanceRow({ item, totals, onDone, onEdit }) {
  const progress = maintenanceProgress(item, totals);
  const badge = { due: ["oui-badge--danger", tx("To do")], soon: ["oui-badge--warn", tx("Soon")], ok: ["oui-badge--ok", tx("OK")] }[progress.state];
  return h(
    "div",
    { className: cx("maintenance-row", "is-" + progress.state), "data-maintenance": item.id, "data-state": progress.state },
    h(
      "button",
      { type: "button", className: "maintenance-row__main", onClick: () => onEdit(item), title: tx("Change") },
      h("span", { className: "maintenance-row__head" }, h("span", { className: "maintenance-row__name" }, item.name), h("span", { className: cx("oui-badge", badge[0]) }, badge[1])),
      h("span", { className: "maintenance-row__bar", role: "progressbar", "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": Math.round(Math.min(1, progress.share) * 100) }, h("span", { style: { width: Math.min(100, progress.share * 100) + "%" } })),
      h("span", { className: "maintenance-row__meta" }, progress.parts.map(maintenancePartText).join(" · ")),
      item.note && h("span", { className: "maintenance-row__note" }, item.note),
    ),
    h("button", { type: "button", className: "oui-btn oui-btn--sm maintenance-row__done", onClick: () => onDone(item) }, h(Icons.Check, { size: 16 }), tx("Done")),
  );
}

/** On the History page: the reminders, «Add», «Done». */
function MaintenanceCard() {
  const maintenance = useMaintenance(true);
  const [editing, setEditing] = useState(null); // null | "new" | item
  const done = async (item) => {
    try {
      await maintenance.done(item.id);
      toast.notice(tx("Done: {name}. It starts counting again.", { name: item.name }));
    } catch (error) {
      toast.action(tx("Error: ") + (error.message || error));
    }
  };
  const order = { due: 0, soon: 1, ok: 2 };
  const items = maintenance.items.slice().sort((a, b) => order[maintenanceProgress(a, maintenance.totals).state] - order[maintenanceProgress(b, maintenance.totals).state] || maintenanceProgress(b, maintenance.totals).share - maintenanceProgress(a, maintenance.totals).share);
  return h(
    Card,
    { className: "maintenance-card", cardId: "maintenance" },
    h(CardHeader, { title: tx("Maintenance") }, h("button", { type: "button", className: "oui-btn oui-btn--sm", "data-maintenance-add": "1", onClick: () => setEditing("new") }, h(Icons.Plus, { size: 16 }), tx("Add"))),
    maintenance.error && h("div", { className: "set-group__note set-group__note--warn" }, maintenance.error),
    maintenance.loaded && !items.length && !maintenance.error && h("div", { className: "oui-caption maintenance-empty" }, tx("No reminders yet: «Add» one, for example greasing the rails every 200 printing hours.")),
    h("div", { className: "maintenance-list" }, items.map((item) => h(MaintenanceRow, { key: item.id, item, totals: maintenance.totals, onDone: done, onEdit: setEditing }))),
    // on the page's body: inside the card (glass) the dialog would be drawn in it
    createPortal(h(Presence, null, editing && h(MaintenanceDialog, { item: editing === "new" ? null : editing, onSave: maintenance.save, onRemove: maintenance.remove, onClose: () => setEditing(null) })), document.body),
  );
}
