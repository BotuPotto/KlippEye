/* ============================================================================
   59r · HOME ASSISTANT / MQTT (1.100)
   Settings › System › Home Assistant / MQTT: the broker the KlippEye service publishes the printer on
   (backend/mqtt_bridge.py), with Home Assistant's discovery (a device with its sensors, buttons and lights appears by
   itself) and plain topics for any other system. The broker's password is kept on the Raspberry and never sent back.
   ========================================================================== */

const MQTT_FORM_KEYS = ["enabled", "host", "port", "tls", "username", "base_topic", "discovery", "discovery_prefix", "commands", "allow_cancel"];

function HomeAutomationPage() {
  const [info, setInfo] = useState(null);
  const [form, setForm] = useState(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const load = React.useCallback(async () => {
    try {
      const response = await fetchFresh("/api/mqtt", { timeout: BACKEND_READ_TIMEOUT_MS });
      if (response.status === 403) return setInfo({ guest: true });
      if (!response.ok) return setInfo((old) => old || { missing: true });
      const json = await response.json();
      setInfo(json);
      setForm((old) => old || Object.fromEntries(MQTT_FORM_KEYS.map((key) => [key, key === "port" ? String(json.port) : json[key]])));
    } catch (error) {
      setInfo((old) => old || { missing: true });
    }
  }, []);
  useEffect(() => {
    load();
    const timer = setInterval(load, 5000); // the connection's state, while the page is open
    return () => clearInterval(timer);
  }, [load]);

  if (!info) return h("div", { className: "set-status" }, h("span", { className: "set-status__dot" }), tx("Reading…"));
  if (info.guest) return h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), tx("Guests can only look: log in with the main password to command the printer."));
  if (info.missing || !form) return h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), tx("The KlippEye service is older than the dashboard: update KlippEye (Settings → Updates)"));

  const set = (key, value) => setForm((old) => ({ ...old, [key]: value }));
  const body = (extra) => ({ ...form, port: Number(form.port) || 0, ...(password ? { password } : {}), ...extra });
  const send = async (url, payload, okMessage) => {
    setBusy(true);
    setResult(null);
    try {
      const response = await fetch(url, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(payload) });
      const json = await response.json().catch(() => ({}));
      if (!response.ok || json.ok === false) setResult({ ok: false, message: json.error || tx("Error {status}", { status: response.status }) });
      else {
        if (url === "/api/mqtt") {
          setInfo(json);
          setForm(Object.fromEntries(MQTT_FORM_KEYS.map((key) => [key, key === "port" ? String(json.port) : json[key]])));
          setPassword("");
        }
        setResult({ ok: true, message: okMessage });
      }
    } catch (error) {
      setResult({ ok: false, message: tx("The KlippEye service does not answer") });
    }
    setBusy(false);
  };
  const running = info.running;
  const base = info.base_topic || info.default_base_topic;
  const changed = password !== "" || MQTT_FORM_KEYS.some((key) => String(form[key]) !== String(info[key]));
  const statusLine = !info.enabled
    ? { tone: "warn", text: tx("Off") }
    : running && running.connected
      ? { tone: "ok", text: tx("Connected to {host}", { host: info.host + ":" + info.port }) }
      : { tone: "warn", text: running && running.error ? tx("Not connected: {error}", { error: running.error }) : tx("Connecting…") };
  const field = (key, label, extra = {}) =>
    h(
      "label",
      { className: "set-field" },
      h("span", { className: "set-field__label" }, label),
      h("input", {
        className: "oui-field set-field__input",
        value: form[key] || "",
        autoCapitalize: "off",
        autoCorrect: "off",
        spellCheck: false,
        "data-mqtt-field": key,
        onChange: (event) => set(key, extra.digits ? event.target.value.replace(/[^0-9]/g, "").slice(0, 5) : event.target.value),
        ...extra.input,
      }),
    );

  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      {
        title: tx("The broker"),
        note: tx("KlippEye publishes the printer on an MQTT broker: in Home Assistant, the Mosquitto broker add-on (Settings → Add-ons) with a user of its own. The printer then appears by itself in Settings → Devices & services → MQTT."),
      },
      h("div", { className: cx("set-status", "set-status--" + statusLine.tone), "data-mqtt-status": running && running.connected ? "connected" : info.enabled ? "trying" : "off" }, h("span", { className: "set-status__dot" }), statusLine.text),
      h("div", { className: "oui-list" }, h(SwitchRow, { title: tx("Publish the printer on MQTT"), checked: Boolean(form.enabled), disabled: busy, onChange: (value) => set("enabled", value) })),
      field("host", tx("Address of the broker"), { input: { placeholder: "192.168.1.20", inputMode: "url" } }),
      field("port", tx("Port"), { digits: true, input: { inputMode: "numeric" } }),
      h("div", { className: "oui-list" }, h(SwitchRow, { title: tx("Encrypted (TLS)"), detail: tx("Usually port 8883. The broker needs a certificate an authority signed."), checked: Boolean(form.tls), disabled: busy, onChange: (value) => set("tls", value) })),
      field("username", tx("User name"), { input: { autoComplete: "off" } }),
      h(PasswordField, { label: info.has_password ? tx("Password (saved: write here to change it)") : tx("Password"), value: password, onChange: setPassword, autoComplete: "new-password", id: "mqtt-password" }),
      h(
        "div",
        { className: "mqtt-actions" },
        h("button", { type: "button", className: "oui-btn oui-btn--primary", disabled: busy || !changed, "data-mqtt-save": "1", onClick: () => send("/api/mqtt", body(), tx("Saved ✓")) }, tx("Save")),
        h("button", { type: "button", className: "oui-btn", disabled: busy || !form.host, "data-mqtt-test": "1", onClick: () => send("/api/mqtt/test", body(), tx("The broker answered: user and password are right.")) }, tx("Test the connection")),
      ),
      h(AccessMessage, { result }),
    ),
    h(
      SettingsGroup,
      { title: "Home Assistant" },
      h(
        "div",
        { className: "oui-list" },
        h(SwitchRow, { title: tx("Discovery"), detail: tx("The printer appears in Home Assistant by itself, with its sensors, buttons and lights."), checked: Boolean(form.discovery), disabled: busy, onChange: (value) => set("discovery", value) }),
        h(SwitchRow, { title: tx("Commands from home automation"), detail: tx("Pause, resume and the lights, from Home Assistant or another system."), checked: Boolean(form.commands), disabled: busy, onChange: (value) => set("commands", value) }),
        form.commands && h(SwitchRow, { title: tx("Allow cancelling the print"), detail: tx("A cancelled print cannot be recovered: turn it on only if nobody can press it by mistake."), danger: true, checked: Boolean(form.allow_cancel), disabled: busy, onChange: (value) => set("allow_cancel", value) }),
      ),
      running && running.lights && running.lights.length > 0 && h("p", { className: "oui-caption", "data-mqtt-lights": "1" }, tx("Lights published: {names}", { names: running.lights.map((light) => light.name).join(", ") })),
      h("p", { className: "oui-caption" }, tx("Save after changing these: they apply at once.")),
    ),
    h(
      SettingsGroup,
      { title: tx("Other systems (Node-RED, openHAB, ioBroker…)"), note: tx("The same values are on plain topics, retained: read them, or publish a command.") },
      h(
        "div",
        { className: "mqtt-topics", "data-mqtt-topics": "1" },
        [
          [base + "/state", tx("everything in one JSON")],
          [base + "/status/…", tx("one value each: state, progress, remaining, nozzle, bed, ai…")],
          [base + "/availability", tx("online / offline")],
          [base + "/command", tx("pause, resume, cancel")],
          [base + "/light/<id>/set", tx("ON / OFF")],
        ].map(([topic, what]) => h("div", { key: topic, className: "mqtt-topic" }, h("code", null, topic), h("span", { className: "oui-caption" }, what))),
      ),
      field("base_topic", tx("Main topic"), { input: { placeholder: info.default_base_topic } }),
      field("discovery_prefix", tx("Home Assistant's discovery prefix"), { input: { placeholder: "homeassistant" } }),
    ),
  );
}
