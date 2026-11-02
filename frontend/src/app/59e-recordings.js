/* ============================================================================
   59e · RECORDINGS
   The page "Registrazioni" of the settings menu: the backend keeps the pictures the AI monitor looked at during each
   print (backend/recorder.py), so that the monitor can be measured instead of guessed (roadmap, phase 3):
     · recording on/off and the space it may take (two settings of /api/backend/config, group "recording");
     · the recorded prints first (1.26): open one to look through its pictures, say "it went fine" or "it failed from
       here", delete; below, «Alarms of this print» opens the list of its alarms to judge (with their pictures);
     · "Measure the monitor": the backend runs the monitor again on the recordings chosen (scripts/replay.py) and the
       page shows how many alarms, how many false, whether the failures were caught;
     · "Precision of the AI" (1.28): on the judged alarms, how often the AI's response matched the real print and what each
       minimum confidence would have given (/api/print/alerts/precision);
     · "Measure and compare" (1.28): the replay also without the G-code zone, without the masks and with other thresholds;
     · the alarms that are in no recording, folded at the bottom.
   An alarm is judged against the AI's verdict (1.26.1): "Correct result" or "Wrong result". What is saved is whether the
   print really had a problem ("right") or not ("false"), so the two buttons swap meaning when the AI said to go on. An
   alarm the AI did not judge (an error of the AI service) is judged by the print: "There was a problem" / "No problem".
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
/** The two answers for one alarm. "label" is what is saved: "right" = the print had a problem, "false" = it had not. */
function alertLabelOptions(action) {
  if (action === "CONTINUE")
    return [
      { id: "false", tone: "good", label: tx("Correct result"), detail: tx("yes: the print really was fine") },
      { id: "right", tone: "bad", label: tx("Wrong result"), detail: tx("no: the print had a problem the AI missed") },
    ];
  if (action === "PAUSE" || action === "CANCEL")
    return [
      { id: "right", tone: "good", label: tx("Correct result"), detail: tx("yes: the print really had a problem") },
      { id: "false", tone: "bad", label: tx("Wrong result"), detail: tx("no: the print was fine (false alarm)") },
    ];
  return [
    { id: "right", tone: "bad", label: tx("There was a problem"), detail: tx("something was going wrong in the print") },
    { id: "false", tone: "good", label: tx("No problem"), detail: tx("the print was fine") },
  ];
}

function AlertLabelButtons({ action, value, onChange, busy }) {
  const judged = action === "CONTINUE" || action === "PAUSE" || action === "CANCEL";
  // 1.26.1: the question names the AI's verdict, so the answers cannot be read the other way round
  const question = judged ? tx("AI response: «{action}». Does it match the real state of the print?", { action: String(aiActionLabel(action)).charAt(0).toUpperCase() + String(aiActionLabel(action)).slice(1).toLowerCase() }) : tx("No AI response for this alarm: what was the real state of the print?");
  return h(
    React.Fragment,
    null,
    h("div", { className: "rec-labels__question" }, question),
    h(
    "div",
    { className: "rec-labels", role: "group", "aria-label": question },
    alertLabelOptions(action).map((option) =>
      h(
        "button",
        {
          key: option.id,
          type: "button",
          disabled: busy,
          className: cx("oui-chip rec-labels__chip", value === option.id && "is-selected", "rec-labels__" + option.tone),
          "aria-pressed": value === option.id,
          "data-label": option.id,
          onClick: () => onChange(value === option.id ? null : option.id),
        },
        h("span", { className: "rec-labels__main" }, option.label),
        h("span", { className: "rec-labels__detail" }, option.detail),
      ),
    ),
  ),
  );
}

/** When an alarm happened (its id is the local time "YYYYMMDD-HHMMSS"), as seconds since 1970. */
function alertSeconds(alert) {
  const match = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})$/.exec(String(alert.id || ""));
  if (!match) return null;
  return new Date(+match[1], +match[2] - 1, +match[3], +match[4], +match[5], +match[6]).getTime() / 1000;
}

/** What an alarm says, in the page's language (the backend writes its outcomes in English). */
function alertSummary(alert) {
  const outcome = String(alert.outcome || "");
  if (outcome.startsWith("skipped: AI cooldown")) return tx("Not analysed: the AI was resting between two analyses (before 1.19 these alarms were written; now the monitor waits for the AI).");
  if (outcome.startsWith("skipped: no AI key")) return tx("Not analysed: there is no AI key (Settings → AI monitor).");
  const error = /^AI error (\d+)/.exec(outcome);
  if (error) {
    const said = alert.error ? " " + tx("The service said: «{text}»", { text: alert.error }) : "";
    if (error[1] === "429") return tx("Not analysed: the AI service refused because it got too many requests (the limits of its plan, per minute or per day).") + said;
    if (error[1] === "401" || error[1] === "403") return tx("Not analysed: the AI service did not accept the key (Settings → AI monitor).") + said;
    return tx("Not analysed: the AI service answered with error {code}.", { code: error[1] }) + said;
  }
  if (outcome === "AI answer not readable") return tx("Not analysed: the AI's answer could not be read.");
  return alert.summary || alert.observation || outcome;
}

function AlertRow({ alert, session, onLabelled, onShow }) {
  const [label, setLabel] = useState(alert.label || null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  useEffect(() => setLabel(alert.label || null), [alert.id, alert.label]);
  const change = async (next) => {
    setBusy(true);
    // 1.26.2: with the recording, so an alarm that already left the alert history is labelled in its recording
    const reply = await brainPost("/api/print/alerts/" + alert.id + "/label", session ? { label: next, session } : { label: next });
    setBusy(false);
    if (reply.ok) {
      setLabel(next);
      setProblem("");
      onLabelled && onLabelled();
    } else setProblem(tx("Not saved: ") + (reply.message || tx("the backend does not answer")));
  };
  const action = aiAction(alert.action);
  const picture = alert.picture || (alert.image ? "/api/print/alerts/image/" + alert.image : null);
  const proposed = aiAction(alert.original_action); // the AI wanted to stop, the threshold made it "continue"
  const summary = alertSummary(alert);
  return h(
    "div",
    { className: "oui-tile rec-alert", "data-alert": alert.id },
    h(
      "div",
      { className: "rec-alert__head" },
      picture && h(ZoomablePhoto, { className: "rec-alert__img", src: picture, title: tx("Picture of the alarm") + (alert.time ? " • " + alert.time : ""), alt: tx("Picture of the alarm") }),
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
    h(AlertLabelButtons, { action: alert.action ? action : null, value: label, onChange: change, busy }),
    onShow && h("button", { type: "button", className: "oui-btn oui-btn--quiet oui-btn--sm set-inline-btn", "data-show-alert": alert.id, onClick: onShow }, h(Icons.Image, { size: 16 }), tx("See it among the pictures")),
    problem && h("p", { className: "set-field__error", role: "alert" }, problem),
  );
}

/** The alarms that belong to no recording (recording off, or a recording deleted): folded at the bottom of the page. */
function AlertsGroup({ active, recorded, open }) {
  const alerts = useBackendJson("/api/print/alerts/history?limit=" + ALERTS_SHOWN, active, RECORDINGS_POLL_MS * 3);
  const all = alerts.phase === "ok" && Array.isArray(alerts.data.alerts) ? alerts.data.alerts : [];
  const list = all.filter((alert) => !alert.session || !recorded.has(alert.session));
  const marked = list.filter((alert) => alert.label === "false" || alert.label === "right").length;
  if (alerts.phase === "ok" && list.length === 0) return null;
  return h(
    "details",
    { className: "set-group rec-loose", open: open || undefined, "data-loose-alerts": list.length },
    h("summary", { className: "set-group__label" }, tx("Alarms outside the recordings ({marked} of {count} judged)", { marked, count: list.length })),
    h("p", { className: "set-group__note" }, tx("The alarms of prints that were not recorded. For each say whether the AI was right: this is how the false alarms are counted.")),
    list.length === 0 ? h("p", { className: "set-group__note" }, tx("Reading the alarms…")) : list.map((alert) => h(AlertRow, { key: alert.id, alert })),
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
  const [view, setView] = useState("print"); // "print" | "alarms" (the list of the alarms to judge)
  const reveal = useRef(false); // after «See it among the pictures»: bring the pictures into view
  // the arrow of the menu and the phone's back: from the alarms to the print, from the print to the list of recordings
  useBackHandler(() => {
    if (view === "alarms") setView("print");
    else onClose(false);
    return true;
  });
  useEffect(() => {
    const body = document.querySelector(".drawer__body");
    if (view === "print" && reveal.current) {
      reveal.current = false;
      const viewer = document.querySelector(".rec-viewer");
      if (viewer && viewer.scrollIntoView) viewer.scrollIntoView({ block: "center" });
    } else if (body) body.scrollTop = 0;
  }, [view]);
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
  const alerts = Array.isArray(session.alerts) ? session.alerts : [];
  const judged = alerts.filter((alert) => alert.label === "false" || alert.label === "right").length;
  const showAlert = (alert) => {
    // the picture of the alarm (the recording notes it), else the one nearest to its time
    let picture = frames.findIndex((f) => f.n === alert.frame);
    const when = Number.isFinite(alert.t) ? alert.t : alertSeconds(alert);
    if (picture < 0 && when !== null && frames.length) {
      picture = 0;
      frames.forEach((f, i) => {
        if (Math.abs(f.t - when) < Math.abs(frames[picture].t - when)) picture = i;
      });
    }
    if (picture < 0) return;
    setIndex(picture);
    reveal.current = true;
    setView("print");
  };
  if (view === "alarms") {
    return h(
      SettingsGroup,
      { title: tx("Alarms of this print ({judged} of {count} judged)", { judged, count: alerts.length }), help: ["recordings", "judge"], note: tx("An alarm is a moment when the camera saw something change; the AI then looked and answered continue, pause or cancel. For each one say whether the AI's response matches the real state of the print. «See it among the pictures» goes back to the print, at the moment of the alarm.") },
      alerts.length === 0 ? h("p", { className: "set-group__note" }, tx("No alarm in this print.")) : alerts.map((alert) => h(AlertRow, { key: alert.id, alert, session: id, onLabelled: detail.reload, onShow: frames.length ? () => showAlert(alert) : null })),
    );
  }
  return h(
    React.Fragment,
    null,
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
          h("div", { className: "set-roi__frame" }, h(ZoomablePhoto, { className: "rec-viewer__photo", src: "/api/recordings/" + id + "/frames/" + frame.n + ".jpg", title: (session.file || "") + " • " + formatOffset(frame.t - session.started), alt: tx("Picture {number}", { number: frame.n }) })),
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
    alerts.length > 0 &&
      h(
        SettingsGroup,
        { title: tx("Judge the alarms"), help: ["recordings", "judge"] },
        h(
          "div",
          { className: "oui-list" },
          h(
            "button",
            { type: "button", className: "set-entry rec-row", "data-open-alarms": alerts.length, onClick: () => setView("alarms") },
            h("span", { className: "oui-row__text" }, h("span", { className: "oui-row__name" }, tx("Alarms of this print")), h("span", { className: "oui-row__meta set-entry__meta" }, alarmCount(alerts.length) + " • " + tx("{judged} of {count} judged", { judged, count: alerts.length }))),
            h("span", { className: cx("oui-badge", judged === alerts.length ? "oui-badge--ok" : "oui-badge--warn") }, judged === alerts.length ? tx("All judged") : tx("To judge")),
            h("span", { className: "set-entry__go", "aria-hidden": "true" }, h(Icons.Forward)),
          ),
        ),
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

/* ---------------------------------------------------------------------------
   1.28 (roadmap 6a part 4): what weighs and where there is margin
   ------------------------------------------------------------------------- */
const COMPARE_TEXTS = {
  no_zone: { title: tx("Without the G-code zone"), detail: tx("only the outer band of the picture, as without the objects of the print") },
  no_masks: { title: tx("Without leaving out toolhead and gantry"), detail: tx("as with a camera that is not calibrated") },
  less_sensitive: { title: tx("Less sensitive"), detail: tx("change threshold {value}%") },
  more_sensitive: { title: tx("More sensitive"), detail: tx("change threshold {value}%") },
  more_checks: { title: tx("One more check in a row"), detail: tx("{value} checks in a row before an alarm") },
};

/** One line of numbers: alarms per hour, false alarms per hour, problems caught. */
function measureNumbers(total) {
  const parts = [tx("{rate} alarms per hour", { rate: total.per_hour === null || total.per_hour === undefined ? "–" : formatNumber(total.per_hour) })];
  parts.push(total.known_hours > 0 ? tx("{rate} false per hour", { rate: formatNumber(total.false_per_hour) }) : tx("false: ?"));
  if (total.failures) parts.push(tx("problems caught {seen} of {count}", { seen: total.seen, count: total.failures }));
  return parts.join(" • ");
}

/** Compared with the settings in use: "better" (fewer false alarms, no problem lost), "worse", or "same". */
function compareVerdict(now, other) {
  const seenNow = now.seen || 0;
  const seenOther = other.seen || 0;
  if (seenOther < seenNow) return "worse";
  const falseNow = now.known_hours > 0 ? now.false_per_hour : null;
  const falseOther = other.known_hours > 0 ? other.false_per_hour : null;
  if (falseNow === null || falseOther === null) return other.alarms < now.alarms ? "fewer" : other.alarms > now.alarms ? "more" : "same";
  if (falseOther < falseNow - 0.005 || seenOther > seenNow) return "better";
  if (falseOther > falseNow + 0.005) return "worse";
  return "same";
}

const VERDICT_BADGES = {
  better: ["ok", tx("better")],
  worse: ["danger", tx("worse")],
  same: ["", tx("same")],
  fewer: ["", tx("fewer alarms")],
  more: ["", tx("more alarms")],
};

function CompareResult({ result }) {
  const now = result.total || {};
  const rows = Array.isArray(result.compare) ? result.compare : [];
  return h(
    "div",
    { className: "rec-compare", "data-compare": rows.length },
    h("div", { className: "set-field__label fn-subtitle" }, tx("What weighs, and where there is margin")),
    h(
      "div",
      { className: "rec-measure" },
      h("div", { className: "rec-measure__row", "data-variant": "now" }, h("div", { className: "rec-measure__file" }, tx("As in use now")), h("div", { className: "rec-measure__meta" }, measureNumbers(now))),
      rows.map((row) => {
        const text = COMPARE_TEXTS[row.id] || { title: row.id, detail: "" };
        const value = Object.values(row.overrides || {})[0];
        const verdict = VERDICT_BADGES[compareVerdict(now, row.total || {})];
        return h(
          "div",
          { key: row.id, className: "rec-measure__row", "data-variant": row.id },
          h("div", { className: "rec-compare__head" }, h("span", { className: "rec-measure__file" }, text.title), h("span", { className: cx("oui-badge", verdict[0] && "oui-badge--" + verdict[0]) }, verdict[1])),
          h("div", { className: "rec-measure__meta" }, i18nFill(text.detail, { value: typeof value === "number" ? formatNumber(value) : value })),
          h("div", { className: "rec-measure__meta" }, measureNumbers(row.total || {})),
        );
      }),
    ),
    h("p", { className: "set-group__note" }, tx("«Better»: fewer false alarms and no problem lost. The G-code zone and the masks weigh as much as the difference with their line; a threshold with «better» has margin (Monitor thresholds).")),
  );
}

/** How often the AI's verdict matched the real print, on the alarms you judged (1.28). */
function AiPrecisionGroup({ active }) {
  const data = useBackendJson("/api/print/alerts/precision", active, RECORDINGS_POLL_MS * 3);
  const config = useBrainConfig(active);
  if (data.phase !== "ok") return null;
  const p = data.data;
  const pct = (value) => (value === null || value === undefined ? "–" : value + "%");
  const current = p.current;
  const advice = p.advice;
  return h(
    SettingsGroup,
    { title: tx("Precision of the AI"), help: ["recordings", "precision"] },
    p.judged === 0
      ? h("p", { className: "set-group__note", "data-precision": "empty" }, tx("No alarm judged yet. Judge the alarms (in each recorded print, or in the print card during a print): this is where you see how often the AI was right."))
      : h(
          React.Fragment,
          null,
          h(
            "div",
            { className: "oui-list set-info-list", "data-precision": p.judged },
            h(InfoLine, { label: tx("Alarms judged"), value: String(p.judged) + (p.no_verdict ? " • " + tx("{count} without a response of the AI", { count: p.no_verdict }) : "") }),
            h(InfoLine, { label: tx("Response matching the print"), value: pct(p.correct_pct) }),
            h(InfoLine, { label: tx("Pauses that were right"), value: tx("{right} of {count}", { right: p.stop_right, count: p.stop_right + p.stop_wrong }) + " • " + pct(p.stop_pct) }),
            h(InfoLine, { label: tx("Problems it stopped"), value: tx("{right} of {count}", { right: p.stop_right, count: p.stop_right + p.continue_wrong }) + " • " + pct(p.caught_pct), warn: p.continue_wrong > 0 }),
            h(InfoLine, { label: tx("False stops"), value: String(p.stop_wrong), warn: p.stop_wrong > 0 }),
            h(InfoLine, { label: tx("Problems missed («continue»)"), value: String(p.continue_wrong), warn: p.continue_wrong > 0 }),
          ),
          !p.enough && h("p", { className: "set-group__note", "data-precision-few": "1" }, tx("Only {count} alarms judged: a first idea. With at least 10 the numbers start to mean something.", { count: p.judged })),
          p.thresholds && p.thresholds.length > 0 && p.thresholds[0].judged > 0 &&
            h(
              React.Fragment,
              null,
              h("div", { className: "set-field__label fn-subtitle" }, tx("Minimum AI confidence: what each value would have given")),
              h(
                "div",
                { className: "rec-thresholds", role: "table" },
                h("div", { className: "rec-thresholds__row rec-thresholds__row--head", role: "row" }, h("span", null, tx("Minimum")), h("span", null, tx("False stops")), h("span", null, tx("Missed"))),
                p.thresholds.map((row) =>
                  h(
                    "div",
                    { key: row.threshold, role: "row", className: cx("rec-thresholds__row", row.threshold === current && "is-current", advice && advice.kind !== "keep" && advice.threshold === row.threshold && "is-best"), "data-threshold": row.threshold },
                    h("span", null, row.threshold + "%" + (row.threshold === current ? " • " + tx("in use") : "")),
                    h("span", null, String(row.false_stops)),
                    h("span", { className: row.missed ? "rec-thresholds__warn" : "" }, String(row.missed)),
                  ),
                ),
              ),
              advice &&
                h(
                  "p",
                  { className: "set-group__note", "data-advice": advice.kind },
                  advice.kind === "keep"
                    ? tx("On your alarms the minimum in use ({value}%) is as good as any other: no change needed.", { value: current })
                    : tx("On your alarms {value}% would have given {missed} problems missed and {false} false stops: better than the one in use.", { value: advice.threshold, missed: advice.missed, false: advice.false_stops }),
                ),
              advice && advice.kind !== "keep" && p.enough && config.phase === "ok" &&
                h("button", { type: "button", className: "oui-btn oui-btn--sm", "data-use-threshold": advice.threshold, onClick: () => config.set({ ai_min_confidence: advice.threshold }) }, tx("Use {value}%", { value: advice.threshold })),
            ),
        ),
  );
}

const MEASURE_SKIP_KEY = "ke_measure_skip"; // the recordings left out of the measurement, on this device

function readSkipped() {
  try {
    const list = JSON.parse(storage.get(MEASURE_SKIP_KEY) || "[]");
    return new Set(Array.isArray(list) ? list.filter((id) => RECORDING_ID.test(id)) : []);
  } catch (error) {
    return new Set();
  }
}

function MeasureGroup({ sessions }) {
  const [state, setState] = useState({ phase: "loading" });
  const [starting, setStarting] = useState(false);
  const [skipped, setSkipped] = useState(readSkipped);
  const usable = sessions.filter((session) => session.ended);
  const chosen = usable.filter((session) => !skipped.has(session.id));
  const count = chosen.length;
  const toggle = (id) => {
    const next = new Set(skipped);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSkipped(next);
    storage.set(MEASURE_SKIP_KEY, JSON.stringify([...next]));
  };
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
  const start = async (compare) => {
    setStarting(true);
    const body = chosen.length === usable.length ? {} : { ids: chosen.map((session) => session.id) };
    if (compare === true) body.compare = true;
    const reply = await brainPost("/api/recordings/measure", body);
    setStarting(false);
    setState(reply.ok ? { phase: "running" } : { phase: "error", result: { error: reply.message } });
  };
  return h(
    SettingsGroup,
    { title: tx("Measure the monitor"), help: ["recordings", "measure"], note: tx("The backend runs the monitor again on the recorded prints chosen here, with the thresholds in use now, and counts the alarms. It takes a minute or two; printing is not disturbed.") },
    usable.length > 0 &&
      h(
        "details",
        { className: "rec-choose", "data-measure-choose": "1" },
        h("summary", null, tx("Prints to use: {count} of {total}", { count, total: usable.length })),
        h(
          "div",
          { className: "rec-choose__list" },
          usable.map((session) =>
            h(
              "label",
              { key: session.id, className: "rec-choose__row" },
              h("input", { type: "checkbox", checked: !skipped.has(session.id), "data-measure-use": session.id, onChange: () => toggle(session.id) }),
              h(
                "span",
                { className: "rec-choose__text" },
                h("span", { className: "rec-choose__name" }, session.file || session.id),
                h("span", { className: "rec-choose__meta" }, formatWhen(session.started) + " • " + printLabel(session).text),
              ),
            ),
          ),
        ),
      ),
    h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", disabled: running || starting || !count, "data-measure": "start", onClick: () => start(false) }, h(Icons.Play, { size: 18 }), running ? tx("Measuring…") : tx("Measure now")),
    h("button", { type: "button", className: "oui-btn oui-btn--block", disabled: running || starting || !count, "data-measure": "compare", onClick: () => start(true) }, tx("Measure and compare the options")),
    h("p", { className: "set-group__note" }, tx("«Measure and compare» also replays the prints without the G-code zone, without the masks and with other thresholds, to show what each weighs: it takes a few minutes.")),
    state.phase === "error" && state.result && state.result.error && h("p", { className: "set-field__error", role: "alert" }, state.result.error),
    state.phase === "done" && state.result && h(MeasureResult, { result: state.result }),
    state.phase === "done" && state.result && Array.isArray(state.result.compare) && h(CompareResult, { result: state.result }),
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
  const recorded = new Set(sessions.map((session) => session.id));
  return h(
    React.Fragment,
    null,
    h("div", { className: cx("set-status", data.status === "recording" ? "set-status--ok" : data.enabled ? "" : "set-status--warn") }, h("span", { className: "set-status__dot" }), recorderStatusText(data.status)),
    // 1.26: the prints first; their alarms are judged inside each of them
    h(
      SettingsGroup,
      { title: tx("Recorded prints"), help: ["recordings", "judge"], note: sessions.length ? tx("Open a print to judge its alarms and look through its pictures.") : null },
      sessions.length === 0
        ? h("p", { className: "set-group__note" }, data.enabled ? tx("No print recorded yet: the next one will be.") : tx("No print recorded. Turn on «Record the prints» below."))
        : h("div", { className: "oui-list" }, sessions.map((session) => h(RecordingRow, { key: session.id, session, onOpen: () => setOpenId(session.id) }))),
    ),
    h(AiPrecisionGroup, { active }),
    h(MeasureGroup, { sessions }),
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
    h(AlertsGroup, { active, recorded, open: sessions.length === 0 }),
  );
}

/** One line for the menu list. */
function recordingsSummary(recordings) {
  if (!recordings || recordings.phase !== "ok") return tx("Measure the AI monitor");
  const data = recordings.data;
  const count = Array.isArray(data.sessions) ? data.sessions.length : 0;
  return (data.enabled ? tx("On") : tx("Off")) + " • " + printCount(count) + " • " + formatSpace(data.used_bytes);
}
