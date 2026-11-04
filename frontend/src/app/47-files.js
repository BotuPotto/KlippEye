/* ============================================================================
   47 · FILES
   The G-code library, newest first, with thumbnails, estimated time and
   filament weight, and a confirmation before a print starts. A long press on a
   file opens its menu (open in the editor, delete): see 49-file-actions.js.
   ========================================================================== */

const GCODES_ROOT = "gcodes";
const FILES_METADATA_LIMIT = 8; // metadata (and thumbnails) are fetched for the newest N files...
const FILES_METADATA_LIMIT_WIDE = 24; // ...a wide screen shows far more tiles at once

/* ---------------------------------------------------------------------------
   Moonraker file API (the "gcodes" root). The backend backend forwards every
   method of /server/*, DELETE included, straight to Moonraker.
   ------------------------------------------------------------------------- */
const encodeRemotePath = (path) => path.split("/").map(encodeURIComponent).join("/");

/** Moonraker reports errors as { error: { code, message } }, the backend proxy as { error: "text" }. */
async function responseError(response) {
  try {
    const error = (await response.json()).error;
    const message = typeof error === "string" ? error : error && error.message;
    if (message) return message;
  } catch (e) {}
  return "HTTP " + response.status;
}

const gcodeFilesApi = {
  /** Deletes the file from the Raspberry's disk. Moonraker refuses the file that is printing. */
  async remove(path) {
    const response = await fetchFresh("/server/files/" + GCODES_ROOT + "/" + encodeRemotePath(path), { method: "DELETE" });
    if (!response.ok) throw new Error(await responseError(response));
  },

  /** The file's text, or with `maxBytes` just its start (cut at a line end): { text, truncated }. */
  async read(path, maxBytes) {
    const response = await fetchFresh("/server/files/" + GCODES_ROOT + "/" + encodeRemotePath(path));
    if (!response.ok) throw new Error(await responseError(response));
    if (!maxBytes || !response.body || !response.body.getReader) return { text: await response.text(), truncated: false };
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let text = "";
    let received = 0;
    let truncated = false;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.length;
      text += decoder.decode(value, { stream: true });
      if (received >= maxBytes) {
        truncated = true;
        reader.cancel().catch(noop); // stop the download: the rest of a long file is not needed
        break;
      }
    }
    if (truncated) text = text.slice(0, Math.max(0, text.lastIndexOf("\n")));
    return { text, truncated };
  },
};

/** "45min", "3.5h", "12h" or "--". */
function formatEstimatedTime(seconds) {
  if (seconds <= 0) return "--";
  if (seconds < 3600) return Math.round(seconds / 60) + "min";
  const hours = seconds / 3600;
  return hours >= 10 ? Math.round(hours) + "h" : hours.toFixed(1) + "h";
}

/** Filament weight from metadata; falls back to an estimate from the length. */
function formatFilamentWeight(meta) {
  const grams = meta.filament_weight_total || 0;
  const millimetres = meta.filament_total || 0;
  if (grams > 0) return grams >= 1000 ? (grams / 1000).toFixed(2) + "kg" : Math.round(grams) + "g";
  if (millimetres > 0) return Math.round((millimetres / 1000) * 1.24) + "g";
  return "--";
}

/**
 * G-code file list, refreshed every 8 s while `active`. Metadata is fetched for
 * the newest `metadataLimit` files only, and only once per file version.
 */
function useFileList(active, metadataLimit = FILES_METADATA_LIMIT) {
  const [state, setState] = useState({ files: [], loading: true, error: null });
  // 1.40: sorting by print time, filament or last print needs every file's metadata (read a few at a time, once each)
  const [allMeta, setAllMeta] = useState(false);
  const limit = allMeta ? Infinity : metadataLimit;
  const [meta, setMeta] = useState({}); // path -> metadata
  const [thumbs, setThumbs] = useState({}); // path -> thumbnail URL
  const fetchedVersion = useRef({}); // path -> modified time already fetched
  const refreshRef = useRef(null);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;

    const refresh = async () => {
      try {
        const json = await fetchJson("/server/files/list?root=gcodes");
        const files = json.result || [];
        files.sort((a, b) => (b.modified || 0) - (a.modified || 0));
        if (cancelled) return;
        setState({ files, loading: false, error: null });
        for (const file of files.slice(0, limit)) {
          if (cancelled) break;
          if (fetchedVersion.current[file.path] === file.modified) continue;
          try {
            const result = (await fetchJson("/server/files/metadata?filename=" + encodeURIComponent(file.path))).result || {};
            if (cancelled) break;
            fetchedVersion.current[file.path] = file.modified;
            setMeta((previous) => ({ ...previous, [file.path]: result }));
            if (result.thumbnails && result.thumbnails.length > 0) {
              const thumbnail = result.thumbnails[result.thumbnails.length - 1];
              setThumbs((previous) => ({ ...previous, [file.path]: "/server/files/gcodes/" + thumbnail.relative_path }));
            }
          } catch (e) {}
        }
      } catch (e) {
        if (!cancelled) setState((previous) => ({ ...previous, loading: false, error: e.message || tx("Error") }));
      }
    };

    refreshRef.current = refresh;
    const stopPolling = startPolling(refresh, POLL_MS.files);
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [active, limit]);

  return {
    ...state,
    /** true: read the metadata of every file, not only of the newest ones. */
    needAllMeta: setAllMeta,
    meta,
    thumbs,
    /** Reads the list again now. */
    reload: () => refreshRef.current && refreshRef.current(),
    /** Drops a file from the list at once (after it was deleted), without waiting for the next read. */
    forget: (path) => setState((previous) => ({ ...previous, files: previous.files.filter((file) => file.path !== path) })),
  };
}

/* ---------------------------------------------------------------------------
   Order and search (1.40, like Mainsail): kept on this device (the search is not)
   ------------------------------------------------------------------------- */
const GCODE_VIEW_KEY = "ke_gcode_view";
const GCODE_SORTS = [
  { id: "newest", label: tx("Newest first") },
  { id: "oldest", label: tx("Oldest first") },
  { id: "name", label: tx("Name A→Z") },
  { id: "name-desc", label: tx("Name Z→A") },
  { id: "time", label: tx("Shortest print first"), meta: true },
  { id: "time-desc", label: tx("Longest print first"), meta: true },
  { id: "filament", label: tx("Most filament first"), meta: true },
  { id: "size", label: tx("Largest first") },
  { id: "printed", label: tx("Last printed first"), meta: true },
];
const gcodeViewStore = (() => {
  const saved = storage.getJson(GCODE_VIEW_KEY) || {};
  let view = { sort: GCODE_SORTS.some((sort) => sort.id === saved.sort) ? saved.sort : "newest", query: "" };
  const listeners = new Set();
  return {
    snapshot: () => view,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    set(change) {
      view = { ...view, ...change };
      storage.set(GCODE_VIEW_KEY, JSON.stringify({ sort: view.sort }));
      listeners.forEach((listener) => listener());
    },
  };
})();
const useGcodeView = () => useSyncExternalStore(gcodeViewStore.subscribe, gcodeViewStore.snapshot);

/** The files as the view says: searched by name (and folder), in the chosen order; files with no figure for it go last. */
function orderedFiles(list, view) {
  const needle = view.query.trim().toLowerCase();
  const files = needle ? list.files.filter((file) => file.path.toLowerCase().includes(needle)) : list.files.slice();
  const meta = (file) => list.meta[file.path] || {};
  const name = (file) => file.path.split("/").pop();
  const byName = (a, b) => name(a).localeCompare(name(b), undefined, { numeric: true, sensitivity: "base" });
  const figure = (pick, descending) => (a, b) => {
    const [x, y] = [pick(a), pick(b)];
    if (!(x > 0) && !(y > 0)) return byName(a, b);
    if (!(x > 0)) return 1;
    if (!(y > 0)) return -1;
    return (descending ? y - x : x - y) || byName(a, b);
  };
  const weight = (file) => meta(file).filament_weight_total || (meta(file).filament_total ? meta(file).filament_total * 0.00124 : 0);
  const compare = {
    newest: (a, b) => (b.modified || 0) - (a.modified || 0),
    oldest: (a, b) => (a.modified || 0) - (b.modified || 0),
    name: byName,
    "name-desc": (a, b) => byName(b, a),
    time: figure((file) => meta(file).estimated_time, false),
    "time-desc": figure((file) => meta(file).estimated_time, true),
    filament: figure(weight, true),
    size: figure((file) => file.size, true),
    printed: figure((file) => meta(file).print_start_time, true),
  }[view.sort];
  return files.sort(compare || ((a, b) => (b.modified || 0) - (a.modified || 0)));
}

/** The order menu of the files card. */
function GcodeSortButton({ view }) {
  const menu = useDropdown();
  const current = GCODE_SORTS.find((sort) => sort.id === view.sort) || GCODE_SORTS[0];
  return h(
    React.Fragment,
    null,
    h(
      "button",
      { type: "button", ref: menu.anchorRef, className: "files-sort__btn", "aria-haspopup": "menu", "aria-expanded": menu.open, "aria-label": tx("Order"), onClick: menu.toggle },
      h("span", { className: "files-sort__icon" }, h(Icons.Sort)),
      h("span", { className: "files-sort__label" }, current.label),
      h("span", { className: cx("menu-chevron", menu.open && "is-open") }, h(Icons.Chevron, { size: 14 })),
    ),
    h(
      DropdownMenu,
      { menu },
      h(MenuLabel, null, tx("Order")),
      GCODE_SORTS.map((sort) =>
        h(
          "button",
          { key: sort.id, type: "button", className: "oui-menu__item console-option", role: "menuitemradio", "aria-checked": view.sort === sort.id, "data-sort": sort.id, onClick: () => (gcodeViewStore.set({ sort: sort.id }), menu.close()) },
          h("span", { className: "oui-menu__icon" }, view.sort === sort.id ? h(Icons.Check, { size: 18 }) : null),
          h("span", { className: "oui-menu__text" }, h("span", { className: "oui-menu__title" }, sort.label)),
        ),
      ),
    ),
  );
}

/**
 * `onMenu({ file, fileName, meta, thumbnail })` runs on a long press (or right click) anywhere on the tile.
 * On a wide screen a tap also selects the tile (`onSelect`) and the detail panel shows it.
 */
function FileCard({ file, meta, thumbnail, onPrint, onMenu, selected, onSelect }) {
  const fileName = file.path.split("/").pop();
  const press = useLongPress(() => onMenu({ file, fileName, meta, thumbnail }));
  return h(
    "div",
    { className: cx("file-card", selected && "is-selected"), title: fileName, onClick: onSelect, ...press },
    h("div", { className: "file-card__preview" }, thumbnail ? h("img", { src: thumbnail, className: "file-thumb", draggable: false }) : h(PrintPlaceholder)),
    h(
      "div",
      { className: "file-card__body" },
      h("div", { className: "file-card__name" }, fileName),
      h(
        "div",
        { className: "file-card__meta" },
        h("span", { className: "file-card__fact" }, h(Icons.Clock), formatEstimatedTime(meta.estimated_time || 0)),
        h("span", { className: "file-card__fact" }, h(Icons.Spool), formatFilamentWeight(meta)),
      ),
    ),
    h(
      "button",
      { onClick: () => onPrint({ path: file.path, fileName, thumbnail }), "aria-label": tx("Start print"), className: "oui-btn oui-btn--accent-soft oui-btn--sm oui-btn--block" },
      h("span", { className: "file-card__print-long" }, tx("Start print")),
      h("span", { className: "file-card__print-short" }, txc("verb", "Print")),
    ),
  );
}

function FilesCard({ list, onPrint, onMenu, selectedPath, onSelect }) {
  const view = useGcodeView();
  const sort = GCODE_SORTS.find((one) => one.id === view.sort);
  const needsMeta = Boolean(sort && sort.meta);
  useEffect(() => {
    if (list.needAllMeta) list.needAllMeta(needsMeta);
  }, [needsMeta]);
  const files = orderedFiles(list, view);
  const notice = (className, text) => h("div", { className: cx("oui-caption", className) }, text);
  let body;
  if (list.loading) body = notice("files-notice", tx("Loading..."));
  else if (list.error) body = notice("files-notice", list.error);
  else if (list.files.length === 0) body = notice("files-notice", tx("No files"));
  else if (files.length === 0) body = notice("files-notice", tx("No file matches «{text}»", { text: view.query.trim() }));
  else
    body = files.map((file) =>
      h(FileCard, {
        key: file.path,
        file,
        meta: list.meta[file.path] || {},
        thumbnail: list.thumbs[file.path] || null,
        onPrint,
        onMenu,
        selected: selectedPath === file.path,
        onSelect: onSelect ? () => onSelect(file.path) : undefined,
      }),
    );

  return h(
    Card,
    null,
    h(CardHeader, { title: tx("Print files") }),
    h(
      "div",
      { className: "files-search" },
      h(Icons.Search, { size: 16 }),
      h("input", {
        type: "search",
        className: "oui-field files-search__input",
        value: view.query,
        placeholder: tx("Search files..."),
        "aria-label": tx("Search files..."),
        onChange: (event) => gcodeViewStore.set({ query: event.target.value }),
      }),
    ),
    h(
      "div",
      { className: "files-sort" },
      h(GcodeSortButton, { view }),
      h("span", { className: "oui-badge" }, list.loading ? "..." : (view.query.trim() ? files.length + " / " : "") + list.files.length + tx(" files")),
    ),
    !list.loading && !list.error && list.files.length > 0 && h("div", { className: "oui-caption files-hint" }, tx("Long-press a file for its details, the editor or to delete it")),
    h("div", { className: "grid grid-cols-2 files-grid" }, body),
  );
}

/* ---------------------------------------------------------------------------
   Print confirmation
   ------------------------------------------------------------------------- */
function PrintConfirmDialog({ job, onConfirm, onCancel }) {
  if (!job) return null;
  return h(
    "div",
    { className: "confirm-overlay", onClick: (e) => e.target === e.currentTarget && onCancel() },
    h(
      "div",
      { className: "confirm-card", onClick: (e) => e.stopPropagation() },
      h("div", { className: "dialog-title mb-4" }, tx("Confirm print")),
      h(
        "div",
        { className: "print-preview oui-well" },
        job.thumbnail ? h("img", { src: job.thumbnail, className: "file-thumb file-thumb--large" }) : h(PrintPlaceholder),
      ),
      h(
        "div",
        { className: "dialog-text" },
        tx("Start printing "),
        h("b", null, job.fileName || job.path || ""),
        "?",
      ),
      h(
        "div",
        { className: "oui-btn-row" },
        h("button", { onClick: onCancel, className: "oui-btn" }, tx("Cancel")),
        h("button", { onClick: onConfirm, className: "oui-btn oui-btn--primary" }, txc("verb", "Print")),
      ),
    ),
  );
}
