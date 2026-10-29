/* ============================================================================
   59e · RECORDINGS
   The page "Registrazioni" of the settings menu: the backend keeps the pictures the AI monitor looked at during each
   print (backend/recorder.py), so that the monitor can be measured instead of guessed (roadmap, phase 3):
     · recording on/off and the space it may take (two settings of /api/backend/config, group "recording");
     · the alarms of the monitor with the AI's verdict, each marked by the person as "false alarm" or "real problem";
     · the recorded prints: look through the pictures, say "it went fine" or "it failed from here", delete;
     · "Measure the monitor": the backend runs the monitor again on every recording (scripts/replay.py) and the page
       shows how many alarms, how many false, whether the failures were caught.
   ========================================================================== */

const RECORDINGS_POLL_MS = 10000;
const MEASURE_POLL_MS = 2000;
const ALERTS_SHOWN = 20;
const alarmCount = (count) => (Number(count) === 1 ? tx("1 alarm") : tx("{count} alarms", { count }));
const printCount = (count) => (Number(count) === 1 ? tx("1 print") : tx("{count} prints", { count }));
const RECORDING_ID = /^\d{8}-\d{6}(-[A-Za-z0-9._-]{1,40})?$/;

/** "420 MB", "1.6 GB" */
function formatSpace(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value)) return "?";
  if (value >= 1024 ** 3) return (value / 1024 ** 3).toFixed(1).replace(".", ",") + " GB";
  return Math.round(value / 1024 ** 2) + " MB";
}

/** "2 h 05 min", "12 min", "45 s" */
function formatRecordingTime(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  if (s < 90) return s + " s";
  const minutes = Math.round(s / 60);
  if (minutes < 60) return minutes + " min";
  return Math.floor(minutes / 60) + " h " + String(minutes % 60).padStart(2, "0") + " min";
}

/** "1:23:45" from the start of the print */
function formatOffset(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  const hh = Math.floor(s / 3600);
  const mm = String(Math.floor((s % 3600) / 60)).padStart(hh ? 2 : 1, "0");
  return (hh ? hh + ":" : "") + mm + ":" + String(s % 60).padStart(2, "0");
}

const formatWhen = (unixSeconds) => {
  try {
    return new Date(Number(unixSeconds) * 1000).toLocaleString(LOCALE, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch (error) {
    return "";
  }
};

/** What the recorder says it is doing (backend/recorder.py, in English), in the page's language. */
const RECORDER_STATUS_TEXTS = [
  [/^off$/, () => tx("Recording is off.")],
  [/^waiting for a print$/, () => tx("Recording is on: it starts with the next print.")],
  [/^recording$/, () => tx("Recording this print now.")],
  [/^paused: less than 1 GB free on the disk$/, () => tx("Paused: less than 1 GB free on the disk.")],
  [/^stopped: this print alone fills the space for the recordings$/, () => tx("Stopped: this print alone fills the space for the recordings.")],
];
function recorderStatusText(status) {
  for (const [pattern, text] of RECORDER_STATUS_TEXTS) if (pattern.test(status || "")) return text();
  return status || "";
}

const END_STATE_TEXTS = { complete: txc("print", "completed"), cancelled: txc("print", "cancelled"), error: txc("print", "error"), standby: txc("print", "stopped") };

/** { phase: "loading" | "ok" | "old" | "down", data, reload } of GET url, read every `ms` while `active`. */
function useBackendJson(url, active, ms = RECORDINGS_POLL_MS) {
  const [state, setState] = useState({ phase: "loading", data: null });
  const reloadRef = useRef(noop);
  useEffect(() => {
    if (!active || !url) return undefined;
    let cancelled = false;
    const read = async () => {
      try {
        const response = await fetchFresh(url, { timeout: BRAIN_READ_TIMEOUT_MS });
        if (cancelled) return;
        if (response.status === 404) return setState((previous) => (previous.phase === "ok" && url.startsWith("/api/recordings/") ? { phase: "gone", data: null } : { phase: "old", data: null }));
        const data = await response.json();
        if (!cancelled) setState(response.ok && isPlainObject(data) ? { phase: "ok", data } : (previous) => ({ ...previous, phase: previous.phase === "ok" ? "ok" : "down" }));
      } catch (error) {
        if (!cancelled) setState((previous) => ({ ...previous, phase: previous.phase === "ok" ? "ok" : "down" }));
      }
    };
    reloadRef.current = read;
    const stop = startPolling(read, ms);
    return () => {
      cancelled = true;
      stop();
    };
  }, [url, active, ms]);
  return { ...state, reload: () => reloadRef.current() };
}

async function brainDelete(url) {
  try {
    const response = await fetch(url, { method: "DELETE" });
    return response.ok;
  } catch (error) {
    return false;
  }
}

/** The label of a print: what the person said, or what follows from the alarms they marked. */
function printLabel(session) {
  const label = (session && session.label) || {};
  if (label.outcome === "ok") return { tone: "ok", text: tx("Went fine") };
  if (label.outcome === "failed") return { tone: "danger", text: tx("Failed") };
  return { tone: "", text: tx("Not marked") };
}

/* ---------------------------------------------------------------------------
   The alarms with the AI's verdict, to be marked
   ------------------------------------------------------------------------- */
const ALERT_LABEL_OPTIONS = [
  { id: "false", label: tx("False alarm") },
  { id: "right", label: tx("Real problem") },
];

function AlertLabelButtons({ value, onChange, busy }) {
  return h(
    "div",
    { className: "rec-labels", role: "group", "aria-label": tx("Was it a real problem?") },
    ALERT_LABEL_OPTIONS.map((option) =>
      h(
        "button",
        {
          key: option.id,
          type: "button",
          disabled: busy,
          className: cx("oui-chip", value === option.id && "is-selected", option.id === "right" && "rec-labels__right"),
          "aria-pressed": value === option.id,
          onClick: () => onChange(value === option.id ? null : option.id),
        },
        option.label,
      ),
    ),
  );
}

/** What an alarm says, in the page's language (the backend writes its outcomes in English). */
function alertSummary(alert) {
  const outcome = String(alert.outcome || "");
  if (outcome.startsWith("skipped: AI cooldown")) return tx("Not analysed: the AI was resting between two analyses (before 1.19 these alarms were written; now the monitor waits for the AI).");
  if (outcome.startsWith("skipped: no AI key")) return tx("Not analysed: there is no AI key (Settings → AI monitor).");
  return alert.summary || alert.observation || outcome;
}

function AlertRow({ alert, onLabelled }) {
  const [label, setLabel] = useState(alert.label || null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  useEffect(() => setLabel(alert.label || null), [alert.id, alert.label]);
  const change = async (next) => {
    setBusy(true);
    const reply = await brainPost("/api/print/alerts/" + alert.id + "/label", { label: next });
    setBusy(false);
    if (reply.ok) {
      setLabel(next);
      setProblem("");
      onLabelled && onLabelled();
    } else setProblem(tx("Not saved: ") + (reply.message || tx("the backend does not answer")));
  };
  const action = aiAction(alert.action);
  const proposed = aiAction(alert.original_action); // the AI wanted to stop, the threshold made it "continue"
  const summary = alertSummary(alert);
  return h(
    "div",
    { className: "oui-tile rec-alert", "data-alert": alert.id },
    h(
      "div",
      { className: "rec-alert__head" },
      alert.image && h("img", { className: "rec-alert__img", src: "/api/print/alerts/image/" + alert.image, alt: tx("Picture of the alarm"), loading: "lazy" }),
      h(
        "div",
        { className: "rec-alert__text" },
        h(
          "div",
          { className: "rec-alert__when" },
          alert.time || "",
          proposed && proposed !== action
            ? h("span", { className: "oui-badge oui-badge--warn", "data-under": "1" }, tx("{action} proposed, under the threshold", { action: aiActionLabel(proposed) }))
            : action && h("span", { className: cx("oui-badge", action === "CONTINUE" ? "oui-badge--ok" : action === "PAUSE" ? "oui-badge--warn" : "oui-badge--danger") }, aiActionLabel(action)),
        ),
        proposed && proposed !== action && Number.isFinite(alert.confidence) && h("div", { className: "rec-alert__under" }, tx("Highest confidence of a defect: {confidence}%", { confidence: alert.confidence })),
        h("div", { className: "rec-alert__summary" }, summary),
      ),
    ),
    h(AlertLabelButtons, { value: label, onChange: change, busy }),
    problem && h("p", { className: "set-field__error", role: "alert" }, problem),
  );
}

function AlertsGroup({ active }) {
  const alerts = useBackendJson("/api/print/alerts/history?limit=" + ALERTS_SHOWN, active, RECORDINGS_POLL_MS * 3);
  const list = alerts.phase === "ok" && Array.isArray(alerts.data.alerts) ? alerts.data.alerts : [];
  const marked = list.filter((alert) => alert.label === "false" || alert.label === "right").length;
  return h(
    SettingsGroup,
    { title: tx("Alarms of the monitor"), note: tx("For each alarm say whether there really was a problem: this is how the false alarms are counted.") },
    list.length === 0
      ? h("p", { className: "set-group__note" }, alerts.phase === "ok" ? tx("No alarm so far.") : tx("Reading the alarms…"))
      : h(React.Fragment, null, h("p", { className: "set-group__note" }, tx("{marked} of {count} marked", { marked, count: list.length })), list.map((alert) => h(AlertRow, { key: alert.id, alert }))),
  );
}

/* ---------------------------------------------------------------------------
   One recording: pictures, label, alarms, delete
   ------------------------------------------------------------------------- */
function RecordingDetail({ id, onClose }) {
  const detail = useBackendJson(RECORDING_ID.test(id) ? "/api/recordings/" + id : null, true, RECORDINGS_POLL_MS * 3);
  const [index, setIndex] = useState(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [askDelete, setAskDelete] = useState(false);
  if (detail.phase === "gone") return h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), tx("This recording is no longer there."));
  if (detail.phase !== "ok") return h("div", { className: "set-status" }, h("span", { className: "set-status__dot" }), tx("Reading the recording…"));
  const session = detail.data.session;
  const frames = Array.isArray(detail.data.frames) ? detail.data.frames : [];
  const at = frames.length ? Math.min(frames.length - 1, Math.max(0, index === null ? frames.length - 1 : index)) : 0;
  const frame = frames[at];
  const alarmIndexes = frames.map((f, i) => (f.trig ? i : -1)).filter((i) => i >= 0);
  const label = session.label || {};
  const failedAt = label.outcome === "failed" ? label.failed_at : null;
  const setLabel = async (outcome, when) => {
    setBusy(true);
    const reply = await brainPost("/api/recordings/" + id + "/label", { outcome, failed_at: when });
    setBusy(false);
    setProblem(reply.ok ? "" : tx("Not saved: ") + (reply.message || tx("the backend does not answer")));
    detail.reload();
  };
  const remove = async () => {
    setBusy(true);
    const ok = await brainDelete("/api/recordings/" + id);
    setBusy(false);
    if (ok) onClose(true);
    else setProblem(tx("The recording was not deleted."));
  };
  const jump = (direction) => {
    const next = direction > 0 ? alarmIndexes.find((i) => i > at) : [...alarmIndexes].reverse().find((i) => i < at);
    if (next !== undefined) setIndex(next);
  };
  const failedFrame = failedAt !== null ? frames.findIndex((f) => f.t >= failedAt) : -1;
  return h(
    React.Fragment,
    null,
    h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm set-inline-btn", onClick: () => onClose(false) }, h(Icons.Back, { size: 16 }), tx("All the recordings")),
    h(
      SettingsGroup,
      { title: session.file || tx("(no file name)") },
      h(
        "div",
        { className: "oui-list set-info-list" },
        h(InfoLine, { label: tx("Started"), value: formatWhen(session.started) }),
        h(InfoLine, { label: tx("Duration"), value: session.ended ? formatRecordingTime(session.ended - session.started) + (END_STATE_TEXTS[session.end_state] ? " • " + END_STATE_TEXTS[session.end_state] : "") : tx("still printing") }),
        h(InfoLine, { label: tx("Pictures"), value: String(session.frames || 0) + (session.truncated ? " • " + tx("space full") : "") }),
        h(InfoLine, { label: tx("Alarms during the print"), value: String((session.live_triggers || []).length) }),
        session.cpu && session.cpu.cpu_percent !== undefined && h(InfoLine, { label: tx("Backend CPU"), value: tx("{percent}% of one core • {ms} ms per check", { percent: formatNumber(session.cpu.cpu_percent), ms: formatNumber(session.cpu.check_ms) }) }),
      ),
    ),
    frames.length > 0 &&
      h(
        SettingsGroup,
        { title: tx("Pictures") },
        h(
          "div",
          { className: "rec-viewer" },
          h("div", { className: "set-roi__frame" }, h("img", { className: "set-roi__img", src: "/api/recordings/" + id + "/frames/" + frame.n + ".jpg", alt: tx("Picture {number}", { number: frame.n }), draggable: false })),
          h(
            "div",
            { className: "rec-viewer__caption" },
            h("span", null, formatOffset(frame.t - session.started)),
            frame.layer !== null && frame.layer !== undefined && h("span", null, tx("layer {layer}", { layer: frame.layer + (frame.layers ? "/" + frame.layers : "") })),
            frame.score !== null && frame.score !== undefined && h("span", null, tx("score {score}%", { score: formatNumber(frame.score) })),
            frame.trig && h("span", { className: "oui-badge oui-badge--warn" }, tx("alarm")),
            frame.cool && h("span", { className: "rec-viewer__muted" }, tx("monitor resting")),
            failedFrame >= 0 && at >= failedFrame && h("span", { className: "oui-badge oui-badge--danger" }, tx("failed")),
          ),
          h("input", { type: "range", className: "set-num__range", "aria-label": tx("Picture"), min: 0, max: frames.length - 1, step: 1, value: at, onChange: (event) => setIndex(Number(event.target.value)) }),
          h(
            "div",
            { className: "rec-viewer__nav" },
            h("button", { type: "button", className: "oui-btn oui-btn--sm", disabled: !alarmIndexes.some((i) => i < at), onClick: () => jump(-1) }, tx("◀ Alarm")),
            h("button", { type: "button", className: "oui-btn oui-btn--sm", disabled: at === 0, onClick: () => setIndex(at - 1) }, "‹"),
            h("button", { type: "button", className: "oui-btn oui-btn--sm", disabled: at >= frames.length - 1, onClick: () => setIndex(at + 1) }, "›"),
            h("button", { type: "button", className: "oui-btn oui-btn--sm", disabled: !alarmIndexes.some((i) => i > at), onClick: () => jump(1) }, tx("Alarm ▶")),
          ),
        ),
      ),
    h(
      SettingsGroup,
      { title: tx("How did the print go?"), note: tx("If it failed, move to the first picture where the problem shows and press «It failed from here». Alarms before that moment count as false.") },
      h(
        "div",
        { className: "rec-outcome" },
        h("button", { type: "button", disabled: busy, className: cx("oui-chip", label.outcome === "ok" && "is-selected"), "aria-pressed": label.outcome === "ok", onClick: () => setLabel(label.outcome === "ok" ? null : "ok") }, tx("It went fine")),
        h("button", { type: "button", disabled: busy || !frame, className: cx("oui-chip", label.outcome === "failed" && "is-selected", "rec-labels__right"), "aria-pressed": label.outcome === "failed", onClick: () => setLabel("failed", frame.t) }, tx("It failed from here")),
        label.outcome && h("button", { type: "button", disabled: busy, className: "oui-chip", onClick: () => setLabel(null) }, tx("Clear")),
      ),
      failedAt !== null && h("p", { className: "set-group__note" }, tx("Failed from {time} after the start.", { time: formatOffset(failedAt - session.started) })),
      problem && h("p", { className: "set-field__error", role: "alert" }, problem),
    ),
    (session.alerts || []).length > 0 &&
      h(
        SettingsGroup,
        { title: tx("AI verdicts in this print") },
        session.alerts.map((alert) => h(AlertRow, { key: alert.id, alert: { ...alert, image: null }, onLabelled: detail.reload })),
      ),
    h(
      SettingsGroup,
      null,
      askDelete
        ? h(
            "div",
            { className: "set-confirm", role: "alertdialog", "aria-label": tx("Delete the recording?") },
            h("span", null, tx("The pictures of this print are deleted for good. Confirm?")),
            h("div", { className: "set-confirm__buttons" }, h("button", { type: "button", className: "oui-btn", onClick: () => setAskDelete(false) }, tx("No")), h("button", { type: "button", className: "oui-btn oui-btn--danger", disabled: busy, onClick: remove }, tx("Yes, delete"))),
          )
        : h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--block", onClick: () => setAskDelete(true) }, h(Icons.Trash, { size: 18 }), tx("Delete this recording")),
    ),
  );
}

/* ---------------------------------------------------------------------------
   Measuring the monitor (scripts/replay.py through the backend)
   ------------------------------------------------------------------------- */
function MeasureResult({ result }) {
  const total = result.total || {};
  const sessions = Array.isArray(result.sessions) ? result.sessions : [];
  if (!sessions.length) return h("p", { className: "set-group__note" }, tx("No recordings to measure yet."));
  const caught = (s) => (s.seen === null || s.seen === undefined ? "–" : s.seen ? tx("caught after {time}", { time: formatRecordingTime(s.delay_s) }) : tx("NOT caught"));
  return h(
    React.Fragment,
    null,
    h(
      "div",
      { className: "oui-list set-info-list" },
      h(InfoLine, { label: tx("Prints measured"), value: tx("{count} • {hours} h", { count: total.recordings, hours: formatNumber(total.hours) }) }),
      h(InfoLine, { label: tx("Alarms"), value: tx("{count} • {rate} per hour", { count: total.alarms, rate: total.per_hour === null ? "–" : formatNumber(total.per_hour) }) }),
      h(InfoLine, { label: tx("False alarms"), value: total.known_hours > 0 ? tx("{count} • {rate} per hour", { count: total.false, rate: formatNumber(total.false_per_hour) }) : tx("mark the prints to know"), warn: total.false > 0 }),
      h(InfoLine, { label: tx("Failures caught"), value: total.failures ? tx("{seen} of {count}", { seen: total.seen, count: total.failures }) + (total.average_delay_s !== null ? " • " + tx("after {time}", { time: formatRecordingTime(total.average_delay_s) }) : "") : tx("no failed print marked"), warn: total.failures > total.seen }),
      total.ms_per_check !== null && h(InfoLine, { label: tx("Time of one check"), value: formatNumber(total.ms_per_check) + " ms" }),
      total.unreadable_frames > 0 && h(InfoLine, { label: tx("Pictures skipped"), value: tx("{count} empty or broken (a power cut while recording)", { count: total.unreadable_frames }), warn: true }),
      total.masks &&
        h(InfoLine, {
          label: tx("Toolhead and gantry left out"),
          value: total.masks === "on" ? tx("yes, in {count} of {total} pictures", { count: total.masked_frames, total: total.frames }) : total.masks === "off" ? tx("no (switched off)") : tx("no: the camera is not calibrated"),
        }),
      total.zone &&
        h(InfoLine, {
          label: tx("Whole bed watched outside the parts"),
          value: total.zone === "on" ? tx("yes, in {count} of {total} pictures", { count: total.zoned_frames, total: total.frames }) : total.zone === "off" ? tx("no (switched off)") : tx("no: the camera is not calibrated"),
        }),
    ),
    h(
      "div",
      { className: "rec-measure" },
      sessions.map((s) =>
        h(
          "div",
          { key: s.id, className: "rec-measure__row" },
          h("div", { className: "rec-measure__file" }, s.file || s.id),
          h(
            "div",
            { className: "rec-measure__meta" },
            formatNumber(s.hours) + " h • " + alarmCount(s.alarms) + " • " + (s.false === null ? tx("false: ?") : tx("false: {count}", { count: s.false })) + (s.outcome === "failed" ? " • " + caught(s) : ""),
          ),
        ),
      ),
    ),
    h("p", { className: "set-group__note" }, tx("Measured with the thresholds in use now, on {when}. «?»: the print is not marked.", { when: formatWhen(result.time) })),
  );
}

function MeasureGroup({ count }) {
  const [state, setState] = useState({ phase: "loading" });
  const [starting, setStarting] = useState(false);
  const running = state.phase === "running";
  useEffect(() => {
    let cancelled = false;
    const read = async () => {
      try {
        const response = await fetchFresh("/api/recordings/measure", { timeout: BRAIN_READ_TIMEOUT_MS });
        const data = await response.json();
        if (!cancelled) setState(response.ok && isPlainObject(data) ? { phase: data.state, result: data.result } : { phase: "error" });
      } catch (error) {
        if (!cancelled) setState((previous) => (previous.phase === "loading" ? { phase: "error" } : previous));
      }
    };
    const stop = startPolling(read, running ? MEASURE_POLL_MS : RECORDINGS_POLL_MS * 6);
    return () => {
      cancelled = true;
      stop();
    };
  }, [running]);
  const start = async () => {
    setStarting(true);
    const reply = await brainPost("/api/recordings/measure", {});
    setStarting(false);
    setState(reply.ok ? { phase: "running" } : { phase: "error", result: { error: reply.message } });
  };
  return h(
    SettingsGroup,
    { title: tx("Measure the monitor"), note: tx("The backend runs the monitor again on every recorded print, with the thresholds in use now, and counts the alarms. It takes a minute or two; printing is not disturbed.") },
    h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", disabled: running || starting || !count, "data-measure": "start", onClick: start }, h(Icons.Play, { size: 18 }), running ? tx("Measuring…") : tx("Measure now")),
    state.phase === "error" && state.result && state.result.error && h("p", { className: "set-field__error", role: "alert" }, state.result.error),
    state.phase === "done" && state.result && h(MeasureResult, { result: state.result }),
  );
}

/* ---------------------------------------------------------------------------
   The page
   ------------------------------------------------------------------------- */
function RecordingRow({ session, onOpen }) {
  const label = printLabel(session);
  const duration = session.ended ? formatRecordingTime(session.ended - session.started) : tx("recording now");
  return h(
    "button",
    { type: "button", className: "set-entry rec-row", "data-recording": session.id, onClick: onOpen },
    h(
      "span",
      { className: "oui-row__text" },
      h("span", { className: "oui-row__name" }, session.file || tx("(no file name)")),
      h("span", { className: "oui-row__meta set-entry__meta" }, formatWhen(session.started) + " • " + duration + " • " + alarmCount(session.live_triggers || 0) + " • " + formatSpace(session.bytes)),
    ),
    h("span", { className: cx("oui-badge", label.tone && "oui-badge--" + label.tone) }, label.text),
    h("span", { className: "set-entry__go", "aria-hidden": "true" }, h(Icons.Forward)),
  );
}

function RecordingsPage({ active }) {
  const config = useBrainConfig(active);
  const list = useBackendJson("/api/recordings", active);
  const detector = useBackendJson("/api/print/detector/status", active, RECORDINGS_POLL_MS);
  const [openId, setOpenId] = useState(null);
  const schema = useMemo(() => (config.data ? localizeBrainSchema(config.data) : null), [config.data]);
  if (openId) {
    return h(RecordingDetail, {
      id: openId,
      onClose: () => {
        setOpenId(null);
        list.reload();
      },
    });
  }
  if (list.phase === "old" || config.phase === "old") {
    return h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), tx("The backend on the Raspberry does not record prints yet: update KlippEye (Settings → Updates)."));
  }
  if (list.phase !== "ok") return h(BrainNotice, { phase: list.phase === "loading" ? "loading" : "down" });
  const data = list.data;
  const specs = schema ? schema.spec.filter((spec) => spec.group === "recording") : [];
  const stats = detector.phase === "ok" && isPlainObject(detector.data.stats) ? detector.data.stats : {};
  const sessions = Array.isArray(data.sessions) ? data.sessions : [];
  return h(
    React.Fragment,
    null,
    h("div", { className: cx("set-status", data.status === "recording" ? "set-status--ok" : data.enabled ? "" : "set-status--warn") }, h("span", { className: "set-status__dot" }), recorderStatusText(data.status)),
    h(
      SettingsGroup,
      { title: tx("Recording"), note: tx("Used {used} of {limit}; {free} free on the disk.", { used: formatSpace(data.used_bytes), limit: formatSpace(data.max_bytes), free: data.free_bytes === null ? "?" : formatSpace(data.free_bytes) }) },
      config.phase === "ok" && specs.filter((spec) => spec.type === "bool").length > 0 && h("div", { className: "oui-list" }, specs.filter((spec) => spec.type === "bool").map((spec) => h(BrainSettingControl, { key: spec.key, spec, config }))),
      config.phase === "ok" && specs.filter((spec) => spec.type !== "bool").map((spec) => h(BrainSettingControl, { key: spec.key, spec, config })),
      config.problem && h("div", { className: "set-status set-status--warn", role: "alert" }, h("span", { className: "set-status__dot" }), config.problem),
    ),
    (stats.check_ms !== undefined || stats.cpu_percent !== undefined) &&
      h(
        SettingsGroup,
        { title: tx("Monitor load") },
        h(
          "div",
          { className: "oui-list set-info-list" },
          stats.check_ms !== undefined && h(InfoLine, { label: tx("Time of one check"), value: formatNumber(stats.check_ms) + " ms" }),
          stats.cpu_percent !== undefined && h(InfoLine, { label: tx("Backend CPU (last minute)"), value: tx("{percent}% of one core", { percent: formatNumber(stats.cpu_percent) }) }),
        ),
      ),
    h(AlertsGroup, { active }),
    h(
      SettingsGroup,
      { title: tx("Recorded prints") },
      sessions.length === 0
        ? h("p", { className: "set-group__note" }, data.enabled ? tx("No print recorded yet: the next one will be.") : tx("No print recorded. Turn on «Record the prints» above."))
        : h("div", { className: "oui-list" }, sessions.map((session) => h(RecordingRow, { key: session.id, session, onOpen: () => setOpenId(session.id) }))),
    ),
    h(MeasureGroup, { count: sessions.length }),
  );
}

/** One line for the menu list. */
function recordingsSummary(recordings) {
  if (!recordings || recordings.phase !== "ok") return tx("Measure the AI monitor");
  const data = recordings.data;
  const count = Array.isArray(data.sessions) ? data.sessions.length : 0;
  return (data.enabled ? tx("On") : tx("Off")) + " • " + printCount(count) + " • " + formatSpace(data.used_bytes);
}
