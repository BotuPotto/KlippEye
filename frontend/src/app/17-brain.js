/* ============================================================================
   17 · BRAIN
   What the dashboard asks the backend (the KlippEye program on the Raspberry that serves this very page) about itself, as
   opposed to Moonraker:
     · who it is           /api/version        release, interface level, commit, since when it runs
     · its monitor limits  /api/backend/config   the thresholds of the AI monitor, with labels and bounds (the backend
                                               describes its own settings: a new one shows up in the menu by itself)
     · coming back         after an update or a restart the backend is away for a few seconds: waitForBrain()
   A backend older than release 1.0 has none of this (its answer is 404): the helpers call that "old", so that the menus can
   say "update the backend" instead of failing.
   ========================================================================== */

/** Written by build.py from the VERSION file of the release; stays as it is when the page is built by hand. */
const DASHBOARD_RELEASE = "__KLIPPEYE_RELEASE__";
const dashboardRelease = () => (DASHBOARD_RELEASE.startsWith("__") ? "sviluppo" : DASHBOARD_RELEASE);

/** The interface level this page needs from the backend (the backend says its own in /api/version). */
const BRAIN_API_LEVEL = 2;
const BRAIN_READ_TIMEOUT_MS = 5000;
const BRAIN_WRITE_TIMEOUT_MS = 12000;
const BRAIN_POLL_MS = 15000;
const BRAIN_SAVE_DELAY_MS = 600; // changes closer than this are sent as one
const BRAIN_WAIT_POLL_MS = 1500;
const BRAIN_WAIT_LIMIT_MS = 150000;
const BRAIN_NO_RESTART_MS = 25000; // a backend that stayed up this long after the work was done was not restarted

/** The backend sees a web page of release `a` and itself of release `b`: worth a hint to reload when they differ. */
const releasesDiffer = (brainRelease) => Boolean(brainRelease) && dashboardRelease() !== "sviluppo" && brainRelease !== "sviluppo" && brainRelease !== dashboardRelease();

/**
 * Asks who the backend is. { state: "ok", info } | { state: "old" } (answers, but knows nothing of releases)
 * | { state: "down" } (no answer, or an error).
 */
async function readBrainVersion(options) {
  try {
    const response = await fetchFresh("/api/version", { timeout: BRAIN_READ_TIMEOUT_MS, ...options });
    if (response.status === 404) return { state: "old" };
    if (!response.ok) return { state: "down" };
    const info = await response.json();
    if (!isPlainObject(info) || !info.release) return { state: "old" };
    return { state: "ok", info };
  } catch (error) {
    return { state: "down" };
  }
}

/** { state, info } of readBrainVersion, read every few seconds while `active`. `reload()` asks at once. */
function useBrainVersion(active = true) {
  const [version, setVersion] = useState({ state: "loading" });
  const reloadRef = useRef(noop);
  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    const read = async () => {
      const answer = await readBrainVersion();
      if (!cancelled) setVersion(answer);
    };
    reloadRef.current = read;
    const stop = startPolling(read, BRAIN_POLL_MS);
    return () => {
      cancelled = true;
      stop();
    };
  }, [active]);
  return { ...version, reload: () => reloadRef.current() };
}

/**
 * Waits until the backend answers again after it was restarted (by an update, a restart or a rollback). `before` is what
 * readBrainVersion() said just before: a backend that started at another moment, or with another release, is the new one.
 * `settled()` (optional) tells whether the work that should have restarted the backend is done (it resolves true): if the backend
 * has stayed up, untouched, for BRAIN_NO_RESTART_MS and the work is done, the restart did not happen by itself.
 * Resolves { ok: true, info, restarted } or { ok: false } after BRAIN_WAIT_LIMIT_MS. `onTick(seconds)` reports the time spent waiting.
 */
async function waitForBrain(before, onTick = noop, settled = null) {
  const started = Date.now();
  const knownStart = before && before.state === "ok" ? before.info.started : null;
  const knownRelease = before && before.state === "ok" ? before.info.release : null;
  let upSince = 0;
  while (Date.now() - started < BRAIN_WAIT_LIMIT_MS) {
    await sleep(BRAIN_WAIT_POLL_MS);
    onTick(Math.round((Date.now() - started) / 1000));
    const now = await readBrainVersion();
    if (now.state !== "ok") {
      upSince = 0;
      continue;
    }
    if (knownStart === null || now.info.started !== knownStart || now.info.release !== knownRelease) return { ok: true, info: now.info, restarted: true };
    upSince = upSince || Date.now();
    if (settled && Date.now() - upSince > BRAIN_NO_RESTART_MS && (await settled()) === true) return { ok: true, info: now.info, restarted: false };
  }
  return { ok: false };
}

/* ---------------------------------------------------------------------------
   The thresholds of the AI monitor
   ------------------------------------------------------------------------- */

/** One read of /api/backend/config: { state: "ok", data } | { state: "old" } | { state: "down" }. */
async function readBrainConfig() {
  try {
    const response = await fetchFresh("/api/backend/config", { timeout: BRAIN_READ_TIMEOUT_MS });
    if (response.status === 404) return { state: "old" };
    if (!response.ok) return { state: "down" };
    const data = await response.json();
    if (!isPlainObject(data) || !Array.isArray(data.spec) || !isPlainObject(data.values)) return { state: "old" };
    return { state: "ok", data };
  } catch (error) {
    return { state: "down" };
  }
}

/** POST to the backend; resolves { ok, data (the backend's answer, parsed), message }. A network failure is { ok: false, data: null }. */
async function brainPost(url, body) {
  try {
    const response = await fetch(url, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body), signal: AbortSignal.timeout ? AbortSignal.timeout(BRAIN_WRITE_TIMEOUT_MS) : undefined });
    let data = null;
    try {
      data = await response.json();
    } catch (error) {}
    return { ok: response.ok && !(data && data.ok === false), data, message: (data && data.error) || (response.ok ? "" : "HTTP " + response.status) };
  } catch (error) {
    return { ok: false, data: null, message: tx("the backend does not answer") };
  }
}

/** "35" -> "35 %": a value with the unit of its setting. */
const withUnit = (spec, value) => String(value).replace(".", ",") + (spec.unit ? (/^[%°]/.test(spec.unit) ? "" : " ") + spec.unit : "");

/**
 * The thresholds as the backend has them, ready for a menu:
 *   { phase: "loading" | "ok" | "old" | "down", data (groups, spec, defaults, running...), values (what the backend has,
 *     plus the changes still on their way), errors { key: why the backend refused it }, problem (a text, or ""), set(changes), reset(keys) }
 * A change shows at once, goes to the backend a moment later (several together as one) and is read back from its answer.
 */
function useBrainConfig(active) {
  const [phase, setPhase] = useState("loading");
  const [data, setData] = useState(null);
  const [edits, setEdits] = useState({}); // changes made here and not yet confirmed by the backend
  const [errors, setErrors] = useState({});
  const [problem, setProblem] = useState("");
  const waiting = useRef({}); // changes not sent yet
  const sending = useRef(false);
  const timer = useRef(0);
  const alive = useRef(true);
  const flushRef = useRef(noop);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      clearTimeout(timer.current);
      if (Object.keys(waiting.current).length) flushRef.current(); // the menu closed with a change on its way: it still goes
    };
  }, []);

  const take = (reply) => {
    if (!alive.current || !reply.data || !isPlainObject(reply.data.values)) return;
    setData((previous) => ({ ...(previous || {}), ...reply.data }));
  };

  const load = async () => {
    if (sending.current || Object.keys(waiting.current).length) return; // our own change is on its way: its answer is newer
    const answer = await readBrainConfig();
    if (!alive.current) return;
    if (answer.state === "ok") {
      setPhase("ok");
      setData(answer.data);
      setProblem("");
    } else if (answer.state === "old") setPhase("old");
    else setPhase((previous) => (previous === "ok" ? previous : "down")); // a short silence of a working backend is not worth a warning
  };

  useEffect(() => {
    if (!active) return undefined;
    return startPolling(load, BRAIN_POLL_MS);
  }, [active]);

  const flush = async () => {
    if (sending.current) return; // the answer to the one in flight sends what has gathered since
    const changes = waiting.current;
    if (!Object.keys(changes).length) return;
    waiting.current = {};
    sending.current = true;
    const reply = await brainPost("/api/backend/config", { values: changes });
    sending.current = false;
    if (alive.current) {
      take(reply);
      if (reply.ok) {
        setErrors((previous) => Object.fromEntries(Object.entries(previous).filter(([key]) => !(key in changes))));
        setProblem(reply.data && reply.data.save_error ? tx("The backend accepted the thresholds but cannot write them to disk (") + reply.data.save_error + tx("): after a restart the previous ones come back.") : "");
      } else if (reply.data && isPlainObject(reply.data.errors)) {
        setErrors((previous) => ({ ...previous, ...reply.data.errors }));
        setProblem("");
      } else setProblem(tx("The change was not saved: ") + (reply.message || tx("the backend does not answer")) + ".");
      setEdits((previous) => Object.fromEntries(Object.entries(previous).filter(([key]) => key in waiting.current)));
    }
    if (Object.keys(waiting.current).length) flush();
  };
  flushRef.current = flush;

  const set = (changes) => {
    waiting.current = { ...waiting.current, ...changes };
    setEdits((previous) => ({ ...previous, ...changes }));
    setErrors((previous) => Object.fromEntries(Object.entries(previous).filter(([key]) => !(key in changes))));
    clearTimeout(timer.current);
    timer.current = setTimeout(flush, BRAIN_SAVE_DELAY_MS);
  };

  const reset = async (keys) => {
    clearTimeout(timer.current);
    waiting.current = {};
    setEdits({});
    setErrors({});
    const reply = await brainPost("/api/backend/config/reset", keys ? { keys } : {});
    if (!alive.current) return;
    take(reply);
    setProblem(reply.ok ? "" : tx("The reset did not work: ") + (reply.message || tx("the backend does not answer")) + ".");
  };

  const values = { ...(data ? data.values : {}), ...edits };
  return { phase, data, values, errors, problem, set, reset };
}
