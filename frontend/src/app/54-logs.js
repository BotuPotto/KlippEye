/* ============================================================================
   54 · SYSTEM LOGS
   Lists the Klipper / Moonraker / crowsnest logs of the Raspberry Pi. Each can
   be read in the editor, downloaded or analysed by the AI; "Analizza
   automaticamente" analyses all of them at once. The gear next to «Error
   analysis and suggestions» opens the AI settings of the logs right under it
   (1.27: service, model, keys; 59l); they open by themselves when the backend
   reports the key missing or rejected.
   ========================================================================== */

const KEY_ERROR_WORDS = ["api key", "configurata", "invalid", "unauthorized", "authentication"];
const KEY_MIN_LENGTH = 10;

const looksLikeKeyProblem = (message) => KEY_ERROR_WORDS.some((word) => message.toLowerCase().includes(word));
const looksLikeAuthFailure = (message) => message.toLowerCase().includes("api key") || message.includes("401") || message.includes("403");

const logsApi = {
  async list() {
    const response = await fetchFresh("/api/logs/list");
    if (!response.ok) throw new Error("HTTP " + response.status + " " + (await response.text()).slice(0, 300));
    const json = await response.json();
    if (!json.files) throw new Error(json.error || tx("no files"));
    return json;
  },
  async content(name) {
    const json = await fetchJson("/api/logs/content?file=" + encodeURIComponent(name) + "&lines=3000");
    if (!json.content) throw new Error(json.error || "no content");
    return json.content;
  },
  /** Analyses one log (`name`) or all of them; resolves to { ok, json }. */
  async analyze(name) {
    const response = await fetchFresh("/api/logs/analyze" + (name ? "?file=" + encodeURIComponent(name) : ""), { method: "POST" });
    return { ok: response.ok, status: response.status, json: await response.json() };
  },
  download: (name) => downloadFile("/api/logs/download?file=" + encodeURIComponent(name), name),
};

/* ---------------------------------------------------------------------------
   State: file list + AI result panel
   ------------------------------------------------------------------------- */
const READY_HINT = tx("Ready • Tap AI for one file or Analyse automatically for all of them");

function useLogs() {
  const [list, setList] = useState({ status: "loading", files: [], dir: "", error: "" });
  const [result, setResult] = useState({ kind: "idle" });
  const [hint, setHint] = useState(null); // { text, tone: "ready" | "busy" | "done" }
  const [badge, setBadge] = useState(null); // "Completed" once an all-logs analysis finished
  const [collapsed, setCollapsed] = useState(false);

  const refresh = async () => {
    try {
      const json = await logsApi.list();
      setList({ status: json.files.length === 0 ? "empty" : "ready", files: json.files, dir: json.dir, error: "" });
      if (json.files.length > 0) setHint({ text: READY_HINT, tone: "ready" });
    } catch (error) {
      setList((previous) => ({ ...previous, status: "error", error: error.message }));
    }
  };
  useEffect(() => {
    refresh();
  }, []);

  /** Runs an analysis of one log (`name`) or of all, updating the panel as it goes. */
  const analyze = async (name) => {
    const scope = name ? "single" : "all";
    setCollapsed(false);
    setResult({ kind: "busy", scope, name, fileCount: list.files.length });
    setHint({ tone: "busy", text: name ? tx("Single analysis: ") + name + "..." : tx("Analysing all the logs...") });
    setBadge(null);
    try {
      const { ok, status, json } = await logsApi.analyze(name);
      if (!ok) {
        if (json.error && looksLikeKeyProblem(json.error)) return setResult({ kind: "key", message: [json.error, h("br", { key: "br" }), json.howto || ""] });
        throw new Error(json.error || "HTTP " + status);
      }
      setResult({ kind: "done", scope, name, json });
      if (name) {
        setHint({ tone: "done", text: tx("Single analysis done: ") + name });
      } else {
        const used = (json.used_files || []).length;
        setHint({ tone: "done", text: tx("Analysis completed • ") + used + tx(" files") });
        setBadge(tx("Completed"));
      }
    } catch (error) {
      if (looksLikeAuthFailure(error.message)) setResult({ kind: "key", message: error.message });
      else setResult({ kind: "error", scope, name, message: error.message });
    }
  };

  return {
    list,
    result,
    hint,
    badge,
    collapsed,
    refresh,
    analyze,
    toggleCollapsed: () => setCollapsed((value) => !value),
    askForKey: (message = "") => {
      setCollapsed(false);
      setResult({ kind: "key", message });
    },
    setResult,
  };
}

/* ---------------------------------------------------------------------------
   The key is missing or refused (1.27: the AI settings are at the top of the card, under the gear)
   ------------------------------------------------------------------------- */
function ApiKeyNotice({ message }) {
  return h(
    "div",
    { className: "oui-tile logs-key", "data-logs-key": "1" },
    h("div", { className: "flex items-center gap-2 mb-2" }, h("span", { className: "logs-key__icon" }, "!"), h("span", { className: "logs-key__title" }, tx("API key missing or wrong"))),
    message && h("div", { className: "logs-key__message" }, message),
    h("div", { className: "logs-key__message mt-2" }, tx("Choose the service and enter its key in the AI settings just above (the gear next to «Error analysis and suggestions»), then tap «Analyse automatically».")),
  );
}

/* ---------------------------------------------------------------------------
   Result panel
   ------------------------------------------------------------------------- */
function Spinner({ title, detail }) {
  return h(
    "div",
    { className: "logs-busy" },
    h("span", { className: "logs-busy__spinner" }),
    h("div", { className: "flex flex-col min-w-0" }, h("span", { className: "logs-busy__title" }, title), h("span", { className: "oui-caption" }, detail)),
  );
}

function AnalysisError({ message, title, onRetry, onChangeKey }) {
  return h(
    "div",
    { className: "oui-tile oui-tile--danger" },
    h("div", { className: "logs-key__title mb-1" }, title),
    h("div", { className: "logs-key__message" }, message),
    h("div", { className: "oui-btn-row mt-3" }, h("button", { onClick: onRetry, className: "oui-btn oui-btn--sm" }, tx("Retry")), h("button", { onClick: onChangeKey, className: "oui-btn oui-btn--sm" }, tx("Change key"))),
  );
}

function AnalysisDone({ scope, name, json }) {
  const source = [json.model, json.provider].filter(Boolean).join(" • ");
  return h(
    "div",
    null,
    h(
      "div",
      { className: "flex items-center gap-2 flex-wrap logs-done" },
      scope === "single" && h("span", { className: "oui-dot logs-done__dot" }),
      scope === "single" && h("span", { className: "oui-label" }, tx("Single analysis")),
      scope === "single" && h("span", { className: "oui-badge logs-done__file" }, name),
      source && h("span", { className: "oui-badge logs-done__source" }, source),
    ),
    h(LogAnalysis, { text: json.analysis || "" }),
  );
}

function AnalysisResult({ logs }) {
  const { result } = logs;
  switch (result.kind) {
    case "busy":
      return result.scope === "single"
        ? h(Spinner, { title: tx("Analysing: ") + result.name, detail: tx("one file • ~8 s") })
        : h(Spinner, { title: tx("Analysing all the logs with AI"), detail: "klippy • moonraker • crowsnest • mainsail • " + result.fileCount + tx(" files • ~15 s") });
    case "done":
      return h(AnalysisDone, { scope: result.scope, name: result.name, json: result.json });
    case "error":
      return h(AnalysisError, {
        title: result.scope === "single" ? tx("Analysis error ") + result.name : tx("Analysis error"),
        message: result.message,
        onRetry: () => logs.analyze(result.name),
        onChangeKey: () => logs.askForKey(),
      });
    case "key":
      return h(ApiKeyNotice, { message: result.message });
    default:
      return h("div", { className: "oui-caption" }, tx("No analysis yet. Tap Analyse automatically for a direct AI analysis."));
  }
}

/* ---------------------------------------------------------------------------
   Card
   ------------------------------------------------------------------------- */
function LogRow({ file, onAnalyze, onOpen }) {
  return h(
    "div",
    { className: "log-row" },
    h(
      "div",
      { className: "log-row__main" },
      h(FileGlyph, { kind: fileKind(file.name) }),
      h("div", { className: "log-row__info" }, h("span", { className: "log-row__name" }, file.name), h("span", { className: "oui-caption oui-num" }, (file.size_h || formatBytes(file.size)) + " • " + (file.modified_str || ""))),
    ),
    h(
      "div",
      { className: "log-row__actions" },
      h("button", { title: tx("Analyse only this one"), onClick: () => onAnalyze(file.name), className: "oui-btn oui-btn--sm log-row__ai" }, "AI"),
      h("button", { onClick: () => onOpen(file.name), className: "oui-btn oui-btn--sm" }, txc("verb", "Open")),
      h("button", { title: "Download", "aria-label": "Download", onClick: () => logsApi.download(file.name), className: "oui-btn oui-btn--sm oui-btn--icon" }, h(Icons.Download, { size: 18 })),
    ),
  );
}

/** What to show instead of the rows (loading / error / no logs), or null when there are rows. */
function logsListNotice(list) {
  if (list.status === "loading") return h("div", { className: "logs-notice" }, tx("Loading the logs…"));
  if (list.status === "error")
    return h(
      "div",
      { className: "oui-tile oui-tile--danger" },
      h("div", { className: "logs-key__title" }, tx("Error loading the logs")),
      h("div", { className: "logs-key__message mt-1" }, list.error),
      h("div", { className: "oui-caption mt-2" }, tx("The logs cannot be read now: try again shortly")),
    );
  if (list.status === "empty") return h("div", { className: "logs-notice" }, tx("No .log in ") + list.dir);
  return null;
}

/** `onEditFile(path, content)` opens a log in the editor. */
function LogsCard({ onEditFile }) {
  const logs = useLogs();
  const { list, hint, badge, collapsed } = logs;
  const resultRef = useRef(null);

  // A single-file analysis lands below the fold on a phone: bring it into view.
  useEffect(() => {
    if (logs.result.kind === "done" && logs.result.scope === "single" && resultRef.current) resultRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [logs.result]);

  const openLog = async (name) => {
    try {
      onEditFile(name, await logsApi.content(name));
    } catch (error) {
      window.alert(tx("Error opening: ") + error.message);
    }
  };
  // the AI settings of the logs (1.27): at the top of the card, opened by the gear or when the key is missing
  const [showSettings, setShowSettings] = useState(false);
  const ai = useAiServices(showSettings);
  const settingsRef = useRef(null);
  useEffect(() => {
    if (logs.result.kind === "key") setShowSettings(true);
  }, [logs.result]);
  useEffect(() => {
    if (showSettings && settingsRef.current && settingsRef.current.scrollIntoView) settingsRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [showSettings]);

  const listNotice = logsListNotice(list);

  return h(
    Card,
    null,
    h(CardHeader, { title: tx("System logs") }),
    h(
      "div",
      { className: "logs-toolbar" },
      h("button", { onClick: logs.refresh, className: "oui-btn oui-btn--sm" }, h(Icons.Refresh, { size: 16 }), tx("Refresh")),
      h("button", { onClick: () => logs.analyze(), className: "oui-btn oui-btn--sm oui-btn--primary logs-toolbar__main" }, tx("Analyse automatically")),
    ),
    listNotice ? h("div", { className: "mt-3" }, listNotice) : h("div", { className: "oui-list log-list" }, list.files.map((file) => h(LogRow, { key: file.name, file, onAnalyze: logs.analyze, onOpen: openLog }))),
    h(
      "div",
      { className: "logs-analysis" },
      h(
        "div",
        { className: "logs-analysis__head", onClick: logs.toggleCollapsed },
        h(
          "div",
          { className: "flex items-center gap-3 flex-wrap min-w-0" },
          h(SectionTitle, null, tx("Error analysis and suggestions")),
          h("span", { className: cx("oui-badge oui-badge--ok", !badge && "hidden") }, badge || tx("Overview")),
        ),
        h(
          "div",
          { className: "logs-analysis__buttons" },
          // 1.27: the AI settings of the logs, next to the analysis they are for
          h(
            "button",
            {
              type: "button",
              onClick: (event) => {
                event.stopPropagation();
                setShowSettings((value) => !value);
              },
              title: tx("AI settings for the logs"),
              "aria-label": tx("AI settings for the logs"),
              "aria-expanded": showSettings,
              "data-logs-gear": "1",
              className: cx("oui-btn oui-btn--sm oui-btn--icon", showSettings && "is-active"),
            },
            h(Icons.Gear, { size: 18 }),
          ),
          h("span", { className: cx("oui-btn oui-btn--sm oui-btn--icon logs-analysis__toggle", collapsed && "is-collapsed"), "aria-hidden": "true" }, h(Icons.Chevron, { size: 18 })),
        ),
      ),
      showSettings &&
        h(
          "div",
          { ref: settingsRef, className: "logs-settings", "data-logs-settings": "1" },
          h("div", { className: "logs-settings__head" }, h(SectionTitle, null, tx("AI for the logs")), h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--quiet", onClick: () => setShowSettings(false) }, tx("Close"))),
          h("p", { className: "oui-caption" }, tx("The service and model that analyse the logs; the AI monitor has its own (Settings → AI monitor). The keys are the same for both.")),
          h(AiServicesPanel, { use: "logs", ai }),
        ),
      hint && h("div", { className: "logs-hint logs-hint--" + hint.tone }, h("span", { className: "oui-dot" }), hint.text),
      h("div", { ref: resultRef, className: cx("logs-result", logs.result.kind === "done" && "logs-result--report", collapsed && "log-result--collapsed") }, h(AnalysisResult, { logs })),
    ),
  );
}
