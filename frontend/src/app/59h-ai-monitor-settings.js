/* ============================================================================
   59h · SETTINGS → AI MONITOR (1.19)
   Everything the AI print monitor does, from one entry of the menu (before 1.19 it was spread over four: "AI monitor",
   "Monitor thresholds", "Camera calibration", "Recordings", with two different confidence thresholds). The page answers,
   top to bottom:
     1. is it on?                      the switch, the notification service, the AI key;
     2. how does it look at the print?  all the bed outside the parts (calibrated camera) or the old rectangle;
     3. what happens when it sees a problem?  ONE confidence threshold, the defects, checks in a row, automatic actions;
     4. the AI service: who judges the pictures (1.119: the online AI, or the local model alone), which service and
        model (1.27: any of several, the model chosen from the service's own list), the keys, the earlier picture
        (59l-ai-services.js);
   and leads to the three pages inside it: Camera calibration, Monitor thresholds (the fine numbers), Recordings.
   The values live where they are used: the backend's thresholds (monitor.json, useBackendConfig) and the dashboard's shared
   settings (automatic actions, defects, checks in a row: read by the notification service).
   ========================================================================== */

const CONFIDENCE_CHOICES = [50, 60, 70, 80, 90, 95];
const CONFIDENCE_WARN_ABOVE = 85;

/** The AI key: { phase, configured, provider, preview }, read from the backend; reload() after a change. */
function useAiKey(active) {
  const [state, setState] = useState({ phase: "loading" });
  const load = async () => {
    try {
      const response = await fetchFresh("/api/ai/config", { timeout: BACKEND_READ_TIMEOUT_MS });
      const data = await response.json();
      setState({ phase: "ok", configured: Boolean(data.configured), provider: data.provider || "", preview: data.key_preview || "" });
    } catch (error) {
      setState({ phase: "down" });
    }
  };
  useEffect(() => {
    if (active) load();
  }, [active]);
  return { ...state, reload: load };
}

/** How the monitor looks at the print now, in one sentence (from the calibration and the two switches). */
function lookingText(calibration, values) {
  const saved = calibration && calibration.phase === "ok" ? calibration.data : null;
  if (!saved || !saved.saved) return { ok: false, text: tx("Only the outer band of a rectangle of the picture: the middle, where the part is, is not watched. Calibrate the camera so that it watches the whole bed.") };
  if (!saved.usable) return { ok: false, text: tx("The camera has moved since its calibration: until it is calibrated again only the outer band of the rectangle is watched.") };
  const zone = values.expected_zone !== false;
  const masks = values.machine_masks !== false;
  if (zone && masks) return { ok: true, text: tx("The whole bed, outside the parts being printed; the toolhead and the gantry are left out.") };
  if (masks) return { ok: true, text: tx("The outer band of the rectangle; the toolhead and the gantry are left out (watching the whole bed is switched off).") };
  return { ok: false, text: tx("The camera is calibrated but its use is switched off (Camera calibration).") };
}

function SubpageRow({ entry, meta, menu }) {
  return h(
    "button",
    { type: "button", className: "set-entry", "data-page": entry.id, onClick: () => menu.goTo(entry.id) },
    h("span", { className: "oui-row__icon oui-row__icon--accent" }, h(entry.icon)),
    h("span", { className: "oui-row__text" }, h("span", { className: "oui-row__name" }, entry.title), meta ? h("span", { className: "oui-row__meta set-entry__meta" }, meta) : null),
    h("span", { className: "set-entry__go", "aria-hidden": "true" }, h(Icons.Forward)),
  );
}

function AiPage({ active, menu }) {
  const { settings, update } = useSettings();
  const ai = settings.ai;
  const status = useNotifierStatus(active);
  const config = useBackendConfig(active);
  const calibration = useBackendJson("/api/camera/calibration", active, BACKEND_POLL_MS);
  const recordings = useBackendJson("/api/recordings", active, BACKEND_POLL_MS);
  const aiServices = useAiServices(active);
  const localModel = useBackendJson("/api/local_model", active, BACKEND_POLL_MS);
  const data = useMemo(() => (config.data ? localizeBackendSchema(config.data) : null), [config.data]);
  const spec = (key) => (data ? data.spec.find((item) => item.key === key) : null);
  const control = (key) => (spec(key) && config.values[key] !== undefined ? h(BackendSettingControl, { key, spec: spec(key), config }) : null);
  const last = lastActionText(status);
  const looking = lookingText(calibration, config.values || {});
  const confidence = config.values ? config.values.ai_min_confidence : undefined;
  const choices = [...new Set([...CONFIDENCE_CHOICES, ...(Number.isFinite(confidence) ? [confidence] : [])])].sort((a, b) => a - b);
  const pauseSeconds = config.values && config.values.ai_cooldown;
  const online = !config.values || config.values.ai_online !== false; // 1.119: off = the local model alone
  return h(
    React.Fragment,
    null,
    config.phase !== "ok" && h(BackendNotice, { phase: config.phase }),
    config.phase === "ok" && h("div", { className: "oui-list" }, control("enabled")),
    h(ServiceLine, { status }),
    h(
      SettingsGroup,
      { title: tx("How it looks at the print"), help: ["ai", "what"] },
      h("div", { className: cx("set-status", looking.ok ? "set-status--ok" : "set-status--warn"), "data-looking": looking.ok ? "zone" : "band" }, h("span", { className: "set-status__dot" }), looking.text),
      h(
        "div",
        { className: "oui-list" },
        h(SubpageRow, { entry: AI_SUBPAGES[0], meta: cameraCalibrationSummary(calibration), menu }),
        h(SubpageRow, { entry: AI_SUBPAGES[1], meta: config.phase === "ok" && config.values ? tx("How watchful: {level}", { level: watchLevelName(config.values) }) : tx("How watchful it is, fine adjustments"), menu }),
        h(SubpageRow, { entry: AI_SUBPAGES[2], meta: recordingsSummary(recordings), menu }),
      ),
    ),
    h(
      SettingsGroup,
      { title: tx("When it sees a problem"), help: ["ai", "confidence"] },
      config.phase === "ok" &&
        !online &&
        h("p", { className: "set-group__note", "data-confidence": "local" }, tx("With the local model alone, its own threshold decides: «Sure from», in Monitor thresholds → Fine adjustments.")),
      config.phase === "ok" &&
        online &&
        Number.isFinite(confidence) &&
        h(
          "div",
          { className: "fn-confidence", "data-confidence": confidence },
          h("div", { className: "set-field__label" }, tx("Minimum AI confidence")),
          h(ChipChoice, { label: tx("Minimum AI confidence"), options: choices.map((value) => ({ id: value, label: value + "%" })), value: confidence, onChange: (value) => config.set({ ai_min_confidence: value }) }),
          h(
            "p",
            { className: cx("set-group__note", confidence > CONFIDENCE_WARN_ABOVE && "fn-warn") },
            confidence > CONFIDENCE_WARN_ABOVE
              ? tx("High: the AI is rarely this sure, so a failed print may NOT be stopped. 70% is the usual value.")
              : tx("If the AI suggests to pause or cancel but no defect reaches this, the verdict becomes «continue» and stays in the history in orange. This is the only threshold."),
          ),
        ),
      h("div", { className: "set-field__label fn-subtitle" }, tx("Defects to consider")),
      h(
        "div",
        { className: "oui-list" },
        AI_DEFECTS.map((defect) => h(SwitchRow, { key: defect.id, title: defect.title, detail: defect.detail, checked: ai.defects[defect.id], onChange: (value) => update((draft) => (draft.ai.defects[defect.id] = value)) })),
      ),
      h("div", { className: "set-field__label fn-subtitle" }, tx("Checks in a row")),
      h(ChipChoice, { label: tx("Checks in a row"), options: CONFIRMATION_OPTIONS, value: ai.confirmations, onChange: (id) => update((draft) => (draft.ai.confirmations = id)) }),
      h(
        "p",
        { className: "set-group__note" },
        tx("How many AI analyses in a row must report the problem before you are told or something is done.") +
          (Number.isFinite(pauseSeconds) ? " " + tx("Between two analyses there are at least {seconds} s: each extra check makes the warning that much later.", { seconds: pauseSeconds }) : ""),
      ),
      h("div", { className: "set-field__label fn-subtitle" }, tx("Automatic actions")),
      h(
        "div",
        { className: "oui-list" },
        h(SwitchRow, { title: tx("Pause by itself"), detail: tx("When the AI suggests PAUSE (or CANCEL, if automatic cancel is off)"), checked: ai.autoPause, onChange: (value) => update((draft) => (draft.ai.autoPause = value)) }),
        h(SwitchRow, { title: tx("Cancel by itself"), detail: tx("When the AI suggests CANCEL. A cancelled print cannot be recovered"), danger: true, checked: ai.autoCancel, onChange: (value) => (value ? menu.ask("autoCancel") : update((draft) => (draft.ai.autoCancel = false))) }),
      ),
      h("p", { className: "set-group__note" }, tx("The Raspberry does them by itself, also with the phone off. The AI can be wrong: a cancel cannot be undone.")),
      h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm set-inline-btn", "data-go": "notifications", onClick: () => menu.goTo("notifications") }, h(Icons.Bell, { size: 16 }), tx("Choose the notifications")),
      last && h("p", { className: "set-group__note" }, last),
    ),
    h(
      SettingsGroup,
      { title: tx("The AI service"), help: ["ai", "service"] },
      config.phase === "ok" && h(JudgeChoice, { config, localModel }),
      online && h(AiServicesPanel, { use: "monitor", ai: aiServices }),
      online && config.phase === "ok" && h("div", { className: "oui-list" }, control("ai_send_reference")),
    ),
    localModel.phase === "ok" && h(LocalModelGroup, { info: localModel.data, reload: localModel.reload, control, config, menu, online }),
  );
}

/**
 * Who judges the pictures (1.119): the online AI (with the local model before it, when there is one) or the local model
 * alone, so that no picture leaves the Raspberry. Saved as the backend's `ai_online`.
 */
function JudgeChoice({ config, localModel }) {
  const online = config.values.ai_online !== false;
  const model = localModel.phase === "ok" ? localModel.data : null;
  const modelReady = Boolean(model && model.available) && config.values.local_enabled !== false;
  let note;
  if (online) note = tx("The pictures of an alarm go to the online AI service chosen below; the local model, when there is one, judges them first.");
  else if (modelReady) note = tx("No picture leaves the Raspberry. The local model judges alone: when it is sure for three looks in a row it proposes a pause, and «Pause by itself» does it.");
  else note = tx("No picture leaves the Raspberry, but there is no local model in use: the monitor cannot judge anything. Install the local model or use the online AI.");
  return h(
    React.Fragment,
    null,
    h("div", { className: "set-field__label" }, tx("Who judges the pictures")),
    h(ChipChoice, {
      label: tx("Who judges the pictures"),
      options: [
        { id: "online", label: tx("Online AI and local model") },
        { id: "local", label: tx("Local model only") },
      ],
      value: online ? "online" : "local",
      onChange: (id) => config.set({ ai_online: id === "online" }),
    }),
    h("p", { className: cx("set-group__note", !online && !modelReady && "set-group__note--warn"), "data-judge": online ? "online" : modelReady ? "local" : "nobody" }, note),
  );
}

/** The local model (1.106): which one is in use and its last look, the switches; its thresholds are in Monitor thresholds. */
function LocalModelGroup({ info, reload, control, config, menu, online }) {
  const last = info.last || {};
  const status = info.available
    ? tx("In use: {source} • version {version}", { source: info.source === "own" ? tx("your model") : tx("KlippEye's model"), version: info.version || "?" }) +
      (Number.isFinite(last.score) ? " • " + tx("last look: {score}%", { score: Math.round(last.score) }) : "")
    : tx("No local model installed yet: the monitor works without it (the motion detection and the online AI).");
  const counts =
    info.available && last.checks
      ? tx("Looks: {checks} • alarms it kept from the online AI: {filtered} • times it asked the online AI: {asked}", { checks: last.checks || 0, filtered: last.filtered || 0, asked: last.asked || 0 })
      : "";
  return h(
    SettingsGroup,
    { title: tx("Local model") },
    h("div", { className: cx("set-status", info.available ? "set-status--ok" : "set-status--warn"), "data-local-model": info.available ? info.source : "none" }, h("span", { className: "set-status__dot" }), status),
    counts && h("p", { className: "oui-caption" }, counts),
    info.available && config.phase === "ok" && h("div", { className: "oui-list" }, control("local_enabled"), online && control("local_filter"), online && control("local_alone")),
    info.available && config.values && config.values.local_enabled !== false && h(LocalTry),
    info.available && h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm set-inline-btn", "data-go": "detector", onClick: () => menu.goTo("detector") }, h(Icons.Sliders, { size: 16 }), tx("Its thresholds: Monitor thresholds → Fine adjustments")),
    info.available && info.personal && config.phase === "ok" && h(PersonalLayerPart, { personal: info.personal, reload, control, on: config.values.personal_learning === true }),
    h("p", { className: "set-group__note" }, tx("A small image model that runs on the Raspberry, without internet: it looks at the print by itself and judges the alarms before the online AI is asked.")),
  );
}

/**
 * The personal layer (1.107, optional): what the local model learned from this printer's answers and labelled
 * recordings; its switch, how far it is, train now, and the examples carried to / from another printer.
 */
function PersonalLayerPart({ personal, reload, control, on }) {
  const [busy, setBusy] = useState("");
  const fileInput = useRef(null);
  const have = personal.have || { failed: 0, fine: 0 };
  const needed = personal.needed || { failed: 5, fine: 20 };
  const measured = personal.measured || {};
  const imported = personal.imported || [];
  let status;
  if (personal.training || busy === "train") status = tx("Learning from the examples…");
  else if (personal.trained)
    status =
      tx("Learned from {count} examples ({failed} failed, {fine} fine)", { count: personal.examples || 0, failed: personal.failed || 0, fine: personal.fine || 0 }) +
      (Number.isFinite(measured.right) ? " • " + tx("right {percent}% of the times", { percent: Math.round(measured.right * 100) }) : "");
  else
    status = tx("Not enough examples yet: {failed} of {needFailed} failed and {fine} of {needFine} fine pictures", {
      failed: have.failed,
      needFailed: needed.failed,
      fine: have.fine,
      needFine: needed.fine,
    });
  const run = async (what, job) => {
    setBusy(what);
    try {
      await job();
    } finally {
      setBusy("");
      reload();
    }
  };
  const train = () =>
    run("train", async () => {
      const reply = await backendPost("/api/local_model/personal", { train: true });
      if (!reply.ok) toast.error(tx("Learning failed: {reason}", { reason: reply.message }));
      else if (reply.data && reply.data.personal && !reply.data.personal.trained) toast.action(tx("Not enough examples yet: answer «How did the print go?» after a few more prints"));
      else toast.success(tx("The local model learned from this printer's examples"));
    });
  const forget = () =>
    run("forget", async () => {
      const reply = await backendPost("/api/local_model/personal", { forget_imported: true });
      if (!reply.ok) toast.error(reply.message);
    });
  const upload = (event) => {
    const file = event.target.files && event.target.files[0];
    event.target.value = "";
    if (!file) return;
    run("import", async () => {
      const form = new FormData();
      form.append("file", file, file.name);
      try {
        const response = await fetch("/api/local_model/personal/import", { method: "POST", body: form });
        const data = await response.json().catch(() => null);
        if (response.ok && data && data.ok) toast.success(tx("{count} examples imported", { count: data.imported }));
        else toast.error(tx("Import failed: {reason}", { reason: (data && data.error) || "HTTP " + response.status }));
      } catch (error) {
        toast.error(tx("the KlippEye service does not answer"));
      }
    });
  };
  return h(
    React.Fragment,
    null,
    h("div", { className: "set-field__label fn-subtitle" }, tx("Learning from this printer")),
    h("div", { className: "oui-list" }, control("personal_learning")),
    on && h("div", { className: cx("set-status", personal.trained ? "set-status--ok" : "set-status--warn"), "data-personal": personal.trained ? "trained" : "waiting" }, h("span", { className: "set-status__dot" }), status),
    on && personal.error && personal.trained && h("p", { className: "oui-caption" }, personal.error),
    on &&
      h(
        "div",
        { className: "oui-btn-row set-personal-actions" },
        h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm", "data-personal-train": "", disabled: Boolean(busy) || personal.training, onClick: train }, h(Icons.Refresh, { size: 16 }), tx("Learn now")),
        h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm", "data-personal-export": "", disabled: Boolean(busy) || !(have.failed + have.fine), onClick: () => downloadFile("/api/local_model/personal/export", "klippeye-examples.zip") }, h(Icons.Download, { size: 16 }), tx("Export the examples")),
        h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm", "data-personal-import": "", disabled: Boolean(busy), onClick: () => fileInput.current && fileInput.current.click() }, h(Icons.Upload, { size: 16 }), tx("Import examples")),
        h("input", { ref: fileInput, type: "file", accept: ".zip,application/zip", hidden: true, onChange: upload }),
      ),
    on &&
      imported.length > 0 &&
      h(
        "p",
        { className: "oui-caption", "data-personal-imported": imported.length },
        tx("Examples from other printers: {list}", { list: imported.map((entry) => (entry.printer || entry.origin) + " (" + entry.pictures + ")").join(", ") }) + " ",
        h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm", "data-personal-forget": "", disabled: Boolean(busy), onClick: forget }, h(Icons.Trash, { size: 16 }), tx("Remove them")),
      ),
    h(
      "p",
      { className: "set-group__note" },
      tx("Optional. The local model is the same for everyone; with this on it also learns what goes wrong on this printer, from your answers at the end of the prints. The pictures stay on the Raspberry; the export carries them to another printer of yours."),
    ),
  );
}

/** One line for the menu list. */
function aiMonitorSummary(settings, backendState) {
  const calibrated = backendState.camcal && backendState.camcal.phase === "ok" && backendState.camcal.data.saved && backendState.camcal.data.usable;
  return (calibrated ? tx("Whole bed") : tx("Outer band only")) + " • " + tx("Auto pause: {pause}", { pause: ON_OFF(settings.ai.autoPause) });
}
