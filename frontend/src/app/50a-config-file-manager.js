/* ============================================================================
   50a · CONFIG FILE MANAGER
   What can be done to the files and folders of the config card:
     · the "New" menu: new file, new folder, upload (files can also be
       dropped on the card from a computer);
     · a menu for every row (the ⋯ button, a long press or a right click):
       open, download (files), rename, move to another folder, delete;
     · on a computer, a row can be dragged onto a folder (or onto "/" and "..").
   It makes the same calls as Mainsail and Fluidd: uploading an empty file
   creates a file, Moonraker's "move" renames and moves files and folders alike,
   and a folder is deleted with everything inside it.
   ========================================================================== */

const MAX_NAME_LENGTH = 100;
/** Not allowed in a name: the path separators, and what the Raspberry proxy cannot pass on in an address (? # %). */
const INVALID_NAME_CHARS = /[\\/?#%\u0000-\u001f]/;
/** Klipper and Moonraker do not start without them. */
const CRITICAL_CONFIG_FILES = ["printer.cfg", "moonraker.conf"];
const DESKTOP_POINTER = "(hover: hover) and (pointer: fine)"; // rows are dragged only where there is a mouse: a finger must scroll

const showPath = (path) => "/" + path;
const isCriticalConfigFile = (item) => item.type === "file" && CRITICAL_CONFIG_FILES.includes(item.path);
const CRITICAL_WARNING = tx("Klipper and Moonraker read this file at startup: if you move, rename or delete it the printer will not start again.");
const CRITICAL_DELETE_MESSAGE = tx("Klipper and Moonraker read this file at startup: without it the printer will not start again. Delete it anyway?");

/** Why `name` cannot be used, or "" when it can. `taken`: the names already in the folder. */
function nameProblem(name, taken) {
  if (name.length > MAX_NAME_LENGTH) return tx("Name too long (at most {max} characters)", { max: MAX_NAME_LENGTH });
  if (name.startsWith(".")) return tx("The name cannot start with a dot: the file would stay hidden");
  if (INVALID_NAME_CHARS.test(name)) return tx("These characters are not allowed:  /  \\  ?  #  %");
  if (HIDDEN_CONFIG_FILE.test(name)) return tx("Name reserved for Klipper's backups, which are not shown");
  if (taken.has(name)) return tx("Something with this name already exists");
  return "";
}

/** What the name dialog's text amounts to: the trimmed name, what is wrong with it, whether OK can be pressed. */
function checkName(dialog, taken) {
  const name = dialog.value.trim();
  const unchanged = dialog.mode === "rename" && name === dialog.item.name;
  const problem = name && !unchanged ? nameProblem(name, taken) : "";
  return { name, problem, canSubmit: Boolean(name) && !unchanged && !problem };
}

/** Whether `item` may go into the folder `target`: not where it already is, and a folder never inside itself. */
function canMoveInto(item, target) {
  if (target === parentPath(item.path)) return false;
  return !(item.type === "folder" && (target === item.path || target.startsWith(item.path + "/")));
}

const dragCarriesFiles = (event) => Array.from(event.dataTransfer.types || []).includes("Files");

/* ---------------------------------------------------------------------------
   Drag and drop (computer only)
   ------------------------------------------------------------------------- */

/**
 * `moveTo(item, folder)` and `receiveFiles(files)` do the work.
 *   rowDrag(item)        props that make a row draggable
 *   dropTarget(path, key) props of a place a row can be dropped on ("" is the root); `key` tells which one is lit
 *   dropZone             props of the card: files dragged in from outside are uploaded
 */
function useConfigDragDrop({ moveTo, receiveFiles }) {
  const [drag, setDrag] = useState({ item: null, over: null });
  const [filesOver, setFilesOver] = useState(false);
  const idle = { item: null, over: null };

  const rowDrag = (item) =>
    window.matchMedia && window.matchMedia(DESKTOP_POINTER).matches
      ? {
          draggable: true,
          onDragStart: (event) => {
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("text/plain", item.path); // Firefox does not start a drag without data
            setDrag({ item, over: null });
          },
          onDragEnd: () => setDrag(idle),
        }
      : {};

  const dropTarget = (path, key = path) => {
    const allowed = Boolean(drag.item) && canMoveInto(drag.item, path);
    return {
      onDragOver: (event) => {
        if (!allowed) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        if (drag.over !== key) setDrag({ item: drag.item, over: key });
      },
      onDragLeave: (event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setDrag((previous) => (previous.over === key ? { item: previous.item, over: null } : previous));
      },
      onDrop: (event) => {
        if (!allowed) return;
        event.preventDefault();
        const item = drag.item;
        setDrag(idle);
        moveTo(item, path);
      },
    };
  };

  const dropZone = {
    onDragOver: (event) => {
      if (!dragCarriesFiles(event)) return;
      event.preventDefault();
      setFilesOver(true);
    },
    onDragLeave: (event) => {
      if (!event.currentTarget.contains(event.relatedTarget)) setFilesOver(false);
    },
    onDrop: (event) => {
      if (!dragCarriesFiles(event)) return;
      event.preventDefault();
      setFilesOver(false);
      receiveFiles(Array.from(event.dataTransfer.files));
    },
  };

  return { rowDrag, dropTarget, dropZone, filesOver, dragging: drag.item, isOver: (key) => drag.over === key };
}

/* ---------------------------------------------------------------------------
   State and operations
   ------------------------------------------------------------------------- */

/**
 * `folder` is useConfigFolder(); `openItem(item)` opens a folder, a file in the editor or an image.
 * One change at a time runs on the server; the folder is read again when it ends.
 */
function useConfigFileManager(folder, openItem) {
  const [menuItem, setMenuItem] = useState(null); // the row whose menu is open
  const [nameDialog, setNameDialog] = useState(null); // { mode: "file" | "folder" | "rename", item, value }
  const [moveItem, setMoveItem] = useState(null); // the row whose destination is being chosen
  const [deleteItem, setDeleteItem] = useState(null);
  const [pendingUpload, setPendingUpload] = useState(null); // { files, replaced } waiting for a yes: some would replace what is there
  const [busy, setBusy] = useState(false);
  const working = useRef(false);
  const fileInput = useRef(null);

  const perform = async (task, doneMessage, failedMessage) => {
    if (working.current) return false;
    working.current = true;
    setBusy(true);
    let done = false;
    try {
      await task();
      toast.notice(doneMessage);
      done = true;
    } catch (error) {
      toast.action(failedMessage + ": " + (error.message || "errore"));
    }
    working.current = false;
    setBusy(false);
    await folder.refresh(); // also after a failure: part of the work may have been done
    return done;
  };

  /* ---- name dialog: new file, new folder, rename ---- */
  const askName = (mode, item = null) => {
    setMenuItem(null);
    setNameDialog({ mode, item, value: item ? item.name : "" });
  };
  const submitName = async () => {
    const { name, canSubmit } = checkName(nameDialog, folder.names);
    if (!canSubmit) return;
    const { mode, item } = nameDialog;
    let done;
    if (mode === "file") done = await perform(() => configFilesApi.createFile(folder.currentPath, name), tx("Created: ") + name, tx("Could not create it"));
    else if (mode === "folder") done = await perform(() => configFilesApi.createFolder(joinPath(folder.currentPath, name)), tx("Folder created: ") + name, tx("Could not create it"));
    else done = await perform(() => configFilesApi.move(item.path, joinPath(parentPath(item.path), name)), tx("Renamed: ") + name, tx("Could not rename it"));
    if (!done) return;
    setNameDialog(null);
    if (mode === "file" && !isImagePath(name)) {
      const path = joinPath(folder.currentPath, name);
      configFileCache.set(path, ""); // the file is empty: no need to ask the server, and the editor is the next thing wanted
      openItem({ type: "file", name, path });
    }
  };

  /* ---- move ---- */
  const askMove = (item) => {
    setMenuItem(null);
    setMoveItem(item);
  };
  /** Moves `item` into the folder `target` ("" is the root). Returns whether it was moved. */
  const moveTo = async (item, target) => {
    if (!canMoveInto(item, target)) return false;
    try {
      if (takenNames(await configFilesApi.listDirectory(target)).has(item.name)) {
        toast.action(tx("«{name}» already exists in {folder}", { name: item.name, folder: showPath(target) }));
        return false;
      }
    } catch (error) {} // cannot tell: Moonraker will refuse if the name is taken
    return perform(() => configFilesApi.move(item.path, joinPath(target, item.name)), tx("Moved to ") + showPath(target), tx("Could not move it"));
  };
  const confirmMove = async (target) => {
    if (await moveTo(moveItem, target)) setMoveItem(null);
  };

  /* ---- delete ---- */
  const askDelete = (item) => {
    setMenuItem(null);
    setDeleteItem(item);
  };
  const cancelDelete = () => {
    if (!working.current) setDeleteItem(null);
  };
  const confirmDelete = async () => {
    const item = deleteItem;
    await perform(() => (item.type === "folder" ? configFilesApi.removeFolder(item.path) : configFilesApi.removeFile(item.path)), tx("Deleted: ") + item.name, tx("Could not delete it"));
    setDeleteItem(null);
  };

  /* ---- upload ---- */
  const chooseFiles = () => fileInput.current && fileInput.current.click();
  const uploadFiles = (files) =>
    perform(
      async () => {
        const failed = [];
        for (const file of files) {
          try {
            await configFilesApi.upload(file, folder.currentPath);
          } catch (error) {
            failed.push(file.name + " (" + (error.message || "errore") + ")");
          }
        }
        if (failed.length) throw new Error(failed.join(", "));
      },
      files.length === 1 ? tx("Uploaded: {name}", { name: files[0].name }) : tx("Uploaded {count} files", { count: files.length }),
      tx("Upload failed"),
    );
  /** Sorts what was chosen or dropped: usable names go up (after a yes if they replace a file), the others are reported. */
  const receiveFiles = (files) => {
    const folders = new Set(folder.entries ? folder.entries.folders.map((item) => item.name) : []);
    const existing = new Set(folder.entries ? folder.entries.files.map((item) => item.name) : []);
    const accepted = [];
    let refused = 0;
    for (const file of files) {
      if (!file.name || nameProblem(file.name, folders) || file.name.trim() !== file.name) refused++;
      else accepted.push(file);
    }
    if (refused) toast.action(refused === 1 ? tx("One file has an invalid name or is a folder: skipped") : tx("{count} files have an invalid name: skipped", { count: refused }));
    const replaced = accepted.filter((file) => existing.has(file.name)).map((file) => file.name);
    if (replaced.length) setPendingUpload({ files: accepted, replaced });
    else if (accepted.length) uploadFiles(accepted);
  };
  const onFilesChosen = (event) => {
    const files = Array.from(event.target.files || []);
    event.target.value = ""; // choosing the same file again must trigger a change
    receiveFiles(files);
  };
  const confirmUpload = () => {
    const { files } = pendingUpload;
    setPendingUpload(null);
    uploadFiles(files);
  };

  const dnd = useConfigDragDrop({ moveTo, receiveFiles });

  return {
    busy,
    dnd,
    openItem,
    // new / upload
    newFile: () => askName("file"),
    newFolder: () => askName("folder"),
    chooseFiles,
    fileInput: { ref: fileInput, type: "file", multiple: true, hidden: true, onChange: onFilesChosen },
    // the row menu
    menuItem,
    openMenu: setMenuItem,
    closeMenu: () => setMenuItem(null),
    download: (item) => downloadFile(configFileUrl(item.path), item.name),
    askRename: (item) => askName("rename", item),
    askMove,
    askDelete,
    // dialogs
    nameDialog,
    setNameValue: (value) => setNameDialog((dialog) => ({ ...dialog, value })),
    closeName: () => setNameDialog(null),
    submitName,
    names: folder.names,
    currentPath: folder.currentPath,
    moveItem,
    closeMove: () => setMoveItem(null),
    confirmMove,
    deleteItem,
    cancelDelete,
    confirmDelete,
    pendingUpload,
    cancelUpload: () => setPendingUpload(null),
    confirmUpload,
  };
}

/* ---------------------------------------------------------------------------
   UI: the "New" menu
   ------------------------------------------------------------------------- */
function ConfigNewMenuButton({ manager }) {
  const menu = useDropdown();
  const choose = (action) => () => {
    menu.close();
    action();
  };
  return h(
    React.Fragment,
    null,
    h(
      "button",
      { ref: menu.anchorRef, className: cx("oui-btn oui-btn--sm oui-btn--accent-soft", manager.busy && "is-busy"), disabled: manager.busy, "aria-haspopup": "menu", "aria-expanded": menu.open, onClick: menu.toggle },
      manager.busy
        ? [h(Icons.Refresh, { key: "icon", size: 16 }), tx("Working...")]
        : [h(Icons.Plus, { key: "icon", size: 16 }), tx("New"), h("span", { key: "arrow", className: cx("menu-chevron", menu.open && "is-open") }, h(Icons.Chevron, { size: 16 }))],
    ),
    h(
      DropdownMenu,
      { menu },
      h(MenuItem, { icon: h(Icons.FilePlus), title: tx("New file"), subtitle: tx("Create an empty file and open it in the editor"), onClick: choose(manager.newFile) }),
      h(MenuItem, { icon: h(Icons.FolderPlus), title: tx("New folder"), subtitle: tx("Create an empty folder"), onClick: choose(manager.newFolder) }),
      h(MenuItem, {
        icon: h(Icons.Upload),
        title: tx("Upload files"),
        subtitle: APP_CAN_PICK_FILES ? tx("From this device, also several at once") : tx("Not available in this version of the app: update it or use the browser"),
        disabled: !APP_CAN_PICK_FILES,
        onClick: choose(manager.chooseFiles),
      }),
    ),
  );
}

/* ---------------------------------------------------------------------------
   UI: the menu of a row
   ------------------------------------------------------------------------- */
function ConfigActionSheet({ manager }) {
  useBodyScrollLock(true);
  const ignoreEarlyClick = useEarlyClickGuard();
  const item = manager.menuItem;
  const isFolder = item.type === "folder";
  const isImage = !isFolder && isImagePath(item.path);
  const act = (action) => () => {
    manager.closeMenu();
    action(item);
  };
  const details = [isFolder ? tx("Folder") : formatBytes(item.size), formatFileDate(item.modified)].filter(Boolean).join(" • ");
  const open = isFolder
    ? { icon: h(Icons.Folder), title: tx("Open folder"), subtitle: tx("Show what it contains") }
    : isImage
      ? { icon: h(Icons.Image), title: tx("View image"), subtitle: tx("Full-screen preview") }
      : { icon: h(Icons.Code), title: tx("Open in the editor"), subtitle: tx("Read and edit the text") };
  return h(
    "div",
    { className: "sheet-overlay sheet-overlay--actions", onClickCapture: ignoreEarlyClick, onClick: (e) => e.target === e.currentTarget && manager.closeMenu() },
    h(
      "div",
      { className: "sheet-card" },
      h(
        "div",
        { className: "file-sheet__head" },
        h("div", { className: "file-sheet__thumb" }, h(FileGlyph, { kind: configFileKind(item), large: true })),
        h("div", { className: "file-sheet__info" }, h("div", { className: "file-sheet__name" }, item.name), details && h("div", { className: "oui-caption oui-num" }, details), h("div", { className: "oui-caption oui-mono cfg-sheet__where" }, "in " + showPath(parentPath(item.path)))),
      ),
      h(
        "div",
        { className: "oui-list file-sheet__actions" },
        h(FileActionRow, { ...open, onClick: act(manager.openItem) }),
        !isFolder && h(FileActionRow, { icon: h(Icons.Download, { size: 20 }), title: tx("Download"), subtitle: IN_APP_WEBVIEW ? tx("Save a copy in the Download folder") : tx("Save a copy on this device"), onClick: act(manager.download) }),
        h(FileActionRow, { icon: h(Icons.Pencil), title: tx("Rename"), subtitle: isFolder ? tx("Change the name of the folder") : tx("Change the name of the file"), onClick: act(manager.askRename) }),
        h(FileActionRow, { icon: h(Icons.Move), title: tx("Move to…"), subtitle: tx("Choose another folder"), onClick: act(manager.askMove) }),
        h(FileActionRow, { icon: h(Icons.Trash), title: tx("Delete from the Raspberry"), subtitle: isFolder ? tx("Delete the folder and everything in it") : tx("Delete the file for good"), danger: true, onClick: act(manager.askDelete) }),
      ),
      h("div", { className: "sheet-footer" }, h("button", { className: "oui-btn", onClick: manager.closeMenu }, tx("Cancel"))),
    ),
  );
}

/* ---------------------------------------------------------------------------
   UI: new file, new folder, rename
   ------------------------------------------------------------------------- */
const NAME_DIALOGS = {
  file: { icon: Icons.FilePlus, title: tx("New file"), placeholder: tx("name.cfg"), confirm: tx("Create") },
  folder: { icon: Icons.FolderPlus, title: tx("New folder"), placeholder: tx("name"), confirm: tx("Create") },
  rename: { icon: Icons.Pencil, title: tx("Rename"), placeholder: "", confirm: tx("Rename") },
};

function ConfigNameDialog({ manager }) {
  const dialog = manager.nameDialog;
  const inputRef = useRef(null);
  const isOpen = Boolean(dialog);
  useBodyScrollLock(isOpen);

  useEffect(() => {
    if (!isOpen) return;
    const timer = setTimeout(() => {
      const input = inputRef.current;
      if (!input) return;
      input.focus();
      const dot = dialog.item && dialog.item.type === "file" ? dialog.value.lastIndexOf(".") : -1;
      input.setSelectionRange(0, dot > 0 ? dot : dialog.value.length); // renaming a file selects the name, not the extension
    }, 100);
    return () => clearTimeout(timer);
  }, [isOpen]);

  if (!dialog) return null;
  const spec = NAME_DIALOGS[dialog.mode];
  const { problem, canSubmit } = checkName(dialog, manager.names);
  const where = dialog.mode === "rename" ? parentPath(dialog.item.path) : manager.currentPath;
  const title = dialog.mode === "rename" ? (dialog.item.type === "folder" ? tx("Rename folder") : tx("Rename file")) : spec.title;
  const submit = () => canSubmit && !manager.busy && manager.submitName();
  return h(
    "div",
    { className: "modal", onClick: (e) => e.target === e.currentTarget && manager.closeName() },
    h(
      "div",
      { className: "modal-card", onClick: (e) => e.stopPropagation() },
      h("div", { className: "dialog-head" }, h("div", { className: "dialog-head__icon" }, h(spec.icon)), h("div", null, h("div", { className: "dialog-title" }, title), h("div", { className: "dialog-sub oui-mono" }, "in " + showPath(where)))),
      h("input", {
        ref: inputRef,
        type: "text",
        value: dialog.value,
        placeholder: spec.placeholder,
        maxLength: 120,
        autoCapitalize: "off",
        autoCorrect: "off",
        spellCheck: false,
        "aria-label": tx("Name"),
        "aria-invalid": Boolean(problem),
        onChange: (e) => manager.setNameValue(e.target.value),
        onKeyDown: (e) => {
          if (e.key === "Enter") submit();
          if (e.key === "Escape") manager.closeName();
        },
        className: "oui-field modal-input",
      }),
      h("div", { className: "cfg-field-error", role: "alert" }, problem),
      dialog.item && isCriticalConfigFile(dialog.item) && h("div", { className: "oui-tile oui-tile--warn cfg-warning" }, CRITICAL_WARNING),
      h(
        "div",
        { className: "oui-btn-row" },
        h("button", { className: "oui-btn", onClick: manager.closeName }, tx("Cancel")),
        h("button", { className: cx("oui-btn oui-btn--primary", manager.busy && "is-busy"), disabled: !canSubmit || manager.busy, onClick: submit }, spec.confirm),
      ),
    ),
  );
}

/* ---------------------------------------------------------------------------
   UI: choose the folder to move into
   ------------------------------------------------------------------------- */
/** `icon` goes in a round button-like disc (the way up); `glyph` is a ready file tile (a folder). */
function PickRow({ icon, glyph, name, meta, onClick }) {
  return h(
    "button",
    { className: "oui-row cfg-pick", onClick },
    glyph || h("span", { className: "oui-row__icon" }, icon),
    h("span", { className: "oui-row__text" }, h("span", { className: "oui-row__name" }, name), meta && h("span", { className: "oui-row__meta oui-mono" }, meta)),
    h("span", { className: "cfg-pick__go" }, "›"),
  );
}

function ConfigMoveSheet({ manager }) {
  useBodyScrollLock(true);
  const item = manager.moveItem;
  const [browse, setBrowse] = useState(parentPath(item.path)); // the folder being looked into: the item goes there
  const [listing, setListing] = useState({ entries: null, error: "" });

  useEffect(() => {
    let current = true;
    setListing({ entries: directoryCache.get(browse) || null, error: "" });
    configFilesApi.listDirectory(browse).then(
      (entries) => {
        directoryCache.set(browse, entries);
        if (current) setListing({ entries, error: "" });
      },
      (error) => current && setListing({ entries: null, error: error.message || tx("Cannot read the folder") }),
    );
    return () => {
      current = false;
    };
  }, [browse]);

  const subfolders = listing.entries ? sortedVisible(listing.entries.folders).filter((entry) => entry.path !== item.path) : [];
  const isHome = browse === parentPath(item.path);
  const taken = Boolean(listing.entries) && !isHome && takenNames(listing.entries).has(item.name);
  const canMove = Boolean(listing.entries) && canMoveInto(item, browse) && !taken && !manager.busy;
  const hint = isHome ? tx("It is already in this folder") : taken ? tx("This folder already contains «{name}»", { name: item.name }) : "";

  let body;
  if (listing.error) body = h("div", { className: "oui-notice" }, listing.error);
  else if (!listing.entries) body = h("div", { className: "oui-notice" }, tx("Loading..."));
  else
    body = h(
      "div",
      { className: "oui-list cfg-pick__list" },
      browse && h(PickRow, { key: "up", icon: h(Icons.ArrowUp, { size: 18 }), name: tx("Parent folder"), meta: showPath(parentPath(browse)), onClick: () => setBrowse(parentPath(browse)) }),
      subfolders.map((entry) => h(PickRow, { key: entry.path, glyph: h(FileGlyph, { kind: fileKind(entry.name, { folder: true }) }), name: entry.name, onClick: () => setBrowse(entry.path) })),
    );

  return h(
    "div",
    { className: "sheet-overlay sheet-overlay--folders", onClick: (e) => e.target === e.currentTarget && manager.closeMove() },
    h(
      "div",
      { className: "sheet-card sheet-card--column" },
      h(
        "div",
        { className: "sheet-header" },
        h("div", { className: "dialog-head cfg-pick__head" }, h("div", { className: "dialog-head__icon" }, h(Icons.Move)), h("div", null, h("div", { className: "dialog-title" }, tx("Move to…")), h("div", { className: "dialog-sub cfg-pick__item" }, item.name))),
        h("div", { className: "oui-label" }, tx("Destination")),
        h("div", { className: "cfg-pick__path oui-mono" }, showPath(browse)),
        isCriticalConfigFile(item) && h("div", { className: "oui-tile oui-tile--warn cfg-warning" }, CRITICAL_WARNING),
      ),
      h("div", { className: "cfg-pick__body" }, body, listing.entries && !listing.error && subfolders.length === 0 && h("div", { className: "oui-notice" }, tx("No subfolders"))),
      h("div", { className: "cfg-pick__hint" }, hint),
      h(
        "div",
        { className: "sheet-footer" },
        h("button", { className: "oui-btn", onClick: manager.closeMove }, tx("Cancel")),
        h("button", { className: cx("oui-btn oui-btn--primary", manager.busy && "is-busy"), disabled: !canMove, onClick: () => manager.confirmMove(browse) }, tx("Move here")),
      ),
    ),
  );
}

/* ---------------------------------------------------------------------------
   UI: all the dialogs of the manager
   ------------------------------------------------------------------------- */
function ConfigManagerDialogs({ manager }) {
  const { deleteItem, pendingUpload } = manager;
  const deletingFolder = Boolean(deleteItem) && deleteItem.type === "folder";
  const critical = Boolean(deleteItem) && isCriticalConfigFile(deleteItem);
  let deleteMessage = tx("The file will be deleted from the Raspberry for good. This cannot be undone.");
  if (deletingFolder) deleteMessage = tx("The folder and everything in it will be deleted from the Raspberry for good. This cannot be undone.");
  if (critical) deleteMessage = CRITICAL_DELETE_MESSAGE;
  return h(
    React.Fragment,
    null,
    h(Presence, null, manager.menuItem && h(ConfigActionSheet, { manager })),
    h(Presence, null, manager.nameDialog && h(ConfigNameDialog, { manager })),
    h(Presence, null, manager.moveItem && h(ConfigMoveSheet, { manager })),
    h(ConfirmDialog, {
      open: Boolean(deleteItem),
      tone: "danger",
      icon: h(Icons.Trash),
      title: deletingFolder ? tx("Delete the folder?") : tx("Delete the file?"),
      subtitle: deleteItem ? deleteItem.name : "",
      message: deleteMessage,
      confirmLabel: tx("Delete"),
      onConfirm: manager.confirmDelete,
      onCancel: manager.cancelDelete,
    }),
    h(ConfirmDialog, {
      open: Boolean(pendingUpload),
      tone: "danger",
      icon: h(Icons.Upload),
      title: tx("Replace the files?"),
      subtitle: pendingUpload ? (pendingUpload.replaced.length === 1 ? pendingUpload.replaced[0] : tx("{count} files already there", { count: pendingUpload.replaced.length })) : "",
      message: pendingUpload && pendingUpload.replaced.length > 1 ? tx("These files already exist and will be replaced: ") + pendingUpload.replaced.join(", ") + "." : tx("A file with this name already exists: its content will be replaced."),
      confirmLabel: tx("Replace"),
      onConfirm: manager.confirmUpload,
      onCancel: manager.cancelUpload,
    }),
  );
}
