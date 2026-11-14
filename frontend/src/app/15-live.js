/* ============================================================================
   15 · LIVE
   Keeps the dashboard live when the phone goes to sleep or the page to the
   background. What goes wrong, and what this file does about it:

     · A sleeping phone's connections to the printer die without a sound. A request sent on one gets no answer,
       and no error either; the browser keeps only six connections to one address, so six such requests and
       nothing else of the page goes out any more. → every read has a time limit (fetchFresh, app/12-api.js), and
       coming back cancels the reads still waiting and tests the connections with a few small requests, which
       throws the dead ones away.
     · Nothing started again by itself. → the pollers (startPolling) run at once when the page comes back; anything
       else that wants to know (the console socket, the camera) subscribes with onResume.
     · A page that is not visible has no use for fresh data. → startPolling does not poll while the page is hidden.
     · Some WebViews do not tell the page that it was away. → a clock check notices that time jumped (timers were
       frozen) and counts it as coming back.
     · 1.126: a page left open in front of the person could stop all the same (a connection asleep in the middle of
       an answer, a poller waiting on it for ever), and coming back did not always bring it to life. → the bodies
       have a time limit too (watchBody, app/12-api.js), a poller drops a run that takes far too long, and a
       watchdog notices when no answer at all has arrived for a while: it runs the coming back by itself, shows
       «Reconnecting…», and reloads the page when the printer answers again but the page still gets nothing. Away
       for long (LIVE_RELOAD_AFTER_AWAY_MS), the page is reloaded at once. Never with unsaved changes (holdPage),
       never twice in a row within a minute, never while the printer does not answer (it says so and tries again).
   ========================================================================== */

/** Away for at least this long and the connections are suspect: they are tested, the dead ones are thrown away. */
const LIVE_STALE_AFTER_MS = 3000;
/** A browser keeps up to six connections to one address and any of them may be the dead one: test them all. */
const LIVE_PROBES = 6;
const LIVE_PROBE_TIMEOUT_MS = 1500;
/** The clock check: this much more time than expected between two ticks means the page was frozen. */
const LIVE_TICK_MS = 1000;
const LIVE_FROZEN_GAP_MS = 4000;
/** Several signals arrive together on coming back (visible, focus, online...): the first one counts. */
const LIVE_RESUME_DEBOUNCE_MS = 800;

/** 1.126: the tests shorten the watchdog's times (localStorage "klippeye.live.scale", e.g. 0.1); 1 otherwise. */
const LIVE_SCALE = (() => {
  try {
    const scale = Number(localStorage.getItem("klippeye.live.scale"));
    return scale > 0 && scale <= 1 ? scale : 1;
  } catch (error) {
    return 1;
  }
})();
/** 1.126: no answer at all for this long while the page is in front: the watchdog runs the coming back by itself... */
const LIVE_QUIET_MS = 15000 * LIVE_SCALE;
/** 1.126: a poller's run this long (at least) is taken as stuck and dropped. */
const LIVE_RUN_STUCK_MS = 20000 * LIVE_SCALE;
/** ...and if answers still do not come this long after, the page is reloaded (when the printer answers a probe). */
const LIVE_RELOAD_QUIET_MS = 45000 * LIVE_SCALE;
/** Away for this long, the page is reloaded on coming back instead of brought back to life (when the printer answers). */
const LIVE_RELOAD_AFTER_AWAY_MS = 10 * 60 * 1000 * LIVE_SCALE;
/** Not two reloads of its own within this long (a page that keeps failing: the person decides). */
const LIVE_RELOAD_GAP_MS = 60000 * LIVE_SCALE;
/** How often the watchdog looks; while the printer does not answer, the probes are spaced out up to the last. */
const LIVE_WATCH_MS = Math.max(200, 2000 * LIVE_SCALE);
const LIVE_PROBE_BACKOFF_MS = [5000, 10000, 20000, 40000, 60000].map((ms) => ms * LIVE_SCALE);
const LIVE_RELOADED_KEY = "klippeye.live.reloaded";

let lastAnswer = Date.now(); // when an answer (any status, body read to the end) last arrived
/** Called by the reads (app/12-api.js) when an answer has arrived whole. */
const liveAnswered = () => {
  lastAnswer = Date.now();
};

const pageHolds = new Set();
/** 1.126: `on`: something that would be lost (unsaved changes) holds the page: the dashboard does not reload itself. */
function holdPage(key, on) {
  if (on) pageHolds.add(key);
  else pageHolds.delete(key);
}

const resumeListeners = new Set();
let hiddenAt = 0; // when the page went to the background (0: it is in front, or was never seen going away)

/**
 * True while the page is in the background. Only a page that was seen going away counts: one that opens hidden, or a
 * WebView that wrongly says so, keeps polling as it always did.
 */
const pageIsHidden = () => hiddenAt !== 0;

/** Calls `callback({ away })` (away: ms) when the page is back in front, awake, or online again. Returns the function that unsubscribes. */
function onResume(callback) {
  resumeListeners.add(callback);
  return () => resumeListeners.delete(callback);
}

/** True when `info` (what onResume passes) says the page was away long enough to distrust what it holds. */
const wasAwayLong = (info, ms = LIVE_STALE_AFTER_MS) => info.away >= ms;

/** Small requests, as many as a browser has connections: the ones that land on a dead connection time out and take it away. */
function testConnections() {
  const probe = () =>
    fetchFresh("/printer/info", { timeout: LIVE_PROBE_TIMEOUT_MS })
      .then((response) => response.text()) // read the answer to the end: an unread one keeps its connection busy
      .catch(noop);
  return Promise.all(Array.from({ length: LIVE_PROBES }, probe));
}

(function watchForResume() {
  let lastTick = Date.now();
  let lastResume = 0;

  const resumed = async (away) => {
    const now = Date.now();
    if (now - lastResume < LIVE_RESUME_DEBOUNCE_MS) return;
    lastResume = now;
    // 1.126: away for long: what the page holds is old anyway, a fresh page is quicker and surer
    if (away >= LIVE_RELOAD_AFTER_AWAY_MS && (await reloadIfAnswering("away"))) return;
    abortReadsInFlight();
    if (away >= LIVE_STALE_AFTER_MS) await testConnections();
    resumeListeners.forEach((callback) => {
      try {
        callback({ away });
      } catch (error) {}
    });
  };
  watchAnswers(resumed);

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      hiddenAt = Date.now();
      return;
    }
    const away = Date.now() - (hiddenAt || lastTick);
    hiddenAt = 0;
    resumed(away);
  });
  // a page brought back from the back/forward cache, a page "thawed" by the browser, a network that came back
  window.addEventListener("pageshow", (event) => event.persisted && resumed(Math.max(Date.now() - lastTick, LIVE_STALE_AFTER_MS)));
  document.addEventListener("resume", () => resumed(Math.max(Date.now() - lastTick, LIVE_STALE_AFTER_MS)));
  window.addEventListener("online", () => resumed(LIVE_STALE_AFTER_MS));

  // the clock check, for the WebViews that say nothing
  setInterval(() => {
    const now = Date.now();
    const gap = now - lastTick;
    lastTick = now;
    if (gap > LIVE_FROZEN_GAP_MS && !pageIsHidden()) resumed(gap);
  }, LIVE_TICK_MS);
})();

/* ---------------------------------------------------------------------------
   1.126 · The watchdog
   ------------------------------------------------------------------------- */

/** Whether the printer's web server answers at all (any status): a small read of its own, outside the six connections' queue. */
async function printerAnswers() {
  try {
    const response = await fetch("/server/info?probe=" + Date.now(), { cache: "no-store", signal: AbortSignal.timeout ? AbortSignal.timeout(4000) : undefined });
    await response.text();
    return true;
  } catch (error) {
    return false;
  }
}

/** Reloads the page if nothing holds it, it did not reload itself a moment ago and the printer answers. -> whether it did. */
async function reloadIfAnswering(why) {
  if (pageHolds.size) return false;
  let last = 0;
  try {
    last = Number(sessionStorage.getItem(LIVE_RELOADED_KEY)) || 0;
  } catch (error) {}
  if (Date.now() - last < LIVE_RELOAD_GAP_MS) return false;
  if (!(await printerAnswers())) return false;
  try {
    sessionStorage.setItem(LIVE_RELOADED_KEY, String(Date.now()));
  } catch (error) {}
  liveBanner("reloading");
  console.info("[live] reloading the page:", why);
  window.location.reload();
  return true;
}

/** The thin strip at the top while the watchdog works: "reconnecting", "unreachable", "reloading" or null. Plain DOM:
 * it shows also when the rest of the page is stuck. */
function liveBanner(state) {
  let strip = document.getElementById("live-banner");
  if (!state) {
    if (strip) strip.remove();
    return;
  }
  if (!strip) {
    strip = document.createElement("div");
    strip.id = "live-banner";
    strip.className = "live-banner";
    strip.setAttribute("role", "status");
    document.body.appendChild(strip);
  }
  strip.dataset.state = state;
  strip.textContent =
    state === "unreachable" ? tx("The printer does not answer: trying again…") : state === "reloading" ? tx("Reloading the page…") : tx("Reconnecting…");
}

/** Looks every LIVE_WATCH_MS, only while the page is in front. */
function watchAnswers(resumed) {
  let acted = 0; // when it last ran the coming back by itself (0: not since the last answer)
  let nextProbe = 0;
  let probes = 0;
  setInterval(async () => {
    if (pageIsHidden() || document.hidden) return;
    const now = Date.now();
    const quiet = now - lastAnswer;
    if (quiet < LIVE_QUIET_MS) {
      if (acted) liveBanner(null);
      acted = nextProbe = probes = 0;
      return;
    }
    if (!acted) {
      acted = now;
      liveBanner("reconnecting");
      resumed(quiet);
      return;
    }
    if (now - acted < LIVE_RELOAD_QUIET_MS - LIVE_QUIET_MS || now < nextProbe) return;
    if (await reloadIfAnswering("no answers for " + Math.round(quiet / 1000) + " s")) return;
    // the printer does not answer (or the page may not reload now): say so, try again later and further apart
    const answers = await printerAnswers();
    liveBanner(answers ? "reconnecting" : "unreachable");
    nextProbe = Date.now() + LIVE_PROBE_BACKOFF_MS[Math.min(probes, LIVE_PROBE_BACKOFF_MS.length - 1)];
    probes += 1;
    if (answers) resumed(quiet);
  }, LIVE_WATCH_MS);
}

/**
 * Runs `poll` now and then every `ms`, one run at a time, but not while the page is hidden; when the page comes
 * back it runs at once. A failing poll is simply tried again at the next tick. Returns the function that stops it.
 * 1.126: a run that takes far too long (LIVE_RUN_STUCK_MS, or three ticks) is dropped: the next tick runs again.
 */
function startPolling(poll, ms) {
  let stopped = false;
  let running = 0; // id of the run in progress (0: none)
  let startedAt = 0;
  let ids = 0;
  const stuckAfter = Math.max(LIVE_RUN_STUCK_MS, 3 * ms);
  const run = async () => {
    if (stopped || pageIsHidden()) return;
    if (running && Date.now() - startedAt < stuckAfter) return;
    const mine = ++ids;
    running = mine;
    startedAt = Date.now();
    try {
      await poll();
    } catch (error) {
    } finally {
      if (running === mine) running = 0;
    }
  };
  run();
  const timer = setInterval(run, ms);
  const stopListening = onResume(() => {
    running = 0; // a run that was waiting on a dead connection has just been cancelled
    run();
  });
  return () => {
    stopped = true;
    clearInterval(timer);
    stopListening();
  };
}
