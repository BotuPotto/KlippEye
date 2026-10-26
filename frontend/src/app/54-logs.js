/* ============================================================================
   54 · SYSTEM LOGS
   Lists the Klipper / Moonraker / crowsnest logs of the Raspberry Pi. Each can
   be read in the editor, downloaded or analysed by the AI; "Analizza
   automaticamente" analyses all of them at once. The AI provider's API key is
   asked for when the backend reports it is missing or rejected.
   ========================================================================== */

const LOGS_DIR_HINT = "/home/pi/printer_data/logs";
const KEY_ERROR_WORDS = ["api key", "configurata", "invalid", "unauthorized", "authentication"];
const KEY_MIN_LENGTH = 10;
const KEY_SAVED_ANALYSIS_DELAY_MS = 600;

const AI_PROVIDERS = [
  { id: "groq", label: "Groq (gratis, consigliato) - gsk_..." },
  { id: "openai", label: "OpenAI - sk-..." },
  { id: "meta", label: "Meta Llama - LLM-..." },
  { id: "openrouter", label: "OpenRouter - sk-or-..." },
];

/** The provider a key belongs to, judging by its prefix (falls back to `chosen`). */
function providerForKey(key, chosen) {
  if (key.startsWith("gsk_")) return "groq";
  if (key.startsWith("LLM-")) return "meta";
  if (key.startsWith("sk-or-")) return "openrouter";
  if (key.startsWith("sk-")) return "openai";
  return chosen;
}

const looksLikeKeyProblem = (message) => KEY_ERROR_WORDS.some((word) => message.toLowerCase().includes(word));
const looksLikeAuthFailure = (message) => message.toLowerCase().includes("api key") || message.includes("401") || message.includes("403");

const logsApi = {
  async list() {
    const response = await fetchFresh("/api/logs/list");
    if (!response.ok) throw new Error("HTTP " + response.status + " " + (await response.text()).slice(0, 300));
    const json = await response.json();
    if (!json.files) throw new Error(json.error || "nessun file");
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
  async saveKey(key, provider) {
    return fetchJson("/api/ai/config", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ api_key: key, provider }) });
  },
  download: (name) => downloadFile("/api/logs/download?file=" + encodeURIComponent(name), name),
};

/* ---------------------------------------------------------------------------
   State: file list + AI result panel
   ------------------------------------------------------------------------- */
const READY_HINT = "Pronto • Tocca AI per un singolo file o Analizza automaticamente per tutti";

function useLogs() {
  const [list, setList] = useState({ status: "loading", files: [], dir: LOGS_DIR_HINT, error: "" });
  const [result, setResult] = useState({ kind: "idle" });
  const [hint, setHint] = useState(null); // { text, tone: "ready" | "busy" | "done" }
  const [badge, setBadge] = useState(null); // "Completata" once an all-logs analysis finished
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
    setHint({ tone: "busy", text: name ? "Analisi singola: " + name + "..." : "Analisi in corso su tutti i log..." });
    setBadge(null);
    try {
      const { ok, status, json } = await logsApi.analyze(name);
      if (!ok) {
        if (json.error && looksLikeKeyProblem(json.error)) return setResult({ kind: "key", message: [json.error, h("br", { key: "br" }), json.howto || ""] });
        throw new Error(json.error || "HTTP " + status);
      }
      setResult({ kind: "done", scope, name, json });
      if (name) {
        setHint({ tone: "done", text: "Singola completata: " + name });
      } else {
        const used = (json.used_files || []).length;
        setHint({ tone: "done", text: "Analisi completata • " + used + " file" });
        setBadge("Completata");
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
   API key form
   ------------------------------------------------------------------------- */
function ApiKeyForm({ message, onSaved, onCleared }) {
  const [provider, setProvider] = useState("groq");
  const [key, setKey] = useState("");

  // Native browser dialogs, as in the original (an Android WebView without a WebChromeClient
  // shows none of them: alert() does nothing and confirm() answers "no").
  const save = async () => {
    const trimmed = key.trim();
    if (trimmed.length < KEY_MIN_LENGTH) return window.alert("Key troppo corta");
    const json = await logsApi.saveKey(trimmed, providerForKey(trimmed, provider));
    if (json.ok) onSaved();
    else window.alert("Errore: " + (json.error || "unknown"));
  };
  const clear = async () => {
    if (!window.confirm("Cancellare key?")) return;
    await logsApi.saveKey("", "openai");
    onCleared();
  };

  return h(
    "div",
    { className: "oui-tile logs-key" },
    h("div", { className: "flex items-center gap-2 mb-2" }, h("span", { className: "logs-key__icon" }, "!"), h("span", { className: "logs-key__title" }, "API key mancante o errata")),
    h("div", { className: "logs-key__message" }, message),
    h(
      "div",
      { className: "logs-key__form" },
      h(
        "select",
        { value: provider, onChange: (e) => setProvider(e.target.value), className: "oui-field" },
        AI_PROVIDERS.map((option) => h("option", { key: option.id, value: option.id }, option.label)),
      ),
      h("input", { value: key, onChange: (e) => setKey(e.target.value), placeholder: "Incolla qui la key...", className: "oui-field oui-mono" }),
      h("div", { className: "oui-btn-row" }, h("button", { onClick: save, className: "oui-btn oui-btn--primary" }, "Salva e analizza"), h("button", { onClick: clear, className: "oui-btn" }, "Cancella")),
    ),
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
    h("div", { className: "oui-btn-row mt-3" }, h("button", { onClick: onRetry, className: "oui-btn oui-btn--sm" }, "Riprova"), h("button", { onClick: onChangeKey, className: "oui-btn oui-btn--sm" }, "Cambia key")),
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
      scope === "single" && h("span", { className: "oui-label" }, "Analisi singola"),
      scope === "single" && h("span", { className: "oui-badge logs-done__file" }, name),
      source && h("span", { className: "oui-badge logs-done__source" }, source),
    ),
    h(LogAnalysis, { text: json.analysis || "" }),
  );
}

function AnalysisResult({ logs, onKeySaved, onKeyCleared }) {
  const { result } = logs;
  switch (result.kind) {
    case "busy":
      return result.scope === "single"
        ? h(Spinner, { title: "Analizzo: " + result.name, detail: "singolo file • ~8 sec" })
        : h(Spinner, { title: "Analizzo tutti i log con AI", detail: "klippy • moonraker • crowsnest • mainsail • " + result.fileCount + " file • ~15 sec" });
    case "done":
      return h(AnalysisDone, { scope: result.scope, name: result.name, json: result.json });
    case "error":
      return h(AnalysisError, {
        title: result.scope === "single" ? "Errore analisi " + result.name : "Errore analisi",
        message: result.message,
        onRetry: () => logs.analyze(result.name),
        onChangeKey: () => logs.askForKey(),
      });
    case "key":
      return h(ApiKeyForm, { message: result.message, onSaved: onKeySaved, onCleared: onKeyCleared });
    case "keySaved":
      return h("div", { className: "oui-tile oui-tile--ok logs-saved" }, h("span", null, "✓"), " Key salvata! Avvio analisi...");
    case "keyCleared":
      return h("div", { className: "logs-key__message" }, "Key cancellata. Da SSH: ", h("code", { className: "ai-code" }, "rm /home/pi/klippeye_ai_config.json"));
    default:
      return h("div", { className: "oui-caption" }, "Nessuna analisi ancora. Tocca Analizza automaticamente per un'analisi diretta con AI.");
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
      h("button", { title: "Analizza solo questo", onClick: () => onAnalyze(file.name), className: "oui-btn oui-btn--sm log-row__ai" }, "AI"),
      h("button", { onClick: () => onOpen(file.name), className: "oui-btn oui-btn--sm" }, "Apri"),
      h("button", { title: "Download", "aria-label": "Download", onClick: () => logsApi.download(file.name), className: "oui-btn oui-btn--sm oui-btn--icon" }, h(Icons.Download, { size: 18 })),
    ),
  );
}

/** What to show instead of the rows (loading / error / no logs), or null when there are rows. */
function logsListNotice(list) {
  if (list.status === "loading") return h("div", { className: "logs-notice" }, "Carico log da " + LOGS_DIR_HINT + "...");
  if (list.status === "error")
    return h(
      "div",
      { className: "oui-tile oui-tile--danger" },
      h("div", { className: "logs-key__title" }, "Errore caricamento log"),
      h("div", { className: "logs-key__message mt-1" }, list.error),
      h("div", { className: "oui-caption mt-2" }, "Verifica backend V7: /api/logs/list"),
    );
  if (list.status === "empty") return h("div", { className: "logs-notice" }, "Nessun .log in " + list.dir);
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
      window.alert("Errore apertura: " + error.message);
    }
  };
  const keySaved = () => {
    logs.setResult({ kind: "keySaved" });
    setTimeout(() => logs.analyze(), KEY_SAVED_ANALYSIS_DELAY_MS);
  };

  const listNotice = logsListNotice(list);

  return h(
    Card,
    null,
    h(CardHeader, { title: "Log di sistema" }),
    h(
      "div",
      { className: "logs-toolbar" },
      h("button", { onClick: logs.refresh, className: "oui-btn oui-btn--sm" }, h(Icons.Refresh, { size: 16 }), "Aggiorna"),
      h("button", { onClick: () => logs.analyze(), className: "oui-btn oui-btn--sm oui-btn--primary logs-toolbar__main" }, "Analizza automaticamente"),
      h("button", { onClick: () => logs.askForKey("Cambia API Key esistente:"), title: "API key", "aria-label": "API key", className: "oui-btn oui-btn--sm oui-btn--icon" }, h(Icons.Gear, { size: 18 })),
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
          h(SectionTitle, null, "Analisi errori e suggerimenti"),
          h("span", { className: cx("oui-badge oui-badge--ok", !badge && "hidden") }, badge || "Riassunto"),
        ),
        h("span", { className: cx("oui-btn oui-btn--sm oui-btn--icon logs-analysis__toggle", collapsed && "is-collapsed"), "aria-hidden": "true" }, h(Icons.Chevron, { size: 18 })),
      ),
      hint && h("div", { className: "logs-hint logs-hint--" + hint.tone }, h("span", { className: "oui-dot" }), hint.text),
      h("div", { ref: resultRef, className: cx("logs-result", logs.result.kind === "done" && "logs-result--report", collapsed && "log-result--collapsed") }, h(AnalysisResult, { logs, onKeySaved: keySaved, onKeyCleared: () => logs.setResult({ kind: "keyCleared" }) })),
    ),
  );
}
