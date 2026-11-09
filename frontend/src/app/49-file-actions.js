/* ============================================================================
   49 · FILE ACTIONS
   Long press (finger or mouse) or right click on a G-code file opens a menu:
     · open it in the text editor (51), to read and change it; only a huge file
       (over 32 MB) opens read-only, just its first lines;
     · delete it, from the Raspberry's disk too (after a confirmation).
   ========================================================================== */

const FILE_PRESS_MS = 500;
const FILE_PRESS_SLOP_PX = 10; // a finger that moves further than this is scrolling, not pressing
const FILE_MENU_GUARD_MS = 450; // after the menu appears, clicks are ignored: lifting the finger must not pick a row
// 1.58: G-code files open editable up to 32 MB (CodeMirror draws only what is on screen; before, 256 KB): almost every
// print. Beyond it only the start is shown, read-only, so a phone is never asked to hold a huge file.
const GCODE_EDIT_MAX_BYTES = 32 * 1024 * 1024;
const GCODE_PREVIEW_BYTES = 512 * 1024;

/* ---------------------------------------------------------------------------
   Long press: spread the returned handlers on any element.
   ------------------------------------------------------------------------- */
function useLongPress(onLongPress) {
  const timer = useRef(null);
  const origin = useRef(null);
  const swallowClick = useRef(false);
  const lastFire = useRef(0);
  const callback = useRef(onLongPress);
  callback.current = onLongPress;

  useEffect(() => () => clearTimeout(timer.current), []);

  const cancel = () => {
    clearTimeout(timer.current);
    timer.current = null;
  };
  const fire = () => {
    cancel();
    swallowClick.current = true; // lifting the finger must not also press the button under it
    lastFire.current = Date.now();
    try {
      if (navigator.vibrate) navigator.vibrate(12);
    } catch (e) {}
    callback.current();
  };

  return {
    onPointerDown: (event) => {
      if (event.pointerType === "mouse" && event.button !== 0) return;
      swallowClick.current = false;
      origin.current = { x: event.clientX, y: event.clientY };
      cancel();
      timer.current = setTimeout(fire, FILE_PRESS_MS);
    },
    onPointerMove: (event) => {
      if (timer.current && origin.current && Math.hypot(event.clientX - origin.current.x, event.clientY - origin.current.y) > FILE_PRESS_SLOP_PX) cancel();
    },
    onPointerUp: cancel,
    onPointerCancel: cancel,
    onPointerLeave: cancel,
    // Right click, the keyboard's menu key, and the long press itself on Android: no native menu, ours instead.
    onContextMenu: (event) => {
      event.preventDefault();
      if (Date.now() - lastFire.current > 800) fire(); // Android sends this event right after our own timer fired
    },
    onClickCapture: (event) => {
      if (!swallowClick.current) return;
      swallowClick.current = false;
      event.preventDefault();
      event.stopPropagation();
    },
  };
}

/* ---------------------------------------------------------------------------
   State: which file's menu is open, which one waits for the delete confirmation
   ------------------------------------------------------------------------- */

/** `list` is the file list (useFileList); `openEditor(path, content, options)` shows the text editor. */
function useFileActions(list, openEditor) {
  const [target, setTarget] = useState(null); // { file, fileName, meta, thumbnail } while its menu is open
  const [pendingDelete, setPendingDelete] = useState(null);
  const [details, setDetails] = useState(null); // the item whose details are open (1.40)
  const [queueItem, setQueueItem] = useState(null); // the item being added to the print queue (1.44)
  const [scheduleItem, setScheduleItem] = useState(null); // the item whose print is being scheduled (1.70)
  const deleting = useRef(false);

  const closeMenu = () => setTarget(null);

  /** Opens `item` ({ file, fileName }) in the editor; the menu and the wide screen's detail panel both start here. */
  const openItemInEditor = async (item) => {
    const { file, fileName } = item;
    const size = file.size || 0;
    const tooLong = size > GCODE_EDIT_MAX_BYTES;
    setTarget(null);
    toast.notice(tx("Opening ") + fileName + "...", 1500);
    try {
      const { text, truncated } = await gcodeFilesApi.read(file.path, tooLong ? GCODE_PREVIEW_BYTES : 0);
      const readOnly = tooLong || truncated;
      const note = readOnly ? tx("Read-only • first ") + text.split("\n").length.toLocaleString(LOCALE) + tx(" lines of a file of ") + (formatBytes(size) || "?") : "";
      openEditor(file.path, text, { root: GCODES_ROOT, readOnly, note });
    } catch (error) {
      toast.action(tx("Error opening ") + fileName + ": " + (error.message || ""));
    }
  };

  const openInEditor = () => openItemInEditor(target);

  const askDeleteItem = (item) => {
    setPendingDelete(item);
    setTarget(null);
  };
  const askDelete = () => askDeleteItem(target);
  const cancelDelete = () => {
    if (!deleting.current) setPendingDelete(null);
  };
  const confirmDelete = async () => {
    if (deleting.current || !pendingDelete) return;
    deleting.current = true;
    const { file, fileName } = pendingDelete;
    try {
      await gcodeFilesApi.remove(file.path);
      list.forget(file.path);
      toast.notice(tx("Deleted: ") + fileName);
    } catch (error) {
      const message = error.message || tx("error");
      toast.action(tx("Delete failed: ") + (/print|load|busy|in use/i.test(message) ? tx("the file is in use, stop the print first") : message));
    }
    deleting.current = false;
    setPendingDelete(null);
    list.reload();
  };

  const openDetailsItem = (item) => {
    setTarget(null);
    setDetails(item);
  };
  return {
    target,
    pendingDelete,
    details,
    openMenu: setTarget,
    closeMenu,
    openInEditor,
    openItemInEditor,
    askDelete,
    askDeleteItem,
    cancelDelete,
    confirmDelete,
    openDetails: () => openDetailsItem(target),
    openDetailsItem,
    closeDetails: () => setDetails(null),
    queueItem,
    openQueueItem: (item) => {
      setTarget(null);
      setQueueItem(item);
    },
    closeQueue: () => setQueueItem(null),
    scheduleItem,
    openScheduleItem: (item) => {
      setTarget(null);
      setScheduleItem(item);
    },
    closeSchedule: () => setScheduleItem(null),
  };
}

/* ---------------------------------------------------------------------------
   UI
   ------------------------------------------------------------------------- */
function FileActionRow({ icon, title, subtitle, danger, disabled, onClick }) {
  return h(
    "button",
    { className: cx("file-action", danger && "file-action--danger"), disabled, onClick },
    h("span", { className: "file-action__icon" }, icon),
    h("span", { className: "file-action__text" }, h("span", { className: "file-action__title" }, title), h("span", { className: "file-action__sub" }, subtitle)),
  );
}

/** For a menu opened by a long press: the click that follows the finger lifting is not a choice. Use as onClickCapture. */
function useEarlyClickGuard() {
  const openedAt = useRef(Date.now());
  return (event) => {
    if (Date.now() - openedAt.current < FILE_MENU_GUARD_MS) {
      event.preventDefault();
      event.stopPropagation();
    }
  };
}

function FileActionSheet({ item, controller }) {
  useBodyScrollLock(true);
  const ignoreEarlyClick = useEarlyClickGuard();
  const { file, fileName, thumbnail } = item;
  const queue = useJobQueue();
  const tooLong = (file.size || 0) > GCODE_EDIT_MAX_BYTES;
  const details = [formatBytes(file.size), formatFileDate(file.modified)].filter(Boolean).join(" • ");
  return h(
    "div",
    { className: "sheet-overlay sheet-overlay--actions", onClickCapture: ignoreEarlyClick, onClick: (e) => e.target === e.currentTarget && controller.closeMenu() },
    h(
      "div",
      { className: "sheet-card" },
      h(
        "div",
        { className: "file-sheet__head" },
        h("div", { className: "file-sheet__thumb oui-well" }, thumbnail ? h("img", { src: thumbnail, className: "file-thumb", draggable: false }) : h(PrintPlaceholder)),
        h("div", { className: "file-sheet__info" }, h("div", { className: "file-sheet__name" }, fileName), details && h("div", { className: "oui-caption oui-num" }, details)),
      ),
      h(
        "div",
        { className: "oui-list file-sheet__actions" },
        h(FileActionRow, { icon: h(Icons.Info), title: tx("Details"), subtitle: tx("Slicer, times, filament, temperatures, last print"), onClick: controller.openDetails }),
        queue.available && h(FileActionRow, { icon: h(Icons.Queue), title: tx("Add to the queue"), subtitle: tx("Prints after the jobs already waiting; as many copies as you like"), onClick: () => controller.openQueueItem(item) }),
        h(FileActionRow, { icon: h(Icons.Clock), title: tx("Schedule the print"), subtitle: tx("It starts by itself at the day and time you choose"), onClick: () => controller.openScheduleItem(item) }),
        h(FileActionRow, { icon: h(Icons.Layers), title: tx("See the layers"), subtitle: tx("The G-code drawn layer by layer"), onClick: () => (controller.closeMenu(), gcodeViewerStore.open(file.path)) }),
        h(FileActionRow, { icon: h(Icons.Code), title: tx("Open in the editor"), subtitle: tooLong ? tx("Huge file: read-only, first lines") : tx("Read and edit the G-code"), onClick: controller.openInEditor }),
        h(FileActionRow, { icon: h(Icons.Trash), title: tx("Delete from the Raspberry"), subtitle: tx("Deletes the file for good"), danger: true, onClick: controller.askDelete }),
      ),
      h("div", { className: "sheet-footer" }, h("button", { className: "oui-btn", onClick: controller.closeMenu }, tx("Cancel"))),
    ),
  );
}

/* ---------------------------------------------------------------------------
   Details (1.40): what Mainsail shows of a file, read from Moonraker's metadata
   ------------------------------------------------------------------------- */
const metaNumber = (value) => (typeof value === "number" && isFinite(value) && value > 0 ? value : null);
const mm = (value, digits = 2) => (metaNumber(value) !== null ? Number(value.toFixed(digits)) + " mm" : null);
const celsius = (value) => (metaNumber(value) !== null ? Math.round(value) + " °C" : null);

/** The rows of the details: [label, value] (only what the file says). */
function fileDetailRows(file, meta) {
  const folder = file.path.includes("/") ? file.path.split("/").slice(0, -1).join("/") : "";
  const length = metaNumber(meta.filament_total);
  const weight = metaNumber(meta.filament_weight_total);
  const printed = metaNumber(meta.print_start_time);
  return [
    [tx("Folder"), folder ? "/" + folder : null],
    [tx("Size"), formatBytes(file.size) || null],
    [tx("Last change"), formatFileDate(file.modified) || null],
    [tx("Last printed"), printed ? formatFileDate(printed) : tx("Never")],
    [tx("Slicer"), [meta.slicer, meta.slicer_version].filter(Boolean).join(" ") || null],
    [tx("Estimated time"), metaNumber(meta.estimated_time) !== null ? formatDuration(meta.estimated_time) : null],
    [tx("Layer height"), mm(meta.layer_height, 3)],
    [tx("First layer height"), mm(meta.first_layer_height, 3)],
    [tx("Object height"), mm(meta.object_height, 1)],
    [tx("Layers"), metaNumber(meta.layer_count) !== null ? String(meta.layer_count) : null],
    [tx("Filament"), [meta.filament_type, meta.filament_name].filter(Boolean).join(" · ") || null],
    [tx("Filament length"), length !== null ? (length / 1000).toFixed(2) + " m" : null],
    [tx("Filament weight"), weight !== null ? Math.round(weight * 10) / 10 + " g" : null],
    [tx("Nozzle"), mm(meta.nozzle_diameter, 2)],
    [tx("First layer: nozzle"), celsius(meta.first_layer_extr_temp)],
    [tx("First layer: bed"), celsius(meta.first_layer_bed_temp)],
    [tx("Chamber"), celsius(meta.chamber_temp)],
  ].filter(([, value]) => value);
}

function FileDetailsSheet({ item, controller, onPrint }) {
  useBodyScrollLock(true);
  useBackHandler(controller.closeDetails, true);
  const { file, fileName } = item;
  const [meta, setMeta] = useState(item.meta && Object.keys(item.meta).length ? item.meta : null);
  useEffect(() => {
    let cancelled = false;
    fetchFresh("/server/files/metadata?filename=" + encodeURIComponent(file.path))
      .then((response) => (response.ok ? response.json() : null))
      .then((json) => !cancelled && json && json.result && setMeta(json.result))
      .catch(noop);
    return () => {
      cancelled = true;
    };
  }, [file.path]);
  const thumbnail = item.thumbnail || (meta ? largestThumbnailUrl(meta) : null);
  const rows = fileDetailRows(file, meta || {});
  return h(
    "div",
    { className: "sheet-overlay sheet-overlay--details", onClick: (e) => e.target === e.currentTarget && controller.closeDetails() },
    h(
      "div",
      { className: "sheet-card sheet-card--column file-details", role: "dialog", "aria-label": tx("Details") },
      h("div", { className: "sheet-header sheet-header--bar" }, h("div", { className: "dialog-title file-details__title" }, fileName), h("button", { className: "dialog-close", onClick: controller.closeDetails, "aria-label": tx("Close") }, "✕")),
      h(
        "div",
        { className: "file-details__body" },
        h("div", { className: "file-details__thumb oui-well" }, thumbnail ? h("img", { src: thumbnail, className: "file-thumb", draggable: false }) : h(PrintPlaceholder)),
        !meta && h("div", { className: "oui-caption" }, tx("Loading...")),
        h(
          "dl",
          { className: "file-details__list" },
          rows.map(([label, value]) => h(React.Fragment, { key: label }, h("dt", null, label), h("dd", { "data-detail": label }, value))),
        ),
      ),
      h(
        "div",
        { className: "sheet-footer" },
        h("button", { className: "oui-btn", onClick: controller.closeDetails }, tx("Close")),
        onPrint &&
          h(
            "button",
            {
              className: "oui-btn oui-btn--primary",
              onClick: () => {
                controller.closeDetails();
                onPrint({ path: file.path, fileName, thumbnail });
              },
            },
            h(Icons.Play, { size: 16 }),
            tx("Start print"),
          ),
      ),
    ),
  );
}

/** The menu and the delete confirmation, driven by useFileActions. */
function FileActionDialogs({ controller, onPrint }) {
  const { target, pendingDelete, details } = controller;
  return h(
    React.Fragment,
    null,
    h(Presence, null, target && h(FileActionSheet, { item: target, controller })),
    h(Presence, null, details && h(FileDetailsSheet, { item: details, controller, onPrint })),
    h(Presence, null, controller.queueItem && h(QueueAddDialog, { item: controller.queueItem, onClose: controller.closeQueue })),
    h(Presence, null, controller.scheduleItem && h(ScheduleDialog, { item: controller.scheduleItem, onClose: controller.closeSchedule })),
    h(ConfirmDialog, {
      open: Boolean(pendingDelete),
      tone: "danger",
      icon: h(Icons.Trash),
      title: tx("Delete the file?"),
      subtitle: pendingDelete ? pendingDelete.fileName : "",
      message: tx("The file will be deleted from the Raspberry for good. This cannot be undone."),
      confirmLabel: tx("Delete"),
      onConfirm: controller.confirmDelete,
      onCancel: controller.cancelDelete,
    }),
  );
}
