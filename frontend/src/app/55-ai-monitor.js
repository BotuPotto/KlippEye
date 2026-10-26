/* ============================================================================
   55 · AI PRINT MONITOR
   The backend watches the webcam while a print runs (OpenCV) and, when
   something looks wrong, asks an AI to judge it. This file polls both and
   feeds two places:
     · the round "AI" badge in the header (green / amber / red),
     · the AI MONITORING card on the Config page.
   The newest verdict is also kept in localStorage for two hours, so the badge
   and the card come back after a page reload.
   ========================================================================== */

const AI_MONITOR_POLL_MS = 4000;
const AI_VERDICT_MAX_AGE_MS = 2 * 60 * 60 * 1000;

/* ---------------------------------------------------------------------------
   Verdict cache
   ------------------------------------------------------------------------- */
const verdictCache = {
  save(response) {
    storage.set(STORAGE_KEYS.lastAiAnalysis, JSON.stringify(response));
    storage.set(STORAGE_KEYS.lastAiAnalysisTime, String(Date.now()));
  },
  load() {
    const response = storage.getJson(STORAGE_KEYS.lastAiAnalysis);
    if (!response) return null;
    if (Date.now() - parseInt(storage.get(STORAGE_KEYS.lastAiAnalysisTime) || "0", 10) > AI_VERDICT_MAX_AGE_MS) {
      storage.remove(STORAGE_KEYS.lastAiAnalysis);
      storage.remove(STORAGE_KEYS.lastAiAnalysisTime);
      return null;
    }
    return response;
  },
};

/** The action ("CONTINUA" | "PAUSA" | "CANCELLA") a verdict recommends, or "". */
function recommendedAction(verdict) {
  if (!verdict) return "";
  return verdict.analysis && verdict.analysis.action ? verdict.analysis.action : verdict.action || "";
}

/* ---------------------------------------------------------------------------
   What the detector's status text means
   ------------------------------------------------------------------------- */
const includesAny = (text, words) => words.some((word) => text.includes(word));

/** Header badge for the current detector status; undefined = leave it as it is. */
function headerBadgeFor(stats, action) {
  const status = stats.status;
  const lower = (status || "").toLowerCase();
  const idle = includesAny(lower, ["idle", "complete", "cancelled", "error"]) || status === "" || (lower === "" && stats.frames_checked === 0);
  if (idle) return null;
  const printingNow = includesAny(lower, ["scanning", "triggered"]) || (stats.frames_checked > 0 && !lower.includes("idle"));
  const recommended = (action || "").toUpperCase();
  if (!recommended) return printingNow ? AI_BADGES.monitoring : undefined;
  if (recommended.includes("CANCELLA")) return AI_BADGES.critical;
  if (recommended.includes("PAUSA")) return AI_BADGES.pause;
  return AI_BADGES.ok;
}

const AI_BADGES = {
  monitoring: { rgb: "61,220,138", hex: "#3ddc8a", glow: 0.35, title: "Monitoraggio OK" },
  ok: { rgb: "61,220,138", hex: "#3ddc8a", glow: 0.35, title: "Stampa OK" },
  critical: { rgb: "255,93,93", hex: "#ff5d5d", glow: 0.45, title: "Difetto critico - CANCELLA" },
  pause: { rgb: "255,183,64", hex: "#ffb740", glow: 0.4, title: "Difetto - PAUSA consigliata" },
};

/** Card header pill + dot for the detector status. */
function describeDetector(json) {
  const stats = json.stats || {};
  const status = stats.status || "";
  const printing = status.includes("scanning") || status.includes("TRIGGERED");
  const idle = status.includes("idle") || status.includes("state=");
  const realStarted = json.real_print_started !== undefined ? json.real_print_started : stats.real_print_started;

  let pill = { text: "In attesa stampa", tone: "waiting" };
  if (realStarted === false && status.toLowerCase().includes("riscaldamento")) pill = { text: "Riscaldamento/mesh - attesa stampa reale", tone: "warming" };
  else if (printing) pill = { text: "Monitoraggio attivo • stampa in corso", tone: "active" };

  return {
    state: (status || "idle").slice(0, 30),
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
const IDLE_DETECTOR = { state: "idle", score: "0%", checks: 0, dot: "idle", pill: { text: "In attesa stampa", tone: "waiting" }, realStarted: undefined, realReason: "" };

function verdictOf(response) {
  return { verdict: response.analysis, model: response.model, progress: response.progress, timestamp: response.timestamp };
}

/** { detector, latest, badge }: always running, whatever page is open. */
function useAiMonitor() {
  const [detector, setDetector] = useState(IDLE_DETECTOR);
  const [latest, setLatest] = useState(() => {
    const cached = verdictCache.load();
    return cached && cached.has_analysis ? verdictOf(cached) : null;
  });
  const [badge, setBadge] = useState(null);
  const latestRef = useRef(latest);

  useEffect(() => {
    let cancelled = false;
    let firstPollDone = false;

    const poll = async () => {
      try {
        const status = await fetchJson("/api/print/detector/status");
        if (cancelled || !status.ok) return;
        const stats = status.stats || {};
        setDetector(describeDetector(status));

        const fresh = await fetchJson("/api/print/last_analysis");
        if (fresh.ok && fresh.has_analysis) verdictCache.save(fresh);
        let effective = fresh;
        if (!(fresh.ok && fresh.has_analysis)) {
          // nothing from the backend: keep showing the cached verdict while a print is running
          const cached = verdictCache.load();
          const finished = includesAny((stats.status || "").toLowerCase(), ["idle", "complete", "cancelled"]);
          if (cached && cached.has_analysis && !finished) effective = cached;
        }
        if (cancelled) return;
        if (effective.ok && effective.has_analysis) {
          // `initial` marks the verdict found when the page opens: it is shown, but never scrolled to
          const next = { ...verdictOf(effective), initial: !firstPollDone };
          if (!latestRef.current || JSON.stringify(next.verdict) !== JSON.stringify(latestRef.current.verdict)) {
            latestRef.current = next;
            setLatest(next);
          }
        }
        const nextBadge = headerBadgeFor(stats, recommendedAction(latestRef.current && latestRef.current.verdict));
        if (nextBadge !== undefined) setBadge(nextBadge);
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

  return { detector, latest, badge };
}

/* ---------------------------------------------------------------------------
   Header badge
   ------------------------------------------------------------------------- */
function AiHeaderBadge({ badge }) {
  if (!badge) return null;
  const tone = { "--ai-hex": badge.hex, "--ai-rgb": badge.rgb, "--ai-glow": badge.glow };
  return h("div", { className: "ai-header-badge", title: badge.title, style: tone }, h("span", { className: "ai-header-badge__dot" }), h("span", { className: "ai-header-badge__label" }, "AI"));
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
  const action = latest.verdict.action;
  if (!action || action === "CONTINUA") return h("div", { className: "ai-alert hidden" });
  return h(
    "div",
    { className: cx("ai-alert", action.includes("CANCELLA") ? "ai-alert--danger" : "ai-alert--warn") },
    h("div", { className: "flex items-center justify-between gap-2" }, h("span", { className: "ai-alert__title" }, "Azione consigliata: " + action), h("span", { className: "oui-caption" }, latest.timestamp || "")),
    h("div", { className: "ai-alert__text" }, latest.verdict.summary || ""),
  );
}

function AiMonitorCard({ monitor }) {
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
    Card,
    null,
    h(
      "div",
      { className: "ai-card-head" },
      h(SectionTitle, null, "AI monitoring automatico"),
      h("div", { className: "oui-caption" }, "V17 1080x720"),
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
      h(MonitorTile, { label: "Stato" }, detector.state),
      h(MonitorTile, { label: "OpenCV score" }, detector.score),
      h(MonitorTile, { label: "Checks" }, detector.checks),
    ),
    latest ? h(VerdictAlert, { latest }) : h("div", { className: "ai-alert hidden" }),
    h("div", { ref: resultRef, className: cx("ai-result", !latest && "hidden") }, latest && h(PrintAnalysis, { text: verdictText, progress: latest.progress, detector })),
  );
}
