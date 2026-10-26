/* ============================================================================
   50b · CONFIG FILES — card
   The "File di configurazione" card: search, folder navigation and the list of
   folders and files. Tapping a row opens it; its ⋯ button, a long press or a
   right click open the row's menu. Data: 50, operations and dialogs: 50a.
   ========================================================================== */

function ConfigFileRow({ item, manager }) {
  const { dnd } = manager;
  const press = useLongPress(() => manager.openMenu(item));
  const isFolder = item.type === "folder";
  const dropKey = "folder:" + item.path;
  return h(
    "div",
    {
      className: cx("cfg-row", dnd.dragging && dnd.dragging.path === item.path && "is-dragging", isFolder && dnd.isOver(dropKey) && "is-drop-target"),
      ...press,
      ...dnd.rowDrag(item),
      ...(isFolder ? dnd.dropTarget(item.path, dropKey) : null),
    },
    h(
      "button",
      { className: "cfg-row__main", onClick: () => manager.openItem(item) },
      h(FileGlyph, { kind: configFileKind(item) }),
      h(
        "span",
        { className: "cfg-row__text" },
        h("span", { className: "cfg-row__name" }, item.name),
        h("span", { className: "cfg-row__meta" }, !isFolder && formatBytes(item.size) && h("span", null, formatBytes(item.size)), formatFileDate(item.modified) && h("span", null, formatFileDate(item.modified)), isFolder && h("span", null, "cartella")),
      ),
    ),
    h("button", { className: "cfg-row__more", title: "Azioni", "aria-label": "Azioni per " + item.name, onClick: () => manager.openMenu(item) }, h(Icons.Dots, { size: 20 })),
  );
}

/** `onEditFile(path, content)` opens the editor; `onViewImage(path)` the viewer. */
function ConfigFilesCard({ onEditFile, onViewImage }) {
  const folder = useConfigFolder();

  const open = async (item) => {
    if (item.type === "folder") return folder.openFolder(item.path);
    if (isImagePath(item.path)) return onViewImage(item.path);
    try {
      onEditFile(item.path, await configFilesApi.read(item.path));
    } catch (error) {
      toast.action("Errore caricamento " + item.path + ": " + (error.message || ""));
    }
  };
  const manager = useConfigFileManager(folder, open);
  const { dnd } = manager;

  let body;
  if (folder.error)
    body = h("div", { className: "oui-tile oui-tile--danger" }, h("div", { className: "oui-notice mb-2" }, folder.error), h("button", { onClick: folder.reload, className: "oui-btn oui-btn--sm" }, "Riprova"));
  else if (folder.loading) body = h("div", { className: "oui-notice" }, "Caricamento /config...");
  else if (folder.items.length === 0) body = h("div", { className: "oui-notice" }, folder.query.trim() ? "Nessun risultato" : folder.currentPath ? "Cartella vuota" : "Nessun file in /config");
  else body = h("div", { className: "oui-list" }, folder.items.map((item) => h(ConfigFileRow, { key: item.path, item, manager })));

  return h(
    Card,
    { className: cx("cfg-card", dnd.filesOver && "is-drop-files", dnd.dragging && "is-row-drag"), ...dnd.dropZone },
    h(
      CardHeader,
      { title: "File di configurazione" },
      h(
        "div",
        { className: "cfg-head-actions" },
        h(ConfigNewMenuButton, { manager }),
        h("button", { onClick: folder.reload, title: "Aggiorna", "aria-label": "Aggiorna", className: "oui-btn oui-btn--sm oui-btn--icon" }, h(Icons.Refresh, { size: 18 })),
      ),
    ),
    h(
      "div",
      { className: "cfg-toolbar" },
      h("input", { type: "text", value: folder.query, onChange: (e) => folder.setQuery(e.target.value), placeholder: "Cerca...", className: "oui-field cfg-toolbar__search" }),
      h("button", { onClick: folder.goRoot, title: "Cartella principale", className: cx("oui-chip", dnd.isOver("chip:root") && "is-drop-target"), ...dnd.dropTarget("", "chip:root") }, "/"),
      h("button", { onClick: folder.goUp, title: "Cartella superiore", className: cx("oui-chip", dnd.isOver("chip:up") && "is-drop-target"), ...dnd.dropTarget(parentPath(folder.currentPath), "chip:up") }, ".."),
    ),
    folder.currentPath && h("div", { className: "cfg-path oui-mono" }, "/" + folder.currentPath),
    body,
    dnd.filesOver && h("div", { className: "cfg-dropzone" }, h(Icons.Upload, { size: 28 }), h("span", null, "Rilascia per caricare in " + showPath(folder.currentPath))),
    h("input", manager.fileInput),
    h(ConfigManagerDialogs, { manager }),
  );
}
