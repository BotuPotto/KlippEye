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
    abortReadsInFlight();
    if (away >= LIVE_STALE_AFTER_MS) await testConnections();
    resumeListeners.forEach((callback) => {
      try {
        callback({ away });
      } catch (error) {}
    });
  };

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

/**
 * Runs `poll` now and then every `ms`, one run at a time, but not while the page is hidden; when the page comes
 * back it runs at once. A failing poll is simply tried again at the next tick. Returns the function that stops it.
 */
function startPolling(poll, ms) {
  let stopped = false;
  let running = 0; // id of the run in progress (0: none)
  let ids = 0;
  const run = async () => {
    if (stopped || running || pageIsHidden()) return;
    const mine = ++ids;
    running = mine;
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
