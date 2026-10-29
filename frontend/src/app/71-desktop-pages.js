/* ============================================================================
   71 · DESKTOP PAGES
   The five pages of the wide layout, built from the same cards as the phone's:
     Dispositivo   camera, AI strip and print progress on the left; heaters, fans,
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

/** The camera fills the space the other cards leave; the case light button sits on top of it. */
function CameraPanel() {
  const light = useCaseLight();
  const reloads = useCameraReloads();
  return h(
    "div",
    { className: "desk-camera" },
    h(CameraMedia, { className: "desk-camera__video", reloads }),
    h("span", { className: "desk-camera__tag" }, h("span", { className: "oui-dot desk-camera__live" }), "Camera"),
    light.available && h("div", { className: "desk-camera__light" }, h(LightButton, light)),
  );
}

function AiChip({ label, value, minor }) {
  return h("span", { className: cx("desk-ai__chip", minor && "desk-ai__chip--minor") }, h("span", { className: "desk-ai__chip-label" }, label), h("b", null, value));
}

/** One line with what the AI monitor sees; a click opens its full card (on the System page). */
function AiStrip({ monitor, onOpen }) {
  const { detector, latest } = monitor;
  const action = aiAction(latest && latest.verdict ? latest.verdict.action : "");
  const advice = action && action !== "CONTINUE" ? action : "";
  return h(
    "button",
    { className: "desk-ai", onClick: onOpen, title: tx("Open the AI monitoring details") },
    h("span", { className: "desk-ai__title" }, tx("AI monitoring")),
    h(
      "span",
      { className: cx(DETECTOR_PILLS[detector.pill.tone], "desk-ai__pill") },
      detector.dot !== "idle" && h("span", { className: cx("oui-dot", detector.dot === "active" && "ai-dot--pulse") }),
      detector.pill.text,
    ),
    h("span", { className: "desk-ai__spacer" }),
    advice && h("span", { className: cx("oui-badge", advice === "CANCEL" ? "oui-badge--danger" : "oui-badge--warn") }, tx("Suggested action: ") + aiActionLabel(advice)),
    h(AiChip, { label: tx("Status"), value: detector.state }),
    h(AiChip, { label: "OpenCV", value: detector.score, minor: true }),
    h(AiChip, { label: "Checks", value: detector.checks, minor: true }),
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

/** The same figures and buttons as the phone's progress card, laid out in a row under the camera. */
function DesktopPrintCard({ status, controls }) {
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
      ),
      h(
        "div",
        { className: "oui-btn-row" },
        h("button", { onClick: controls.togglePause, className: "oui-btn" }, status.state === "paused" ? tx("Resume") : tx("Pause")),
        h("button", { onClick: controls.askCancel, className: "oui-btn oui-btn--danger-soft" }, tx("Cancel print")),
      ),
    ),
  );
}

const LAST_PRINT_OUTCOME = { complete: tx("completed"), cancelled: tx("cancelled"), error: tx("stopped by an error") };

/** Shown when nothing prints: the last job Klipper remembers, and the way to the file list. */
function IdlePrintCard({ status, onOpenFiles }) {
  const outcome = LAST_PRINT_OUTCOME[status.state];
  const last = outcome && status.filename && status.filename !== "-";
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
    h("button", { onClick: onOpenFiles, className: "oui-btn oui-btn--primary desk-print__cta" }, h(Icons.Folder, { size: 18 }), tx("Choose a file to print")),
  );
}

/** The phone's heaters-and-fans card in two: on a wide screen the fans (tall) must not push the movement controls out of view. */
function DesktopHeatersCard({ hotend, bed, onEditTemperature }) {
  return h(
    Card,
    null,
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
  return h(Card, null, h(CardHeader, { title: tx("Fans") }), h(FanList));
}

/**
 * Left: camera, AI strip, progress. Right: heaters, what moves the machine, fans, extruder. While a job prints the
 * Z-offset card takes the movement card's place and the extruder is out of the way (a pause leaves both in view).
 * On a narrow wide-screen the four slots stack in that order; on an extra-wide one they form two columns (css/70).
 */
function DesktopDevicePage({ printStatus, printControls, status, motion, bedTools, zOffset, lockReason, aiMonitor, onEditTemperature, onGcode, onNavigate }) {
  const placement = zOffsetPlacement(printStatus, status.zOffset);
  return h(
    "div",
    { className: "desk-device" },
    h(
      "section",
      { className: "desk-device__main" },
      h(CameraPanel),
      h(AiStrip, { monitor: aiMonitor, onOpen: () => onNavigate("sistema") }),
      printStatus.printing ? h(DesktopPrintCard, { status: printStatus, controls: printControls }) : h(IdlePrintCard, { status: printStatus, onOpenFiles: () => onNavigate("files") }),
    ),
    h(
      "aside",
      { className: "desk-side" },
      h(
        "div",
        { className: "desk-side__group" },
        h("div", { className: "desk-slot desk-slot--heaters" }, h(DesktopHeatersCard, { hotend: status.hotend, bed: status.bed, onEditTemperature })),
        h("div", { className: "desk-slot desk-slot--fans" }, h(DesktopFansCard)),
      ),
      h(
        "div",
        { className: "desk-side__group" },
        h(
          "div",
          { className: "desk-slot desk-slot--motion" },
          placement && h(ZOffsetCard, { zOffset, printing: placement === "instead" }),
          placement !== "instead" && h(MovementCard, { position: status.position, homedAxes: status.homedAxes, motion, bedTools, lockReason }),
        ),
        printStatus.state !== "printing" && h("div", { className: "desk-slot desk-slot--extruder" }, h(ExtruderCard, { hotend: status.hotend, onGcode, onEditTemperature })),
      ),
    ),
  );
}

/* ---------------------------------------------------------------------------
   Calibrazione
   ------------------------------------------------------------------------- */
function DesktopCalibrationPage({ capabilities, lockReason, onGcode }) {
  return h(
    "div",
    { className: "desk-split" },
    h("div", { className: "desk-col" }, h(BedMeshCard, { onGcode })),
    h("div", { className: "desk-col" }, h(CalibrationCard, { onGcode, capabilities, lockReason })),
  );
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
      h("button", { className: "oui-btn oui-btn--sm", onClick: () => fileActions.openItemInEditor(item) }, h(Icons.Code, { size: 16 }), "Editor"),
      h("button", { className: "oui-btn oui-btn--sm oui-btn--danger-soft", onClick: () => fileActions.askDeleteItem(item) }, h(Icons.Trash, { size: 16 }), tx("Delete")),
    ),
  );
}

function DesktopFilesPage({ list, onPrint, fileActions }) {
  const [selectedPath, setSelectedPath] = useState(null);
  // the first file until the reader picks one (and again if the picked file is gone, deleted for instance)
  const current = list.files.find((file) => file.path === selectedPath) || list.files[0] || null;
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
    h("div", { className: "desk-col" }, h(AiMonitorCard, { monitor: aiMonitor })),
  );
}
