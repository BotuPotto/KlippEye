/* ============================================================================
   30 · KLIPPER STATE
   The panel Mainsail shows when Klipper is not "ready" ("Klipper reports: SHUTDOWN"), and the restarts that
   lead into and out of it. What it does, after Mainsail's own behaviour:

     · it asks Klipper how it is (/printer/info: state + state_message), now and then when all is well, every
       2 s when it is not; a shutdown line in the console, or the emergency stop, asks at once;
     · state "startup" / "shutdown" / "error": the panel shows Klipper's own message and the restart buttons;
       state "disconnected" (Moonraker cannot reach Klipper): it says so;
     · a restart started here (the panel's buttons, the power menu, SAVE_CONFIG) shows a loading ring until Klipper
       is back. If it comes back as "shutdown" or "error" the panel appears again with the NEW message: the
       answers that still describe the state from before the restart are ignored until Klipper was seen going down;
     · a restart that works reloads the page (as the panel always did), so that everything is read afresh.

   The Raspberry's own restarts (Moonraker, the whole machine) go through the same ring: while they run nothing
   answers, which is not an error but exactly what is expected.
   ========================================================================== */

/** How often Klipper is asked how it is, by situation (ms). */
const KLIPPER_WATCH_MS = {
  ready: 4000, // all is well: now and then (a shutdown line in the console and the emergency stop ask at once)
  fault: 2000, // Klipper is not ready: Mainsail's rhythm
  restarting: 1000, // a restart is under way
  alert: 500, // just after something that may shut Klipper down
};
const KLIPPER_ALERT_MS = 6000;
const KLIPPER_INFO_TIMEOUT_MS = 3000;
/** Klipper takes a moment to disconnect: until it was seen going down, a "shutdown" / "error" answer is the one from before. */
const KLIPPER_RESTART_GRACE_MS = 6000;
/** A "disconnected" Klipper is most likely restarting (anyone may have asked): this long it shows the ring, then the explanation. */
const KLIPPER_DISCONNECTED_PATIENCE_MS = 25000;
const KLIPPER_RELOAD_DELAY_MS = 800;
/** A host that was told to shut down should stop answering; if it never does, the "shutting down" panel goes away after this long. */
const HOST_OFF_LIMIT_MS = 90000;

/** The restarts this dashboard can start. `limit`: how long to wait for the machine to answer again before giving up. */
const RESTART_KINDS = {
  klipper: { label: tx("Restarting Klipper"), limit: 90000, grace: KLIPPER_RESTART_GRACE_MS, reload: true },
  firmware: { label: tx("Restarting the firmware"), limit: 90000, grace: KLIPPER_RESTART_GRACE_MS, reload: true },
  service: { label: tx("Restarting the Klipper service"), limit: 90000, grace: KLIPPER_RESTART_GRACE_MS, reload: true },
  moonraker: { label: tx("Restarting Moonraker"), limit: 120000, grace: KLIPPER_RESTART_GRACE_MS, reload: true },
  // the program that serves this page: it is back when it answers again, whatever Klipper is doing (it may be off: "disconnected")
  brain: { label: tx("Restarting the backend"), limit: 120000, grace: KLIPPER_RESTART_GRACE_MS, reload: true, anyAnswer: true },
  host: { label: tx("Restarting the Raspberry"), limit: 360000, grace: KLIPPER_RESTART_GRACE_MS, reload: true },
  save: { label: tx("Saving and restarting Klipper"), limit: 90000, grace: 4000, reload: false }, // SAVE_CONFIG may have nothing to save: then nothing restarts
};
/** Services whose restart takes Klipper (or the whole of Moonraker) away for a while, by name. */
const SERVICE_RESTART_KIND = { klipper: "service", moonraker: "moonraker", klippeye: "brain" };
/** Services whose restart cuts the connection of this very page (Moonraker answers through the backend; the backend is the page's server). */
const CUTS_CONNECTION = ["moonraker", "klippeye"];

/* Messages of the console that mean "Klipper is down". */
const isShutdownMessage = (msg) => msg.includes("klipper state: shutdown") || msg.includes("shutdown due to") || msg.includes("printer is shutdown");

const klipperReadyListeners = new Set();
/** `listener()` runs when Klipper is ready again after having been away or in a fault (the config may have changed). Returns the unsubscribe. */
function onKlipperReady(listener) {
  klipperReadyListeners.add(listener);
  return () => klipperReadyListeners.delete(listener);
}

/**
 * One look at Klipper: { phase, message }. phase is Klipper's state ("ready", "startup", "shutdown", "error"),
 * "disconnected" (Moonraker answers 503: it has no Klipper) or "unreachable" (nobody answers: Moonraker or the
 * Raspberry is down, or busy; this says nothing about Klipper).
 */
async function readKlipper() {
  try {
    const response = await moonraker.printerInfo({ timeout: KLIPPER_INFO_TIMEOUT_MS });
    if (response.status === 503) return { phase: "disconnected", message: null };
    if (!response.ok) return { phase: "unreachable" };
    const info = (await response.json()).result || {};
    if (!["ready", "startup", "shutdown", "error"].includes(info.state)) return { phase: "unreachable" };
    const message = typeof info.state_message === "string" ? info.state_message.trim() : "";
    return { phase: info.state, message: message || null };
  } catch (error) {
    return { phase: "unreachable" };
  }
}

/** Klipper's RESTART / FIRMWARE_RESTART through Moonraker's endpoint, the G-code as fallback. Resolves null, or the reason it failed. */
async function requestKlipperRestart(firmware) {
  try {
    const response = await (firmware ? moonraker.firmwareRestart() : moonraker.klipperRestart());
    if (response.ok) return null;
  } catch (error) {}
  try {
    const response = await sendGcode(firmware ? "FIRMWARE_RESTART" : "RESTART");
    return response.ok ? null : await errorMessageOf(response);
  } catch (error) {
    return error.message || tx("printer not reachable");
  }
}

/**
 * The state machine behind the panel, kept out of React so that it reads top to bottom.
 * `publish(view)` is called whenever what the panel shows changes; the view is null (nothing to show) or
 *   { hostOff: true }                                     the Raspberry was told to shut down
 *   { restart: { label }, phase }                          a restart is under way; `phase` is what was last seen
 *   { phase, message, waiting }                            Klipper is not ready (`waiting`: probably just restarting)
 */
function createKlipperWatch(publish) {
  let alive = false;
  let phase = "ready"; // what Klipper last said (an answer that says nothing about Klipper leaves it alone)
  let message = null;
  let disconnectedSince = 0;
  let restart = null; // the restart this dashboard started: { label, limit, grace, reload, startedAt, sawDown, seen }
  let finishing = null; // the restart worked and the page is about to reload
  let hostOff = 0; // when the Raspberry was told to shut down (0: no)
  let hostWentDown = false;
  let alertUntil = 0;
  let newestShutdownLine = 0;
  let timer = 0;
  let loop = 0; // identifies the current checking loop, so that a cancelled one does not reschedule
  let readNumber = 0; // only the newest reading counts
  let shown = "null";
  let stopListening = noop; // unsubscribes from "the page is back" (app/15-live.js)

  const view = () => {
    if (hostOff) return { hostOff: true };
    if (finishing) return { restart: { label: finishing }, phase: "ready" };
    if (restart) return { restart: { label: restart.label }, phase: restart.seen };
    if (phase === "ready") return null;
    const waiting = phase === "disconnected" && Date.now() - disconnectedSince < KLIPPER_DISCONNECTED_PATIENCE_MS;
    return { phase, message, waiting };
  };

  const emit = () => {
    const next = view();
    const signature = JSON.stringify(next);
    if (signature === shown) return;
    shown = signature;
    publish(next);
  };

  const announceReady = () => klipperReadyListeners.forEach((listener) => listener());

  /** The restart is over: it worked (Klipper is ready and was seen going down), or it did not and the panel shows why. */
  const endRestart = () => {
    const done = restart;
    restart = null;
    if ((phase === "ready" || (done.anyAnswer && phase === "disconnected")) && done.sawDown) {
      if (done.reload) {
        finishing = tx("Klipper is ready again: reloading the page");
        setTimeout(() => location.reload(), KLIPPER_RELOAD_DELAY_MS);
      } else announceReady();
    }
  };

  const apply = (result) => {
    const now = Date.now();
    if (result.phase === "unreachable") {
      if (restart) {
        restart.sawDown = true;
        restart.seen = "unreachable";
        restart.gone = true; // nobody answered: the program really went away
      }
      if (hostOff) hostWentDown = true;
    } else {
      const before = phase;
      phase = result.phase;
      message = result.message;
      if (phase === "disconnected" && before !== "disconnected") disconnectedSince = now;
      if (hostOff && (hostWentDown || now - hostOff > HOST_OFF_LIMIT_MS)) hostOff = 0;
      if (restart) {
        restart.seen = phase;
        if (phase === "startup" || phase === "disconnected") restart.sawDown = true;
        const settled = phase === "ready" || phase === "shutdown" || phase === "error" || (restart.anyAnswer && phase === "disconnected" && (restart.gone || now - restart.startedAt >= restart.grace));
        if (settled && (restart.sawDown || now - restart.startedAt >= restart.grace)) endRestart();
      } else if (before !== "ready" && phase === "ready" && !finishing) announceReady();
    }
    if (restart && now - restart.startedAt > restart.limit) restart = null; // nobody came back: show what is known
    emit();
  };

  const check = async () => {
    const mine = ++readNumber;
    const result = await readKlipper();
    if (alive && mine === readNumber) apply(result);
  };

  const delay = () => {
    if (restart || hostOff) return KLIPPER_WATCH_MS.restarting;
    if (Date.now() < alertUntil) return KLIPPER_WATCH_MS.alert;
    return phase === "ready" ? KLIPPER_WATCH_MS.ready : KLIPPER_WATCH_MS.fault;
  };

  const tick = async () => {
    const mine = loop;
    if (!pageIsHidden()) await check(); // nobody is looking: no need to ask
    if (mine === loop && alive) timer = setTimeout(tick, delay());
  };

  /** Asks again after `ms`, whatever the rhythm was. */
  const kick = (ms = 0) => {
    loop += 1;
    clearTimeout(timer);
    if (alive) timer = setTimeout(tick, ms);
  };

  /** A restart starts here: the ring appears at once, before Klipper has even gone down. */
  const begin = (kind) => {
    restart = { ...RESTART_KINDS[kind], startedAt: Date.now(), sawDown: false, seen: "" };
    finishing = null;
    emit();
    kick(KLIPPER_WATCH_MS.restarting);
  };

  /** The request did not go through: no restart is under way after all. */
  const abandon = (reason) => {
    restart = null;
    emit();
    toast.action(reason);
    kick(0);
  };

  /** Runs `request` for a restart of `kind`; Moonraker and the Raspberry cut the connection themselves, which is no failure. */
  const startRestart = async (kind, request, expectsCutConnection) => {
    if (restart || finishing) return;
    begin(kind);
    try {
      const outcome = await request();
      if (typeof outcome === "string") return abandon(tx("Restart failed: ") + outcome);
      // Moonraker restarting itself (or the machine) often cuts the answer off: a 5xx or no answer is expected then, a refusal (4xx) is not
      const refused = outcome && outcome.ok === false && (!expectsCutConnection || outcome.status < 500);
      if (refused) return abandon(tx("Restart failed: ") + (await errorMessageOf(outcome)));
    } catch (error) {
      if (!expectsCutConnection) return abandon(tx("Restart failed: ") + (error.message || tx("no answer")));
    }
    return undefined;
  };

  return {
    start() {
      alive = true;
      stopListening = onResume(() => kick(0)); // back from a sleep: ask at once
      kick(0);
    },
    stop() {
      alive = false;
      stopListening();
      clearTimeout(timer);
    },

    /** Klipper's RESTART (`firmware` false) or FIRMWARE_RESTART. */
    restartKlipper(firmware) {
      return startRestart(firmware ? "firmware" : "klipper", () => requestKlipperRestart(firmware), false);
    },
    /**
     * A systemd service of the Raspberry: "restart", "start" or "stop". Only Klipper's and Moonraker's take the panel's
     * ring (resolves undefined); for the others it resolves true when the request went through, false when it did not.
     */
    async serviceAction(action, service) {
      const kind = action !== "stop" ? SERVICE_RESTART_KIND[service] : null;
      const send = () => moonraker.serviceAction(action, service);
      if (kind) return startRestart(kind, send, CUTS_CONNECTION.includes(service));
      try {
        const response = await send();
        if (!response.ok) {
          toast.action(tx("Failed: ") + (await errorMessageOf(response)));
          return false;
        }
        if (service === "klipper") kick(0); // stopped: the panel says so soon
        return true;
      } catch (error) {
        toast.action(tx("Failed: ") + (error.message || tx("no answer")));
        return false;
      }
    },
    rebootHost() {
      return startRestart("host", () => moonraker.rebootHost(), true);
    },
    async shutdownHost() {
      try {
        const response = await moonraker.shutdownHost();
        if (!response.ok && response.status < 500) return toast.action(tx("Shutdown failed: ") + (await errorMessageOf(response)));
      } catch (error) {
        // the connection may drop as the machine goes down
      }
      hostOff = Date.now();
      hostWentDown = false;
      emit();
      kick(KLIPPER_WATCH_MS.restarting);
      return undefined;
    },
    /** Klipper restarts by itself soon (SAVE_CONFIG): show the ring at once. */
    expectRestart() {
      if (restart || finishing) return;
      begin("save");
    },
    /** Something may shut Klipper down: look closely for a few seconds. */
    watchClosely() {
      alertUntil = Date.now() + KLIPPER_ALERT_MS;
      kick(KLIPPER_WATCH_MS.alert / 2);
    },
    /** The console store (or a websocket batch): a new shutdown line asks Klipper at once. */
    noteConsole(store) {
      let newest = 0;
      for (const entry of store) {
        const text = (entry.message || "").toLowerCase();
        if (text && isShutdownMessage(text) && (entry.time || 0) > newest) newest = entry.time || 0;
      }
      if (newest > newestShutdownLine) {
        newestShutdownLine = newest;
        kick(0);
      }
    },
  };
}

/** The panel's state, and what can be done to it. Everything but `view` keeps its identity from one render to the next. */
function useKlipperState() {
  const [view, setView] = useState(null);
  const watch = useRef(null);
  if (!watch.current) watch.current = createKlipperWatch(setView);
  useEffect(() => {
    watch.current.start();
    return () => watch.current.stop();
  }, []);

  const actions = watch.current;
  /** Emergency stop: brief pause, M112 + emergency_stop, then Klipper's own message is looked for. */
  const emergencyStop = async () => {
    await sleep(100);
    moonraker.emergencyStop().catch(noop);
    fireGcode("M112");
    actions.watchClosely();
  };
  return { view, emergencyStop, evaluateConsoleStore: actions.noteConsole, restartKlipper: actions.restartKlipper, serviceAction: actions.serviceAction, rebootHost: actions.rebootHost, shutdownHost: actions.shutdownHost, expectRestart: actions.expectRestart };
}

/* ---------------------------------------------------------------------------
   The panel
   ------------------------------------------------------------------------- */

/** Mainsail's colours and symbols by state: startup blue, shutdown orange, error red, disconnected grey. */
const KLIPPER_STATE_STYLE = {
  startup: { tone: "info", icon: () => h(Icons.Rocket) },
  shutdown: { tone: "warn", icon: () => h(Icons.Warning) },
  error: { tone: "error", icon: () => h(Icons.Warning) },
  disconnected: { tone: "neutral", icon: () => h(Icons.Plug) },
};

/** The indeterminate ring (Mainsail's v-progress-circular): a dash that chases its tail. */
function LoadingRing({ size = 30 }) {
  return h("svg", { className: "klipper-state__ring", width: size, height: size, viewBox: "0 0 36 36", "aria-hidden": "true" }, h("circle", { cx: "18", cy: "18", r: "14" }));
}

/** What the ring panel says under its title, by what was last seen of the machine. */
const RESTART_DETAIL = {
  startup: tx("Klipper is starting..."),
  disconnected: tx("Klipper is reconnecting to Moonraker..."),
  unreachable: tx("Waiting for the Raspberry to answer again..."),
};
const RESTART_DETAIL_DEFAULT = tx("Waiting for Klipper to answer...");
const DISCONNECTED_HELP = tx("Moonraker cannot connect to Klipper! Check that the Klipper service is running and that klippy_uds_address is set correctly in moonraker.conf.");

/** `state` is what useKlipperState returns. Look and layout: css/35-klipper-state.css. */
function KlipperStateBanner({ state }) {
  const { view } = state;
  if (!view) return null;

  let tone = "neutral";
  let icon = h(Icons.Power);
  let title;
  let body = null;
  let loading = false;
  let actions = null;

  if (view.hostOff) {
    title = tx("The Raspberry is shutting down");
    body = h("div", { className: "klipper-state__text" }, tx("Once it is off the dashboard stops answering. To turn it on again, unplug and plug the power back in."));
  } else if (view.restart) {
    tone = "info";
    loading = true;
    title = view.restart.label + "...";
    body = h("div", { className: "klipper-state__text" }, RESTART_DETAIL[view.phase] || RESTART_DETAIL_DEFAULT);
  } else {
    const style = KLIPPER_STATE_STYLE[view.phase] || KLIPPER_STATE_STYLE.error;
    tone = style.tone;
    icon = style.icon();
    const disconnected = view.phase === "disconnected";
    title = (disconnected ? "Moonraker" : "Klipper") + tx(" reports: ") + view.phase.toUpperCase();
    // Mainsail: the ring stands in for a message that has not arrived yet
    loading = view.waiting || view.phase === "startup" || (!disconnected && view.message === null);
    if (view.waiting) body = h("div", { className: "klipper-state__text" }, tx("Klipper is restarting or reconnecting to Moonraker..."));
    else if (disconnected) body = h("div", { className: "klipper-state__text" }, DISCONNECTED_HELP);
    else if (view.message !== null) body = h("pre", { className: "klipper-state__message" }, view.message);

    if (!view.waiting) {
      actions = h(
        "div",
        { className: "klipper-state__actions" },
        !disconnected && h("button", { className: "oui-btn oui-btn--primary oui-btn--sm", onClick: () => state.restartKlipper(true) }, h(Icons.RotateCw, { size: 16 }), "Firmware restart"),
        !disconnected && h("button", { className: "oui-btn oui-btn--sm", onClick: () => state.restartKlipper(false) }, h(Icons.RotateCw, { size: 16 }), "Klipper restart"),
        disconnected && h("button", { className: "oui-btn oui-btn--primary oui-btn--sm", onClick: () => state.serviceAction("restart", "klipper") }, h(Icons.RotateCw, { size: 16 }), tx("Restart the Klipper service")),
        !disconnected && h("button", { className: "oui-btn oui-btn--sm", onClick: () => logsApi.download("klippy.log") }, h(Icons.Download, { size: 16 }), tx("Klipper log")),
        h("button", { className: "oui-btn oui-btn--sm", onClick: () => logsApi.download("moonraker.log") }, h(Icons.Download, { size: 16 }), tx("Moonraker log")),
      );
    }
  }

  return h(
    "div",
    { className: cx("klipper-state", loading && "is-loading"), "data-tone": tone, role: loading ? "status" : "alert" },
    h(
      "div",
      { className: "klipper-state__card" },
      h("div", { className: "klipper-state__head" }, h("div", { className: "klipper-state__icon" }, loading ? h(LoadingRing) : icon), h("div", { className: "klipper-state__title" }, title)),
      body,
      actions,
    ),
  );
}
