/* ============================================================================
   55 · AI PRINT MONITOR
   The backend watches the webcam while a print runs (OpenCV) and, when
   something looks wrong, asks an AI to judge it. This file polls both and
   feeds three places (1.25):
     · the round "AI" badge in the header (grey / green / amber / red): a tap opens
       the AI monitoring panel (it was a card of the Config page);
     · the question in the print card: was the alarm right, false, or to ignore?
       ("false" and "ignore" put the badge back to green until the next alarm);
     · the panel itself.
   The backend closes the alarm at the start and at the end of every print, so the
   badge and the verdict always belong to the print that is running.
   ========================================================================== */

const AI_MONITOR_POLL_MS = 4000;

/** The action ("CONTINUE" | "PAUSE" | "CANCEL") a verdict recommends, or "". */
function recommendedAction(verdict) {
  if (!verdict) return "";
  return aiAction(verdict.analysis && verdict.analysis.action ? verdict.analysis.action : verdict.action);
}

/* ---------------------------------------------------------------------------
   What the detector's status text means
   ------------------------------------------------------------------------- */
const includesAny = (text, words) => words.some((word) => text.includes(word));

/** Header badge for the current detector status; undefined = leave it as it is. `answer`: the person's answer to the alarm. */
function headerBadgeFor(stats, action, answer) {
  const status = stats.status;
  const lower = (status || "").toLowerCase();
  const idle = includesAny(lower, ["idle", "complete", "cancelled", "error"]) || status === "" || (lower === "" && stats.frames_checked === 0);
  if (idle) return AI_BADGES.idle;
  if (answer === "false" || answer === "ignore") return AI_BADGES.monitoring; // a false alarm, or one to ignore: green until the next one
  const printingNow = includesAny(lower, ["scanning", "triggered"]) || (stats.frames_checked > 0 && !lower.includes("idle"));
  const recommended = aiAction(action);
  if (!recommended) return printingNow ? AI_BADGES.monitoring : undefined;
  if (recommended === "CANCEL") return AI_BADGES.critical;
  if (recommended === "PAUSE") return AI_BADGES.pause;
  return AI_BADGES.ok;
}

const AI_BADGES = {
  idle: { rgb: "140,146,160", hex: "#8c92a0", glow: 0, title: tx("AI monitor: waiting for a print"), idle: true },
  monitoring: { rgb: "61,220,138", hex: "#3ddc8a", glow: 0.35, title: tx("Monitoring OK") },
  ok: { rgb: "61,220,138", hex: "#3ddc8a", glow: 0.35, title: tx("Print OK") },
  critical: { rgb: "255,93,93", hex: "#ff5d5d", glow: 0.45, title: tx("Critical defect - CANCEL") },
  pause: { rgb: "255,183,64", hex: "#ffb740", glow: 0.4, title: tx("Defect - PAUSE suggested") },
};

/**
 * The detector's status line, written by the backend in English (1.7.0), in the page's language. Technical words
 * (idle, scanning, TRIGGERED, cooldown) stay as they are; an Italian line of an older backend passes unchanged.
 */
const DETECTOR_STATUS_TEXTS = [
  [/^idle - waiting for a print$/, () => tx("idle - waiting for a print")],
  [/^heating\/mesh - waiting for the real print(.*)$/, (m) => tx("heating/mesh - waiting for the real print") + m[1]],
  [/^preparing the comparison \((\d+)\/(\d+) pictures\)$/, (m) => tx("preparing the comparison ({count}/{total} pictures)", { count: m[1], total: m[2] })],
  [/^light change or camera moved \((\d+)% of the picture\): ignored$/, (m) => tx("light change or camera moved ({percent}% of the picture): ignored", { percent: m[1] })],
  [/^scanning \(large lasting change\)$/, () => tx("scanning") + " (" + tx("large lasting change") + ")"],
  [/^cv2 not installed$/, () => tx("OpenCV not installed")],
];
function detectorStatusText(status) {
  for (const [pattern, text] of DETECTOR_STATUS_TEXTS) {
    const match = pattern.exec(status);
    if (match) return text(match);
  }
  return status;
}

/** Card header pill + dot for the detector status. */
function describeDetector(json) {
  const stats = json.stats || {};
  const status = stats.status || "";
  const printing = status.includes("scanning") || status.includes("TRIGGERED");
  const idle = status.includes("idle") || status.includes("state=");
  const realStarted = json.real_print_started !== undefined ? json.real_print_started : stats.real_print_started;

  let pill = { text: tx("Waiting for a print"), tone: "waiting" };
  if (realStarted === false && /heating|riscaldamento/i.test(status)) pill = { text: tx("Heating/mesh - waiting for the real print"), tone: "warming" };
  else if (printing) pill = { text: tx("Monitoring on • printing"), tone: "active" };

  return {
    state: detectorStatusText(status || "idle").slice(0, 30),
    score: (stats.last_score || 0) + "%",
    checks: stats.frames_checked || 0,
    dot: printing ? "active" : idle ? "idle" : "warming",
    pill,
    realStarted,
    realReason: json.real_print_reason || stats.real_print_reason || stats.status,
    progress: json.progress !== undefined ? json.progress : stats.progress,
  };
}

/* ---------------------------------------------------------------------------
   Polling
   ------------------------------------------------------------------------- */
const IDLE_DETECTOR = { state: "idle", score: "0%", checks: 0, dot: "idle", pill: { text: tx("Waiting for a print"), tone: "waiting" }, realStarted: undefined, realReason: "" };

function verdictOf(response) {
  return { verdict: response.analysis, model: response.model, progress: response.progress, timestamp: response.timestamp, alertId: response.alert_id || "", image: response.image || "", answer: response.answer || "" };
}

/** Is this verdict an alarm (the AI proposes to pause or cancel the print)? */
const isAlarm = (latest) => Boolean(latest && latest.verdict && ["PAUSE", "CANCEL"].includes(recommendedAction(latest.verdict)));

/** { detector, latest, badge, answer(answer) }: always running, whatever page is open. */
function useAiMonitor() {
  const [detector, setDetector] = useState(IDLE_DETECTOR);
  const [latest, setLatest] = useState(null);
  const [badge, setBadge] = useState(AI_BADGES.idle);
  const latestRef = useRef(latest);
  const statsRef = useRef({});

  const show = (next) => {
    latestRef.current = next;
    setLatest(next);
    const nextBadge = headerBadgeFor(statsRef.current, recommendedAction(next && next.verdict), next && next.answer);
    if (nextBadge !== undefined) setBadge(nextBadge);
  };

  useEffect(() => {
    let cancelled = false;
    let firstPollDone = false;
    try {
      storage.remove(STORAGE_KEYS.lastAiAnalysis); // the copy kept by releases before 1.25: the backend is the only one now
      storage.remove(STORAGE_KEYS.lastAiAnalysisTime);
    } catch (e) {}

    const poll = async () => {
      try {
        const status = await fetchJson("/api/print/detector/status");
        if (cancelled || !status.ok) return;
        statsRef.current = status.stats || {};
        setDetector(describeDetector(status));
        const fresh = await fetchJson("/api/print/last_analysis");
        if (cancelled || !fresh.ok) return;
        if (!fresh.has_analysis) {
          // the backend closed the alarm (a print started or ended): nothing to show any more
          if (latestRef.current) show(null);
          else {
            const nextBadge = headerBadgeFor(statsRef.current, "", "");
            if (nextBadge !== undefined) setBadge(nextBadge);
          }
          return;
        }
        // `initial` marks the verdict found when the page opens: it is shown, but never scrolled to
        const next = { ...verdictOf(fresh), initial: !firstPollDone };
        const before = latestRef.current;
        if (!before || JSON.stringify(next.verdict) !== JSON.stringify(before.verdict) || next.answer !== before.answer || next.alertId !== before.alertId) show(next);
        else {
          const nextBadge = headerBadgeFor(statsRef.current, recommendedAction(before.verdict), before.answer);
          if (nextBadge !== undefined) setBadge(nextBadge);
        }
      } catch (e) {
      } finally {
        firstPollDone = true;
      }
    };

    const stopPolling = startPolling(poll, AI_MONITOR_POLL_MS);
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, []);

  /** The person's answer to the alarm: "right" | "false" | "ignore". Shown at once, then confirmed by the backend. */
  const answer = async (value) => {
    const current = latestRef.current;
    if (!current) return false;
    show({ ...current, answer: value, initial: true });
    try {
      const response = await fetch("/api/print/last_analysis/answer", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ answer: value }) });
      if (response.ok) return true;
    } catch (e) {}
    show({ ...current, initial: true }); // not saved: the question comes back
    toast.notice(tx("The answer did not reach the Raspberry: try again"), 3000);
    return false;
  };

  return { detector, latest, badge, answer };
}

/* ---------------------------------------------------------------------------
   Header badge: always there; a tap opens the AI monitoring panel
   ------------------------------------------------------------------------- */
const aiPanelListeners = new Set();
let aiPanelOpen = false;
function openAiPanel() {
  aiPanelOpen = true;
  aiPanelListeners.forEach((listener) => listener(true));
}
function closeAiPanel() {
  aiPanelOpen = false;
  aiPanelListeners.forEach((listener) => listener(false));
}

function AiHeaderBadge({ badge }) {
  const shown = badge || AI_BADGES.idle;
  const tone = { "--ai-hex": shown.hex, "--ai-rgb": shown.rgb, "--ai-glow": shown.glow };
  return h(
    "button",
    { type: "button", className: cx("ai-header-badge", shown.idle && "ai-header-badge--idle"), title: shown.title + " • " + tx("tap for the details"), "aria-label": tx("AI monitoring") + ": " + shown.title, style: tone, "data-ai-badge": shown.idle ? "idle" : "on", onClick: openAiPanel },
    h("span", { className: "ai-header-badge__dot" }),
    h("span", { className: "ai-header-badge__label" }, "AI"),
  );
}

/* ---------------------------------------------------------------------------
   Card
   ------------------------------------------------------------------------- */
const DETECTOR_PILLS = { waiting: "oui-badge", warming: "oui-badge oui-badge--warn", active: "oui-badge oui-badge--ok" };

function MonitorTile({ label, children }) {
  return h("div", { className: "oui-tile monitor-tile" }, h("div", { className: "oui-caption" }, label), h("div", { className: "ai-metric" }, children));
}

/** Banner for a verdict that recommends stopping or pausing. */
function VerdictAlert({ latest }) {
  const action = aiAction(latest.verdict.action);
  const proposed = aiAction(latest.verdict.original_action);
  if (action === "CONTINUE" && proposed && proposed !== "CONTINUE") {
    // the AI wanted to stop the print, the minimum confidence made it "continue": said, not hidden behind a green verdict
    return h(
      "div",
      { className: "ai-alert ai-alert--warn", "data-under": "1" },
      h("div", { className: "flex items-center justify-between gap-2" }, h("span", { className: "ai-alert__title" }, tx("{action} proposed, under the threshold", { action: aiActionLabel(proposed) })), h("span", { className: "oui-caption" }, latest.timestamp || "")),
      h("div", { className: "ai-alert__text" }, latest.verdict.summary || ""),
    );
  }
  if (!action || action === "CONTINUE") return h("div", { className: "ai-alert hidden" });
  return h(
    "div",
    { className: cx("ai-alert", action === "CANCEL" ? "ai-alert--danger" : "ai-alert--warn") },
    h("div", { className: "flex items-center justify-between gap-2" }, h("span", { className: "ai-alert__title" }, tx("Suggested action: ") + aiActionLabel(action)), h("span", { className: "oui-caption" }, latest.timestamp || "")),
    h("div", { className: "ai-alert__text" }, latest.verdict.summary || ""),
  );
}

function AiMonitorCard({ monitor, bare }) {
  const { detector, latest } = monitor;
  const resultRef = useRef(null);
  const shownVerdict = useRef(latest && JSON.stringify(latest.verdict));

  // A new verdict that arrives while the card is open is scrolled into view
  // (the one found at page load is not: the page stays where it is).
  useEffect(() => {
    const serialized = latest && JSON.stringify(latest.verdict);
    if (serialized && serialized !== shownVerdict.current && !latest.initial && resultRef.current) resultRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    shownVerdict.current = serialized;
  }, [latest]);

  const verdictText = latest ? latest.verdict.analysis || JSON.stringify(latest.verdict) : "";
  return h(
    bare ? "div" : Card,
    bare ? { className: "ai-panel__card" } : null,
    !bare &&
      h(
        "div",
        { className: "ai-card-head" },
        h(SectionTitle, null, tx("Automatic AI monitoring")),
      ),
    h(
      "div",
      { className: cx(DETECTOR_PILLS[detector.pill.tone], "ai-status") },
      detector.dot !== "idle" && h("span", { className: cx("oui-dot", detector.dot === "active" && "ai-dot--pulse") }),
      detector.pill.text,
    ),
    h(
      "div",
      { className: "monitor-grid" },
      h(MonitorTile, { label: tx("Status") }, detector.state),
      h(MonitorTile, { label: tx("OpenCV score") }, detector.score),
      h(MonitorTile, { label: tx("Checks") }, detector.checks),
    ),
    latest ? h(VerdictAlert, { latest }) : h("div", { className: "ai-alert hidden" }),
    latest && alarmPhoto(latest) && h(ZoomablePhoto, { src: alarmPhoto(latest), title: tx("What the AI monitor saw") + (latest.timestamp ? " • " + latest.timestamp : ""), className: "ai-panel__photo" }),
    isAlarm(latest) && latest.answer && h("p", { className: "oui-caption", "data-ai-answered": latest.answer }, AI_ANSWER_TEXT[latest.answer]),
    !latest && h("p", { className: "oui-caption ai-panel__empty" }, tx("No alarm in this print.")),
    h("div", { ref: resultRef, className: cx("ai-result", !latest && "hidden") }, latest && h(PrintAnalysis, { text: verdictText, progress: latest.progress, detector })),
  );
}

/* ---------------------------------------------------------------------------
   The alarm, with the person's answer (1.25)
   ------------------------------------------------------------------------- */
const AI_ANSWERS = [
  { id: "right", label: tx("Real problem"), detail: tx("The AI was right") },
  { id: "false", label: tx("False alarm"), detail: tx("The print is fine") },
  { id: "ignore", label: tx("Ignore"), detail: tx("Not a failure, but nothing to stop for") },
];
const AI_ANSWER_TEXT = {
  right: tx("You said it is a real problem: pause or cancel the print if needed."),
  false: tx("Marked as a false alarm: it helps measure the monitor. The badge is green until the next alarm."),
  ignore: tx("Ignored: the badge is green until the next alarm."),
};

const alarmPhoto = (latest) => (latest && latest.image ? "/api/print/alerts/image/" + latest.image : "");

/** In the print card: what the AI saw, and three buttons. Gone once answered "false" or "ignore". */
function AiAlarmQuestion({ monitor }) {
  const latest = monitor && monitor.latest;
  const [busy, setBusy] = useState(false);
  if (!isAlarm(latest) || latest.answer === "false" || latest.answer === "ignore") return null;
  const action = recommendedAction(latest.verdict);
  const answered = latest.answer === "right";
  const send = async (value) => {
    setBusy(true);
    await monitor.answer(value);
    setBusy(false);
  };
  return h(
    "div",
    { className: cx("ai-question", action === "CANCEL" ? "ai-question--danger" : "ai-question--warn"), role: "alert", "data-ai-question": answered ? "answered" : "open" },
    h(
      "div",
      { className: "ai-question__head" },
      alarmPhoto(latest) && h(ZoomablePhoto, { src: alarmPhoto(latest), title: tx("What the AI monitor saw") + (latest.timestamp ? " • " + latest.timestamp : ""), className: "ai-question__photo" }),
      h(
        "div",
        { className: "ai-question__text" },
        h("div", { className: "ai-question__title" }, tx("The AI monitor saw a problem") + " • " + aiActionLabel(action)),
        h("div", { className: "ai-question__summary" }, latest.verdict.summary || ""),
      ),
    ),
    answered
      ? h("p", { className: "ai-question__done" }, AI_ANSWER_TEXT.right)
      : h(
          React.Fragment,
          null,
          h("div", { className: "ai-question__ask" }, tx("Is it a real problem?")),
          h(
            "div",
            { className: "ai-question__buttons" },
            AI_ANSWERS.map((one) => h("button", { key: one.id, type: "button", className: cx("oui-btn oui-btn--sm", one.id === "right" && "oui-btn--danger-soft"), disabled: busy, title: one.detail, "data-ai-answer": one.id, onClick: () => send(one.id) }, one.label)),
          ),
        ),
  );
}

/** The AI monitoring panel, opened by the badge in the header (it was a card of the Config page before 1.25). */
function AiPanelLayer({ monitor, onSettings }) {
  const [open, setOpen] = useState(aiPanelOpen);
  useEffect(() => {
    aiPanelListeners.add(setOpen);
    return () => aiPanelListeners.delete(setOpen);
  }, []);
  useBackHandler(() => {
    closeAiPanel();
    return true;
  }, open);
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => event.key === "Escape" && !document.querySelector(".photo-viewer") && closeAiPanel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  return h(
    Presence,
    null,
    open &&
      h(
        "div",
        { className: "help-overlay ai-panel-overlay", onClick: (event) => event.target === event.currentTarget && closeAiPanel() },
        h(
          "div",
          { className: "help-sheet ai-panel", role: "dialog", "aria-modal": "true", "aria-label": tx("AI monitoring"), "data-ai-panel": "1" },
          h(
            "div",
            { className: "help-sheet__head" },
            h("div", { className: "help-sheet__title" }, tx("AI monitoring")),
            h("button", { type: "button", className: "header-btn drawer__btn", "aria-label": tx("AI monitor settings"), title: tx("AI monitor settings"), "data-ai-settings": "1", onClick: () => (closeAiPanel(), onSettings()) }, h(Icons.Sliders)),
            h("button", { type: "button", className: "header-btn drawer__btn", "aria-label": tx("Close"), onClick: closeAiPanel }, h(Icons.Close)),
          ),
          h("div", { className: "help-sheet__body" }, h(AiMonitorCard, { monitor, bare: true })),
        ),
      ),
  );
}
