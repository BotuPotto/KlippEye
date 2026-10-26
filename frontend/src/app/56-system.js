/* ============================================================================
   56 · SYSTEM PAGE
   Raspberry Pi load and memory, the MCU firmware versions and Moonraker's
   software updates (with confirmation, live progress and rollback).

   The update dialog belongs to the App, not to the page: an update keeps
   running (and the page reloads when it ends) even if the user switches tab.

   KlippEye's own update (the component "klippeye", see app/59b-software-settings.js) is special: Moonraker restarts the backend
   that serves this page, so the answer to the request is cut off and the page cannot ask anything for a few seconds.
   That is expected, not a failure: the dialog waits for the backend to come back (app/17-brain.js), checks what became of
   the update and only then reloads the page.
   ========================================================================== */

const UPDATE_POLL_MS = 1500;
const UPDATE_POLL_LIMIT_MS = 60000;
const UPDATE_RELOAD_DELAY_MS = 3000;
const ROLLBACK_RELOAD_DELAY_MS = 2000;
const BRAIN_RELOAD_DELAY_MS = 1500;
const UPDATE_REFRESH_DELAY_MS = 1500;
const WS_CONNECT_TIMEOUT_MS = 4000;
const WS_CALL_TIMEOUT_MS = 12000;
const WS_RETRY_AFTER_MS = 60000;
/** The system page asks Moonraker for more than the live pollers do (update status can be slow). */
const SYSTEM_READ_TIMEOUT_MS = 15000;

/* ---------------------------------------------------------------------------
   Moonraker access
   ------------------------------------------------------------------------- */

/** Moonraker's `result` (or the whole body); null when the request fails. */
async function fetchResult(url, options) {
  try {
    const response = await fetchFresh(url, { timeout: SYSTEM_READ_TIMEOUT_MS, ...options });
    if (!response.ok) throw new Error(url + " " + response.status);
    const json = await response.json();
    return json.result !== undefined ? json.result : json;
  } catch (error) {
    return null;
  }
}

async function loadMcuStatus() {
  try {
    const list = await fetchResult("/printer/objects/list");
    const objects = (list && list.objects) || list || [];
    const names = objects.filter((name) => name.startsWith("mcu"));
    if (names.length === 0) return null;
    const body = { objects: Object.fromEntries(names.map((name) => [name, null])) };
    const query = await fetchResult("/printer/objects/query", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) });
    return (query && query.status) || (query && query.result && query.result.status) || query;
  } catch (error) {
    return null;
  }
}

async function loadSystemInfo() {
  const [system, proc, printer, updates] = await Promise.all([
    fetchResult("/machine/system_info"),
    fetchResult("/machine/proc_stats"),
    fetchResult("/printer/info"),
    fetchResult("/machine/update/status"),
  ]);
  const mcus = await loadMcuStatus();
  return { system: system && system.system_info ? system.system_info : system, proc, printer, updates, mcus };
}

/**
 * JSON-RPC over Moonraker's websocket, used for the update commands (their
 * progress arrives as notifications). Connects on first use.
 */
const updateSocket = {
  socket: null,
  nextId: 1,
  onProgress: noop, // (message) => void
  onRefreshed: noop, // () => void

  failedAt: 0, // when the websocket last failed to open: the backend that serves this page has none, so it is not asked again at once

  connect() {
    return new Promise((resolve, reject) => {
      if (this.socket && this.socket.readyState === 1) return resolve(this.socket);
      if (this.failedAt && Date.now() - this.failedAt < WS_RETRY_AFTER_MS) return reject(new Error("WS unavailable"));
      const protocol = location.protocol === "https:" ? "wss:" : "ws:";
      const socket = new WebSocket(protocol + "//" + location.host + "/websocket");
      let opened = false;
      socket.onopen = () => {
        opened = true;
        this.socket = socket;
        resolve(socket);
      };
      socket.onerror = (event) => {
        if (!opened) {
          this.failedAt = Date.now();
          reject(event);
        }
      };
      socket.onclose = () => {
        this.socket = null;
      };
      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.method === "notify_update_response") this.onProgress(data.params.message || JSON.stringify(data.params).substring(0, 150));
          if (data.method === "notify_update_refreshed") this.onRefreshed();
        } catch (error) {}
      };
      setTimeout(() => {
        if (opened) return;
        this.failedAt = Date.now();
        try {
          socket.close();
        } catch (error) {}
        reject(new Error("WS timeout"));
      }, WS_CONNECT_TIMEOUT_MS);
    });
  },

  async call(method, params = {}) {
    const socket = await this.connect();
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const onMessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.id !== id) return;
          socket.removeEventListener("message", onMessage);
          if (data.error) reject(new Error(data.error.message));
          else resolve(data.result);
        } catch (error) {}
      };
      socket.addEventListener("message", onMessage);
      socket.send(JSON.stringify({ jsonrpc: "2.0", method, params, id }));
      setTimeout(() => {
        socket.removeEventListener("message", onMessage);
        reject(new Error("WS timeout"));
      }, WS_CALL_TIMEOUT_MS);
    });
  },
};

/** POST (JSON body unless `body` is null) and return the parsed reply; throws Moonraker's message on HTTP errors. */
async function postOrThrow(url, body) {
  const options = { method: "POST" };
  if (body !== null) Object.assign(options, { headers: JSON_HEADERS, body: JSON.stringify(body) });
  const response = await fetch(url, options);
  const text = await response.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch (error) {
    json = { result: text };
  }
  if (!response.ok) throw new Error((json.error && json.error.message) || text || "HTTP " + response.status);
  return json;
}

/** The connection dropped (fetch fails with a TypeError): what happens when the backend restarts under the request. */
const isCutConnection = (error) => error instanceof TypeError || /failed to fetch|networkerror|load failed|network request failed/i.test(String((error && error.message) || ""));

/** Errors that mean "try again later" rather than "this endpoint doesn't exist". */
const isBusyError = (error) => error.message.toLowerCase().includes("busy") || error.message.toLowerCase().includes("print");

/** Upgrades `name` (everything when omitted): websocket first, then plain HTTP. */
async function startUpgrade(name) {
  try {
    return await updateSocket.call("machine.update.upgrade", name ? { name } : {});
  } catch (error) {}
  const attempts = [{ url: "/machine/update/upgrade", body: name ? { name } : {} }];
  if (!name) attempts.push({ url: "/machine/update/full", body: null });
  let lastError = null;
  for (const attempt of attempts) {
    try {
      return await postOrThrow(attempt.url, attempt.body);
    } catch (error) {
      if (isBusyError(error) || isCutConnection(error)) throw error; // a cut connection is not tried again: the update may be under way
      lastError = error;
    }
  }
  throw lastError || new Error("Tutti i metodi falliti");
}

async function rollbackComponent(name) {
  try {
    await updateSocket.call("machine.update.rollback", { name });
  } catch (error) {
    await postOrThrow("/machine/update/rollback", { name });
  }
}

/** Puts the files of a component back as they should be: a soft recovery first, a new copy from the repository when that is not enough. */
async function recoverComponent(name, hard) {
  return postOrThrow("/machine/update/recover", { name, hard: Boolean(hard) });
}

/** What Moonraker says of the KlippEye repository now (null when it cannot be read). */
async function readProgramEntry() {
  const status = await fetchResult("/machine/update/status");
  return status ? programEntry(status.version_info) : null;
}

async function refreshUpdateStatus() {
  try {
    await updateSocket.call("machine.update.refresh", {});
  } catch (error) {
    try {
      await postOrThrow("/machine/update/refresh", {});
    } catch (innerError) {}
  }
}

/* ---------------------------------------------------------------------------
   Interpreting the data
   ------------------------------------------------------------------------- */
const shortHash = (hash) => (hash ? hash.substring(0, 7) : "-");

/** One entry of Moonraker's update status, ready to display. */
function describeComponent(key, info) {
  const isSystem = info.configured_type === "system" || key === "system";
  const current = isSystem ? (info.package_count != null ? info.package_count + " pkg" : "system") : info.version || shortHash(info.current_hash);
  const remote = isSystem ? "" : info.remote_version || shortHash(info.remote_hash);
  const behind = info.commits_behind ? info.commits_behind.length : 0;
  const hasUpdate = isSystem ? info.package_count > 0 : (current !== remote && remote && remote !== "-" && remote !== "system") || behind > 0 || (info.package_count && info.package_count > 0);
  let badge = { tone: "ok", text: "Aggiornato" };
  if (info.corrupt) badge = { tone: "error", text: "Corrotto" };
  else if (!isSystem && info.is_valid === false) badge = { tone: "error", text: "Invalido" };
  else if (hasUpdate) badge = { tone: "update", text: isSystem ? info.package_count + " update" : "Update" };
  return {
    key,
    raw: info,
    isSystem,
    name: key === PROGRAM_COMPONENT ? "KlippEye (backend, dashboard, notifiche)" : info.name || key,
    current,
    remote,
    behind,
    hasUpdate: !!hasUpdate,
    badge,
    packageSummary: isSystem && info.package_list ? info.package_list.slice(0, 2).join(", ") : "",
    packageList: info.package_list ? info.package_list.slice(0, 5).join(", ") : "",
    packageCount: info.package_count || 0,
    canRollback: !!info.rollback_version && !isSystem,
    rollbackVersion: info.rollback_version || "precedente",
  };
}

function describeUpdates(updates) {
  programEntry(updates && updates.version_info); // which name Moonraker knows the program by (KlippEye, or VzBot before the move)
  const components = Object.entries((updates && updates.version_info) || {})
    .filter(([, info]) => info && typeof info === "object")
    .map(([key, info]) => describeComponent(key, info));
  return { components, availableCount: components.filter((component) => component.hasUpdate).length, busy: !!(updates && updates.busy) };
}

/**
 * Components named by "Aggiorna tutto". Decided on versions and pending
 * commits/packages only, so it can differ from the per-row "Update" badge.
 */
function fullUpdateTargets(updates) {
  return Object.entries((updates && updates.version_info) || {})
    .filter(([, info]) => {
      const current = (info && info.version) || "";
      const remote = (info && info.remote_version) || "";
      return (current !== remote && remote) || (info && info.commits_behind && info.commits_behind.length > 0) || (info && info.package_count > 0);
    })
    .map(([key]) => key);
}

const usageTone = (percent, warn, danger) => (percent > danger ? "danger" : percent > warn ? "warn" : "ok");

function describeHost(system, proc) {
  const cpu = (system && system.cpu_info) || {};
  const cpuUsage = proc && proc.system_cpu_usage;
  const cpuPercent = (typeof cpuUsage === "object" ? cpuUsage && cpuUsage.cpu : cpuUsage) || 0;
  const memory = (proc && proc.system_memory) || {};
  const memoryPercent = memory.total ? ((memory.used || 0) / memory.total) * 100 : 0;
  return {
    model: cpu.model || "PI",
    distribution: ((system && system.distribution) || {}).name || "",
    cpuPercent,
    cpuTemp: proc && proc.cpu_temp,
    cpuTone: usageTone(cpuPercent, 60, 85),
    memoryPercent,
    memoryTone: usageTone(memoryPercent, 70, 85),
    memoryText: memory.total ? ((memory.used || 0) / 1024).toFixed(0) + " / " + (memory.total / 1024).toFixed(0) + " MiB" : "-",
  };
}

/* ---------------------------------------------------------------------------
   Update dialog: confirmation → progress → done
   ------------------------------------------------------------------------- */
const CLOSED_DIALOG = { open: false, mode: null, title: "", sub: "", info: null, log: null, progress: null, cancel: null, confirm: null };

const InfoBox = ({ className, children }) => h("div", { className: cx("oui-tile update-info", className) }, children);
const InfoValue = ({ wrap, children }) => h("div", { className: cx("update-info-value", wrap && "update-info-value--wrap") }, children);
const UpdateWorking = ({ text }) => h("div", { className: "update-working" }, h("div", { className: "dialog-spinner" }), h("div", { className: "update-working-text" }, text));
const ResultBox = ({ tone, title, text }) =>
  h("div", { className: cx("oui-tile update-result", tone === "ok" ? "oui-tile--ok update-result--ok" : "oui-tile--danger update-result--error") }, h("div", { className: "update-result-title" }, title), text && h("div", { className: "update-result-text" }, text));

/** The confirmation of KlippEye's own update: releases, what is coming, and what will happen to the backend. */
function ProgramUpdateInfo({ component }) {
  const version = useBrainVersion(true);
  const remote = useRemoteRelease(component.raw);
  const raw = component.raw || {};
  const behind = raw.commits_behind_count != null ? Number(raw.commits_behind_count) : component.behind;
  const current = version.state === "ok" ? version.info.release : "?";
  return h(
    InfoBox,
    { className: "update-info--program" },
    h(
      "div",
      { className: "update-info--versions" },
      h("div", null, h("div", { className: "update-info-label" }, "Installata"), h("div", { className: "update-version" }, current)),
      h("div", { className: "update-info-right" }, h("div", { className: "update-info-label" }, "Nuova"), h("div", { className: "update-version update-version--new" }, remote || behind + (behind === 1 ? " modifica" : " modifiche"))),
    ),
    h(CommitList, { commits: raw.commits_behind }),
    h("p", { className: "update-note" }, "Moonraker scarica i file nuovi e riavvia il backend: per qualche secondo la pagina non risponde, poi si ricarica da sola. Impostazioni, chiave dell'IA e notifiche non vengono toccate."),
  );
}

/** What to ask the user before running an update / full update / rollback / recovery. */
function confirmationFor(kind, subject) {
  if (kind === "recover") {
    return {
      mode: "confirm-recover",
      confirmText: "Ripristina",
      view: {
        title: "Ripristinare i file di KlippEye?",
        sub: "Torna la versione ufficiale installata",
        info: h(
          InfoBox,
          null,
          h("p", { className: "update-note" }, "I file del programma sul Raspberry sono stati modificati a mano e Moonraker per questo non li aggiorna. Il ripristino li riporta come sono su GitHub; poi il backend si riavvia."),
          h("p", { className: "update-note" }, "Impostazioni, chiave dell'IA e notifiche stanno in un'altra cartella e non si toccano."),
        ),
      },
    };
  }
  if (kind === "update" && subject.key === PROGRAM_COMPONENT) {
    return { mode: "confirm-update", confirmText: "Aggiorna", view: { title: "Aggiornare KlippEye?", sub: "backend, dashboard e notifiche", info: h(ProgramUpdateInfo, { component: subject }) } };
  }
  if (kind === "rollback" && subject.key === PROGRAM_COMPONENT) {
    return {
      mode: "confirm-rollback",
      confirmText: "Torna indietro",
      view: {
        title: "Tornare alla versione precedente?",
        sub: "Versione " + subject.rollbackVersion,
        info: h(InfoBox, null, h("p", { className: "update-note" }, "KlippEye torna com'era prima dell'ultimo aggiornamento e il backend si riavvia. Le impostazioni non cambiano. Per aggiornare di nuovo basta ripremere Aggiorna.")),
      },
    };
  }
  if (kind === "update-all") {
    return {
      mode: "confirm-full",
      confirmText: "Aggiorna tutto",
      view: { title: "Aggiornare tutto?", sub: subject.length + " componenti", info: h(InfoBox, null, h(InfoValue, null, subject.join(", "))) },
    };
  }
  if (kind === "rollback") {
    return {
      mode: "confirm-rollback",
      confirmText: "Rollback",
      view: {
        title: "Rollback " + subject.key + "?",
        sub: "Ripristina " + subject.rollbackVersion.substring(0, 7),
        info: h(InfoBox, null, h(InfoValue, null, "Rollback a: " + subject.rollbackVersion)),
      },
    };
  }
  if (subject.isSystem) {
    return {
      mode: "confirm-update",
      confirmText: "Aggiorna sistema",
      view: {
        title: "Aggiornare sistema?",
        sub: subject.packageCount ? subject.packageCount + " pacchetti" : "Aggiornamento OS",
        info: h(
          InfoBox,
          { className: "update-info--packages" },
          h("div", { className: "update-info-label" }, "Pacchetti"),
          h(InfoValue, { wrap: true }, subject.packageList || "system"),
          h("div", { className: "update-info-count" }, subject.packageCount + " pacchetti"),
        ),
      },
    };
  }
  return {
    mode: "confirm-update",
    confirmText: "Aggiorna",
    view: {
      title: "Aggiornare " + subject.key + "?",
      sub: subject.current + " -> " + subject.remote + " " + (subject.behind ? "• " + subject.behind + " behind" : ""),
      info: h(
        InfoBox,
        { className: "update-info--versions" },
        h("div", null, h("div", { className: "update-info-label" }, "Attuale"), h("div", { className: "update-version" }, subject.current)),
        h("div", { className: "update-info-right" }, h("div", { className: "update-info-label" }, "Nuova"), h("div", { className: "update-version update-version--new" }, subject.remote)),
      ),
    },
  };
}

/** Moonraker's refusals in plain Italian (the original text stays in the log). */
function friendlyUpdateError(message) {
  const text = String(message || "");
  if (/print|busy/i.test(text)) return "C'è una stampa in corso (o un altro aggiornamento): riprova quando ha finito. (" + text + ")";
  if (/not valid|repo not valid|dirty/i.test(text)) return "I file del programma sul Raspberry non sono in ordine (modificati a mano?). In Impostazioni → Aggiornamenti c'è il tasto «Ripristina i file del programma». (" + text + ")";
  return text;
}

/** State machine of the update dialog; call once, in the App. */
function useUpdateDialog() {
  const [dialog, setDialog] = useState(CLOSED_DIALOG);
  const target = useRef({ name: null, full: false, brain: false });
  const pollTimer = useRef(null);

  const patch = (changes) => setDialog((previous) => ({ ...previous, ...changes }));
  const log = (message) => setDialog((previous) => ({ ...previous, log: [...(previous.log || []), "[" + localTimeString() + "] " + message] }));
  const progress = (percent, text) => patch({ progress: percent, ...(text ? { sub: text } : {}) });
  const close = () => {
    clearInterval(pollTimer.current);
    setDialog(CLOSED_DIALOG);
  };

  useEffect(() => {
    updateSocket.onProgress = log;
    return () => {
      updateSocket.onProgress = noop;
      clearInterval(pollTimer.current);
    };
  }, []);

  // The bar starts empty. (The original asked for 10 % / 20 % as a unit-less number, which the browser
  // ignores, so it never showed that initial fill: the first real value is the one set by progress().)
  const startProgress = (title, sub, working) =>
    setDialog({ ...CLOSED_DIALOG, open: true, mode: "progress", title, sub, info: h(UpdateWorking, { text: working }), log: [], progress: 0 });
  const showDone = (info) => patch({ mode: "progress-done", info, cancel: null, confirm: { text: "Ricarica" } });
  const brainLost = () =>
    showFailure(
      "Il backend non è tornato entro due minuti e mezzo. Da Mainsail apri Aggiornamenti e usa Rollback sulla voce klippeye (o riavvia il servizio klippeye); dal terminale: klippeye log.",
    );
  function showFailure(message) {
    patch({ cancel: { text: "Chiudi" }, confirm: null, info: h(ResultBox, { tone: "error", title: "Fallito", text: message }) });
  }

  /** Polls Moonraker until the update stops being busy, then reloads the page. */
  const watchUpdate = () => {
    let percent = 35;
    const startedAt = Date.now();
    pollTimer.current = setInterval(async () => {
      if (Date.now() - startedAt > UPDATE_POLL_LIMIT_MS) {
        clearInterval(pollTimer.current);
        patch({ cancel: { text: "Chiudi" } }); // still running: let the user leave the dialog
        return;
      }
      const status = await fetchResult("/machine/update/status");
      if (!status) return;
      if (status.busy) {
        percent = Math.min(90, percent + 2);
        return progress(percent, "BUSY...");
      }
      clearInterval(pollTimer.current);
      progress(100, "Completato!");
      log("Completato!");
      showDone(h(ResultBox, { tone: "ok", title: "Aggiornamento completato", text: "Riavvio servizi..." }));
      setTimeout(() => location.reload(), UPDATE_RELOAD_DELAY_MS);
    }, UPDATE_POLL_MS);
  };

  /**
   * The backend is about to restart (or has): wait for it to come back, check with `verify()` what became of the work, and
   * reload the page. If Moonraker did the work but did not restart the backend, restart it here: the new files must run.
   */
  const finishAfterBrainRestart = async (before, doneTitle, verify) => {
    progress(40, "Il backend si riavvia...");
    patch({ info: h(UpdateWorking, { text: "Il backend si riavvia: la pagina si ricollega da sola..." }) });
    let result = await waitForBrain(before, (seconds) => progress(Math.min(92, 40 + seconds), "Attendo il backend... " + seconds + " s"), verify);
    if (result.ok && result.restarted === false) {
      log("Il backend non si è riavviato da solo: lo riavvio io.");
      const again = await readBrainVersion();
      try {
        await moonraker.serviceAction("restart", PROGRAM_COMPONENT);
      } catch (error) {} // the connection is cut as the backend goes down: expected
      result = await waitForBrain(again, (seconds) => progress(Math.min(95, 60 + seconds), "Attendo il backend... " + seconds + " s"));
    }
    if (!result.ok) {
      progress(100, "Il backend non è tornato");
      log("Il backend non risponde più.");
      return brainLost();
    }
    log("Il backend è tornato (release " + result.info.release + ").");
    const outcome = await verify();
    if (outcome !== true) {
      progress(100, "Non completato");
      log("ESITO: " + outcome);
      return showFailure(outcome);
    }
    progress(100, "Completato!");
    log("Completato!");
    showDone(h(ResultBox, { tone: "ok", title: doneTitle, text: "Release " + result.info.release + ": ricarico la pagina..." }));
    return setTimeout(() => location.reload(), BRAIN_RELOAD_DELAY_MS);
  };

  const runUpdate = async (name, full, brain) => {
    startProgress(full ? "Aggiornamento completo" : name === PROGRAM_COMPONENT ? "Aggiornamento KlippEye" : "Aggiornamento " + name, "Avvio...", "Preparazione...");
    log("Avvio upgrade " + (name || "FULL"));
    const before = brain ? await readBrainVersion() : null;
    const verify = async () => {
      const entry = await readProgramEntry();
      if (!entry) return true; // Moonraker did not answer: the backend is back, which is what could be checked
      return Number(entry.commits_behind_count) > 0 ? "Il backend è tornato ma l'aggiornamento non risulta completato: in Mainsail, Aggiornamenti, c'è scritto il motivo." : true;
    };
    try {
      progress(20, "Connessione...");
      const result = await startUpgrade(name);
      progress(30, "Avviato - in corso...");
      log("Avviato: " + JSON.stringify(result).substring(0, 200));
      if (brain) return finishAfterBrainRestart(before, "Aggiornamento completato", verify);
      return watchUpdate();
    } catch (error) {
      if (brain && isCutConnection(error)) return finishAfterBrainRestart(before, "Aggiornamento completato", verify);
      progress(100, "Errore");
      log("ERRORE: " + error.message);
      return showFailure(friendlyUpdateError(error.message));
    }
  };

  const runRollback = async (name) => {
    const brain = name === PROGRAM_COMPONENT;
    startProgress(brain ? "Versione precedente di KlippEye" : "Rollback " + name, "Ripristino...", "Rollback...");
    log("Rollback " + name);
    const before = brain ? await readBrainVersion() : null;
    try {
      await rollbackComponent(name);
      log("Rollback OK");
      if (brain) return finishAfterBrainRestart(before, "Versione precedente ripristinata", async () => true);
      progress(100, "Completato");
      showDone(null);
      return setTimeout(() => location.reload(), ROLLBACK_RELOAD_DELAY_MS);
    } catch (error) {
      if (brain && isCutConnection(error)) return finishAfterBrainRestart(before, "Versione precedente ripristinata", async () => true);
      log("Fallito: " + error.message);
      return showFailure(friendlyUpdateError(error.message));
    }
  };

  const runRecover = async (name) => {
    startProgress("Ripristino dei file di KlippEye", "Ripristino...", "Ripristino...");
    log("Ripristino di " + name);
    const before = await readBrainVersion();
    const verify = async () => {
      const entry = await readProgramEntry();
      return !entry || (entry.is_valid !== false && !entry.is_dirty && !entry.corrupt) ? true : "Il backend è tornato ma Moonraker segna ancora il programma come non in ordine: prova il ripristino da Mainsail (Aggiornamenti, voce klippeye).";
    };
    const attempt = async (hard) => {
      try {
        await recoverComponent(name, hard);
        return null;
      } catch (error) {
        return error;
      }
    };
    let error = await attempt(false);
    if (error && !isCutConnection(error)) {
      log("Il ripristino semplice non è bastato (" + error.message + "): riscarico il programma da GitHub.");
      error = await attempt(true);
    }
    if (error && !isCutConnection(error)) {
      log("Fallito: " + error.message);
      return showFailure(friendlyUpdateError(error.message));
    }
    return finishAfterBrainRestart(before, "File ripristinati", verify);
  };

  const ask = (kind, subject, name, full) => {
    const confirmation = confirmationFor(kind, subject);
    target.current = { name, full, brain: full ? Array.isArray(subject) && subject.includes(PROGRAM_COMPONENT) : name === PROGRAM_COMPONENT };
    setDialog({ ...CLOSED_DIALOG, open: true, mode: confirmation.mode, ...confirmation.view, cancel: { text: "Annulla" }, confirm: { text: confirmation.confirmText } });
  };

  return {
    dialog,
    close,
    askUpdate: (component) => ask("update", component, component.key, false),
    askUpdateAll: (names) => ask("update-all", names, null, true),
    askRollback: (component) => ask("rollback", component, component.key, false),
    askRecover: (component) => ask("recover", component, component.key, false),
    confirm() {
      const { name, full, brain } = target.current;
      if (dialog.mode === "confirm-update") runUpdate(name, full, brain);
      else if (dialog.mode === "confirm-rollback") runRollback(name);
      else if (dialog.mode === "confirm-recover") runRecover(name);
      else if (dialog.mode === "confirm-full") runUpdate(null, true, brain);
      else if (dialog.mode === "progress-done") {
        close();
        location.reload();
      }
    },
    /** Tapping the backdrop closes the confirmation steps only (never a running update). */
    dismissOnBackdrop() {
      if (dialog.mode && dialog.mode.startsWith("confirm")) close();
    },
  };
}

function UpdateDialog({ controller }) {
  const { dialog } = controller;
  const logRef = useRef(null);
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [dialog.log]);
  if (!dialog.open) return null;
  return h(
    "div",
    { className: "sheet-overlay", onClick: (e) => e.target === e.currentTarget && controller.dismissOnBackdrop() },
    h(
      "div",
      { className: "sheet-card sheet-card--column" },
      h(
        "div",
        { className: "sheet-header" },
        h("div", { className: "dialog-title" }, dialog.title),
        h("div", { className: "dialog-sub" }, dialog.sub),
        dialog.progress !== null && h("div", { className: "oui-progress dialog-progress" }, h("div", { className: "oui-progress__bar", style: { width: dialog.progress + "%" } })),
      ),
      h(
        "div",
        { className: "sheet-body" },
        h("div", null, dialog.info),
        dialog.log &&
          h(
            "div",
            { className: "dialog-log-section" },
            h("div", { className: "oui-label mb-2" }, "Log live"),
            h("div", { className: "dialog-log oui-well", ref: logRef }, dialog.log.map((line, index) => h("div", { key: index, className: "dialog-log-line" }, line))),
          ),
      ),
      h(
        "div",
        { className: "sheet-footer" },
        dialog.cancel && h("button", { className: "oui-btn", onClick: controller.close }, dialog.cancel.text),
        dialog.confirm && h("button", { className: "oui-btn oui-btn--primary", onClick: controller.confirm }, dialog.confirm.text),
      ),
    ),
  );
}

/* ---------------------------------------------------------------------------
   Cards
   ------------------------------------------------------------------------- */
function SystemCard({ label, sublabel, actions, children }) {
  return h(
    Card,
    null,
    h(
      "div",
      { className: "sys-card-header" },
      h("div", { className: "min-w-0" }, h(SectionTitle, null, label), sublabel ? h("div", { className: "oui-caption sys-sublabel" }, sublabel) : null),
      actions,
    ),
    children,
  );
}
const LoadingCard = ({ label, text }) => h(Card, null, h(SectionTitle, null, label), h("div", { className: "oui-caption mt-2" }, text));

function StatBox({ label, value, percent, tone, footnote }) {
  return h(
    "div",
    { className: "oui-tile stat-box" },
    h("div", { className: "oui-label" }, label),
    h("div", { className: "stat-box-value" }, value),
    h("div", { className: "oui-progress stat-bar" }, h("div", { className: cx("oui-progress__bar", tone !== "ok" && "oui-progress__bar--" + tone), style: { width: Math.min(100, percent).toFixed(0) + "%" } })),
    footnote && h("div", { className: "oui-caption stat-box-footnote" }, footnote),
  );
}

function HostCard({ data, onRefresh }) {
  if (!data.system && !data.proc) return h(LoadingCard, { label: "Host", text: "Caricamento..." });
  const host = describeHost(data.system, data.proc);
  return h(
    SystemCard,
    {
      label: "Host • " + host.model,
      sublabel: host.distribution,
      actions: h("button", { onClick: onRefresh, className: "oui-btn oui-btn--sm" }, h(Icons.Refresh, { size: 16 }), "Aggiorna dati"),
    },
    h(
      "div",
      { className: "stat-grid" },
      h(StatBox, { label: "CPU" + (host.cpuTemp != null ? " • " + host.cpuTemp.toFixed(1) + "°C" : ""), value: host.cpuPercent.toFixed(1) + "%", percent: host.cpuPercent, tone: host.cpuTone }),
      h(StatBox, { label: "Memoria", value: host.memoryPercent.toFixed(0) + "%", percent: host.memoryPercent, tone: host.memoryTone, footnote: host.memoryText }),
    ),
  );
}

function McuCard({ data }) {
  const printer = data.printer || {};
  const mcus = data.mcus || {};
  const names = Object.keys(mcus).length ? Object.keys(mcus) : ["mcu"];
  return h(
    SystemCard,
    { label: "MCU e firmware", sublabel: "Klipper " + (printer.software_version || "") },
    h(
      "div",
      { className: "oui-list" },
      names.map((name) => {
        const info = mcus[name] || {};
        return h(
          "div",
          { key: name, className: "mcu-row" },
          h("div", { className: "min-w-0" }, h("div", { className: "oui-label" }, name), h("div", { className: "mcu-row__version" }, info.mcu_version || info.version || printer.software_version || "-")),
          h("span", { className: "oui-badge oui-badge--ok" }, h("span", { className: "oui-dot" }), "Connesso"),
        );
      }),
    ),
  );
}

const UPDATE_BADGE_CLASS = { ok: "oui-badge--ok", update: "oui-badge--warn", error: "oui-badge--danger" };

function UpdateRow({ component, onUpdate, onRollback }) {
  const { badge } = component;
  const versions = component.key === PROGRAM_COMPONENT
    ? component.behind
      ? component.behind + (component.behind === 1 ? " modifica in arrivo" : " modifiche in arrivo")
      : "aggiornato"
    : component.current +
    (component.remote ? " -> " + component.remote : "") +
    " " +
    (component.behind ? " • " + component.behind + " behind" : "") +
    " " +
    (component.packageSummary ? " • " + component.packageSummary : "");
  return h(
    "div",
    { className: cx("update-row", component.hasUpdate && "has-update") },
    h(
      "div",
      { className: "update-row-main" },
      h("div", { className: "update-row-title" }, h("span", { className: "update-row-name" }, component.name), h("span", { className: cx("oui-badge", UPDATE_BADGE_CLASS[badge.tone]) }, badge.text)),
      h("div", { className: "update-row-versions" }, versions),
    ),
    (component.hasUpdate || component.canRollback) &&
      h(
        "div",
        { className: "update-row-actions" },
        component.hasUpdate && h("button", { className: "oui-btn oui-btn--sm oui-btn--primary", onClick: () => onUpdate(component) }, "Aggiorna"),
        component.canRollback && h("button", { className: "oui-btn oui-btn--sm", onClick: () => onRollback(component) }, "Rollback"),
      ),
  );
}

function UpdatesCard({ data, controller, onCheck }) {
  if (!data.updates) return h(LoadingCard, { label: "Aggiornamenti", text: "Caricamento..." });
  const { components, availableCount, busy } = describeUpdates(data.updates);
  return h(
    SystemCard,
    {
      label: "Aggiornamenti",
      sublabel: (availableCount ? availableCount + " disponibili" : "Tutto aggiornato") + (busy ? " • busy" : ""),
      actions: h(
        "div",
        { className: "sys-actions" },
        h("button", { className: "oui-btn oui-btn--sm", onClick: onCheck }, "Controlla"),
        availableCount > 0 && h("button", { className: "oui-btn oui-btn--sm oui-btn--primary", onClick: () => controller.askUpdateAll(fullUpdateTargets(data.updates)) }, "Aggiorna tutto"),
      ),
    },
    components.length ? h("div", { className: "oui-list" }, components.map((component) => h(UpdateRow, { key: component.key, component, onUpdate: controller.askUpdate, onRollback: controller.askRollback }))) : h("div", { className: "oui-caption" }, "Nessun componente"),
  );
}

/** The page's data: fetched on every visit, plus on request and when Moonraker reports a refresh. */
function useSystemData() {
  const [data, setData] = useState(null);
  const reload = async () => setData(await loadSystemInfo());

  useEffect(() => {
    reload();
    updateSocket.onRefreshed = reload;
    return () => {
      updateSocket.onRefreshed = noop;
    };
  }, []);

  const checkForUpdates = async () => {
    await refreshUpdateStatus();
    setTimeout(reload, UPDATE_REFRESH_DELAY_MS);
  };

  return { data, reload, checkForUpdates };
}

function SystemPage({ controller }) {
  const { data, reload, checkForUpdates } = useSystemData();

  return data
    ? h("div", { className: "sys-grid" }, h(HostCard, { data, onRefresh: reload }), h(McuCard, { data }), h(UpdatesCard, { data, controller, onCheck: checkForUpdates }))
    : h(LoadingCard, { label: "Sistema", text: "Caricamento..." });
}
