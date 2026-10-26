/* ============================================================================
   99 · APPLICATION
   Wires state and behaviour together and lays out the five tabs.
   ========================================================================== */

function startPrint(job) {
  fetch("/printer/print/start", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ filename: job.path }) }).catch(noop);
}

/** The Z-offset card takes the Movement card's place while a job prints, and sits above it once the job is over while an offset is left to save. */
function HomePage({ printStatus, printControls, status, motion, bedTools, zOffset, lockReason, onEditTemperature }) {
  const placement = zOffsetPlacement(printStatus, status.zOffset);
  const zOffsetCard = placement && h("div", { className: "md:col-span-2" }, h(ZOffsetCard, { zOffset, printing: placement === "instead" }));
  return h(
    "div",
    { className: "grid grid-cols-1 md:grid-cols-2" },
    printStatus.printing && h(PrintProgressCard, { status: printStatus, controls: printControls }),
    h("div", { className: "md:col-span-2" }, h(CameraCard)),
    h("div", { className: "md:col-span-2" }, h(HeatersFansCard, { hotend: status.hotend, bed: status.bed, onEditTemperature })),
    zOffsetCard,
    placement !== "instead" && h("div", { className: "md:col-span-2" }, h(MovementCard, { position: status.position, homedAxes: status.homedAxes, motion, bedTools, lockReason })),
  );
}

function ControlPage({ entries, status, capabilities, lockReason, onGcode, onEditTemperature }) {
  return h(
    "div",
    { className: "grid grid-cols-1" },
    h(ConsoleCard, { entries }),
    h(ExtruderCard, { hotend: status.hotend, onGcode, onEditTemperature }),
    h(CalibrationCard, { onGcode, capabilities, lockReason }),
    h(BedMeshCard, { onGcode }),
  );
}

function ConfigPage({ aiMonitor, onEditFile, onViewImage }) {
  return h("div", { className: "grid grid-cols-1" }, h(ConfigFilesCard, { onEditFile, onViewImage }), h(AiMonitorCard, { monitor: aiMonitor }), h(LogsCard, { onEditFile }));
}

const TAB_TITLES = { home: "Home", controllo: "Controllo", files: "Files", config: "Config", sistema: "Sistema" };

function App() {
  const [tab, setTab] = useState(() => {
    const saved = storage.get(STORAGE_KEYS.currentTab);
    return TAB_IDS.includes(saved) ? saved : "home";
  });
  const [printJob, setPrintJob] = useState(null);
  const [editorSession, setEditorSession] = useState(null); // { path, content, token } while a file is open
  const [imagePath, setImagePath] = useState(null);

  const status = usePrinterStatus();
  const klipper = useKlipperState();
  const consoleFeed = useConsoleFeed(klipper.evaluateConsoleStore);
  const printStatus = usePrintStatus();
  const printControls = usePrintControls(printStatus.state);
  const saveConfig = useSaveConfig(klipper.expectRestart);
  const power = usePowerMenu({ klipper, printing: printStatus.printing });
  const settingsMenu = useSettingsMenu();
  useSettingsSync();
  usePrinterIdentity();
  const temperature = useTemperatureDialog();
  const motion = useMotion(consoleFeed.echo);
  const capabilities = usePrinterCapabilities();
  const lockReason = printLockReason(printStatus);
  const zOffset = useZOffset({ status, capabilities, onSaveConfig: saveConfig.confirm });
  const bedTools = useBedTools({ capabilities, homedAxes: status.homedAxes, lockReason, onSaveConfig: saveConfig.confirm });
  const desktop = useIsDesktop();
  const files = useFileList(tab === "files", desktop ? FILES_METADATA_LIMIT_WIDE : FILES_METADATA_LIMIT);
  const aiMonitor = useAiMonitor();
  const updates = useUpdateDialog();

  useExternalLinksInNewTab();
  useModalInputScroll();
  useEffect(scrollPageToTop, [tab]);
  useEffect(() => {
    document.documentElement.classList.toggle("is-wide", desktop);
  }, [desktop]);

  // On a wide screen the Config page edits inside the page, so leaving it (or opening another file) could drop unsaved changes.
  const inlineEditor = desktop && tab === "config";
  const [editorDirty, setEditorDirty] = useState(false);
  const [discardPrompt, setDiscardPrompt] = useState(null); // { proceed } while the "unsaved changes" question is open
  const unlessUnsaved = (proceed) => (inlineEditor && editorDirty ? setDiscardPrompt({ proceed }) : proceed());

  const selectTab = (id) =>
    unlessUnsaved(() => {
      if (inlineEditor && id !== tab) setEditorSession(null); // the wide editor belongs to the Config page: it does not follow to the others
      storage.set(STORAGE_KEYS.currentTab, id);
      setTab(id);
    });
  const runFromConsole = (script) => sendFromConsole(script, consoleFeed.echo);
  const restartService = (name) => {
    settingsMenu.close();
    power.service("restart", name);
  };
  const openEditor = (path, content, options) => setEditorSession({ path, content, token: Date.now(), ...options });
  const openEditorAskingFirst = (path, content, options) => unlessUnsaved(() => openEditor(path, content, options));
  const fileActions = useFileActions(files, openEditor);

  const pages = {
    home: desktop
      ? h(DesktopDevicePage, { printStatus, printControls, status, motion, bedTools, zOffset, lockReason, aiMonitor, onEditTemperature: temperature.edit, onGcode: runFromConsole, onNavigate: selectTab })
      : h(HomePage, { printStatus, printControls, status, motion, bedTools, zOffset, lockReason, onEditTemperature: temperature.edit }),
    controllo: desktop
      ? h(DesktopCalibrationPage, { capabilities, lockReason, onGcode: runFromConsole })
      : h(ControlPage, { entries: consoleFeed.entries, status, capabilities, lockReason, onGcode: runFromConsole, onEditTemperature: temperature.edit }),
    files: desktop ? h(DesktopFilesPage, { list: files, onPrint: setPrintJob, fileActions }) : h(FilesCard, { list: files, onPrint: setPrintJob, onMenu: fileActions.openMenu }),
    config: desktop
      ? h(DesktopConfigPage, {
          onEditFile: openEditorAskingFirst,
          onViewImage: setImagePath,
          editing: Boolean(editorSession),
          editor: h(TextEditor, { session: editorSession, onClose: () => setEditorSession(null), inline: true, onDirtyChange: setEditorDirty }),
        })
      : h(ConfigPage, { aiMonitor, onEditFile: openEditor, onViewImage: setImagePath }),
    sistema: desktop ? h(DesktopSystemPage, { controller: updates, aiMonitor, onEditFile: openEditor }) : h(SystemPage, { controller: updates }),
  };

  return h(
    "div",
    { className: desktop ? "desk-app" : "min-h-screen" },
    h(AppHeader, {
      onSettings: settingsMenu.show,
      onPower: power.toggle,
      onSaveConfig: saveConfig.open,
      onEmergencyStop: klipper.emergencyStop,
      saveBusy: saveConfig.busy,
      aiBadge: aiMonitor.badge,
      wide: desktop ? { tabs: DESKTOP_TABS, active: tab, onSelect: selectTab, state: printerStatePill(printStatus) } : undefined,
    }),
    desktop
      ? h(
          "main",
          { className: "desk-main" },
          h(KlipperStateBanner, { state: klipper }),
          h("div", { className: "desk-page" }, pages[tab]),
          h(ConsoleDock, { entries: consoleFeed.entries }),
        )
      : h(
          "main",
          { className: "app-main" },
          h(KlipperStateBanner, { state: klipper }),
          h(PageTitle, null, TAB_TITLES[tab]),
          pages[tab],
        ),
    h(PowerMenuDialogs, { menu: power, klipper }),
    h(SettingsMenuLayer, { menu: settingsMenu, updates, printing: printStatus.printing, actions: { restartService } }),
    h(Presence, null, temperature.dialog.open && h(TemperatureDialog, { dialog: temperature.dialog, onChange: temperature.setValue, onClose: temperature.close, onConfirm: temperature.confirm })),
    h(Presence, null, motion.positionDialog.open && h(PositionDialog, { dialog: motion.positionDialog, onChange: motion.setPositionValue, onClose: motion.closePositionDialog, onConfirm: motion.goToPosition })),
    h(Presence, null, updates.dialog.open && h(UpdateDialog, { controller: updates })),
    !desktop && h(BottomNav, { active: tab, onSelect: selectTab }),
    h(
      Presence,
      null,
      printJob &&
        h(PrintConfirmDialog, {
          job: printJob,
          onCancel: () => setPrintJob(null),
          onConfirm: () => {
            startPrint(printJob);
            setPrintJob(null);
          },
        }),
    ),
    h(FileActionDialogs, { controller: fileActions }),
    h(BedToolsDialogs, { controller: bedTools }),
    h(ZOffsetDialogs, { controller: zOffset }),
    h(SaveConfigDialog, { open: saveConfig.dialogOpen, onConfirm: saveConfig.confirm, onCancel: saveConfig.close }),
    h(CancelPrintDialog, { open: printControls.confirmingCancel, onConfirm: printControls.cancelPrint, onCancel: printControls.dismissCancel }),
    desktop &&
      h(ConfirmDialog, {
        open: Boolean(discardPrompt),
        tone: "danger",
        icon: h(Icons.CancelCircle),
        title: "Modifiche non salvate",
        subtitle: editorSession ? editorSession.path : "",
        message: "Hai modifiche non salvate in questo file. Continuare senza salvare?",
        confirmLabel: "Continua",
        onConfirm: () => {
          const { proceed } = discardPrompt;
          setDiscardPrompt(null);
          setEditorDirty(false);
          proceed();
        },
        onCancel: () => setDiscardPrompt(null),
      }),
    h(Presence, null, !inlineEditor && editorSession && h(TextEditor, { session: editorSession, onClose: () => setEditorSession(null) })),
    h(Presence, null, imagePath && h(ImageViewer, { path: imagePath, onClose: () => setImagePath(null) })),
    h(ToastHost),
    !desktop && h(PullToRefresh),
  );
}

createRoot(document.getElementById("root")).render(h(React.StrictMode, null, h(App)));
