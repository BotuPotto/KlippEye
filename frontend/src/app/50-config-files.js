/* ============================================================================
   50 · CONFIG FILES — data
   Moonraker's "config" root (printer.cfg, macros/, ...): the file API and the
   folder the card is showing. The operations on files and folders (new,
   upload, rename, move, delete) are in 50a, the card itself in 50b.
   A file opens in the full-screen editor (51), an image in the image viewer (52).
   Klipper's backups (printer-YYYYMMDD_HHMMSS.cfg, *.bak...) and hidden files
   (.name) are left out unless the person shows them (1.39); the
   order is chosen too (name, last change, size). Both are kept on this device.
   ========================================================================== */

const CONFIG_ROOT = "config";
const IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "ico", "tiff", "tif"];
/** printer-*.cfg (generated backups) and crowsnest.conf.*: names reserved to the backups Klipper and crowsnest write. */
const HIDDEN_CONFIG_FILE = /^(printer-.*\.cfg|crownest\.conf\..*|crowsnest\.conf\..*)$/i;
/** 1.39: what counts as a backup: those, and the usual backup endings (.bak, .bkp, .backup, .old, ~). */
const BACKUP_CONFIG_FILE = /^(printer-.*\.cfg|crownest\.conf\..*|crowsnest\.conf\..*|.*\.(bak|bkp|backup|old|orig)|.*~)$/i;
const isHiddenName = (name) => name.startsWith(".");
const isBackupName = (name) => BACKUP_CONFIG_FILE.test(name.replace(/^\./, ""));

const baseName = (path) => path.split("/").pop() || "";
const isImagePath = (path) => IMAGE_EXTENSIONS.includes(baseName(path).split(".").pop().toLowerCase());
/** "macros" + "led.cfg" → "macros/led.cfg" (a path relative to the config root; "" is the root itself). */
const joinPath = (folder, name) => (folder ? folder + "/" + name : name);
const parentPath = (path) => path.split("/").slice(0, -1).join("/");
/** The path as Moonraker's directory and move endpoints want it: "config/macros". */
const configPath = (path) => joinPath(CONFIG_ROOT, path);
/** Where the server hands out the file itself (to read, to show as an image, to download). */
const configFileUrl = (path) => "/server/files/" + CONFIG_ROOT + "/" + encodeRemotePath(path);

/** "900 B", "4.0 KB", "1.2 MB"; "" when unknown. */
function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return "";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

/** "09/10, 10:53" */
function formatFileDate(unixSeconds) {
  if (!unixSeconds) return "";
  try {
    return new Date(unixSeconds * 1000).toLocaleString(LOCALE, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch (e) {
    return "";
  }
}

/* ---------------------------------------------------------------------------
   Moonraker file API (the "config" root)
   ------------------------------------------------------------------------- */

/** Last known server content of every config file opened so far (path → text). */
const configFileCache = new Map();

/** Moonraker answers either with the raw text or with { result: "text" | { content } }. */
function extractFileContent(responseText) {
  try {
    const json = JSON.parse(responseText);
    if (typeof json.result === "string") return json.result;
    if (json.result && typeof json.result === "object" && json.result.content) return json.result.content;
  } catch (e) {}
  return responseText;
}

/** Throws Moonraker's own message when the request failed. */
async function ensureOk(response) {
  if (!response.ok) throw new Error(await responseError(response));
  return response;
}

const postJson = async (url, body) => ensureOk(await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }));

const configFilesApi = {
  /** What is directly inside `folder`, hidden backups included: { folders, files } of { type, name, path, size, modified }. */
  async listDirectory(folder) {
    const response = await ensureOk(await fetchFresh("/server/files/directory?path=" + encodeURIComponent(configPath(folder))));
    const { result } = await response.json();
    return {
      folders: (result.dirs || []).map((dir) => ({ type: "folder", name: dir.dirname, path: joinPath(folder, dir.dirname), size: 0, modified: dir.modified })),
      files: (result.files || []).map((file) => ({ type: "file", name: file.filename, path: joinPath(folder, file.filename), size: file.size, modified: file.modified })),
    };
  },

  /** File text (served from the cache after the first read). */
  async read(path) {
    if (configFileCache.has(path)) return configFileCache.get(path);
    const encoded = encodeURIComponent(path);
    let response = await fetchFresh("/server/files/content?root=" + CONFIG_ROOT + "&path=" + encoded);
    if (!response.ok) response = await fetchFresh("/server/files/" + CONFIG_ROOT + "/" + encoded);
    if (!response.ok) throw new Error(tx("Cannot load ") + path);
    const content = extractFileContent(await response.text());
    configFileCache.set(path, content);
    return content;
  },

  /** Uploads `content` over `path` (in the config root, or `root`), trying the known Moonraker endpoints in turn. */
  async save(path, content, root = CONFIG_ROOT) {
    const slash = path.lastIndexOf("/");
    const directory = slash >= 0 ? path.slice(0, slash) : "";
    const form = new FormData();
    form.append("file", new Blob([content], { type: "text/plain" }), slash >= 0 ? path.slice(slash + 1) : path);
    form.append("root", root);
    if (directory) form.append("path", directory);
    const putText = (url) => fetch(url, { method: "PUT", body: content, headers: { "Content-Type": "text/plain" } });
    const attempts = [
      () => fetch("/server/files/upload", { method: "POST", body: form }),
      () => fetch("/machine/files/upload", { method: "POST", body: form }),
      () => putText("/server/files/" + root + "/" + encodeURIComponent(path)),
      () => putText("/server/files/content?root=" + root + "&path=" + encodeURIComponent(path)),
    ];
    let lastError = null;
    for (const attempt of attempts) {
      try {
        const response = await attempt();
        if (response.ok) {
          if (root === CONFIG_ROOT) configFileCache.set(path, content);
          return;
        }
        lastError = "HTTP " + response.status;
      } catch (error) {
        lastError = error.message;
      }
    }
    throw new Error(lastError || "404");
  },

  /** Puts `file` (a File, or a Blob plus `name`) into `folder`; an existing file of that name is replaced. */
  async upload(file, folder, name = file.name) {
    const form = new FormData();
    form.append("file", file, name);
    form.append("root", CONFIG_ROOT);
    if (folder) form.append("path", folder);
    await ensureOk(await fetch("/server/files/upload", { method: "POST", body: form }));
  },

  /** An empty file: Moonraker has no "create": nothing is uploaded under the new name. */
  createFile: (folder, name) => configFilesApi.upload(new Blob([""], { type: "text/plain" }), folder, name),

  createFolder: async (path) => void (await postJson("/server/files/directory", { path: configPath(path) })),

  /** Renames and moves are the same call: the new path says both the folder and the name. Works for folders too. */
  move: async (from, to) => void (await postJson("/server/files/move", { source: configPath(from), dest: configPath(to) })),

  async removeFile(path) {
    await ensureOk(await fetch(configFileUrl(path), { method: "DELETE" }));
  },

  /** The folder with everything inside it (without `force` Moonraker refuses a folder that is not empty). */
  async removeFolder(path) {
    await ensureOk(await fetch("/server/files/directory?path=" + encodeURIComponent(configPath(path)) + "&force=true", { method: "DELETE" }));
  },
};

/* ---------------------------------------------------------------------------
   Folder view
   ------------------------------------------------------------------------- */

/** The items of a listing that are shown by default (no backups, no hidden names), by name: the folders of the move dialog. */
const sortedVisible = (list) => list.filter((item) => !isBackupName(item.name) && !isHiddenName(item.name)).sort((a, b) => a.name.localeCompare(b.name));

/* ---- how the list is shown (1.39), kept on this device ---- */
const CONFIG_VIEW_KEY = "ke_cfg_view";
const CONFIG_SORTS = [
  { id: "name", label: tx("Name A→Z") },
  { id: "name-desc", label: tx("Name Z→A") },
  { id: "modified", label: tx("Last changed first") },
  { id: "modified-asc", label: tx("Oldest change first") },
  { id: "size", label: tx("Largest first") },
];
const configViewStore = (() => {
  const saved = storage.getJson(CONFIG_VIEW_KEY) || {};
  let view = { sort: CONFIG_SORTS.some((sort) => sort.id === saved.sort) ? saved.sort : "name", backups: saved.backups === true, hidden: saved.hidden === true };
  const listeners = new Set();
  return {
    snapshot: () => view,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    set(change) {
      view = { ...view, ...change };
      storage.set(CONFIG_VIEW_KEY, JSON.stringify(view));
      listeners.forEach((listener) => listener());
    },
  };
})();
const useConfigView = () => useSyncExternalStore(configViewStore.subscribe, configViewStore.snapshot);

/** `list` sorted as chosen (folders by name when sorted by size: they have none). */
function sortConfigItems(list, sort) {
  const byName = (a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" });
  const compare = {
    name: byName,
    "name-desc": (a, b) => byName(b, a),
    modified: (a, b) => (b.modified || 0) - (a.modified || 0) || byName(a, b),
    "modified-asc": (a, b) => (a.modified || 0) - (b.modified || 0) || byName(a, b),
    size: (a, b) => (b.size || 0) - (a.size || 0) || byName(a, b),
  }[sort] || byName;
  return [...list].sort(compare);
}

/** Folders (first) and files of a listing, as the view says, narrowed by the search box; `left` counts what is left out. */
function visibleItems(entries, query, view = { sort: "name", backups: false, hidden: false }) {
  if (!entries) return { items: [], left: { backups: 0, hidden: 0 } };
  const left = { backups: 0, hidden: 0 };
  const keep = (item) => {
    if (isHiddenName(item.name) && !view.hidden) {
      left.hidden += 1;
      return false;
    }
    if (isBackupName(item.name) && !view.backups) {
      left.backups += 1;
      return false;
    }
    return true;
  };
  const folders = sortConfigItems(entries.folders.filter(keep), view.sort === "size" ? "name" : view.sort);
  const files = sortConfigItems(entries.files.filter(keep), view.sort);
  const items = [...folders, ...files];
  const needle = query.trim().toLowerCase();
  return { items: needle ? items.filter((item) => item.name.toLowerCase().includes(needle) || item.path.toLowerCase().includes(needle)) : items, left };
}

/** Every name taken in a folder, the hidden ones too: a new name must not collide with those either. */
const takenNames = (entries) => new Set(entries ? [...entries.folders, ...entries.files].map((item) => item.name) : []);

/** What a listed folder or file looks like (app/20a-file-icons.js). */
const configFileKind = (item) => fileKind(item.name, { folder: item.type === "folder", image: item.type !== "folder" && isImagePath(item.name) });

/** Last listing of every folder visited: going back to one shows it at once, the fresh one replaces it a moment later. */
const directoryCache = new Map();

function useConfigFolder() {
  const [currentPath, setCurrentPath] = useState("");
  const [query, setQuery] = useState("");
  const [state, setState] = useState({ entries: null, loading: true, error: null });
  const latestRequest = useRef(0);
  const view = useConfigView();

  /** Shows `folder`. `quiet` keeps the list on screen while the new one arrives (after a change the user made). */
  const load = async (folder, { quiet = false } = {}) => {
    const request = ++latestRequest.current;
    const cached = directoryCache.get(folder);
    if (!quiet) setState({ entries: cached || null, loading: !cached, error: null });
    try {
      const entries = await configFilesApi.listDirectory(folder);
      directoryCache.set(folder, entries);
      if (request === latestRequest.current) setState({ entries, loading: false, error: null });
    } catch (error) {
      if (request === latestRequest.current) setState((previous) => ({ ...previous, loading: false, error: error.message || tx("Error loading the configuration") }));
    }
  };
  useEffect(() => {
    load(currentPath);
  }, [currentPath]);

  /** Forgets every cached listing and file text, then reads the folder again. */
  const reload = (options) => {
    directoryCache.clear();
    configFileCache.clear();
    return load(currentPath, options);
  };

  const shown = visibleItems(state.entries, query, view);
  return {
    ...state,
    currentPath,
    items: shown.items,
    left: shown.left,
    view,
    names: takenNames(state.entries),
    query,
    setQuery,
    openFolder: setCurrentPath,
    goRoot: () => setCurrentPath(""),
    goUp: () => setCurrentPath(parentPath),
    reload: () => reload(),
    refresh: () => reload({ quiet: true }),
  };
}
