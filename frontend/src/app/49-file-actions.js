/* ============================================================================
   49 · FILE ACTIONS
   Long press (finger or mouse) or right click on a G-code file opens a menu:
     · open it in the text editor (51). A file too long for the editor opens
       read-only, just its first lines, so the app never freezes;
     · delete it, from the Raspberry's disk too (after a confirmation).
   ========================================================================== */

const FILE_PRESS_MS = 500;
const FILE_PRESS_SLOP_PX = 10; // a finger that moves further than this is scrolling, not pressing
const FILE_MENU_GUARD_MS = 450; // after the menu appears, clicks are ignored: lifting the finger must not pick a row
const GCODE_EDIT_MAX_BYTES = 256 * 1024; // up to here a file opens editable (the editor colours every line on each key)
const GCODE_PREVIEW_BYTES = 192 * 1024; // beyond it only this much of the start is shown, read-only

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
  const deleting = useRef(false);

  const closeMenu = () => setTarget(null);

  /** Opens `item` ({ file, fileName }) in the editor; the menu and the wide screen's detail panel both start here. */
  const openItemInEditor = async (item) => {
    const { file, fileName } = item;
    const size = file.size || 0;
    const tooLong = size > GCODE_EDIT_MAX_BYTES;
    setTarget(null);
    toast.notice("Apro " + fileName + "...", 1500);
    try {
      const { text, truncated } = await gcodeFilesApi.read(file.path, tooLong ? GCODE_PREVIEW_BYTES : 0);
      const readOnly = tooLong || truncated;
      const note = readOnly ? "Sola lettura • prime " + text.split("\n").length.toLocaleString("it-IT") + " righe di un file da " + (formatBytes(size) || "?") : "";
      openEditor(file.path, text, { root: GCODES_ROOT, readOnly, note });
    } catch (error) {
      toast.action("Errore apertura " + fileName + ": " + (error.message || ""));
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
      toast.notice("Eliminato: " + fileName);
    } catch (error) {
      const message = error.message || "errore";
      toast.action("Eliminazione non riuscita: " + (/print|load|busy|in use/i.test(message) ? "il file è in uso, ferma prima la stampa" : message));
    }
    deleting.current = false;
    setPendingDelete(null);
    list.reload();
  };

  return { target, pendingDelete, openMenu: setTarget, closeMenu, openInEditor, openItemInEditor, askDelete, askDeleteItem, cancelDelete, confirmDelete };
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
        h(FileActionRow, { icon: h(Icons.Code), title: "Apri nell'editor", subtitle: tooLong ? "File grande: solo lettura, prime righe" : "Leggi e modifica il gcode", onClick: controller.openInEditor }),
        h(FileActionRow, { icon: h(Icons.Trash), title: "Elimina dal Raspberry", subtitle: "Cancella il file per sempre", danger: true, onClick: controller.askDelete }),
      ),
      h("div", { className: "sheet-footer" }, h("button", { className: "oui-btn", onClick: controller.closeMenu }, "Annulla")),
    ),
  );
}

/** The menu and the delete confirmation, driven by useFileActions. */
function FileActionDialogs({ controller }) {
  const { target, pendingDelete } = controller;
  return h(
    React.Fragment,
    null,
    h(Presence, null, target && h(FileActionSheet, { item: target, controller })),
    h(ConfirmDialog, {
      open: Boolean(pendingDelete),
      tone: "danger",
      icon: h(Icons.Trash),
      title: "Eliminare il file?",
      subtitle: pendingDelete ? pendingDelete.fileName : "",
      message: "Il file verrà cancellato per sempre dal Raspberry. L'operazione non si può annullare.",
      confirmLabel: "Elimina",
      onConfirm: controller.confirmDelete,
      onCancel: controller.cancelDelete,
    }),
  );
}
