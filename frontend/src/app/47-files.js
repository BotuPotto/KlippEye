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
        for (const file of files.slice(0, metadataLimit)) {
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
        if (!cancelled) setState((previous) => ({ ...previous, loading: false, error: e.message || "Errore" }));
      }
    };

    refreshRef.current = refresh;
    const stopPolling = startPolling(refresh, POLL_MS.files);
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [active, metadataLimit]);

  return {
    ...state,
    meta,
    thumbs,
    /** Reads the list again now. */
    reload: () => refreshRef.current && refreshRef.current(),
    /** Drops a file from the list at once (after it was deleted), without waiting for the next read. */
    forget: (path) => setState((previous) => ({ ...previous, files: previous.files.filter((file) => file.path !== path) })),
  };
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
      { onClick: () => onPrint({ path: file.path, fileName, thumbnail }), "aria-label": "Avvia stampa", className: "oui-btn oui-btn--accent-soft oui-btn--sm oui-btn--block" },
      h("span", { className: "file-card__print-long" }, "Avvia stampa"),
      h("span", { className: "file-card__print-short" }, "Stampa"),
    ),
  );
}

function FilesCard({ list, onPrint, onMenu, selectedPath, onSelect }) {
  const notice = (className, text) => h("div", { className: cx("oui-caption", className) }, text);
  let body;
  if (list.loading) body = notice("files-notice", "Caricamento...");
  else if (list.error) body = notice("files-notice", list.error);
  else if (list.files.length === 0) body = notice("files-notice", "Nessun file");
  else
    body = list.files.map((file) =>
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
    h(CardHeader, { title: "File di stampa" }),
    h(
      "div",
      { className: "files-sort" },
      h("span", { className: "files-sort__icon" }, h(Icons.Sort)),
      h("span", { className: "files-sort__label" }, "Ordinati dal più recente"),
      h("span", { className: "oui-badge" }, list.loading ? "..." : list.files.length + " file"),
    ),
    !list.loading && !list.error && list.files.length > 0 && h("div", { className: "oui-caption files-hint" }, "Tieni premuto su un file per aprirlo nell'editor o eliminarlo"),
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
      h("div", { className: "dialog-title mb-4" }, "Conferma stampa"),
      h(
        "div",
        { className: "print-preview oui-well" },
        job.thumbnail ? h("img", { src: job.thumbnail, className: "file-thumb file-thumb--large" }) : h(PrintPlaceholder),
      ),
      h(
        "div",
        { className: "dialog-text" },
        "Vuoi far partire la stampa di ",
        h("b", null, job.fileName || job.path || ""),
        "?",
      ),
      h(
        "div",
        { className: "oui-btn-row" },
        h("button", { onClick: onCancel, className: "oui-btn" }, "Annulla"),
        h("button", { onClick: onConfirm, className: "oui-btn oui-btn--primary" }, "Stampa"),
      ),
    ),
  );
}
