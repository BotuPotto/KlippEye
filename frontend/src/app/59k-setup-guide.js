/* ============================================================================
   59k · GUIDED SET-UP (1.22, phase 5e)
   Everything KlippEye needs, one step at a time, over the whole page: shown by itself once on a new installation (the
   shared setting setup.done, see 16-settings.js), skippable at any moment and repeatable from Settings → Guided set-up.
   Each step is the settings page of that subject (the same component, so there is one way of doing each thing), with
   a few words before it. The step reached is remembered on this device: a step that leads elsewhere (camera calibration),
   or a reload (a new language), comes back to it.
   ========================================================================== */

const SETUP_STEP_KEY = "ke_setup_step";
const SETUP_OFFERED_KEY = "ke_setup_offered";
const setupListeners = new Set();
let setupOpen = false;

function openSetupGuide() {
  setupOpen = true;
  setupListeners.forEach((listener) => listener(true));
}

function closeSetupGuide() {
  setupOpen = false;
  setupListeners.forEach((listener) => listener(false));
}

function useSetupOpen() {
  const [open, setOpen] = useState(setupOpen);
  useEffect(() => {
    setupListeners.add(setOpen);
    return () => setupListeners.delete(setOpen);
  }, []);
  return open;
}

/** The camera as the settings describe it now, small, to see at once whether the address is right. */
function SetupCameraPreview() {
  const reloads = useCameraReloads();
  return h("div", { className: "camera-frame setup-camera" }, h(CameraMedia, { className: "camera-frame__video", reloads }));
}

function SetupIntro({ children }) {
  return h("p", { className: "setup-intro" }, children);
}

/** The AI step: switch, key and the way to the camera calibration (the whole AI page is too much for a first set-up). */
function SetupAi({ onCalibrate }) {
  const config = useBrainConfig(true);
  const aiKey = useAiKey(true);
  const data = useMemo(() => (config.data ? localizeBrainSchema(config.data) : null), [config.data]);
  const spec = data ? data.spec.find((item) => item.key === "enabled") : null;
  const calibration = useBackendJson("/api/camera/calibration", true, BRAIN_POLL_MS);
  const calibrated = calibration.phase === "ok" && calibration.data.saved && calibration.data.usable;
  return h(
    React.Fragment,
    null,
    config.phase !== "ok" && h(BrainNotice, { phase: config.phase }),
    spec && config.values.enabled !== undefined && h("div", { className: "oui-list" }, h(BrainSettingControl, { spec, config })),
    h(SettingsGroup, { title: tx("The AI service"), help: ["ai", "start"] }, h(AiKeySection, { aiKey }), h("p", { className: "set-group__note" }, tx("Groq gives a free key: console.groq.com → API Keys → Create API Key. Copy it and paste it here."))),
    h(
      SettingsGroup,
      { title: tx("Camera calibration"), help: ["camcal", "tap"] },
      h("div", { className: cx("set-status", calibrated ? "set-status--ok" : "set-status--warn"), "data-setup-camcal": calibrated ? "yes" : "no" }, h("span", { className: "set-status__dot" }), calibrated ? tx("The camera is calibrated: the whole bed is watched.") : tx("Not calibrated yet: only a band around the picture is watched.")),
      h("button", { type: "button", className: "oui-btn oui-btn--block", "data-setup-go": "camcal", onClick: onCalibrate }, h(Icons.Probe, { size: 18 }), calibrated ? tx("Calibrate again") : tx("Calibrate the camera (5 minutes)")),
      h("p", { className: "set-group__note" }, tx("It opens in the settings; when it is done, «Guided set-up» brings you back here.")),
    ),
  );
}

/** The notifications step: this phone in the app, the ntfy app elsewhere. */
function SetupNotifications() {
  const channels = useNotifyChannels(true);
  return IN_APP_WEBVIEW
    ? h(SettingsGroup, { title: tx("This phone"), help: ["notifications", "app"] }, h(PhoneNotifications, { store: channels }))
    : h(SettingsGroup, { title: tx("Where they arrive"), help: ["notifications", "how"] }, h(NotificationChannels, { store: channels }));
}

/** How far each subject is, for the last step: "ok" | "todo" | "optional". */
function useSetupStatus(active) {
  const { settings } = useSettings();
  const channels = useBackendJson("/api/notifications/channels", active, 30000);
  const aiKey = useAiKey(active);
  const calibration = useBackendJson("/api/camera/calibration", active, BRAIN_POLL_MS);
  const [access] = useAccessStatus(active);
  const phone = readAppNotifyState();
  const notifications = IN_APP_WEBVIEW && phone ? Boolean(phone.mode) : channels.phase === "ok" && (channels.data.ntfy.enabled || channels.data.firebase.on);
  return {
    printer: "ok",
    camera: "ok",
    network: settings.network.localIp || settings.network.externalIp ? "ok" : "optional",
    functions: settings.functions.reviewed ? "ok" : "todo",
    notifications: notifications ? "ok" : "todo",
    ai: aiKey.phase === "ok" && aiKey.configured ? (calibration.phase === "ok" && calibration.data.saved && calibration.data.usable ? "ok" : "todo") : "todo",
    access: access.info && access.info.enabled ? "ok" : "optional",
  };
}

const SETUP_STATUS_TEXT = { ok: tx("Done"), todo: tx("To do"), optional: tx("Optional") };

function SetupSummary({ steps, onGo }) {
  const status = useSetupStatus(true);
  return h(
    React.Fragment,
    null,
    h(SetupIntro, null, tx("That is all. Here is where each part stands; tap one to go back to it. You can repeat this guide whenever you want from Settings → Guided set-up.")),
    h(
      "div",
      { className: "oui-list" },
      steps
        .filter((step) => status[step.id])
        .map((step) =>
          h(
            "button",
            { key: step.id, type: "button", className: "set-entry", "data-setup-summary": step.id, "data-status": status[step.id], onClick: () => onGo(step.id) },
            h("span", { className: cx("setup-tick", "setup-tick--" + status[step.id]), "aria-hidden": "true" }, status[step.id] === "ok" ? h(Icons.Check, { size: 16 }) : status[step.id] === "todo" ? "!" : "–"),
            h("span", { className: "oui-row__text" }, h("span", { className: "oui-row__name" }, step.title), h("span", { className: "oui-row__meta set-entry__meta" }, SETUP_STATUS_TEXT[status[step.id]])),
            h("span", { className: "set-entry__go", "aria-hidden": "true" }, h(Icons.Forward)),
          ),
        ),
    ),
  );
}

function SetupWelcome() {
  return h(
    React.Fragment,
    null,
    h("div", { className: "setup-welcome" }, h(PrinterLogo, { id: "klippeye", className: "setup-welcome__logo" }), h("h2", null, tx("Welcome to KlippEye"))),
    h(SetupIntro, null, tx("A few steps to set up what KlippEye needs: the name of the printer, the camera, the buttons that use your macros, the notifications on the phone and the AI monitor. Every step can be skipped and done later; nothing here can harm the printer.")),
    h(SetupIntro, null, tx("The «?» buttons open a short guide wherever you are.")),
    h(SettingsGroup, { title: tx("Language of this device") }, h(SetupLanguage)),
  );
}

function SetupLanguage() {
  const choice = savedLanguageChoice();
  const options = [{ id: "auto", label: tx("Automatic") }].concat(I18N_LANGUAGES.map((language) => ({ id: language.code, label: language.name })));
  return h(ChipChoice, { label: tx("Language"), options, value: choice, onChange: (id) => id !== choice && setLanguageChoice(id) });
}

/** The steps, in order. `page` is the help page of the step. */
function setupSteps(menuTo, printing) {
  return [
    { id: "welcome", title: tx("Welcome"), page: "home", body: () => h(SetupWelcome) },
    { id: "printer", title: tx("Name and logo"), page: "printer", intro: tx("How the printer is called in the top bar and in the browser tab."), body: () => h(PrinterPage) },
    {
      id: "camera",
      title: "Camera",
      page: "camera",
      intro: tx("If the camera works in Mainsail, «Import from Mainsail» at the bottom is the quickest way. The preview shows at once whether it is right."),
      body: () => h(React.Fragment, null, h(SetupCameraPreview), h(CameraPage)),
    },
    { id: "network", title: tx("Addresses"), page: "network", intro: tx("Only if you open KlippEye from outside your home with ZeroTier, Tailscale or another VPN. Otherwise leave them empty and go on."), body: () => h(NetworkPage) },
    { id: "functions", title: tx("Printer functions"), page: "functions", intro: tx("What the buttons that use your macros do. KlippEye has looked for them by itself: check each one and press «All right» at the bottom."), body: () => h(PrinterFunctionsPage, { printing }) },
    { id: "notifications", title: tx("Notifications"), page: "notifications", intro: tx("Print finished, errors, filament run out, AI alarms: on the phone, also with the app closed."), body: () => h(SetupNotifications) },
    { id: "ai", title: tx("AI monitor"), page: "ai", intro: tx("It watches the print through the camera and warns you of a failure. It needs an AI key (free) and, to watch the whole bed, the camera calibrated."), body: () => h(SetupAi, { onCalibrate: () => menuTo("camcal") }) },
    { id: "access", title: tx("Password"), page: "access", intro: tx("Optional: with a password, only who knows it can use the printer from the dashboard. Useful if other people use your network."), body: () => h(AccessPage, { active: true }) },
    { id: "done", title: tx("Ready"), page: "home" },
  ];
}

function readSetupStep(steps) {
  const saved = storage.get(SETUP_STEP_KEY);
  const index = steps.findIndex((step) => step.id === saved);
  return index >= 0 ? index : 0;
}

function SetupGuide({ menu, printing }) {
  useBodyScrollLock(true);
  const { update } = useSettings();
  const menuTo = (page) => {
    closeSetupGuide();
    menu.openPage(page);
  };
  const steps = setupSteps(menuTo, printing);
  const [index, setIndex] = useState(() => readSetupStep(steps));
  const bodyRef = useRef(null);
  const step = steps[index];
  const go = (next) => {
    const target = Math.max(0, Math.min(steps.length - 1, next));
    storage.set(SETUP_STEP_KEY, steps[target].id);
    setIndex(target);
    if (bodyRef.current) bodyRef.current.scrollTop = 0;
  };
  const finish = () => {
    update((draft) => (draft.setup.done = true));
    storage.set(SETUP_STEP_KEY, "welcome");
    closeSetupGuide();
  };
  // leaving before the end counts as "skipped": it is not shown by itself again (Settings → Guided set-up repeats it)
  const leave = () => {
    update((draft) => (draft.setup.done = true));
    closeSetupGuide();
  };
  useEffect(() => {
    const onKey = (event) => event.key === "Escape" && !document.querySelector(".help-overlay") && leave();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const last = index === steps.length - 1;
  return h(
    "div",
    { className: "setup-overlay" },
    h(
      "div",
      { className: "setup", role: "dialog", "aria-modal": "true", "aria-label": tx("Guided set-up"), "data-setup-step": step.id },
      h(
        "div",
        { className: "setup__head" },
        h("div", { className: "setup__heading" }, h("div", { className: "setup__count" }, tx("Step {n} of {total}", { n: index + 1, total: steps.length })), h("div", { className: "setup__title" }, step.title)),
        h(HelpButton, { page: step.page, className: "drawer__help" }),
        h("button", { type: "button", className: "header-btn drawer__btn", "aria-label": tx("Exit the guided set-up"), title: tx("Exit the guided set-up"), "data-setup-exit": "1", onClick: leave }, h(Icons.Close)),
      ),
      h("div", { className: "setup__dots", "aria-hidden": "true" }, steps.map((one, position) => h("span", { key: one.id, className: cx("setup__dot", position === index && "is-current", position < index && "is-past") }))),
      h(
        "div",
        { className: "setup__body drawer__body", ref: bodyRef, key: step.id },
        step.intro && h(SetupIntro, null, step.intro),
        step.id === "done" ? h(SetupSummary, { steps: steps.slice(1, -1), onGo: (id) => go(steps.findIndex((one) => one.id === id)) }) : step.body(),
      ),
      h(
        "div",
        { className: "setup__foot" },
        index > 0 ? h("button", { type: "button", className: "oui-btn", "data-setup-back": "1", onClick: () => go(index - 1) }, h(Icons.Back, { size: 18 }), tx("Back")) : h("button", { type: "button", className: "oui-btn oui-btn--quiet", "data-setup-skip-all": "1", onClick: leave }, tx("Skip the guide")),
        last
          ? h("button", { type: "button", className: "oui-btn oui-btn--primary", "data-setup-finish": "1", onClick: finish }, h(Icons.Check, { size: 18 }), tx("Finish"))
          : h("button", { type: "button", className: "oui-btn oui-btn--primary", "data-setup-next": "1", onClick: () => go(index + 1) }, index === 0 ? tx("Start") : tx("Next"), h(Icons.Forward, { size: 18 })),
      ),
    ),
  );
}

/** The guide over the page; opened by itself once on a new installation (when the Raspberry's settings are known). */
function SetupGuideLayer({ menu, printing }) {
  const open = useSetupOpen();
  const { settings, sync } = useSettings();
  const offered = useRef(false);
  useEffect(() => {
    if (offered.current || sync.state !== "shared") return;
    offered.current = true;
    // once per device at most: a device where it was already offered (and closed some other way) is not asked again
    if (!settings.setup.done && storage.get(SETUP_OFFERED_KEY) !== "1") {
      storage.set(SETUP_OFFERED_KEY, "1");
      openSetupGuide();
    }
  }, [sync.state, settings.setup.done]);
  return h(Presence, null, open && h(SetupGuide, { menu, printing }));
}
