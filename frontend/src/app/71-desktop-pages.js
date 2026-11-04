/* ============================================================================
   71 · DESKTOP PAGES
   The five pages of the wide layout, built from the same cards as the phone's:
     Dispositivo   camera and print progress on the left; heaters, fans,
                   movement (or Z-offset while printing) and extruder on the right
     Calibrazione  mesh next to the calibration macros and endstops
     File          the file tiles next to the selected file's details
     Config        the file manager next to the editor, which opens inside the page
     Sistema       host, firmware and updates | logs | AI monitor
   Every column scrolls on its own, so the top bar and the console bar stay put.
   ========================================================================== */

/* ---------------------------------------------------------------------------
   Dispositivo
   ------------------------------------------------------------------------- */

/**
 * The camera fills the space the other cards leave, but never more than its own shape needs (1.67: it used to stretch
 * to the column's height, so the picture sat small between two wide grey bands); the case light button sits on top of it.
 */
function CameraPanel() {
  const light = useCaseLight();
  const reloads = useCameraReloads();
  const [full, setFull] = useState(false);
  const camera = useCurrentCamera().current;
  const ratio = camera.ratio || 16 / 9;
  const shape = camera.rotation === 90 || camera.rotation === 270 ? 1 / ratio : ratio;
  return h(
    "div",
    { className: "desk-camera", style: { "--desk-cam-ratio": shape.toFixed(4) } },
    !full && h(CameraMedia, { className: "desk-camera__video", reloads }),
    h("span", { className: "desk-camera__tag" }, h("span", { className: "oui-dot desk-camera__live" }), "Camera"),
    h(CameraPicker, { className: "desk-camera__picker" }),
    h("div", { className: "desk-camera__light" }, light.available && h(LightButton, light), h(CameraFullscreenButton, { onOpen: () => setFull(true), className: "desk-camera__full" })),
    h(Presence, null, full && h(CameraFullscreen, { onClose: () => setFull(false) })),
  );
}

/** The preview of a file: its thumbnail, or a placeholder when it has none (or the image does not load). */
function PrintThumb({ src, className }) {
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [src]);
  const shown = !!src && !broken;
  return h(
    "div",
    { className: cx("desk-thumb", className) },
    shown ? h("img", { src, alt: "", draggable: false, onError: () => setBroken(true) }) : h(PrintPlaceholder),
  );
}

/**
 * The same figures and buttons as the phone's progress card, laid out in a row under the camera. 1.67: compact, so the
 * camera above it can be large: the six figures on one line, the buttons on one line, «More details» among them.
 */
function DesktopPrintCard({ status, controls, monitor }) {
  const [more, setMore] = useState(false);
  return h(
    Card,
    { className: "desk-print" },
    h(PrintThumb, { src: status.thumbnail, className: "desk-print__thumb" }),
    h(
      "div",
      { className: "desk-print__body" },
      h(
        "div",
        { className: "desk-print__top" },
        h("div", { className: "print-file desk-print__file" }, status.filename),
        h("span", { className: "oui-badge oui-badge--info print-pct" }, status.pct + "%"),
      ),
      h("div", { className: "oui-progress" }, h("div", { className: "oui-progress__bar", style: { width: status.pct + "%" } })),
      h(
        "div",
        { className: "desk-print__stats" },
        h(PrintStat, { label: tx("Time"), value: status.time }),
        h(PrintStat, { label: tx("Remaining"), value: status.remaining }),
        h(PrintStat, { label: "Layer", value: status.layer }),
        h(PrintLiveStats, { status, className: "desk-print__live" }),
      ),
      h(AiAlarmQuestion, { monitor }),
      h(
        "div",
        { className: "desk-print__actions" },
        h(
          "button",
          { type: "button", className: cx("oui-btn oui-btn--sm desk-print__more", more && "is-open"), "aria-expanded": more, "data-print-more": "1", onClick: () => setMore(!more) },
          tx("More details"),
          h(Icons.Chevron, { size: 14 }),
        ),
        h(GcodeViewButton, { status }),
        h(ExcludeObjectButton, { status }),
        h("span", { className: "desk-print__gap" }),
        h("button", { onClick: controls.togglePause, className: "oui-btn oui-btn--sm desk-print__pause" }, status.state === "paused" ? tx("Resume") : tx("Pause")),
        h("button", { onClick: controls.askCancel, className: "oui-btn oui-btn--sm oui-btn--danger-soft desk-print__cancel" }, tx("Cancel print")),
      ),
      more && h(PrintDetails, { status, open: true }),
    ),
  );
}

const LAST_PRINT_OUTCOME = { complete: tx("completed"), cancelled: tx("cancelled"), error: tx("stopped by an error") };

/** Shown when nothing prints: the last job Klipper remembers (1.67: with «Print again»), and the way to the file list. */
function IdlePrintCard({ status, onOpenFiles, onPrint }) {
  const outcome = LAST_PRINT_OUTCOME[status.state];
  const last = outcome && status.filename && status.filename !== "-";
  const again = last && status.filePath && onPrint;
  return h(
    Card,
    { className: "desk-print desk-print--idle" },
    last && h(PrintThumb, { src: status.thumbnail, className: "desk-print__thumb desk-print__thumb--small" }),
    h(
      "div",
      { className: "desk-print__body desk-print__body--idle" },
      h("div", { className: "oui-label" }, tx("Nothing printing")),
      last
        ? h(
            React.Fragment,
            null,
            h("div", { className: "print-file desk-print__file" }, tx("Last print: ") + status.filename),
            h("div", { className: "oui-caption" }, tx("Print ") + outcome + tx(" · duration ") + status.time),
          )
        : h("div", { className: "oui-caption" }, tx("Choose a file from the list to start it")),
    ),
    h(
      "div",
      { className: "desk-print__ctas" },
      again &&
        h(
          "button",
          { type: "button", className: "oui-btn oui-btn--primary desk-print__again", "data-print-again": status.filePath, onClick: () => onPrint({ path: status.filePath, fileName: status.filename, thumbnail: status.thumbnail }) },
          h(Icons.Play, { size: 16 }),
          tx("Print again"),
        ),
      h("button", { onClick: onOpenFiles, className: cx("oui-btn desk-print__cta", !again && "oui-btn--primary") }, h(Icons.Folder, { size: 18 }), tx("Choose a file to print")),
    ),
  );
}

/** The phone's heaters-and-fans card in two: on a wide screen the fans (tall) must not push the movement controls out of view. */
function DesktopHeatersCard({ hotend, bed, onEditTemperature }) {
  return h(
    Card,
    { cardId: "heaters" },
    h(CardHeader, { title: tx("Heaters") }),
    h(
      "div",
      { className: "grid grid-cols-2 heater-tiles heater-tiles--last" },
      h(HeaterTile, { kind: "hotend", heater: hotend, onEdit: () => onEditTemperature("hotend", hotend.target) }),
      h(HeaterTile, { kind: "bed", heater: bed, onEdit: () => onEditTemperature("bed", bed.target) }),
    ),
  );
}

function DesktopFansCard() {
  return h(Card, { cardId: "fans" }, h(CardHeader, { title: tx("Fans") }), h(FanList));
}

/**
 * Left: camera, progress. Right: heaters, what moves the machine, fans, extruder, tune (1.32); 1.66: in the
 * order (and with the cards) of the computer's layout, Settings → Appearance → Cards. While a job prints the
 * Z-offset card takes the movement card's place and the extruder is out of the way (a pause leaves both in view).
 * On a narrow wide-screen the four slots stack in that order; on an extra-wide one they form two columns (css/70).
 */
function DesktopDevicePage({ printStatus, printControls, status, capabilities, motion, bedTools, zOffset, lockReason, aiMonitor, onEditTemperature, onGcode, onNavigate, onPrint }) {
  const placement = zOffsetPlacement(printStatus, status.zOffset);
  useLayout(); // 1.66: the computer's own layout (Settings → Appearance → Cards)
  const main = {
    camera: h(CameraPanel),
    // 1.67: no AI strip above it any more: the AI badge at the top says the same, and opens the same panel
    print: printStatus.printing ? h(DesktopPrintCard, { status: printStatus, controls: printControls, monitor: aiMonitor }) : h(IdlePrintCard, { status: printStatus, onOpenFiles: () => onNavigate("files"), onPrint }),
    temps: h(TemperatureCard, { onEditTemperature }),
  };
  const side = {
    heaters: h(DesktopHeatersCard, { hotend: status.hotend, bed: status.bed, onEditTemperature }),
    motion: h(
      React.Fragment,
      null,
      placement && h(ZOffsetCard, { zOffset, printing: placement === "instead" }),
      placement !== "instead" && h(MovementCard, { position: status.position, homedAxes: status.homedAxes, motion, bedTools, lockReason }),
    ),
    fans: h(DesktopFansCard),
    spool: h(SpoolCard),
    devices: h(DevicesCard),
    extruder: printStatus.state !== "printing" && h(ExtruderCard, { hotend: status.hotend, onGcode, onEditTemperature }), // out of the way while a job prints
    tune: h(TuneCard, { capabilities, onGcode }),
  };
  const cards = { ...main, ...side }; // any card can go in either column (Settings → Appearance → Cards)
  const sideIds = layoutStore.shown("home", "side");
  const slot = (id) => cards[id] && h("div", { key: id, className: "desk-slot desk-slot--" + id }, cards[id]);
  // extra wide: the side column in two (css/70), the first half and the second
  const half = Math.ceil(sideIds.length / 2);
  return h(
    "div",
    { className: "desk-device" },
    h("section", { className: "desk-device__main" }, arrangeCards("home", cards, "main")),
    h("aside", { className: "desk-side" }, h("div", { className: "desk-side__group" }, sideIds.slice(0, half).map(slot)), h("div", { className: "desk-side__group" }, sideIds.slice(half).map(slot))),
  );
}

/* ---------------------------------------------------------------------------
   Calibrazione
   ------------------------------------------------------------------------- */
function DesktopCalibrationPage({ capabilities, lockReason, homedAxes, printState, onGcode, onMacroSettings }) {
  useLayout(); // 1.66: the computer's own layout
  const cards = {
    bedmesh: h(BedMeshCard, { onGcode, lockReason, homedAxes }),
    macros: h(MacroCards, { printState, onGcode, onSettings: onMacroSettings }),
    endstops: h(EndstopsCard, { capabilities, lockReason }),
  };
  return h("div", { className: "desk-split" }, h("div", { className: "desk-col" }, arrangeCards("control", cards, "left")), h("div", { className: "desk-col" }, arrangeCards("control", cards, "right")));
}

/* ---------------------------------------------------------------------------
   File
   ------------------------------------------------------------------------- */
function FileFact({ label, value }) {
  return h("div", { className: "oui-tile desk-fact" }, h("div", { className: "oui-caption" }, label), h("div", { className: "desk-fact__value" }, value));
}

/** The file selected in the list: preview, figures from its metadata, and what can be done with it. */
function FileDetail({ file, list, fileActions, onPrint }) {
  const fileName = file.path.split("/").pop();
  const known = list.meta[file.path];
  const haveMeta = !!known && Object.keys(known).length > 0;
  const [fetched, setFetched] = useState(null); // files beyond the newest ones have no metadata in the list yet

  useEffect(() => {
    setFetched(null);
    if (haveMeta) return undefined;
    let cancelled = false;
    fetchFileMetadata(file.path).then((meta) => !cancelled && setFetched(meta));
    return () => {
      cancelled = true;
    };
  }, [file.path, file.modified, haveMeta]);

  const meta = (haveMeta ? known : fetched) || {};
  const thumbnail = list.thumbs[file.path] || (fetched ? largestThumbnailUrl(fetched) : null);
  const item = { file, fileName, meta, thumbnail };
  const queue = useJobQueue();
  const chips = [meta.filament_type, meta.layer_height ? meta.layer_height + " mm" : "", meta.object_height ? "h " + Math.round(meta.object_height) + " mm" : ""].filter(Boolean);

  return h(
    Card,
    { className: "desk-detail" },
    h(PrintThumb, { src: thumbnail, className: "desk-detail__preview" }),
    h("div", { className: "desk-detail__name" }, fileName),
    chips.length > 0 && h("div", { className: "desk-detail__chips" }, chips.map((chip) => h("span", { key: chip, className: "oui-badge oui-badge--info" }, chip))),
    h(
      "div",
      { className: "desk-detail__facts" },
      h(FileFact, { label: tx("Estimated time"), value: formatEstimatedTime(meta.estimated_time || 0) }),
      h(FileFact, { label: tx("Filament"), value: formatFilamentWeight(meta) }),
      h(FileFact, { label: tx("Size"), value: formatBytes(file.size) || "--" }),
      h(FileFact, { label: tx("Modified"), value: formatFileDate(file.modified) || "--" }),
    ),
    h("button", { className: "oui-btn oui-btn--primary oui-btn--block desk-detail__print", onClick: () => onPrint({ path: file.path, fileName, thumbnail }) }, h(Icons.Play, { size: 18 }), tx("Start print")),
    h(
      "div",
      { className: "desk-detail__actions" },
      h("button", { className: "oui-btn oui-btn--sm", title: tx("Save a copy on this device"), onClick: () => downloadFile("/server/files/" + GCODES_ROOT + "/" + encodeRemotePath(file.path), fileName) }, h(Icons.Download, { size: 16 }), tx("Download")),
      h("button", { className: "oui-btn oui-btn--sm", onClick: () => fileActions.openDetailsItem(item) }, h(Icons.Info, { size: 16 }), tx("Details")),
      queue.available && h("button", { className: "oui-btn oui-btn--sm desk-detail__queue", onClick: () => fileActions.openQueueItem(item) }, h(Icons.Queue, { size: 16 }), tx("Queue")),
      h("button", { className: "oui-btn oui-btn--sm desk-detail__layers", onClick: () => gcodeViewerStore.open(file.path) }, h(Icons.Layers, { size: 16 }), tx("Layers")),
      h("button", { className: "oui-btn oui-btn--sm", onClick: () => fileActions.openItemInEditor(item) }, h(Icons.Code, { size: 16 }), "Editor"),
      h("button", { className: "oui-btn oui-btn--sm oui-btn--danger-soft", onClick: () => fileActions.askDeleteItem(item) }, h(Icons.Trash, { size: 16 }), tx("Delete")),
    ),
  );
}

function DesktopFilesPage({ list, onPrint, fileActions }) {
  const [selectedPath, setSelectedPath] = useState(null);
  const view = useGcodeView();
  const shown = orderedFiles(list, view);
  // the first file shown until the reader picks one (and again if the picked file is gone, deleted for instance)
  const current = shown.find((file) => file.path === selectedPath) || shown[0] || null;
  return h(
    "div",
    { className: "desk-split desk-split--files" },
    h("div", { className: "desk-col desk-col--files" }, h(FilesCard, { list, onPrint, onMenu: fileActions.openMenu, selectedPath: current && current.path, onSelect: setSelectedPath })),
    h("div", { className: "desk-col" }, current ? h(FileDetail, { key: current.path, file: current, list, fileActions, onPrint }) : null),
  );
}

/* ---------------------------------------------------------------------------
   Config
   ------------------------------------------------------------------------- */

/** `editor` is the TextEditor element (inline); `editing` says whether a file is open in it. */
function DesktopConfigPage({ onEditFile, onViewImage, editor, editing }) {
  return h(
    "div",
    { className: "desk-split desk-split--config" },
    h("div", { className: "desk-col" }, h(ConfigFilesCard, { onEditFile, onViewImage })),
    h(
      "div",
      { className: "desk-editor" },
      editing
        ? editor
        : h(
            "div",
            { className: "desk-empty" },
            h(Icons.Code, { size: 30 }),
            h("div", { className: "oui-label" }, tx("Choose a configuration file")),
            h("div", { className: "oui-caption" }, tx("It opens here, ready to edit. Pictures open full screen.")),
          ),
    ),
  );
}

/* ---------------------------------------------------------------------------
   Sistema
   ------------------------------------------------------------------------- */
function DesktopSystemPage({ controller, aiMonitor, onEditFile }) {
  const { data, reload, checkForUpdates } = useSystemData();
  return h(
    "div",
    { className: "desk-system" },
    h(
      "div",
      { className: "desk-col" },
      data
        ? h(
            React.Fragment,
            null,
            h(HostCard, { data, onRefresh: reload }),
            h(McuCard, { data }),
            h(UpdatesCard, { data, controller, onCheck: checkForUpdates }),
          )
        : h(LoadingCard, { label: tx("System"), text: tx("Loading...") }),
    ),
    h("div", { className: "desk-col" }, h(LogsCard, { onEditFile })),
  );
}
