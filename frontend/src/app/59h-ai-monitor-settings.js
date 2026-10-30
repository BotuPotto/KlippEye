/* ============================================================================
   59h · SETTINGS → AI MONITOR (1.19)
   Everything the AI print monitor does, from one entry of the menu (before 1.19 it was spread over four: "AI monitor",
   "Monitor thresholds", "Camera calibration", "Recordings", with two different confidence thresholds). The page answers,
   top to bottom:
     1. is it on?                      the switch, the notification service, the AI key;
     2. how does it look at the print?  all the bed outside the parts (calibrated camera) or the old rectangle;
     3. what happens when it sees a problem?  ONE confidence threshold, the defects, checks in a row, automatic actions;
     4. the AI service: key, model, the earlier picture;
   and leads to the three pages inside it: Camera calibration, Monitor thresholds (the fine numbers), Recordings.
   The values live where they are used: the backend's thresholds (monitor.json, useBrainConfig) and the dashboard's shared
   settings (automatic actions, defects, checks in a row: read by the notification service).
   ========================================================================== */

const CONFIDENCE_CHOICES = [50, 60, 70, 80, 90, 95];
const CONFIDENCE_WARN_ABOVE = 85;

/** The AI key: { phase, configured, provider, preview }, read from the backend; reload() after a change. */
function useAiKey(active) {
  const [state, setState] = useState({ phase: "loading" });
  const load = async () => {
    try {
      const response = await fetchFresh("/api/ai/config", { timeout: BRAIN_READ_TIMEOUT_MS });
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

function AiKeySection({ aiKey }) {
  const [editing, setEditing] = useState(false);
  const [key, setKey] = useState("");
  const [provider, setProvider] = useState("groq");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const post = async (body) => {
    setBusy(true);
    try {
      const response = await fetch("/api/ai/config", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) });
      const data = await response.json().catch(() => ({}));
      setBusy(false);
      if (!response.ok || data.error) return setProblem(data.error || "HTTP " + response.status);
      setProblem("");
      setEditing(false);
      setKey("");
      aiKey.reload();
    } catch (error) {
      setBusy(false);
      setProblem(tx("the backend does not answer"));
    }
  };
  const save = () => {
    const trimmed = key.trim();
    if (trimmed.length < KEY_MIN_LENGTH) return setProblem(tx("Key too short"));
    post({ api_key: trimmed, provider: providerForKey(trimmed, provider) });
  };
  const line =
    aiKey.phase !== "ok"
      ? tx("Reading the AI key…")
      : aiKey.configured
        ? tx("AI key saved ({provider}, ends with {end}).", { provider: aiKey.provider || "?", end: aiKey.preview || "?" })
        : tx("No AI key: the monitor sees the problems but nobody judges them. Groq has a free key.");
  return h(
    React.Fragment,
    null,
    h("div", { className: cx("set-status", aiKey.configured ? "set-status--ok" : "set-status--warn"), "data-ai-key": aiKey.configured ? "yes" : "no" }, h("span", { className: "set-status__dot" }), line),
    editing
      ? h(
          "div",
          { className: "fn-key" },
          h("select", { className: "oui-field", value: provider, onChange: (event) => setProvider(event.target.value) }, AI_PROVIDERS.map((option) => h("option", { key: option.id, value: option.id }, option.label))),
          h("input", { className: "oui-field oui-mono", value: key, placeholder: tx("Paste the key here..."), "data-ai-key-input": "1", onChange: (event) => setKey(event.target.value) }),
          h("div", { className: "oui-btn-row" }, h("button", { type: "button", className: "oui-btn oui-btn--primary", disabled: busy, onClick: save }, tx("Save the key")), h("button", { type: "button", className: "oui-btn", onClick: () => setEditing(false) }, tx("Cancel"))),
        )
      : h(
          "div",
          { className: "oui-btn-row" },
          h("button", { type: "button", className: "oui-btn oui-btn--sm", "data-ai-key-edit": "1", onClick: () => setEditing(true) }, aiKey.configured ? tx("Change the key") : tx("Enter the key")),
          aiKey.configured && h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--quiet", disabled: busy, onClick: () => window.confirm(tx("Delete the key?")) && post({ delete: true }) }, txc("key", "Delete")),
        ),
    problem && h("p", { className: "set-field__error", role: "alert" }, problem),
  );
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
  const config = useBrainConfig(active);
  const calibration = useBackendJson("/api/camera/calibration", active, BRAIN_POLL_MS);
  const recordings = useBackendJson("/api/recordings", active, BRAIN_POLL_MS);
  const aiKey = useAiKey(active);
  const data = useMemo(() => (config.data ? localizeBrainSchema(config.data) : null), [config.data]);
  const spec = (key) => (data ? data.spec.find((item) => item.key === key) : null);
  const control = (key) => (spec(key) && config.values[key] !== undefined ? h(BrainSettingControl, { key, spec: spec(key), config }) : null);
  const last = lastActionText(status);
  const looking = lookingText(calibration, config.values || {});
  const confidence = config.values ? config.values.ai_min_confidence : undefined;
  const choices = [...new Set([...CONFIDENCE_CHOICES, ...(Number.isFinite(confidence) ? [confidence] : [])])].sort((a, b) => a - b);
  const pauseSeconds = config.values && config.values.ai_cooldown;
  return h(
    React.Fragment,
    null,
    config.phase !== "ok" && h(BrainNotice, { phase: config.phase }),
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
        h(SubpageRow, { entry: AI_SUBPAGES[1], meta: tx("Sensitivity, persistence, pauses, when it starts"), menu }),
        h(SubpageRow, { entry: AI_SUBPAGES[2], meta: recordingsSummary(recordings), menu }),
      ),
    ),
    h(
      SettingsGroup,
      { title: tx("When it sees a problem"), help: ["ai", "confidence"] },
      config.phase === "ok" &&
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
      { title: tx("The AI service"), help: ["ai", "start"] },
      h(AiKeySection, { aiKey }),
      config.phase === "ok" && h("div", { className: "oui-list" }, control("ai_send_reference")),
      config.phase === "ok" && control("ai_model"),
    ),
  );
}

/** One line for the menu list. */
function aiMonitorSummary(settings, brain) {
  const calibrated = brain.camcal && brain.camcal.phase === "ok" && brain.camcal.data.saved && brain.camcal.data.usable;
  return (calibrated ? tx("Whole bed") : tx("Outer band only")) + " • " + tx("Auto pause: {pause}", { pause: ON_OFF(settings.ai.autoPause) });
}
