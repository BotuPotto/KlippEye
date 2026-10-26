/* ============================================================================
   12 · API LAYER
   Every HTTP call to Moonraker (the Klipper API) and to the KlippEye "backend"
   backend goes through this file, so endpoints live in exactly one place.
   ========================================================================== */

const JSON_HEADERS = { "Content-Type": "application/json" };

/* ---------------------------------------------------------------------------
   G-code sending with duplicate suppression
   Two identical scripts sent less than 500 ms apart (a double tap, a touch +
   click pair, ...) are collapsed into one. The check is shared by the Moonraker
   endpoint and the backend endpoint.
   ------------------------------------------------------------------------- */
const GCODE_DUPLICATE_WINDOW_MS = 500;
const gcodeGuard = {
  lastScript: "",
  lastTime: 0,
  /** Returns true when `script` repeats the previous one inside the window. */
  isDuplicate(script) {
    const squash = (s) => s.replace(/\s+/g, " ").trim();
    const now = Date.now();
    const duplicate = squash(script) === squash(this.lastScript) && now - this.lastTime < GCODE_DUPLICATE_WINDOW_MS;
    if (!duplicate) {
      this.lastScript = script;
      this.lastTime = now;
    }
    return duplicate;
  },
};
/** Stand-in for a Response when a duplicate is dropped (callers keep working). */
const blockedDuplicateResponse = () => ({
  ok: true,
  json: () => Promise.resolve({ result: "blocked duplicate" }),
  text: () => Promise.resolve("blocked"),
});

function postGcodeTo(endpoint, script) {
  const trimmed = (script || "").trim();
  if (trimmed && gcodeGuard.isDuplicate(trimmed)) return Promise.resolve(blockedDuplicateResponse());
  return fetch(endpoint, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ script }) });
}

/** Sends G-code through Moonraker. Rejects on network failure. */
const sendGcode = (script) => postGcodeTo("/printer/gcode/script", script);
/** Same, but ignores failures (fire-and-forget buttons). */
const fireGcode = (script) => {
  try {
    sendGcode(script).catch(noop);
  } catch (e) {}
};
/** Sends G-code through the backend backend (/api/gcode). */
const sendBrainGcode = (script) => postGcodeTo("/api/gcode", script);

/** Klipper's own words for a failed request: Moonraker's { error: { message } }, a plain { error }, or the raw text. */
async function errorMessageOf(response) {
  const text = await response.text().catch(() => "");
  try {
    const json = JSON.parse(text);
    const error = json.error;
    return (error && error.message) || (typeof error === "string" ? error : "") || text || "HTTP " + response.status;
  } catch (e) {
    return text || "HTTP " + response.status;
  }
}

/**
 * Sends a script that may run for minutes (probing, calibration) and says what became of it.
 * The backend's proxy drops a request after 10 s with a 502 while Klipper carries on, so that timeout
 * is "still running", not a failure. Resolves
 *   { ok: true, finished: true }    Klipper answered: the script is done;
 *   { ok: true, finished: false }   the proxy timed out: it is still running;
 *   { ok: false, message }          Klipper refused it or could not be reached.
 */
async function sendLongGcode(script) {
  try {
    const response = await sendGcode(script);
    if (response.ok) return { ok: true, finished: true };
    const message = await errorMessageOf(response);
    if (response.status === 502 && /time/i.test(message)) return { ok: true, finished: false };
    return { ok: false, message };
  } catch (error) {
    return { ok: false, message: error.message || tx("printer not reachable") };
  }
}

/* ---------------------------------------------------------------------------
   Generic helpers
   ------------------------------------------------------------------------- */
/** A read nobody has answered after this long is given up: a healthy answer takes milliseconds. */
const READ_TIMEOUT_MS = 6000;
/** The reads still waiting for an answer, so that coming back from a sleep can cancel them all (app/15-live.js). */
const readsInFlight = new Set();

/** Cancels every read still waiting: after a sleep their connections are dead and they would never end. */
function abortReadsInFlight() {
  for (const controller of [...readsInFlight]) controller.abort();
  readsInFlight.clear();
}

/**
 * fetch that never goes to the cache. A GET is cancelled after `timeout` ms (default READ_TIMEOUT_MS, 0 = never) and by
 * abortReadsInFlight(); other methods (commands, uploads, the AI analysis) are left alone unless `timeout` is given.
 * Without this a request on a dead connection waits for ever, and a browser keeps only six connections to one address:
 * six such requests and no other request of the page goes out any more.
 */
function fetchFresh(url, options = {}) {
  const { timeout = (options.method || "GET").toUpperCase() === "GET" ? READ_TIMEOUT_MS : 0, signal, ...init } = options;
  if (!timeout) return fetch(url, { cache: "no-store", signal, ...init });
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal) signal.aborted ? abort() : signal.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(abort, timeout);
  readsInFlight.add(controller);
  return fetch(url, { cache: "no-store", ...init, signal: controller.signal }).finally(() => {
    clearTimeout(timer);
    readsInFlight.delete(controller);
    if (signal) signal.removeEventListener("abort", abort);
  });
}

async function fetchJson(url, options) {
  const response = await fetchFresh(url, options);
  return response.json();
}

/** POST with no body (Moonraker action endpoints). */
const postAction = (url) => fetch(url, { method: "POST" });

/* ---------------------------------------------------------------------------
   Moonraker — Klipper API
   ------------------------------------------------------------------------- */
const moonraker = {
  /** GET /printer/objects/query?<names>; resolves to `result.status`. */
  async queryObjects(query, options) {
    const json = await fetchJson("/printer/objects/query?" + query, options);
    return (json.result && json.result.status) || {};
  },
  emergencyStop: () => postAction("/printer/emergency_stop"),
  firmwareRestart: () => postAction("/printer/firmware_restart"),
  klipperRestart: () => postAction("/printer/restart"),
  saveConfig: () => postAction("/machine/save_config"),
  /** The raw answer of /printer/info: { result: { state, state_message } }; 503 while Klipper is not connected to Moonraker. */
  printerInfo: (options) => fetchFresh("/printer/info", options),
  /** The Raspberry itself (`result.system_info`: available_services, service_state, ...). */
  async systemInfo(options) {
    const json = await fetchJson("/machine/system_info", options);
    return (json.result && json.result.system_info) || {};
  },
  /** `action`: "restart", "start" or "stop"; `service`: a systemd service Moonraker may manage (klipper, moonraker, crowsnest...). */
  serviceAction: (action, service) => postAction("/machine/services/" + action + "?service=" + encodeURIComponent(service)),
  rebootHost: () => postAction("/machine/reboot"),
  shutdownHost: () => postAction("/machine/shutdown"),
  /** Klipper's `configfile` object ({ settings, save_config_pending, ... }); `fields` narrows it, e.g. "save_config_pending". */
  async configfile(fields, options) {
    const status = await moonraker.queryObjects("configfile" + (fields ? "=" + fields : ""), options);
    return status.configfile || {};
  },
  /** Every registered G-code command as { NAME: help text }. */
  async gcodeCommands(options) {
    const json = await fetchJson("/printer/gcode/help", options);
    return json.result || {};
  },
  /** Webhooks state, e.g. { state: "ready" | "shutdown" | "error", state_message }. */
  async webhooks(options) {
    const status = await moonraker.queryObjects("webhooks", options);
    return status.webhooks || {};
  },
};

/* ---------------------------------------------------------------------------
   backend — KlippEye backend
   ------------------------------------------------------------------------- */
const brain = {
  /** Aggregated printer snapshot { heater_bed, extruder, raw: {...} }. */
  printer: () => fetchJson("/api/printer"),
};
