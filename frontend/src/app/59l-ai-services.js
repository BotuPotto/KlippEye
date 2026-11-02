/* ============================================================================
   59l · THE AI SERVICES (1.27, roadmap phase 6a part 3)
   Which AI service and model KlippEye uses, for two jobs on their own:
     · the AI monitor and «Analyse the print» (the model must see pictures)  → Settings → AI monitor → The AI service;
     · the analysis of the system logs (text only)                            → the gear of the System logs card.
   The keys are one list for both (a key per service, kept on the Raspberry in ai.json, never sent back whole); the models
   are read from the service itself with that key (/api/ai/models), so the list is always the current one. The service
   "Other (OpenAI-compatible)" is any server that speaks the same language (a model on the home network, for example).
   ========================================================================== */

/** The AI settings as the backend has them: { phase, data, reload(), save(body) -> {ok, message} }. */
function useAiServices(active) {
  const [state, setState] = useState({ phase: "loading", data: null });
  const load = async () => {
    try {
      const response = await fetchFresh("/api/ai/config", { timeout: BRAIN_READ_TIMEOUT_MS });
      const data = await response.json();
      setState(response.ok && isPlainObject(data) && Array.isArray(data.services) ? { phase: "ok", data } : { phase: "old", data: null });
    } catch (error) {
      setState((previous) => (previous.phase === "ok" ? previous : { phase: "down", data: null }));
    }
  };
  useEffect(() => {
    if (active) load();
  }, [active]);
  const save = async (body) => {
    const reply = await brainPost("/api/ai/config", body);
    if (reply.ok && reply.data && Array.isArray(reply.data.services)) setState({ phase: "ok", data: reply.data });
    return reply;
  };
  return { ...state, reload: load, save };
}

/** The models of one service: { phase: "idle" | "loading" | "ok" | "error", models, message }. */
function useAiModels(provider, enabled) {
  const [state, setState] = useState({ phase: "idle", models: [], message: "" });
  useEffect(() => {
    if (!provider || !enabled) return setState({ phase: "idle", models: [], message: "" });
    let cancelled = false;
    setState({ phase: "loading", models: [], message: "" });
    (async () => {
      try {
        const response = await fetchFresh("/api/ai/models?provider=" + encodeURIComponent(provider), { timeout: 20000 });
        const data = await response.json();
        if (cancelled) return;
        if (response.ok && data.ok) setState({ phase: "ok", models: Array.isArray(data.models) ? data.models : [], message: "" });
        else setState({ phase: "error", models: [], message: data.error || "HTTP " + response.status });
      } catch (error) {
        if (!cancelled) setState({ phase: "error", models: [], message: tx("the backend does not answer") });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [provider, enabled]);
  return state;
}

const AI_USE_TEXTS = {
  monitor: { service: tx("Service for the monitor"), model: tx("Model for the monitor") },
  logs: { service: tx("Service for the logs"), model: tx("Model for the logs") },
};
const MODEL_OTHER = "__other__";

/** The service and the model of one use ("monitor" or "logs"). */
function AiUseSettings({ use, ai }) {
  const data = ai.data;
  const current = data[use] || {};
  const services = data.services || [];
  const service = services.find((s) => s.id === current.provider) || null;
  const usable = Boolean(service && (service.key_set || service.key_optional));
  const models = useAiModels(usable ? current.provider : "", usable);
  const [typing, setTyping] = useState(false);
  const [typed, setTyped] = useState("");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async (body) => {
    setBusy(true);
    const reply = await ai.save({ [use]: body });
    setBusy(false);
    setProblem(reply.ok ? "" : tx("Not saved: ") + reply.message);
    return reply.ok;
  };
  const list = models.models;
  // the monitor needs a model that sees pictures: those first, then the ones nobody knows, then text only
  const groups =
    use === "monitor"
      ? [
          { label: tx("They see pictures"), items: list.filter((m) => m.vision === true) },
          { label: tx("Not known whether they see pictures"), items: list.filter((m) => m.vision === null || m.vision === undefined) },
          { label: tx("Text only (not for the monitor)"), items: list.filter((m) => m.vision === false) },
        ].filter((group) => group.items.length)
      : [{ label: null, items: list }];
  const known = list.some((m) => m.id === current.model);
  const chosen = list.find((m) => m.id === (current.model || current.default_model));
  const visionWarning = use === "monitor" && chosen && chosen.vision === false;
  const texts = AI_USE_TEXTS[use];
  const pick = (value) => {
    if (value === MODEL_OTHER) {
      setTyped(current.model || "");
      return setTyping(true);
    }
    setTyping(false);
    save({ provider: current.provider, model: value });
  };
  return h(
    "div",
    { className: "ai-use", "data-ai-use": use },
    h(
      "label",
      { className: "set-field" },
      h("span", { className: "set-field__label" }, texts.service),
      h(
        "select",
        { className: "oui-field", value: current.provider || "", disabled: busy, "data-ai-service": use, onChange: (event) => save({ provider: event.target.value }) },
        !current.provider && h("option", { value: "" }, tx("— choose —")),
        services.map((s) => h("option", { key: s.id, value: s.id }, s.name + (s.key_set ? "" : s.key_optional ? "" : " " + tx("(no key)")))),
      ),
    ),
    service && !usable && h("p", { className: "set-field__error", role: "alert" }, tx("No key saved for {name}: enter it below, in «Keys of the AI services».", { name: service.name })),
    usable &&
      h(
        "label",
        { className: "set-field" },
        h("span", { className: "set-field__label" }, texts.model),
        h(
          "select",
          { className: "oui-field", value: typing ? MODEL_OTHER : current.model || "", disabled: busy || models.phase === "loading", "data-ai-model": use, onChange: (event) => pick(event.target.value) },
          h("option", { value: "" }, current.default_model ? tx("Default: {model}", { model: current.default_model }) : tx("— choose —")),
          current.model && !known && h("option", { value: current.model }, current.model),
          groups.map((group, index) =>
            group.label
              ? h("optgroup", { key: index, label: group.label }, group.items.map((m) => h("option", { key: m.id, value: m.id }, m.id)))
              : group.items.map((m) => h("option", { key: m.id, value: m.id }, m.id)),
          ),
          h("option", { value: MODEL_OTHER }, tx("Another model (type its name)…")),
        ),
        models.phase === "loading" && h("span", { className: "set-field__hint" }, tx("Reading the models of {name}…", { name: service.name })),
        models.phase === "error" && h("span", { className: "set-field__error", role: "alert", "data-ai-models-error": "1" }, tx("The list of models could not be read: {error}", { error: models.message })),
        models.phase === "ok" && h("span", { className: "set-field__hint" }, tx("{count} models of {name}, read from the service now.", { count: list.length, name: service.name })),
      ),
    typing &&
      h(
        "div",
        { className: "ai-use__typed" },
        h("input", { className: "oui-field oui-mono", value: typed, placeholder: tx("exact name of the model"), "data-ai-model-typed": use, onChange: (event) => setTyped(event.target.value) }),
        h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--primary", disabled: busy || !typed.trim(), onClick: async () => (await save({ provider: current.provider, model: typed.trim() })) && setTyping(false) }, tx("Use it")),
      ),
    visionWarning && h("p", { className: "set-field__error", role: "alert" }, tx("This model does not see pictures: the monitor needs one that does.")),
    problem && h("p", { className: "set-field__error", role: "alert" }, problem),
  );
}

/** One service in the list of the keys. */
function AiKeyRow({ service, ai, customBase }) {
  const [editing, setEditing] = useState(false);
  const [key, setKey] = useState("");
  const [base, setBase] = useState(customBase || "");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const [askDelete, setAskDelete] = useState(false);
  const send = async (body) => {
    setBusy(true);
    const reply = await ai.save(body);
    setBusy(false);
    if (!reply.ok) return setProblem(tx("Not saved: ") + reply.message);
    setProblem("");
    setEditing(false);
    setAskDelete(false);
    setKey("");
  };
  const custom = service.id === "custom";
  const saveKey = () => {
    const trimmed = key.trim();
    if (custom) {
      const body = { custom_base: base.trim() };
      if (trimmed) body.key = { provider: "custom", api_key: trimmed };
      return send(body);
    }
    if (trimmed.length < KEY_MIN_LENGTH) return setProblem(tx("Key too short"));
    send({ key: { provider: service.id, api_key: trimmed } });
  };
  const status = custom
    ? customBase
      ? customBase + (service.key_set ? " • " + tx("key {end}", { end: service.key_preview }) : "")
      : tx("no address")
    : service.key_set
      ? tx("key saved, ends with {end}", { end: service.key_preview })
      : tx("no key");
  return h(
    "div",
    { className: cx("ai-key", service.key_set && "is-set"), "data-ai-key-row": service.id },
    h(
      "div",
      { className: "ai-key__head" },
      h("span", { className: "ai-key__name" }, service.name, service.free && !custom && h("span", { className: "oui-badge oui-badge--ok ai-key__free" }, tx("free plan"))),
      h("span", { className: "ai-key__status" }, status),
    ),
    editing
      ? h(
          "div",
          { className: "fn-key" },
          custom && h("input", { className: "oui-field oui-mono", value: base, placeholder: "http://192.168.1.20:11434/v1", "data-ai-base": "1", onChange: (event) => setBase(event.target.value) }),
          h("input", { className: "oui-field oui-mono", value: key, placeholder: custom ? tx("key (if the server asks for one)") : tx("Paste the key here..."), autoComplete: "off", "data-ai-key-input": service.id, onChange: (event) => setKey(event.target.value) }),
          h("div", { className: "oui-btn-row" }, h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--sm", disabled: busy, "data-ai-key-save": service.id, onClick: saveKey }, tx("Save")), h("button", { type: "button", className: "oui-btn oui-btn--sm", onClick: () => setEditing(false) }, tx("Cancel"))),
        )
      : askDelete
        ? h(
            "div",
            { className: "set-confirm", role: "alertdialog" },
            h("span", null, tx("Delete the key of {name}?", { name: service.name })),
            h("div", { className: "set-confirm__buttons" }, h("button", { type: "button", className: "oui-btn", onClick: () => setAskDelete(false) }, tx("No")), h("button", { type: "button", className: "oui-btn oui-btn--danger", disabled: busy, "data-ai-key-confirm": service.id, onClick: () => send({ key: { provider: service.id, delete: true } }) }, txc("key", "Delete"))),
          )
        : h(
            "div",
            { className: "oui-btn-row ai-key__actions" },
            h("button", { type: "button", className: "oui-btn oui-btn--sm", "data-ai-key-edit": service.id, onClick: () => setEditing(true) }, custom ? tx("Set the address") : service.key_set ? tx("Change the key") : tx("Enter the key")),
            service.key_set && h("button", { type: "button", className: "oui-btn oui-btn--sm oui-btn--quiet", "data-ai-key-delete": service.id, onClick: () => setAskDelete(true) }, txc("key", "Delete")),
            service.key_url && (!IN_APP_WEBVIEW || APP_OPENS_LINKS) && h("a", { className: "oui-btn oui-btn--sm oui-btn--quiet", href: service.key_url, target: "_blank", rel: "noopener noreferrer", "data-ai-key-url": service.id }, tx("Get a key") + " ↗"),
          ),
    problem && h("p", { className: "set-field__error", role: "alert" }, problem),
  );
}

/** The keys of every service, folded (open when there is none yet). */
function AiKeysList({ ai }) {
  const services = ai.data.services || [];
  const saved = services.filter((s) => s.key_set).length;
  return h(
    "details",
    { className: "ai-keys", open: saved === 0 || undefined, "data-ai-keys": saved },
    h("summary", null, saved === 1 ? tx("Keys of the AI services (1 saved)") : tx("Keys of the AI services ({count} saved)", { count: saved })),
    h("p", { className: "set-group__note" }, tx("A key is like a password of your account at that service: it stays on the Raspberry. Groq, Google Gemini and Mistral have a free plan; with a free plan there are limits per minute and per day.")),
    services.map((service) => h(AiKeyRow, { key: service.id, service, ai, customBase: ai.data.custom_base })),
  );
}

/** Everything for one use: the notice while reading, the service and model, the keys. */
function AiServicesPanel({ use, ai }) {
  if (ai.phase === "loading") return h("div", { className: "set-status" }, h("span", { className: "set-status__dot" }), tx("Reading the AI settings…"));
  if (ai.phase === "old") return h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), tx("The backend on the Raspberry is older than the dashboard: update KlippEye to choose the AI service and model."));
  if (ai.phase !== "ok") return h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), tx("The backend does not answer."));
  const current = ai.data[use] || {};
  return h(
    React.Fragment,
    null,
    h(
      "div",
      { className: cx("set-status", current.usable ? "set-status--ok" : "set-status--warn"), "data-ai-ready": current.usable ? "yes" : "no" },
      h("span", { className: "set-status__dot" }),
      current.usable
        ? tx("In use: {service} • {model}", { service: (ai.data.services.find((s) => s.id === current.provider) || {}).name || current.provider, model: current.model || current.default_model || "?" })
        : use === "monitor"
          ? tx("No AI key: the monitor sees the problems but nobody judges them. Groq and Google Gemini have a free key.")
          : tx("No AI key: the logs cannot be analysed. Groq and Google Gemini have a free key."),
    ),
    h(AiUseSettings, { use, ai }),
    h(AiKeysList, { ai }),
  );
}
