/* ============================================================================
   51a · EARLIER VERSIONS OF A CONFIG FILE (1.81)
   Before the editor writes a file of the config folder over, the KlippEye
   service keeps the text it had (backend/config_versions.py, the last 30).
   For printer.cfg also Klipper's own backups (printer-YYYYMMDD_HHMMSS.cfg,
   written by SAVE_CONFIG). The «Versions» button of the editor lists them,
   shows what is different from the text in the editor, and puts one back in
   the editor: nothing is written until Save is pressed (and Undo takes it back).
   ========================================================================== */

const KLIPPER_BACKUP_NAME = /^printer-(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.cfg$/;
const DIFF_CONTEXT = 2;
const DIFF_MAX_CELLS = 4000000; // beyond this (two long, very different texts) the middle is shown as all changed

const configVersionsApi = {
  /** Keeps `content` as the version of `path` before a save. Never stops the save: an older service simply has no versions. */
  async keep(path, content) {
    try {
      await fetch("/api/config/versions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path, content, reason: "save" }) });
    } catch (error) {}
  },
  async list(path) {
    const response = await fetchFresh("/api/config/versions?path=" + encodeURIComponent(path));
    if (response.status === 404) return [];
    if (!response.ok) throw new Error(await responseError(response));
    return (await response.json()).versions || [];
  },
  async read(path, id) {
    const response = await fetchFresh("/api/config/versions/" + encodeURIComponent(id) + "?path=" + encodeURIComponent(path));
    if (!response.ok) throw new Error(await responseError(response));
    return (await response.json()).content;
  },
};

/** Klipper's backups of printer.cfg, next to it (only for the file called printer.cfg): [{ path, time }], newest first. */
async function klipperBackupsOf(path) {
  const slash = path.lastIndexOf("/");
  if (path.slice(slash + 1) !== "printer.cfg") return [];
  const folder = slash >= 0 ? path.slice(0, slash) : "";
  const { files } = await configFilesApi.listDirectory(folder);
  return files
    .map((file) => {
      const match = KLIPPER_BACKUP_NAME.exec(file.name);
      return match ? { path: file.path, name: file.name, time: new Date(+match[1], +match[2] - 1, +match[3], +match[4], +match[5], +match[6]).getTime() / 1000 } : null;
    })
    .filter(Boolean)
    .sort((a, b) => b.time - a.time);
}

/**
 * The lines of `before` and `after` as a list of { kind: "same" | "del" | "add", text, a, b } (a / b: the line's number
 * in each text). The lines the two share at the start and at the end are matched first, the rest by longest common
 * subsequence.
 */
function lineDiff(before, after) {
  const a = before.split("\n");
  const b = after.split("\n");
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let endA = a.length;
  let endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
    endA--;
    endB--;
  }
  const out = [];
  for (let i = 0; i < start; i++) out.push({ kind: "same", text: a[i], a: i + 1, b: i + 1 });
  const n = endA - start;
  const m = endB - start;
  if (n * m > DIFF_MAX_CELLS) {
    for (let i = start; i < endA; i++) out.push({ kind: "del", text: a[i], a: i + 1 });
    for (let j = start; j < endB; j++) out.push({ kind: "add", text: b[j], b: j + 1 });
  } else {
    // lengths of the common subsequences of the tails, then a walk from the top
    const table = new Uint32Array((n + 1) * (m + 1));
    const at = (i, j) => i * (m + 1) + j;
    for (let i = n - 1; i >= 0; i--)
      for (let j = m - 1; j >= 0; j--) table[at(i, j)] = a[start + i] === b[start + j] ? table[at(i + 1, j + 1)] + 1 : Math.max(table[at(i + 1, j)], table[at(i, j + 1)]);
    let i = 0;
    let j = 0;
    while (i < n || j < m) {
      if (i < n && j < m && a[start + i] === b[start + j]) {
        out.push({ kind: "same", text: a[start + i], a: start + i + 1, b: start + j + 1 });
        i++;
        j++;
      } else if (j < m && (i === n || table[at(i, j + 1)] >= table[at(i + 1, j)])) {
        out.push({ kind: "add", text: b[start + j], b: start + j + 1 });
        j++;
      } else {
        out.push({ kind: "del", text: a[start + i], a: start + i + 1 });
        i++;
      }
    }
  }
  for (let i = endA, j = endB; i < a.length; i++, j++) out.push({ kind: "same", text: a[i], a: i + 1, b: j + 1 });
  return out;
}

/** The changed lines with DIFF_CONTEXT lines around them, in hunks; and how many lines were removed and added. */
function diffHunks(lines) {
  const keep = new Array(lines.length).fill(false);
  lines.forEach((line, index) => {
    if (line.kind === "same") return;
    for (let k = Math.max(0, index - DIFF_CONTEXT); k <= Math.min(lines.length - 1, index + DIFF_CONTEXT); k++) keep[k] = true;
  });
  const hunks = [];
  let current = null;
  lines.forEach((line, index) => {
    if (!keep[index]) return (current = null);
    if (!current) hunks.push((current = []));
    current.push(line);
  });
  return { hunks, removed: lines.filter((l) => l.kind === "del").length, added: lines.filter((l) => l.kind === "add").length };
}

const versionDate = (seconds) => new Date(seconds * 1000).toLocaleString(LOCALE, { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });

/**
 * The versions of `path`: a list, and for the one chosen what putting it back would change in the text in the editor
 * (`current`): the lines that would go (−) and those that would come back (+).
 */
function ConfigVersionsDialog({ path, current, onRestore, onClose }) {
  useBackHandler(onClose, true);
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState(null);
  const [chosen, setChosen] = useState(null); // { entry, content } or { entry, loading }
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [kept, backups] = await Promise.all([configVersionsApi.list(path).catch((problem) => (setError(problem.message || String(problem)), [])), klipperBackupsOf(path).catch(() => [])]);
      const list = kept
        .map((version) => ({ key: "v" + version.id, kind: "kept", time: version.time, version }))
        .concat(backups.map((backup) => ({ key: "k" + backup.path, kind: "klipper", time: backup.time, backup })))
        .sort((a, b) => b.time - a.time);
      if (!cancelled) setEntries(list);
    })();
    return () => {
      cancelled = true;
    };
  }, [path]);
  const choose = async (entry) => {
    setChosen({ entry, loading: true });
    try {
      const content = entry.kind === "kept" ? await configVersionsApi.read(path, entry.version.id) : await configFilesApi.read(entry.backup.path);
      setChosen({ entry, content });
    } catch (problem) {
      setChosen({ entry, error: problem.message || String(problem) });
    }
  };
  const diff = useMemo(() => (chosen && typeof chosen.content === "string" ? diffHunks(lineDiff(current, chosen.content)) : null), [chosen, current]);
  const label = (entry) => (entry.kind === "kept" ? tx("Before a save from here") : tx("Klipper's backup (SAVE_CONFIG)"));

  return h(
    "div",
    { className: "confirm-overlay", style: { zIndex: 10002 }, onClick: (event) => event.target === event.currentTarget && onClose() },
    h(
      "div",
      { className: "confirm-card cfg-versions", role: "dialog", "aria-label": tx("Earlier versions") },
      h("div", { className: "dialog-head" }, h("div", { className: "dialog-head__icon" }, h(Icons.Clock, { size: 22 })), h("div", null, h("div", { className: "dialog-title" }, tx("Earlier versions")), h("div", { className: "dialog-sub" }, path))),
      !chosen &&
        h(
          React.Fragment,
          null,
          h("div", { className: "dialog-text" }, tx("The text the file had before each save from KlippEye (the last 30), and for printer.cfg Klipper's backups. Choose one to see what is different.")),
          entries === null && h("div", { className: "oui-caption" }, tx("Loading...")),
          error && h("div", { className: "oui-caption" }, error),
          entries &&
            entries.length === 0 &&
            h("div", { className: "oui-caption cfg-versions__empty", "data-versions-empty": "1" }, tx("No earlier version yet: one is kept at each save from here.")),
          entries &&
            entries.length > 0 &&
            h(
              "div",
              { className: "oui-list cfg-versions__list" },
              entries.map((entry) =>
                h(
                  "button",
                  { key: entry.key, type: "button", className: "cfg-versions__row", "data-version": entry.kind, onClick: () => choose(entry) },
                  h("span", { className: "cfg-versions__date" }, versionDate(entry.time)),
                  h("span", { className: "cfg-versions__what" }, label(entry) + (entry.kind === "kept" ? " · " + tx("{count} lines", { count: entry.version.lines }) : "")),
                  h(Icons.Chevron, { size: 16, className: "cfg-versions__go" }),
                ),
              ),
            ),
          h("div", { className: "oui-btn-row" }, h("button", { type: "button", className: "oui-btn", onClick: onClose }, tx("Close"))),
        ),
      chosen &&
        h(
          React.Fragment,
          null,
          h("div", { className: "cfg-versions__chosen" }, h("strong", null, versionDate(chosen.entry.time)), " · ", label(chosen.entry)),
          chosen.loading && h("div", { className: "oui-caption" }, tx("Loading...")),
          chosen.error && h("div", { className: "oui-caption" }, chosen.error),
          diff &&
            (diff.hunks.length === 0
              ? h("div", { className: "oui-caption", "data-diff-same": "1" }, tx("Same as the text in the editor."))
              : h(
                  React.Fragment,
                  null,
                  h("div", { className: "oui-caption cfg-versions__sum", "data-diff-sum": diff.removed + "-" + diff.added }, tx("Putting it back: −{removed} / +{added} lines.", { removed: diff.removed, added: diff.added })),
                  h(
                    "div",
                    { className: "cfg-diff" },
                    diff.hunks.map((hunk, index) =>
                      h(
                        "div",
                        { key: index, className: "cfg-diff__hunk" },
                        hunk.map((line, k) =>
                          h("div", { key: k, className: "cfg-diff__line cfg-diff__line--" + line.kind }, h("span", { className: "cfg-diff__num" }, line.kind === "add" ? "" : line.a), h("span", { className: "cfg-diff__mark" }, line.kind === "del" ? "−" : line.kind === "add" ? "+" : " "), h("span", { className: "cfg-diff__text" }, line.text || " ")),
                        ),
                      ),
                    ),
                  ),
                )),
          h(
            "div",
            { className: "oui-btn-row" },
            h("button", { type: "button", className: "oui-btn", onClick: () => setChosen(null) }, tx("Back")),
            h("button", { type: "button", className: "oui-btn oui-btn--primary", "data-version-restore": "1", disabled: !diff || diff.hunks.length === 0, onClick: () => onRestore(chosen.content) }, tx("Put back in the editor")),
          ),
        ),
    ),
  );
}
